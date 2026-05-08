"""Comprehensive tests for graphify.test_linking — Phase 5 deterministic test-to-source linking.

Covers: basic test-to-code linking, stem-based resolution, edge dedup behavior,
empty/None inputs, error paths, multi-function test files, test files that
don't match any production code.
"""
from __future__ import annotations

from graphify.test_linking import (
    _normalise_label,
    _stem_from_source,
    _test_class_to_production_name,
    _test_file_to_production_stem,
    _test_func_to_production_name,
    is_test_node,
    resolve_python_test_edges,
)


# ============================================================================
# Helper: node factory
# ============================================================================


def _make_node(
    nid: str,
    label: str,
    source_file: str = "",
    source_location: str = "",
    file_type: str = "code",
) -> dict:
    """Create a minimal node dict for test fixtures."""
    return {
        "id": nid,
        "label": label,
        "source_file": source_file,
        "source_location": source_location,
        "file_type": file_type,
    }


# ---------------------------------------------------------------------------
# is_test_node
# ---------------------------------------------------------------------------


def test_is_test_node_recognises_test_function_prefix() -> None:
    """Labels starting with test_ are test nodes."""
    assert is_test_node({"label": "test_calculate()", "file_type": "code"}) is True
    assert is_test_node({"label": "test_process_data", "file_type": "code"}) is True
    assert is_test_node({"label": "test_", "file_type": "code"}) is True


def test_is_test_node_recognises_test_class_prefix() -> None:
    """Labels starting with Test are test nodes."""
    assert is_test_node({"label": "TestCalculator", "file_type": "code"}) is True
    assert is_test_node({"label": "TestFoo", "file_type": "code"}) is True


def test_is_test_node_rejects_non_test_labels() -> None:
    """Ordinary function/class labels are not test nodes."""
    assert is_test_node({"label": "calculate()", "file_type": "code"}) is False
    assert is_test_node({"label": "process", "file_type": "code"}) is False
    assert is_test_node({"label": "Foo", "file_type": "code"}) is False


def test_is_test_node_rejects_empty_label() -> None:
    """Empty string label is not a test node."""
    assert is_test_node({"label": "", "file_type": "code"}) is False


def test_is_test_node_rejects_missing_label_key() -> None:
    """Node dict without a 'label' key is not a test node."""
    assert is_test_node({"id": "n1", "file_type": "code"}) is False


def test_is_test_node_rejects_non_python_language() -> None:
    """Only language='python' is recognised; other languages return False."""
    assert is_test_node({"label": "test_foo()"}, language="go") is False
    assert is_test_node({"label": "test_foo()"}, language="python") is True


# ---------------------------------------------------------------------------
# _test_file_to_production_stem
# ---------------------------------------------------------------------------


def test_test_file_to_production_stem_test_prefix_with_directory() -> None:
    """tests/test_foo.py → foo."""
    assert _test_file_to_production_stem("/repo/tests/test_foo.py") == "foo"
    assert _test_file_to_production_stem("tests/test_calc.py") == "calc"


def test_test_file_to_production_stem_test_prefix_basename_only() -> None:
    """test_bar.py → bar."""
    assert _test_file_to_production_stem("test_bar.py") == "bar"
    assert _test_file_to_production_stem("test_helper.py") == "helper"


def test_test_file_to_production_stem_test_suffix_with_directory() -> None:
    """foo_test.py → foo."""
    assert _test_file_to_production_stem("/repo/foo_test.py") == "foo"
    assert _test_file_to_production_stem("pkg/calc_test.py") == "calc"


def test_test_file_to_production_stem_test_suffix_basename_only() -> None:
    """bar_test.py → bar."""
    assert _test_file_to_production_stem("bar_test.py") == "bar"
    assert _test_file_to_production_stem("utils_test.py") == "utils"


def test_test_file_to_production_stem_no_convention_returns_none() -> None:
    """Files without test naming convention return None."""
    assert _test_file_to_production_stem("/repo/foo.py") is None
    assert _test_file_to_production_stem("module.py") is None
    assert _test_file_to_production_stem("testing.py") is None


def test_test_file_to_production_stem_empty_string_returns_none() -> None:
    """Empty source_file returns None."""
    assert _test_file_to_production_stem("") is None


# ---------------------------------------------------------------------------
# _test_func_to_production_name
# ---------------------------------------------------------------------------


