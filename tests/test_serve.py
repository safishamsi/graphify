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
    EXACT_MATCH_BONUS,
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
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))
    G2 = _load_graph(str(p))
    assert G2.number_of_nodes() == G.number_of_nodes()
    assert G2.number_of_edges() == G.number_of_edges()

def test_load_graph_missing_file(tmp_path):
    graphify_dir = tmp_path / "graphify-out"
    graphify_dir.mkdir()
    with pytest.raises(SystemExit):
        _load_graph(str(graphify_dir / "nonexistent.json"))


# --- exact-match bonus + seed-first rendering ---
#
# Single-token identifier queries (e.g. a function name) used to tie at score 1
# against every node containing the substring, then lose tie-breaks during
# _subgraph_to_text rendering, where high-degree hubs (app.js, controller.js)
# always rendered first. The two changes below — EXACT_MATCH_BONUS in
# _score_nodes and the optional `seeds` arg in _subgraph_to_text — fix that.

def _make_hub_graph() -> nx.Graph:
    """Graph with a low-degree exact-match seed and a high-degree hub."""
    G = nx.Graph()
    # Seed: the function we're querying for. Degree 1.
    G.add_node("seed", label="pasteFromClipboard()", source_file="frontend/clipboard.js",
               source_location="L42", community=1)
    # High-degree hub. The substring "pasteFromClipboard" also appears in app.js
    # via call sites, so it scores 1 on a single-token query without the bonus.
    G.add_node("hub", label="app.js", source_file="frontend/app.js",
               source_location="L1", community=1)
    G.add_edge("seed", "hub", relation="defined_in", confidence="EXTRACTED")
    # Distractors that mention the substring but aren't exact matches.
    for i, name in enumerate(["pasteFromClipboard_handler", "wrap_pasteFromClipboard", "_pasteFromClipboard_inner"]):
        nid = f"sub{i}"
        G.add_node(nid, label=name, source_file="frontend/app.js",
                   source_location=f"L{100+i}", community=1)
        G.add_edge("hub", nid, relation="defines", confidence="EXTRACTED")
    # Pad the hub up to degree ~10 so degree-sort would otherwise float it to top.
    for i in range(7):
        nid = f"pad{i}"
        G.add_node(nid, label=f"helper{i}", source_file="frontend/app.js",
                   source_location=f"L{200+i}", community=1)
        G.add_edge("hub", nid, relation="defines", confidence="EXTRACTED")
    return G


def test_score_nodes_exact_match_beats_substring():
    G = _make_hub_graph()
    scored = _score_nodes(G, ["pastefromclipboard"])
    assert scored, "expected at least one scoring node"
    top_score, top_nid = scored[0]
    assert top_nid == "seed", f"exact match should win; got {top_nid}"
    # Bonus should dominate any substring sum.
    assert top_score >= EXACT_MATCH_BONUS
    # The substring-only matches must rank well below the seed.
    sub_scores = [s for s, nid in scored if nid != "seed"]
    assert all(s < EXACT_MATCH_BONUS for s in sub_scores)


def test_score_nodes_exact_match_strips_function_parens():
    """Labels emitted by the AST extractor often carry trailing parens (foo())."""
    G = nx.Graph()
    G.add_node("a", label="saveDiagram()", source_file="x.js", source_location="L1", community=0)
    G.add_node("b", label="saveDiagram_helper", source_file="x.js", source_location="L2", community=0)
    scored = _score_nodes(G, ["savediagram"])
    assert scored[0][1] == "a"
    assert scored[0][0] >= EXACT_MATCH_BONUS


def test_score_nodes_exact_match_no_false_positive():
    """Unrelated query must not trigger the bonus."""
    G = _make_hub_graph()
    scored = _score_nodes(G, ["xyzzy"])
    assert scored == []


def test_subgraph_to_text_seeds_render_first():
    G = _make_hub_graph()
    nodes = {"seed", "hub", "sub0", "sub1", "sub2"} | {f"pad{i}" for i in range(7)}
    edges = list(G.edges())
    text = _subgraph_to_text(G, nodes, edges, token_budget=4000, seeds=["seed"])
    seed_pos = text.index("pasteFromClipboard")
    hub_pos = text.index("app.js")
    assert seed_pos < hub_pos, "seed must render before the high-degree hub"


def test_subgraph_to_text_no_seeds_preserves_legacy_order():
    """Without seeds, ordering still falls back to degree desc (back-compat)."""
    G = _make_hub_graph()
    nodes = {"seed", "hub", "sub0", "sub1", "sub2"} | {f"pad{i}" for i in range(7)}
    edges = list(G.edges())
    legacy = _subgraph_to_text(G, nodes, edges, token_budget=4000)
    explicit_none = _subgraph_to_text(G, nodes, edges, token_budget=4000, seeds=None)
    assert legacy == explicit_none
    # Hub has degree ~11 vs seed degree 1, so without seeds the hub renders first.
    assert legacy.index("app.js") < legacy.index("pasteFromClipboard")


def test_query_pipeline_exact_match_ranks_above_hub():
    """End-to-end: _score_nodes -> _bfs -> _subgraph_to_text(seeds=...)."""
    G = _make_hub_graph()
    terms = ["pastefromclipboard"]
    scored = _score_nodes(G, terms)
    start = [nid for _, nid in scored[:5]]
    assert start[0] == "seed"
    nodes, edges = _bfs(G, start, depth=2)
    text = _subgraph_to_text(G, nodes, edges, token_budget=4000, seeds=start)
    assert text.index("pasteFromClipboard") < text.index("app.js")
