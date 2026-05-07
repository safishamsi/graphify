"""Comprehensive tests for graphify.semantic_facts."""
from __future__ import annotations

import pytest

from graphify.semantic_facts import (
    SemanticFact,
    append_unique_edge,
    append_unique_node,
    fact_to_edge,
    facts_to_edges,
    make_fact_node,
)


# ---------------------------------------------------------------------------
# SemanticFact — creation and validation
# ---------------------------------------------------------------------------


def test_semantic_fact_creation_with_all_fields() -> None:
    """Smoke test: all fields are stored correctly."""
    fact = SemanticFact(
        kind="call",
        source="caller",
        target="callee",
        relation="calls",
        label="caller->callee",
        source_file="pkg/mod.py",
        source_location="L10",
        confidence="EXTRACTED",
        confidence_score=0.95,
        weight=2.0,
        context="function_call",
        metadata={"resolver": "test", "line": 42},
    )
    assert fact.kind == "call"
    assert fact.source == "caller"
    assert fact.target == "callee"
    assert fact.relation == "calls"
    assert fact.label == "caller->callee"
    assert fact.source_file == "pkg/mod.py"
    assert fact.source_location == "L10"
    assert fact.confidence == "EXTRACTED"
    assert fact.confidence_score == 0.95
    assert fact.weight == 2.0
    assert fact.context == "function_call"
    assert fact.metadata == {"resolver": "test", "line": 42}


def test_semantic_fact_creation_with_minimal_fields() -> None:
    """Kind and source are the only required fields."""
    fact = SemanticFact(kind="definition", source="module_a")
    assert fact.kind == "definition"
    assert fact.source == "module_a"
    assert fact.target is None
    assert fact.relation is None
    assert fact.label is None
    assert fact.source_file is None
    assert fact.source_location is None
    assert fact.confidence == "EXTRACTED"
    assert fact.confidence_score == 1.0
    assert fact.weight == 1.0
    assert fact.context is None
    assert fact.metadata == {}


def test_semantic_fact_rejects_invalid_confidence() -> None:
    """Confidence must be one of EXTRACTED, INFERRED, or AMBIGUOUS."""
    with pytest.raises(ValueError, match="Invalid confidence"):
        SemanticFact(kind="call", source="a", target="b", relation="calls", confidence="CERTAIN")


def test_semantic_fact_requires_kind() -> None:
    """Kind cannot be empty."""
    with pytest.raises(ValueError, match="kind must be non-empty"):
        SemanticFact(kind="", source="a")


def test_semantic_fact_requires_source() -> None:
    """Source cannot be empty."""
    with pytest.raises(ValueError, match="source must be non-empty"):
        SemanticFact(kind="definition", source="")


def test_semantic_fact_is_frozen() -> None:
    """SemanticFact is a frozen dataclass — mutation should fail."""
    fact = SemanticFact(kind="call", source="a")
    with pytest.raises(Exception):
        fact.kind = "import"  # type: ignore[misc]


def test_semantic_fact_allows_all_valid_confidences() -> None:
    """EXTRACTED, INFERRED, and AMBIGUOUS are all accepted."""
    for conf in ("EXTRACTED", "INFERRED", "AMBIGUOUS"):
        fact = SemanticFact(kind="x", source="y", confidence=conf)
        assert fact.confidence == conf


# ---------------------------------------------------------------------------
# fact_to_edge — conversion and sanitisation
# ---------------------------------------------------------------------------


def test_fact_to_edge_returns_none_without_target() -> None:
    """When target is None the fact is node-only – return None."""
    fact = SemanticFact(kind="definition", source="module_a")
    assert fact_to_edge(fact) is None


def test_fact_to_edge_returns_none_without_relation() -> None:
    """When target is set but relation is None – return None."""
    fact = SemanticFact(kind="call", source="a", target="b", relation=None)
    assert fact_to_edge(fact) is None


