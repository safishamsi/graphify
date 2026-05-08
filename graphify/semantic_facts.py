"""Deterministic semantic fact helpers for Graphify extraction.

This module intentionally has no Tree-sitter dependency. Tree-sitter-specific
extractors can create these facts, but the fact model itself is plain Python so
it is easy to unit test and safe to import from any extraction path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from graphify.security import sanitize_metadata


_VALID_CONFIDENCE = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}


@dataclass(frozen=True)
class SemanticFact:
    """A neutral deterministic fact discovered before graph edge emission.

    A fact is not necessarily a final graph edge. It is evidence. For example,
    a Python docstring section may produce a ``documents`` fact, while an import
    statement may produce an ``imports`` fact that later name resolution can use.
    """

    kind: str
    source: str
    target: str | None = None
    relation: str | None = None
    label: str | None = None
    source_file: str | None = None
    source_location: str | None = None
    confidence: str = "EXTRACTED"
    confidence_score: float | None = 1.0
    weight: float = 1.0
    context: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.confidence not in _VALID_CONFIDENCE:
            raise ValueError(
                f"Invalid confidence {self.confidence!r}; "
                f"expected one of {sorted(_VALID_CONFIDENCE)}"
            )
        if not self.kind:
            raise ValueError("SemanticFact.kind must be non-empty")
        if not self.source:
            raise ValueError("SemanticFact.source must be non-empty")


def fact_to_edge(fact: SemanticFact) -> dict[str, Any] | None:
    """Convert a relation fact into a Graphify edge dictionary.

    Returns ``None`` when the fact does not have both a target and a relation.
    This lets callers keep node-only facts in the same list without branching.
    """

    if not fact.target or not fact.relation:
        return None

    edge: dict[str, Any] = {
        "source": fact.source,
        "target": fact.target,
        "relation": fact.relation,
        "confidence": fact.confidence,
        "source_file": fact.source_file or "",
        "source_location": fact.source_location,
        "weight": fact.weight,
    }
    if fact.confidence_score is not None:
        edge["confidence_score"] = fact.confidence_score
    if fact.context:
        edge["context"] = fact.context
    if fact.metadata:
        edge["metadata"] = sanitize_metadata(fact.metadata)
    return edge


def facts_to_edges(facts: list[SemanticFact]) -> list[dict[str, Any]]:
    """Convert all edge-capable facts into Graphify edge dictionaries."""

    edges: list[dict[str, Any]] = []
    for fact in facts:
        edge = fact_to_edge(fact)
        if edge is not None:
            edges.append(edge)
    return edges


def make_fact_node(
    *,
    node_id: str,
    label: str,
    file_type: str,
    source_file: str,
    source_location: str | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a Graphify-compatible node dictionary for deterministic facts."""

    node: dict[str, Any] = {
        "id": node_id,
        "label": label,
        "file_type": file_type,
        "source_file": source_file,
        "source_location": source_location,
    }
    if metadata:
        node["metadata"] = sanitize_metadata(metadata)
    return node


def append_unique_node(
    nodes: list[dict[str, Any]],
    seen_ids: set[str],
    node: dict[str, Any],
) -> bool:
    """Append ``node`` only when its id has not already been emitted.

    Returns True when a node was added and False when it was skipped.
    """

    node_id = node.get("id")
    if not node_id:
        raise ValueError("node must contain a non-empty 'id'")
    if node_id in seen_ids:
        return False
    seen_ids.add(node_id)
    nodes.append(node)
    return True


def append_unique_edge(
    edges: list[dict[str, Any]],
    seen_edges: set[tuple[str, str, str, str | None]],
    edge: dict[str, Any],
) -> bool:
    """Append ``edge`` only when the semantic edge key has not appeared.

    The key includes source, target, relation, and source_location. Keeping the
    source location in the key allows two different call sites to remain visible
    when a future relation needs that detail, while still removing accidental
    duplicate emissions from the same fact.
    """

    source = edge.get("source")
    target = edge.get("target")
    relation = edge.get("relation")
    source_location = edge.get("source_location")
    if not source or not target or not relation:
        raise ValueError("edge must contain source, target, and relation")
    key = (source, target, relation, source_location)
    if key in seen_edges:
        return False
    seen_edges.add(key)
    edges.append(edge)
    return True
