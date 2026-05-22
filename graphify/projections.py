"""Projection helpers for graph consumers that need explicit edge semantics."""

from __future__ import annotations

from collections.abc import Hashable, Iterable
from typing import Any, Literal, cast

import networkx as nx

WeightMode = Literal["confidence", "count", "sum"]

_CONFIDENCE_SCORE = {
    "EXTRACTED": 1.0,
    "INFERRED": 0.5,
    "AMBIGUOUS": 0.2,
}


def _confidence_score(data: dict[str, Any]) -> float:
    raw_score = data.get("confidence_score")
    if isinstance(raw_score, int | float) and not isinstance(raw_score, bool):  # Python 3.10+
        return float(raw_score)
    raw_confidence = data.get("confidence")
    if isinstance(raw_confidence, str):
        return _CONFIDENCE_SCORE.get(raw_confidence.upper(), 0.0)
    return 0.0


def _edge_sort_key(data: dict[str, Any]) -> tuple:
    return (
        -_confidence_score(data),
        str(data.get("relation", "")),
        str(data.get("source_file", "")),
        str(data.get("source_location", "")),
        str(data.get("context", "")),
        repr(sorted((str(key), repr(value)) for key, value in data.items())),
    )


def _iter_edge_data(G: nx.Graph) -> Iterable[tuple[Any, Any, Any, dict[str, Any]]]:
    if isinstance(G, nx.MultiGraph | nx.MultiDiGraph):  # Python 3.10+
        yield from G.edges(keys=True, data=True)
        return
    for u, v, data in G.edges(data=True):
        yield u, v, None, data


def _copy_graph_skeleton(G: nx.Graph, graph_type: type[nx.Graph]) -> nx.Graph:
    H = graph_type()
    H.graph.update(G.graph)
    H.add_nodes_from((node, attrs.copy()) for node, attrs in G.nodes(data=True))
    return H


def _unordered_pair(u: Any, v: Any) -> tuple[Any, Any]:
    if repr(u) <= repr(v):
        return u, v
    return v, u


def _merged_edge_attrs(records: list[dict[str, Any]], weight_mode: WeightMode) -> dict[str, Any]:
    if weight_mode not in ("confidence", "count", "sum"):
        raise ValueError("weight_mode must be one of: confidence, count, sum")
    sorted_records = sorted(records, key=_edge_sort_key)
    representative = sorted_records[0].copy()
    scores = [_confidence_score(record) for record in records]
    if weight_mode == "confidence":
        weight = max(scores, default=0.0)
    elif weight_mode == "count":
        weight = float(len(records))
    else:
        weight = float(sum(scores))
    representative["weight"] = weight
    representative["parallel_edge_count"] = len(records)
    return representative


def project_for_community(G: nx.Graph, *, weight_mode: WeightMode = "confidence") -> nx.Graph:
    """Return a simple undirected projection for clustering and community metrics."""
    groups: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for u, v, _key, data in _iter_edge_data(G):
        if u == v:
            continue
        pair = _unordered_pair(u, v)
        groups.setdefault(pair, []).append(dict(data))

    H = _copy_graph_skeleton(G, nx.Graph)
    for (u, v), records in sorted(
        groups.items(), key=lambda item: (repr(item[0][0]), repr(item[0][1]))
    ):
        H.add_edge(u, v, **_merged_edge_attrs(records, weight_mode))
    return H


def project_for_path(G: nx.Graph) -> nx.Graph:
    """Return a simple undirected topology projection for path search."""
    return project_for_community(G, weight_mode="count")


