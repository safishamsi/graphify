"""Whitelisted helpers for detector DSL expressions."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

import networkx as nx


def attr(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def regex(pattern: str, value: Any) -> bool:
    return bool(re.search(pattern, str(value or "")))


def has_edge(graph: nx.DiGraph, rel: str, src: str | None = None, dst: str | None = None) -> bool:
    if src and dst:
        return any(data.get("relation") == rel for _, _, data in graph.edges(src, dst, data=True))
    if src:
        return any(data.get("relation") == rel for _, _, data in graph.out_edges(src, data=True))
    if dst:
        return any(data.get("relation") == rel for _, _, data in graph.in_edges(dst, data=True))
    return any(data.get("relation") == rel for _, _, data in graph.edges(data=True))


def count(items: Iterable[Any]) -> int:
    if isinstance(items, (list, tuple, set, dict)):
        return len(items)
    return sum(1 for _ in items)


def version_satisfies(range_spec: str, version: str) -> bool:
    try:
        from depos.analysis.oracles.pep440 import satisfies as pep440_satisfies

        if pep440_satisfies(range_spec, version):
            return True
    except Exception:
        pass
    try:
        from depos.analysis.oracles.semver import satisfies as semver_satisfies

        return semver_satisfies(range_spec, version)
    except Exception:
        return False


def cross_universe(node: Any) -> bool:
    universe = str(attr(node, "universe", attr(node, "source_system", "")) or "")
    return bool(universe and universe not in {"code", "python", "typescript", "javascript"})


def siblings_with_same_pkg(node: Any, *, graph: nx.DiGraph) -> list[dict[str, Any]]:
    name = str(attr(node, "package_name", "") or attr(node, "name", ""))
    if not name:
        return []
    out: list[dict[str, Any]] = []
    for _, attrs in graph.nodes(data=True):
        if str(attrs.get("package_name", "") or attrs.get("name", "")) == name:
            out.append(dict(attrs))
    return out


def all_satisfy_common_range(node: Any, *, graph: nx.DiGraph) -> bool:
    siblings = siblings_with_same_pkg(node, graph=graph)
    ranges = [str(row.get("declared_range", "")).strip() for row in siblings if str(row.get("declared_range", "")).strip()]
    if len(ranges) <= 1:
        return True
    versions = [str(row.get("resolved_version", "")).strip() for row in siblings if str(row.get("resolved_version", "")).strip()]
    if not versions:
        return len(set(ranges)) == 1
    return all(any(version_satisfies(spec, version) for spec in ranges) for version in versions)


def schema_validate(schema_id: str, payload: Any, *, registry: dict[str, Any] | None = None) -> bool:
    if registry is None or schema_id not in registry:
        return False
    from depos.analysis.oracles.json_schema import validate_payload

    return validate_payload(registry[schema_id], payload).conclusion == "pass"


def path_endswith(path_value: Any, suffix: str) -> bool:
    return str(Path(str(path_value or "")).as_posix()).endswith(str(Path(suffix).as_posix()))


HELPERS = {
    "attr": attr,
    "regex": regex,
    "has_edge": has_edge,
    "count": count,
    "version_satisfies": version_satisfies,
    "cross_universe": cross_universe,
    "siblings_with_same_pkg": siblings_with_same_pkg,
    "all_satisfy_common_range": all_satisfy_common_range,
    "schema_validate": schema_validate,
    "path_endswith": path_endswith,
}


__all__ = ["HELPERS"]
