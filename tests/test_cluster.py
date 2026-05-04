import json
import sys
import networkx as nx
from pathlib import Path
from graphify.build import build_from_json
from graphify.cluster import cluster, cohesion_score, score_all

FIXTURES = Path(__file__).parent / "fixtures"

def make_graph():
    return build_from_json(json.loads((FIXTURES / "extraction.json").read_text()))

def test_cluster_returns_dict():
    G = make_graph()
    communities = cluster(G)
    assert isinstance(communities, dict)

def test_cluster_covers_all_nodes():
    G = make_graph()
    communities = cluster(G)
    all_nodes = {n for nodes in communities.values() for n in nodes}
    assert all_nodes == set(G.nodes)

def test_cohesion_score_complete_graph():
    G = nx.complete_graph(4)
    G = nx.relabel_nodes(G, {i: str(i) for i in G.nodes})
    score = cohesion_score(G, list(G.nodes))
    assert score == 1.0

def test_cohesion_score_single_node():
    G = nx.DiGraph()
    G.add_node("a")
    score = cohesion_score(G, ["a"])
    assert score == 1.0

def test_cohesion_score_disconnected():
    G = nx.DiGraph()
    G.add_nodes_from(["a", "b", "c"])
    score = cohesion_score(G, ["a", "b", "c"])
    assert score == 0.0

def test_cohesion_score_range():
    G = make_graph()
    communities = cluster(G)
    for cid, nodes in communities.items():
        score = cohesion_score(G, nodes)
        assert 0.0 <= score <= 1.0

def test_score_all_keys_match_communities():
    G = make_graph()
    communities = cluster(G)
    scores = score_all(G, communities)
    assert set(scores.keys()) == set(communities.keys())


def test_cluster_does_not_write_to_stdout(capsys):
    """Clustering should not emit ANSI escape codes or other output.

    graspologic's leiden() can emit ANSI escape sequences that break
    PowerShell 5.1's scroll buffer on Windows (issue #19). The output
    suppression in _partition() should prevent any output from leaking.
    """
    G = make_graph()
    cluster(G)
    captured = capsys.readouterr()
    assert captured.out == "", f"cluster() wrote to stdout: {captured.out!r}"


def test_cluster_does_not_write_to_stderr(capsys):
    """Same as above but for stderr — ANSI codes can go to either stream."""
    G = make_graph()
    cluster(G)
    captured = capsys.readouterr()
    # Allow logging output (starts with [graphify]) but no raw ANSI codes
    for line in captured.err.splitlines():
        assert "\x1b" not in line, f"cluster() wrote ANSI to stderr: {line!r}"
