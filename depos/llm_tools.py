"""Agent-oriented helpers (MCP-style surface without requiring MCP server)."""
from __future__ import annotations

from typing import Any

import networkx as nx

from depos.export_llm import build_llm_export
from depos.fusion import graph_error_index


def list_erroneous_nodes(G: nx.Graph) -> list[dict[str, Any]]:
    out = []
    for nid, data in G.nodes(data=True):
        if data.get("erroneous"):
            out.append({"id": nid, "label": data.get("label"), "errors": data.get("errors", [])})
    return out


def explain_blast_radius_json(G: nx.Graph, changed_files: list[str], hop_depth: int = 2) -> dict[str, Any]:
    exp = build_llm_export(G, changed_files=changed_files, hop_depth=hop_depth)
    return json_ready(exp.model_dump())


def json_ready(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return obj


def get_subgraph_with_errors(G: nx.Graph, node_ids: set[str]) -> dict[str, Any]:
    sub = G.subgraph(node_ids).copy()
    err_idx, edge_idx = graph_error_index(sub)
    from depos.snapshot import graph_to_node_link

    return {"graph": graph_to_node_link(sub), "error_index": err_idx, "edge_fault_index": edge_idx}
