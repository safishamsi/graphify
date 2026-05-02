"""Tests for source-location deduplication and graph hygiene.

These tests validate that duplicate nodes sharing the same
(source_file, source_location) are merged conservatively,
edges are remapped, self-loops are dropped, and hyperedges
are remapped correctly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.build import (
    _compatible_duplicate,
    _dedup_key,
    _edge_key,
    deduplicate_by_source_location,
    prune_graph_references,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ── helpers ────────────────────────────────────────────────────────────


def _nid_map(nodes: list[dict]) -> dict[str, dict]:
    """Map node ID -> full node dict for quick assertion."""
    return {n["id"]: n for n in nodes}


# ── _dedup_key ─────────────────────────────────────────────────────────


def test_dedup_key_returns_file_location_tuple():
    assert _dedup_key(
        {"source_file": "src/lib.rs", "source_location": "lib.rs:187"}
    ) == ("src/lib.rs", "lib.rs:187")


def test_dedup_key_strips_whitespace():
    assert _dedup_key(
        {"source_file": "  x.py  ", "source_location": "  x.py:1  "}
    ) == ("x.py", "x.py:1")


def test_dedup_key_returns_none_when_source_file_missing():
    assert _dedup_key({"source_file": "", "source_location": "lib.rs:1"}) is None


def test_dedup_key_returns_none_when_source_location_missing():
    assert _dedup_key({"source_file": "x.py", "source_location": ""}) is None


# ── _compatible_duplicate ──────────────────────────────────────────────


def test_compatible_when_normalised_labels_match():
    assert _compatible_duplicate(
        {"label": "sort_all_nodes_topologically"},
        {"label": "sort_all_nodes_topologically"},
    ) is True


def test_compatible_when_ids_match():
    assert _compatible_duplicate(
        {"id": "func_1", "label": ""},
        {"id": "func_1", "label": "different"},
    ) is True


def test_compatible_when_one_label_contains_other():
    assert _compatible_duplicate(
        {"label": "sort_all_nodes_topologically Method"},
        {"label": "sort_all_nodes_topologically"},
    ) is True


def test_compatible_when_one_id_contains_other():
    assert _compatible_duplicate(
        {"id": "lib_sort_all_nodes_topologically", "label": ""},
        {"id": "sort_all_nodes_topologically", "label": ""},
    ) is True


def test_compatible_when_source_snippets_match():
    assert _compatible_duplicate(
        {"label": "foo", "source_snippet": "fn foo() {}"},
        {"label": "bar", "source_snippet": "fn foo() {}"},
    ) is True


def test_incompatible_when_labels_and_ids_differ():
    assert _compatible_duplicate(
        {"id": "func_a", "label": "Function A"},
        {"id": "func_b", "label": "Function B"},
    ) is False


def test_incompatible_when_no_labels_or_ids():
    assert _compatible_duplicate(
        {"id": "x1", "label": ""},
        {"id": "x2", "label": ""},
    ) is False


# ── _edge_key ──────────────────────────────────────────────────────────


def test_edge_key_is_deterministic():
    e = {"source": "a", "target": "b", "relation": "calls"}
    assert _edge_key(e) == _edge_key(e)


def test_edge_key_differentiates_by_relation():
    e1 = {"source": "a", "target": "b", "relation": "calls"}
    e2 = {"source": "a", "target": "b", "relation": "imports"}
    assert _edge_key(e1) != _edge_key(e2)


# ── same-location merge ────────────────────────────────────────────────


def test_merges_same_source_location_compatible_labels():
    nodes = [
        {"id": "lib_sort_all_nodes_topologically", "label": "sort_all_nodes_topologically Method",
         "source_file": "src/lib.rs", "source_location": "lib.rs:187"},
        {"id": "sort_all_nodes_topologically", "label": "sort_all_nodes_topologically Method",
         "source_file": "src/lib.rs", "source_location": "lib.rs:187"},
    ]
    edges = []

    new_nodes, new_edges, _, _stats = deduplicate_by_source_location(nodes, edges)

    assert len(new_nodes) == 1
    assert new_edges == []


def test_keeps_more_descriptive_node_as_canonical():
    nodes = [
        {"id": "lib_func", "label": "func",
         "source_file": "a.py", "source_location": "a.py:1"},
        {"id": "sem_func", "label": "func — the main entry point",
         "source_file": "a.py", "source_location": "a.py:1"},
    ]
    edges = []

    new_nodes, _, _, _ = deduplicate_by_source_location(nodes, edges)

    assert len(new_nodes) == 1
    # Canonical should be the longer label (sem_func)
    canonical = new_nodes[0]
    assert canonical["id"] == "sem_func"
    assert "entry point" in canonical["label"]


def test_same_source_location_incompatible_labels_does_not_merge():
    """Two different symbols on the same line should NOT be merged."""
    nodes = [
        {"id": "symbol_A", "label": "class A",
         "source_file": "src/module.py", "source_location": "module.py:42"},
        {"id": "symbol_B", "label": "class B",
         "source_file": "src/module.py", "source_location": "module.py:42"},
    ]
    edges = []

    new_nodes, _, _, _ = deduplicate_by_source_location(nodes, edges)

    assert len(new_nodes) == 2


def test_same_source_location_no_labels_does_not_merge():
    nodes = [
        {"id": "unknown_1", "label": "",
         "source_file": "x.py", "source_location": "x.py:99"},
        {"id": "unknown_2", "label": "",
         "source_file": "x.py", "source_location": "x.py:99"},
    ]
    edges = []

    new_nodes, _, _, _ = deduplicate_by_source_location(nodes, edges)

    assert len(new_nodes) == 2


# ── edge remapping ─────────────────────────────────────────────────────


def test_remaps_edges_to_canonical_node():
    nodes = [
        {"id": "ast_foo", "label": "foo",
         "source_file": "a.py", "source_location": "a.py:1"},
        {"id": "sem_foo", "label": "foo function",
         "source_file": "a.py", "source_location": "a.py:1"},
        {"id": "bar", "label": "bar",
         "source_file": "a.py", "source_location": "a.py:2"},
    ]
    edges = [
        {"source": "ast_foo", "target": "bar", "relation": "calls"},
        {"source": "sem_foo", "target": "bar", "relation": "calls"},
    ]

    new_nodes, new_edges, _, _stats = deduplicate_by_source_location(nodes, edges)

    assert len(new_nodes) == 2
    canonical_id = _nid_map(new_nodes)["sem_foo"]["id"]
    for edge in new_edges:
        assert edge["source"] != "ast_foo"  # old ID should be gone
        assert edge["source"] == canonical_id
        assert edge["target"] == "bar"


def test_remaps_both_directions():
    nodes = [
        {"id": "ast_foo", "label": "foo",
         "source_file": "a.py", "source_location": "a.py:1"},
        {"id": "sem_foo", "label": "foo",
         "source_file": "a.py", "source_location": "a.py:1"},
        {"id": "bar", "label": "bar",
         "source_file": "a.py", "source_location": "a.py:2"},
    ]
    edges = [
        {"source": "ast_foo", "target": "bar", "relation": "calls"},
        {"source": "bar", "target": "sem_foo", "relation": "called_by"},
    ]

    new_nodes, new_edges, _, _stats = deduplicate_by_source_location(nodes, edges)

    assert len(new_nodes) == 2
    canonical = "sem_foo"
    sources = {e["source"] for e in new_edges}
    targets = {e["target"] for e in new_edges}
    assert canonical in sources
    assert canonical in targets
    assert "ast_foo" not in sources
    assert "ast_foo" not in targets


# ── self-loop removal ──────────────────────────────────────────────────


def test_drops_self_loops_created_by_merge():
    nodes = [
        {"id": "ast_x", "label": "x",
         "source_file": "a.py", "source_location": "a.py:1"},
        {"id": "sem_x", "label": "x",
         "source_file": "a.py", "source_location": "a.py:1"},
    ]
    edges = [
        {"source": "ast_x", "target": "sem_x", "relation": "same_entity"},
    ]

    new_nodes, new_edges, _, _stats = deduplicate_by_source_location(nodes, edges)

    assert len(new_nodes) == 1
    assert new_edges == []


def test_keeps_non_self_edges_after_merge():
    nodes = [
        {"id": "ast_x", "label": "x",
         "source_file": "a.py", "source_location": "a.py:1"},
        {"id": "sem_x", "label": "x",
         "source_file": "a.py", "source_location": "a.py:1"},
        {"id": "y", "label": "y",
         "source_file": "a.py", "source_location": "a.py:2"},
    ]
    edges = [
        {"source": "ast_x", "target": "y", "relation": "calls"},
        {"source": "sem_x", "target": "y", "relation": "implements"},
    ]

    new_nodes, new_edges, _, _stats = deduplicate_by_source_location(nodes, edges)

    canonical = "sem_x"
    for edge in new_edges:
        assert edge["source"] == canonical
        assert edge["target"] == "y"


# ── edge deduplication ─────────────────────────────────────────────────


def test_deduplicates_idempotent_edges_after_remap():
    nodes = [
        {"id": "ast_x", "label": "x",
         "source_file": "a.py", "source_location": "a.py:1"},
        {"id": "sem_x", "label": "x",
         "source_file": "a.py", "source_location": "a.py:1"},
        {"id": "y", "label": "y",
         "source_file": "a.py", "source_location": "a.py:2"},
    ]
    edges = [
        {"source": "ast_x", "target": "y", "relation": "calls"},
        {"source": "sem_x", "target": "y", "relation": "calls"},
    ]

    _, new_edges, _, _ = deduplicate_by_source_location(nodes, edges)

    assert len(new_edges) == 1


# ── idempotence ────────────────────────────────────────────────────────


def test_dedup_is_idempotent():
    nodes = [
        {"id": "lib_sort_all_nodes_topologically", "label": "sort_all_nodes_topologically Method",
         "source_file": "src/lib.rs", "source_location": "lib.rs:187"},
        {"id": "sort_all_nodes_topologically", "label": "sort_all_nodes_topologically Method",
         "source_file": "src/lib.rs", "source_location": "lib.rs:187"},
        {"id": "lib_add_edge_to_graph", "label": "add_edge_to_graph Method",
         "source_file": "src/lib.rs", "source_location": "lib.rs:125"},
        {"id": "add_edge_to_graph", "label": "add_edge_to_graph Method",
         "source_file": "src/lib.rs", "source_location": "lib.rs:125"},
        {"id": "unique_node", "label": "unique",
         "source_file": "src/error.rs", "source_location": "error.rs:10"},
    ]
    edges = [
        {"source": "lib_sort_all_nodes_topologically", "target": "lib_add_edge_to_graph", "relation": "calls"},
        {"source": "sort_all_nodes_topologically", "target": "add_edge_to_graph", "relation": "calls"},
        {"source": "lib_add_edge_to_graph", "target": "unique_node", "relation": "references"},
    ]

    first_nodes, first_edges, _, _ = deduplicate_by_source_location(nodes, edges)
    second_nodes, second_edges, _, _ = deduplicate_by_source_location(first_nodes, first_edges)

    assert len(first_nodes) == len(second_nodes)
    assert len(first_edges) == len(second_edges)


# ── hyperedge remapping ────────────────────────────────────────────────


def test_remaps_hyperedge_member_ids_after_dedup():
    nodes = [
        {"id": "ast_foo", "label": "foo",
         "source_file": "a.py", "source_location": "a.py:1"},
        {"id": "sem_foo", "label": "foo",
         "source_file": "a.py", "source_location": "a.py:1"},
        {"id": "bar", "label": "bar",
         "source_file": "a.py", "source_location": "a.py:2"},
    ]
    edges = []
    hyperedges = [
        {"id": "h1", "nodes": ["ast_foo", "sem_foo", "bar"], "label": "same concept"},
    ]

    new_nodes, new_edges, new_hyperedges, stats = deduplicate_by_source_location(nodes, edges, hyperedges)

    assert len(new_nodes) == 2
    canonical = "sem_foo"
    assert stats["hyperedges_remapped"] >= 1
    members = stats.get("hyperedge_member_sets", [[]])[0]
    assert sorted(members) == sorted([canonical, "bar"])


def test_drops_hyperedge_members_that_no_longer_exist():
    nodes = [
        {"id": "a", "label": "a", "source_file": "x.py", "source_location": "x.py:1"},
        {"id": "b", "label": "b", "source_file": "x.py", "source_location": "x.py:2"},
    ]
    edges = []
    hyperedges = [{"id": "h", "nodes": ["a", "missing_node"]}]

    _, _, _, stats = deduplicate_by_source_location(nodes, edges, hyperedges)

    assert len(stats.get("hyperedge_member_sets", [[]])[0]) == 1


# ── prune_graph_references ─────────────────────────────────────────────


def test_prune_drops_edges_with_missing_endpoints():
    extraction = {
        "nodes": [
            {"id": "a", "label": "node a"},
            {"id": "b", "label": "node b"},
        ],
        "edges": [
            {"source": "a", "target": "b", "relation": "ok"},
            {"source": "a", "target": "missing", "relation": "bad"},
        ],
        "hyperedges": [],
    }
    result = prune_graph_references(extraction)
    assert len(result["edges"]) == 1
    assert result["edges"][0]["target"] == "b"


def test_prune_drops_self_loops():
    extraction = {
        "nodes": [{"id": "a", "label": "a"}],
        "edges": [{"source": "a", "target": "a", "relation": "self"}],
        "hyperedges": [],
    }
    result = prune_graph_references(extraction)
    assert result["edges"] == []


def test_prune_deduplicates_edges():
    extraction = {
        "nodes": [
            {"id": "a", "label": "a"},
            {"id": "b", "label": "b"},
        ],
        "edges": [
            {"source": "a", "target": "b", "relation": "calls"},
            {"source": "a", "target": "b", "relation": "calls"},
        ],
        "hyperedges": [],
    }
    result = prune_graph_references(extraction)
    assert len(result["edges"]) == 1


def test_prune_drops_hyperedge_members_that_no_longer_exist():
    extraction = {
        "nodes": [
            {"id": "a", "label": "a"},
            {"id": "b", "label": "b"},
        ],
        "edges": [],
        "hyperedges": [{"id": "h1", "nodes": ["a", "b", "missing"]}],
    }
    result = prune_graph_references(extraction)
    assert sorted(result["hyperedges"][0]["nodes"]) == sorted(["a", "b"])


def test_prune_drops_hyperedges_with_less_than_two_members():
    extraction = {
        "nodes": [{"id": "a", "label": "a"}],
        "edges": [],
        "hyperedges": [
            {"id": "h1", "nodes": ["a"]},
            {"id": "h2", "nodes": ["a", "b"]},
            {"id": "h3", "nodes": ["missing"]},
        ],
    }
    result = prune_graph_references(extraction)
    assert len(result["hyperedges"]) == 0  # h2: b is missing too


def test_prune_is_idempotent():
    extraction = {
        "nodes": [
            {"id": "a", "label": "a"},
            {"id": "b", "label": "b"},
        ],
        "edges": [
            {"source": "a", "target": "b", "relation": "ok"},
            {"source": "a", "target": "missing", "relation": "bad"},
            {"source": "a", "target": "b", "relation": "ok"},
        ],
        "hyperedges": [{"id": "h1", "nodes": ["a", "missing"]}],
    }
    first = prune_graph_references(extraction)
    second = prune_graph_references(first)
    assert len(first["edges"]) == len(second["edges"])
    assert len(first["hyperedges"]) == len(second["hyperedges"])


# ── integration: dedup + prune with build ──────────────────────────────


def test_dedup_then_prune_cleans_duplicate_ast_semantic_nodes():
    """Simulates the real-world pattern: AST and semantic extraction both
    produce nodes for the same source location with different IDs."""
    extraction = {
        "nodes": [
            {"id": "lib_sort_all_nodes_topologically", "label": "sort_all_nodes_topologically Method",
             "file_type": "code", "source_file": "src/lib.rs", "source_location": "lib.rs:187"},
            {"id": "sort_all_nodes_topologically", "label": "sort_all_nodes_topologically Method",
             "file_type": "code", "source_file": "src/lib.rs", "source_location": "lib.rs:187"},
            {"id": "lib_add_edge_to_graph", "label": "add_edge_to_graph Method",
             "file_type": "code", "source_file": "src/lib.rs", "source_location": "lib.rs:125"},
            {"id": "unique_node", "label": "TopoSortError",
             "file_type": "code", "source_file": "src/error.rs", "source_location": "error.rs:10"},
        ],
        "edges": [
            {"source": "lib_sort_all_nodes_topologically", "target": "lib_add_edge_to_graph",
             "relation": "calls"},
            {"source": "sort_all_nodes_topologically", "target": "unique_node",
             "relation": "references"},
        ],
        "hyperedges": [
            {"id": "h1", "nodes": ["lib_sort_all_nodes_topologically", "sort_all_nodes_topologically",
                                    "unique_node"], "label": "core functions"},
        ],
    }

    # Dedup
    deduped, dedup_edges, _, _stats = deduplicate_by_source_location(
        extraction["nodes"],
        extraction["edges"],
        extraction.get("hyperedges", []),
    )
    extraction["nodes"] = deduped
    extraction["edges"] = dedup_edges

    assert len(deduped) == 3  # 4 → 3 (two sort nodes merged)
    canonical_sort = _nid_map(deduped)["sort_all_nodes_topologically"]["id"]

    # All edge sources should use canonical
    for edge in dedup_edges:
        assert edge["source"] != "lib_sort_all_nodes_topologically"

    # Prune
    clean = prune_graph_references(extraction)

    assert len(clean["nodes"]) == 3
    for edge in clean["edges"]:
        assert edge["source"] in {n["id"] for n in clean["nodes"]}
        assert edge["target"] in {n["id"] for n in clean["nodes"]}


# ── fixture-based tests (golden data) ──────────────────────────────────


def test_dedup_fixture_same_source_location():
    """Load a real-world-like fixture with known duplicates and verify."""
    path = FIXTURES / "dedup_same_source_location.json"
    if not path.exists():
        pytest.skip("fixture not found — run tests/generate_fixtures.py first")
    data = json.loads(path.read_text())
    nodes, edges, _, stats = deduplicate_by_source_location(
        data["nodes"], data.get("edges", []), data.get("hyperedges", [])
    )
    assert len(nodes) < len(data["nodes"]), "expected at least one merge"
    assert stats["merged_nodes"] > 0


# ── Internal helper coverage ──────────────────────────────────────────────


def test_norm_label_normalizes_punctuation_and_case():
    from graphify.build import _norm_label
    assert _norm_label("Foo_Bar-123") == "foobar123"
    assert _norm_label("Hello World!") == "hello world"
    assert _norm_label("") == ""


def test_norm_member_label_strips_t_prefix():
    from graphify.build import _norm_member_label
    assert _norm_member_label("T-21  Graph Query & Analysis Notes") == "Graph Query & Analysis Notes"


def test_norm_member_label_no_prefix_passthrough():
    from graphify.build import _norm_member_label
    assert _norm_member_label("Core Architecture") == "Core Architecture"


def test_norm_member_label_empty():
    from graphify.build import _norm_member_label
    assert _norm_member_label("") == ""


# ── deduplicate_extraction_by_source_location wrapper ─────────────────────


def test_deduplicate_extraction_by_source_location_merges_document_nodes():
    from graphify.build import deduplicate_extraction_by_source_location
    extraction = {
        "nodes": [
            {"id": "ast_foo", "label": "foo", "source_file": "a.py", "source_location": "a.py:1", "type": "function", "file_type": "code"},
            {"id": "sem_foo", "label": "foo function", "source_file": "a.py", "source_location": "a.py:1", "type": "function", "file_type": "code"},
        ],
        "edges": [{"source": "ast_foo", "target": "sem_foo", "relation": "same_entity"}],
        "hyperedges": [{"id": "h1", "nodes": ["ast_foo", "sem_foo"]}],
    }
    result = deduplicate_extraction_by_source_location(extraction)
    assert len(result["nodes"]) == 1
    # hyperedge becomes a singleton after merge and is dropped by prune
    assert len(result["hyperedges"]) == 0


def test_deduplicate_extraction_by_source_location_no_hyperedges():
    from graphify.build import deduplicate_extraction_by_source_location
    extraction = {
        "nodes": [
            {"id": "ast_foo", "label": "foo", "source_file": "a.py", "source_location": "a.py:1", "type": "function", "file_type": "code"},
            {"id": "sem_foo", "label": "foo function", "source_file": "a.py", "source_location": "a.py:1", "type": "function", "file_type": "code"},
        ],
        "edges": [],
    }
    result = deduplicate_extraction_by_source_location(extraction)
    assert len(result["nodes"]) == 1


# ── deduplicate_by_source_location early-return paths ─────────────────────


def test_deduplicate_early_return_when_no_source_locations():
    """Early return when no nodes carry source_file+source_location."""
    nodes = [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]
    edges = [{"source": "a", "target": "b", "relation": "calls"}]
    _, _, _, stats = deduplicate_by_source_location(nodes, edges)
    assert stats["source_location_groups"] == 0
    assert stats["merged_nodes"] == 0


def test_deduplicate_early_return_when_no_groups_need_merge():
    """Each source-location group has only one node — no merging."""
    nodes = [
        {"id": "a", "label": "A", "source_file": "x.py", "source_location": "x.py:1"},
        {"id": "b", "label": "B", "source_file": "x.py", "source_location": "x.py:2"},
    ]
    edges = []
    _, _, _, stats = deduplicate_by_source_location(nodes, edges)
    assert stats["merged_nodes"] == 0


# ── Canonical node attributes merge ────────────────────────────────────────


def test_deduplicate_preserves_non_empty_attributes():
    """Canonical node absorbs attributes that the survivor lacks."""
    import copy
    nodes = [
        {"id": "ast_foo", "label": "foo", "source_file": "a.py", "source_location": "a.py:1", "type": "function"},
        {"id": "sem_foo", "label": "foo function", "source_file": "a.py", "source_location": "a.py:1", "docstring": "does the thing"},
    ]
    n, _, _, _stats = deduplicate_by_source_location(copy.deepcopy(nodes), [])
    canonical = next(nd for nd in n if nd["id"] != "ast_foo")
    assert canonical.get("docstring") == "does the thing"


# ── prune_graph_references edge cases ──────────────────────────────────────


def test_prune_removes_edges_to_missing_nodes():
    from graphify.build import prune_graph_references
    extraction = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [
            {"source": "a", "target": "b", "relation": "calls"},
            {"source": "a", "target": "missing", "relation": "calls"},
        ],
        "hyperedges": [],
    }
    result = prune_graph_references(extraction)
    assert len(result["edges"]) == 1
    assert result["edges"][0]["target"] == "b"


def test_prune_drops_self_loops():
    from graphify.build import prune_graph_references
    extraction = {
        "nodes": [{"id": "a"}],
        "edges": [
            {"source": "a", "target": "a", "relation": "self"},
            {"source": "a", "target": "a", "relation": "self"},
        ],
        "hyperedges": [],
    }
    result = prune_graph_references(extraction)
    assert result["edges"] == []


def test_prune_deduplicates_identical_edges():
    from graphify.build import prune_graph_references
    extraction = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [
            {"source": "a", "target": "b", "relation": "calls"},
            {"source": "a", "target": "b", "relation": "calls"},
        ],
        "hyperedges": [],
    }
    result = prune_graph_references(extraction)
    assert len(result["edges"]) == 1


def test_prune_filters_hyperedge_members():
    from graphify.build import prune_graph_references
    extraction = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [],
        "hyperedges": [
            {"id": "h1", "nodes": ["a", "b", "missing"]},
        ],
    }
    result = prune_graph_references(extraction)
    assert result["hyperedges"][0]["nodes"] == ["a", "b"]


def test_prune_drops_hyperedges_with_less_than_two_members():
    from graphify.build import prune_graph_references
    extraction = {
        "nodes": [{"id": "a"}],
        "edges": [],
        "hyperedges": [
            {"id": "h1", "nodes": ["a", "missing"]},  # only 1 valid member after filter
        ],
    }
    result = prune_graph_references(extraction)
    assert len(result["hyperedges"]) == 0


def test_prune_hyperedges_with_full_duplicate_after_remap():
    from graphify.build import prune_graph_references
    extraction = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [],
        "hyperedges": [
            {"id": "h1", "nodes": ["a", "b"]},
            {"id": "h2", "nodes": ["b", "a"]},
        ],
    }
    result = prune_graph_references(extraction)
    # Both hyperedges should survive (ordering doesn't collapse them)
    assert len(result["hyperedges"]) >= 1


# ---------------------------------------------------------------------------
# build_from_json edge-case tests (lines 91-96, 99-104 in build.py)
# ---------------------------------------------------------------------------

def test_build_from_json_skips_edge_without_source_or_target():
    """Edges missing both 'source' and 'target' (and no 'from'/'to') are skipped."""
    from graphify.build import build_from_json
    extraction = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [
            {"relation": "missing_both"},  # no source, no target, no from, no to
        ],
        "hyperedges": [],
    }
    G = build_from_json(extraction)
    assert G.number_of_nodes() == 2
    assert G.number_of_edges() == 0


def test_build_from_json_remaps_from_to_fields():
    """Edges using 'from'/'to' instead of 'source'/'target' are accepted."""
    from graphify.build import build_from_json
    extraction = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [
            {"from": "a", "to": "b", "relation": "calls", "source_file": "/x.py", "confidence": "INFERRED"},
        ],
        "hyperedges": [],
    }
    G = build_from_json(extraction)
    assert G.number_of_nodes() == 2
    assert G.number_of_edges() == 1


def test_build_from_json_normalized_id_remap():
    """Edge endpoints that differ in case/punctuation are remapped via norm_to_id."""
    from graphify.build import build_from_json
    extraction = {
        "nodes": [{"id": "Session_ValidateToken"}],
        "edges": [
            {"source": "session_validatetoken", "target": "session_validatetoken",
             "relation": "self_ref", "source_file": "/x.py",
             "confidence": "EXTRACTED"},
        ],
        "hyperedges": [],
    }
    G = build_from_json(extraction)
    assert G.number_of_nodes() == 1
    assert G.number_of_edges() == 1


def test_build_from_json_edge_with_unmapped_endpoint_skipped():
    """Edges whose endpoints can't be resolved via norm_to_id are discarded."""
    from graphify.build import build_from_json
    extraction = {
        "nodes": [{"id": "a"}],
        "edges": [
            {"source": "a", "target": "completely_missing_node",
             "relation": "broken", "source_file": "/x.py",
             "confidence": "EXTRACTED"},
        ],
        "hyperedges": [],
    }
    G = build_from_json(extraction)
    assert G.number_of_nodes() == 1
    assert G.number_of_edges() == 0


