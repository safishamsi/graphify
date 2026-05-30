"""Runtime compatibility probe for Graphify MultiDiGraph mode.

Verifies that the current NetworkX runtime supports the behaviors a future
opt-in --multigraph build will rely on. The probe is BEHAVIOR-based, not
version-based — both NX 3.4.2 (Py 3.10 lane) and NX 3.6.1+ (Py 3.11+ lane)
pass. The probe result is cached for the process lifetime via lru_cache.

No call sites added yet; downstream multigraph PRs will gate on
require_multigraph_capabilities() before enabling MDG mode.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
import sys
from typing import Any

import networkx as nx
from networkx.readwrite import json_graph


@dataclass(frozen=True)
class CapabilityCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class MultigraphCapabilityResult:
    python_version: str
    networkx_version: str
    checks: tuple[CapabilityCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def failed(self) -> tuple[CapabilityCheck, ...]:
        return tuple(check for check in self.checks if not check.ok)

    def error_message(self) -> str:
        if self.ok:
            return (
                "Graphify MultiDiGraph capability probe passed "
                f"(Python {self.python_version}, NetworkX {self.networkx_version})."
            )
        failed = "; ".join(f"{check.name}: {check.detail}" for check in self.failed)
        return (
            "error: --multigraph requires NetworkX keyed MultiDiGraph node-link "
            "round-trip support. "
            f"Detected Python {self.python_version}, NetworkX {self.networkx_version}. "
            f"Failed capability check(s): {failed}. "
            "Default simple graph mode remains available."
        )


def _check(name: str, func: Callable[[], bool | str]) -> CapabilityCheck:
    try:
        detail = func()
    except Exception as exc:
        return CapabilityCheck(name, False, f"{type(exc).__name__}: {exc}")
    if detail is True:
        return CapabilityCheck(name, True, "ok")
    if isinstance(detail, str):
        return CapabilityCheck(name, False, detail)
    return CapabilityCheck(name, False, f"unexpected result {detail!r}")


def _build_probe_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("a", label="A")
    graph.add_node("b", label="B")
    graph.add_edge("a", "b", key="calls:a.py:L1", relation="calls", source_file="a.py")
    graph.add_edge("a", "b", key="imports:a.py:L2", relation="imports", source_file="a.py")
    return graph


def _probe_keyed_parallel_edges() -> bool | str:
    graph = _build_probe_graph()
    if not graph.is_multigraph() or not graph.is_directed():
        return f"probe graph type was {type(graph).__name__}"
    if graph.number_of_edges("a", "b") != 2:
        return f"expected 2 keyed parallel edges, got {graph.number_of_edges('a', 'b')}"
    keys = set(graph["a"]["b"].keys())
    expected = {"calls:a.py:L1", "imports:a.py:L2"}
    if keys != expected:
        return f"expected keys {sorted(expected)}, got {sorted(keys)}"
    return True


def _probe_node_link_round_trip() -> bool | str:
    graph = _build_probe_graph()
    data = json_graph.node_link_data(graph, edges="links")
    if data.get("multigraph") is not True:
        return f"serialized multigraph flag was {data.get('multigraph')!r}"
    if data.get("directed") is not True:
        return f"serialized directed flag was {data.get('directed')!r}"
    links = data.get("links")
    if not isinstance(links, list) or len(links) != 2:
        length = 0 if not isinstance(links, list) else len(links)
        return f"serialized links length was {length}"
    serialized_keys: set[str] = set()
    for edge in links:
        if isinstance(edge, dict):
            edge_key = edge.get("key")
            if isinstance(edge_key, str):
                serialized_keys.add(edge_key)
    expected = {"calls:a.py:L1", "imports:a.py:L2"}
    if serialized_keys != expected:
        return f"serialized keys {sorted(serialized_keys)} did not match {sorted(expected)}"
    loaded = json_graph.node_link_graph(data, edges="links")
    if not isinstance(loaded, nx.MultiDiGraph):
        return f"round-trip graph type was {type(loaded).__name__}"
    if loaded.number_of_edges("a", "b") != 2:
        return f"round-trip edge count was {loaded.number_of_edges('a', 'b')}"
    loaded_keys = set(loaded["a"]["b"].keys())
    if loaded_keys != expected:
        return f"round-trip keys {sorted(loaded_keys)} did not match {sorted(expected)}"
    return True


def _probe_duplicate_key_overwrite_semantics() -> bool | str:
    graph = nx.MultiDiGraph()
    graph.add_edge("x", "y", key="same", marker="first")
    graph.add_edge("x", "y", key="same", marker="second")
    edges = list(graph.edges(keys=True, data=True))
    if len(edges) != 1:
        return f"expected one edge after duplicate-key add, got {len(edges)}"
    if edges[0][3].get("marker") != "second":
        return f"expected second attr overwrite, got {edges[0][3].get('marker')!r}"
    return True


def _probe_reserved_key_attr_rejected() -> bool | str:
    """Verify the Python language guarantee that NetworkX add_edge inherits.

    Python forbids passing the same keyword argument twice — once explicitly
    and once via **kwargs. This probe confirms that protection still applies
    to nx.MultiDiGraph.add_edge: a future loader that builds attrs from JSON
    will be reliably protected from accidentally setting `key` via attrs while
    also passing `key=` explicitly.

    The probe always passes on any Python 3.x version. Its purpose is to
    document the invariant explicitly in the probe suite so that if a future
    Python version relaxes this rule (extremely unlikely), the probe surfaces
    the regression.
    """
    graph = nx.MultiDiGraph()
    attrs: dict[str, Any] = {"key": "attr-key", "relation": "calls"}
    try:
        graph.add_edge("a", "b", key="schema-key", **attrs)
    except TypeError:
        return True
    return "add_edge accepted duplicate key keyword and attr; loader must not rely on this"


def _probe_remove_edges_from_two_tuple_semantics() -> bool | str:
    graph = nx.MultiDiGraph()
    graph.add_edge("a", "b", key="one")
    graph.add_edge("a", "b", key="two")
    graph.remove_edges_from([("a", "b")])
    remaining = graph.number_of_edges("a", "b")
    if remaining != 1:
        return f"expected one remaining edge after two-tuple removal, got {remaining}"
    return True


def _probe_to_undirected_preserves_multigraph_type() -> bool | str:
    graph = _build_probe_graph()
    undirected = graph.to_undirected()
    undirected_view = graph.to_undirected(as_view=True)
    if not isinstance(undirected, nx.MultiGraph):
        return f"to_undirected() returned {type(undirected).__name__}"
    if not isinstance(undirected_view, nx.MultiGraph):
        return f"to_undirected(as_view=True) returned {type(undirected_view).__name__}"
    return True


@lru_cache(maxsize=1)
def probe_multigraph_capabilities() -> MultigraphCapabilityResult:
    checks = (
        _check("keyed_parallel_edges", _probe_keyed_parallel_edges),
        _check("node_link_edges_links_round_trip", _probe_node_link_round_trip),
        _check("duplicate_key_overwrite_semantics", _probe_duplicate_key_overwrite_semantics),
        _check("reserved_key_attr_rejected", _probe_reserved_key_attr_rejected),
        _check(
            "remove_edges_from_two_tuple_semantics",
            _probe_remove_edges_from_two_tuple_semantics,
        ),
        _check(
            "to_undirected_preserves_multigraph_type",
            _probe_to_undirected_preserves_multigraph_type,
        ),
    )
    return MultigraphCapabilityResult(
        python_version=(
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ),
        networkx_version=nx.__version__,
        checks=checks,
    )


def require_multigraph_capabilities() -> MultigraphCapabilityResult:
    result = probe_multigraph_capabilities()
    if not result.ok:
        raise RuntimeError(result.error_message())
    return result
