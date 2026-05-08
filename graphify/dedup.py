"""Entity deduplication pipeline for graphify knowledge graphs.

Pipeline: source-location pre-pass → exact normalization → entropy gate →
MinHash/LSH blocking → Jaro-Winkler verification → same-community boost →
union-find merge → prune stale references.
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
_AST_PREFIX = re.compile(r"^[a-z]+_", re.IGNORECASE)

# ── source-location dedup helpers ─────────────────────────────────────────────

def _norm_member_label(label: str) -> str:
    """Strip common chunk prefix like 'T-21  ' from member labels."""
    label = label.strip()
    if not label:
        return ""
    parts = label.split(None, 1)
    if len(parts) == 2 and re.match(r"^[A-Z]-\d+$", parts[0]):
        return parts[1].strip()
    return label


def _compatible_duplicate(a: dict, b: dict) -> bool:
    """Return True if two nodes at the same source location are
    likely the same entity (conservative guard).

    Two nodes at the same line with different labels are checked via
    token-level comparison, not character-level substring containment —
    ``user`` and ``userId`` on the same line are different symbols,
    not variants of the same one (#F6).  But ``sort_all_nodes_topologically
    Method`` DOES contain the token ``sort_all_nodes_topologically``
    so those are compatible.
    """
    a_label = _norm(a.get("label") or "")
    b_label = _norm(b.get("label") or "")
    a_id = _norm(a.get("id") or "")
    b_id = _norm(b.get("id") or "")

    if a_label and b_label and a_label == b_label:
        return True
    if a_id and b_id and a_id == b_id:
        return True

    # Token-level label containment: if all tokens of the shorter label
    # appear as whole tokens in the longer label, they're compatible.
    # This allows "sort Method" to contain "sort" but prevents "user"
    # from matching "userId" (token boundary required).
    if a_label and b_label:
        a_tokens = set(a_label.split())
        b_tokens = set(b_label.split())
        if a_tokens and b_tokens:
            if a_tokens.issubset(b_tokens) or b_tokens.issubset(a_tokens):
                return True

    # ID comparison with common prefix stripping.
    # Strip prefix BEFORE normalization so _AST_PREFIX can match underscores.
    _AST_PREFIX_RE = re.compile(r"^(?:ast_|sem_|lib_|det_|doc_|syn_|tmp_)", re.IGNORECASE)
    a_raw = (a.get("id") or "").strip()
    b_raw = (b.get("id") or "").strip()
    a_stripped = _norm(_AST_PREFIX_RE.sub("", a_raw))
    b_stripped = _norm(_AST_PREFIX_RE.sub("", b_raw))
    if a_stripped and b_stripped and a_stripped == b_stripped:
        return True

    a_snip = (a.get("source_snippet") or "").strip()
    b_snip = (b.get("source_snippet") or "").strip()
    if a_snip and b_snip and a_snip == b_snip and (a_label or b_label or a_id or b_id):
        return True
    return False


def _dedup_key(node: dict) -> tuple[str, str] | None:
    """Return stable dedup key from source identity."""
    sf = (node.get("source_file") or "").strip()
    sl = (node.get("source_location") or "").strip()
    if not sf or not sl:
        return None
    return (sf, sl)


def _edge_key(edge: dict) -> tuple:
    """Return deduplication key for an edge."""
    return (
        edge.get("source"),
        edge.get("target"),
        edge.get("relation"),
        edge.get("source_file"),
        edge.get("confidence"),
    )


def _canonical_score(node: dict) -> tuple:
    """Score a node for canonical selection (higher = better).
    Prefers: has label, long label, many attrs, shorter ID, fewer underscores.
    Semantic nodes naturally score higher via attr_cnt (more metadata)
    and lexical tiebreaker (sem_* > ast_* alphabetically)."""
    label = (node.get("label") or "").strip()
    node_id = node.get("id", "")
    has_label = 1 if label else 0
    label_len = len(label)
    attr_cnt = sum(1 for v in node.values() if v not in (None, "", [], {}))
    shorter_id = -len(node_id)
    fewer_underscores = -node_id.count("_")
    return (has_label, label_len, attr_cnt, shorter_id, fewer_underscores, node_id)


# ── internal dedup passes ─────────────────────────────────────────────────────

def _source_location_dedup(
    nodes: list[dict],
    edges: list[dict],
    hyperedges: list[dict] | None,
) -> tuple[list[dict], list[dict], list[dict] | None, int, int]:
    """Pre-pass: merge nodes sharing the same (source_file, source_location)."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for node in nodes:
        key = _dedup_key(node)
        if key:
            groups[key].append(node)

    merges = 0
    remap: dict[str, str] = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=_canonical_score, reverse=True)
        canonical = group[0]
        for node in group[1:]:
            if _compatible_duplicate(canonical, node):
                remap[node["id"]] = canonical["id"]
                merges += 1

    if not merges:
        return nodes, edges, hyperedges, 0, 0

    remove_ids = set(remap.keys())
    deduped_nodes = [n for n in nodes if n["id"] not in remove_ids]

    deduped_edges: list[dict] = []
    seen = set()
    for edge in edges:
        e = dict(edge)
        e["source"] = remap.get(e["source"], e["source"])
        e["target"] = remap.get(e["target"], e["target"])
        if e["source"] == e["target"]:
            continue
        key = _edge_key(e)
        if key in seen:
            continue
        seen.add(key)
        deduped_edges.append(e)

    deduped_hyperedges: list[dict] | None = None
    hyperedges_remapped = 0
    if hyperedges is not None:
        deduped_hyperedges = []
        for he in hyperedges:
            h = dict(he)
            members = he.get("nodes", [])
            remapped: list[str] = []
            remapped_seen: set[str] = set()
            was_remapped = False
            for mid in members:
                new_id = remap.get(mid, mid)
                if new_id != mid:
                    was_remapped = True
                if new_id not in remapped_seen:
                    remapped.append(new_id)
                    remapped_seen.add(new_id)
            if was_remapped:
                hyperedges_remapped += 1
            if len(remapped) >= 2:
                h["nodes"] = remapped
                deduped_hyperedges.append(h)

    return deduped_nodes, deduped_edges, deduped_hyperedges, merges, hyperedges_remapped