def test_test_func_to_production_name_strips_test_prefix() -> None:
    """test_ prefix is removed from the function name."""
    assert _test_func_to_production_name("test_calculate") == "calculate"
    assert _test_func_to_production_name("test_foo_bar") == "foo_bar"


def test_test_func_to_production_name_preserves_parentheses() -> None:
    """Parentheses in the test label are preserved in the output."""
    assert _test_func_to_production_name("test_calculate()") == "calculate()"
    assert _test_func_to_production_name("test_process_data()") == "process_data()"


def test_test_func_to_production_name_rejects_non_test_function() -> None:
    """Functions without test_ prefix return None."""
    assert _test_func_to_production_name("calculate()") is None
    assert _test_func_to_production_name("run") is None


def test_test_func_to_production_name_empty_suffix_returns_none() -> None:
    """Label 'test_' with nothing after returns None."""
    assert _test_func_to_production_name("test_") is None


# ---------------------------------------------------------------------------
# _test_class_to_production_name
# ---------------------------------------------------------------------------


def test_test_class_to_production_name_test_prefix_convention() -> None:
    """TestFoo → Foo."""
    assert _test_class_to_production_name("TestFoo") == "Foo"
    assert _test_class_to_production_name("TestCalculator") == "Calculator"
    assert _test_class_to_production_name("TestHTTPClient") == "HTTPClient"


def test_test_class_to_production_name_test_suffix_convention() -> None:
    """FooTest → Foo."""
    assert _test_class_to_production_name("FooTest") == "Foo"
    assert _test_class_to_production_name("CalculatorTest") == "Calculator"


def test_test_class_to_production_name_tests_suffix_convention() -> None:
    """FooTests → Foo (plural suffix stripped)."""
    assert _test_class_to_production_name("FooTests") == "Foo"
    assert _test_class_to_production_name("CalculatorTests") == "Calculator"


def test_test_class_to_production_name_no_convention_returns_none() -> None:
    """Classes without test naming convention return None."""
    assert _test_class_to_production_name("Foo") is None
    assert _test_class_to_production_name("Calculator") is None


def test_test_class_to_production_name_ambiguous_suffix_returns_none() -> None:
    """'Test' alone is not a valid test class naming pattern."""
    assert _test_class_to_production_name("Test") is None


# ---------------------------------------------------------------------------
# _normalise_label
# ---------------------------------------------------------------------------


def test_normalise_label_strips_parentheses() -> None:
    assert _normalise_label("calculate()") == "calculate"
    assert _normalise_label("run()") == "run"


def test_normalise_label_strips_leading_dot() -> None:
    assert _normalise_label(".process()") == "process"
    assert _normalise_label(".execute") == "execute"


def test_normalise_label_lowercases() -> None:
    assert _normalise_label("Calculate()") == "calculate"
    assert _normalise_label("RUN") == "run"


def test_normalise_label_strips_whitespace() -> None:
    assert _normalise_label("  run  ") == "run"
    assert _normalise_label("\tprocess\n") == "process"


def test_normalise_label_combined_transformations() -> None:
    """All normalisations applied together."""
    assert _normalise_label("  .Foo()  ") == "foo"


# ---------------------------------------------------------------------------
# _stem_from_source
# ---------------------------------------------------------------------------


def test_stem_from_source_extracts_basename_stem() -> None:
    assert _stem_from_source("/repo/pkg/module.py") == "module"
    assert _stem_from_source("helper.py") == "helper"
    assert _stem_from_source("/a/b/c/util.py") == "util"


def test_stem_from_source_handles_empty_string() -> None:
    assert _stem_from_source("") == ""


def test_stem_from_source_handles_no_extension() -> None:
    assert _stem_from_source("/repo/Makefile") == "Makefile"


# ---------------------------------------------------------------------------
# resolve_python_test_edges — basic linking
# ---------------------------------------------------------------------------


