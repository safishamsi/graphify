"""LLM-oriented export (JSON) for Claude Code / MCP."""
from __future__ import annotations

import networkx as nx

from depos.blast import blast_radius
from depos.fusion import graph_error_index
from depos.models import BlastRadiusResult, LLMGraphExport
from depos.snapshot import graph_to_node_link


def build_llm_export(
    G: nx.Graph,
    *,
    changed_files: list[str] | None = None,
    hop_depth: int = 2,
) -> LLMGraphExport:
    """Produce node-link graph + error indices + optional blast radius."""
    err_idx, edge_idx = graph_error_index(G)
    blast: BlastRadiusResult | None = None
    if changed_files:
        blast = blast_radius(G, changed_files, hop_depth=hop_depth)

    summary_parts = [
        f"Nodes: {G.number_of_nodes()}, edges: {G.number_of_edges()}",
        f"Nodes with errors: {len(err_idx)}",
        f"Faulty edges: {len(edge_idx)}",
    ]
    if blast:
        summary_parts.append(blast.summary)
    exec_summary = " ".join(summary_parts)

    return LLMGraphExport(
        graph=graph_to_node_link(G),
        error_index=err_idx,
        edge_fault_index=edge_idx,
        executive_summary=exec_summary,
        blast_radius=blast,
    )


def subgraph_for_nodes(G: nx.Graph, node_ids: set[str]) -> nx.Graph:
    """Induced subgraph preserving edge attrs."""
    return G.subgraph(node_ids).copy()