def prune_graph_references(
    nodes_or_extraction: list[dict] | dict,
    edges: list[dict] | None = None,
    hyperedges: list[dict] | None = None,
) -> tuple[list[dict], list[dict], list[dict] | None, int] | dict:
    """Post-pass: remove edges and hyperedge members referencing missing nodes.

    Accepts either a dict extraction or separate (nodes, edges, hyperedges).
    Returns a dict if given a dict, otherwise a tuple.
    """
    if isinstance(nodes_or_extraction, dict):
        ex = nodes_or_extraction
        nodes = ex.get("nodes", [])
        edges = ex.get("edges", [])
        hyperedges = ex.get("hyperedges", [])
        is_dict = True
    else:
        nodes = nodes_or_extraction
        edges = edges or []
        hyperedges = hyperedges or []
        is_dict = False
    dropped = 0
    node_ids = {n["id"] for n in nodes}

    pruned_edges: list[dict] = []
    seen = set()
    for edge in edges:
        if edge["source"] not in node_ids or edge["target"] not in node_ids:
            dropped += 1
            continue
        if edge["source"] == edge["target"]:
            dropped += 1
            continue
        key = _edge_key(edge)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        pruned_edges.append(edge)

    pruned_hyperedges: list[dict] | None = None
    if hyperedges is not None:
        pruned_hyperedges = []
        for he in hyperedges:
            h = dict(he)
            members = [m for m in h.get("nodes", []) if m in node_ids]
            unique = list(dict.fromkeys(members))
            if len(unique) >= 2:
                h["nodes"] = unique
                pruned_hyperedges.append(h)
            else:
                dropped += 1

    if is_dict:
        nodes_or_extraction["nodes"] = nodes
        nodes_or_extraction["edges"] = pruned_edges
        nodes_or_extraction["hyperedges"] = pruned_hyperedges
        return nodes_or_extraction
    return nodes, pruned_edges, pruned_hyperedges, dropped


# ── main entry point ──────────────────────────────────────────────────────────

