"""Parse SARIF and map diagnostics to graph nodes."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import networkx as nx

from depos.models import DiagnosticCategory, DiagnosticRef

_LEVEL_TO_SEVERITY = {
    "error": "error",
    "warning": "warning",
    "note": "note",
    "none": "note",
}


def _cat_from_rule(rule_id: str, message: str) -> DiagnosticCategory:
    rid = (rule_id or "").lower()
    msg = (message or "").lower()
    if "security" in rid or "semgrep" in rid or "sql injection" in msg:
        return DiagnosticCategory.security
    if "test" in rid or "pytest" in rid or "assert" in msg:
        return DiagnosticCategory.test_failure
    if "import" in msg or "cannot find" in msg or "unresolved" in msg:
        return DiagnosticCategory.unresolved
    if "type" in rid or "ts" in rid or "mypy" in rid or "pyright" in rid:
        return DiagnosticCategory.type_error
    if "eslint" in rid or "lint" in rid or "ruff" in rid:
        return DiagnosticCategory.lint
    if "build" in rid or "compile" in msg or "syntax" in msg:
        return DiagnosticCategory.build
    return DiagnosticCategory.unknown


def parse_sarif(sarif: dict[str, Any], *, tool_name: str = "sarif") -> list[DiagnosticRef]:
    """Extract DiagnosticRef list from SARIF 2.1 JSON."""
    out: list[DiagnosticRef] = []
    for run in sarif.get("runs") or []:
        driver = (run.get("tool") or {}).get("driver") or {}
        tname = driver.get("name") or tool_name
        for i, res in enumerate(run.get("results") or []):
            rule_id = res.get("ruleId") or ""
            level = _LEVEL_TO_SEVERITY.get(str(res.get("level", "error")).lower(), "error")
            msg_obj = res.get("message") or {}
            text = msg_obj.get("text") or ""
            if not text and isinstance(msg_obj.get("markdown"), str):
                text = msg_obj["markdown"]
            for loc in res.get("locations") or []:
                phys = loc.get("physicalLocation") or {}
                art = phys.get("artifactLocation") or {}
                uri = art.get("uri") or ""
                region = phys.get("region") or {}
                sl = int(region.get("startLine") or 0)
                el = int(region.get("endLine") or sl)
                uid = hashlib.sha256(f"{tname}:{rule_id}:{uri}:{sl}:{i}".encode()).hexdigest()[:16]
                out.append(
                    DiagnosticRef(
                        id=uid,
                        category=_cat_from_rule(rule_id, text),
                        severity=level,
                        rule_id=rule_id or None,
                        message=text[:4000],
                        tool=tname,
                        uri=uri,
                        start_line=sl,
                        end_line=el,
                    )
                )
    return out


def _norm_path(p: str) -> str:
    return str(Path(p).as_posix()).lstrip("./")


def _parse_source_line(loc: str | None) -> int | None:
    if not loc:
        return None
    m = re.match(r"L(\d+)", str(loc).strip())
    return int(m.group(1)) if m else None


def map_diagnostics_to_nodes(
    G: nx.Graph,
    diagnostics: list[DiagnosticRef],
    *,
    repo_root: Path | None = None,
) -> dict[str, list[DiagnosticRef]]:
    """Map each diagnostic to the best-matching node id(s). Returns node_id -> list."""
    mapping: dict[str, list[DiagnosticRef]] = {}
    nodes_by_file: dict[str, list[tuple[str, int | None, str]]] = {}
    for nid, data in G.nodes(data=True):
        sf = data.get("source_file") or ""
        if not sf:
            continue
        key = _norm_path(sf)
        line = _parse_source_line(data.get("source_location"))
        label = str(data.get("label") or "")
        nodes_by_file.setdefault(key, []).append((nid, line, label))

    for d in diagnostics:
        uri = d.uri
        if not uri:
            continue
        # strip file:// and normalize
        path = uri.replace("file://", "").split("?", 1)[0]
        key = _norm_path(path)
        if repo_root:
            try:
                rel = Path(path).resolve().relative_to(repo_root.resolve())
                key = _norm_path(str(rel))
            except ValueError:
                pass

        candidates = []
        for k, lst in nodes_by_file.items():
            if k.endswith(key) or key.endswith(k) or k == key:
                candidates.extend(lst)
        if not candidates:
            # try basename match
            base = Path(key).name
            for k, lst in nodes_by_file.items():
                if k.endswith(base):
                    candidates.extend(lst)

        if not candidates:
            continue

        best: tuple[str, int] | None = None
        for nid, line, _lbl in candidates:
            if line is None:
                dist = 10_000
            elif d.start_line <= 0:
                dist = 0
            else:
                dist = abs(line - d.start_line)
            if best is None or dist < best[1]:
                best = (nid, dist)
        if best:
            mapping.setdefault(best[0], []).append(d)
    return mapping


def mark_edge_faults_heuristic(G: nx.Graph, mapping: dict[str, list[DiagnosticRef]]) -> None:
    """Mark edges as faulty when both endpoints have errors or unresolved category."""
    erroneous = set(mapping.keys())
    for u, v, data in G.edges(data=True):
        if data.get("fault"):
            continue
        if u in erroneous and v in erroneous:
            data["fault"] = True
            data["fault_categories"] = ["lint"]
        rel = data.get("relation", "")
        if rel in ("imports", "uses") and (u in erroneous or v in erroneous):
            combined = mapping.get(u, []) + mapping.get(v, [])
            cats = [d.category.value for d in combined]
            if "unresolved" in cats or "type_error" in cats:
                data["fault"] = True
                data["fault_categories"] = list({c for c in cats if c})
