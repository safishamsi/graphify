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
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project")
    assert "# Graph Report" in report

def test_report_contains_corpus_check():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project")
    assert "## Corpus Check" in report

def test_report_contains_god_nodes():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project")
    assert "## God Nodes" in report

def test_report_contains_surprising_connections():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project")
    assert "## Surprising Connections" in report

def test_report_contains_communities():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project")
    assert "## Communities" in report

def test_report_contains_ambiguous_section():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project")
    assert "## Ambiguous Edges" in report

def test_report_shows_token_cost():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project")
    assert "Token cost" in report
    assert "1,200" in report

def test_report_shows_raw_cohesion_scores():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project", min_community_size=1)
    assert "Cohesion:" in report
    assert "✓" not in report
    assert "⚠" not in report


def test_report_surfaces_high_weak_node_ratio():
    """When >=20% of nodes are weak (degree <=1, non-file, non-concept),
    the report should include a high-noise warning."""
    import networkx as nx
    G = nx.Graph()
    # 3 weak nodes: low degree, look like real entities (have source_file with extension)
    for i in range(3):
        G.add_node(f"weak_{i}", label=f"isolated_func_{i}", source_file=f"module_{i}.py")
    # 7 normal well-connected nodes
    for i in range(7):
        G.add_node(f"normal_{i}", label=f"connected_{i}", source_file=f"core_{i}.py")
    for i in range(7):
        for j in range(i + 1, 7):
            G.add_edge(f"normal_{i}", f"normal_{j}", confidence="EXTRACTED")
    # Give one weak node a single edge (degree=1 still weak)
    G.add_edge("weak_0", "normal_0", confidence="EXTRACTED")
    # weak_1 and weak_2 stay at degree 0

    detection = {"total_files": 10, "total_words": 5000, "needs_graph": True, "warning": None}
    tokens = {"input": 1000, "output": 2000}
    communities = {0: [f"normal_{i}" for i in range(7)] + [f"weak_{i}" for i in range(3)]}
    cohesion = {0: 0.5}
    labels = {0: "Test Community"}
    gods = []
    surprises = []

    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./test")
    assert "Warning: weak-node ratio is high" in report
