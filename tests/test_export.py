import json
import os
import tempfile
import pytest
from pathlib import Path
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import (
    to_json,
    to_cypher,
    to_graphml,
    to_html,
    to_canvas,
    _viz_node_limit,
    MAX_NODES_FOR_VIZ,
)

FIXTURES = Path(__file__).parent / "fixtures"

def make_graph():
    return build_from_json(json.loads((FIXTURES / "extraction.json").read_text()))

def test_to_json_creates_file():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, communities, str(out))
        assert out.exists()

def test_to_json_valid_json():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, communities, str(out))
        data = json.loads(out.read_text())
        assert "nodes" in data
        assert "links" in data

def test_to_json_nodes_have_community():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, communities, str(out))
        data = json.loads(out.read_text())
        for node in data["nodes"]:
            assert "community" in node

def test_to_cypher_creates_file():
    G = make_graph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "cypher.txt"
        to_cypher(G, str(out))
        assert out.exists()

def test_to_cypher_contains_merge_statements():
    G = make_graph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "cypher.txt"
        to_cypher(G, str(out))
        content = out.read_text()
        assert "MERGE" in content

def test_to_graphml_creates_file():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.graphml"
        to_graphml(G, communities, str(out))
        assert out.exists()

def test_to_graphml_valid_xml():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.graphml"
        to_graphml(G, communities, str(out))
        content = out.read_text()
        assert "<graphml" in content
        assert "<node" in content

def test_to_graphml_has_community_attribute():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.graphml"
        to_graphml(G, communities, str(out))
        content = out.read_text()
        assert "community" in content

def test_to_html_creates_file():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        assert out.exists()

def test_to_html_contains_visjs():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        content = out.read_text()
        assert "vis-network" in content

def test_to_html_contains_search():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        content = out.read_text()
        assert "search" in content.lower()

def test_to_html_contains_legend_with_labels():
    G = make_graph()
    communities = cluster(G)
    labels = {cid: f"Group {cid}" for cid in communities}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out), community_labels=labels)
        content = out.read_text()
        assert "Group 0" in content

def test_to_html_contains_nodes_and_edges():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        content = out.read_text()
        assert "RAW_NODES" in content
        assert "RAW_EDGES" in content


# --- GRAPHIFY_VIZ_NODE_LIMIT env var --------------------------------------------

@pytest.fixture
def restore_viz_env(monkeypatch):
    """Ensure each test runs without GRAPHIFY_VIZ_NODE_LIMIT bleeding across cases."""
    monkeypatch.delenv("GRAPHIFY_VIZ_NODE_LIMIT", raising=False)
    yield


def test_viz_node_limit_default(restore_viz_env):
    assert _viz_node_limit() == MAX_NODES_FOR_VIZ


def test_viz_node_limit_env_override_higher(restore_viz_env, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "20000")
    assert _viz_node_limit() == 20000


def test_viz_node_limit_env_override_zero_disables(restore_viz_env, monkeypatch):
    """Setting to 0 lets users disable HTML viz unconditionally (CI runners)."""
    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "0")
    assert _viz_node_limit() == 0


def test_viz_node_limit_invalid_falls_back_to_default(restore_viz_env, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "not-an-int")
    assert _viz_node_limit() == MAX_NODES_FOR_VIZ


def test_viz_node_limit_empty_falls_back_to_default(restore_viz_env, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "  ")
    assert _viz_node_limit() == MAX_NODES_FOR_VIZ


def test_to_html_raises_with_lowered_limit(restore_viz_env, monkeypatch):
    """Lowering the limit below the test graph's size triggers ValueError."""
    G = make_graph()
    communities = cluster(G)
    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "1")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        with pytest.raises(ValueError, match="too large for HTML viz"):
            to_html(G, communities, str(out))


def test_to_html_writes_with_raised_limit(restore_viz_env, monkeypatch):
    """Raising the limit above the graph's size lets to_html proceed normally."""
    G = make_graph()
    communities = cluster(G)
    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "100000")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        assert out.exists()


def test_to_html_member_counts_accepted():
    """to_html accepts member_counts without raising."""
    G = make_graph()
    communities = cluster(G)
    member_counts = {cid: len(members) for cid, members in communities.items()}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out), member_counts=member_counts)
        assert out.exists()


def test_to_canvas_file_paths_relative_to_vault():
    """Node file paths in canvas must be vault-root-relative (just fname.md), not hardcoded."""
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.canvas"
        to_canvas(G, communities, str(out))
        data = json.loads(out.read_text())
        file_nodes = [n for n in data["nodes"] if n.get("type") == "file"]
        assert file_nodes, "canvas should contain file nodes"
        for node in file_nodes:
            assert "/" not in node["file"], f"file path should not contain '/': {node['file']}"
            assert node["file"].endswith(".md")
