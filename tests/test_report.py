import json
from pathlib import Path
import networkx as nx
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


# --- Helpers for edge-count tests ---


def _minimal_report(G):
    """Generate a report from a graph with minimal scaffolding."""
    communities = {0: list(G.nodes())}
    cohesion = {0: 0.5}
    labels = {0: "Test Community"}
    god_list = [{"id": n, "label": n, "degree": G.degree(n)} for n in list(G.nodes())[:3]]
    surprise_list = []
    detection = {"total_files": 1, "total_words": 100, "needs_graph": True, "warning": None}
    tokens = {"input": 100, "output": 50}
    return generate(
        G,
        communities,
        cohesion,
        labels,
        god_list,
        surprise_list,
        detection,
        tokens,
        "./test",
        min_community_size=1,
    )


# --- PR 4B: Edge count reporting tests ---


def test_report_multigraph_edge_count_distinguishes_pairs():
    """MultiDiGraph with parallel edges: report must show both total and unique pair count."""
    G = nx.MultiDiGraph()
    G.add_nodes_from(["A", "B", "C", "D"], label="x", type="entity")
    # 3 unique pairs, 8 total edges
    G.add_edge("A", "B", relation="calls", confidence="EXTRACTED")
    G.add_edge("A", "B", relation="imports", confidence="EXTRACTED")
    G.add_edge("A", "B", relation="uses", confidence="EXTRACTED")
    G.add_edge("B", "C", relation="calls", confidence="EXTRACTED")
    G.add_edge("B", "C", relation="imports", confidence="EXTRACTED")
    G.add_edge("B", "C", relation="uses", confidence="EXTRACTED")
    G.add_edge("C", "D", relation="calls", confidence="EXTRACTED")
    G.add_edge("C", "D", relation="imports", confidence="EXTRACTED")
    assert G.number_of_edges() == 8
    report = _minimal_report(G)
    assert "8 edges (3 unique pairs)" in report


def test_report_simple_graph_edge_count_unchanged():
    """Simple DiGraph: report must show just 'X edges' without unique-pairs qualifier."""
    G = nx.DiGraph()
    G.add_nodes_from(["A", "B", "C"], label="x", type="entity")
    G.add_edge("A", "B", relation="calls", confidence="EXTRACTED")
    G.add_edge("B", "C", relation="calls", confidence="EXTRACTED")
    G.add_edge("A", "C", relation="calls", confidence="EXTRACTED")
    report = _minimal_report(G)
    assert "3 edges" in report
    assert "unique pairs" not in report


def test_report_multigraph_no_parallel_just_shows_total():
    """MultiDiGraph with no actual parallel edges: show just 'X edges', no redundant qualifier."""
    G = nx.MultiDiGraph()
    G.add_nodes_from(["A", "B", "C"], label="x", type="entity")
    G.add_edge("A", "B", relation="calls", confidence="EXTRACTED")
    G.add_edge("B", "C", relation="calls", confidence="EXTRACTED")
    G.add_edge("A", "C", relation="calls", confidence="EXTRACTED")
    assert G.number_of_edges() == 3
    report = _minimal_report(G)
    assert "3 edges" in report
    assert "unique pairs" not in report


def test_report_god_node_degree_not_inflated():
    """God-node degree should reflect unique neighbors, not parallel edge count.

    analyze.god_nodes() already uses distinct_neighbor_degree(), so the degree
    value in the report should equal the neighbor count, not the edge count.
    """
    G = nx.MultiDiGraph()
    # Nodes need source_file with an extension to avoid being filtered as concept nodes
    attrs = {"label": "hub", "type": "entity", "source_file": "test.py"}
    G.add_node("hub", **attrs)
    for name in ["A", "B", "C"]:
        G.add_node(name, label=name, type="entity", source_file="test.py")
    # hub -> A: 4 parallel edges, hub -> B: 3, hub -> C: 3 = 10 total, 3 unique neighbors
    for _ in range(4):
        G.add_edge("hub", "A", relation="calls", confidence="EXTRACTED")
    for _ in range(3):
        G.add_edge("hub", "B", relation="calls", confidence="EXTRACTED")
    for _ in range(3):
        G.add_edge("hub", "C", relation="calls", confidence="EXTRACTED")
    assert G.number_of_edges() == 10
    gods = god_nodes(G)
    hub_entry = next(g for g in gods if g["label"] == "hub")
    assert hub_entry["degree"] == 3, f"Expected 3 unique neighbors, got {hub_entry['degree']}"


# --- PR 6: parallel-edge preservation in per-edge report surfaces ---


def test_report_preserves_parallel_inferred_edges():
    """MultiDiGraph with parallel edges between one pair: every per-edge report
    surface must preserve ALL parallel edges, not collapse to one (PR 6).

    report.py iterates ``G.edges(data=True)`` for confidence stats, the INFERRED
    count/avg, and the ambiguous-edges list — on a MultiDiGraph that yields every
    parallel edge. This confirms the no-collapse contract:
      - INFERRED count reflects all 3 parallel inferred edges (not 1)
      - INFERRED avg confidence averages all 3 distinct scores (0.5/0.7/0.9 -> 0.7)
      - the ambiguous-edges section emits one line per parallel ambiguous edge
    """
    G = nx.MultiDiGraph()
    G.add_node("A", label="alpha", type="entity", source_file="a.py")
    G.add_node("B", label="beta", type="entity", source_file="b.py")
    # 3 parallel INFERRED edges between the SAME pair, distinct scores.
    G.add_edge("A", "B", relation="calls", confidence="INFERRED", confidence_score=0.5)
    G.add_edge("A", "B", relation="imports", confidence="INFERRED", confidence_score=0.7)
    G.add_edge("A", "B", relation="contains", confidence="INFERRED", confidence_score=0.9)
    # 2 parallel AMBIGUOUS edges between the SAME pair, distinct relations.
    G.add_edge("A", "B", relation="maybe_uses", confidence="AMBIGUOUS")
    G.add_edge("A", "B", relation="maybe_refs", confidence="AMBIGUOUS")
    assert G.number_of_edges() == 5
    report = _minimal_report(G)
    # All 3 parallel inferred edges are counted (collapse would show "1 edges").
    assert "INFERRED: 3 edges" in report
    # Average over all 3 parallel scores, proving each edge contributed.
    assert "avg confidence: 0.7" in report
    # The ambiguous-edges list preserves one line per parallel ambiguous edge.
    assert "relation: maybe_uses" in report
    assert "relation: maybe_refs" in report


def test_report_multigraph_edge_count_unchanged_semantics():
    """PR4B total-vs-unique-pairs edge-count line still renders correctly on a
    multigraph with parallel edges (regression for PR 6)."""
    G = nx.MultiDiGraph()
    G.add_node("A", label="alpha", type="entity", source_file="a.py")
    G.add_node("B", label="beta", type="entity", source_file="b.py")
    G.add_node("C", label="gamma", type="entity", source_file="c.py")
    # 2 unique pairs, 5 total edges (3 parallel A->B, 2 parallel B->C).
    G.add_edge("A", "B", relation="calls", confidence="EXTRACTED")
    G.add_edge("A", "B", relation="imports", confidence="EXTRACTED")
    G.add_edge("A", "B", relation="contains", confidence="EXTRACTED")
    G.add_edge("B", "C", relation="calls", confidence="EXTRACTED")
    G.add_edge("B", "C", relation="imports", confidence="EXTRACTED")
    assert G.number_of_edges() == 5
    report = _minimal_report(G)
    assert "5 edges (2 unique pairs)" in report