def project_for_callflow(
    G: nx.Graph,
    *,
    relations: frozenset[str] | set[str] | None = None,
) -> nx.DiGraph:
    """Return a simple directed projection for callflow-style consumers."""
    relation_filter = set(relations) if relations is not None else None
    groups: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for u, v, _key, data in _iter_edge_data(G):
        relation = data.get("relation")
        # Guard against non-string `relation`; relation_filter is set[str], and
        # an unhashable relation would TypeError on the `in` membership test.
        if relation_filter is not None and (
            not isinstance(relation, str) or relation not in relation_filter
        ):
            continue
        src = data.get("_src", u)
        tgt = data.get("_tgt", v)
        if src == tgt:
            continue
        groups.setdefault((src, tgt), []).append(dict(data))

    H = cast(nx.DiGraph, _copy_graph_skeleton(G, nx.DiGraph))
    for (src, tgt), records in sorted(
        groups.items(), key=lambda item: (repr(item[0][0]), repr(item[0][1]))
    ):
        if src not in H:
            H.add_node(src)
        if tgt not in H:
            H.add_node(tgt)
        H.add_edge(src, tgt, **_merged_edge_attrs(records, "confidence"))
    return H


def _normalize_contexts(contexts: Iterable[str] | str | None) -> set[str] | None:
    if contexts is None:
        return None
    raw_contexts = [contexts] if isinstance(contexts, str) else contexts
    normalized = {str(context).strip().lower() for context in raw_contexts if str(context).strip()}
    return normalized or None


def project_for_context(G: nx.Graph, *, contexts: Iterable[str] | str | None = None) -> nx.Graph:
    """Return a graph copy containing only edges whose context matches the filter."""
    filters = _normalize_contexts(contexts)
    H = _copy_graph_skeleton(G, G.__class__)
    for u, v, key, data in _iter_edge_data(G):
        if filters is not None and str(data.get("context", "")).strip().lower() not in filters:
            continue
        if isinstance(H, nx.MultiGraph | nx.MultiDiGraph):  # Python 3.10+
            H.add_edge(u, v, key=key, **data)
        else:
            H.add_edge(u, v, **data)
    return H


def edge_records_between(G: nx.Graph, u: Hashable, v: Hashable) -> list[dict[str, Any]]:
    """Return shallow copies of all edge records connecting two nodes."""
    records: list[dict[str, Any]] = []

    def collect(src: Hashable, tgt: Hashable) -> None:
        if not G.has_edge(src, tgt):
            return
        raw = G.get_edge_data(src, tgt)
        if not isinstance(raw, dict):
            return
        if isinstance(G, nx.MultiGraph | nx.MultiDiGraph):  # Python 3.10+
            records.extend(dict(data) for data in raw.values() if isinstance(data, dict))
        else:
            records.append(dict(raw))

    collect(u, v)
    if G.is_directed() and u != v:
        collect(v, u)
    return sorted(records, key=_edge_sort_key)


def edge_summary_between(G: nx.Graph, u: Hashable, v: Hashable) -> dict[str, Any]:
    """Summarize all relationships between two nodes for display consumers."""
    records = edge_records_between(G, u, v)
    representative = records[0].copy() if records else {}
    return {
        "count": len(records),
        "relations": sorted(
            {str(record.get("relation")) for record in records if record.get("relation")}
        ),
        "confidences": sorted(
            {str(record.get("confidence")) for record in records if record.get("confidence")}
        ),
        "representative": representative,
    }


def distinct_neighbor_degree(G: nx.Graph, node: Hashable) -> int:
    """Count unique adjacent nodes without inflating parallel edges."""
    if node not in G:
        return 0
    if G.is_directed():
        directed = cast(nx.DiGraph, G)
        return len(set(directed.predecessors(node)) | set(directed.successors(node)))
    return len(set(G.neighbors(node)))


def normalize_to_multidigraph(G: nx.Graph) -> nx.MultiDiGraph:
    """Return a MultiDiGraph copy, preserving parallel keys when present."""
    H = nx.MultiDiGraph()
    H.graph.update(G.graph)
    H.add_nodes_from((node, attrs.copy()) for node, attrs in G.nodes(data=True))
    if isinstance(G, nx.MultiGraph | nx.MultiDiGraph):  # Python 3.10+
        for u, v, key, data in G.edges(keys=True, data=True):
            H.add_edge(u, v, key=key, **data)
    else:
        for u, v, data in G.edges(data=True):
            H.add_edge(u, v, **data)
    return H
