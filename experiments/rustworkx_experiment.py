"""Additive rustworkx experiment helpers.

This module is intentionally not wired into the production pipeline. It mirrors
the subset of graphify's current NetworkX usage that is easiest to evaluate
with rustworkx: graph construction, graph.json loading, neighbor traversal,
bounded BFS, shortest-path lookup, and simple graph stats.

The core migration constraint is that graphify uses string node IDs and dict
attributes heavily, while rustworkx uses integer node indices. To bridge that,
each rustworkx node stores the original graphify node dict as its payload and
this adapter maintains an ID↔index mapping.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

from graphify.validate import validate_extraction


@dataclass
class RustworkxGraphAdapter:
    graph: Any
    id_to_index: dict[str, int]
    index_to_id: dict[int, str]
    directed: bool
    metadata: dict[str, Any]

    def node_data(self, node_id: str) -> dict[str, Any]:
        return self.graph[self.id_to_index[node_id]]


def _load_rustworkx():
    try:
        import rustworkx as rx
    except ImportError as exc:
        raise ImportError(
            "rustworkx not installed. Run: pip install 'graphifyy[rustworkx]' or pip install rustworkx"
        ) from exc
    return rx


def _new_graph(directed: bool):
    rx = _load_rustworkx()
    return rx.PyDiGraph() if directed else rx.PyGraph()


def _warn_on_real_errors(extraction: dict) -> None:
    errors = validate_extraction(extraction)
    real_errors = [e for e in errors if "does not match any node id" not in e]
    if real_errors:
        print(
            f"[graphify] Extraction warning ({len(real_errors)} issues): {real_errors[0]}",
            file=sys.stderr,
        )


def _edge_payload(edge: dict, src: str, tgt: str) -> dict[str, Any]:
    attrs = {k: v for k, v in edge.items() if k not in ("source", "target", "from", "to")}
    attrs.setdefault("_src", src)
    attrs.setdefault("_tgt", tgt)
    return attrs


def _finalize_adapter(
    graph: Any,
    id_to_index: dict[str, int],
    directed: bool,
    metadata: dict[str, Any] | None = None,
) -> RustworkxGraphAdapter:
    return RustworkxGraphAdapter(
        graph=graph,
        id_to_index=id_to_index,
        index_to_id={index: node_id for node_id, index in id_to_index.items()},
        directed=directed,
        metadata=metadata or {},
    )


def build_rustworkx_from_extraction(extraction: dict, *, directed: bool = False) -> RustworkxGraphAdapter:
    """Build an additive rustworkx graph from graphify extraction output."""
    if "edges" not in extraction and "links" in extraction:
        extraction = dict(extraction, edges=extraction["links"])

    _warn_on_real_errors(extraction)

    graph = _new_graph(directed)
    id_to_index: dict[str, int] = {}

    for node in extraction.get("nodes", []):
        payload = dict(node)
        node_id = payload["id"]
        id_to_index[node_id] = graph.add_node(payload)

    edge_payloads: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in extraction.get("edges", []):
        src = edge.get("source", edge.get("from"))
        tgt = edge.get("target", edge.get("to"))
        if src not in id_to_index or tgt not in id_to_index:
            continue
        edge_key = (src, tgt) if directed else tuple(sorted((src, tgt)))
        edge_payloads[edge_key] = _edge_payload(edge, src, tgt)

    for src, tgt in edge_payloads:
        graph.add_edge(id_to_index[src], id_to_index[tgt], edge_payloads[(src, tgt)])

    metadata = {
        "hyperedges": list(extraction.get("hyperedges", [])),
        "input_tokens": extraction.get("input_tokens", 0),
        "output_tokens": extraction.get("output_tokens", 0),
        "source": "extraction",
    }
    return _finalize_adapter(graph, id_to_index, directed, metadata)


def build_rustworkx_from_graph_json(
    graph_path: str = "graphify-out/graph.json",
    *,
    directed: bool | None = None,
) -> RustworkxGraphAdapter:
    """Build an additive rustworkx graph from graphify's graph.json export."""
    data = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    graph_directed = bool(data.get("directed", False)) if directed is None else directed
    graph = _new_graph(graph_directed)
    id_to_index: dict[str, int] = {}

    for node in data.get("nodes", []):
        payload = dict(node)
        node_id = payload["id"]
        id_to_index[node_id] = graph.add_node(payload)

    for edge in data.get("links", data.get("edges", [])):
        src = edge.get("source")
        tgt = edge.get("target")
        if src not in id_to_index or tgt not in id_to_index:
            continue
        graph.add_edge(id_to_index[src], id_to_index[tgt], _edge_payload(edge, src, tgt))

    metadata = {
        "graph_attrs": dict(data.get("graph", {})),
        "source": "graph.json",
    }
    return _finalize_adapter(graph, id_to_index, graph_directed, metadata)


