"""HTTP probes: lift FastAPI route decorators and TypeScript fetch / axios
URL literals onto the graph.

Graphify does not extract:
- FastAPI ``@router.get(...)``/``@app.post(...)`` decorator arguments.
- Literal URL strings passed to ``fetch(...)`` or ``axios.<method>(...)``.

These probes re-read the Python / TS source files referenced by existing
nodes and annotate those nodes with ``route_pattern``, ``http_method``,
``decorator``, ``url_literal``, ``url_template_tokens``, and
``is_dynamic_url``. We do NOT edit ``graphify/extract.py`` \u2014 all new
logic lives under ``depos/enrichment/`` so the vendored library stays
upstream-clean.

The probes are regex-based for portability (no extra tree-sitter wiring
needed in PR 2). They operate per-file and only on files already
referenced by graph nodes, so they do not blow up on gigantic repos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import networkx as nx

# ---------------------------------------------------------------------------
# FastAPI route decorator lifter (Python)
# ---------------------------------------------------------------------------

# Matches @router.get("/repos"), @app.post("/x", status_code=201), etc.
_FASTAPI_DECORATOR = re.compile(
    r"@(?P<obj>[A-Za-z_][A-Za-z0-9_]*)\.(?P<method>get|post|put|patch|delete|options|head)"
    r"\s*\(\s*(?P<quote>[\"'])(?P<path>[^\"']+)(?P=quote)",
)

# Matches `def handler_name(` on a line that immediately follows one or more
# decorators. We look at the raw source below each decorator for a function
# definition.
_FUNCDEF = re.compile(r"^\s*(?:async\s+)?def\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE)


@dataclass
class RouteDecoration:
    file: str
    handler_name: str
    http_method: str  # uppercase
    route_pattern: str
    decorator_object: str
    line: int


def scan_fastapi_routes(source: str, *, file: str) -> list[RouteDecoration]:
    """Return all FastAPI route decorations discovered in ``source``.

    Each decoration is paired with the *next* function definition in the file.
    """
    out: list[RouteDecoration] = []
    lines = source.splitlines()
    for m in _FASTAPI_DECORATOR.finditer(source):
        start = m.start()
        line_no = source[:start].count("\n") + 1
        # Walk forward to find the next function definition.
        rest = source[m.end():]
        fm = _FUNCDEF.search(rest)
        handler = fm.group("name") if fm else ""
        out.append(
            RouteDecoration(
                file=file,
                handler_name=handler,
                http_method=m.group("method").upper(),
                route_pattern=m.group("path"),
                decorator_object=m.group("obj"),
                line=line_no,
            )
        )
    return out


# ---------------------------------------------------------------------------
# TypeScript fetch / axios call lifter
# ---------------------------------------------------------------------------

# fetch("/api/...") with optional `{ method: 'GET' }` second arg.
_TS_FETCH = re.compile(
    r"""fetch\s*\(\s*
        (?P<quote>[`'"])(?P<url>[^`'"]+)(?P=quote)       # url literal or template
        (?:\s*,\s*\{(?P<options>[^}]*)\})?              # optional options
    """,
    re.VERBOSE,
)

# axios.get("/api/..."), axios.post("/api/...", body), axios("/...", {...})
_TS_AXIOS = re.compile(
    r"""axios
        (?:\.(?P<method>get|post|put|patch|delete|options|head))?
        \s*\(\s*
        (?P<quote>[`'"])(?P<url>[^`'"]+)(?P=quote)
    """,
    re.VERBOSE,
)

# ${ } inside a template literal -> dynamic URL
_TEMPLATE_EXPR = re.compile(r"\$\{([^}]+)\}")


def _detect_method(options_blob: Optional[str]) -> Optional[str]:
    if not options_blob:
        return None
    m = re.search(r"method\s*:\s*['\"]([A-Za-z]+)['\"]", options_blob)
    return m.group(1).upper() if m else None


@dataclass
class HTTPCallSite:
    file: str
    line: int
    url_literal: str
    url_template_tokens: list[str] = field(default_factory=list)
    is_dynamic_url: bool = False
    http_method: Optional[str] = None
    method_inferred: bool = False
    kind: str = "fetch"  # "fetch" | "axios"


def scan_ts_http_calls(source: str, *, file: str) -> list[HTTPCallSite]:
    out: list[HTTPCallSite] = []
    for m in _TS_FETCH.finditer(source):
        url = m.group("url")
        line = source[: m.start()].count("\n") + 1
        options = m.group("options")
        method = _detect_method(options)
        tokens = [t.strip() for t in _TEMPLATE_EXPR.findall(url)]
        dynamic = "${" in url
        out.append(
            HTTPCallSite(
                file=file,
                line=line,
                url_literal=url,
                url_template_tokens=tokens,
                is_dynamic_url=dynamic,
                http_method=method or ("GET" if not options else None),
                method_inferred=method is None,
                kind="fetch",
            )
        )
    for m in _TS_AXIOS.finditer(source):
        url = m.group("url")
        line = source[: m.start()].count("\n") + 1
        method = (m.group("method") or "get").upper()
        tokens = [t.strip() for t in _TEMPLATE_EXPR.findall(url)]
        dynamic = "${" in url
        out.append(
            HTTPCallSite(
                file=file,
                line=line,
                url_literal=url,
                url_template_tokens=tokens,
                is_dynamic_url=dynamic,
                http_method=method,
                method_inferred=False,
                kind="axios",
            )
        )
    return out


# ---------------------------------------------------------------------------
# Graph annotation
# ---------------------------------------------------------------------------

_PY_EXTS = {".py"}
_TS_EXTS = {".ts", ".tsx", ".js", ".jsx", ".mjs"}


def _unique_source_files(graph: nx.DiGraph, suffixes: set[str]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for _, attrs in graph.nodes(data=True):
        sf = attrs.get("source_file")
        if not sf or sf in seen:
            continue
        p = Path(sf)
        if p.suffix.lower() in suffixes:
            seen.add(sf)
            out.append(p)
    return out


def _node_for_file_and_name(
    graph: nx.DiGraph,
    *,
    source_file: str,
    name_hint: str,
) -> Optional[str]:
    sf_norm = Path(source_file).as_posix()
    name_suffix = f"{name_hint}()"
    for nid, attrs in graph.nodes(data=True):
        sf = attrs.get("source_file")
        if not sf:
            continue
        if Path(sf).as_posix() != sf_norm:
            continue
        label = attrs.get("label", "")
        if label == name_suffix or label == name_hint:
            return nid
    return None


def _nodes_for_file(graph: nx.DiGraph, source_file: str) -> list[str]:
    sf_norm = Path(source_file).as_posix()
    return [
        nid
        for nid, attrs in graph.nodes(data=True)
        if attrs.get("source_file") and Path(attrs["source_file"]).as_posix() == sf_norm
    ]


def _read_text_safely(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return None


def annotate_fastapi_routes(graph: nx.DiGraph, repo_root: Optional[Path] = None) -> list[str]:
    """Walk every distinct Python source file referenced by nodes, parse
    route decorations, and annotate the matching function-definition node
    with ``route_pattern`` / ``http_method`` / ``decorator``.

    Returns the list of annotated node IDs.
    """
    annotated: list[str] = []
    for p in _unique_source_files(graph, _PY_EXTS):
        full = p if p.is_absolute() else ((repo_root / p) if repo_root else p)
        text = _read_text_safely(full)
        if text is None:
            continue
        for dec in scan_fastapi_routes(text, file=p.as_posix()):
            nid = _node_for_file_and_name(graph, source_file=p.as_posix(), name_hint=dec.handler_name)
            if nid is None:
                continue
            attrs = graph.nodes[nid]
            attrs["route_pattern"] = dec.route_pattern
            attrs["http_method"] = dec.http_method
            attrs["decorator"] = f"@{dec.decorator_object}.{dec.http_method.lower()}"
            attrs["is_fastapi_route"] = True
            annotated.append(nid)
    return annotated


def annotate_ts_http_calls(graph: nx.DiGraph, repo_root: Optional[Path] = None) -> list[dict]:
    """Walk TS source files, find fetch/axios call sites, and attach a
    ``http_call_sites`` list attribute on one representative node per file.

    Returns the raw call site dicts (file + line + url + method + dynamic flag)
    so the caller can emit :data:`HTTP_CALLS_ROUTE` edges without having to
    rescan.
    """
    collected: list[dict] = []
    for p in _unique_source_files(graph, _TS_EXTS):
        full = p if p.is_absolute() else ((repo_root / p) if repo_root else p)
        text = _read_text_safely(full)
        if text is None:
            continue
        sites = scan_ts_http_calls(text, file=p.as_posix())
        if not sites:
            continue
        file_nodes = _nodes_for_file(graph, p.as_posix())
        if not file_nodes:
            continue
        call_site_dicts = [
            {
                "file": s.file,
                "line": s.line,
                "url_literal": s.url_literal,
                "url_template_tokens": s.url_template_tokens,
                "is_dynamic_url": s.is_dynamic_url,
                "http_method": s.http_method,
                "method_inferred": s.method_inferred,
                "kind": s.kind,
                "node_id": file_nodes[0],
            }
            for s in sites
        ]
        # Annotate the first file-level node; Module 1's edge emitter matches
        # on ``http_call_sites`` without caring which node specifically.
        graph.nodes[file_nodes[0]]["http_call_sites"] = call_site_dicts
        collected.extend(call_site_dicts)
    return collected


def iter_fastapi_route_nodes(graph: nx.DiGraph) -> Iterable[tuple[str, dict]]:
    for nid, attrs in graph.nodes(data=True):
        if attrs.get("is_fastapi_route"):
            yield nid, attrs
