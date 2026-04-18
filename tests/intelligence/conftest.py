"""Shared fixtures for intelligence-layer tests.

Builds ``nx.DiGraph`` objects from committed node-link JSON fixtures so
acceptance tests never re-run graphify extraction and CI does not need a
live repo graph.
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_node_link(path: Path) -> nx.DiGraph:
    data = json.loads(path.read_text(encoding="utf-8"))
    g = nx.DiGraph()
    for node in data.get("nodes", []):
        nid = node["id"]
        g.add_node(nid, **{k: v for k, v in node.items() if k != "id"})
    for edge in data.get("links", data.get("edges", [])):
        g.add_edge(edge["source"], edge["target"], **{k: v for k, v in edge.items() if k not in ("source", "target")})
    return g


@pytest.fixture
def load_fixture_graph():
    """Return a loader that takes a fixture filename and yields a DiGraph."""

    def _load(name: str) -> nx.DiGraph:
        path = FIXTURE_DIR / name
        if not path.exists():
            pytest.skip(f"fixture missing: {path}")
        return _load_node_link(path)

    return _load
