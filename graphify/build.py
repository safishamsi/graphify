# assemble node+edge dicts into a NetworkX graph, preserving edge direction
#
# Node deduplication — three layers:
#
# 1. Within a file (AST): each extractor tracks a `seen_ids` set. A node ID is
#    emitted at most once per file, so duplicate class/function definitions in
#    the same source file are collapsed to the first occurrence.
#
# 2. Between files (build): NetworkX G.add_node() is idempotent — calling it
#    twice with the same ID overwrites the attributes with the second call's
#    values. Nodes are added in extraction order (AST first, then semantic),
#    so if the same entity is extracted by both passes the semantic node
#    silently overwrites the AST node. This is intentional: semantic nodes
#    carry richer labels and cross-file context, while AST nodes have precise
#    source_location. If you need to change the priority, reorder extractions
#    passed to build().
#
# 3. Semantic merge (skill): before calling build(), the skill merges cached
#    and new semantic results using an explicit `seen` set keyed on node["id"],
#    so duplicates across cache hits and new extractions are resolved there
#    before any graph construction happens.
#
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
import networkx as nx
from .validate import validate_extraction


def _normalize_id(s: str) -> str:
    """Normalize an ID string the same way extract._make_id does.

    Used to reconcile edge endpoints when the LLM generates IDs with slightly
    different punctuation or casing than the AST extractor.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", s)
    return cleaned.strip("_").lower()


def _norm_source_file(p: str | None) -> str | None:
    """Normalize path separators to forward slashes so Windows backslash paths
    and POSIX paths from semantic subagents resolve to the same node identity."""
    return p.replace("\\", "/") if p else p


def build_from_json(extraction: dict, *, directed: bool = False) -> nx.Graph:
    """Build a NetworkX graph from an extraction dict.

    directed=True produces a DiGraph that preserves edge direction (source→target).
    directed=False (default) produces an undirected Graph for backward compatibility.
    """
    # NetworkX <= 3.1 serialised edges as "links"; remap to "edges" for compatibility.
    if "edges" not in extraction and "links" in extraction:
        extraction = dict(extraction, edges=extraction["links"])

    # Canonicalize legacy node/edge schema before validation.
    for node in extraction.get("nodes", []):
        if not isinstance(node, dict):
            continue
        if "source" in node and "source_file" not in node:
            # Count edges that reference this node so the warning is actionable (#479)
            node_id = node.get("id", "?")
            affected_edges = sum(
                1 for e in extraction.get("edges", [])
                if e.get("source") == node_id or e.get("target") == node_id
            )
            print(
                f"[graphify] WARNING: node '{node_id}' uses field 'source' instead of "
                f"'source_file' — {affected_edges} edge(s) may be misrouted. "
                f"Rename the field to 'source_file' to silence this warning.",
                file=sys.stderr,
            )
            node["source_file"] = node.pop("source")
        # Default missing/None file_type to "concept" so legacy graph.json
        # entries (and stub nodes preserved by `_rebuild_code` from older
        # graphify versions that didn't always populate file_type) don't
        # trigger spurious "invalid file_type 'None'" validator warnings (#660).
        if node.get("file_type") in (None, ""):
            node["file_type"] = "concept"

    errors = validate_extraction(extraction)
    # Dangling edges (stdlib/external imports) are expected - only warn about real schema errors.
    real_errors = [e for e in errors if "does not match any node id" not in e]
    if real_errors:
        print(f"[graphify] Extraction warning ({len(real_errors)} issues): {real_errors[0]}", file=sys.stderr)
    G: nx.Graph = nx.DiGraph() if directed else nx.Graph()
    for node in extraction.get("nodes", []):
        if "source_file" in node:
            node["source_file"] = _norm_source_file(node["source_file"])
        G.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    node_set = set(G.nodes())
    # Normalized ID map: lets edges survive when the LLM generates IDs with
    # slightly different casing or punctuation than the AST extractor.
    # e.g. "Session_ValidateToken" maps to "session_validatetoken".
    norm_to_id: dict[str, str] = {_normalize_id(nid): nid for nid in node_set}
    for edge in extraction.get("edges", []):
        if "source" not in edge and "from" in edge:
            edge["source"] = edge["from"]
        if "target" not in edge and "to" in edge:
            edge["target"] = edge["to"]
        if "source" not in edge or "target" not in edge:
            continue
        src, tgt = edge["source"], edge["target"]
        # Remap mismatched IDs via normalization before dropping the edge.
        if src not in node_set:
            src = norm_to_id.get(_normalize_id(src), src)
        if tgt not in node_set:
            tgt = norm_to_id.get(_normalize_id(tgt), tgt)
        if src not in node_set or tgt not in node_set:
            continue  # skip edges to external/stdlib nodes - expected, not an error
        attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
        if "source_file" in attrs:
            attrs["source_file"] = _norm_source_file(attrs["source_file"])
        # Preserve original edge direction - undirected graphs lose it otherwise,
        # causing display functions to show edges backwards.
        attrs["_src"] = src
        attrs["_tgt"] = tgt
        G.add_edge(src, tgt, **attrs)
    hyperedges = extraction.get("hyperedges", [])
    if hyperedges:
        G.graph["hyperedges"] = hyperedges
    return G


def build(
    extractions: list[dict],
    *,
    directed: bool = False,
    dedup: bool = True,
    dedup_llm_backend: str | None = None,
) -> nx.Graph:
    """Merge multiple extraction results into one graph.

    directed=True produces a DiGraph that preserves edge direction (source→target).
    directed=False (default) produces an undirected Graph for backward compatibility.
    dedup=True (default) runs entity deduplication before building the graph.
    dedup_llm_backend: if set (e.g. "gemini", "claude", or "kimi"), uses LLM to resolve
        ambiguous pairs in the 75–92 Jaro-Winkler score zone.

    Extractions are merged in order. For nodes with the same ID, the last
    extraction's attributes win (NetworkX add_node overwrites). Pass AST
    results before semantic results so semantic labels take precedence, or
    reverse the order if you prefer AST source_location precision to win.
    """
    combined: dict = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    for ext in extractions:
        combined["nodes"].extend(ext.get("nodes", []))
        combined["edges"].extend(ext.get("edges", []))
        combined["hyperedges"].extend(ext.get("hyperedges", []))
        combined["input_tokens"] += ext.get("input_tokens", 0)
        combined["output_tokens"] += ext.get("output_tokens", 0)
    nodes, edges, hyperedges, _stats = deduplicate_by_source_location(
        combined.get("nodes", []), combined.get("edges", []),
        combined.get("hyperedges", []),
    )
    combined["nodes"] = nodes
    combined["edges"] = edges
    combined["hyperedges"] = hyperedges
    return build_from_json(combined, directed=directed)

def _dedup_key(node: dict) -> tuple | None:
    """Return a canonical source-identity key for a node.

    Nodes that share the same (source_file, source_location) key are
    candidates for source-location deduplication. Returns None when the
    node lacks sufficient source-identity fields.
    """
    source_file = (node.get("source_file") or "").strip()
    source_location = (node.get("source_location") or "").strip()
    if not source_file or not source_location:
        return None
    return (source_file, source_location)


def _norm_label(label: str) -> str:
    """Canonical dedup key — lowercase, alphanumeric only."""
    return re.sub(r"[^a-z0-9 ]", "", label.lower()).strip()


def _norm_member_label(label: str) -> str:
    """Normalize a label that may contain a membership prefix like 'T-21 '.

    LLM semantic extraction sometimes prefixes community-member labels with
    'T-<number> ' (e.g. 'T-21 sort_all_nodes_topologically'). This strips that
    prefix so dedup matching works across prefixed and non-prefixed labels.
    """
    if not label:
        return label
    if re.match(r"^T-\d+\s+", label):
        return re.sub(r"^T-\d+\s+", "", label, count=1).strip()
    return label


def _edge_key(edge: dict) -> tuple:
    """Return a stable identity key for an edge.

    Two edges that share the same key are considered duplicates and may
    be collapsed during deduplication. The key is order-stable (does not
    depend on edge direction).
    """
    return (
        edge.get("source"),
        edge.get("target"),
        edge.get("relation"),
        edge.get("source_file"),
        edge.get("confidence"),
    )


def _compatible_duplicate(a: dict, b: dict) -> bool:
    """Check whether two nodes are compatible enough to be considered duplicates.

    Two nodes sharing a (source_file, source_location) key may still represent
    different entities (e.g. multiple symbols on the same source line). This
    guard prevents incorrect merges by requiring at least one of:
      - normalized labels match
      - normalized IDs match
      - one normalized label contains the other
      - one normalized ID contains the other
      - source snippets match (exact) and labels are compatible
    """
    import re as _re

    def _norm(value: str) -> str:
        return _re.sub(r"[^a-z0-9]+", "", (value or "").lower())

    a_label = _norm(a.get("label") or "")
    b_label = _norm(b.get("label") or "")
    a_id = _norm(a.get("id") or "")
    b_id = _norm(b.get("id") or "")

    if a_label and b_label and a_label == b_label:
        return True
    if a_id and b_id and a_id == b_id:
        return True
    if a_label and b_label:
        if a_label in b_label or b_label in a_label:
            return True
    if a_id and b_id:
        if a_id in b_id or b_id in a_id:
            return True
    a_snip = (a.get("source_snippet") or "").strip()
    b_snip = (b.get("source_snippet") or "").strip()
    if a_snip and b_snip and a_snip == b_snip and (a_label or b_label):
        return True
    return False


def deduplicate_by_source_location(
    nodes: list[dict],
    edges: list[dict],
    hyperedges: list[dict] | None = None,
) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Merge nodes that share the same (source_file, source_location), rewriting edge references.

    Prefers nodes with richer labels (non-empty, longer) and shorter IDs without
    chunk suffixes. Merges non-conflicting attributes (<source_file>, <location>,
    <file_type>, <source_snippet>, <doc_type>, <kind>) from removed nodes into the
    surviving node. Drops self-loops created by the merge.

    This fixes the duplicate-god-node bug where AST extraction creates
    \"lib_sort_all_nodes_topologically\" and semantic extraction creates
    \"sort_all_nodes_topologically\" — both pointing to lib.rs:187 — and
    the skill.md merge preserves both because it deduplicates by ID only.
    """
    import re as _re
    _CHUNK_SUFFIX = _re.compile(r"_c\d+$")

    # Group nodes by (source_file, source_location) where both exist
    groups: dict[tuple[str, str], list[dict]] = {}
    for node in nodes:
        sf = (node.get("source_file") or "").strip()
        sl = (node.get("source_location") or "").strip()
        if sf and sl:
            groups.setdefault((sf, sl), []).append(node)

    # Early exit when no source-location keys exist: prune stale refs, keep edges/hyperedges intact
    if not groups:
        # Prune edges and hyperedges whose endpoints don't exist
        valid_ids = {n["id"] for n in nodes}
        pruned_edges = [
            e for e in edges
            if e["source"] in valid_ids and e["target"] in valid_ids
        ]
        pruned_hyperedges = []
        for h in hyperedges or []:
            kept = [n for n in h.get("nodes", []) if n in valid_ids]
            if len(kept) >= 2:
                h = dict(h)
                h["nodes"] = kept
                pruned_hyperedges.append(h)
        stats = {
            "merged_nodes": 0,
            "source_location_groups": 0,
            "deduped_edges": len(edges) - len(pruned_edges),
            "dropped_self_loops": 0,
            "hyperedges_remapped": len(hyperedges or []) - len(pruned_hyperedges),
            "hyperedge_member_sets": len(pruned_hyperedges),
        }
        return list(nodes), pruned_edges, pruned_hyperedges, stats
    # Build remap: old_id -> surviving_id for nodes that should be merged
    remap: dict[str, str] = {}
    surviving: dict[str, dict] = {}  # surviving_id -> merged node
    removed_ids: set[str] = set()

    for (sf, sl), group in groups.items():
        if len(group) <= 1:
            continue
        # Conservative: merge only when nodes are compatible.
        mergeable: list[dict] = []
        unmergeable: list[dict] = []
        canonical_candidate = group[0]
        mergeable.append(canonical_candidate)
        for other in group[1:]:
            if _compatible_duplicate(canonical_candidate, other):
                mergeable.append(other)
            else:
                unmergeable.append(other)
        # Re-try with next mergeable if the first was too dissimilar
        while not mergeable and unmergeable:
            canonical_candidate = unmergeable.pop(0)
            mergeable.append(canonical_candidate)
            still_unmergeable: list[dict] = []
            for other in unmergeable:
                if _compatible_duplicate(canonical_candidate, other):
                    mergeable.append(other)
                else:
                    still_unmergeable.append(other)
            unmergeable = still_unmergeable
        if len(mergeable) <= 1:
            continue
        # Pick canonical: prefer non-empty label, then longer label,
        # then non-chunk-suffix ID, then non-AST-prefixed ID, then shorter ID,
        # then more attributes.
        def _score(n: dict) -> tuple:
            label = (n.get("label") or "").strip()
            nid = n.get("id", "")
            has_label = 1 if label else 0
            label_len = len(label)
            # Prefer non-"chunk-" prefixed / non-generated IDs
            no_chunk = 0 if (nid or "").startswith("chunk_") else 1
            no_ast = 0 if (nid or "").startswith("ast_") else 1
            # Attribute-count tiebreaker: nodes with richer attribute sets
            # (more populated fields) are preferred as canonical
            attr_cnt = sum(
                1 for v in n.values()
                if v not in (None, "", [], {})
            )
            # Negative len so shorter IDs rank higher
            return (has_label, label_len, no_chunk, no_ast, attr_cnt, -len(nid))
        mergeable.sort(key=_score, reverse=True)
        canonical = mergeable[0]
        surviving[canonical["id"]] = canonical
        for dup in mergeable[1:]:
            remap[dup["id"]] = canonical["id"]
            removed_ids.add(dup["id"])
            # Merge non-conflicting attributes from dup into canonical
            for key in ("label", "source_snippet", "doc_type", "kind"):
                dv = (dup.get(key) or "").strip()
                cv = (canonical.get(key) or "").strip()
                if dv and not cv:
                    canonical[key] = dv

    # Build node list (exclude removed duplicates), rewrite edges, drop
    # self-loops, and deduplicate identical edges.  Even when no nodes were
    # merged edge rewriting is a no-op and dedup may still collapse duplicate
    # edges.

    stats = {
        "merged_nodes": len(remap),
        "source_location_groups": len(groups),
    }

    # Rewrite edges, drop self-loops
    deduped_nodes = [n for n in nodes if n["id"] not in removed_ids]
    deduped_edges = []
    seen_edge_keys = set()
    for edge in edges:
        e = dict(edge)
        e["source"] = remap.get(e["source"], e["source"])
        e["target"] = remap.get(e["target"], e["target"])
        if e["source"] != e["target"]:
            key = _edge_key(e)
            if key not in seen_edge_keys:
                seen_edge_keys.add(key)
                deduped_edges.append(e)

    # Count self-loops dropped
    stats["self_loop_count"] = sum(1 for e in edges if remap.get(e["source"], e["source"]) == remap.get(e["target"], e["target"]))
    stats["deduped_edge_count"] = len(deduped_edges)

    # Remap hyperedge member IDs to canonical node IDs and drop members that do
    # not correspond to surviving nodes. Hyperedges with fewer than two
    # remaining members are left out of the returned hyperedge list, but the
    # member sets are still reported in stats for testability and diagnostics.
    surviving_node_ids = {n["id"] for n in deduped_nodes}
    remapped_hyperedges = []
    hyperedge_member_sets = []
    if hyperedges:
        for hyperedge in hyperedges:
            h = dict(hyperedge)
            members = h.get("nodes", [])
            remapped_members = []
            seen = set()
            for member in members:
                new_member = remap.get(member, member)
                if new_member in surviving_node_ids and new_member not in seen:
                    remapped_members.append(new_member)
                    seen.add(new_member)
            hyperedge_member_sets.append(remapped_members)
            if len(remapped_members) >= 2:
                h["nodes"] = remapped_members
                remapped_hyperedges.append(h)
    stats["hyperedges_remapped"] = sum(
        1 for members in hyperedge_member_sets if len(members) >= 2
    )
    stats["hyperedge_member_sets"] = hyperedge_member_sets

    stats["hyperedges"] = remapped_hyperedges
    return deduped_nodes, deduped_edges, remapped_hyperedges, stats