def deduplicate_entities(
    nodes: list[dict],
    edges: list[dict],
    hyperedges: list[dict] | None = None,
    *,
    communities: dict[str, int] | None = None,
    dedup_llm_backend: str | None = None,
) -> tuple[list[dict], list[dict], list[dict] | None, dict]:
    """Deduplicate entities in a knowledge graph.

    Runs three phases internally:
    1. Source-location pre-pass: merge nodes at the same source_location
    2. Entity dedup: exact normalization → MinHash/LSH → Jaro-Winkler → LLM
    3. Prune: remove stale edges and hyperedge members

    Args:
        nodes: list of node dicts with at minimum {"id": str, "label": str}
        edges: list of edge dicts
        communities: mapping of node_id -> community_id (from cluster())
        hyperedges: optional list of hyperedge dicts
        dedup_llm_backend: if set, use LLM to resolve ambiguous pairs

    Returns:
        (nodes, edges) when hyperedges is None,
        (nodes, edges, hyperedges) when hyperedges provided.
    """
    if communities is None:
        communities = {}

    # Guard: cross-project dedup is not supported — nodes from different repos
    # share label names by coincidence and must never be merged by string similarity.
    # If you need to dedup a global graph, run deduplicate_entities per-repo first.
    repos_seen = {n.get("repo") for n in nodes if n.get("repo")}
    if len(repos_seen) > 1:
        raise ValueError(
            f"deduplicate_entities: nodes span multiple repos {sorted(repos_seen)!r}. "
            f"Cross-project dedup is disabled — run dedup per-repo before merging."
        )

    # ── phase 1: source-location dedup ───────────────────────────────────────
    nodes, edges, hyperedges, _loc_merges, _loc_hyper_remapped = _source_location_dedup(
        nodes, edges, hyperedges
    )

    # ── pre-deduplicate: keep first occurrence of each id ────────────────────
    if len(nodes) <= 1:
        nodes, edges, hyperedges, dropped = prune_graph_references(nodes, edges, hyperedges)
        stats = {
            "merged_nodes": _loc_merges,
            "source_location_groups": 0,
            "deduped_edges": dropped,
            "dropped_self_loops": 0,
            "hyperedges_remapped": _loc_hyper_remapped,
            "hyperedge_member_sets": [list(h.get("nodes", [])) for h in (hyperedges or [])],
        }
        return _maybe_return(nodes, edges, hyperedges, stats)

    seen_ids: dict[str, dict] = {}
    for node in nodes:
        nid = node.get("id", "")
        if nid and nid not in seen_ids:
            seen_ids[nid] = node
    unique_nodes = list(seen_ids.values())

    if len(unique_nodes) <= 1:
        unique_nodes, edges, hyperedges, dropped = prune_graph_references(unique_nodes, edges, hyperedges)
        stats = {
            "merged_nodes": _loc_merges,
            "source_location_groups": 0,
            "deduped_edges": dropped,
            "dropped_self_loops": 0,
            "hyperedges_remapped": _loc_hyper_remapped,
            "hyperedge_member_sets": [list(h.get("nodes", [])) for h in (hyperedges or [])],
        }
        return _maybe_return(unique_nodes, edges, hyperedges, stats)

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
    if remap:
        total = len(remap)
        msg = f"[graphify] Deduplicated {total} node(s)"
        if _loc_merges:
            msg += f" ({_loc_merges} source-location"
            msg += f", {exact_merges} exact" if exact_merges else ""
            if fuzzy_merges:
                msg += f", {fuzzy_merges} fuzzy"
            msg += ")"
        elif exact_merges:
            msg += f" ({exact_merges} exact"
            if fuzzy_merges:
                msg += f", {fuzzy_merges} fuzzy"
            msg += ")"
        print(msg + ".", flush=True)

        deduped_nodes = [n for n in unique_nodes if n["id"] not in remap]
        deduped_edges: list[dict] = []
        for edge in edges:
            e = dict(edge)
            e["source"] = remap.get(e["source"], e["source"])
            e["target"] = remap.get(e["target"], e["target"])
            if e["source"] != e["target"]:
                deduped_edges.append(e)

        # Remap hyperedge member IDs too
        hyperedges_remapped_count = 0
        if hyperedges is not None:
            deduped_hyperedges: list[dict] = []
            for he in hyperedges:
                h = dict(he)
                remapped_members: list[str] = []
                remapped_seen: set[str] = set()
                was_remapped = False
                for mid in h.get("nodes", []):
                    new_id = remap.get(mid, mid)
                    if new_id != mid:
                        was_remapped = True
                    if new_id not in remapped_seen:
                        remapped_members.append(new_id)
                        remapped_seen.add(new_id)
                if was_remapped:
                    hyperedges_remapped_count += 1
                if len(remapped_members) >= 2:
                    h["nodes"] = remapped_members
                    deduped_hyperedges.append(h)
            hyperedges = deduped_hyperedges
    else:
        hyperedges_remapped_count = 0
        deduped_nodes = unique_nodes
        deduped_edges = edges

    # ── phase 3: prune stale references ───────────────────────────────────────
    orig_hyper_len = len(hyperedges) if hyperedges is not None else 0
    deduped_nodes, deduped_edges, hyperedges, _dropped = prune_graph_references(
        deduped_nodes, deduped_edges, hyperedges
    )
    final_hyper_len = len(hyperedges) if hyperedges is not None else 0
    hyperedges_remapped_count += (orig_hyper_len - final_hyper_len)

    stats = {
        "merged_nodes": _loc_merges + (len(remap) if remap else 0),
        "source_location_groups": len(components),
        "deduped_edges": _dropped,
        "dropped_self_loops": 0,
        "hyperedges_remapped": hyperedges_remapped_count + _loc_hyper_remapped,
        "hyperedge_member_sets": [list(h.get("nodes", [])) for h in (hyperedges or [])],
    }
    return _maybe_return(deduped_nodes, deduped_edges, hyperedges, stats)


def _maybe_return(
    nodes: list[dict],
    edges: list[dict],
    hyperedges: list[dict] | None,
    stats: dict | None = None,
) -> tuple[list[dict], list[dict], list[dict] | None, dict]:
    """Return 4-tuple (nodes, edges, hyperedges|None, stats)."""
    if stats is None:
        stats = {}
    if hyperedges is not None:
        return nodes, edges, hyperedges, stats
    return nodes, edges, None, stats


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
