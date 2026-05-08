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
    # F8: detect collisions where two real node ids normalize to the same key
    # (e.g. "api-v1" and "api_v1" both → "api_v1") and skip remapping for those.
    raw_norm: dict[str, list[str]] = {}
    for nid in node_set:
        nk = _normalize_id(nid)
        raw_norm.setdefault(nk, []).append(nid)
    norm_to_id: dict[str, str] = {}
    collisions: set[str] = set()
    for nk, ids in raw_norm.items():
        if len(ids) == 1:
            norm_to_id[nk] = ids[0]
        else:
            # Two or more real node ids normalize to the same key.
            # Skip remapping for this key — ambiguous which one is intended (#F8)
            collisions.add(nk)
    # Deduplicate edges by (source, target, relation) and prevent edge collapse
    # (#F3): NetworkX Graph can only store one edge per (source, target) pair.
    # When multiple edges share the same endpoints but have different relations,
    # the first one wins (deterministic) and a warning is emitted.
    deduped_edges: list[dict] = []
    seen_edge_pairs: set[tuple[str, str, str]] = set()
    seen_endpoint_pairs: set[tuple[str, str]] = set()
    collapsed: int = 0
    for edge in extraction.get("edges", []):
        if "source" not in edge and "from" in edge:
            edge["source"] = edge["from"]
        if "target" not in edge and "to" in edge:
            edge["target"] = edge["to"]
        if "source" not in edge or "target" not in edge:
            continue
        src, tgt = edge["source"], edge["target"]
        rel = edge.get("relation", "")
        triple = (src, tgt, rel)
        if triple in seen_edge_pairs:
            continue  # exact duplicate
        seen_edge_pairs.add(triple)
        endpoint_pair = (src, tgt)
        if endpoint_pair in seen_endpoint_pairs:
            collapsed += 1
            # Skip this edge — a different relation already uses this pair
            continue
        seen_endpoint_pairs.add(endpoint_pair)
        deduped_edges.append(edge)
    if collapsed:
        print(f"[graphify] Note: {collapsed} edge(s) between same endpoints with "
              f"different relations could not be stored in the graph (#F3). "
              f"The first relation found for each (source, target) pair was kept. "
              f"Consider upgrading to MultiGraph in a future release.",
              file=sys.stderr)
    for edge in deduped_edges:
        src, tgt = edge["source"], edge["target"]
        # Remap mismatched IDs via normalization before dropping the edge.
        if src not in node_set:
            src_nk = _normalize_id(src)
            if src_nk not in collisions:
                src = norm_to_id.get(src_nk, src)
        if tgt not in node_set:
            tgt_nk = _normalize_id(tgt)
            if tgt_nk not in collisions:
                tgt = norm_to_id.get(tgt_nk, tgt)
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
    dedup_llm_backend: if set (e.g. "claude", "kimi", or "gemini"), uses LLM to resolve
        ambiguous pairs in the 75–92 Jaro-Winkler score zone.

    Extractions are merged in order. For nodes with the same ID, the last
    extraction's attributes win (NetworkX add_node overwrites). Pass AST
    results before semantic results so semantic labels take precedence, or
    reverse the order if you prefer AST source_location precision to win.
    """
    from graphify.dedup import deduplicate_entities
    combined: dict = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    for ext in extractions:
        combined["nodes"].extend(ext.get("nodes", []))
        combined["edges"].extend(ext.get("edges", []))
        combined["hyperedges"].extend(ext.get("hyperedges", []))
        combined["input_tokens"] += ext.get("input_tokens", 0)
        combined["output_tokens"] += ext.get("output_tokens", 0)
    if dedup and combined["nodes"]:
        combined["nodes"], combined["edges"], combined["hyperedges"], _stats = deduplicate_entities(
            combined["nodes"], combined["edges"], combined["hyperedges"],
            communities={},
            dedup_llm_backend=dedup_llm_backend,
        )
    return build_from_json(combined, directed=directed)


def _norm_label(label: str) -> str:
    """Canonical dedup key — lowercase, alphanumeric only."""
    return re.sub(r"[^a-z0-9 ]", "", label.lower()).strip()



def build_merge(
    new_chunks: list[dict] | None = None,
    graph_path: str | Path = "graphify-out/graph.json",
    prune_sources: list[str] | None = None,
    *,
    directed: bool = False,
    dedup: bool = True,
    dedup_llm_backend: str | None = None,
    extractions: list[dict] | None = None,
    root: Path | None = None,
) -> nx.Graph:
    """Load existing graph.json, merge new chunks into it, and save back.

    Never replaces — only grows (or prunes deleted-file nodes via prune_sources).
    Safe to call repeatedly: existing nodes and edges are preserved.

    F1: root is used to normalize prune_sources paths for comparison against
    relativized source_file values on graph nodes. New-chunk source_file values
    are checked to evict stale nodes from modified files before merging.
    """
    from networkx.readwrite import json_graph as _jg

    if new_chunks is None:
        new_chunks = extractions or []
    elif extractions is not None:
        raise TypeError("build_merge received both new_chunks and extractions")

    graph_path = Path(graph_path)
    if graph_path.exists():
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        try:
            existing_G = _jg.node_link_graph(data, edges="links")
        except TypeError:
            existing_G = _jg.node_link_graph(data)
        # F1: Evict stale nodes from sources that appear in new_chunks.
        # If a file was modified, its old extraction nodes must be cleared
        # before merging the new extraction; otherwise renamed/removed symbols
        # survive alongside their replacements.
        new_source_files: set[str] = set()
        for chunk in (new_chunks or []):
            for node in chunk.get("nodes", []):
                sf = node.get("source_file")
                if sf:
                    new_source_files.add(sf)
        if new_source_files:
            stale_nodes = [
                n for n, d in existing_G.nodes(data=True)
                if d.get("source_file") in new_source_files
            ]
            if stale_nodes:
                existing_G.remove_nodes_from(stale_nodes)
        # Reconstruct as a plain extraction dict so build() can merge it
        existing_nodes = [{"id": n, **existing_G.nodes[n]} for n in existing_G.nodes]
        existing_edges = []
        for u, v, d in existing_G.edges(data=True):
            existing_edges.append({"source": u, "target": v, **d})
        base = [{"nodes": existing_nodes, "edges": existing_edges}]
    else:
        base = []

    all_chunks = base + list(new_chunks)
    G = build(all_chunks, directed=directed, dedup=dedup, dedup_llm_backend=dedup_llm_backend)

    # Prune nodes from deleted source files
    if prune_sources:
        # F1: normalize prune_sources for comparison against graph node
        # source_file values. detect_incremental returns absolute paths, but
        # graph nodes may store relativized values (extract.py rel#555).
        prune_set: set[str] = set(prune_sources)
        if root is not None:
            for p in prune_sources:
                try:
                    prune_set.add(str(Path(p).resolve().relative_to(root.resolve())))
                except ValueError:
                    pass  # not under root, keep original only
        to_remove = [
            n for n, d in G.nodes(data=True)
            if d.get("source_file") in prune_set
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
    # Skip when dedup or prune_sources is active — shrinkage is intentional there.
    if graph_path.exists() and not dedup and not prune_sources:
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