def deduplicate_extraction_by_source_location(extraction: dict) -> dict:
    """Apply source-location dedup to a full extraction dict.

    Returns a new extraction dict with deduplicated nodes, edges, and hyperedges
    plus a ``_dedup_stats`` key containing the merge statistics.
    """
    extracted = dict(extraction)
    nodes, edges, hyperedges, stats = deduplicate_by_source_location(
        extracted.get("nodes", []),
        extracted.get("edges", []),
        hyperedges=extracted.get("hyperedges", []),
    )
    extracted["nodes"] = nodes
    extracted["edges"] = edges
    extracted["hyperedges"] = hyperedges
    extracted["_dedup_stats"] = stats
    return extracted


def prune_graph_references(extraction: dict) -> dict:
    """Remove references to nodes that no longer exist in the extraction.

    Returns a new extraction dict with:
      - edges whose endpoints don't exist in ``nodes`` dropped
      - self-loops dropped
      - duplicate edges collapsed
      - hyperedge members that don't exist dropped
      - hyperedges with fewer than 2 remaining members dropped
    """
    extracted = dict(extraction)
    node_ids = {n["id"] for n in extracted.get("nodes", [])}

    # Deduplicate edges and drop unresolvable/self-loop edges.
    pruned_edges = []
    seen_edges = set()
    for edge in extracted.get("edges", []):
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            continue
        if source not in node_ids or target not in node_ids:
            continue
        if source == target:
            continue
        # Stable, hashable edge key for deduplication.
        ekey = (
            source,
            target,
            edge.get("relation"),
            edge.get("source_file"),
            edge.get("confidence"),
        )
        if ekey in seen_edges:
            continue
        seen_edges.add(ekey)
        pruned_edges.append(edge)

    # Prune hyperedge members and drop singletons.
    pruned_hyperedges = []
    for hyperedge in extracted.get("hyperedges", []):
        h = dict(hyperedge)
        members = []
        seen = set()
        for node_id in h.get("nodes", []):
            if node_id in node_ids and node_id not in seen:
                members.append(node_id)
                seen.add(node_id)
        if len(members) >= 2:
            h["nodes"] = members
            pruned_hyperedges.append(h)

    extracted["edges"] = pruned_edges
    extracted["hyperedges"] = pruned_hyperedges
    return extracted


