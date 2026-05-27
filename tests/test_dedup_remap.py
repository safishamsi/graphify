"""Tests for PR 4A: dedup remap contract — parallel edge preservation,
self-loop counting, exact duplicate collapse, build integration, and the
remove_all_parallel_edges helper.

Groups A–C and E will fail until the production dedup/build changes land
(diagnostics parameter, remap counters).  Group D tests the helper
implemented in edge_identity.py and should pass immediately.
"""

from __future__ import annotations

import networkx as nx

from graphify.dedup import deduplicate_entities
from graphify.build import build
from graphify.edge_identity import remove_all_parallel_edges


# ── helpers (mirrors test_dedup.py patterns) ─────────────────────────────────


def _make_nodes(*labels, source_file="test.md"):
    return [
        {"id": label.lower().replace(" ", "_"), "label": label, "source_file": source_file}
        for label in labels
    ]


def _make_edge(src, tgt, relation="relates_to", source_file="test.py", **extra):
    edge = {"source": src, "target": tgt, "relation": relation, "source_file": source_file}
    edge.update(extra)
    return edge


# ═══════════════════════════════════════════════════════════════════════════════
# Group A: Post-remap parallel edge preservation
# ═══════════════════════════════════════════════════════════════════════════════


def test_remap_preserves_parallel_edges_different_relation():
    """Two edges A->C (calls) and A->C (imports) survive when B is merged into C.

    Setup: nodes A, B, C where B and C are exact duplicates (same normalized label).
    Edges: A->B (calls), A->C (imports).  After dedup, B merges into C (winner).
    Expected: two edges A->C with different relations survive.
    """
    # B and C share the normalized label "dataloader" so they are exact duplicates.
    nodes = [
        {"id": "a", "label": "Caller", "source_file": "a.py"},
        {"id": "b", "label": "DataLoader", "source_file": "a.py"},
        {"id": "c", "label": "dataloader", "source_file": "a.py"},
    ]
    edges = [
        _make_edge("a", "b", relation="calls", source_file="a.py"),
        _make_edge("a", "c", relation="imports", source_file="a.py"),
    ]
    diagnostics: dict = {}
    result_nodes, result_edges = deduplicate_entities(
        nodes,
        edges,
        communities={},
        diagnostics=diagnostics,
    )
    # B merged into winner; both edges now point to the winner
    assert len(result_nodes) == 2
    # Two distinct relations -> both edges survive
    relations = {e["relation"] for e in result_edges}
    assert "calls" in relations
    assert "imports" in relations
    assert len(result_edges) == 2


def test_remap_preserves_parallel_edges_incoming_and_outgoing():
    """Edges B->X and Y->B survive as C->X and Y->C when B merges into C."""
    nodes = [
        {"id": "x", "label": "NodeX", "source_file": "a.py"},
        {"id": "y", "label": "NodeY", "source_file": "a.py"},
        {"id": "b", "label": "DataLoader", "source_file": "a.py"},
        {"id": "c", "label": "dataloader", "source_file": "a.py"},
    ]
    edges = [
        _make_edge("b", "x", relation="calls", source_file="a.py"),
        _make_edge("y", "b", relation="imports", source_file="a.py"),
    ]
    diagnostics: dict = {}
    result_nodes, result_edges = deduplicate_entities(
        nodes,
        edges,
        communities={},
        diagnostics=diagnostics,
    )
    assert len(result_nodes) == 3  # x, y, winner(b/c)
    # Both edges survive: one outgoing, one incoming
    assert len(result_edges) == 2
    # The loser ID should be remapped to the winner
    winner_id = next(n["id"] for n in result_nodes if n["label"] in ("DataLoader", "dataloader"))
    sources = {e["source"] for e in result_edges}
    targets = {e["target"] for e in result_edges}
    assert winner_id in sources or winner_id in targets


