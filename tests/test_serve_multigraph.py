"""MultiDiGraph display tests for serve.py surfaces (PR 5 first-edge-only gate).

These verify that serve.py's read/query/path surfaces never collapse parallel
edges between two nodes to a single first-edge representative. Every surface
must show all relevant relationships or an explicit capped summary, while plain
DiGraph output stays unchanged in substance (single relation per pair, no
``(+K more)`` marker).
"""

from __future__ import annotations

import re

import networkx as nx

from graphify.serve import (
    _bfs,
    _neighbors_text,
    _query_graph_text,
    _shortest_path_text,
    _subgraph_to_text,
)

# Pattern for the capped-summary marker, e.g. "(+3 more, 6 total)".
_CAPPED_MARKER = re.compile(r"\(\+\d+ more, \d+ total\)")


def _multidigraph_hop(
    relations: list[str], *, confidence: str = "EXTRACTED"
) -> nx.MultiDiGraph:
    """Build A(Alpha) -> B(Beta) with one parallel edge per supplied relation."""
    graph = nx.MultiDiGraph()
    graph.add_node("a", label="Alpha", source_file="a.py", source_location="L1", community=0)
    graph.add_node("b", label="Beta", source_file="b.py", source_location="L1", community=0)
    for index, relation in enumerate(relations):
        graph.add_edge(
            "a", "b", key=f"{relation}-{index}", relation=relation, confidence=confidence
        )
    return graph


# ---------------------------------------------------------------------------
# 1. query/subgraph text shows all relations on a multi-relation hop
# ---------------------------------------------------------------------------


def test_query_text_multigraph_shows_all_relations():
    """A hop A->B carrying calls/imports/contains shows ALL three, not just the
    first parallel edge."""
    graph = _multidigraph_hop(["calls", "imports", "contains"])
    nodes, edges = _bfs(graph, ["a"], depth=1)

    text = _subgraph_to_text(graph, nodes, edges)

    # Exactly one EDGE line for the pair (bundled, not one line per parallel edge)
    edge_lines = [line for line in text.splitlines() if line.startswith("EDGE ")]
    assert len(edge_lines) == 1, edge_lines
    edge_line = edge_lines[0]
    assert "calls" in edge_line
    assert "imports" in edge_line
    assert "contains" in edge_line
    # Three relations fit under the default cap of 3 -> no capped marker
    assert not _CAPPED_MARKER.search(edge_line)


def test_query_graph_text_multigraph_end_to_end_shows_all_relations():
    """Full _query_graph_text pipeline (the path query_graph MCP tool uses) shows
    every parallel relation for the matched hop."""
    graph = _multidigraph_hop(["calls", "imports", "contains"])

    text = _query_graph_text(graph, "Alpha", mode="bfs", depth=1)

    assert "No matching nodes found." not in text
    edge_lines = [line for line in text.splitlines() if line.startswith("EDGE ")]
    assert len(edge_lines) == 1, edge_lines
    assert "calls" in edge_lines[0]
    assert "imports" in edge_lines[0]
    assert "contains" in edge_lines[0]


def test_subgraph_to_text_directional_isolation():
    """The directional EDGE arrow must report only the forward (u->v) relations.

    With A->B 'calls' and B->A 'imports', the A-->B line shows 'calls' and NOT
    'imports', and the B-->A line shows 'imports' and NOT 'calls'. Without
    directed_only=True the envelope would merge the reverse edge into both lines.
    """
    graph = nx.MultiDiGraph()
    graph.add_node("a", label="Alpha")
    graph.add_node("b", label="Beta")
    graph.add_edge("a", "b", key="k1", relation="calls", confidence="EXTRACTED")
    graph.add_edge("b", "a", key="k2", relation="imports", confidence="EXTRACTED")

    text = _subgraph_to_text(graph, {"a", "b"}, [("a", "b"), ("b", "a")])

    ab_line = next(line for line in text.splitlines() if line.startswith("EDGE Alpha "))
    ba_line = next(line for line in text.splitlines() if line.startswith("EDGE Beta "))
    assert "calls" in ab_line and "imports" not in ab_line, ab_line
    assert "imports" in ba_line and "calls" not in ba_line, ba_line


def test_subgraph_to_text_single_relation_format_pinned():
    """Pin the EXACT single-relation EDGE line so the historical
    ``--{rel} [{conf} context={ctx}]-->`` square-bracket format cannot silently
    regress (it must match path/explain and any downstream EDGE-line parser)."""
    graph = nx.DiGraph()
    graph.add_node("a", label="alpha()")
    graph.add_node("b", label="beta()")
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED", context="call")

    text = _subgraph_to_text(graph, {"a", "b"}, [("a", "b")])

    edge_line = next(line for line in text.splitlines() if line.startswith("EDGE "))
    assert edge_line == "EDGE alpha() --calls [EXTRACTED context=call]--> beta()"

    # And the no-context variant keeps the bare [conf] bracket group.
    graph2 = nx.DiGraph()
    graph2.add_node("a", label="alpha")
    graph2.add_node("b", label="beta")
    graph2.add_edge("a", "b", relation="uses", confidence="INFERRED")
    line2 = next(
        line
        for line in _subgraph_to_text(graph2, {"a", "b"}, [("a", "b")]).splitlines()
        if line.startswith("EDGE ")
    )
    assert line2 == "EDGE alpha --uses [INFERRED]--> beta"