def test_basic_test_function_to_production_linking() -> None:
    """test_calculate() in test_calc.py links to calculate() in calc.py."""
    nodes = [
        _make_node("test_calculate", "test_calculate()", "/repo/tests/test_calc.py", "L5"),
        _make_node("calc_calculate", "calculate()", "/repo/calc.py", "L3"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")

    assert created == 2  # test_of + tests reverse
    test_of = next(e for e in edges if e["relation"] == "test_of")
    assert test_of["source"] == "test_calculate"
    assert test_of["target"] == "calc_calculate"
    assert test_of["confidence"] == "INFERRED"
    assert test_of["confidence_score"] == 0.8
    assert test_of["context"] == "test_linking"
    assert test_of["weight"] == 1.0


def test_test_class_to_production_linking() -> None:
    """TestCalculator in test_calc.py links to Calculator in calc.py."""
    nodes = [
        _make_node("test_calc", "TestCalculator", "/repo/tests/test_calc.py", "L1"),
        _make_node("calc", "Calculator", "/repo/calc.py", "L1"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")

    assert created == 2
    test_of = next(e for e in edges if e["relation"] == "test_of")
    assert test_of["source"] == "test_calc"
    assert test_of["target"] == "calc"


# ---------------------------------------------------------------------------
# Stem-based matching
# ---------------------------------------------------------------------------


def test_stem_based_matching_links_across_files() -> None:
    """test_foo in test_helper.py links to foo in helper.py via stem match."""
    nodes = [
        _make_node("test_h_foo", "test_foo()", "/repo/tests/test_helper.py", "L10"),
        _make_node("h_foo", "foo()", "/repo/helper.py", "L5"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_helper.py")

    assert created == 2
    test_of = next(e for e in edges if e["relation"] == "test_of")
    assert test_of["source"] == "test_h_foo"
    assert test_of["target"] == "h_foo"


def test_fallback_any_stem_match() -> None:
    """When test_stem doesn't match, falls back to any stem with matching label."""
    nodes = [
        _make_node("test_x_foo", "test_foo()", "/repo/tests/test_unrelated.py", "L10"),
        _make_node("other_foo", "foo()", "/repo/other.py", "L5"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_unrelated.py")

    assert created == 2
    test_of = next(e for e in edges if e["relation"] == "test_of")
    assert test_of["target"] == "other_foo"


def test_exact_label_match_priority_over_stem() -> None:
    """Exact label match takes priority over stem-based matching."""
    nodes = [
        _make_node("test_calc", "test_calculate()", "/repo/tests/test_calc.py", "L5"),
        # Exact match in wrong stem — but exact match has priority
        _make_node("wrong_stem_calc", "calculate()", "/repo/wrong.py", "L2"),
        # Correct stem match
        _make_node("correct_stem_calc", "calculate()", "/repo/calc.py", "L3"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")

    assert created == 2
    test_of = next(e for e in edges if e["relation"] == "test_of")
    # Exact label match should resolve to the first one found in prod_id_by_label
    # (which is the first entry with that label, not the stem-matched one)
    assert test_of["target"] == "wrong_stem_calc"


# ---------------------------------------------------------------------------
# Multi-function test files
# ---------------------------------------------------------------------------


def test_multi_function_test_file_links_all() -> None:
    """A test file with multiple test functions links each to its production."""
    nodes = [
        _make_node("t_add", "test_add()", "/repo/tests/test_math.py", "L5"),
        _make_node("t_sub", "test_subtract()", "/repo/tests/test_math.py", "L10"),
        _make_node("t_mul", "test_multiply()", "/repo/tests/test_math.py", "L15"),
        _make_node("p_add", "add()", "/repo/math.py", "L3"),
        _make_node("p_sub", "subtract()", "/repo/math.py", "L8"),
        _make_node("p_mul", "multiply()", "/repo/math.py", "L13"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_math.py")

    assert created == 6  # 3 test_of + 3 tests reverse
    test_of_edges = [e for e in edges if e["relation"] == "test_of"]
    assert len(test_of_edges) == 3

    sources = {e["source"] for e in test_of_edges}
    targets = {e["target"] for e in test_of_edges}
    assert sources == {"t_add", "t_sub", "t_mul"}
    assert targets == {"p_add", "p_sub", "p_mul"}


def test_mixed_test_functions_and_test_classes() -> None:
    """A test file with both test functions and test classes links all."""
    nodes = [
        _make_node("t_func", "test_process()", "/repo/tests/test_worker.py", "L5"),
        _make_node("t_class", "TestWorker", "/repo/tests/test_worker.py", "L20"),
        _make_node("p_func", "process()", "/repo/worker.py", "L3"),
        _make_node("p_class", "Worker", "/repo/worker.py", "L15"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_worker.py")

    assert created == 4  # 2 test_of + 2 tests
    test_of_edges = [e for e in edges if e["relation"] == "test_of"]
    assert len(test_of_edges) == 2


# ---------------------------------------------------------------------------
# No matching production
# ---------------------------------------------------------------------------


def test_no_matching_production_creates_no_edges() -> None:
    """When no production node matches, zero edges are created."""
    nodes = [
        _make_node("test_h_unknown", "test_unknown()", "/repo/tests/test_helper.py", "L10"),
        _make_node("h_foo", "foo()", "/repo/helper.py", "L5"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_helper.py")
    assert created == 0


def test_test_file_stem_mismatch_no_fallback_match() -> None:
    """When test stem doesn't match and no fallback exists, no edges."""
    nodes = [
        _make_node("t_calc", "test_calculate()", "/repo/tests/test_calc.py", "L5"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")
    assert created == 0


# ---------------------------------------------------------------------------
# Edge dedup
# ---------------------------------------------------------------------------


def test_edge_dedup_test_of_already_exists() -> None:
    """Does not create test_of edge when it already exists in the edges list."""
    nodes = [
        _make_node("test_calc", "test_calculate()", "/repo/tests/test_calc.py", "L5"),
        _make_node("calc", "calculate()", "/repo/calc.py", "L3"),
    ]
    edges: list[dict] = [
        {
            "source": "test_calc",
            "target": "calc",
            "relation": "test_of",
            "confidence": "INFERRED",
            "source_file": "/repo/tests/test_calc.py",
        }
    ]
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")
    # test_of already exists, so the entire test node is skipped (continue)
    assert created == 0
    assert len(edges) == 1  # original test_of only


def test_edge_dedup_tests_reverse_already_exists() -> None:
    """Does not create tests edge when it already exists."""
    nodes = [
        _make_node("test_calc", "test_calculate()", "/repo/tests/test_calc.py", "L5"),
        _make_node("calc", "calculate()", "/repo/calc.py", "L3"),
    ]
    edges: list[dict] = [
        {
            "source": "calc",
            "target": "test_calc",
            "relation": "tests",
            "confidence": "INFERRED",
            "source_file": "/repo/tests/test_calc.py",
        }
    ]
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")
    assert created == 1  # only test_of is new
    assert len(edges) == 2


def test_edge_dedup_both_directions_preexist() -> None:
    """When both test_of and tests edges already exist, nothing is added."""
    nodes = [
        _make_node("test_calc", "test_calculate()", "/repo/tests/test_calc.py", "L5"),
        _make_node("calc", "calculate()", "/repo/calc.py", "L3"),
    ]
    edges: list[dict] = [
        {
            "source": "test_calc",
            "target": "calc",
            "relation": "test_of",
        },
        {
            "source": "calc",
            "target": "test_calc",
            "relation": "tests",
        },
    ]
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")
    assert created == 0
    assert len(edges) == 2


def test_edge_dedup_idempotent_second_call() -> None:
    """Calling resolve_python_test_edges twice does not create duplicates."""
    nodes = [
        _make_node("test_calc", "test_calculate()", "/repo/tests/test_calc.py", "L5"),
        _make_node("calc", "calculate()", "/repo/calc.py", "L3"),
    ]
    edges: list[dict] = []
    first = resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")
    assert first == 2

    second = resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")
    assert second == 0
    assert len(edges) == 2


# ---------------------------------------------------------------------------
# Empty / None / missing inputs
# ---------------------------------------------------------------------------


def test_empty_nodes_list_returns_zero() -> None:
    assert resolve_python_test_edges([], [], "/repo/tests/test_calc.py") == 0


def test_empty_source_file_still_links_via_exact_match() -> None:
    """Empty string source_file — test_stem is None, but exact label match
    still succeeds."""
    nodes = [
        _make_node("test_calc", "test_calculate()", "", "L5"),
        _make_node("calc", "calculate()", "/repo/calc.py", "L3"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "")
    assert created == 2  # exact label match succeeds


def test_non_python_language_returns_zero() -> None:
    nodes = [
        _make_node("t_calc", "test_calculate()", "/repo/tests/test_calc.py"),
        _make_node("calc", "calculate()", "/repo/calc.py"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(
        nodes, edges, "/repo/tests/test_calc.py", language="go"
    )
    assert created == 0


def test_test_node_without_id_is_skipped() -> None:
    """Test node missing 'id' key should be skipped silently."""
    nodes = [
        {"label": "test_calculate()", "source_file": "/repo/tests/test_calc.py"},
        _make_node("calc", "calculate()", "/repo/calc.py", "L3"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")
    assert created == 0


def test_test_node_without_label_is_skipped() -> None:
    """Test node missing 'label' key should be skipped."""
    nodes = [
        {"id": "test_calc", "source_file": "/repo/tests/test_calc.py"},
        _make_node("calc", "calculate()", "/repo/calc.py", "L3"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")
    assert created == 0


def test_production_node_without_id_is_skipped_in_index() -> None:
    """Production node missing 'id' is not added to lookup indexes."""
    nodes = [
        _make_node("test_calc", "test_calculate()", "/repo/tests/test_calc.py", "L5"),
        {"label": "calculate()", "source_file": "/repo/calc.py"},  # no id
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")
    assert created == 0


def test_production_node_without_label_is_skipped_in_index() -> None:
    """Production node missing 'label' is not added to lookup indexes."""
    nodes = [
        _make_node("test_calc", "test_calculate()", "/repo/tests/test_calc.py", "L5"),
        {"id": "calc", "source_file": "/repo/calc.py"},  # no label
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")
    assert created == 0


# ---------------------------------------------------------------------------
# Source file filtering
# ---------------------------------------------------------------------------


def test_test_node_from_different_source_file_is_skipped() -> None:
    """Only test nodes whose source_file matches the given source_file
    are linked."""
    nodes = [
        _make_node("test_a", "test_foo()", "/repo/tests/test_a.py", "L5"),
        _make_node("test_b", "test_bar()", "/repo/tests/test_b.py", "L10"),
        _make_node("p_foo", "foo()", "/repo/a.py", "L3"),
        _make_node("p_bar", "bar()", "/repo/b.py", "L8"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_a.py")

    assert created == 2  # only test_a → foo linked
    test_of = next(e for e in edges if e["relation"] == "test_of")
    assert test_of["source"] == "test_a"


def test_only_non_test_nodes_in_source_file() -> None:
    """When the source file has only production code (no test nodes), no links."""
    nodes = [
        _make_node("calc_calc", "calculate()", "/repo/calc.py", "L3"),
        _make_node("calc_add", "add()", "/repo/calc.py", "L8"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/calc.py")
    assert created == 0


# ---------------------------------------------------------------------------
# Self-link prevention
# ---------------------------------------------------------------------------


def test_test_node_self_link_is_skipped() -> None:
    """When test node and production node have the same id, no edge created."""
    nodes = [
        _make_node("same_id", "test_calculate()", "/repo/tests/test_calc.py", "L5"),
        _make_node("same_id", "calculate()", "/repo/calc.py", "L3"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")
    assert created == 0


# ---------------------------------------------------------------------------
# Multiple candidates
# ---------------------------------------------------------------------------


def test_multiple_production_candidates_stem_match_picks_first() -> None:
    """When multiple production nodes match in the correct stem, picks first."""
    nodes = [
        _make_node("test_calc", "test_calculate()", "/repo/tests/test_calc.py", "L5"),
        _make_node("calc_v1", "calculate()", "/repo/calc.py", "L3"),
        _make_node("calc_v2", "calculate()", "/repo/calc.py", "L15"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")

    assert created == 2
    test_of = next(e for e in edges if e["relation"] == "test_of")
    assert test_of["target"] == "calc_v1"


def test_any_stem_match_multiple_candidates() -> None:
    """Fallback any-stem match picks first available candidate."""
    nodes = [
        _make_node("test_x", "test_foo()", "/repo/tests/test_x.py", "L5"),
        _make_node("a_foo", "foo()", "/repo/a.py", "L3"),
        _make_node("b_foo", "foo()", "/repo/b.py", "L8"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_x.py")
    assert created == 2


# ---------------------------------------------------------------------------
# Edge metadata verification
# ---------------------------------------------------------------------------


def test_created_test_of_edge_has_all_required_fields() -> None:
    """Verify all expected keys and values in a created test_of edge."""
    nodes = [
        _make_node("test_calc", "test_calculate()", "/repo/tests/test_calc.py", "L5"),
        _make_node("calc", "calculate()", "/repo/calc.py", "L3"),
    ]
    edges: list[dict] = []
    resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")

    test_of = next(e for e in edges if e["relation"] == "test_of")
    assert test_of["source"] == "test_calc"
    assert test_of["target"] == "calc"
    assert test_of["relation"] == "test_of"
    assert test_of["confidence"] == "INFERRED"
    assert test_of["confidence_score"] == 0.8
    assert test_of["source_file"] == "/repo/tests/test_calc.py"
    assert test_of["source_location"] == "L5"
    assert test_of["weight"] == 1.0
    assert test_of["context"] == "test_linking"
    assert test_of["metadata"] == {
        "resolver": "python_test_linking",
        "test_label": "test_calculate()",
        "production_name": "calculate()",
    }


def test_reverse_tests_edge_has_swapped_source_target() -> None:
    """The reverse 'tests' edge swaps source and target."""
    nodes = [
        _make_node("test_calc", "test_calculate()", "/repo/tests/test_calc.py", "L5"),
        _make_node("calc", "calculate()", "/repo/calc.py", "L3"),
    ]
    edges: list[dict] = []
    resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")

    tests_edge = next(e for e in edges if e["relation"] == "tests")
    assert tests_edge["source"] == "calc"
    assert tests_edge["target"] == "test_calc"
    assert tests_edge["relation"] == "tests"
    assert tests_edge["context"] == "test_linking"


def test_reverse_tests_edge_metadata_matches_test_of() -> None:
    """Reverse edge carries the same metadata as test_of edge."""
    nodes = [
        _make_node("test_calc", "test_calculate()", "/repo/tests/test_calc.py", "L5"),
        _make_node("calc", "calculate()", "/repo/calc.py", "L3"),
    ]
    edges: list[dict] = []
    resolve_python_test_edges(nodes, edges, "/repo/tests/test_calc.py")

    test_of = next(e for e in edges if e["relation"] == "test_of")
    tests_edge = next(e for e in edges if e["relation"] == "tests")
    assert tests_edge["metadata"] == test_of["metadata"]
    assert tests_edge["confidence"] == test_of["confidence"]
    assert tests_edge["confidence_score"] == test_of["confidence_score"]


# ---------------------------------------------------------------------------
# Test files that don't import production code
# ---------------------------------------------------------------------------


def test_test_file_with_no_imports_still_links_by_naming() -> None:
    """Test linking relies on naming convention, not import analysis.
    Even without import statements, the naming convention resolves."""
    nodes = [
        _make_node("test_e2e", "test_login_flow()", "/repo/tests/test_auth.py", "L12"),
        _make_node("auth_login", "login_flow()", "/repo/auth.py", "L45"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_auth.py")
    assert created == 2
    test_of = next(e for e in edges if e["relation"] == "test_of")
    assert test_of["source"] == "test_e2e"
    assert test_of["target"] == "auth_login"


def test_test_file_naming_does_not_match_any_production_stem() -> None:
    """When test file stem doesn't match any production file stem,
    falls back to any-stem match."""
    nodes = [
        _make_node("test_x_foo", "test_foo()", "/repo/tests/test_x.py", "L5"),
        # foo() is in bar.py — stem doesn't match test_x → x
        _make_node("bar_foo", "foo()", "/repo/bar.py", "L3"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_x.py")
    assert created == 2


# ---------------------------------------------------------------------------
# Test suffix file naming convention
# ---------------------------------------------------------------------------


def test_test_suffix_file_linking() -> None:
    """Test file named calc_test.py links to calc.py via suffix convention."""
    nodes = [
        _make_node("t_add", "test_add()", "/repo/tests/calc_test.py", "L5"),
        _make_node("c_add", "add()", "/repo/calc.py", "L3"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/calc_test.py")
    assert created == 2
    test_of = next(e for e in edges if e["relation"] == "test_of")
    assert test_of["source"] == "t_add"
    assert test_of["target"] == "c_add"


# ---------------------------------------------------------------------------
# Test method naming convention
# ---------------------------------------------------------------------------


def test_test_method_links_via_test_prefix() -> None:
    """A test method like test_login is treated as a test function for linking."""
    nodes = [
        _make_node("test_method", "test_login()", "/repo/tests/test_auth.py", "L20"),
        _make_node("auth_login", "login()", "/repo/auth.py", "L5"),
    ]
    edges: list[dict] = []
    created = resolve_python_test_edges(nodes, edges, "/repo/tests/test_auth.py")
    assert created == 2
