import json
from pathlib import Path
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections
from graphify.report import generate

FIXTURES = Path(__file__).parent / "fixtures"


def make_inputs():
    extraction = json.loads((FIXTURES / "extraction.json").read_text())
    G = build_from_json(extraction)
    communities = cluster(G)
    cohesion = score_all(G, communities)
    labels = {cid: f"Community {cid}" for cid in communities}
    gods = god_nodes(G)
    surprises = surprising_connections(G)
    detection = {"total_files": 4, "total_words": 62400, "needs_graph": True, "warning": None}
    tokens = {"input": extraction["input_tokens"], "output": extraction["output_tokens"]}
    return G, communities, cohesion, labels, gods, surprises, detection, tokens


def test_report_contains_header():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(
        G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project"
    )
    assert "# Graph Report" in report


def test_report_contains_corpus_check():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(
        G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project"
    )
    assert "## Corpus Check" in report


def test_report_contains_god_nodes():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(
        G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project"
    )
    assert "## God Nodes" in report


def test_report_contains_surprising_connections():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(
        G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project"
    )
    assert "## Surprising Connections" in report


def test_report_contains_communities():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(
        G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project"
    )
    assert "## Communities" in report


def test_report_contains_ambiguous_section():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(
        G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project"
    )
    assert "## Ambiguous Edges" in report


def test_report_shows_token_cost():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(
        G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project"
    )
    assert "Token cost" in report
    assert "1,200" in report


def test_report_shows_raw_cohesion_scores():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(
        G,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        detection,
        tokens,
        "./project",
        min_community_size=1,
    )
    assert "Cohesion:" in report
    assert "✓" not in report
    assert "⚠" not in report
