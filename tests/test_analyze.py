"""Tests for analyze.py."""
import json
import networkx as nx
from pathlib import Path
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.analyze import god_nodes, surprising_connections, _is_concept_node, graph_diff, _surprise_score, _file_category
from graphify.analyze import _cross_language, _is_file_node, _cross_file_surprises, _cross_community_surprises, suggest_questions

FIXTURES = Path(__file__).parent / "fixtures"


def make_graph():
    return build_from_json(json.loads((FIXTURES / "extraction.json").read_text()))


def test_god_nodes_returns_list():
    G = make_graph()
    result = god_nodes(G, top_n=3)
    assert isinstance(result, list)
    assert len(result) <= 3


def test_god_nodes_sorted_by_degree():
    G = make_graph()
    result = god_nodes(G, top_n=10)
    degrees = [r["degree"] for r in result]
    assert degrees == sorted(degrees, reverse=True)


def test_god_nodes_have_required_keys():
    G = make_graph()
    result = god_nodes(G, top_n=1)
    assert "id" in result[0]
    assert "label" in result[0]
    assert "degree" in result[0]


def test_surprising_connections_cross_source_multi_file():
    """Multi-file graph: should find cross-file edges between real entities."""
    G = make_graph()
    communities = cluster(G)
    surprises = surprising_connections(G, communities)
    assert len(surprises) > 0
    for s in surprises:
        assert s["source_files"][0] != s["source_files"][1]


def test_surprising_connections_excludes_concept_nodes():
    """Concept nodes (empty source_file) must not appear in surprises."""
    G = make_graph()
    # Add a concept node with empty source_file
    G.add_node("concept_x", label="Abstract Concept", file_type="document", source_file="")
    G.add_edge("n_transformer", "concept_x", relation="relates_to",
               confidence="INFERRED", source_file="", weight=0.5)
    communities = cluster(G)
    surprises = surprising_connections(G, communities)
    labels = [s["source"] for s in surprises] + [s["target"] for s in surprises]
    assert "Abstract Concept" not in labels


def test_surprising_connections_single_file_uses_community_bridges():
    """Single-file graph: should return cross-community edges, not empty list."""
    G = nx.Graph()
    # Build a graph with 2 clear communities + 1 bridge edge
    for i in range(5):
        G.add_node(f"a{i}", label=f"A{i}", file_type="code", source_file="single.py",
                   source_location=f"L{i}")
    for i in range(5):
        G.add_node(f"b{i}", label=f"B{i}", file_type="code", source_file="single.py",
                   source_location=f"L{i+10}")
    # Dense intra-community edges
    for i in range(4):
        G.add_edge(f"a{i}", f"a{i+1}", relation="calls", confidence="EXTRACTED",
                   source_file="single.py", weight=1.0)
    for i in range(4):
        G.add_edge(f"b{i}", f"b{i+1}", relation="calls", confidence="EXTRACTED",
                   source_file="single.py", weight=1.0)
    # One cross-community bridge
    G.add_edge("a4", "b0", relation="references", confidence="INFERRED",
               source_file="single.py", weight=0.5)

    communities = cluster(G)
    surprises = surprising_connections(G, communities)
    # Should find at least the bridge edge
    assert len(surprises) > 0


def test_surprising_connections_ambiguous_scores_higher_than_extracted():
    """AMBIGUOUS edge should score higher than an otherwise identical EXTRACTED edge."""
    G = nx.Graph()
    for nid, label, src in [
        ("a", "Alpha", "repo1/model.py"),
        ("b", "Beta", "repo2/train.py"),
        ("c", "Gamma", "repo1/data.py"),
        ("d", "Delta", "repo2/eval.py"),
    ]:
        G.add_node(nid, label=label, source_file=src, file_type="code")
    G.add_edge("a", "b", relation="calls", confidence="AMBIGUOUS", weight=1.0, source_file="repo1/model.py")
    G.add_edge("c", "d", relation="calls", confidence="EXTRACTED", weight=1.0, source_file="repo1/data.py")
    communities = {0: ["a", "c"], 1: ["b", "d"]}
    nc = {"a": 0, "c": 0, "b": 1, "d": 1}
    score_amb, _ = _surprise_score(G, "a", "b", G.edges["a", "b"], nc, "repo1/model.py", "repo2/train.py")
    score_ext, _ = _surprise_score(G, "c", "d", G.edges["c", "d"], nc, "repo1/data.py", "repo2/eval.py")
    assert score_amb > score_ext


