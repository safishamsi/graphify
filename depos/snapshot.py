"""Build a dependency graph using graphify extract → build_from_json only."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

from graphify.build import build_from_json
from graphify.detect import detect
from graphify.extract import extract

logger = logging.getLogger(__name__)


def build_graph_for_root(
    root: Path,
    *,
    directed: bool = True,
) -> tuple[dict, nx.Graph]:
    """Run graphify extract + build_from_json. Returns (extraction dict, NetworkX graph)."""
    root = root.resolve()
    detected = detect(root)
    paths = [Path(p) for p in detected.get("files", {}).get("code", [])]
    if not paths:
        empty: dict = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
        return empty, build_from_json(empty, directed=directed)
    extraction = extract(paths)
    g = build_from_json(extraction, directed=directed)
    return extraction, g


def graph_to_node_link(G: nx.Graph) -> dict:
    """Serialize graph for storage (node-link format)."""
    return json_graph.node_link_data(G, edges="links")


def persist_graph_json(G: nx.Graph, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = graph_to_node_link(G)
    dest.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_graph_json(path: Path) -> nx.Graph:
    data = json.loads(path.read_text(encoding="utf-8"))
    try:
        return json_graph.node_link_graph(data, edges="links")
    except TypeError:
        return json_graph.node_link_graph(data)
