"""Tests for serve.py - MCP graph query helpers (no mcp package required)."""
import json
import pytest
import networkx as nx
from networkx.readwrite import json_graph

from graphify.serve import (
    _communities_from_graph,
    _score_nodes,
    _bfs,
    _dfs,
    _subgraph_to_text,
    _load_graph,
    _find_node,
    _resolve_label,
)


def _make_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("n1", label="extract", source_file="extract.py", source_location="L10", community=0)
    G.add_node("n2", label="cluster", source_file="cluster.py", source_location="L5", community=0)
    G.add_node("n3", label="build", source_file="build.py", source_location="L1", community=1)
    G.add_node("n4", label="report", source_file="report.py", source_location="L1", community=1)
    G.add_node("n5", label="isolated", source_file="other.py", source_location="L1", community=2)
    G.add_edge("n1", "n2", relation="calls", confidence="INFERRED")
    G.add_edge("n2", "n3", relation="imports", confidence="EXTRACTED")
    G.add_edge("n3", "n4", relation="uses", confidence="EXTRACTED")
    return G


# --- _communities_from_graph ---

def test_communities_from_graph_basic():
    G = _make_graph()
    communities = _communities_from_graph(G)
    assert 0 in communities
    assert 1 in communities
    assert "n1" in communities[0]
    assert "n2" in communities[0]
    assert "n3" in communities[1]

def test_communities_from_graph_no_community_attr():
    G = nx.Graph()
    G.add_node("a", label="foo")  # no community attr
    communities = _communities_from_graph(G)
    assert communities == {}

def test_communities_from_graph_isolated():
    G = _make_graph()
    communities = _communities_from_graph(G)
    assert 2 in communities
    assert "n5" in communities[2]


# --- _score_nodes ---

def test_score_nodes_exact_label_match():
    G = _make_graph()
    scored = _score_nodes(G, ["extract"])
    nids = [nid for _, nid in scored]
    assert "n1" in nids
    assert scored[0][1] == "n1"  # highest score first

def test_score_nodes_no_match():
    G = _make_graph()
    scored = _score_nodes(G, ["xyzzy"])
    assert scored == []

def test_score_nodes_source_file_partial():
    G = _make_graph()
    # "cluster.py" contains "cluster" - should score 0.5 for source match
    scored = _score_nodes(G, ["cluster"])
    nids = [nid for _, nid in scored]
    assert "n2" in nids


# --- _bfs ---

def test_bfs_depth_1():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=1)
    assert "n1" in visited
    assert "n2" in visited  # direct neighbor
    assert "n3" not in visited  # 2 hops away

def test_bfs_depth_2():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=2)
    assert "n3" in visited  # n1 -> n2 -> n3

def test_bfs_disconnected():
    G = _make_graph()
    visited, edges = _bfs(G, ["n5"], depth=3)
    assert visited == {"n5"}  # isolated node

def test_bfs_returns_edges():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=1)
    assert len(edges) >= 1
    assert any(u == "n1" or v == "n1" for u, v in edges)


# --- _dfs ---

def test_dfs_depth_1():
    G = _make_graph()
    visited, edges = _dfs(G, ["n1"], depth=1)
    assert "n1" in visited
    assert "n2" in visited
    assert "n3" not in visited

def test_dfs_full_chain():
    G = _make_graph()
    visited, edges = _dfs(G, ["n1"], depth=5)
    assert {"n1", "n2", "n3", "n4"}.issubset(visited)


# --- _subgraph_to_text ---

def test_subgraph_to_text_contains_labels():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, [("n1", "n2")])
    assert "extract" in text
    assert "cluster" in text

def test_subgraph_to_text_truncates():
    G = _make_graph()
    # Very small budget forces truncation
    text = _subgraph_to_text(G, {"n1", "n2", "n3", "n4"}, [("n1", "n2")], token_budget=1)
    assert "truncated" in text

def test_subgraph_to_text_edge_included():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, [("n1", "n2")])
    assert "EDGE" in text
    assert "calls" in text


# --- _load_graph ---

def test_load_graph_roundtrip(tmp_path):
    from unittest.mock import patch
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))
    # validate_graph_path is tested separately; here we test parse correctness
    with patch("graphify.serve.validate_graph_path", return_value=p):
        G2 = _load_graph(str(p))
    assert G2.number_of_nodes() == G.number_of_nodes()
    assert G2.number_of_edges() == G.number_of_edges()

def test_load_graph_missing_file(tmp_path):
    graphify_dir = tmp_path / "graphify-out"
    graphify_dir.mkdir()
    with pytest.raises(SystemExit):
        _load_graph(str(graphify_dir / "nonexistent.json"))


# --- exact-label-match precedence ---