def test_surprising_connections_cross_type_scores_higher():
    """Code↔paper edge should score higher than code↔code edge."""
    G = nx.Graph()
    for nid, label, src in [
        ("a", "Transformer", "code/model.py"),
        ("b", "FlashAttn", "papers/flash.pdf"),
        ("c", "Trainer", "code/train.py"),
        ("d", "Dataset", "code/data.py"),
    ]:
        G.add_node(nid, label=label, source_file=src, file_type="code")
    G.add_edge("a", "b", relation="references", confidence="EXTRACTED", weight=1.0, source_file="code/model.py")
    G.add_edge("c", "d", relation="calls", confidence="EXTRACTED", weight=1.0, source_file="code/train.py")
    nc = {"a": 0, "b": 1, "c": 0, "d": 0}
    score_cross, reasons_cross = _surprise_score(G, "a", "b", G.edges["a", "b"], nc, "code/model.py", "papers/flash.pdf")
    score_same, _ = _surprise_score(G, "c", "d", G.edges["c", "d"], nc, "code/train.py", "code/data.py")
    assert score_cross > score_same
    assert any("code" in r and "paper" in r for r in reasons_cross)


def test_surprising_connections_have_why_field():
    G = make_graph()
    communities = cluster(G)
    for s in surprising_connections(G, communities):
        assert "why" in s
        assert isinstance(s["why"], str)
        assert len(s["why"]) > 0


def test_file_category():
    assert _file_category("model.py") == "code"
    assert _file_category("flash.pdf") == "paper"
    assert _file_category("diagram.png") == "image"
    assert _file_category("notes.md") == "doc"
    # Languages added in later releases — would misclassify as "doc" without detect.py import
    assert _file_category("app.swift") == "code"
    assert _file_category("plugin.lua") == "code"
    assert _file_category("build.zig") == "code"
    assert _file_category("deploy.ps1") == "code"
    assert _file_category("server.ex") == "code"
    assert _file_category("component.jsx") == "code"
    assert _file_category("analysis.jl") == "code"
    assert _file_category("view.m") == "code"


def test_is_concept_node_empty_source():
    G = nx.Graph()
    G.add_node("c1", source_file="")
    assert _is_concept_node(G, "c1") is True


def test_is_concept_node_real_file():
    G = nx.Graph()
    G.add_node("n1", source_file="model.py")
    assert _is_concept_node(G, "n1") is False


def test_surprising_connections_have_required_keys():
    G = make_graph()
    communities = cluster(G)
    for s in surprising_connections(G, communities):
        assert "source" in s
        assert "target" in s
        assert "source_files" in s
        assert "confidence" in s


# --- graph_diff tests ---

def _make_simple_graph(nodes, edges):
    """Helper: build a small nx.Graph from node/edge specs."""
    G = nx.Graph()
    for node_id, label in nodes:
        G.add_node(node_id, label=label, source_file="test.py")
    for src, tgt, rel, conf in edges:
        G.add_edge(src, tgt, relation=rel, confidence=conf)
    return G


def test_graph_diff_new_nodes():
    G_old = _make_simple_graph([("n1", "Alpha"), ("n2", "Beta")], [])
    G_new = _make_simple_graph([("n1", "Alpha"), ("n2", "Beta"), ("n3", "Gamma")], [])
    diff = graph_diff(G_old, G_new)
    assert len(diff["new_nodes"]) == 1
    assert diff["new_nodes"][0]["id"] == "n3"
    assert diff["new_nodes"][0]["label"] == "Gamma"
    assert diff["removed_nodes"] == []
    assert "1 new node" in diff["summary"]


def test_graph_diff_removed_nodes():
    G_old = _make_simple_graph([("n1", "Alpha"), ("n2", "Beta"), ("n3", "Gamma")], [])
    G_new = _make_simple_graph([("n1", "Alpha"), ("n2", "Beta")], [])
    diff = graph_diff(G_old, G_new)
    assert diff["new_nodes"] == []
    assert len(diff["removed_nodes"]) == 1
    assert diff["removed_nodes"][0]["id"] == "n3"
    assert "removed" in diff["summary"]


def test_graph_diff_new_edges():
    nodes = [("n1", "Alpha"), ("n2", "Beta"), ("n3", "Gamma")]
    G_old = _make_simple_graph(nodes, [("n1", "n2", "calls", "EXTRACTED")])
    G_new = _make_simple_graph(
        nodes,
        [("n1", "n2", "calls", "EXTRACTED"), ("n2", "n3", "uses", "INFERRED")],
    )
    diff = graph_diff(G_old, G_new)
    assert len(diff["new_edges"]) == 1
    new_edge = diff["new_edges"][0]
    assert new_edge["relation"] == "uses"
    assert new_edge["confidence"] == "INFERRED"
    assert diff["removed_edges"] == []
    assert "new edge" in diff["summary"]