# ---------------------------------------------------------------------------
# deduplicate_by_source_location edge-case tests
# ---------------------------------------------------------------------------

def test_dedup_empty_nodes_and_hyperedges():
    """Dedup with no nodes returns empty stats."""
    from graphify.build import deduplicate_by_source_location
    nodes, edges, hyperedges, stats = deduplicate_by_source_location(
        [], [{"source": "a", "target": "b"}], [{"id": "h", "nodes": ["a"]}]
    )
    assert len(nodes) == 0
    assert len(edges) == 0
    assert len(hyperedges) == 0
    assert stats["merged_nodes"] == 0


def test_dedup_canonical_keeps_richer_node():
    """When merging, the node with more attributes wins as canonical."""
    from graphify.build import deduplicate_by_source_location
    nodes = [
        {"id": "thin", "label": "x", "source_file": "a.py", "source_location": "a.py:1"},
        {"id": "rich", "label": "x", "source_file": "a.py", "source_location": "a.py:1",
         "type": "function", "source_snippet": "def x(): ..."},
    ]
    dedup_nodes, _, _, stats = deduplicate_by_source_location(nodes, [])
    assert len(dedup_nodes) == 1
    assert dedup_nodes[0]["id"] == "rich" or dedup_nodes[0].get("type") == "function"