def _make_ambiguous_graph() -> nx.Graph:
    """Graph with a literal 'audit' node alongside several substring matches.

    Models the silent-substring failure mode: querying for 'audit' under the
    pure-substring strategy can promote 'audit_log', 'audit_trail', or even
    'audit()' (a function node) ahead of the literal 'audit' document node.
    """
    G = nx.Graph()
    G.add_node("doc_audit", label="audit", source_file="docs/audit.md", community=0)
    G.add_node("fn_audit", label="audit()", source_file="src/runner.py", community=0)
    G.add_node("doc_log", label="audit_log", source_file="docs/audit_log.md", community=0)
    G.add_node("doc_trail", label="audit_trail", source_file="docs/audit_trail.md", community=0)
    G.add_node("doc_runner", label="audit_runner", source_file="docs/audit_runner.md", community=0)
    G.add_edge("doc_audit", "fn_audit", relation="documents", confidence="EXTRACTED")
    G.add_edge("doc_log", "doc_audit", relation="related", confidence="INFERRED")
    return G


def test_find_node_prefers_exact_match_over_substring():
    """`_find_node('audit')` must return the literal 'audit' node before any
    substring match like 'audit_log' / 'audit()'. Today pure-substring picks
    whichever scan order finds first - silently wrong."""
    G = _make_ambiguous_graph()
    matches = _find_node(G, "audit")
    assert matches, "expected at least one match"
    assert matches[0] == "doc_audit", (
        f"exact match should rank first; got {matches[0]!r} (full list: {matches})"
    )


def test_find_node_falls_back_to_substring_when_no_exact_match():
    """If nothing matches exactly, substring fallback still works."""
    G = _make_ambiguous_graph()
    matches = _find_node(G, "log")
    assert "doc_log" in matches  # 'audit_log' contains 'log'


def test_score_nodes_exact_match_outranks_substring():
    """The literal 'audit' node must score higher than 'audit_log' etc.
    Without an exact-match bonus, substring count alone can tie or invert."""
    G = _make_ambiguous_graph()
    scored = _score_nodes(G, ["audit"])
    assert scored, "expected at least one scored node"
    top_score, top_nid = scored[0]
    assert top_nid == "doc_audit", (
        f"exact-match node should rank first; got {top_nid!r} "
        f"(scored: {scored})"
    )
    # And it should be a strict lead, not a tie.
    if len(scored) > 1:
        assert top_score > scored[1][0], (
            f"exact match should strictly outrank substring; "
            f"top={scored[0]} runner_up={scored[1]}"
        )


def test_score_nodes_exact_match_handles_function_suffix():
    """A label like 'audit()' (function-style) should still register as an
    exact match for the bare query 'audit' once the trailing () is stripped."""
    G = nx.Graph()
    G.add_node("fn", label="audit()", source_file="src/runner.py")
    G.add_node("other", label="audit_log", source_file="docs/audit_log.md")
    scored = _score_nodes(G, ["audit"])
    assert scored[0][1] == "fn", f"expected 'fn' to win on exact match; got {scored}"


def test_resolve_label_returns_label_for_resolved_node():
    """`_resolve_label` is the small helper used by `_tool_shortest_path` to
    echo resolved labels back. It must return the display label for a known
    node ID, falling back to the ID when no label is set."""
    G = _make_ambiguous_graph()
    assert _resolve_label(G, "doc_audit") == "audit"
    G.add_node("unlabeled")  # no label attribute
    assert _resolve_label(G, "unlabeled") == "unlabeled"


# --- _tool_shortest_path resolved-label echo ---
# Exercise the inner function directly: we don't need a live MCP server for
# this. We re-import the closure via a small harness that mirrors serve()'s
# definition order. To keep the test hermetic we redefine the function body
# from the module by extracting it via getattr on a fake server build.
# Simpler: patch serve() to expose its closure for testing.

def test_tool_shortest_path_echoes_resolved_labels(monkeypatch):
    """`shortest_path('audit', 'cluster')` should prefix its output with
    'Resolving ...' lines so callers can see which nodes the substring/exact
    resolver actually picked. Today the resolution is silent, which masked
    a 1-hour audit misdiagnosis (substring coerced 'Repo content audit'
    to the 'audit()' function node)."""
    from graphify.serve import _build_shortest_path_handler

    G = _make_ambiguous_graph()
    # Link doc_audit to a 'cluster' node so a path exists.
    G.add_node("doc_cluster", label="cluster", source_file="docs/cluster.md")
    G.add_edge("doc_audit", "doc_cluster", relation="links", confidence="EXTRACTED")

    handler = _build_shortest_path_handler(G)
    out = handler({"source": "audit", "target": "cluster"})

    assert "Resolving 'audit'" in out, (
        f"missing source resolution echo in output:\n{out}"
    )
    assert "Resolving 'cluster'" in out, (
        f"missing target resolution echo in output:\n{out}"
    )
    assert "-> node 'audit'" in out, (
        f"source should resolve to literal 'audit' node, not a substring; "
        f"output:\n{out}"
    )
    assert "-> node 'cluster'" in out, (
        f"target should resolve to literal 'cluster' node; output:\n{out}"
    )
    # The original path summary line must still be present.
    assert "Shortest path" in out, f"missing path summary; output:\n{out}"
