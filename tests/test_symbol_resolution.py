"""Tests for graphify.symbol_resolution."""
from __future__ import annotations

from pathlib import Path

from graphify.symbol_resolution import (
    build_label_index,
    build_python_symbol_index,
    find_unique_python_symbol,
    node_is_resolvable_symbol,
    normalise_callable_label,
    parse_python_import_aliases,
    resolve_cross_file_raw_calls,
    resolve_python_import_guided_calls,
)


def test_normalise_callable_label_strips_function_punctuation() -> None:
    assert normalise_callable_label("run()") == "run"
    assert normalise_callable_label(".process()") == "process"
    assert normalise_callable_label("  Execute  ") == "execute"


def test_node_is_resolvable_symbol_skips_rationale_and_doc_tags() -> None:
    assert node_is_resolvable_symbol({"id": "a", "label": "run()", "file_type": "code"}) is True
    assert node_is_resolvable_symbol({"id": "r", "label": "why", "file_type": "rationale"}) is False
    assert node_is_resolvable_symbol({"id": "d", "label": "param x", "file_type": "doc_tag"}) is False


def test_build_label_index_collects_unique_symbols() -> None:
    nodes = [
        {"id": "a_run", "label": "run()", "file_type": "code"},
        {"id": "b_run", "label": "run()", "file_type": "code"},
        {"id": "doc", "label": "run docs", "file_type": "doc_tag"},
    ]
    assert build_label_index(nodes) == {"run": ["a_run", "b_run"]}


def test_resolve_cross_file_raw_calls_emits_unique_unqualified_call() -> None:
    per_file = [
        {
            "raw_calls": [
                {
                    "caller_nid": "caller_run",
                    "callee": "helper",
                    "is_member_call": False,
                    "source_file": "caller.py",
                    "source_location": "L2",
                }
            ]
        }
    ]
    nodes = [
        {"id": "caller_run", "label": "run()", "file_type": "code"},
        {"id": "helper_helper", "label": "helper()", "file_type": "code"},
    ]
    edges = []

    resolved = resolve_cross_file_raw_calls(per_file, nodes, edges)

    assert resolved == [
        {
            "source": "caller_run",
            "target": "helper_helper",
            "relation": "calls",
            "context": "call",
            "confidence": "INFERRED",
            "confidence_score": 0.8,
            "source_file": "caller.py",
            "source_location": "L2",
            "weight": 1.0,
        }
    ]


def test_resolve_cross_file_raw_calls_skips_member_calls() -> None:
    per_file = [
        {
            "raw_calls": [
                {
                    "caller_nid": "caller_run",
                    "callee": "helper",
                    "is_member_call": True,
                    "source_file": "caller.py",
                    "source_location": "L2",
                }
            ]
        }
    ]
    nodes = [
        {"id": "caller_run", "label": "run()", "file_type": "code"},
        {"id": "helper_helper", "label": "helper()", "file_type": "code"},
    ]
    assert resolve_cross_file_raw_calls(per_file, nodes, []) == []


def test_resolve_cross_file_raw_calls_skips_ambiguous_duplicate_labels() -> None:
    per_file = [
        {
            "raw_calls": [
                {
                    "caller_nid": "caller_run",
                    "callee": "log",
                    "is_member_call": False,
                    "source_file": "caller.py",
                    "source_location": "L2",
                }
            ]
        }
    ]
    nodes = [
        {"id": "caller_run", "label": "run()", "file_type": "code"},
        {"id": "a_log", "label": "log()", "file_type": "code"},
        {"id": "b_log", "label": "log()", "file_type": "code"},
    ]
    assert resolve_cross_file_raw_calls(per_file, nodes, []) == []


def test_resolve_cross_file_raw_calls_skips_existing_pair() -> None:
    per_file = [
        {
            "raw_calls": [
                {
                    "caller_nid": "caller_run",
                    "callee": "helper",
                    "is_member_call": False,
                    "source_file": "caller.py",
                    "source_location": "L2",
                }
            ]
        }
    ]
    nodes = [
        {"id": "caller_run", "label": "run()", "file_type": "code"},
        {"id": "helper_helper", "label": "helper()", "file_type": "code"},
    ]
    edges = [{"source": "caller_run", "target": "helper_helper", "relation": "calls"}]
    assert resolve_cross_file_raw_calls(per_file, nodes, edges) == []


def test_parse_python_import_aliases_supports_from_import_alias(tmp_path: Path) -> None:
    src = tmp_path / "caller.py"
    src.write_text("from helper import transform as tx\n", encoding="utf-8")

    aliases = parse_python_import_aliases(src)

    assert set(aliases) == {"tx"}
    imported = aliases["tx"]
    assert imported.local_name == "tx"
    assert imported.imported_name == "transform"
    assert imported.module_stem == "helper"
    assert imported.source_location == "L1"


def test_build_python_symbol_index_uses_module_stem_and_label() -> None:
    nodes = [
        {"id": "helper_transform", "label": "transform()", "file_type": "code", "source_file": "/repo/helper.py"},
        {"id": "other_transform", "label": "transform()", "file_type": "code", "source_file": "/repo/other.py"},
    ]
    index = build_python_symbol_index(nodes)
    assert index[("helper", "transform")] == ["helper_transform"]
    assert index[("other", "transform")] == ["other_transform"]


def test_find_unique_python_symbol_returns_none_when_ambiguous(tmp_path: Path) -> None:
    src = tmp_path / "caller.py"
    src.write_text("from helper import transform\n", encoding="utf-8")
    imported = parse_python_import_aliases(src)["transform"]
    index = {("helper", "transform"): ["a", "b"]}
    assert find_unique_python_symbol(index, imported) is None


def test_resolve_python_import_guided_calls_emits_extracted_edge(tmp_path: Path) -> None:
    caller = tmp_path / "caller.py"
    helper = tmp_path / "helper.py"
    caller.write_text("from helper import transform as tx\n\ndef run(value):\n    return tx(value)\n", encoding="utf-8")
    helper.write_text("def transform(value):\n    return value\n", encoding="utf-8")

    per_file = [
        {
            "raw_calls": [
                {
                    "caller_nid": "caller_run",
                    "callee": "tx",
                    "is_member_call": False,
                    "source_file": str(caller),
                    "source_location": "L4",
                }
            ]
        },
        {"raw_calls": []},
    ]
    nodes = [
        {"id": "caller_run", "label": "run()", "file_type": "code", "source_file": str(caller)},
        {"id": "helper_transform", "label": "transform()", "file_type": "code", "source_file": str(helper)},
    ]

    edges = resolve_python_import_guided_calls(per_file, [caller, helper], nodes, [])

    assert edges == [
        {
            "source": "caller_run",
            "target": "helper_transform",
            "relation": "calls",
            "context": "import_guided_call",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": str(caller),
            "source_location": "L4",
            "weight": 1.0,
            "metadata": {
                "resolver": "python_import_guided",
                "local_name": "tx",
                "imported_name": "transform",
                "module_stem": "helper",
                "import_source_location": "L1",
            },
        }
    ]