# ---------------------------------------------------------------------------
# 2. get_neighbors bundles parallel edges to one neighbor
# ---------------------------------------------------------------------------


def test_get_neighbors_multigraph_bundles_parallel_edges():
    """A node with 3 parallel edges to one neighbor lists that neighbor ONCE with
    all relations bundled, never 3 lines and never first-edge-only."""
    graph = _multidigraph_hop(["calls", "imports", "contains"])

    text = _neighbors_text(graph, "Alpha")

    neighbor_lines = [line for line in text.splitlines() if line.strip().startswith("-->")]
    assert len(neighbor_lines) == 1, neighbor_lines
    line = neighbor_lines[0]
    assert "Beta" in line
    assert "calls" in line
    assert "imports" in line
    assert "contains" in line


def test_get_neighbors_multigraph_directional_isolation():
    """Outgoing (-->) and incoming (<--) lines bundle only their own direction:
    a->b 'calls' must not leak into the <-- incoming line and vice versa."""
    graph = nx.MultiDiGraph()
    graph.add_node("a", label="Alpha")
    graph.add_node("b", label="Beta")
    graph.add_edge("a", "b", key="k1", relation="calls", confidence="EXTRACTED")
    graph.add_edge("a", "b", key="k2", relation="imports", confidence="EXTRACTED")
    graph.add_edge("b", "a", key="k3", relation="returns", confidence="INFERRED")

    text = _neighbors_text(graph, "Alpha")

    out_line = next(line for line in text.splitlines() if line.strip().startswith("-->"))
    in_line = next(line for line in text.splitlines() if line.strip().startswith("<--"))
    # Outgoing bundle: calls + imports, NOT returns
    assert "calls" in out_line and "imports" in out_line
    assert "returns" not in out_line
    # Incoming bundle: returns only, NOT the outgoing relations
    assert "returns" in in_line
    assert "calls" not in in_line and "imports" not in in_line


def test_get_neighbors_single_relation_format_pinned():
    """Pin the EXACT single-relation neighbor lines so the historical
    ``[rel] [conf]`` two-bracket form cannot regress to the envelope ``(conf)``
    parens form — MCP get_neighbors must stay consistent with path/explain."""
    graph = nx.DiGraph()
    graph.add_node("a", label="alpha")
    graph.add_node("b", label="beta")
    graph.add_node("c", label="gamma")
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    graph.add_edge("c", "a", relation="imports", confidence="INFERRED")

    text = _neighbors_text(graph, "alpha")

    out_line = next(line for line in text.splitlines() if line.strip().startswith("-->"))
    in_line = next(line for line in text.splitlines() if line.strip().startswith("<--"))
    assert out_line == "  --> beta [calls] [EXTRACTED]"
    assert in_line == "  <-- gamma [imports] [INFERRED]"

    # No-confidence variant keeps the empty second bracket group.
    graph2 = nx.DiGraph()
    graph2.add_node("a", label="a")
    graph2.add_node("b", label="b")
    graph2.add_edge("a", "b", relation="rel")
    line2 = next(
        line
        for line in _neighbors_text(graph2, "a").splitlines()
        if line.strip().startswith("-->")
    )
    assert line2 == "  --> b [rel] []"


def test_get_neighbors_multigraph_relation_filter_checks_all_parallel():
    """relation_filter matches a relation even when it is on a non-first parallel
    edge (first-edge-only filtering would miss it)."""
    graph = _multidigraph_hop(["calls", "imports", "contains"])

    # "contains" is not the first sorted relation; filter must still surface it.
    text = _neighbors_text(graph, "Alpha", relation_filter="contains")

    neighbor_lines = [line for line in text.splitlines() if line.strip().startswith("-->")]
    assert len(neighbor_lines) == 1, neighbor_lines
    assert "Beta" in neighbor_lines[0]

    # A relation present on no edge filters the neighbor out entirely.
    empty = _neighbors_text(graph, "Alpha", relation_filter="nonexistent")
    assert not [line for line in empty.splitlines() if line.strip().startswith("-->")]


# ---------------------------------------------------------------------------
# 3. shortest_path shows bundled hops
# ---------------------------------------------------------------------------


def test_shortest_path_multigraph_shows_bundled_hops():
    """A path hop carrying multiple parallel relations shows the bundle per hop,
    not a single first-edge representative."""
    graph = nx.MultiDiGraph()
    graph.add_node("a", label="Alpha", source_file="a.py", community=0)
    graph.add_node("b", label="Beta", source_file="b.py", community=0)
    graph.add_node("c", label="Gamma", source_file="c.py", community=0)
    for index, relation in enumerate(["calls", "imports", "contains"]):
        graph.add_edge("a", "b", key=f"{relation}-{index}", relation=relation, confidence="EXTRACTED")
    graph.add_edge("b", "c", key="uses-0", relation="uses", confidence="EXTRACTED")

    text = _shortest_path_text(graph, "Alpha", "Gamma")

    assert "Shortest path" in text
    # The A->B hop must show all three parallel relations.
    assert "calls" in text
    assert "imports" in text
    assert "contains" in text
    assert "uses" in text  # the B->C hop