def test_fact_to_edge_returns_none_with_both_target_and_relation_none() -> None:
    """Both target and relation missing."""
    fact = SemanticFact(kind="definition", source="module_a")
    assert fact_to_edge(fact) is None


def test_fact_to_edge_returns_none_with_empty_target_string() -> None:
    """Falsy empty string target counts as missing."""
    fact = SemanticFact(kind="call", source="a", target="", relation="calls")
    assert fact_to_edge(fact) is None


def test_fact_to_edge_returns_none_with_empty_relation_string() -> None:
    """Falsy empty string relation counts as missing."""
    fact = SemanticFact(kind="call", source="a", target="b", relation="")
    assert fact_to_edge(fact) is None


def test_fact_to_edge_converts_full_relation_fact() -> None:
    """All optional fields present — every key appears in the edge."""
    fact = SemanticFact(
        kind="call",
        source="caller",
        target="callee",
        relation="calls",
        source_file="pkg/mod.py",
        source_location="L10",
        confidence="EXTRACTED",
        confidence_score=1.0,
        weight=0.75,
        context="call",
        metadata={"resolver": "unit-test"},
    )
    edge = fact_to_edge(fact)
    assert edge == {
        "source": "caller",
        "target": "callee",
        "relation": "calls",
        "confidence": "EXTRACTED",
        "source_file": "pkg/mod.py",
        "source_location": "L10",
        "weight": 0.75,
        "confidence_score": 1.0,
        "context": "call",
        "metadata": {"resolver": "unit-test"},
    }


def test_fact_to_edge_omits_none_confidence_score() -> None:
    """When confidence_score is None it should not appear in the edge."""
    fact = SemanticFact(
        kind="call",
        source="a",
        target="b",
        relation="calls",
        confidence_score=None,
    )
    edge = fact_to_edge(fact)
    assert "confidence_score" not in edge
    assert edge["source"] == "a"
    assert edge["target"] == "b"
    assert edge["relation"] == "calls"


def test_fact_to_edge_omits_empty_context() -> None:
    """When context is None or empty it should not appear in the edge."""
    fact = SemanticFact(
        kind="call",
        source="a",
        target="b",
        relation="calls",
        context=None,
    )
    edge = fact_to_edge(fact)
    assert "context" not in edge


def test_fact_to_edge_omits_empty_metadata() -> None:
    """Empty metadata dict (falsy) should not appear in the edge."""
    fact = SemanticFact(
        kind="call",
        source="a",
        target="b",
        relation="calls",
        metadata={},
    )
    edge = fact_to_edge(fact)
    assert "metadata" not in edge


def test_fact_to_edge_default_source_file_to_empty_string() -> None:
    """source_file=None defaults to empty string in the edge."""
    fact = SemanticFact(kind="call", source="a", target="b", relation="calls", source_file=None)
    edge = fact_to_edge(fact)
    assert edge["source_file"] == ""


def test_fact_to_edge_preserves_none_source_location() -> None:
    """source_location=None is kept as None in the edge."""
    fact = SemanticFact(kind="call", source="a", target="b", relation="calls", source_location=None)
    edge = fact_to_edge(fact)
    assert edge["source_location"] is None


def test_fact_to_edge_renders_inferred_confidence() -> None:
    """INFERRED confidence is passed through unchanged."""
    fact = SemanticFact(kind="call", source="a", target="b", relation="calls", confidence="INFERRED")
    edge = fact_to_edge(fact)
    assert edge["confidence"] == "INFERRED"


# ---------------------------------------------------------------------------
# facts_to_edges — batch filtering
# ---------------------------------------------------------------------------


def test_facts_to_edges_skips_node_only_facts() -> None:
    """Node-only facts (no target/relation) are filtered out."""
    facts = [
        SemanticFact(kind="definition", source="a"),
        SemanticFact(kind="call", source="a", target="b", relation="calls"),
    ]
    assert facts_to_edges(facts) == [
        {
            "source": "a",
            "target": "b",
            "relation": "calls",
            "confidence": "EXTRACTED",
            "source_file": "",
            "source_location": None,
            "weight": 1.0,
            "confidence_score": 1.0,
        }
    ]


