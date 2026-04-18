"""Blast-radius: k-hop expansion from changed files; defect-aware scoring."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import networkx as nx

from depos.models import BlastRadiusResult


def _nodes_touching_files(G: nx.Graph, files: Iterable[str]) -> set[str]:
    """Find graph nodes whose source_file matches any changed path."""
    files_norm = {_norm(p) for p in files}
    seeds: set[str] = set()
    for nid, data in G.nodes(data=True):
        sf = data.get("source_file") or ""
        if not sf:
            continue
        n = _norm(sf)
        for f in files_norm:
            if n.endswith(f) or f.endswith(n) or n == f:
                seeds.add(nid)
                break
    return seeds


def _norm(p: str) -> str:
    return str(Path(p).as_posix()).replace("\\", "/")


def blast_radius(
    G: nx.Graph,
    changed_files: list[str],
    *,
    hop_depth: int = 2,
    directed: bool = True,
) -> BlastRadiusResult:
    """Expand from seed nodes along edges up to hop_depth."""
    seeds = _nodes_touching_files(G, changed_files)
    if not seeds and changed_files:
        # fallback: file-level nodes only
        for nid, data in G.nodes(data=True):
            lbl = data.get("label") or ""
            if any(Path(c).name == lbl for c in changed_files):
                seeds.add(nid)

    if not G.number_of_nodes():
        return BlastRadiusResult(seed_files=changed_files, hop_depth=hop_depth, summary="Empty graph.")

    # Use successors+predecessors for directed
    frontier = set(seeds)
    visited = set(seeds)
    def _neighbors_all(g: nx.Graph, n: str) -> set[str]:
        if g.is_directed():
            return set(g.successors(n)) | set(g.predecessors(n))
        return set(g.neighbors(n))

    for _ in range(hop_depth):
        nxt: set[str] = set()
        for n in frontier:
            others = _neighbors_all(G, n)
            for m in others:
                if m not in visited:
                    nxt.add(m)
                    visited.add(m)
        frontier = nxt
        if not frontier:
            break

    defect_boost = 0.0
    err_nodes = 0
    for n in visited:
        if G.nodes[n].get("erroneous"):
            err_nodes += 1
            defect_boost += G.nodes[n].get("error_count", 1)

    n = max(len(visited), 1)
    blast_score = min(1.0, len(visited) / (n + 10) + 0.1 * defect_boost)

    return BlastRadiusResult(
        seed_files=changed_files,
        impacted_node_ids=sorted(visited),
        hop_depth=hop_depth,
        blast_score=round(blast_score, 4),
        defect_boost=round(defect_boost, 4),
        summary=(
            f"{len(visited)} nodes within {hop_depth} hop(s) of {len(seeds)} seed(s); "
            f"{err_nodes} with diagnostics."
        ),
    )


def drift_edge_jaccard(G1: nx.Graph, G2: nx.Graph) -> float:
    """Simple structural drift metric between two graphs (edge sets)."""
    e1 = {tuple(sorted((u, v))) for u, v in G1.edges()}
    e2 = {tuple(sorted((u, v))) for u, v in G2.edges()}
    if not e1 and not e2:
        return 1.0
    inter = len(e1 & e2)
    union = len(e1 | e2)
    return inter / union if union else 0.0