def build_merge(
    new_chunks: list[dict],
    graph_path: str | Path = "graphify-out/graph.json",
    prune_sources: list[str] | None = None,
    *,
    directed: bool = False,
) -> nx.Graph:
    """Load existing graph.json, merge new chunks into it, and save back.

    Never replaces — only grows (or prunes deleted-file nodes via prune_sources).
    Safe to call repeatedly: existing nodes and edges are preserved.
    """
    from networkx.readwrite import json_graph as _jg

    graph_path = Path(graph_path)
    if graph_path.exists():
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        try:
            existing_G = _jg.node_link_graph(data, edges="links")
        except TypeError:
            existing_G = _jg.node_link_graph(data)
        # Reconstruct as a plain extraction dict so build() can merge it
        existing_nodes = [{"id": n, **existing_G.nodes[n]} for n in existing_G.nodes]
        existing_edges = [
            {"source": u, "target": v, **d} for u, v, d in existing_G.edges(data=True)
        ]
        base = [{"nodes": existing_nodes, "edges": existing_edges}]
    else:
        base = []

    all_chunks = base + list(new_chunks)
    G = build(all_chunks, directed=directed)

    # Prune nodes from deleted source files
    if prune_sources:
        to_remove = [
            n for n, d in G.nodes(data=True)
            if d.get("source_file") in prune_sources
        ]
        G.remove_nodes_from(to_remove)
        n_files = len(prune_sources)
        n_nodes = len(to_remove)
        if n_nodes:
            print(
                f"[graphify] Pruned {n_nodes} node(s) from {n_files} deleted source file(s).",
                file=sys.stderr,
            )
        else:
            print(
                f"[graphify] {n_files} source file(s) deleted since last run — "
                f"no matching nodes in graph, already clean.",
                file=sys.stderr,
            )

    # Safety check: refuse to shrink the graph silently (#479)
    if graph_path.exists():
        existing_n = len(existing_nodes)
        new_n = G.number_of_nodes()
        if new_n < existing_n:
            raise ValueError(
                f"graphify: build_merge would shrink graph from {existing_n} → {new_n} nodes. "
                f"Pass prune_sources explicitly if you intend to remove nodes."
            )

    return G


def prefix_graph_for_global(G: nx.Graph, repo_tag: str) -> nx.Graph:
    """Return a copy of G with all node IDs prefixed with repo_tag::.

    Labels are preserved unchanged (for display). A 'local_id' attribute
    is added to each node so the original ID can be recovered. Edges are
    rewritten to match the new prefixed IDs. The 'repo' attribute is set
    on every node.
    """
    relabel = {n: f"{repo_tag}::{n}" for n in G.nodes}
    H = nx.relabel_nodes(G, relabel, copy=True)
    for node, data in H.nodes(data=True):
        data["repo"] = repo_tag
        data.setdefault("local_id", node.split("::", 1)[1])
    return H


def prune_repo_from_graph(G: nx.Graph, repo_tag: str) -> int:
    """Remove all nodes tagged with repo_tag from G in-place. Returns count removed."""
    to_remove = [n for n, d in G.nodes(data=True) if d.get("repo") == repo_tag]
    G.remove_nodes_from(to_remove)
    return len(to_remove)
