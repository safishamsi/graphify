"""Cross-link code and Next routes to OpenAPI operations."""
from __future__ import annotations

from pathlib import Path

import networkx as nx

from depos.enrichment.url_normalize import normalize_route


def emit_openapi_edges(graph: nx.DiGraph, *, repo_root: Path | None = None) -> int:
    _ = repo_root
    operations: dict[tuple[str, str], str] = {}
    by_operation_id: dict[str, str] = {}
    for node_id, attrs in graph.nodes(data=True):
        if str(attrs.get("node_kind") or "") != "openapi_operation":
            continue
        method = str(attrs.get("method") or "").upper()
        path = str(attrs.get("path") or "")
        operations[(method, normalize_route(path, method=method).normalized)] = node_id
        operation_id = str(attrs.get("operation_id") or "")
        if operation_id:
            by_operation_id[operation_id] = node_id
    added = 0
    for node_id, attrs in list(graph.nodes(data=True)):
        method = ""
        path = ""
        relation = ""
        if attrs.get("is_fastapi_route"):
            method = str(attrs.get("http_method") or "").upper()
            path = str(attrs.get("route_pattern") or "")
            relation = "IMPLEMENTS_OPENAPI_OP"
        elif str(attrs.get("node_kind") or "") == "next_route":
            methods = attrs.get("methods") or []
            method = str(methods[0] if methods else "GET").upper()
            path = str(attrs.get("path") or "")
            relation = "CONSUMES_OPENAPI_OP"
        operation_id = str(attrs.get("operation_id") or attrs.get("openapi_operation_id") or "")
        target_id = by_operation_id.get(operation_id) if operation_id else None
        if target_id is None and method and path:
            target_id = operations.get((method, normalize_route(path, method=method).normalized))
        if target_id and not graph.has_edge(node_id, target_id):
            graph.add_edge(
                node_id,
                target_id,
                relation=relation,
                source_system="code" if relation == "IMPLEMENTS_OPENAPI_OP" else "nextjs",
                target_system="schema",
                confidence=0.95,
                inferred=False,
            )
            added += 1
    return added


__all__ = ["emit_openapi_edges"]