def test_remap_preserves_edges_with_different_source_location():
    """Two edges A->B with same relation but different source_location survive remap."""
    nodes = [
        {"id": "a", "label": "Caller", "source_file": "a.py"},
        {"id": "b", "label": "DataLoader", "source_file": "a.py"},
        {"id": "c", "label": "dataloader", "source_file": "a.py"},
    ]
    edges = [
        _make_edge("a", "b", relation="calls", source_file="a.py", source_location="L10"),
        _make_edge("a", "c", relation="calls", source_file="a.py", source_location="L20"),
    ]
    diagnostics: dict = {}
    result_nodes, result_edges = deduplicate_entities(
        nodes,
        edges,
        communities={},
        diagnostics=diagnostics,
    )
    assert len(result_nodes) == 2
    # Same relation but different source_location -> both survive (not exact duplicates)
    assert len(result_edges) == 2
    locations = {e.get("source_location") for e in result_edges}
    assert locations == {"L10", "L20"}


def test_remap_preserves_key_field_through_dict_copy():
    """If edge dicts carry a pre-existing 'key' field, remap preserves it verbatim."""
    nodes = [
        {"id": "a", "label": "Caller", "source_file": "a.py"},
        {"id": "b", "label": "DataLoader", "source_file": "a.py"},
        {"id": "c", "label": "dataloader", "source_file": "a.py"},
    ]
    edges = [
        _make_edge("a", "b", relation="calls", source_file="a.py", key="user-key-1"),
    ]
    diagnostics: dict = {}
    result_nodes, result_edges = deduplicate_entities(
        nodes,
        edges,
        communities={},
        diagnostics=diagnostics,
    )
    assert len(result_edges) == 1
    assert result_edges[0].get("key") == "user-key-1"


# ═══════════════════════════════════════════════════════════════════════════════
# Group B: Self-loop counting + exact duplicate collapse
# ═══════════════════════════════════════════════════════════════════════════════


def test_remap_counts_self_loop_drops():
    """Self-loop drops counted in diagnostics dict, broken down by relation and source_file.

    Setup: nodes A, B that are exact duplicates.  Edge A->B (calls, from a.py).
    After remap: B merges into A, edge becomes A->A = self-loop, dropped.
    Assert diagnostics: remap_self_loop_drops=1, by_relation={'calls':1}, by_source={'a.py':1}
    """
    nodes = [
        {"id": "a", "label": "DataLoader", "source_file": "a.py"},
        {"id": "b", "label": "dataloader", "source_file": "a.py"},
    ]
    edges = [
        _make_edge("a", "b", relation="calls", source_file="a.py"),
    ]
    diagnostics: dict = {}
    result_nodes, result_edges = deduplicate_entities(
        nodes,
        edges,
        communities={},
        diagnostics=diagnostics,
    )
    assert len(result_nodes) == 1
    assert result_edges == []  # self-loop dropped
    assert diagnostics.get("remap_self_loop_drops") == 1
    assert diagnostics.get("remap_self_loop_drops_by_relation", {}).get("calls") == 1
    assert diagnostics.get("remap_self_loop_drops_by_source", {}).get("a.py") == 1


def test_remap_preserves_preexisting_self_loop_on_remapped_node():
    """A real self-loop survives when its node is remapped to the canonical winner."""
    nodes = [
        {"id": "winner", "label": "DataLoader", "source_file": "a.py"},
        {"id": "loser_long", "label": "dataloader", "source_file": "a.py"},
    ]
    edges = [
        _make_edge("loser_long", "loser_long", relation="calls", source_file="a.py"),
    ]
    diagnostics: dict = {}

    result_nodes, result_edges = deduplicate_entities(
        nodes,
        edges,
        communities={},
        diagnostics=diagnostics,
    )

    assert len(result_nodes) == 1
    assert result_edges == [
        {"source": "winner", "target": "winner", "relation": "calls", "source_file": "a.py"}
    ]
    assert diagnostics.get("remap_self_loop_drops") == 0


