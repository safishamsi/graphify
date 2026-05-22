from __future__ import annotations

import networkx as nx
import pytest
from typing import Any, cast

from graphify.projections import (
    distinct_neighbor_degree,
    edge_records_between,
    edge_summary_between,
    normalize_to_multidigraph,
    project_for_callflow,
    project_for_community,
    project_for_context,
    project_for_path,
)


def _parallel_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.graph["graphify_profile"] = "test-profile"
    graph.add_node("a", label="A")
    graph.add_node("b", label="B")
    graph.add_node("c", label="C")
    graph.add_edge(
        "a",
        "b",
        key="calls-low",
        relation="calls",
        confidence="INFERRED",
        confidence_score=0.4,
        source_file="src/a.py",
        source_location="L10",
        context="code",
    )
    graph.add_edge(
        "a",
        "b",
        key="imports-high",
        relation="imports",
        confidence="EXTRACTED",
        confidence_score=0.9,
        source_file="src/a.py",
        source_location="L2",
        context="code",
    )
    graph.add_edge(
        "b",
        "a",
        key="returns",
        relation="returns",
        confidence="AMBIGUOUS",
        confidence_score=0.2,
        source_file="src/b.py",
        source_location="L5",
        context="runtime",
    )
    graph.add_edge(
        "b",
        "c",
        key="calls-c",
        relation="calls",
        confidence="EXTRACTED",
        confidence_score=1.0,
        source_file="src/b.py",
        source_location="L7",
        context="code",
    )
    graph.add_edge("c", "c", key="self", relation="calls", confidence="EXTRACTED")
    return graph


def test_project_for_community_returns_simple_weighted_copy() -> None:
    projected = project_for_community(_parallel_graph(), weight_mode="count")

    assert type(projected) is nx.Graph
    assert projected.graph["graphify_profile"] == "test-profile"
    assert set(projected.nodes) == {"a", "b", "c"}
    assert not projected.has_edge("c", "c")
    assert projected["a"]["b"]["weight"] == 3.0
    assert projected["a"]["b"]["parallel_edge_count"] == 3
    assert projected["b"]["c"]["weight"] == 1.0


def test_project_for_community_supports_confidence_and_sum_weight_modes() -> None:
    graph = _parallel_graph()

    by_confidence = project_for_community(graph, weight_mode="confidence")
    by_sum = project_for_community(graph, weight_mode="sum")

    assert by_confidence["a"]["b"]["weight"] == 0.9
    assert by_confidence["a"]["b"]["relation"] == "imports"
    assert by_sum["a"]["b"]["weight"] == pytest.approx(1.5)
    with pytest.raises(ValueError, match="weight_mode"):
        project_for_community(graph, weight_mode=cast(Any, "unknown"))


def test_project_for_path_uses_simple_graph_not_multigraph_view() -> None:
    projected = project_for_path(_parallel_graph())

    assert type(projected) is nx.Graph
    assert not projected.is_multigraph()
    assert projected.number_of_edges("a", "b") == 1
    assert nx.shortest_path(projected, "a", "c") == ["a", "b", "c"]


def test_project_for_callflow_preserves_direction_and_filters_relations() -> None:
    projected = project_for_callflow(_parallel_graph(), relations=frozenset({"calls"}))

    assert type(projected) is nx.DiGraph
    assert set(projected.edges()) == {("a", "b"), ("b", "c")}
    assert projected["a"]["b"]["relation"] == "calls"


def test_project_for_callflow_recovers_src_tgt_from_undirected_edges() -> None:
    graph = nx.Graph()
    graph.add_node("display_a")
    graph.add_node("display_b")
    graph.add_edge("display_a", "display_b", _src="real_src", _tgt="real_tgt", relation="calls")

    projected = project_for_callflow(graph)

    assert set(projected.edges()) == {("real_src", "real_tgt")}
    assert projected["real_src"]["real_tgt"]["relation"] == "calls"


def test_project_for_context_preserves_multigraph_type_keys_and_metadata() -> None:
    projected = project_for_context(_parallel_graph(), contexts=["code"])

    assert isinstance(projected, nx.MultiDiGraph)
    assert projected.graph["graphify_profile"] == "test-profile"
    assert set(projected["a"]["b"]) == {"calls-low", "imports-high"}
    assert "returns" not in projected.get_edge_data("b", "a", default={})


def test_project_for_context_none_returns_copy_not_original() -> None:
    graph = _parallel_graph()

    projected = project_for_context(graph)

    assert projected is not graph
    assert isinstance(projected, nx.MultiDiGraph)
    assert projected.number_of_edges() == graph.number_of_edges()


def test_project_for_context_empty_filter_is_noop_copy() -> None:
    graph = _parallel_graph()

    projected = project_for_context(graph, contexts=[])

    assert projected is not graph
    assert projected.number_of_edges() == graph.number_of_edges()


def test_edge_records_between_returns_copies_from_both_directions() -> None:
    graph = _parallel_graph()

    records = edge_records_between(graph, "a", "b")

    assert [record["relation"] for record in records] == ["imports", "calls", "returns"]
    records[0]["relation"] = "mutated"
    assert graph["a"]["b"]["imports-high"]["relation"] == "imports"


def test_edge_summary_between_counts_and_picks_representative() -> None:
    summary = edge_summary_between(_parallel_graph(), "a", "b")

    assert summary["count"] == 3
    assert summary["relations"] == ["calls", "imports", "returns"]
    assert summary["confidences"] == ["AMBIGUOUS", "EXTRACTED", "INFERRED"]
    assert summary["representative"]["relation"] == "imports"


def test_distinct_neighbor_degree_does_not_count_parallel_edges() -> None:
    graph = _parallel_graph()

    assert graph.degree("a") == 3
    assert distinct_neighbor_degree(graph, "a") == 1
    assert distinct_neighbor_degree(graph, "missing") == 0


def test_normalize_to_multidigraph_preserves_parallel_keys_and_simple_edges() -> None:
    graph = nx.MultiGraph()
    graph.graph["name"] = "mixed"
    graph.add_node("a", label="A")
    graph.add_node("b", label="B")
    graph.add_edge("a", "b", key="one", relation="calls")
    graph.add_edge("a", "b", key="two", relation="imports")

    normalized = normalize_to_multidigraph(graph)

    assert isinstance(normalized, nx.MultiDiGraph)
    assert normalized.graph["name"] == "mixed"
    assert set(normalized["a"]["b"]) == {"one", "two"}

    simple = nx.Graph()
    simple.add_edge("x", "y", relation="uses")
    simple_normalized = normalize_to_multidigraph(simple)

    assert isinstance(simple_normalized, nx.MultiDiGraph)
    assert simple_normalized.number_of_edges("x", "y") == 1
    assert next(iter(simple_normalized["x"]["y"].values()))["relation"] == "uses"
