from __future__ import annotations

import networkx as nx
import pytest
from typing import Any, cast

from graphify.projections import (
    DEFAULT_RELATIONSHIP_CAP,
    distinct_neighbor_degree,
    edge_records_between,
    edge_summary_between,
    format_relationship_envelope,
    normalize_to_multidigraph,
    project_for_callflow,
    project_for_community,
    project_for_context,
    project_for_path,
    relationship_envelope,
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


# ---------------------------------------------------------------------------
# relationship_envelope / format_relationship_envelope
# ---------------------------------------------------------------------------


def _multidigraph_with_parallel_relations(
    relations: list[str], *, confidence: str | None = None
) -> nx.MultiDiGraph:
    """Build A->B with one parallel edge per supplied relation."""
    graph = nx.MultiDiGraph()
    graph.add_node("a", label="A")
    graph.add_node("b", label="B")
    for index, relation in enumerate(relations):
        attrs: dict[str, Any] = {"relation": relation}
        if confidence is not None:
            attrs["confidence"] = confidence
        graph.add_edge("a", "b", key=f"{relation}-{index}", **attrs)
    return graph


def test_relationship_envelope_single_edge() -> None:
    graph = nx.DiGraph()
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED")

    envelope = relationship_envelope(graph, "a", "b")

    assert envelope["count"] == 1
    assert len(envelope["shown"]) == 1
    assert envelope["shown"][0]["relation"] == "calls"
    assert envelope["truncated"] == 0
    assert envelope["relations"] == ["calls"]
    assert envelope["confidences"] == ["EXTRACTED"]


def test_relationship_envelope_multidigraph_bundles_all() -> None:
    graph = _multidigraph_with_parallel_relations(["calls", "imports", "contains"])

    envelope = relationship_envelope(graph, "a", "b")

    assert envelope["count"] == 3
    assert envelope["relations"] == ["calls", "contains", "imports"]
    assert len(envelope["shown"]) == 3  # default cap == 3 fits all
    assert envelope["truncated"] == 0
    # shown records mirror edge_records_between ordering
    assert envelope["shown"] == edge_records_between(graph, "a", "b")


def test_relationship_envelope_caps_shown() -> None:
    graph = _multidigraph_with_parallel_relations(["r1", "r2", "r3", "r4", "r5"])

    envelope = relationship_envelope(graph, "a", "b", cap=3)

    assert envelope["count"] == 5
    assert len(envelope["shown"]) == 3
    assert envelope["truncated"] == 2
    assert envelope["relations"] == ["r1", "r2", "r3", "r4", "r5"]
    # shown is the leading slice of the full sorted record list
    assert envelope["shown"] == edge_records_between(graph, "a", "b")[:3]


def test_relationship_envelope_cap_zero_or_negative() -> None:
    graph = _multidigraph_with_parallel_relations(
        ["calls", "imports", "contains"], confidence="EXTRACTED"
    )

    zero = relationship_envelope(graph, "a", "b", cap=0)
    assert zero["shown"] == []
    assert zero["truncated"] == zero["count"] == 3
    assert zero["relations"] == ["calls", "contains", "imports"]
    assert zero["confidences"] == ["EXTRACTED"]

    negative = relationship_envelope(graph, "a", "b", cap=-1)
    assert negative["shown"] == []
    assert negative["truncated"] == negative["count"] == 3
    assert negative["relations"] == ["calls", "contains", "imports"]


def test_relationship_envelope_directed_both_directions() -> None:
    graph = nx.DiGraph()
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    graph.add_edge("b", "a", relation="returns", confidence="INFERRED")

    envelope = relationship_envelope(graph, "a", "b")

    assert envelope["count"] == 2
    assert envelope["relations"] == ["calls", "returns"]
    assert envelope["confidences"] == ["EXTRACTED", "INFERRED"]
    assert envelope["shown"] == edge_records_between(graph, "a", "b")


def test_relationship_envelope_no_edge() -> None:
    graph = nx.DiGraph()
    graph.add_node("a")
    graph.add_node("b")

    envelope = relationship_envelope(graph, "a", "b")

    assert envelope["count"] == 0
    assert envelope["shown"] == []
    assert envelope["truncated"] == 0
    assert envelope["relations"] == []
    assert envelope["confidences"] == []


def test_format_relationship_envelope_single() -> None:
    without_confidence = nx.DiGraph()
    without_confidence.add_edge("a", "b", relation="calls")
    assert format_relationship_envelope(without_confidence, "a", "b") == "calls"

    with_confidence = nx.DiGraph()
    with_confidence.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    assert format_relationship_envelope(with_confidence, "a", "b") == "calls (EXTRACTED)"


def test_format_relationship_envelope_multiple_within_cap() -> None:
    graph = _multidigraph_with_parallel_relations(
        ["imports", "calls", "contains"], confidence="EXTRACTED"
    )

    # 3 unique relations within the default cap; confidence omitted for multi-relation lines
    assert format_relationship_envelope(graph, "a", "b") == "calls, contains, imports"


def test_format_relationship_envelope_capped() -> None:
    graph = _multidigraph_with_parallel_relations(
        ["gamma", "alpha", "epsilon", "beta", "delta"]
    )

    # sorted unique relations: alpha, beta, delta, epsilon, gamma -> first 3 shown
    assert (
        format_relationship_envelope(graph, "a", "b", cap=3)
        == "alpha, beta, delta (+2 more, 5 total)"
    )


def test_format_relationship_envelope_empty() -> None:
    graph = nx.DiGraph()
    graph.add_node("a")
    graph.add_node("b")

    assert format_relationship_envelope(graph, "a", "b") == ""


def test_relationship_envelope_simple_graph_regression() -> None:
    graph = nx.DiGraph()
    graph.add_edge("a", "b", relation="calls")
    graph.add_edge("a", "c", relation="imports")

    # Plain DiGraph: no parallel edges, so the envelope between a single pair
    # reflects exactly the one edge and shown == all records (cap unreached).
    assert DEFAULT_RELATIONSHIP_CAP == 3
    envelope = relationship_envelope(graph, "a", "b")
    assert envelope["count"] == graph.number_of_edges("a", "b") == 1
    assert envelope["shown"] == edge_records_between(graph, "a", "b")
    assert envelope["truncated"] == 0


def _bidirectional_digraph() -> nx.DiGraph:
    """Directed A->B (calls) plus the reverse B->A (imports)."""
    graph = nx.DiGraph()
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    graph.add_edge("b", "a", relation="imports", confidence="INFERRED")
    return graph


def test_edge_records_between_directed_only_excludes_reverse() -> None:
    graph = _bidirectional_digraph()

    both = edge_records_between(graph, "a", "b")
    assert len(both) == 2
    assert {record["relation"] for record in both} == {"calls", "imports"}

    forward = edge_records_between(graph, "a", "b", directed_only=True)
    assert len(forward) == 1
    assert forward[0]["relation"] == "calls"


def test_relationship_envelope_directed_only() -> None:
    graph = _bidirectional_digraph()

    envelope = relationship_envelope(graph, "a", "b", directed_only=True)

    assert envelope["count"] == 1
    assert envelope["relations"] == ["calls"]
    assert "imports" not in envelope["relations"]
    assert [record["relation"] for record in envelope["shown"]] == ["calls"]


def test_format_relationship_envelope_directed_only() -> None:
    graph = _bidirectional_digraph()

    # Single forward relation with confidence present -> "calls (EXTRACTED)".
    rendered = format_relationship_envelope(graph, "a", "b", directed_only=True)
    assert rendered == "calls (EXTRACTED)"
    assert "imports" not in rendered

    # Without confidence the single forward relation renders bare.
    plain = nx.DiGraph()
    plain.add_edge("a", "b", relation="calls")
    plain.add_edge("b", "a", relation="imports")
    assert format_relationship_envelope(plain, "a", "b", directed_only=True) == "calls"


def test_directed_only_noop_on_undirected() -> None:
    graph = nx.Graph()
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    graph.add_edge("a", "b", relation="imports")  # simple graph: overwrites attrs, single edge

    assert edge_records_between(graph, "a", "b", directed_only=True) == edge_records_between(
        graph, "a", "b"
    )
    assert relationship_envelope(graph, "a", "b", directed_only=True) == relationship_envelope(
        graph, "a", "b"
    )
    assert format_relationship_envelope(
        graph, "a", "b", directed_only=True
    ) == format_relationship_envelope(graph, "a", "b")
