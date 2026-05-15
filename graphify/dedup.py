"""Entity deduplication pipeline for graphify knowledge graphs.

Pipeline: exact normalization → entropy gate → MinHash/LSH blocking →
Jaro-Winkler verification → same-community boost → union-find merge.
"""
from __future__ import annotations
import math
import re
from collections import defaultdict

from datasketch import MinHash, MinHashLSH
from rapidfuzz.distance import JaroWinkler


# ── helpers ───────────────────────────────────────────────────────────────────

def _norm(label: str) -> str:
    """Lowercase + collapse non-alphanumeric runs to space."""
    return re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()


def _entropy(label: str) -> float:
    """Shannon entropy in bits/char of the normalised label."""
    s = _norm(label)
    if not s:
        return 0.0
    freq: dict[str, int] = defaultdict(int)
    for ch in s:
        freq[ch] += 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _shingles(text: str, k: int = 3) -> set[str]:
    """Return k-gram character shingles of text."""
    if len(text) < k:
        return {text}
    return {text[i : i + k] for i in range(len(text) - k + 1)}


def _make_minhash(text: str, num_perm: int = 128) -> MinHash:
    # Strip spaces so "graph extractor" and "graphextractor" share shingles
    m = MinHash(num_perm=num_perm)
    for shingle in _shingles(text.replace(" ", "")):
        m.update(shingle.encode("utf-8"))
    return m


# ── union-find ────────────────────────────────────────────────────────────────

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
    for key, group in norm_to_nodes.items():
        if len(group) > 1:
            winner = _pick_winner(group)
            for node in group:
                uf.union(winner["id"], node["id"])

    exact_merges = sum(len(g) - 1 for g in norm_to_nodes.values() if len(g) > 1)

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

                c1 = communities.get(node_id)
                c2 = communities.get(neighbor_id)
                if c1 is not None and c2 is not None and c1 == c2:
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


def _llm_tiebreak(
    candidates: list[dict],
    uf: _UF,
    communities: dict[str, int],
    *,
    backend: str,
    batch_size: int = 30,
    low: float = 75.0,
    high: float = 92.0,
) -> None:
    """Batch-resolve ambiguous pairs (score in [low, high)) via LLM."""
    try:
        from graphify.llm import BACKENDS, _format_backend_env_keys, _get_backend_api_key
        if backend not in BACKENDS:
            print(f"[graphify] --dedup-llm: unknown backend {backend!r}, skipping LLM tiebreaker.", flush=True)
            return
        if not _get_backend_api_key(backend):
            env_keys = _format_backend_env_keys(backend)
            print(f"[graphify] --dedup-llm: {env_keys} not set, skipping LLM tiebreaker.", flush=True)
            return
    except ImportError:
        return

    ambiguous: list[tuple[dict, dict, float]] = []
    for i, node in enumerate(candidates):
        norm_i = _norm(node.get("label", node.get("id", "")))
        for j in range(i + 1, len(candidates)):
            neighbor = candidates[j]
            if uf.find(node["id"]) == uf.find(neighbor["id"]):
                continue
            norm_j = _norm(neighbor.get("label", neighbor.get("id", "")))
            score = JaroWinkler.normalized_similarity(norm_i, norm_j) * 100
            c1 = communities.get(node["id"])
            c2 = communities.get(neighbor["id"])
            if c1 is not None and c2 is not None and c1 == c2:
                score += _COMMUNITY_BOOST
            if low <= score < high:
                ambiguous.append((node, neighbor, score))

    if not ambiguous:
        return

    try:
        from graphify.llm import _call_llm
    except ImportError as exc:
        # F-038: previously this silent fallback hid the fact that `_call_llm`
        # didn't exist in `graphify.llm` at all, so `--dedup-llm` was a no-op.
        # Surface the import failure so future regressions are visible.
        print(
            f"[graphify] --dedup-llm: cannot import _call_llm ({exc}); skipping LLM tiebreaker.",
            flush=True,
        )
        return

    for batch_start in range(0, len(ambiguous), batch_size):
        batch = ambiguous[batch_start : batch_start + batch_size]
        pairs_text = "\n".join(
            f"{i+1}. \"{a['label']}\" vs \"{b['label']}\""
            for i, (a, b, _) in enumerate(batch)
        )
        prompt = (
            "For each pair below, answer only 'yes' or 'no': are they the same real-world concept?\n\n"
            f"{pairs_text}\n\n"
            "Reply with one line per pair: '1. yes', '2. no', etc."
        )
        try:
            response = _call_llm(prompt, backend=backend, max_tokens=200)
            lines = response.strip().splitlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(".", 1)
                if len(parts) != 2:
                    continue
                try:
                    idx = int(parts[0].strip()) - 1
                except ValueError:
                    continue
                if 0 <= idx < len(batch):
                    answer = parts[1].strip().lower()
                    if answer.startswith("yes"):
                        a, b, _ = batch[idx]
                        winner = _pick_winner([a, b])
                        uf.union(winner["id"], a["id"])
                        uf.union(winner["id"], b["id"])
        except Exception as exc:
            print(f"[graphify] --dedup-llm batch failed: {exc}", flush=True)
