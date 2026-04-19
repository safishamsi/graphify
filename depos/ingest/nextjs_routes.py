"""Next.js App Router ingest."""
from __future__ import annotations

import re
from pathlib import Path

import networkx as nx

from depos.analysis.schemas import IngestReport

_ROUTE_SUFFIXES = ("page.tsx", "page.ts", "page.jsx", "page.js", "route.ts", "route.tsx", "route.js", "route.jsx", "layout.tsx", "layout.ts", "layout.jsx", "layout.js", "middleware.ts", "middleware.tsx", "middleware.js", "middleware.jsx")
_ENV_REF = re.compile(r"(?:process\.env\.|process\.env\[['\"]|os\.getenv\(['\"])([A-Z0-9_]+)")
_METHODS = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b")
_MATCHER = re.compile(r"matcher\s*:\s*(\[[^\]]+\]|['\"][^'\"]+['\"])")


def _add_node(graph: nx.DiGraph, node_id: str, **attrs) -> bool:
    if graph.has_node(node_id):
        graph.nodes[node_id].update(attrs)
        return False
    graph.add_node(node_id, **attrs)
    return True


def _add_edge(graph: nx.DiGraph, source: str, target: str, **attrs) -> bool:
    if graph.has_edge(source, target):
        return False
    graph.add_edge(source, target, **attrs)
    return True


def _route_path(rel: Path) -> str:
    parts = list(rel.parts)
    if "app" in parts:
        parts = parts[parts.index("app") + 1 :]
    if parts and parts[-1].split(".")[0] in {"page", "route", "layout", "middleware"}:
        parts = parts[:-1]
    path = "/" + "/".join(part for part in parts if not part.startswith("("))
    path = path.replace("/index", "")
    return path or "/"


def _route_kind(path: Path) -> str:
    stem = path.name.split(".", 1)[0]
    return "next_middleware" if stem == "middleware" else "next_route"


def _route_node_id(rel: Path) -> str:
    kind = "middleware" if rel.name.startswith("middleware.") else "route"
    return f"next::{kind}:{rel.as_posix()}"


def _nearest_layout(repo_root: Path, rel: Path) -> Path | None:
    parent = repo_root / rel.parent
    while True:
        for ext in (".tsx", ".ts", ".jsx", ".js"):
            candidate = parent / f"layout{ext}"
            if candidate.exists():
                return candidate
        if parent == repo_root:
            return None
        parent = parent.parent


def _middleware_matchers(text: str) -> list[str]:
    match = _MATCHER.search(text)
    if not match:
        return ["/(.*)"]
    raw = match.group(1)
    if raw.startswith("["):
        return [item.strip().strip("'\"") for item in raw.strip("[]").split(",") if item.strip()]
    return [raw.strip().strip("'\"")]


def _matcher_applies(route_path: str, matcher: str) -> bool:
    normalized = matcher.replace(":path*", ".*").replace("*", ".*")
    if normalized in {"/(.*)", ".*"}:
        return True
    try:
        return re.match(f"^{normalized}$", route_path) is not None
    except re.error:
        return route_path.startswith(matcher.rstrip("*"))


def ingest(graph: nx.DiGraph, *, repo_root: Path, config) -> IngestReport:
    report = IngestReport(module=__name__)
    middleware_nodes: list[tuple[str, list[str]]] = []
    for path in sorted(repo_root.glob("**/*")):
        if not path.is_file() or "node_modules" in path.parts or ".next" in path.parts:
            continue
        if path.name not in _ROUTE_SUFFIXES:
            continue
        rel = path.relative_to(repo_root)
        text = path.read_text(encoding="utf-8", errors="replace")
        report.files_seen += 1
        node_id = _route_node_id(rel)
        kind = _route_kind(path)
        route_path = _route_path(rel)
        env_refs = sorted(set(match.group(1) for match in _ENV_REF.finditer(text)))
        methods = sorted(set(_METHODS.findall(text))) or (["GET"] if "/route." in str(rel).replace("\\", "/") else [])
        session_checked = "getServerSession" in text or "auth()" in text or "requireUser" in text or "cookies()" in text
        public = "login" not in route_path and "auth" not in route_path and "private" not in route_path
        attrs = {
            "node_kind": kind,
            "universe": "nextjs",
            "source_file": str(path),
            "label": path.name,
            "path": route_path,
            "methods": methods,
            "is_server_component": path.name.startswith(("page.", "layout.")),
            "session_checked": session_checked,
            "public": public,
            "env_refs": env_refs,
            "matchers": _middleware_matchers(text) if kind == "next_middleware" else [],
        }
        if _add_node(graph, node_id, **attrs):
            report.nodes_added += 1
        if kind == "next_middleware":
            middleware_nodes.append((node_id, _middleware_matchers(text)))
        layout_path = _nearest_layout(repo_root, rel)
        if layout_path is not None and layout_path != path:
            layout_id = _route_node_id(layout_path.relative_to(repo_root))
            if _add_edge(graph, layout_id, node_id, relation="NEXT_ROUTE_USES_LAYOUT", source_system="nextjs", target_system="nextjs"):
                report.edges_added += 1
        for env_name in env_refs:
            env_id = f"env::{env_name}@{rel.as_posix()}"
            if not graph.has_node(env_id):
                graph.add_node(
                    env_id,
                    node_kind="env_var",
                    universe="env",
                    source_file=str(path),
                    name=env_name,
                    label=env_name,
                    defined=False,
                )
                report.nodes_added += 1
            if _add_edge(graph, node_id, env_id, relation="READS_ENV_VAR", source_system="nextjs", target_system="env"):
                report.edges_added += 1
    for route_id, attrs in list(graph.nodes(data=True)):
        if attrs.get("node_kind") != "next_route":
            continue
        route_path = str(attrs.get("path") or "/")
        for middleware_id, matchers in middleware_nodes:
            if any(_matcher_applies(route_path, matcher) for matcher in matchers):
                if _add_edge(graph, middleware_id, route_id, relation="NEXT_ROUTE_GUARDED_BY_MIDDLEWARE", source_system="nextjs", target_system="nextjs"):
                    report.edges_added += 1
    return report


__all__ = ["ingest"]
