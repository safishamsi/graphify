# assemble node+edge dicts into a NetworkX graph, preserving edge direction
from __future__ import annotations
import sys
from pathlib import Path
import networkx as nx
from .validate import validate_extraction


def build_from_json(extraction: dict, *, directed: bool = False) -> "nx.Graph":
    # Detect and warn about legacy "source" field on nodes; rename to "source_file" without mutating caller data.
    nodes = extraction.get("nodes", [])
    edges = extraction.get("edges", [])
    legacy_nodes = [n for n in nodes if isinstance(n, dict) and "source_file" not in n and "source" in n]
    if legacy_nodes:
        legacy_ids = {n["id"] for n in legacy_nodes if "id" in n}
        affected_edge_count = sum(
            1 for e in edges
            if isinstance(e, dict) and (e.get("source") in legacy_ids or e.get("target") in legacy_ids)
        )
        print(
            f"[graphify] WARNING: {len(legacy_nodes)} node(s) use legacy field 'source' instead of 'source_file' "
            f"({affected_edge_count} affected edge(s)). Rename 'source' -> 'source_file' in your extraction.",
            file=sys.stderr,
        )
        # Build a patched copy - do not mutate caller's dicts
        extraction = dict(extraction)
        extraction["nodes"] = [
            {**{k: v for k, v in n.items() if k != "source"}, "source_file": n["source"]}
            if isinstance(n, dict) and "source_file" not in n and "source" in n
            else n
            for n in nodes
        ]

    errors = validate_extraction(extraction)
    # Dangling edges (stdlib/external imports) are expected - only warn about real schema errors.
    real_errors = [e for e in errors if "does not match any node id" not in e]
    if real_errors:
        print(f"[graphify] Extraction warning ({len(real_errors)} issues): {real_errors[0]}", file=sys.stderr)
    G: nx.Graph = nx.DiGraph() if directed else nx.Graph()
    for node in extraction.get("nodes", []):
        G.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    node_set = set(G.nodes())
    for edge in extraction.get("edges", []):
        src, tgt = edge["source"], edge["target"]
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
    # Strip degree-0 code nodes — they are bundled/synthetic symbols with no
    # connections and only inflate god-node centrality and clustering noise.
    # Document, paper, and image nodes are kept even when isolated since they
    # may be leaf concepts intentionally referenced by the skill.
    isolated_code = [
        n for n in list(G.nodes())
        if G.degree(n) == 0 and G.nodes[n].get("file_type") == "code"
    ]
    G.remove_nodes_from(isolated_code)
    return G


def build(extractions: list[dict], *, directed: bool = False) -> "nx.Graph":
    """Merge multiple extraction results into one graph."""
    combined: dict = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
    for ext in extractions:
        combined["nodes"].extend(ext.get("nodes", []))
        combined["edges"].extend(ext.get("edges", []))
        combined["input_tokens"] += ext.get("input_tokens", 0)
        combined["output_tokens"] += ext.get("output_tokens", 0)
    return build_from_json(combined, directed=directed)


def build_merge(
    new_extractions: list[dict],
    existing_graph_path,
    *,
    directed: bool = False,
    force: bool = False,
) -> "nx.Graph":
    """Load existing graph, merge new_extractions in, never replace only grow."""
    from networkx.readwrite import json_graph
    import json as _json

    new_G = build(new_extractions, directed=directed)
    existing_path = Path(existing_graph_path)

    if existing_path.exists():
        existing_data = _json.loads(existing_path.read_text())
        old_G = json_graph.node_link_graph(existing_data, edges="edges")
        merged_G = old_G.copy()
        merged_G.update(new_G)
        if not force:
            nodes_list = existing_data.get("nodes")
            old_count = len(nodes_list) if nodes_list is not None else old_G.number_of_nodes()
            if merged_G.number_of_nodes() < old_count:
                raise ValueError(
                    f"[graphify] build_merge: merged graph has {merged_G.number_of_nodes()} nodes "
                    f"but existing had {old_count}. Pass force=True to override."
                )
    else:
        merged_G = new_G

    return merged_G
