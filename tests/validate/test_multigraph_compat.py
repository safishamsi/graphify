from __future__ import annotations

import networkx as nx

from graphify.multigraph_compat import (
    CapabilityCheck,
    MultigraphCapabilityResult,
    probe_multigraph_capabilities,
    require_multigraph_capabilities,
)


def test_probe_multigraph_capabilities_passes_current_runtime() -> None:
    result = probe_multigraph_capabilities()

    assert result.ok, result.error_message()
    assert result.python_version
    assert result.networkx_version
    assert {check.name for check in result.checks} == {
        "keyed_parallel_edges",
        "node_link_edges_links_round_trip",
        "duplicate_key_overwrite_semantics",
        "reserved_key_attr_rejected",
        "remove_edges_from_two_tuple_semantics",
        "to_undirected_preserves_multigraph_type",
    }


def test_require_multigraph_capabilities_returns_result() -> None:
    result = require_multigraph_capabilities()

    assert result.ok


def test_failure_message_is_actionable() -> None:
    result = MultigraphCapabilityResult(
        python_version="3.10.0",
        networkx_version="0.0",
        checks=(CapabilityCheck("node_link_edges_links_round_trip", False, "boom"),),
    )

    message = result.error_message()

    assert "--multigraph requires NetworkX keyed MultiDiGraph node-link" in message
    assert "Default simple graph mode remains available" in message
    assert "node_link_edges_links_round_trip: boom" in message


def test_networkx_duplicate_key_overwrite_trap_is_real() -> None:
    graph = nx.MultiDiGraph()

    graph.add_edge("a", "b", key="same", relation="first")
    graph.add_edge("a", "b", key="same", relation="second")

    assert graph.number_of_edges("a", "b") == 1
    assert graph["a"]["b"]["same"]["relation"] == "second"