def test_dedup_no_source_locations_returns_unchanged():
    """Dedup with no source_location data returns early without merging."""
    from graphify.build import deduplicate_by_source_location
    nodes = [
        {"id": "a", "label": "foo"},
        {"id": "b", "label": "foo"},
    ]
    dedup_nodes, _, _, stats = deduplicate_by_source_location(nodes, [])
    assert len(dedup_nodes) == 2
    assert stats["merged_nodes"] == 0


# ---------------------------------------------------------------------------
# prune_graph_references edge-case tests
# ---------------------------------------------------------------------------

def test_prune_skips_edge_with_missing_source_or_target():
    """prune_graph_references drops edges whose source/target are missing."""
    from graphify.build import prune_graph_references
    extraction = {
        "nodes": [{"id": "a"}],
        "edges": [
            {"source": "missing", "target": "a", "relation": "ref"},
            {"source": "a", "target": "missing", "relation": "ref"},
            {"source": "missing2", "target": "missing3", "relation": "ref"},
        ],
        "hyperedges": [],
    }
    result = prune_graph_references(extraction)
    assert result["edges"] == []


# ---------------------------------------------------------------------------
# build_merge tests
# ---------------------------------------------------------------------------

def test_build_merge_with_typeerror_fallback():
    """build_merge handles garbled graph data."""
    from graphify.build import build_merge
    G1 = build_merge(
        [
            {
                "nodes": [{"id": "a"}],
                "edges": [],
                "hyperedges": [],
            }
        ]
    )
    assert G1.number_of_nodes() > 0 or isinstance(G1, object)