def test_facts_to_edges_empty_list() -> None:
    """Empty input produces empty output."""
    assert facts_to_edges([]) == []


def test_facts_to_edges_all_node_only() -> None:
    """When no fact has both target and relation, result is empty."""
    facts = [
        SemanticFact(kind="definition", source="a"),
        SemanticFact(kind="definition", source="b", target="c"),  # no relation
        SemanticFact(kind="call", source="d", relation="calls"),  # no target
    ]
    assert facts_to_edges(facts) == []


def test_facts_to_edges_all_edge_capable() -> None:
    """All facts become edges."""
    facts = [
        SemanticFact(kind="call", source="a", target="b", relation="calls"),
        SemanticFact(kind="import", source="x", target="y", relation="imports"),
    ]
    edges = facts_to_edges(facts)
    assert len(edges) == 2
    assert edges[0]["source"] == "a"
    assert edges[1]["source"] == "x"


def test_facts_to_edges_preserves_order() -> None:
    """Edge-capable facts appear in the same order as the input list."""
    facts = [
        SemanticFact(kind="def", source="first", target="a", relation="defines"),
        SemanticFact(kind="def", source="skip_me"),
        SemanticFact(kind="call", source="third", target="b", relation="calls"),
    ]
    edges = facts_to_edges(facts)
    assert len(edges) == 2
    assert edges[0]["source"] == "first"
    assert edges[1]["source"] == "third"


# ---------------------------------------------------------------------------
# make_fact_node — node creation and sanitisation
# ---------------------------------------------------------------------------


def test_make_fact_node_full() -> None:
    """All fields including metadata."""
    node = make_fact_node(
        node_id="pkg_mod_doc_param_name",
        label="name",
        file_type="doc_tag",
        source_file="pkg/mod.py",
        source_location="L5",
        metadata={"tag": "param"},
    )
    assert node == {
        "id": "pkg_mod_doc_param_name",
        "label": "name",
        "file_type": "doc_tag",
        "source_file": "pkg/mod.py",
        "source_location": "L5",
        "metadata": {"tag": "param"},
    }


def test_make_fact_node_without_metadata() -> None:
    """Metadata is optional — omitted from dict when None."""
    node = make_fact_node(
        node_id="n1",
        label="N1",
        file_type="code",
        source_file="src/main.py",
        source_location="L1",
    )
    assert node == {
        "id": "n1",
        "label": "N1",
        "file_type": "code",
        "source_file": "src/main.py",
        "source_location": "L1",
    }
    assert "metadata" not in node


def test_make_fact_node_without_source_location() -> None:
    """source_location can be None."""
    node = make_fact_node(
        node_id="n1",
        label="N1",
        file_type="code",
        source_file="src/main.py",
        source_location=None,
    )
    assert node["source_location"] is None


def test_make_fact_node_sanitizes_metadata() -> None:
    """Metadata is passed through sanitize_metadata (HTML-escapes strings)."""
    node = make_fact_node(
        node_id="n1",
        label="N1",
        file_type="code",
        source_file="src/main.py",
        source_location="L1",
        metadata={"key": "<script>alert(1)</script>"},
    )
    assert node["metadata"]["key"] == "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_make_fact_node_preserves_non_string_metadata() -> None:
    """Int, float, bool, None metadata values pass through unsanitised."""
    node = make_fact_node(
        node_id="n1",
        label="N1",
        file_type="code",
        source_file="src/main.py",
        source_location="L1",
        metadata={"line": 42, "score": 0.95, "active": True, "extra": None},
    )
    assert node["metadata"]["line"] == 42
    assert node["metadata"]["score"] == 0.95
    assert node["metadata"]["active"] is True
    assert node["metadata"]["extra"] is None


# ---------------------------------------------------------------------------
# append_unique_node — dedup by id
# ---------------------------------------------------------------------------