def test_graph_diff_empty_diff():
    nodes = [("n1", "Alpha"), ("n2", "Beta")]
    edges = [("n1", "n2", "calls", "EXTRACTED")]
    G_old = _make_simple_graph(nodes, edges)
    G_new = _make_simple_graph(nodes, edges)
    diff = graph_diff(G_old, G_new)
    assert diff["new_nodes"] == []
    assert diff["removed_nodes"] == []
    assert diff["new_edges"] == []
    assert diff["removed_edges"] == []
    assert diff["summary"] == "no changes"


# ---------------------------------------------------------------------------
# _cross_language (lines 24-30)
# ---------------------------------------------------------------------------

def test_cross_language_same_family():
    """Two Python files should return False (same family)."""
    assert _cross_language("a.py", "b.py") is False


def test_cross_language_different_family():
    """Python vs JavaScript should return True (different family)."""
    assert _cross_language("a.py", "b.js") is True


def test_cross_language_unknown_extension():
    """Unknown extension should return False (conservative)."""
    assert _cross_language("a.xyz", "b.py") is False


def test_cross_language_both_unknown():
    """Both unknown extensions should return False."""
    assert _cross_language("a.xyz", "b.abc") is False


# ---------------------------------------------------------------------------
# _is_file_node — empty label (line 49)
# ---------------------------------------------------------------------------

def test_is_file_node_empty_label():
    """Node with empty label is not a file node."""
    G = nx.Graph()
    G.add_node("n1", label="")
    assert _is_file_node(G, "n1") is False


def test_is_file_node_no_label_key():
    """Node without 'label' key is not a file node."""
    G = nx.Graph()
    G.add_node("n1")
    assert _is_file_node(G, "n1") is False


# ---------------------------------------------------------------------------
# _is_concept_node — no extension in filename (line 135)
# ---------------------------------------------------------------------------

def test_is_concept_node_no_extension():
    """source_file without extension is a concept node."""
    G = nx.Graph()
    G.add_node("c1", source_file="some_concept")
    assert _is_concept_node(G, "c1") is True


# ---------------------------------------------------------------------------
# _surprise_score — cross-language INFERRED calls downgrade (line 178)
# ---------------------------------------------------------------------------

def test_surprise_score_cross_lang_inferred_calls_downgraded():
    """Cross-language INFERRED calls get a 0 conf_bonus."""
    G = nx.Graph()
    G.add_node("a", source_file="model.py", label="A")
    G.add_node("b", source_file="lib.rs", label="B")
    G.add_edge("a", "b", relation="calls", confidence="INFERRED", weight=1.0)
    nc = {"a": 0, "b": 1}
    score, reasons = _surprise_score(G, "a", "b", G.edges["a", "b"], nc,
                                     "model.py", "lib.rs")
    # Without downgrade: conf_bonus=2 + cross_repo=2 + cross_community=1 = 5
    # With downgrade: conf_bonus=0 + cross_repo=2 + cross_community=1 = 3
    assert score == 3  # downgrade applied
    assert "inferred connection" in reasons[0]


# ---------------------------------------------------------------------------
# _cross_file_surprises — src_id/tgt_id not in G (lines 255, 258)
# ---------------------------------------------------------------------------

def test_cross_file_surprises_src_tgt_not_in_graph():
    """Edges with _src/_tgt attributes pointing to missing nodes still work."""
    G = nx.Graph()
    G.add_node("a", label="Alpha", source_file="repo1/model.py", file_type="code")
    G.add_node("b", label="Beta", source_file="repo2/train.py", file_type="code")
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED",
               weight=1.0, source_file="repo1/model.py",
               _src="nonexistent_src", _tgt="nonexistent_tgt")
    communities = {0: ["a"], 1: ["b"]}
    result = _cross_file_surprises(G, communities, top_n=5)
    # Should fall back to u/v and return a result
    assert len(result) >= 1
    assert result[0]["source"] == "Alpha"
    assert result[0]["target"] == "Beta"


def test_cross_file_surprises_fallback_to_cross_community():
    """No cross-file candidates falls back to _cross_community_surprises."""
    G = nx.Graph()
    # Single-source-file graph: no cross-file candidates
    G.add_node("a", label="A", source_file="single.py", file_type="code")
    G.add_node("b", label="B", source_file="single.py", file_type="code")
    G.add_edge("a", "b", relation="references", confidence="EXTRACTED",
               weight=1.0, source_file="single.py")
    communities = cluster(G)
    result = _cross_file_surprises(G, communities, top_n=5)
    # Should return cross-community surprises (or empty list if no communities)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# surprising_connections — without communities (edge betweenness, lines 296-316)
