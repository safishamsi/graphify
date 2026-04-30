import networkx as nx
import pytest

from graphify.cypher import _parse_cypher, execute_cypher, render_results


@pytest.fixture
def sample_graph():
    # _src/_tgt mirror what build_from_json populates so directional
    # MATCH queries can resolve edge orientation.
    G = nx.Graph()
    G.add_node("a", label="Alpha", file_type="code", community=0)
    G.add_node("b", label="Beta", file_type="code", community=1)
    G.add_node("c", label="Gamma", file_type="document", community=0)
    G.add_edge("a", "b", relation="uses", confidence="EXTRACTED", _src="a", _tgt="b")
    G.add_edge("b", "c", relation="imports", confidence="INFERRED", _src="b", _tgt="c")
    return G


def test_parse_simple_match():
    parsed = _parse_cypher("MATCH (n) RETURN n")
    assert len(parsed["match_nodes"]) == 1
    assert parsed["match_nodes"][0]["var"] == "n"
    assert parsed["return_fields"] == ["n"]


def test_parse_match_with_label():
    parsed = _parse_cypher("MATCH (n:code) RETURN n.label")
    assert parsed["match_nodes"][0]["label"] == "code"
    assert parsed["return_fields"] == ["n.label"]


def test_parse_match_edge():
    parsed = _parse_cypher("MATCH (n)-[r:uses]->(m) RETURN n, m")
    assert len(parsed["match_nodes"]) == 2
    assert len(parsed["match_edges"]) == 1
    assert parsed["match_edges"][0]["type"] == "uses"


def test_parse_where():
    parsed = _parse_cypher("MATCH (n) WHERE n.community = 0 RETURN n")
    assert len(parsed["where"]) == 1
    assert parsed["where"][0]["prop"] == "community"
    assert parsed["where"][0]["value"] == 0


def test_parse_limit():
    parsed = _parse_cypher("MATCH (n) RETURN n LIMIT 5")
    assert parsed["limit"] == 5


def test_execute_all_nodes(sample_graph):
    results = execute_cypher(sample_graph, "MATCH (n) RETURN n.label")
    labels = {r["n.label"] for r in results}
    assert labels == {"Alpha", "Beta", "Gamma"}


def test_execute_label_filter(sample_graph):
    results = execute_cypher(sample_graph, "MATCH (n:code) RETURN n.label")
    labels = {r["n.label"] for r in results}
    assert labels == {"Alpha", "Beta"}


def test_execute_where_equality(sample_graph):
    results = execute_cypher(sample_graph, "MATCH (n) WHERE n.community = 0 RETURN n.label")
    labels = {r["n.label"] for r in results}
    assert labels == {"Alpha", "Gamma"}


def test_execute_edge_query(sample_graph):
    results = execute_cypher(sample_graph, "MATCH (n)-[r:uses]->(m) RETURN n.label, m.label")
    assert len(results) == 1
    assert results[0]["n.label"] == "Alpha"
    assert results[0]["m.label"] == "Beta"


def test_execute_contains(sample_graph):
    results = execute_cypher(sample_graph, "MATCH (n) WHERE n.label CONTAINS 'et' RETURN n.label")
    labels = {r["n.label"] for r in results}
    assert "Beta" in labels


def test_execute_limit(sample_graph):
    results = execute_cypher(sample_graph, "MATCH (n) RETURN n.label LIMIT 2")
    assert len(results) == 2


def test_execute_edge_direction_respects_src_tgt():
    # Build a graph where NetworkX's canonical (u, v) order disagrees with
    # the original directional intent stored in _src/_tgt. The Cypher
    # ->m direction should bind n=src, m=tgt regardless of iteration order.
    G = nx.Graph()
    G.add_node("alpha", label="Alpha", file_type="code")
    G.add_node("beta", label="Beta", file_type="code")
    G.add_edge("beta", "alpha", relation="uses", _src="alpha", _tgt="beta")

    results = execute_cypher(G, "MATCH (n)-[r:uses]->(m) RETURN n.label, m.label")
    assert len(results) == 1
    assert results[0]["n.label"] == "Alpha"
    assert results[0]["m.label"] == "Beta"


def test_execute_edge_direction_skips_when_src_tgt_missing():
    # Without _src/_tgt, a directional MATCH must not silently return
    # back-edges — it should yield no rows rather than a fake match.
    G = nx.Graph()
    G.add_node("a", label="A", file_type="code")
    G.add_node("b", label="B", file_type="code")
    G.add_edge("a", "b", relation="uses")  # no _src/_tgt

    results = execute_cypher(G, "MATCH (n)-[r:uses]->(m) RETURN n.label")
    assert results == []


def test_render_results_table():
    text = render_results([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
    assert "a | b" in text
    assert "1 | 2" in text


def test_render_results_empty():
    assert render_results([]) == "(no results)"
