"""Tests for semantically_similar_to edge support."""
import networkx as nx
import pytest
from graphify.build import build_from_json
from graphify.analyze import surprising_connections, _surprise_score
from graphify.report import generate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_extraction_with_semantic_edge():
    """Two nodes in separate files connected by a semantically_similar_to edge."""
    return {
        "nodes": [
            {"id": "a_validate_input", "label": "validate_input", "file_type": "code",
             "source_file": "auth/validators.py", "source_location": "L5"},
            {"id": "b_check_input", "label": "check_input", "file_type": "code",
             "source_file": "api/checks.py", "source_location": "L12"},
        ],
        "edges": [
            {
                "source": "a_validate_input",
                "target": "b_check_input",
                "relation": "semantically_similar_to",
                "confidence": "INFERRED",
                "confidence_score": 0.82,
                "source_file": "auth/validators.py",
                "source_location": None,
                "weight": 0.82,
            }
        ],
        "input_tokens": 100,
        "output_tokens": 50,
    }


def _make_graph_with_semantic_edge():
    return build_from_json(_make_extraction_with_semantic_edge())


def _make_two_edge_graph():
    """Graph with one semantically_similar_to edge and one references edge, both cross-file."""
    G = nx.DiGraph()
    for nid, label, src in [
        ("a", "ValidateInput", "auth/validators.py"),
        ("b", "CheckInput", "api/checks.py"),
        ("c", "LoadConfig", "config/loader.py"),
        ("d", "ReadConfig", "utils/reader.py"),
    ]:
        G.add_node(nid, label=label, source_file=src, file_type="code")
    # semantically_similar_to edge
    G.add_edge("a", "b", relation="semantically_similar_to", confidence="INFERRED",
               confidence_score=0.82, source_file="auth/validators.py", weight=0.82)
    # plain references edge (same confidence tier)
    G.add_edge("c", "d", relation="references", confidence="INFERRED",
               confidence_score=0.7, source_file="config/loader.py", weight=0.7)
    return G


# ---------------------------------------------------------------------------
# Test 1: semantically_similar_to passes through build_from_json without being dropped
# ---------------------------------------------------------------------------

def test_semantic_edge_survives_build_from_json():
    G = _make_graph_with_semantic_edge()
    assert G.number_of_edges() == 1
    u, v, data = next(iter(G.edges(data=True)))
    assert data["relation"] == "semantically_similar_to"


def test_semantic_edge_nodes_present():
    G = _make_graph_with_semantic_edge()
    assert "a_validate_input" in G.nodes
    assert "b_check_input" in G.nodes


# ---------------------------------------------------------------------------
# Test 2: confidence_score is preserved for semantically_similar_to edges
# ---------------------------------------------------------------------------

def test_semantic_edge_confidence_score_preserved():
    G = _make_graph_with_semantic_edge()
    u, v, data = next(iter(G.edges(data=True)))
    assert data.get("confidence_score") == pytest.approx(0.82)
    assert data.get("confidence") == "INFERRED"


# ---------------------------------------------------------------------------
# Test 3: surprising_connections scores semantically_similar_to edges higher
#         than references edges with the same community membership
# ---------------------------------------------------------------------------

def test_semantic_edge_scores_higher_than_references():
    G = _make_two_edge_graph()
    communities = {0: ["a", "b"], 1: ["c", "d"]}
    node_community = {"a": 0, "b": 0, "c": 1, "d": 1}

    score_sem, reasons_sem = _surprise_score(
        G, "a", "b", G.edges["a", "b"], node_community,
        "auth/validators.py", "api/checks.py"
    )
    score_ref, _ = _surprise_score(
        G, "c", "d", G.edges["c", "d"], node_community,
        "config/loader.py", "utils/reader.py"
    )
    assert score_sem > score_ref


def test_semantic_edge_reason_mentions_similarity():
    G = _make_two_edge_graph()
    communities = {0: ["a", "b"], 1: ["c", "d"]}
    node_community = {"a": 0, "b": 0, "c": 1, "d": 1}

    _, reasons = _surprise_score(
        G, "a", "b", G.edges["a", "b"], node_community,
        "auth/validators.py", "api/checks.py"
    )
    assert any("similar" in r for r in reasons)


# ---------------------------------------------------------------------------
# Test 4: report renders [semantically similar] tag for these edges
# ---------------------------------------------------------------------------

def _make_report_with_semantic_surprise():
    G = _make_graph_with_semantic_edge()
    communities = {0: ["a_validate_input", "b_check_input"]}
    cohesion = {0: 0.5}
    labels = {0: "Validators"}
    gods = []
    surprises = [
        {
            "source": "validate_input",
            "target": "check_input",
            "relation": "semantically_similar_to",
            "confidence": "INFERRED",
            "confidence_score": 0.82,
            "source_files": ["auth/validators.py", "api/checks.py"],
            "why": "semantically similar concepts with no structural link",
        }
    ]
    detection = {"total_files": 2, "total_words": 500, "needs_graph": True, "warning": None}
    tokens = {"input": 100, "output": 50}
    return generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project")


def test_report_renders_semantically_similar_tag():
    report = _make_report_with_semantic_surprise()
    assert "[semantically similar]" in report


def test_report_semantic_tag_on_correct_line():
    report = _make_report_with_semantic_surprise()
    for line in report.splitlines():
        if "semantically_similar_to" in line:
            assert "[semantically similar]" in line
            break
    else:
        pytest.fail("No line with semantically_similar_to found in report")


def test_report_no_semantic_tag_for_other_relations():
    """Non-semantic edges must not get the [semantically similar] tag."""
    G = nx.DiGraph()
    for nid, label, src in [
        ("x", "Alpha", "repo1/a.py"),
        ("y", "Beta", "repo2/b.py"),
    ]:
        G.add_node(nid, label=label, source_file=src, file_type="code")
    G.add_edge("x", "y", relation="references", confidence="EXTRACTED",
               confidence_score=1.0, source_file="repo1/a.py", weight=1.0)

    communities = {0: ["x", "y"]}
    cohesion = {0: 0.5}
    labels = {0: "Misc"}
    gods = []
    surprises = [
        {
            "source": "Alpha",
            "target": "Beta",
            "relation": "references",
            "confidence": "EXTRACTED",
            "source_files": ["repo1/a.py", "repo2/b.py"],
            "why": "cross-file connection",
        }
    ]
    detection = {"total_files": 2, "total_words": 200, "needs_graph": True, "warning": None}
    tokens = {"input": 50, "output": 25}
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project")
    assert "[semantically similar]" not in report
