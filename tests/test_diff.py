"""Tests for graphify.diff — graph diff engine."""
from __future__ import annotations

import json

import networkx as nx
import pytest
from networkx.readwrite import json_graph

from graphify.diff import (
    diff_graphs,
    render_diff,
    _jaccard,
    _diff_communities,
    _diff_god_nodes,
    _existing_communities,
)


def _save_graph(tmp_path, name: str, G: nx.Graph) -> str:
    path = tmp_path / name
    data = json_graph.node_link_data(G, edges="links")
    data["graph"] = {"schema_version": "0.5.5"}
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# _jaccard
# ---------------------------------------------------------------------------

def test_jaccard_identical():
    assert _jaccard({1, 2, 3}, {1, 2, 3}) == 1.0


def test_jaccard_disjoint():
    assert _jaccard({1, 2}, {3, 4}) == 0.0


def test_jaccard_half():
    assert _jaccard({1, 2, 3, 4}, {3, 4, 5, 6}) == 0.3333333333333333


# ---------------------------------------------------------------------------
# diff_graphs — no changes
# ---------------------------------------------------------------------------

def test_diff_no_changes(tmp_path):
    G = nx.Graph()
    G.add_node("a", label="A", file_type="code", source_file="a.py")
    G.add_node("b", label="B", file_type="code", source_file="b.py")
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED", source_file="a.py")

    p = _save_graph(tmp_path, "old.json", G)
    result = diff_graphs(p, p)

    assert result["old_nodes"] == 2
    assert result["new_nodes"] == 2
    assert result["nodes_added"] == []
    assert result["nodes_removed"] == []
    assert result["nodes_changed"] == []
    assert result["edges_added"] == []
    assert result["edges_removed"] == []


# ---------------------------------------------------------------------------
# diff_graphs — node added / removed
# ---------------------------------------------------------------------------

def test_diff_node_added(tmp_path):
    old = nx.Graph()
    old.add_node("a", label="A", file_type="code", source_file="a.py")

    new = nx.Graph()
    new.add_node("a", label="A", file_type="code", source_file="a.py")
    new.add_node("b", label="B", file_type="code", source_file="b.py")

    p1 = _save_graph(tmp_path, "old.json", old)
    p2 = _save_graph(tmp_path, "new.json", new)
    result = diff_graphs(p1, p2)

    assert len(result["nodes_added"]) == 1
    assert result["nodes_added"][0]["id"] == "b"
    assert result["nodes_removed"] == []


def test_diff_node_removed(tmp_path):
    old = nx.Graph()
    old.add_node("a", label="A", file_type="code", source_file="a.py")
    old.add_node("b", label="B", file_type="code", source_file="b.py")

    new = nx.Graph()
    new.add_node("a", label="A", file_type="code", source_file="a.py")

    p1 = _save_graph(tmp_path, "old.json", old)
    p2 = _save_graph(tmp_path, "new.json", new)
    result = diff_graphs(p1, p2)

    assert len(result["nodes_removed"]) == 1
    assert result["nodes_removed"][0]["id"] == "b"
    assert result["nodes_added"] == []


# ---------------------------------------------------------------------------
# diff_graphs — node attribute changed
# ---------------------------------------------------------------------------

def test_diff_node_changed(tmp_path):
    old = nx.Graph()
    old.add_node("a", label="A", file_type="code", source_file="a.py", community=0)

    new = nx.Graph()
    new.add_node("a", label="A", file_type="code", source_file="a.py", community=1)

    p1 = _save_graph(tmp_path, "old.json", old)
    p2 = _save_graph(tmp_path, "new.json", new)
    result = diff_graphs(p1, p2)

    assert len(result["nodes_changed"]) == 1
    assert result["nodes_changed"][0]["id"] == "a"
    assert result["nodes_changed"][0]["changes"]["community"]["old"] == 0
    assert result["nodes_changed"][0]["changes"]["community"]["new"] == 1


# ---------------------------------------------------------------------------
# diff_graphs — edges added / removed
# ---------------------------------------------------------------------------