def test_append_unique_node_adds_new() -> None:
    """First insertion returns True and appends the node."""
    nodes: list[dict] = []
    seen: set[str] = set()
    node = {"id": "n1", "label": "N1"}
    assert append_unique_node(nodes, seen, node) is True
    assert nodes == [node]
    assert "n1" in seen


def test_append_unique_node_rejects_duplicate() -> None:
    """Same id a second time returns False and does not append."""
    nodes: list[dict] = []
    seen: set[str] = set()
    node = {"id": "n1", "label": "N1"}
    append_unique_node(nodes, seen, node)
    assert append_unique_node(nodes, seen, node) is False
    assert len(nodes) == 1


def test_append_unique_node_multiple_unique() -> None:
    """Different ids should all be appended."""
    nodes: list[dict] = []
    seen: set[str] = set()
    n1 = {"id": "n1", "label": "N1"}
    n2 = {"id": "n2", "label": "N2"}
    n3 = {"id": "n3", "label": "N3"}
    assert append_unique_node(nodes, seen, n1) is True
    assert append_unique_node(nodes, seen, n2) is True
    assert append_unique_node(nodes, seen, n3) is True
    assert nodes == [n1, n2, n3]
    assert seen == {"n1", "n2", "n3"}


def test_append_unique_node_rejects_missing_id_key() -> None:
    """Node dict without an 'id' key raises ValueError."""
    with pytest.raises(ValueError, match="node must contain a non-empty 'id'"):
        append_unique_node([], set(), {"label": "missing"})


def test_append_unique_node_rejects_empty_id() -> None:
    """Node dict with id='' raises ValueError."""
    with pytest.raises(ValueError, match="node must contain a non-empty 'id'"):
        append_unique_node([], set(), {"id": "", "label": "X"})


def test_append_unique_node_rejects_none_id() -> None:
    """Node dict with id=None raises ValueError (None is falsy)."""
    with pytest.raises(ValueError, match="node must contain a non-empty 'id'"):
        append_unique_node([], set(), {"id": None, "label": "X"})


# ---------------------------------------------------------------------------
# append_unique_edge — dedup by (source, target, relation, source_location)
# ---------------------------------------------------------------------------


def test_append_unique_edge_adds_new() -> None:
    """First insertion returns True and appends the edge."""
    edges: list[dict] = []
    seen: set[tuple[str, str, str, str | None]] = set()
    edge = {"source": "a", "target": "b", "relation": "calls", "source_location": "L1"}
    assert append_unique_edge(edges, seen, edge) is True
    assert edges == [edge]


def test_append_unique_edge_rejects_exact_duplicate() -> None:
    """Same source, target, relation, source_location is skipped."""
    edges: list[dict] = []
    seen: set[tuple[str, str, str, str | None]] = set()
    edge = {"source": "a", "target": "b", "relation": "calls", "source_location": "L1"}
    append_unique_edge(edges, seen, edge)
    assert append_unique_edge(edges, seen, edge) is False
    assert len(edges) == 1


def test_append_unique_edge_different_source_location_allows() -> None:
    """Same source/target/relation but different source_location → new edge."""
    edges: list[dict] = []
    seen: set[tuple[str, str, str, str | None]] = set()
    e1 = {"source": "a", "target": "b", "relation": "calls", "source_location": "L1"}
    e2 = {"source": "a", "target": "b", "relation": "calls", "source_location": "L2"}
    assert append_unique_edge(edges, seen, e1) is True
    assert append_unique_edge(edges, seen, e2) is True
    assert edges == [e1, e2]


def test_append_unique_edge_none_source_location_is_distinct() -> None:
    """None source_location is a distinct key from a string location."""
    edges: list[dict] = []
    seen: set[tuple[str, str, str, str | None]] = set()
    e1 = {"source": "a", "target": "b", "relation": "calls", "source_location": "L1"}
    e2 = {"source": "a", "target": "b", "relation": "calls", "source_location": None}
    assert append_unique_edge(edges, seen, e1) is True
    assert append_unique_edge(edges, seen, e2) is True
    assert edges == [e1, e2]


