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
import re
import sys
import networkx as nx
from .validate import validate_extraction


def _normalize_id(s: str) -> str:
    """Normalize an ID string the same way extract._make_id does.

    Used to reconcile edge endpoints when the LLM generates IDs with slightly
    different punctuation or casing than the AST extractor.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", s)
    return cleaned.strip("_").lower()


def build_from_json(extraction: dict, *, directed: bool = False) -> nx.Graph:
    """Build a NetworkX graph from an extraction dict.

    directed=True produces a DiGraph that preserves edge direction (source→target).
    directed=False (default) produces an undirected Graph for backward compatibility.
    """
    # NetworkX <= 3.1 serialised edges as "links"; remap to "edges" for compatibility.
    if "edges" not in extraction and "links" in extraction:
        extraction = dict(extraction, edges=extraction["links"])
    errors = validate_extraction(extraction)
    # Dangling edges (stdlib/external imports) are expected - only warn about real schema errors.
    real_errors = [e for e in errors if "does not match any node id" not in e]
    if real_errors:
        print(f"[graphify] Extraction warning ({len(real_errors)} issues): {real_errors[0]}", file=sys.stderr)
    G: nx.Graph = nx.DiGraph() if directed else nx.Graph()
    for node in extraction.get("nodes", []):
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
        # Preserve original edge direction - undirected graphs lose it otherwise,
        # causing display functions to show edges backwards.
        attrs["_src"] = src
        attrs["_tgt"] = tgt
        G.add_edge(src, tgt, **attrs)
    hyperedges = extraction.get("hyperedges", [])
    if hyperedges:
        G.graph["hyperedges"] = hyperedges
    return G


def build(extractions: list[dict], *, directed: bool = False) -> nx.Graph:
    """Merge multiple extraction results into one graph.

    directed=True produces a DiGraph that preserves edge direction (source→target).
    directed=False (default) produces an undirected Graph for backward compatibility.

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
    return build_from_json(combined, directed=directed)


def merge_graphs(G_base: nx.Graph, G_overlay: nx.Graph, source_layer_id: str) -> nx.Graph:
    """Merge an overlay (summary) graph into a base graph.

    Overlay node IDs are prefixed with ``summary:<source_layer_id>:`` to avoid
    collisions.  Every overlay node also gets a ``_source_layer`` attribute for
    provenance tracking.  All node and edge attributes from both graphs are
    preserved.
    """
    prefix = f"summary:{source_layer_id}:"
    result = G_base.__class__()
    result.graph.update(G_base.graph)

    for nid, data in G_base.nodes(data=True):
        result.add_node(nid, **data)

    id_map: dict[str, str] = {}
    for nid, data in G_overlay.nodes(data=True):
        prefixed = f"{prefix}{nid}"
        id_map[nid] = prefixed
        merged_data = dict(data)
        merged_data["_source_layer"] = source_layer_id
        result.add_node(prefixed, **merged_data)

    for u, v, data in G_overlay.edges(data=True):
        new_u = id_map.get(u, u)
        new_v = id_map.get(v, v)
        result.add_edge(new_u, new_v, **data)

    for u, v, data in G_base.edges(data=True):
        if not result.has_edge(u, v):
            result.add_edge(u, v, **data)

    return result


def graph_diff(G_a: nx.Graph, G_b: nx.Graph) -> dict:
    """Compare two graphs and return structural differences.

    Returns a dict with keys:
    - nodes_only_in_a: set of node IDs only in G_a
    - nodes_only_in_b: set of node IDs only in G_b
    - common_nodes: set of node IDs in both graphs
    - edges_only_in_a: set of edge tuples only in G_a
    - edges_only_in_b: set of edge tuples only in G_b
    - common_edges: set of edge tuples in both graphs
    """
    nodes_a = set(G_a.nodes())
    nodes_b = set(G_b.nodes())

    edges_a = set(G_a.edges())
    edges_b = set(G_b.edges())

    return {
        "nodes_only_in_a": nodes_a - nodes_b,
        "nodes_only_in_b": nodes_b - nodes_a,
        "common_nodes": nodes_a & nodes_b,
        "edges_only_in_a": edges_a - edges_b,
        "edges_only_in_b": edges_b - edges_a,
        "common_edges": edges_a & edges_b,
    }
