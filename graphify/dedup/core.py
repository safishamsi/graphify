from __future__ import annotations
import re
from collections import defaultdict
from datasketch import MinHashLSH
from rapidfuzz.distance import JaroWinkler
from .metrics import _norm, _entropy, _make_minhash, _is_variant_pair, _short_label_blocked
class _UF:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self._parent.setdefault(x, x)
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, x: str, y: str) -> None:
        self._parent.setdefault(x, x)
        self._parent.setdefault(y, y)
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._parent[ry] = rx

    def components(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = defaultdict(list)
        for x in self._parent:
            groups[self.find(x)].append(x)
        return dict(groups)


# ── constants ─────────────────────────────────────────────────────────────────

_ENTROPY_THRESHOLD = 2.5
_LSH_THRESHOLD = 0.7
_MERGE_THRESHOLD = 92.0     # rapidfuzz normalized_similarity * 100
_COMMUNITY_BOOST = 5.0      # score bonus when both nodes share community
_NUM_PERM = 128
_CHUNK_SUFFIX = re.compile(r"_c\d+$")


# ── main entry point ──────────────────────────────────────────────────────────

def deduplicate_entities(
    nodes: list[dict],
    edges: list[dict],
    *,
    communities: dict[str, int],
    dedup_llm_backend: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Deduplicate near-identical entities in a knowledge graph.

    Args:
        nodes: list of node dicts with at minimum {"id": str, "label": str}
        edges: list of edge dicts with {"source": str, "target": str, ...}
        communities: mapping of node_id -> community_id (from cluster())
        dedup_llm_backend: if set, use LLM to resolve ambiguous pairs

    Returns:
        (deduped_nodes, deduped_edges) with edges rewired to survivors
    """
    # Guard: cross-project dedup is not supported — nodes from different repos
    # share label names by coincidence and must never be merged by string similarity.
    # If you need to dedup a global graph, run deduplicate_entities per-repo first.
    repos_seen = {n.get("repo") for n in nodes if n.get("repo")}
    if len(repos_seen) > 1:
        raise ValueError(
            f"deduplicate_entities: nodes span multiple repos {sorted(repos_seen)!r}. "
            f"Cross-project dedup is disabled — run dedup per-repo before merging."
        )

    if len(nodes) <= 1:
        return nodes, edges

    # Pre-deduplicate: keep first occurrence of each id
    seen_ids: dict[str, dict] = {}
    for node in nodes:
        nid = node.get("id", "")
        if nid and nid not in seen_ids:
            seen_ids[nid] = node
    unique_nodes = list(seen_ids.values())

    if len(unique_nodes) <= 1:
        return unique_nodes, edges

    # ── pass 1: exact normalization ───────────────────────────────────────────
    norm_to_nodes: dict[str, list[dict]] = defaultdict(list)
    for node in unique_nodes:
        key = _norm(node.get("label", node.get("id", "")))
        if key:
            norm_to_nodes[key].append(node)

    uf = _UF()
    exact_merges = 0
    for key, group in norm_to_nodes.items():
        if len(group) <= 1:
            continue
        # Partition by source_file — only merge within the same file in Pass 1.
        # Cross-file matches fall through to Pass 2 fuzzy matching.
        by_file: dict[str, list[dict]] = defaultdict(list)
        for node in group:
            sf = node.get("source_file") or ""
            by_file[sf].append(node)
        for file_group in by_file.values():
            if len(file_group) > 1:
                winner = _pick_winner(file_group)
                for node in file_group:
                    uf.union(winner["id"], node["id"])
                exact_merges += len(file_group) - 1

    # ── pass 2: MinHash/LSH + Jaro-Winkler (high-entropy nodes only) ─────────
    candidates: list[dict] = []
    seen_norms: set[str] = set()
    for node in unique_nodes:
        key = _norm(node.get("label", node.get("id", "")))
        if key and key not in seen_norms:
            seen_norms.add(key)
            if _entropy(node.get("label", "")) >= _ENTROPY_THRESHOLD:
                candidates.append(node)

    fuzzy_merges = 0
    if len(candidates) >= 2:
        lsh = MinHashLSH(threshold=_LSH_THRESHOLD, num_perm=_NUM_PERM)
        minhashes: dict[str, MinHash] = {}

        for node in candidates:
            norm_label = _norm(node.get("label", node.get("id", "")))
            m = _make_minhash(norm_label)
            minhashes[node["id"]] = m
            try:
                lsh.insert(node["id"], m)
            except ValueError:
                pass  # duplicate key in LSH — already inserted

        for node in candidates:
            node_id = node["id"]
            norm_label = _norm(node.get("label", node.get("id", "")))
            neighbors = lsh.query(minhashes[node_id])

            for neighbor_id in neighbors:
                if neighbor_id == node_id:
                    continue
                if uf.find(node_id) == uf.find(neighbor_id):
                    continue

                neighbor = next((n for n in candidates if n["id"] == neighbor_id), None)
                if neighbor is None:
                    continue

                neighbor_norm = _norm(neighbor.get("label", neighbor.get("id", "")))
                score = JaroWinkler.normalized_similarity(norm_label, neighbor_norm) * 100

                if _is_variant_pair(norm_label, neighbor_norm):
                    continue
                if _short_label_blocked(norm_label, neighbor_norm, score):
                    continue

                c1 = communities.get(node_id)
                c2 = communities.get(neighbor_id)
                if (c1 is not None and c2 is not None and c1 == c2
                        and min(len(norm_label), len(neighbor_norm)) >= 12):
                    score += _COMMUNITY_BOOST

                if score >= _MERGE_THRESHOLD:
                    all_group = norm_to_nodes.get(norm_label, [node]) + \
                                norm_to_nodes.get(neighbor_norm, [neighbor])
                    winner = _pick_winner(all_group)
                    uf.union(winner["id"], node_id)
                    uf.union(winner["id"], neighbor_id)
                    fuzzy_merges += 1

    # ── pass 3: LLM tiebreaker for ambiguous pairs (opt-in) ──────────────────
    if dedup_llm_backend is not None:
        from .ai import _llm_tiebreak
        _llm_tiebreak(candidates, uf, communities, backend=dedup_llm_backend)

    # ── build remap table from union-find components ──────────────────────────
    components = uf.components()
    remap: dict[str, str] = {}

    for root, members in components.items():
        if len(members) == 1:
            continue
        group_nodes = [n for n in unique_nodes if n["id"] in members]
        winner = _pick_winner(group_nodes) if group_nodes else {"id": root}
        winner_id = winner["id"]
        for member in members:
            if member != winner_id:
                remap[member] = winner_id

    # ── apply remap ───────────────────────────────────────────────────────────
    if not remap:
        return unique_nodes, edges

    total = len(remap)
    msg = f"[graphify] Deduplicated {total} node(s)"
    if exact_merges:
        msg += f" ({exact_merges} exact"
        if fuzzy_merges:
            msg += f", {fuzzy_merges} fuzzy"
        msg += ")"
    print(msg + ".", flush=True)

    deduped_nodes = [n for n in unique_nodes if n["id"] not in remap]
    deduped_edges = []
    for edge in edges:
        e = dict(edge)
        # Tolerate "from"/"to" keys from LLM backends that don't follow the
        # schema exactly — build_from_json normalises later but dedup runs
        # first so bracket access would KeyError here (#803).
        # Use explicit key presence check (not `or`) so empty-string src/tgt
        # aren't silently replaced by the fallback key.
        src = e["source"] if "source" in e else e.get("from")
        tgt = e["target"] if "target" in e else e.get("to")
        if src is None or tgt is None:
            continue
        e["source"] = remap.get(src, src)
        e["target"] = remap.get(tgt, tgt)
        # Remove legacy keys so they don't leak into edge attrs in graph.json.
        e.pop("from", None)
        e.pop("to", None)
        if e["source"] != e["target"]:
            deduped_edges.append(e)

    return deduped_nodes, deduped_edges


def _pick_winner(nodes: list[dict]) -> dict:
    """Pick the canonical survivor: prefer no chunk suffix, then shorter ID."""
    if not nodes:
        raise ValueError("Cannot pick winner from empty list")

    def _score(n: dict) -> tuple[int, int]:
        has_suffix = bool(_CHUNK_SUFFIX.search(n["id"]))
        return (1 if has_suffix else 0, len(n["id"]))

    return min(nodes, key=_score)


# Lazy import of _llm_tiebreak to break circular import