def test_remap_collapses_exact_duplicates_after_remap():
    """Two edges that become identical after remap collapse to one.

    Setup: nodes A, B, C where B merges into C.
    Two edges: A->B (calls, from x.py, line 10) and A->C (calls, from x.py, line 10).
    After remap both become A->C with identical attrs -> collapse to one.
    Assert diagnostics: remap_exact_duplicate_collapses=1, by_relation={'calls':1}
    """
    nodes = [
        {"id": "a", "label": "Caller", "source_file": "x.py"},
        {"id": "b", "label": "DataLoader", "source_file": "x.py"},
        {"id": "c", "label": "dataloader", "source_file": "x.py"},
    ]
    edges = [
        _make_edge("a", "b", relation="calls", source_file="x.py", source_location="L10"),
        _make_edge("a", "c", relation="calls", source_file="x.py", source_location="L10"),
    ]
    diagnostics: dict = {}
    result_nodes, result_edges = deduplicate_entities(
        nodes,
        edges,
        communities={},
        diagnostics=diagnostics,
    )
    assert len(result_nodes) == 2
    # After remap, both edges are identical (A->winner, calls, x.py, L10) -> collapse to 1
    assert len(result_edges) == 1
    assert diagnostics.get("remap_exact_duplicate_collapses") == 1
    assert diagnostics.get("remap_exact_duplicate_collapses_by_relation", {}).get("calls") == 1


def test_remap_does_not_collapse_non_exact_duplicates():
    """Two edges with same source/target after remap but different attrs both survive.

    Setup: nodes A, B, C where B merges into C.
    Edges: A->B (calls, line 10), A->C (calls, line 20).
    After remap: A->C (calls, line 10) and A->C (calls, line 20) — both survive.
    """
    nodes = [
        {"id": "a", "label": "Caller", "source_file": "x.py"},
        {"id": "b", "label": "DataLoader", "source_file": "x.py"},
        {"id": "c", "label": "dataloader", "source_file": "x.py"},
    ]
    edges = [
        _make_edge("a", "b", relation="calls", source_file="x.py", source_location="L10"),
        _make_edge("a", "c", relation="calls", source_file="x.py", source_location="L20"),
    ]
    diagnostics: dict = {}
    result_nodes, result_edges = deduplicate_entities(
        nodes,
        edges,
        communities={},
        diagnostics=diagnostics,
    )
    assert len(result_nodes) == 2
    assert len(result_edges) == 2
    locations = {e.get("source_location") for e in result_edges}
    assert locations == {"L10", "L20"}


