"""Merge per-repo graphs with optional cross-repo edges (allowlist-gated)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

from depos.snapshot import graph_to_node_link, load_graph_json


def merge_repo_graphs(
    repo_graphs: dict[str, nx.Graph],
    *,
    cross_repo_edges: list[dict[str, Any]] | None = None,
    allowed_repos: set[str] | None = None,
) -> nx.Graph:
    """
    Union graphs with prefixed node ids to avoid collisions.
    repo_graphs: repo_slug -> nx.Graph
    cross_repo_edges: {source_repo, source_id, target_repo, target_id, relation}
    """
    allowed = allowed_repos or set(repo_graphs.keys())
    H = nx.DiGraph()
    prefix_map: dict[tuple[str, str], str] = {}

    for repo, G in repo_graphs.items():
        if repo not in allowed:
            continue
        if not G.is_directed():
            G = G.to_directed()
        for nid, data in G.nodes(data=True):
            new_id = f"{repo}::{nid}"
            prefix_map[(repo, nid)] = new_id
            nd = dict(data)
            nd["repo"] = repo
            H.add_node(new_id, **nd)
        for u, v, data in G.edges(data=True):
            nu = prefix_map.get((repo, u))
            nv = prefix_map.get((repo, v))
            if nu and nv:
                H.add_edge(nu, nv, **dict(data), cross_repo=False)

    for e in cross_repo_edges or []:
        sr = e.get("source_repo")
        tr = e.get("target_repo")
        if allowed is not None and (sr not in allowed or tr not in allowed):
            continue
        su = prefix_map.get((sr, e.get("source_id")))
        tv = prefix_map.get((tr, e.get("target_id")))
        if su and tv:
            H.add_edge(su, tv, relation=e.get("relation", "depends_on"), cross_repo=True)

    return H


def save_federated_graph(G: nx.Graph, path: Path) -> None:
    path.write_text(json.dumps(graph_to_node_link(G), indent=2), encoding="utf-8")


def load_federated_graph(path: Path) -> nx.Graph:
    return load_graph_json(path)