def build_rustworkx_from_networkx(G: Any) -> RustworkxGraphAdapter:
    """Bridge an existing NetworkX graph into rustworkx without mutating runtime code."""
    directed = bool(G.is_directed())
    graph = _new_graph(directed)
    id_to_index: dict[str, int] = {}

    for node_id, data in G.nodes(data=True):
        payload = {"id": node_id, **dict(data)}
        id_to_index[node_id] = graph.add_node(payload)

    for src, tgt, data in G.edges(data=True):
        graph.add_edge(id_to_index[src], id_to_index[tgt], _edge_payload(dict(data), src, tgt))

    metadata = {
        "graph_attrs": dict(getattr(G, "graph", {})),
        "source": "networkx",
    }
    return _finalize_adapter(graph, id_to_index, directed, metadata)


def rustworkx_neighbors(adapter: RustworkxGraphAdapter, node_id: str) -> list[str]:
    """Return neighbor IDs using graphify's original string node IDs."""
    node_index = adapter.id_to_index[node_id]
    return [adapter.index_to_id[index] for index in adapter.graph.neighbors(node_index)]


def rustworkx_bfs(
    adapter: RustworkxGraphAdapter,
    start_ids: list[str],
    depth: int = 3,
) -> tuple[set[str], list[tuple[str, str]]]:
    """Bounded BFS using original node IDs for inputs and outputs."""
    visited: set[str] = set(start_ids)
    frontier = deque((node_id, 0) for node_id in start_ids)
    edges_seen: list[tuple[str, str]] = []

    while frontier:
        node_id, node_depth = frontier.popleft()
        if node_depth >= depth:
            continue
        for neighbor_id in rustworkx_neighbors(adapter, node_id):
            edges_seen.append((node_id, neighbor_id))
            if neighbor_id in visited:
                continue
            visited.add(neighbor_id)
            frontier.append((neighbor_id, node_depth + 1))
    return visited, edges_seen


def rustworkx_shortest_path(
    adapter: RustworkxGraphAdapter,
    source_id: str,
    target_id: str,
) -> list[str]:
    """Return one unweighted shortest path using graphify's original node IDs."""
    if source_id not in adapter.id_to_index or target_id not in adapter.id_to_index:
        return []

    rx = _load_rustworkx()
    source_index = adapter.id_to_index[source_id]
    target_index = adapter.id_to_index[target_id]
    if adapter.directed:
        paths = rx.digraph_all_shortest_paths(adapter.graph, source_index, target_index)
    else:
        paths = rx.graph_all_shortest_paths(adapter.graph, source_index, target_index)
    if not paths:
        return []
    return [adapter.index_to_id[index] for index in paths[0]]


def rustworkx_graph_stats(adapter: RustworkxGraphAdapter) -> dict[str, Any]:
    """Return simple stats for side-by-side comparisons with NetworkX graphs."""
    isolate_count = 0
    for index in adapter.index_to_id:
        if not list(adapter.graph.neighbors(index)):
            isolate_count += 1
    return {
        "nodes": adapter.graph.num_nodes(),
        "edges": adapter.graph.num_edges(),
        "directed": adapter.directed,
        "isolates": isolate_count,
        "metadata": dict(adapter.metadata),
    }
