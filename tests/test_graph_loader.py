"""Tests for graphify.graph_loader — schema-aware graph loading.

Seven required PR 2 scenarios from the Wave 3 handoff guardrails.
"""

from __future__ import annotations

from unittest.mock import patch

import networkx as nx
import pytest

from graphify.graph_loader import GRAPHIFY_PROFILE_KEY, load_graph

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NODES = [
    {"id": "a", "label": "A", "file_type": "code", "source_file": "a.py"},
    {"id": "b", "label": "B", "file_type": "code", "source_file": "b.py"},
]

_SIMPLE_EDGE = {
    "source": "a",
    "target": "b",
    "relation": "calls",
    "confidence": "EXTRACTED",
    "confidence_score": 1.0,
    "source_file": "a.py",
    "weight": 1.0,
}

_KEYED_EDGE = {**_SIMPLE_EDGE, "key": "calls:a.py:L1"}

_KEYED_EDGE_2 = {
    "source": "a",
    "target": "b",
    "relation": "imports",
    "confidence": "EXTRACTED",
    "confidence_score": 1.0,
    "source_file": "a.py",
    "key": "imports:a.py:L5",
    "weight": 1.0,
}


def _simple_links() -> dict:
    """Legacy simple JSON using 'links' key."""
    return {"nodes": _NODES, "links": [_SIMPLE_EDGE]}


def _simple_edges() -> dict:
    """Modern simple JSON using 'edges' key."""
    return {"nodes": _NODES, "edges": [_SIMPLE_EDGE]}


def _multigraph_data() -> dict:
    """Valid multigraph node-link JSON with two keyed parallel edges."""
    return {
        "multigraph": True,
        "nodes": _NODES,
        "links": [_KEYED_EDGE, _KEYED_EDGE_2],
    }


def _multigraph_missing_keys() -> dict:
    """Multigraph JSON where edges lack 'key' fields."""
    edge_no_key = {k: v for k, v in _SIMPLE_EDGE.items() if k != "key"}
    return {"multigraph": True, "nodes": _NODES, "links": [edge_no_key]}


# ---------------------------------------------------------------------------
# Scenario 1: legacy 'links' loads as nx.Graph
# ---------------------------------------------------------------------------


def test_legacy_links_loads_as_simple_graph():
    G = load_graph(_simple_links())
    assert type(G) is nx.Graph
    assert not G.is_multigraph()
    assert G.number_of_nodes() == 2
    assert G.number_of_edges() == 1


# ---------------------------------------------------------------------------
# Scenario 2: modern 'edges' loads as nx.Graph
# ---------------------------------------------------------------------------


def test_modern_edges_loads_as_simple_graph():
    G = load_graph(_simple_edges())
    assert type(G) is nx.Graph
    assert not G.is_multigraph()
    assert G.number_of_edges() == 1


# ---------------------------------------------------------------------------
# Scenario 3: valid multigraph JSON with keyed parallel edges → nx.MultiDiGraph
# ---------------------------------------------------------------------------


def test_valid_multigraph_loads_as_multidigraph():
    G = load_graph(_multigraph_data())
    assert type(G) is nx.MultiDiGraph
    assert G.is_multigraph()
    assert G.number_of_nodes() == 2
    assert G.number_of_edges() == 2  # both parallel edges preserved


# ---------------------------------------------------------------------------
# Scenario 4: malformed multigraph (missing keys) repairs explicitly, not silently
# ---------------------------------------------------------------------------


def test_malformed_multigraph_missing_keys_repairs_explicitly(capsys):
    G = load_graph(_multigraph_missing_keys())
    # Must produce a MultiDiGraph (not silently fall back to simple)
    assert type(G) is nx.MultiDiGraph
    assert G.number_of_edges() == 1
    # Must warn to stderr
    captured = capsys.readouterr()
    assert "missing" in captured.err.lower() or "key" in captured.err.lower()


# ---------------------------------------------------------------------------
# Scenario 5: edge 'key' is stripped from attrs — not stored as an edge attribute
# ---------------------------------------------------------------------------


def test_schema_key_stripped_from_edge_attrs():
    G = load_graph(_multigraph_data())
    assert isinstance(G, nx.MultiDiGraph)
    for u, v, k, data in G.edges(keys=True, data=True):
        assert "key" not in data, (
            f"Edge ({u},{v},key={k!r}) must not store 'key' inside its attrs dict"
        )


# ---------------------------------------------------------------------------
# Scenario 6: G.graph["graphify_profile"] is present after load
# ---------------------------------------------------------------------------


def test_graph_profile_metadata_round_trips():
    G = load_graph(_simple_links())
    assert GRAPHIFY_PROFILE_KEY in G.graph
    profile = G.graph[GRAPHIFY_PROFILE_KEY]
    assert isinstance(profile, dict)
    assert "graph_type" in profile


def test_graph_profile_type_for_multidigraph():
    G = load_graph(_multigraph_data())
    assert G.graph[GRAPHIFY_PROFILE_KEY]["graph_type"] == "multidigraph"