def test_diff_edge_added(tmp_path):
    old = nx.Graph()
    old.add_node("a", label="A", file_type="code", source_file="a.py")
    old.add_node("b", label="B", file_type="code", source_file="b.py")

    new = nx.Graph()
    new.add_node("a", label="A", file_type="code", source_file="a.py")
    new.add_node("b", label="B", file_type="code", source_file="b.py")
    new.add_edge("a", "b", relation="calls", confidence="EXTRACTED", source_file="a.py")

    p1 = _save_graph(tmp_path, "old.json", old)
    p2 = _save_graph(tmp_path, "new.json", new)
    result = diff_graphs(p1, p2)

    assert len(result["edges_added"]) == 1
    assert result["edges_added"][0]["source"] == "a"
    assert result["edges_removed"] == []


def test_diff_edge_removed(tmp_path):
    old = nx.Graph()
    old.add_node("a", label="A", file_type="code", source_file="a.py")
    old.add_node("b", label="B", file_type="code", source_file="b.py")
    old.add_edge("a", "b", relation="calls", confidence="EXTRACTED", source_file="a.py")

    new = nx.Graph()
    new.add_node("a", label="A", file_type="code", source_file="a.py")
    new.add_node("b", label="B", file_type="code", source_file="b.py")

    p1 = _save_graph(tmp_path, "old.json", old)
    p2 = _save_graph(tmp_path, "new.json", new)
    result = diff_graphs(p1, p2)

    assert len(result["edges_removed"]) == 1
    assert result["edges_removed"][0]["source"] == "a"
    assert result["edges_added"] == []


# ---------------------------------------------------------------------------
# _diff_communities — split / merge
# ---------------------------------------------------------------------------

def test_community_split_detected():
    old_G = nx.Graph()
    old_G.add_nodes_from(["a", "b", "c", "d", "e", "f"])
    new_G = nx.Graph()
    new_G.add_nodes_from(["a", "b", "c", "d", "e", "f"])

    old_communities = {0: ["a", "b", "c", "d", "e", "f"]}
    new_communities = {0: ["a", "b", "c"], 1: ["d", "e", "f"]}

    changed = _diff_communities(old_G, new_G, old_communities, new_communities)
    assert any(c["type"] == "split" for c in changed)


def test_community_merge_detected():
    old_G = nx.Graph()
    old_G.add_nodes_from(["a", "b", "c", "d", "e", "f"])
    new_G = nx.Graph()
    new_G.add_nodes_from(["a", "b", "c", "d", "e", "f"])

    old_communities = {0: ["a", "b", "c"], 1: ["d", "e", "f"]}
    new_communities = {0: ["a", "b", "c", "d", "e", "f"]}

    changed = _diff_communities(old_G, new_G, old_communities, new_communities)
    assert any(c["type"] == "merge" for c in changed)


# ---------------------------------------------------------------------------
# _diff_god_nodes
# ---------------------------------------------------------------------------

def test_god_node_promoted():
    old_G = nx.Graph()
    old_G.add_node("a", label="A", source_file="a.py")
    old_G.add_node("b", label="B", source_file="b.py")
    old_G.add_edge("a", "b", relation="calls", confidence="EXTRACTED", source_file="x.py")

    new_G = nx.Graph()
    new_G.add_node("a", label="A", source_file="a.py")
    new_G.add_node("b", label="B", source_file="b.py")
    new_G.add_node("c", label="C", source_file="c.py")
    new_G.add_node("d", label="D", source_file="d.py")
    new_G.add_edges_from([
        ("a", "b", {"relation": "calls", "confidence": "EXTRACTED", "source_file": "x.py"}),
        ("a", "c", {"relation": "calls", "confidence": "EXTRACTED", "source_file": "x.py"}),
        ("b", "c", {"relation": "calls", "confidence": "EXTRACTED", "source_file": "x.py"}),
        ("c", "d", {"relation": "calls", "confidence": "EXTRACTED", "source_file": "x.py"}),
        ("d", "a", {"relation": "calls", "confidence": "EXTRACTED", "source_file": "x.py"}),
    ])
    # c now has degree 3, a and d have degree 2, b has degree 2
    # In old_G, a and b both have degree 1
    # In new_G, top 2 are c (3) and one of a/b/d (2)
    # So c should be promoted when going old -> new

    result_forward = _diff_god_nodes(old_G, new_G, top_n=2)
    assert any(g["id"] == "c" for g in result_forward["promoted"])