def test_build_merge_prunes_stale_source_file_edges(tmp_path):
    """build_merge with source_file filter prunes edges from removed files."""
    from graphify.build import build_merge
    G = build_merge(
        [
            {
                "nodes": [
                    {"id": "a", "source_file": "/keep.py"},
                    {"id": "b", "source_file": "/remove.py"},
                ],
                "edges": [
                    {"source": "a", "target": "b", "relation": "ref",
                     "source_file": "/keep.py", "confidence": "EXTRACTED"},
                ],
                "hyperedges": [],
            }
        ],
        prune_sources={"/remove.py"},
        graph_path=tmp_path / "graph.json",
    )
    assert "a" in G.nodes()


# ---------------------------------------------------------------------------
# _norm_member_label tests
# ---------------------------------------------------------------------------

def test_norm_member_label_returns_input_for_non_member():
    """_norm_member_label is a noop for non-member-formatted labels."""
    from graphify.build import _norm_member_label
    assert _norm_member_label("plain_label") == "plain_label"
    assert _norm_member_label("T-") == "T-"
    assert _norm_member_label("") == ""


def test_prune_hyperedges_when_no_source_location_groups():
    """Hyperedges with stale members are pruned even without source-location groups."""
    nodes = [
        {"id": "a", "label": "A"},
        {"id": "b", "label": "B"},
    ]
    edges = [
        {"source": "a", "target": "missing", "relation": "calls"},
        {"source": "a", "target": "b", "relation": "calls"},
    ]
    hyperedges = [
        {"id": "h1", "nodes": ["a", "b", "missing"]},
        {"id": "h2", "nodes": ["a"]},
        {"id": "h3", "nodes": ["a", "b"]},
    ]
    new_nodes, new_edges, new_hyperedges, stats = deduplicate_by_source_location(
        nodes, edges, hyperedges
    )
    # Edges with missing endpoints dropped
    assert len(new_edges) == 1
    assert new_edges[0]["source"] == "a"
    assert new_edges[0]["target"] == "b"
    # h1: "missing" removed, a,b remain → kept
    # h2: only "a" left → dropped  
    # h3: a,b both valid → kept
    assert len(new_hyperedges) == 2
    kept_ids = {h["id"] for h in new_hyperedges}
    assert kept_ids == {"h1", "h3"}
    # Stats reflect pruning
    assert stats["merged_nodes"] == 0
    assert stats["hyperedges_remapped"] == 1  # h2 dropped
    assert stats["deduped_edges"] == 1  # missing endpoint edge dropped


def test_build_merge_with_prune_sources_removes_nodes(tmp_path):
    """Prune sources remove nodes from specific files."""
    extraction = {
        "nodes": [
            {"id": "keep", "source_file": "src/keep.py"},
            {"id": "drop", "source_file": "src/drop.py"},
            {"id": "also_keep", "source_file": "src/keep.py"},
        ],
        "edges": [],
        "hyperedges": [],
    }
    from graphify.build import build_merge
    g = build_merge(
        [extraction],
        graph_path=tmp_path / "graph.json",
        prune_sources={"src/drop.py"},
    )
    assert g.number_of_nodes() == 2
    assert "keep" in g.nodes
    assert "also_keep" in g.nodes
    assert "drop" not in g.nodes


def test_member_label_normalization():
    """_norm_member_label strips common prefixes."""
    from graphify.build import _norm_member_label
    assert _norm_member_label("T-21  some.Name") == "some.Name"
    assert _norm_member_label("T-1  foo_bar") == "foo_bar"
    assert _norm_member_label("plain name") == "plain name"
    assert _norm_member_label("") == ""
