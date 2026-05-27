"""Tests for confidence_score on edges."""
import json
import tempfile
from pathlib import Path


from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections
from graphify.export import to_json
from graphify.report import generate

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _make_extraction(**edge_overrides):
    """Return a minimal extraction dict with one edge of each confidence type."""
    base = {
        "nodes": [
            {"id": "n_a", "label": "A", "file_type": "code", "source_file": "a.py"},
            {"id": "n_b", "label": "B", "file_type": "code", "source_file": "b.py"},
            {"id": "n_c", "label": "C", "file_type": "document", "source_file": "c.md"},
            {"id": "n_d", "label": "D", "file_type": "document", "source_file": "d.md"},
        ],
        "edges": [
            {"source": "n_a", "target": "n_b", "relation": "calls", "confidence": "EXTRACTED",
             "confidence_score": 1.0, "source_file": "a.py", "weight": 1.0},
            {"source": "n_b", "target": "n_c", "relation": "implements", "confidence": "INFERRED",
             "confidence_score": 0.75, "source_file": "b.py", "weight": 0.8},
            {"source": "n_c", "target": "n_d", "relation": "references", "confidence": "AMBIGUOUS",
             "confidence_score": 0.2, "source_file": "c.md", "weight": 0.5},
        ],
        "input_tokens": 100,
        "output_tokens": 50,
    }
    return base


def test_extracted_edges_have_score_1():
    """EXTRACTED edges must have confidence_score == 1.0."""
    G = build_from_json(_make_extraction())
    for u, v, d in G.edges(data=True):
        if d.get("confidence") == "EXTRACTED":
            assert d.get("confidence_score") == 1.0, (
                f"EXTRACTED edge ({u},{v}) should have confidence_score=1.0, got {d.get('confidence_score')}"
            )


def test_inferred_edges_score_in_range():
    """INFERRED edges must have confidence_score between 0.0 and 1.0."""
    G = build_from_json(_make_extraction())
    found = False
    for u, v, d in G.edges(data=True):
        if d.get("confidence") == "INFERRED":
            found = True
            score = d.get("confidence_score")
            assert score is not None, f"INFERRED edge ({u},{v}) missing confidence_score"
            assert 0.0 <= score <= 1.0, (
                f"INFERRED edge ({u},{v}) confidence_score={score} out of range [0,1]"
            )
    assert found, "No INFERRED edges found in test fixture"


def test_ambiguous_edges_score_at_most_04():
    """AMBIGUOUS edges must have confidence_score <= 0.4."""
    G = build_from_json(_make_extraction())
    found = False
    for u, v, d in G.edges(data=True):
        if d.get("confidence") == "AMBIGUOUS":
            found = True
            score = d.get("confidence_score")
            assert score is not None, f"AMBIGUOUS edge ({u},{v}) missing confidence_score"
            assert score <= 0.4, (
                f"AMBIGUOUS edge ({u},{v}) confidence_score={score} should be <= 0.4"
            )
    assert found, "No AMBIGUOUS edges found in test fixture"


def test_confidence_score_round_trip():
    """confidence_score survives build_from_json → to_json → JSON parse round-trip."""
    extraction = _make_extraction()
    G = build_from_json(extraction)
    communities = cluster(G)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, communities, str(out))
        data = json.loads(out.read_text())

    # to_json uses node_link_data which puts edges in "links"
    links = data.get("links", [])
    assert links, "No links found in exported graph.json"
    for link in links:
        assert "confidence_score" in link, f"Link missing confidence_score: {link}"
        score = link["confidence_score"]
        assert isinstance(score, float), f"confidence_score should be float, got {type(score)}"
        assert 0.0 <= score <= 1.0, f"confidence_score={score} out of range"


def test_to_json_defaults_missing_confidence_score():
    """Edges lacking confidence_score get sensible defaults in to_json."""
    extraction = {
        "nodes": [
            {"id": "n_x", "label": "X", "file_type": "code", "source_file": "x.py"},
            {"id": "n_y", "label": "Y", "file_type": "code", "source_file": "y.py"},
            {"id": "n_z", "label": "Z", "file_type": "code", "source_file": "z.py"},
        ],
        "edges": [
            # No confidence_score field on any of these
            {"source": "n_x", "target": "n_y", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "x.py", "weight": 1.0},
            {"source": "n_y", "target": "n_z", "relation": "depends_on",
             "confidence": "INFERRED", "source_file": "y.py", "weight": 1.0},
        ],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_from_json(extraction)
    communities = cluster(G)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, communities, str(out))
        data = json.loads(out.read_text())

    links_by_conf = {}
    for link in data.get("links", []):
        conf = link.get("confidence", "EXTRACTED")
        links_by_conf[conf] = link.get("confidence_score")

    assert links_by_conf.get("EXTRACTED") == 1.0, "EXTRACTED default should be 1.0"
    assert links_by_conf.get("INFERRED") == 0.5, "INFERRED default should be 0.5"


def test_report_shows_avg_confidence_for_inferred():
    """Report summary line should include avg confidence for INFERRED edges."""
    extraction = _make_extraction()
    G = build_from_json(extraction)
    communities = cluster(G)
    cohesion = score_all(G, communities)
    labels = {cid: f"Community {cid}" for cid in communities}
    gods = god_nodes(G)
    surprises = surprising_connections(G)
    detection = {"total_files": 2, "total_words": 5000, "needs_graph": True, "warning": None}
    tokens = {"input": 100, "output": 50}

    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, ".")
    assert "avg confidence" in report, "Report should show avg confidence for INFERRED edges"
    # The fixture has one INFERRED edge with score 0.75, so avg should be 0.75
    assert "0.75" in report, f"Expected avg confidence 0.75 in report"


def test_report_inferred_tag_with_score():
    """Surprising connections section shows confidence score next to INFERRED edges."""
    # Build a graph where surprising_connections will find an INFERRED cross-file edge
    extraction = {
        "nodes": [
            {"id": "n_p", "label": "Parser", "file_type": "code", "source_file": "parser.py"},
            {"id": "n_q", "label": "Renderer", "file_type": "code", "source_file": "renderer.py"},
        ],
        "edges": [
            {"source": "n_p", "target": "n_q", "relation": "feeds",
             "confidence": "INFERRED", "confidence_score": 0.82,
             "source_file": "parser.py", "weight": 1.0},
        ],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_from_json(extraction)

    # Manually construct a surprise entry the way analyze.surprising_connections would
    surprise = {
        "source": "Parser",
        "target": "Renderer",
        "relation": "feeds",
        "confidence": "INFERRED",
        "confidence_score": 0.82,
        "source_files": ["parser.py", "renderer.py"],
        "note": "",
    }
    communities = cluster(G)
    cohesion = score_all(G, communities)
    labels = {cid: f"Community {cid}" for cid in communities}
    gods = god_nodes(G)
    detection = {"total_files": 2, "total_words": 1000, "needs_graph": True, "warning": None}
    tokens = {"input": 0, "output": 0}

    report = generate(G, communities, cohesion, labels, gods, [surprise], detection, tokens, ".")
    assert "INFERRED 0.82" in report, (
        f"Report should show 'INFERRED 0.82' in surprising connections section. Got:\n{report}"
    )
