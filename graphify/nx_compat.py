from __future__ import annotations

from typing import Any

from networkx.readwrite import json_graph

_ORIGINAL_NODE_LINK_DATA = json_graph.node_link_data
_ORIGINAL_NODE_LINK_GRAPH = json_graph.node_link_graph


def _normalize_edge_key(data: Any, edges: str | None) -> Any:
    if not isinstance(data, dict) or not edges:
        return data
    normalized = dict(data)
    if edges == "links" and "links" not in normalized and "edges" in normalized:
        normalized["links"] = normalized["edges"]
    elif edges == "edges" and "edges" not in normalized and "links" in normalized:
        normalized["edges"] = normalized["links"]
    return normalized


def node_link_data_compat(graph: Any, *, edges: str | None = None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if edges is not None:
        kwargs["edges"] = edges
    try:
        data = _ORIGINAL_NODE_LINK_DATA(graph, **kwargs)
    except TypeError:
        if edges is None:
            data = _ORIGINAL_NODE_LINK_DATA(graph)
        else:
            data = _ORIGINAL_NODE_LINK_DATA(graph, link=edges)
    return _normalize_edge_key(data, edges)


def node_link_graph_compat(data: dict[str, Any], *, edges: str | None = None) -> Any:
    payload = _normalize_edge_key(data, edges)
    kwargs: dict[str, Any] = {}
    if edges is not None:
        kwargs["edges"] = edges
    try:
        return _ORIGINAL_NODE_LINK_GRAPH(payload, **kwargs)
    except TypeError:
        if edges is None:
            return _ORIGINAL_NODE_LINK_GRAPH(payload)
        return _ORIGINAL_NODE_LINK_GRAPH(payload, link=edges)


def patch_json_graph_compat() -> None:
    if getattr(json_graph.node_link_data, "_graphify_compat", False):
        return

    def wrapped_node_link_data(graph: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        edges = kwargs.pop("edges", None)
        link = kwargs.pop("link", None)
        if edges is None:
            edges = link
        elif link is not None and link != edges:
            raise TypeError("Specify only one of 'edges' or legacy 'link'.")
        if edges is not None:
            kwargs["edges"] = edges
        try:
            data = _ORIGINAL_NODE_LINK_DATA(graph, *args, **kwargs)
        except TypeError:
            kwargs.pop("edges", None)
            if edges is not None:
                kwargs["link"] = edges
            data = _ORIGINAL_NODE_LINK_DATA(graph, *args, **kwargs)
        return _normalize_edge_key(data, edges)

    def wrapped_node_link_graph(data: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        edges = kwargs.pop("edges", None)
        link = kwargs.pop("link", None)
        if edges is None:
            edges = link
        elif link is not None and link != edges:
            raise TypeError("Specify only one of 'edges' or legacy 'link'.")
        payload = _normalize_edge_key(data, edges)
        if edges is not None:
            kwargs["edges"] = edges
        try:
            return _ORIGINAL_NODE_LINK_GRAPH(payload, *args, **kwargs)
        except TypeError:
            kwargs.pop("edges", None)
            if edges is not None:
                kwargs["link"] = edges
            return _ORIGINAL_NODE_LINK_GRAPH(payload, *args, **kwargs)

    wrapped_node_link_data._graphify_compat = True
    wrapped_node_link_graph._graphify_compat = True
    json_graph.node_link_data = wrapped_node_link_data
    json_graph.node_link_graph = wrapped_node_link_graph


__all__ = [
    "node_link_data_compat",
    "node_link_graph_compat",
    "patch_json_graph_compat",
]