def test_graph_profile_type_for_simple():
    G = load_graph(_simple_links())
    assert G.graph[GRAPHIFY_PROFILE_KEY]["graph_type"] == "simple"


# ---------------------------------------------------------------------------
# Scenario 7: capability probe failure raises clearly; simple loading unaffected
# ---------------------------------------------------------------------------


def test_capability_probe_failure_raises_clear_error():
    with patch(
        "graphify.graph_loader.require_multigraph_capabilities",
        side_effect=RuntimeError("MultiDiGraph not supported: simulated failure"),
    ):
        with pytest.raises(RuntimeError, match="MultiDiGraph not supported"):
            load_graph(_multigraph_data(), require_capabilities=True)


def test_capability_probe_failure_does_not_affect_simple_load():
    with patch(
        "graphify.graph_loader.require_multigraph_capabilities",
        side_effect=RuntimeError("should not be called"),
    ):
        # Simple JSON must not trigger the capability probe at all
        G = load_graph(_simple_links(), require_capabilities=True)
    assert type(G) is nx.Graph


# ---------------------------------------------------------------------------
# Blocker 2: missing-key repair must preserve distinct parallel edges
# ---------------------------------------------------------------------------


def _two_missing_key_parallel_edges() -> dict:
    """Multigraph with two missing-key edges sharing relation/file but different attrs."""
    return {
        "multigraph": True,
        "nodes": _NODES,
        "links": [
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "source_file": "a.py",
                "confidence": "EXTRACTED",
                "weight": 1.0,
                "context": "one",
            },
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "source_file": "a.py",
                "confidence": "EXTRACTED",
                "weight": 1.0,
                "context": "two",
            },
        ],
    }


def test_missing_key_repair_preserves_distinct_parallel_edges(capsys):
    G = load_graph(_two_missing_key_parallel_edges())
    assert type(G) is nx.MultiDiGraph
    assert G.number_of_edges() == 2, (
        f"Both missing-key parallel edges must survive repair; got {G.number_of_edges()}"
    )
    captured = capsys.readouterr()
    assert "missing" in captured.err.lower() or "key" in captured.err.lower()


# ---------------------------------------------------------------------------
# Blocker 3: simple loader must respect serialized directedness
# ---------------------------------------------------------------------------


def test_directed_true_loads_as_digraph():
    data = {
        "directed": True,
        "multigraph": False,
        "nodes": _NODES,
        "edges": [_SIMPLE_EDGE],
    }
    G = load_graph(data)
    assert type(G) is nx.DiGraph


def test_directed_false_explicitly_loads_as_graph():
    data = {
        "directed": False,
        "multigraph": False,
        "nodes": _NODES,
        "edges": [_SIMPLE_EDGE],
    }
    G = load_graph(data)
    assert type(G) is nx.Graph


def test_directed_true_profile_graph_type():
    data = {
        "directed": True,
        "multigraph": False,
        "nodes": _NODES,
        "edges": [_SIMPLE_EDGE],
    }
    G = load_graph(data)
    assert G.graph[GRAPHIFY_PROFILE_KEY]["graph_type"] == "digraph"


# ---------------------------------------------------------------------------
# Blocker 4: malformed JSON must fail cleanly or skip under documented policy
# ---------------------------------------------------------------------------


def test_non_dict_edge_entries_are_skipped():
    data = {"nodes": _NODES, "edges": ["not-a-dict", None, 42]}
    G = load_graph(data)
    assert G.number_of_edges() == 0


def test_edges_value_not_a_list_raises():
    data = {"nodes": _NODES, "edges": "not-a-list"}
    with pytest.raises((TypeError, ValueError)):
        load_graph(data)


def test_non_dict_graphify_profile_is_ignored():
    data = {
        "nodes": _NODES,
        "edges": [_SIMPLE_EDGE],
        GRAPHIFY_PROFILE_KEY: "bad-profile",
    }
    G = load_graph(data)
    assert isinstance(G.graph[GRAPHIFY_PROFILE_KEY], dict)
    assert "graph_type" in G.graph[GRAPHIFY_PROFILE_KEY]


def test_edge_missing_source_or_target_skipped():
    data = {
        "nodes": _NODES,
        "edges": [
            {"target": "b", "relation": "calls"},
            {"source": "a", "relation": "calls"},
        ],
    }
    G = load_graph(data)
    assert G.number_of_edges() == 0


# ---------------------------------------------------------------------------
# Non-string multigraph key values must raise before NetworkX sees them
# ---------------------------------------------------------------------------


def _multigraph_with_key(key_value: object) -> dict:
    return {
        "multigraph": True,
        "nodes": _NODES,
        "links": [{**_SIMPLE_EDGE, "key": key_value}],
    }


def test_multigraph_list_key_raises():
    with pytest.raises((TypeError, ValueError)):
        load_graph(_multigraph_with_key(["bad"]))


def test_multigraph_dict_key_raises():
    with pytest.raises((TypeError, ValueError)):
        load_graph(_multigraph_with_key({"bad": 1}))


def test_multigraph_int_key_raises():
    with pytest.raises((TypeError, ValueError)):
        load_graph(_multigraph_with_key(123))
