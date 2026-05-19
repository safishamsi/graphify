from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _edge_list(data: dict[str, Any]) -> list[Any]:
    if "links" in data:
        value = data.get("links")
    else:
        value = data.get("edges")
    return value if isinstance(value, list) else []


def _node_list(data: dict[str, Any]) -> list[Any]:
    value = data.get("nodes", [])
    return value if isinstance(value, list) else []


def inspect_graph(path: str | Path) -> dict[str, Any]:
    """Return schema-quality counters for a graphify graph.json file."""
    graph_path = Path(path)
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    raw_nodes = data.get("nodes", [])
    raw_edges = data.get("links") if "links" in data else data.get("edges", [])
    nodes = _node_list(data)
    edges = _edge_list(data)
    node_dicts = [n for n in nodes if isinstance(n, dict)]
    edge_dicts = [e for e in edges if isinstance(e, dict)]
    node_ids = [n.get("id") for n in node_dicts if n.get("id")]
    node_id_set = set(node_ids)

    dangling_edges = 0
    for edge in edge_dicts:
        src = edge.get("source")
        tgt = edge.get("target")
        if src and src not in node_id_set:
            dangling_edges += 1
        if tgt and tgt not in node_id_set:
            dangling_edges += 1

    issues = {
        "non_object_nodes": len(nodes) - len(node_dicts) if isinstance(raw_nodes, list) else 1,
        "non_object_edges": len(edges) - len(edge_dicts) if isinstance(raw_edges, list) else 1,
        "missing_node_ids": sum(1 for n in node_dicts if not n.get("id")),
        "missing_node_labels": sum(1 for n in node_dicts if not n.get("label")),
        "missing_node_source_files": sum(1 for n in node_dicts if not n.get("source_file")),
        "missing_edge_sources": sum(1 for e in edge_dicts if not e.get("source")),
        "missing_edge_targets": sum(1 for e in edge_dicts if not e.get("target")),
        "missing_edge_relations": sum(1 for e in edge_dicts if not e.get("relation")),
        "missing_edge_confidences": sum(1 for e in edge_dicts if not e.get("confidence")),
        "missing_edge_source_files": sum(1 for e in edge_dicts if not e.get("source_file")),
        "typo_confience_score_edges": sum(1 for e in edge_dicts if "confience_score" in e),
        "duplicate_node_ids": len(node_ids) - len(node_id_set),
        "dangling_edge_endpoints": dangling_edges,
    }
    total_issues = sum(issues.values())
    return {
        "path": str(graph_path),
        "nodes": len(node_dicts),
        "edges": len(edge_dicts),
        "issues": issues,
        "total_issues": total_issues,
        "status": "pass" if total_issues == 0 else "fail",
    }


def format_report(report: dict[str, Any]) -> str:
    """Return a concise human-readable graph quality report."""
    lines = [
        f"Graph quality: {report['status']}",
        f"  path: {report['path']}",
        f"  nodes: {report['nodes']}",
        f"  edges: {report['edges']}",
        f"  total issues: {report['total_issues']}",
    ]
    for key, value in report["issues"].items():
        if value:
            lines.append(f"  {key}: {value}")
    return "\n".join(lines)