# ---------------------------------------------------------------------------

def test_surprising_connections_no_communities_small_graph():
    """Without communities, falls back to edge betweenness centrality."""
    G = nx.Graph()
    for i in range(10):
        G.add_node(f"n{i}", label=f"Node {i}", source_file="multi", file_type="code")
    # Build a bridge pattern
    for i in range(4):
        G.add_edge(f"n{i}", f"n{i+1}", relation="calls", confidence="EXTRACTED",
                   weight=1.0, source_file="multi")
    for i in range(5, 9):
        G.add_edge(f"n{i}", f"n{i+1}", relation="calls", confidence="EXTRACTED",
                   weight=1.0, source_file="multi")
    G.add_edge("n4", "n5", relation="references", confidence="INFERRED",
               weight=0.5, source_file="multi")
    result = surprising_connections(G, communities=None, top_n=3)
    assert isinstance(result, list)


def test_surprising_connections_no_communities_empty():
    """Without communities and no edges, returns empty list."""
    G = nx.Graph()
    G.add_node("a", label="A", source_file="single.py", file_type="code")
    G.add_node("b", label="B", source_file="single.py", file_type="code")
    result = surprising_connections(G, communities=None)
    assert result == []


def test_surprising_connections_no_communities_large_graph():
    """Without communities and >5000 nodes, returns empty list."""
    G = nx.Graph()
    # Add 5001 nodes without building the actual graph to avoid perf hit
    for i in range(5001):
        G.add_node(f"n{i}", label=f"Node{i}", source_file="big", file_type="code")
    # Just needs one edge to pass the first check
    G.add_edge("n0", "n1", relation="calls", confidence="EXTRACTED",
               weight=1.0, source_file="big")
    result = surprising_connections(G, communities=None)
    assert result == []


# ---------------------------------------------------------------------------
# _cross_community_surprises — file node skip, relation skip (lines 329, 332)
# ---------------------------------------------------------------------------

def test_cross_community_surprises_skips_file_nodes():
    """File-level hub nodes are skipped in cross-community surprises."""
    G = nx.Graph()
    G.add_node("f1", label="stuff", source_file="stuff.py", file_type="code")
    G.add_node("n2", label="Func", source_file="stuff.py", file_type="code")
    G.add_node("n3", label="Other", source_file="stuff.py", file_type="code")
    G.add_edge("f1", "n2", relation="contains", confidence="EXTRACTED",
               weight=1.0, source_file="stuff.py")
    G.add_edge("f1", "n3", relation="contains", confidence="EXTRACTED",
               weight=1.0, source_file="stuff.py")
    # f1 is a file node (label matches filename), n2 and n3 are not
    communities = {0: ["f1", "n2"], 1: ["n3"]}
    result = _cross_community_surprises(G, communities, top_n=5)
    # f1 should be skipped; no cross-community edges remain without imports/contains
    assert len(result) == 0


def test_cross_community_surprises_skips_imports_contains():
    """Relations like imports, imports_from, contains, method are skipped."""
    G = nx.Graph()
    G.add_node("n1", label="Func1", source_file="lib.py", file_type="code")
    G.add_node("n2", label="Func2", source_file="lib.py", file_type="code")
    G.add_edge("n1", "n2", relation="imports", confidence="EXTRACTED",
               weight=1.0, source_file="lib.py")
    communities = {0: ["n1"], 1: ["n2"]}
    result = _cross_community_surprises(G, communities, top_n=5)
    assert len(result) == 0


# ---------------------------------------------------------------------------
# suggest_questions — ambiguous edges (lines 387-390)
# ---------------------------------------------------------------------------

def test_suggest_questions_ambiguous_edges():
    """AMBIGUOUS edges generate verification questions."""
    G = nx.Graph()
    G.add_node("a", label="Encoder", source_file="model.py", file_type="code")
    G.add_node("b", label="Decoder", source_file="model.py", file_type="code")
    G.add_edge("a", "b", relation="relates_to", confidence="AMBIGUOUS",
               weight=0.3, source_file="model.py")
    communities = cluster(G)
    community_labels = {cid: f"Community {cid}" for cid in communities}
    result = suggest_questions(G, communities, community_labels)
    ambiguous = [q for q in result if q["type"] == "ambiguous_edge"]
    assert len(ambiguous) >= 1
    assert "Encoder" in ambiguous[0]["question"]
    assert "Decoder" in ambiguous[0]["question"]


