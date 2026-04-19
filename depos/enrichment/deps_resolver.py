"""Cross-link code imports to dependency nodes."""
from __future__ import annotations

from pathlib import Path

import networkx as nx


def _import_names(attrs: dict) -> set[str]:
    names: set[str] = set()
    for key in ("import_name", "module_name", "package_name"):
        value = attrs.get(key)
        if isinstance(value, str) and value.strip():
            names.add(value.split(".")[0])
    label = str(attrs.get("label") or "")
    if label.startswith("import "):
        target = label.replace("import ", "", 1).split()[0].split(".")[0]
        if target:
            names.add(target)
    return names


def emit_dependency_edges(graph: nx.DiGraph, *, repo_root: Path | None = None) -> int:
    _ = repo_root
    dep_index: dict[str, list[tuple[str, dict]]] = {}
    for node_id, attrs in graph.nodes(data=True):
        if str(attrs.get("node_kind") or "") not in {"package_dep", "lockfile_resolution"}:
            continue
        name = str(attrs.get("package_name") or attrs.get("name") or "").split(".")[0]
        if name:
            dep_index.setdefault(name, []).append((node_id, attrs))
    added = 0
    for node_id, attrs in list(graph.nodes(data=True)):
        if str(attrs.get("node_kind") or "") in {"package_dep", "lockfile_resolution", "package_manifest"}:
            continue
        if not attrs.get("source_file"):
            continue
        for name in _import_names(attrs):
            for target_id, target_attrs in dep_index.get(name, []):
                if graph.has_edge(node_id, target_id):
                    continue
                graph.add_edge(
                    node_id,
                    target_id,
                    relation="IMPORTS_PACKAGE",
                    source_system="code",
                    target_system="deps",
                    confidence=1.0,
                    inferred=False,
                    drift_kind="lockfile_drift" if target_attrs.get("lockfile_drift") else "",
                )
                added += 1
    return added


__all__ = ["emit_dependency_edges"]