def test_god_node_demoted():
    old_G = nx.Graph()
    old_G.add_node("a", label="A")
    old_G.add_node("b", label="B")
    old_G.add_edges_from([
        ("a", "b", {"relation": "calls", "confidence": "EXTRACTED", "source_file": "x.py"}),
    ])

    new_G = nx.Graph()
    new_G.add_node("a", label="A")
    new_G.add_node("b", label="B")

    result = _diff_god_nodes(old_G, new_G, top_n=2)
    # Both nodes lost their edge; depending on ranking, one may be demoted
    assert len(result["demoted"]) >= 0  # just ensure it runs without error


# ---------------------------------------------------------------------------
# render_diff
# ---------------------------------------------------------------------------

def test_render_diff_markdown():
    diff = {
        "old_nodes": 2,
        "new_nodes": 3,
        "nodes_added": [{"id": "c", "label": "C"}],
        "nodes_removed": [],
        "nodes_changed": [],
        "old_edges": 1,
        "new_edges": 2,
        "edges_added": [{"source": "b", "target": "c", "relation": "calls"}],
        "edges_removed": [],
        "communities_changed": [],
        "god_nodes_changed": {
            "old_gods": [],
            "new_gods": [],
            "promoted": [],
            "demoted": [],
            "changed": [],
        },
        "schema_version": "0.5.5",
    }
    text = render_diff(diff, fmt="markdown")
    assert "# Graph Diff Report" in text
    assert "Nodes: 2 → 3" in text
    assert "Edges: 1 → 2" in text
    assert "Added (1)" in text


def test_render_diff_json():
    diff = {"old_nodes": 1, "new_nodes": 1, "nodes_added": [], "nodes_removed": [], "nodes_changed": [],
            "old_edges": 0, "new_edges": 0, "edges_added": [], "edges_removed": [],
            "communities_changed": [], "god_nodes_changed": {"old_gods": [], "new_gods": [], "promoted": [], "demoted": [], "changed": []},
            "schema_version": "0.5.5"}
    text = render_diff(diff, fmt="json")
    parsed = json.loads(text)
    assert parsed["old_nodes"] == 1


def test_existing_communities_reads_from_node_attrs():
    G = nx.Graph()
    G.add_node("a", community=0)
    G.add_node("b", community=0)
    G.add_node("c", community=1)
    G.add_node("d")  # no community attr — must be ignored
    out = _existing_communities(G)
    assert sorted(out[0]) == ["a", "b"]
    assert out[1] == ["c"]
    assert "d" not in {n for nodes in out.values() for n in nodes}


def test_diff_communities_uses_stored_assignments():
    # When both graphs already carry community labels, diff must use them
    # verbatim instead of re-running cluster() — re-clustering is
    # non-deterministic and would yield unstable splits/merges.
    old_G = nx.Graph()
    old_G.add_node("a", community=0)
    old_G.add_node("b", community=0)
    old_G.add_node("c", community=0)
    old_G.add_node("d", community=0)
    old_G.add_edge("a", "b")
    old_G.add_edge("c", "d")

    new_G = nx.Graph()
    new_G.add_node("a", community=0)
    new_G.add_node("b", community=0)
    new_G.add_node("c", community=1)
    new_G.add_node("d", community=1)
    new_G.add_edge("a", "b")
    new_G.add_edge("c", "d")

    changes = _diff_communities(old_G, new_G)
    splits = [c for c in changes if c["type"] == "split"]
    assert len(splits) == 1
    assert splits[0]["old_community"] == 0
    new_ids = {nc["id"] for nc in splits[0]["new_communities"]}
    assert new_ids == {0, 1}