def test_append_unique_edge_two_none_source_locations_are_duplicate() -> None:
    """Two edges with same source/target/relation and both source_location=None are duplicates."""
    edges: list[dict] = []
    seen: set[tuple[str, str, str, str | None]] = set()
    e1 = {"source": "a", "target": "b", "relation": "calls", "source_location": None}
    e2 = {"source": "a", "target": "b", "relation": "calls", "source_location": None}
    assert append_unique_edge(edges, seen, e1) is True
    assert append_unique_edge(edges, seen, e2) is False


def test_append_unique_edge_different_relation_allows() -> None:
    """Same source/target but different relation → new edge."""
    edges: list[dict] = []
    seen: set[tuple[str, str, str, str | None]] = set()
    e1 = {"source": "a", "target": "b", "relation": "calls", "source_location": "L1"}
    e2 = {"source": "a", "target": "b", "relation": "imports", "source_location": "L1"}
    assert append_unique_edge(edges, seen, e1) is True
    assert append_unique_edge(edges, seen, e2) is True
    assert edges == [e1, e2]


def test_append_unique_edge_different_target_allows() -> None:
    """Same source/relation but different target → new edge."""
    edges: list[dict] = []
    seen: set[tuple[str, str, str, str | None]] = set()
    e1 = {"source": "a", "target": "b", "relation": "calls", "source_location": "L1"}
    e2 = {"source": "a", "target": "c", "relation": "calls", "source_location": "L1"}
    assert append_unique_edge(edges, seen, e1) is True
    assert append_unique_edge(edges, seen, e2) is True
    assert edges == [e1, e2]


def test_append_unique_edge_different_source_allows() -> None:
    """Same target/relation but different source → new edge."""
    edges: list[dict] = []
    seen: set[tuple[str, str, str, str | None]] = set()
    e1 = {"source": "a", "target": "b", "relation": "calls", "source_location": "L1"}
    e2 = {"source": "x", "target": "b", "relation": "calls", "source_location": "L1"}
    assert append_unique_edge(edges, seen, e1) is True
    assert append_unique_edge(edges, seen, e2) is True
    assert edges == [e1, e2]


def test_append_unique_edge_rejects_missing_source() -> None:
    """Missing source key raises ValueError."""
    with pytest.raises(ValueError, match="edge must contain source, target, and relation"):
        append_unique_edge([], set(), {"target": "b", "relation": "calls"})


def test_append_unique_edge_rejects_missing_target() -> None:
    """Missing target key raises ValueError."""
    with pytest.raises(ValueError, match="edge must contain source, target, and relation"):
        append_unique_edge([], set(), {"source": "a", "relation": "calls"})


def test_append_unique_edge_rejects_missing_relation() -> None:
    """Missing relation key raises ValueError."""
    with pytest.raises(ValueError, match="edge must contain source, target, and relation"):
        append_unique_edge([], set(), {"source": "a", "target": "b"})


def test_append_unique_edge_rejects_empty_source() -> None:
    """Empty string source is falsy → raises ValueError."""
    with pytest.raises(ValueError, match="edge must contain source, target, and relation"):
        append_unique_edge([], set(), {"source": "", "target": "b", "relation": "calls"})


def test_append_unique_edge_rejects_empty_target() -> None:
    """Empty string target is falsy → raises ValueError."""
    with pytest.raises(ValueError, match="edge must contain source, target, and relation"):
        append_unique_edge([], set(), {"source": "a", "target": "", "relation": "calls"})


def test_append_unique_edge_rejects_empty_relation() -> None:
    """Empty string relation is falsy → raises ValueError."""
    with pytest.raises(ValueError, match="edge must contain source, target, and relation"):
        append_unique_edge([], set(), {"source": "a", "target": "b", "relation": ""})
