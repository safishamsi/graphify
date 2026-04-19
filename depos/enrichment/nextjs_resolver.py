"""Cross-link Next.js routes to middleware matchers."""
from __future__ import annotations

import re
from pathlib import Path

import networkx as nx


def _matches(route_path: str, matcher: str) -> bool:
    normalized = matcher.replace(":path*", ".*").replace("*", ".*")
    if normalized in {"/(.*)", ".*"}:
        return True
    try:
        return re.match(f"^{normalized}$", route_path) is not None
    except re.error:
        return route_path.startswith(matcher.rstrip("*"))


def emit_nextjs_edges(graph: nx.DiGraph, *, repo_root: Path | None = None) -> int:
    _ = repo_root
    middleware: list[tuple[str, list[str]]] = []
    for node_id, attrs in graph.nodes(data=True):
        if str(attrs.get("node_kind") or "") == "next_middleware":
            middleware.append((node_id, list(attrs.get("matchers") or ["/(.*)"])))
    added = 0
    for route_id, attrs in list(graph.nodes(data=True)):
        if str(attrs.get("node_kind") or "") != "next_route":
            continue
        route_path = str(attrs.get("path") or "/")
        for middleware_id, matchers in middleware:
            if any(_matches(route_path, matcher) for matcher in matchers) and not graph.has_edge(middleware_id, route_id):
                graph.add_edge(
                    middleware_id,
                    route_id,
                    relation="NEXT_ROUTE_GUARDED_BY_MIDDLEWARE",
                    source_system="nextjs",
                    target_system="nextjs",
                    confidence=0.9,
                    inferred=True,
                )
                added += 1
    return added


__all__ = ["emit_nextjs_edges"]
