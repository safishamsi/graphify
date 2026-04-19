"""Cross-link code env access to env/config nodes."""
from __future__ import annotations

import re
from pathlib import Path

import networkx as nx

_ENV_REF = re.compile(r"(?:process\.env\.|process\.env\[['\"]|os\.getenv\(['\"]|os\.environ(?:\.get)?\(['\"])([A-Z0-9_]+)")


def _candidate_nodes(graph: nx.DiGraph, source_file: str) -> list[str]:
    out = [
        node_id
        for node_id, attrs in graph.nodes(data=True)
        if str(attrs.get("source_file") or "") == source_file and str(attrs.get("node_kind") or "") not in {"env_var", "config_key"}
    ]
    return out[:1]


def emit_env_edges(graph: nx.DiGraph, *, repo_root: Path | None = None) -> int:
    if repo_root is None:
        return 0
    env_nodes: dict[str, list[str]] = {}
    for node_id, attrs in graph.nodes(data=True):
        if str(attrs.get("node_kind") or "") == "env_var":
            env_nodes.setdefault(str(attrs.get("name") or ""), []).append(node_id)
    added = 0
    seen_files: set[str] = set()
    for _, attrs in list(graph.nodes(data=True)):
        source_file = str(attrs.get("source_file") or "")
        if not source_file or source_file in seen_files:
            continue
        seen_files.add(source_file)
        path = Path(source_file)
        if not path.exists() or path.is_dir():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        readers = _candidate_nodes(graph, source_file)
        if not readers:
            continue
        source_id = readers[0]
        for match in _ENV_REF.finditer(text):
            name = match.group(1)
            targets = env_nodes.get(name, [])
            if not targets:
                synthetic_id = f"env::{name}@{path.name}"
                if not graph.has_node(synthetic_id):
                    graph.add_node(
                        synthetic_id,
                        node_kind="env_var",
                        universe="env",
                        source_file=source_file,
                        name=name,
                        label=name,
                        defined=False,
                    )
                targets = [synthetic_id]
            for target_id in targets:
                if graph.has_edge(source_id, target_id):
                    continue
                confidence = 1.0 if graph.nodes[target_id].get("defined") and not graph.nodes[target_id].get("typed_drift") else 0.8 if graph.nodes[target_id].get("defined") else 0.5
                graph.add_edge(
                    source_id,
                    target_id,
                    relation="READS_ENV_VAR",
                    source_system="code",
                    target_system="env",
                    confidence=confidence,
                    inferred=False,
                )
                added += 1
    return added


__all__ = ["emit_env_edges"]