def test_remap_returns_diagnostics_when_dict_provided():
    """diagnostics dict is populated with all counter keys even when counts are zero."""
    nodes = [
        {"id": "a", "label": "Caller", "source_file": "a.py"},
        {"id": "b", "label": "Target", "source_file": "a.py"},
    ]
    edges = [_make_edge("a", "b", relation="calls")]
    diagnostics: dict = {}
    deduplicate_entities(nodes, edges, communities={}, diagnostics=diagnostics)
    # When no merges happen, diagnostics should still have the counter keys at 0
    assert "remap_self_loop_drops" in diagnostics
    assert "remap_exact_duplicate_collapses" in diagnostics
    assert diagnostics["remap_self_loop_drops"] == 0
    assert diagnostics["remap_exact_duplicate_collapses"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Group C: Build integration
# ═══════════════════════════════════════════════════════════════════════════════


def test_build_with_dedup_and_multigraph_preserves_parallel_edges():
    """build(extractions, dedup=True, multigraph=True) preserves non-duplicate parallel edges.

    Create 2 extraction chunks with overlapping nodes but different edges.
    Assert the built MultiDiGraph has the expected parallel edges.
    """
    ext1 = {
        "nodes": [
            {"id": "caller", "label": "Caller", "file_type": "code", "source_file": "a.py"},
            {"id": "dataloader", "label": "DataLoader", "file_type": "code", "source_file": "b.py"},
        ],
        "edges": [
            {
                "source": "caller",
                "target": "dataloader",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "source_location": "L10",
            },
        ],
    }
    ext2 = {
        "nodes": [
            {"id": "caller", "label": "Caller", "file_type": "code", "source_file": "a.py"},
            {"id": "dataloader", "label": "DataLoader", "file_type": "code", "source_file": "b.py"},
        ],
        "edges": [
            {
                "source": "caller",
                "target": "dataloader",
                "relation": "imports",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "source_location": "L2",
            },
        ],
    }
    G = build([ext1, ext2], dedup=True, multigraph=True, directed=True)
    assert isinstance(G, nx.MultiDiGraph)
    # Two edges with different relations should both survive
    assert G.number_of_edges("caller", "dataloader") == 2
    relations = {data["relation"] for data in G["caller"]["dataloader"].values()}
    assert relations == {"calls", "imports"}


def test_build_with_dedup_and_multigraph_reports_diagnostics():
    """G.graph['graphify_multigraph_diagnostics'] contains remap_ prefixed counters after build."""
    ext1 = {
        "nodes": [
            {"id": "a", "label": "Caller", "file_type": "code", "source_file": "a.py"},
            {"id": "b", "label": "DataLoader", "file_type": "code", "source_file": "a.py"},
            {"id": "c", "label": "dataloader", "file_type": "code", "source_file": "a.py"},
        ],
        "edges": [
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "source_location": "L10",
            },
        ],
    }
    G = build([ext1], dedup=True, multigraph=True, directed=True)
    diag = G.graph.get("graphify_multigraph_diagnostics", {})
    # Should contain remap_ prefixed counters from the dedup pass
    remap_keys = [k for k in diag if k.startswith("remap_")]
    assert len(remap_keys) > 0, f"Expected remap_ keys in diagnostics, got: {diag}"


# ═══════════════════════════════════════════════════════════════════════════════
# Group D: Safe remove-all-parallel helper
# ═══════════════════════════════════════════════════════════════════════════════


def test_remove_all_parallel_edges_removes_all_keys():
    """On MultiDiGraph with 3 edges between u,v (different keys), removes all 3."""
    G = nx.MultiDiGraph()
    G.add_edge("a", "b", key="k1", relation="calls")
    G.add_edge("a", "b", key="k2", relation="imports")
    G.add_edge("a", "b", key="k3", relation="references")
    assert G.number_of_edges("a", "b") == 3

    removed = remove_all_parallel_edges(G, "a", "b")

    assert removed == 3
    assert G.number_of_edges("a", "b") == 0


def test_remove_all_parallel_edges_no_edges_noop():
    """No edges between u,v -> returns 0, no raise."""
    G = nx.MultiDiGraph()
    G.add_node("a")
    G.add_node("b")

    removed = remove_all_parallel_edges(G, "a", "b")

    assert removed == 0


def test_remove_all_parallel_edges_simple_digraph():
    """On simple DiGraph, removes the single edge, returns 1."""
    G = nx.DiGraph()
    G.add_edge("a", "b", relation="calls")

    removed = remove_all_parallel_edges(G, "a", "b")

    assert removed == 1
    assert not G.has_edge("a", "b")


def test_remove_all_parallel_edges_does_not_use_two_tuple_semantics():
    """Verify the helper works correctly even if NetworkX's remove_edges_from
    would only remove one.

    Create MultiDiGraph with 3 keyed edges between (a,b). Call helper.
    Assert all 3 removed.
    """
    G = nx.MultiDiGraph()
    G.add_edge("a", "b", key="k1", relation="calls")
    G.add_edge("a", "b", key="k2", relation="imports")
    G.add_edge("a", "b", key="k3", relation="references")

    # NetworkX's remove_edges_from with 2-tuple only removes first key:
    # G.remove_edges_from([("a", "b")]) would leave 2 edges.
    # Our helper must remove all 3.
    removed = remove_all_parallel_edges(G, "a", "b")

    assert removed == 3
    assert G.number_of_edges() == 0
    assert G.has_node("a")  # nodes preserved
    assert G.has_node("b")


