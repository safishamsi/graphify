"""Property-based fuzz tests for extraction and graph building.

Uses Hypothesis to generate random extraction dicts and verify that
build_from_json never crashes on well-formed or malformed input.
"""
from __future__ import annotations
import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from graphify.build import build_from_json
from graphify.validate import validate_extraction, VALID_FILE_TYPES, VALID_CONFIDENCES
from graphify.cluster import cluster
from graphify.constants import Confidence


# ── Strategies ──────────────────────────────────────────────────────────────

_node_id = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_",
    min_size=1,
    max_size=30,
)

_label = st.text(min_size=1, max_size=50)
_file_type = st.sampled_from(sorted(VALID_FILE_TYPES))
_confidence = st.sampled_from([c.value for c in Confidence])
_source_file = st.from_regex(r"[a-z]{1,10}/[a-z]{1,10}\.(py|js|ts|go|rs)", fullmatch=True)

_node = st.fixed_dictionaries({
    "id": _node_id,
    "label": _label,
    "file_type": _file_type,
    "source_file": _source_file,
})

_relation = st.sampled_from([
    "imports", "calls", "contains", "references", "extends",
    "implements", "semantically_similar_to",
])


def _extraction(nodes, edges):
    return {
        "nodes": nodes,
        "edges": edges,
        "input_tokens": 0,
        "output_tokens": 0,
    }


# ── Property tests ──────────────────────────────────────────────────────────

@given(st.lists(_node, min_size=0, max_size=20))
@settings(max_examples=50)
def test_build_never_crashes_on_valid_nodes(nodes):
    """build_from_json should handle any list of valid nodes without crashing."""
    # Deduplicate IDs
    seen = set()
    unique_nodes = []
    for n in nodes:
        if n["id"] not in seen:
            seen.add(n["id"])
            unique_nodes.append(n)
    ext = _extraction(unique_nodes, [])
    G = build_from_json(ext)
    assert G.number_of_nodes() == len(unique_nodes)


@given(
    st.lists(_node, min_size=2, max_size=15),
    st.data(),
)
@settings(max_examples=50)
def test_build_with_random_edges(nodes, data):
    """build_from_json should handle random edges between existing nodes."""
    seen = set()
    unique_nodes = []
    for n in nodes:
        if n["id"] not in seen:
            seen.add(n["id"])
            unique_nodes.append(n)
    assume(len(unique_nodes) >= 2)

    ids = [n["id"] for n in unique_nodes]
    num_edges = data.draw(st.integers(min_value=0, max_value=len(ids) * 2))
    edges = []
    for _ in range(num_edges):
        src = data.draw(st.sampled_from(ids))
        tgt = data.draw(st.sampled_from(ids))
        if src != tgt:
            edges.append({
                "source": src,
                "target": tgt,
                "relation": data.draw(_relation),
                "confidence": data.draw(_confidence),
                "source_file": data.draw(_source_file),
            })

    ext = _extraction(unique_nodes, edges)
    G = build_from_json(ext)
    assert G.number_of_nodes() == len(unique_nodes)


@given(st.lists(_node, min_size=3, max_size=15))
@settings(max_examples=30)
def test_cluster_never_crashes(nodes):
    """cluster() should handle any valid graph without crashing."""
    seen = set()
    unique_nodes = []
    for n in nodes:
        if n["id"] not in seen:
            seen.add(n["id"])
            unique_nodes.append(n)
    assume(len(unique_nodes) >= 3)

    # Build a connected graph
    edges = []
    ids = [n["id"] for n in unique_nodes]
    for i in range(len(ids) - 1):
        edges.append({
            "source": ids[i],
            "target": ids[i + 1],
            "relation": "references",
            "confidence": "EXTRACTED",
            "source_file": unique_nodes[i]["source_file"],
        })

    ext = _extraction(unique_nodes, edges)
    G = build_from_json(ext)
    communities = cluster(G)
    # Every node should be in exactly one community
    all_assigned = set()
    for node_list in communities.values():
        all_assigned.update(node_list)
    assert all_assigned == set(G.nodes())


@given(st.dictionaries(
    keys=st.text(min_size=1, max_size=10),
    values=st.one_of(st.none(), st.integers(), st.text(max_size=20), st.lists(st.integers(), max_size=3)),
    max_size=10,
))
@settings(max_examples=50)
def test_validate_never_crashes_on_garbage(data):
    """validate_extraction should return errors, never crash, on random dicts."""
    errors = validate_extraction(data)
    assert isinstance(errors, list)


@given(st.one_of(st.none(), st.integers(), st.text(max_size=20), st.lists(st.none(), max_size=3)))
@settings(max_examples=30)
def test_validate_rejects_non_dict(data):
    """validate_extraction should reject non-dict input."""
    errors = validate_extraction(data)
    assert len(errors) > 0
