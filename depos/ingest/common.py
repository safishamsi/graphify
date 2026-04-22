"""Shared ingest helpers for graph node and edge insertion."""
from __future__ import annotations

import networkx as nx


def upsert_node(graph: nx.DiGraph, node_id: str, **attrs) -> bool:
    """Insert a node once, updating attributes on repeated sightings."""
    if graph.has_node(node_id):
        graph.nodes[node_id].update(attrs)
        return False
    graph.add_node(node_id, **attrs)
    return True


def add_edge_once(graph: nx.DiGraph, source: str, target: str, **attrs) -> bool:
    """Insert an edge only when the endpoint pair has not been seen yet."""
    if graph.has_edge(source, target):
        return False
    graph.add_edge(source, target, **attrs)
    return True


__all__ = ["add_edge_once", "upsert_node"]
