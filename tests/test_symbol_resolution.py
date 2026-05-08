"""Tests for graphify.symbol_resolution."""
from __future__ import annotations

from pathlib import Path

from graphify.symbol_resolution import (
    _bash_make_id,
    build_label_index,
    build_python_symbol_index,
    find_unique_python_symbol,
    node_is_resolvable_symbol,
    normalise_callable_label,
    parse_python_import_aliases,
    resolve_bash_source_edges,
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


# ═══════════════════════════════════════════════════════════════════════════════
# ── Bash source edges resolver tests ──────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════


def test_bash_call_resolver_emits_source_edges(tmp_path: Path) -> None:
    a_sh = tmp_path / "a.sh"
    b_sh = tmp_path / "b.sh"
    a_sh.write_text("#!/usr/bin/env bash\nsource ./b.sh\n")
    b_sh.write_text("#!/usr/bin/env bash\nb_func() { echo ok; }\n")

    per_file = [
        {
            "nodes": [
                {"id": "a_sh", "label": "a.sh", "file_type": "code", "source_file": str(a_sh)},
                {"id": "a_entry", "label": "a.sh script", "file_type": "code", "source_file": str(a_sh)},
            ],
            "edges": [],
            "raw_calls": [],
            "bash_sources": [
                {"source_file": str(a_sh), "target_path": str(b_sh), "source_location": "L2"}
            ],
        },
        {
            "nodes": [
                {"id": "b_sh", "label": "b.sh", "file_type": "code", "source_file": str(b_sh)},
                {"id": "b_func", "label": "b_func()", "file_type": "code", "source_file": str(b_sh),
                 "metadata": {"kind": "bash_function"}},
            ],
            "edges": [],
            "raw_calls": [],
            "bash_sources": [],
        },
    ]

    edges = resolve_bash_source_edges(per_file, [a_sh, b_sh], tmp_path)

    imports = [e for e in edges if e["relation"] == "imports_from"]
    assert len(imports) == 1
    assert imports[0]["confidence"] == "EXTRACTED"


def test_bash_call_resolver_emits_call_edges_from_sourced_files(tmp_path: Path) -> None:
    a_sh = tmp_path / "a.sh"
    b_sh = tmp_path / "b.sh"
    a_sh.write_text("#!/usr/bin/env bash\nsource ./b.sh\nmain() { b_func; }\n")
    b_sh.write_text("#!/usr/bin/env bash\nb_func() { echo ok; }\n")

    per_file = [
        {
            "nodes": [
                {"id": "a_sh", "label": "a.sh", "file_type": "code", "source_file": str(a_sh)},
                {"id": "main", "label": "main()", "file_type": "code", "source_file": str(a_sh),
                 "metadata": {"kind": "bash_function"}},
            ],
            "edges": [],
            "raw_calls": [
                {"language": "bash", "caller_nid": "main", "callee": "b_func",
                 "is_member_call": False, "source_file": str(a_sh), "source_location": "L3"}
            ],
            "bash_sources": [
                {"source_file": str(a_sh), "target_path": str(b_sh), "source_location": "L2"}
            ],
        },
        {
            "nodes": [
                {"id": "b_sh", "label": "b.sh", "file_type": "code", "source_file": str(b_sh)},
                {"id": "b_func", "label": "b_func()", "file_type": "code", "source_file": str(b_sh),
                 "metadata": {"kind": "bash_function"}},
            ],
            "edges": [],
            "raw_calls": [],
            "bash_sources": [],
        },
    ]

    edges = resolve_bash_source_edges(per_file, [a_sh, b_sh], tmp_path)

    calls = [e for e in edges if e["relation"] == "calls"]
    assert len(calls) == 1
    assert calls[0]["source"] == "main"
    assert calls[0]["target"] == "b_func"
    assert calls[0]["confidence"] == "EXTRACTED"


def test_bash_call_resolver_skips_existing_pair(tmp_path: Path) -> None:
    a_sh = tmp_path / "a.sh"
    b_sh = tmp_path / "b.sh"
    a_sh.write_text("#!/usr/bin/env bash\nsource ./b.sh\nmain() { b_func; }\n")
    b_sh.write_text("#!/usr/bin/env bash\nb_func() { echo ok; }\n")

    per_file = [
        {
            "nodes": [
                {"id": "a_sh", "label": "a.sh", "file_type": "code", "source_file": str(a_sh)},
                {"id": "main", "label": "main()", "file_type": "code", "source_file": str(a_sh),
                 "metadata": {"kind": "bash_function"}},
            ],
            "edges": [],
            "raw_calls": [
                {"language": "bash", "caller_nid": "main", "callee": "b_func",
                 "is_member_call": False, "source_file": str(a_sh), "source_location": "L3"}
            ],
            "bash_sources": [
                {"source_file": str(a_sh), "target_path": str(b_sh), "source_location": "L2"}
            ],
        },
        {
            "nodes": [
                {"id": "b_sh", "label": "b.sh", "file_type": "code", "source_file": str(b_sh)},
                {"id": "b_func", "label": "b_func()", "file_type": "code", "source_file": str(b_sh),
                 "metadata": {"kind": "bash_function"}},
            ],
            "edges": [],
            "raw_calls": [],
            "bash_sources": [],
        },
    ]
    existing = [
        {"source": "main", "target": "b_func", "relation": "calls"}
    ]

    edges = resolve_bash_source_edges(per_file, [a_sh, b_sh], tmp_path, existing_edges=existing)

    calls = [e for e in edges if e["relation"] == "calls"]
    assert len(calls) == 0, f"Should skip existing pair but got: {calls}"


def test_bash_call_resolver_skips_ambiguous_multiple_candidates(tmp_path: Path) -> None:
    """When a callee function is defined in multiple sourced files, skip it."""
    a_sh = tmp_path / "a.sh"
    b_sh = tmp_path / "b.sh"
    c_sh = tmp_path / "c.sh"
    a_sh.write_text("#!/usr/bin/env bash\nsource ./b.sh\nsource ./c.sh\nmain() { helper; }\n")
    b_sh.write_text("#!/usr/bin/env bash\nhelper() { echo b; }\n")
    c_sh.write_text("#!/usr/bin/env bash\nhelper() { echo c; }\n")

    per_file = [
        {
            "nodes": [
                {"id": "a_sh", "label": "a.sh", "file_type": "code", "source_file": str(a_sh)},
                {"id": "main", "label": "main()", "file_type": "code", "source_file": str(a_sh),
                 "metadata": {"kind": "bash_function"}},
            ],
            "edges": [],
            "raw_calls": [
                {"language": "bash", "caller_nid": "main", "callee": "helper",
                 "is_member_call": False, "source_file": str(a_sh), "source_location": "L4"}
            ],
            "bash_sources": [
                {"source_file": str(a_sh), "target_path": str(b_sh), "source_location": "L2"},
                {"source_file": str(a_sh), "target_path": str(c_sh), "source_location": "L3"},
            ],
        },
        {
            "nodes": [
                {"id": "b_sh", "label": "b.sh", "file_type": "code", "source_file": str(b_sh)},
                {"id": "b_helper", "label": "helper()", "file_type": "code", "source_file": str(b_sh),
                 "metadata": {"kind": "bash_function"}},
            ],
            "edges": [],
            "raw_calls": [],
            "bash_sources": [],
        },
        {
            "nodes": [
                {"id": "c_sh", "label": "c.sh", "file_type": "code", "source_file": str(c_sh)},
                {"id": "c_helper", "label": "helper()", "file_type": "code", "source_file": str(c_sh),
                 "metadata": {"kind": "bash_function"}},
            ],
            "edges": [],
            "raw_calls": [],
            "bash_sources": [],
        },
    ]

    edges = resolve_bash_source_edges(per_file, [a_sh, b_sh, c_sh], tmp_path)

    calls = [e for e in edges if e["relation"] == "calls"]
    # helper() is defined in both b.sh and c.sh → ambiguous → should be skipped
    assert len(calls) == 0, f"Should skip ambiguous callee but got: {calls}"


def test_bash_call_resolver_skips_non_bash_raw_calls(tmp_path: Path) -> None:
    """Non-bash raw_calls inside sourced-file per_file entries are ignored."""
    a_sh = tmp_path / "a.sh"
    a_sh.write_text("#!/usr/bin/env bash\n")

    per_file = [
        {
            "nodes": [
                {"id": "a_sh", "label": "a.sh", "file_type": "code", "source_file": str(a_sh)},
            ],
            "edges": [],
            "raw_calls": [
                {"language": "python", "caller_nid": "a_main", "callee": "helper",
                 "is_member_call": False, "source_file": str(a_sh), "source_location": "L1"}
            ],
            "bash_sources": [],
        },
    ]

    edges = resolve_bash_source_edges(per_file, [a_sh], tmp_path)
    assert edges == [], f"Should ignore non-bash raw_calls but got: {edges}"


def test_bash_make_id_identical_to_make_id() -> None:
    from graphify.extract import _make_id

    assert _bash_make_id("foo", "bar") == _make_id("foo", "bar")
    assert _bash_make_id("auth") == _make_id("auth")
    assert _bash_make_id("_module", "_helper") == _make_id("_module", "_helper")
    assert _bash_make_id("my-script", "main") == _make_id("my-script", "main")
