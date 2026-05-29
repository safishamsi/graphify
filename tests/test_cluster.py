import json
import networkx as nx
from pathlib import Path
from graphify.build import build_from_json
from graphify.cluster import cluster, cohesion_score, remap_communities_to_previous, score_all

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
    G = nx.Graph()
    G.add_node("a")
    score = cohesion_score(G, ["a"])
    assert score == 1.0


def test_cohesion_score_disconnected():
    G = nx.Graph()
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


def test_remap_communities_to_previous_reuses_old_ids():
    communities = {
        10: ["a", "b", "c"],
        11: ["d", "e"],
    }
    previous = {"a": 5, "b": 5, "c": 5, "d": 1, "e": 1}
    remapped = remap_communities_to_previous(communities, previous)
    assert set(remapped.keys()) == {1, 5}
    assert remapped[5] == ["a", "b", "c"]
    assert remapped[1] == ["d", "e"]


def test_remap_communities_to_previous_assigns_deterministic_new_ids():
    communities = {
        7: ["x", "y", "z"],
        8: ["m"],
    }
    previous = {"a": 3}
    remapped = remap_communities_to_previous(communities, previous)
    assert list(remapped.keys()) == [0, 1]
    assert remapped[0] == ["x", "y", "z"]
    assert remapped[1] == ["m"]


# --- MultiDiGraph safety tests (PR 4B) ---


def _make_multigraph_triangle():
    """MultiDiGraph with nodes {a, b, c}: 5 parallel edges a->b, 3 parallel edges b->c."""
    G = nx.MultiDiGraph()
    G.add_nodes_from(["a", "b", "c"])
    for i in range(5):
        G.add_edge("a", "b", key=f"ab-{i}", relation=f"rel-{i}")
    for i in range(3):
        G.add_edge("b", "c", key=f"bc-{i}", relation=f"rel-{i}")
    return G


def test_cohesion_multigraph_stays_bounded():
    """Cohesion must be <= 1.0 even when parallel edges outnumber unique pairs."""
    G = _make_multigraph_triangle()
    # 3 nodes, 8 total edge records, but only 2 unique pairs -> must not exceed 1.0
    score = cohesion_score(G, ["a", "b", "c"])
    assert score <= 1.0, f"cohesion {score} exceeds 1.0 on multigraph"
    assert score >= 0.0


def test_cohesion_multigraph_equals_simple_graph_cohesion():
    """Cohesion on a multigraph should equal cohesion on the equivalent simple graph."""
    # Build a MultiDiGraph: a-b, b-c, a-c each with 3 parallel edges
    MG = nx.MultiDiGraph()
    MG.add_nodes_from(["a", "b", "c"])
    for pair in [("a", "b"), ("b", "c"), ("a", "c")]:
        for i in range(3):
            MG.add_edge(pair[0], pair[1], key=f"{pair[0]}{pair[1]}-{i}")

    # Build equivalent simple graph: a-b, b-c, a-c (1 edge each)
    SG = nx.Graph()
    SG.add_nodes_from(["a", "b", "c"])
    SG.add_edge("a", "b")
    SG.add_edge("b", "c")
    SG.add_edge("a", "c")

    multi_score = cohesion_score(MG, ["a", "b", "c"])
    simple_score = cohesion_score(SG, ["a", "b", "c"])
    assert multi_score == simple_score, f"multi={multi_score} != simple={simple_score}"


def test_cluster_multigraph_produces_valid_communities():
    """cluster() on a MultiDiGraph with clear community structure should detect communities."""
    G = nx.MultiDiGraph()
    # Two triangles connected by a weak bridge, with parallel edges and
    # confidence data so projected weights are non-zero (avoids graspologic
    # zero-weight panic in some versions).
    for pair in [("a", "b"), ("b", "c"), ("a", "c")]:
        for k in range(3):
            G.add_edge(pair[0], pair[1], key=f"{pair[0]}{pair[1]}-{k}", confidence="EXTRACTED")
    for pair in [("d", "e"), ("e", "f"), ("d", "f")]:
        for k in range(3):
            G.add_edge(pair[0], pair[1], key=f"{pair[0]}{pair[1]}-{k}", confidence="EXTRACTED")
    G.add_edge("c", "d", key="bridge", confidence="AMBIGUOUS")

    communities = cluster(G)
    assert isinstance(communities, dict)
    assert len(communities) > 0
    all_nodes = {n for nodes in communities.values() for n in nodes}
    assert all_nodes == set(G.nodes), "Not all nodes assigned to communities"


def test_cluster_multigraph_does_not_crash():
    """Smoke test: cluster() on a MultiDiGraph with parallel edges must not raise."""
    G = nx.MultiDiGraph()
    nodes = ["a", "b", "c", "d", "e"]
    G.add_nodes_from(nodes)
    for i in range(len(nodes)):
        for j in range(i + 1, min(i + 3, len(nodes))):
            for k in range(4):
                G.add_edge(
                    nodes[i], nodes[j], key=f"{nodes[i]}-{nodes[j]}-{k}", confidence="EXTRACTED"
                )
    # Must not raise
    communities = cluster(G)
    assert isinstance(communities, dict)