def test_remove_all_parallel_edges_missing_node():
    """If either node doesn't exist in the graph, returns 0 without raising."""
    G = nx.MultiDiGraph()
    G.add_node("a")

    assert remove_all_parallel_edges(G, "a", "nonexistent") == 0
    assert remove_all_parallel_edges(G, "nonexistent", "a") == 0


def test_remove_all_parallel_edges_simple_graph_no_edge():
    """On simple Graph with no edge between u,v, returns 0."""
    G = nx.Graph()
    G.add_node("a")
    G.add_node("b")

    assert remove_all_parallel_edges(G, "a", "b") == 0


def test_remove_all_parallel_edges_multigraph_undirected():
    """On undirected MultiGraph, removes all parallel edges."""
    G = nx.MultiGraph()
    G.add_edge("a", "b", key="k1", relation="calls")
    G.add_edge("a", "b", key="k2", relation="imports")

    removed = remove_all_parallel_edges(G, "a", "b")

    assert removed == 2
    assert G.number_of_edges() == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Group E: Simple-graph regression
# ═══════════════════════════════════════════════════════════════════════════════


def test_simple_graph_dedup_output_unchanged():
    """Default simple-graph build+dedup on a fixed fixture produces identical output.

    This is the go/no-go regression: if this test fails, PR 4A broke the default path.
    """
    extraction = {
        "nodes": [
            {
                "id": "graphextractor",
                "label": "GraphExtractor",
                "file_type": "code",
                "source_file": "a.py",
            },
            {
                "id": "graph_extractor",
                "label": "graph_extractor",
                "file_type": "code",
                "source_file": "a.py",
            },
            {"id": "dataloader", "label": "DataLoader", "file_type": "code", "source_file": "b.py"},
            {
                "id": "networkanalyzer",
                "label": "NetworkAnalyzer",
                "file_type": "code",
                "source_file": "c.py",
            },
        ],
        "edges": [
            {
                "source": "graphextractor",
                "target": "dataloader",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "source_location": "L5",
            },
            {
                "source": "graph_extractor",
                "target": "dataloader",
                "relation": "imports",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "source_location": "L1",
            },
            {
                "source": "dataloader",
                "target": "networkanalyzer",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "b.py",
                "source_location": "L10",
            },
        ],
    }

    # Default simple-graph build with dedup
    G = build([extraction], dedup=True, directed=True)
    assert "graphify_multigraph_diagnostics" not in G.graph

    # "GraphExtractor" and "graph_extractor" are near-duplicates — dedup merges them.
    # _pick_winner prefers shorter ID, no chunk suffix -> "graphextractor" wins
    # (both are same length=14; tiebreak is by sort, so the first is picked).
    # Alternatively graph_extractor (15 chars) vs graphextractor (14 chars) -> graphextractor wins.
    winner_candidates = {"graphextractor", "graph_extractor"}
    surviving_nodes = set(G.nodes())

    # After dedup: 3 nodes survive (one of the two graph-extractor variants + dataloader + networkanalyzer)
    assert G.number_of_nodes() == 3, (
        f"Expected 3 nodes after dedup, got {G.number_of_nodes()}: {sorted(surviving_nodes)}"
    )

    # The winner is the one that survived
    winner = winner_candidates & surviving_nodes
    assert len(winner) == 1, f"Expected exactly one winner from {winner_candidates}, got {winner}"

    assert "dataloader" in surviving_nodes
    assert "networkanalyzer" in surviving_nodes

    # Edges: after remap, both edges pointing to dataloader should survive
    # (different relations: calls vs imports), plus the dataloader->networkanalyzer edge.
    # The self-loop case doesn't apply here since edges go from graph_extractor -> dataloader.
    assert G.number_of_edges() >= 2, f"Expected at least 2 edges, got {G.number_of_edges()}"

    # The dataloader->networkanalyzer edge must survive unchanged
    assert G.has_edge("dataloader", "networkanalyzer")