# ---------------------------------------------------------------------------
# suggest_questions — inferred edges with src/tgt (lines 434-446)
# ---------------------------------------------------------------------------

def test_suggest_questions_inferred_edges():
    """God nodes with multiple INFERRED edges generate verification questions."""
    G = nx.Graph()
    G.add_node("hub", label="HubNode", source_file="core.py", file_type="code")
    for i in range(5):
        G.add_node(f"n{i}", label=f"Node{i}", source_file="core.py", file_type="code")
        G.add_edge("hub", f"n{i}", relation="uses", confidence="INFERRED",
                   weight=0.5, source_file="core.py")
    communities = cluster(G)
    community_labels = {cid: f"Community {cid}" for cid in communities}
    result = suggest_questions(G, communities, community_labels)
    verify = [q for q in result if q["type"] == "verify_inferred"]
    assert len(verify) >= 1
    assert "HubNode" in verify[0]["question"]


# ---------------------------------------------------------------------------
# suggest_questions — no signal fallback (line 478)
# ---------------------------------------------------------------------------

def test_suggest_questions_no_signal():
    """When there are no interesting patterns, returns no_signal fallback."""
    G = nx.Graph()
    # Need a small clique where all nodes have degree >= 2,
    # all edges are EXTRACTED, and no low-cohesion communities
    for i in range(4):
        G.add_node(f"n{i}", label=f"Node{i}", source_file="x.py", file_type="code")
    # Fully connected clique — all nodes degree 3, no isolated nodes
    for i in range(4):
        for j in range(i + 1, 4):
            G.add_edge(f"n{i}", f"n{j}", relation="calls", confidence="EXTRACTED",
                       weight=1.0, source_file="x.py")
    communities = cluster(G)
    community_labels = {cid: f"Community {cid}" for cid in communities}
    result = suggest_questions(G, communities, community_labels)
    # Should have the no_signal fallback
    assert len(result) >= 1
    assert result[0]["type"] == "no_signal"


# ---------------------------------------------------------------------------
# graph_diff — directed graph (line 521)
# ---------------------------------------------------------------------------

def test_graph_diff_directed_graph():
    """Directed graphs preserve edge direction in edge_key."""
    G_old = nx.DiGraph()
    G_old.add_node("a", label="A", source_file="test.py")
    G_old.add_node("b", label="B", source_file="test.py")
    G_old.add_edge("a", "b", relation="calls", confidence="EXTRACTED")

    G_new = nx.DiGraph()
    G_new.add_node("a", label="A", source_file="test.py")
    G_new.add_node("b", label="B", source_file="test.py")
    G_new.add_edge("b", "a", relation="calls", confidence="EXTRACTED")

    diff = graph_diff(G_old, G_new)
    # a→b is removed, b→a is new
    assert len(diff["new_edges"]) == 1
    assert len(diff["removed_edges"]) == 1


# ---------------------------------------------------------------------------
# graph_diff — removed edges with summary (lines 549, 564)
# ---------------------------------------------------------------------------

def test_graph_diff_removed_edges():
    """Removed edges are listed and appear in summary."""
    G_old = nx.Graph()
    G_old.add_node("a", label="A", source_file="test.py")
    G_old.add_node("b", label="B", source_file="test.py")
    G_old.add_node("c", label="C", source_file="test.py")
    G_old.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    G_old.add_edge("b", "c", relation="uses", confidence="INFERRED")

    G_new = nx.Graph()
    G_new.add_node("a", label="A", source_file="test.py")
    G_new.add_node("b", label="B", source_file="test.py")
    G_new.add_node("c", label="C", source_file="test.py")
    G_new.add_edge("a", "b", relation="calls", confidence="EXTRACTED")

    diff = graph_diff(G_old, G_new)
    assert len(diff["removed_edges"]) == 1
    assert diff["removed_edges"][0]["relation"] == "uses"
    assert "edge" in diff["summary"] and "removed" in diff["summary"]


def test_graph_diff_removed_edges_plural():
    """Multiple removed edges show plural in summary."""
    G_old = nx.Graph()
    for nid in "abcd":
        G_old.add_node(nid, label=nid.upper(), source_file="test.py")
    G_old.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    G_old.add_edge("c", "d", relation="uses", confidence="INFERRED")

    G_new = nx.Graph()
    for nid in "abcd":
        G_new.add_node(nid, label=nid.upper(), source_file="test.py")

    diff = graph_diff(G_old, G_new)
    assert len(diff["removed_edges"]) == 2
    assert "2 edges removed" in diff["summary"]
