"""Attach diagnostics to an existing NetworkX graph (post build_from_json)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import networkx as nx

from depos.diagnostics import map_diagnostics_to_nodes, mark_edge_faults_heuristic, parse_sarif
from depos.models import DiagnosticRef


def attach_diagnostics(
    G: nx.Graph,
    sarif: dict[str, Any] | None,
    *,
    repo_root: Path | None = None,
    extra: list[DiagnosticRef] | None = None,
) -> nx.Graph:
    """Mutate G: set node attrs errors, error_count, max_severity; edge fault flags."""
    diagnostics: list[DiagnosticRef] = list(extra or [])
    if sarif:
        diagnostics.extend(parse_sarif(sarif))
    root = repo_root
    mapping = map_diagnostics_to_nodes(G, diagnostics, repo_root=root)

    for nid, diags in mapping.items():
        if nid not in G:
            continue
        ser = [d.model_dump(mode="json") for d in diags]
        G.nodes[nid]["errors"] = ser
        G.nodes[nid]["error_count"] = len(diags)
        sev_order = {"error": 3, "warning": 2, "note": 1}
        G.nodes[nid]["max_severity"] = max(
            (sev_order.get(d.severity, 0) for d in diags),
            default=0,
        )
        G.nodes[nid]["has_blocking_error"] = any(d.severity == "error" for d in diags)
        G.nodes[nid]["erroneous"] = True

    mark_edge_faults_heuristic(G, mapping)
    G.graph["diagnostic_mapping_stats"] = {"nodes_with_errors": len(mapping), "total": len(diagnostics)}
    return G


def graph_error_index(G: nx.Graph) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Build error_index and edge_fault_index for LLM export."""
    error_index: dict[str, list[dict[str, Any]]] = {}
    for nid, data in G.nodes(data=True):
        errs = data.get("errors")
        if errs:
            error_index[nid] = errs
    edge_fault_index: list[dict[str, Any]] = []
    for u, v, data in G.edges(data=True):
        if data.get("fault"):
            edge_fault_index.append(
                {
                    "source": u,
                    "target": v,
                    "fault": True,
                    "fault_categories": data.get("fault_categories", []),
                    "relation": data.get("relation"),
                }
            )
    return error_index, edge_fault_index