def test_shortest_path_single_relation_format_pinned():
    """Pin the EXACT single-relation hop format ``--{rel} [{conf}]-->`` so it
    cannot regress to the envelope ``(conf)`` parens form."""
    graph = nx.DiGraph()
    graph.add_node("a", label="alpha")
    graph.add_node("b", label="beta")
    graph.add_node("c", label="gamma")
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    graph.add_edge("b", "c", relation="imports", confidence="INFERRED")

    text = _shortest_path_text(graph, "alpha", "gamma")

    assert text == (
        "Shortest path (2 hops):\n"
        "  alpha --calls [EXTRACTED]--> beta --imports [INFERRED]--> gamma"
    )

    # No-confidence hop drops the confidence bracket entirely (historical form).
    graph2 = nx.DiGraph()
    graph2.add_node("a", label="a")
    graph2.add_node("b", label="b")
    graph2.add_edge("a", "b", relation="rel")
    assert _shortest_path_text(graph2, "a", "b") == (
        "Shortest path (1 hops):\n  a --rel--> b"
    )


# ---------------------------------------------------------------------------
# 4. capped summary for a noisy pair (bounded output)
# ---------------------------------------------------------------------------


def test_query_capped_summary_for_noisy_pair():
    """A pair with 6 parallel relations renders the capped '(+K more, N total)'
    form, proving output is bounded rather than unbounded enumeration."""
    graph = _multidigraph_hop(["alpha", "beta", "gamma", "delta", "epsilon", "zeta"])
    nodes, edges = _bfs(graph, ["a"], depth=1)

    text = _subgraph_to_text(graph, nodes, edges)

    edge_line = next(line for line in text.splitlines() if line.startswith("EDGE "))
    match = _CAPPED_MARKER.search(edge_line)
    assert match, edge_line
    # N total counts edge records (6), not unique relations.
    assert "6 total" in match.group(0)
    # First cap=3 sorted relations are shown, the rest summarised as "+K more".
    assert "alpha" in edge_line and "beta" in edge_line and "delta" in edge_line
    assert "+3 more" in edge_line

    # get_neighbors applies the same bounded cap.
    neighbors = _neighbors_text(graph, "Alpha")
    nbr_line = next(line for line in neighbors.splitlines() if line.strip().startswith("-->"))
    assert _CAPPED_MARKER.search(nbr_line), nbr_line


# ---------------------------------------------------------------------------
# 5. simple-graph regression gate
# ---------------------------------------------------------------------------


def _simple_digraph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("a", label="Alpha", source_file="a.py", source_location="L1", community=0)
    graph.add_node("b", label="Beta", source_file="b.py", source_location="L1", community=0)
    graph.add_node("c", label="Gamma", source_file="c.py", source_location="L1", community=0)
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED", context="call")
    graph.add_edge("b", "c", relation="imports", confidence="EXTRACTED")
    return graph


def test_serve_simple_graph_output_regression():
    """A plain DiGraph produces single-relation-per-pair output across query,
    neighbors, and path surfaces with NO capped '(+K more)' marker — the
    simple-graph regression gate."""
    graph = _simple_digraph()

    # --- subgraph / query text ---
    nodes, edges = _bfs(graph, ["a"], depth=2)
    sub = _subgraph_to_text(graph, nodes, edges)
    assert not _CAPPED_MARKER.search(sub)
    ab_edge = next(line for line in sub.splitlines() if line.startswith("EDGE Alpha "))
    assert "calls" in ab_edge
    # Single relation per pair: no comma-joined relation list on the hop.
    relation_segment = ab_edge.split("--", 1)[1].split("-->", 1)[0]
    assert "," not in relation_segment
    # Edge context is still emitted exactly as before.
    assert "context=call" in ab_edge

    # --- get_neighbors ---
    neighbors = _neighbors_text(graph, "Alpha")
    assert not _CAPPED_MARKER.search(neighbors)
    out_line = next(line for line in neighbors.splitlines() if line.strip().startswith("-->"))
    assert "Beta" in out_line and "calls" in out_line
    assert "," not in out_line.split("[", 1)[1]  # single relation in the bracket

    # --- shortest_path ---
    path = _shortest_path_text(graph, "Alpha", "Gamma")
    assert not _CAPPED_MARKER.search(path)
    assert "Shortest path (2 hops):" in path
    assert "calls" in path and "imports" in path


def test_serve_simple_graph_query_cli_text_unchanged():
    """The CLI-facing _query_graph_text path on a simple graph keeps its header
    and per-hop format (single relation, no capping)."""
    graph = _simple_digraph()
    text = _query_graph_text(graph, "Alpha", mode="bfs", depth=2)
    assert "Traversal: BFS depth=2" in text
    assert not _CAPPED_MARKER.search(text)
    assert "calls" in text
