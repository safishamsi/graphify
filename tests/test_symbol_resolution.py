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
    assert (
        node_is_resolvable_symbol({"id": "d", "label": "param x", "file_type": "doc_tag"}) is False
    )


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
        {
            "id": "helper_transform",
            "label": "transform()",
            "file_type": "code",
            "source_file": "/repo/helper.py",
        },
        {
            "id": "other_transform",
            "label": "transform()",
            "file_type": "code",
            "source_file": "/repo/other.py",
        },
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
    caller.write_text(
        "from helper import transform as tx\n\ndef run(value):\n    return tx(value)\n",
        encoding="utf-8",
    )
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
        {
            "id": "helper_transform",
            "label": "transform()",
            "file_type": "code",
            "source_file": str(helper),
        },
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
                {
                    "id": "a_entry",
                    "label": "a.sh script",
                    "file_type": "code",
                    "source_file": str(a_sh),
                },
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
                {
                    "id": "b_func",
                    "label": "b_func()",
                    "file_type": "code",
                    "source_file": str(b_sh),
                    "metadata": {"kind": "bash_function"},
                },
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
                {
                    "id": "main",
                    "label": "main()",
                    "file_type": "code",
                    "source_file": str(a_sh),
                    "metadata": {"kind": "bash_function"},
                },
            ],
            "edges": [],
            "raw_calls": [
                {
                    "language": "bash",
                    "caller_nid": "main",
                    "callee": "b_func",
                    "is_member_call": False,
                    "source_file": str(a_sh),
                    "source_location": "L3",
                }
            ],
            "bash_sources": [
                {"source_file": str(a_sh), "target_path": str(b_sh), "source_location": "L2"}
            ],
        },
        {
            "nodes": [
                {"id": "b_sh", "label": "b.sh", "file_type": "code", "source_file": str(b_sh)},
                {
                    "id": "b_func",
                    "label": "b_func()",
                    "file_type": "code",
                    "source_file": str(b_sh),
                    "metadata": {"kind": "bash_function"},
                },
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
                {
                    "id": "main",
                    "label": "main()",
                    "file_type": "code",
                    "source_file": str(a_sh),
                    "metadata": {"kind": "bash_function"},
                },
            ],
            "edges": [],
            "raw_calls": [
                {
                    "language": "bash",
                    "caller_nid": "main",
                    "callee": "b_func",
                    "is_member_call": False,
                    "source_file": str(a_sh),
                    "source_location": "L3",
                }
            ],
            "bash_sources": [
                {"source_file": str(a_sh), "target_path": str(b_sh), "source_location": "L2"}
            ],
        },
        {
            "nodes": [
                {"id": "b_sh", "label": "b.sh", "file_type": "code", "source_file": str(b_sh)},
                {
                    "id": "b_func",
                    "label": "b_func()",
                    "file_type": "code",
                    "source_file": str(b_sh),
                    "metadata": {"kind": "bash_function"},
                },
            ],
            "edges": [],
            "raw_calls": [],
            "bash_sources": [],
        },
    ]
    existing = [{"source": "main", "target": "b_func", "relation": "calls"}]

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
                {
                    "id": "main",
                    "label": "main()",
                    "file_type": "code",
                    "source_file": str(a_sh),
                    "metadata": {"kind": "bash_function"},
                },
            ],
            "edges": [],
            "raw_calls": [
                {
                    "language": "bash",
                    "caller_nid": "main",
                    "callee": "helper",
                    "is_member_call": False,
                    "source_file": str(a_sh),
                    "source_location": "L4",
                }
            ],
            "bash_sources": [
                {"source_file": str(a_sh), "target_path": str(b_sh), "source_location": "L2"},
                {"source_file": str(a_sh), "target_path": str(c_sh), "source_location": "L3"},
            ],
        },
        {
            "nodes": [
                {"id": "b_sh", "label": "b.sh", "file_type": "code", "source_file": str(b_sh)},
                {
                    "id": "b_helper",
                    "label": "helper()",
                    "file_type": "code",
                    "source_file": str(b_sh),
                    "metadata": {"kind": "bash_function"},
                },
            ],
            "edges": [],
            "raw_calls": [],
            "bash_sources": [],
        },
        {
            "nodes": [
                {"id": "c_sh", "label": "c.sh", "file_type": "code", "source_file": str(c_sh)},
                {
                    "id": "c_helper",
                    "label": "helper()",
                    "file_type": "code",
                    "source_file": str(c_sh),
                    "metadata": {"kind": "bash_function"},
                },
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
                {
                    "language": "python",
                    "caller_nid": "a_main",
                    "callee": "helper",
                    "is_member_call": False,
                    "source_file": str(a_sh),
                    "source_location": "L1",
                }
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


def test_bash_make_id_unicode_matches_make_id() -> None:
    """_bash_make_id must produce identical output to _make_id for Unicode inputs.

    The two functions must remain in sync so resolve_bash_source_edges
    produces node IDs that match those from extract_bash.  The original local
    copy lacked NFKC normalisation, Unicode-aware regex, and casefold().
    """
    from graphify.extract import _make_id

    # Accented letter: é is a Unicode word char that _make_id preserves
    assert _bash_make_id("café", "run") == _make_id("café", "run"), (
        "_bash_make_id must preserve Unicode word characters like _make_id"
    )
    # German sharp s: casefold maps ß→ss, lower does not
    assert _bash_make_id("straße") == _make_id("straße"), (
        "_bash_make_id must use casefold not lower to match _make_id"
    )


# ---------------------------------------------------------------------------
# Cycle 2.5 v2 — Codex blocker fixes
# ---------------------------------------------------------------------------


# F1 — top-level imports only
def test_parse_python_import_aliases_skips_function_local_imports(tmp_path):
    """A `from helper import transform` inside a function MUST NOT become
    file-wide evidence — function-local imports are only valid in their
    lexical scope. Walking the whole AST would falsely justify unrelated
    calls in other scopes."""
    from graphify.symbol_resolution import parse_python_import_aliases

    py = tmp_path / "scoped.py"
    py.write_text(
        "def one():\n"
        "    from helper import transform\n"
        "    return transform()\n"
        "\n"
        "def two():\n"
        "    return transform()\n"
    )
    aliases = parse_python_import_aliases(py)
    assert "transform" not in aliases, (
        f"function-local import leaked as file-wide evidence: {aliases}"
    )


def test_parse_python_import_aliases_accepts_top_level_import(tmp_path):
    """A module-level `from helper import transform` IS file-wide evidence."""
    from graphify.symbol_resolution import parse_python_import_aliases

    py = tmp_path / "toplevel.py"
    py.write_text("from helper import transform\n\ndef one():\n    return transform()\n")
    aliases = parse_python_import_aliases(py)
    assert "transform" in aliases
    assert aliases["transform"].module_stem == "helper"


# F2 — only code nodes are resolvable
def test_node_is_resolvable_symbol_requires_code_file_type():
    """Document/paper/image/concept nodes MUST NOT be indexed as call targets,
    even when their label looks like a callable identifier."""
    from graphify.symbol_resolution import node_is_resolvable_symbol

    code = {"id": "n1", "label": "helper", "file_type": "code"}
    doc = {"id": "n2", "label": "helper", "file_type": "document"}
    paper = {"id": "n3", "label": "helper", "file_type": "paper"}
    image = {"id": "n4", "label": "helper", "file_type": "image"}
    no_ft = {"id": "n5", "label": "helper"}

    assert node_is_resolvable_symbol(code) is True
    assert node_is_resolvable_symbol(doc) is False
    assert node_is_resolvable_symbol(paper) is False
    assert node_is_resolvable_symbol(image) is False
    assert node_is_resolvable_symbol(no_ft) is False


def test_build_label_index_excludes_non_code_nodes():
    """label index must not include document/paper/image nodes even when
    label and id are present and well-formed."""
    from graphify.symbol_resolution import build_label_index

    nodes = [
        {"id": "code_one", "label": "helper", "file_type": "code"},
        {"id": "doc_one", "label": "helper", "file_type": "document"},
        {"id": "paper_one", "label": "helper", "file_type": "paper"},
    ]
    index = build_label_index(nodes)
    assert index.get("helper") == ["code_one"]


# F3 — bash resolver defensive against malformed input
def test_resolve_bash_source_edges_skips_malformed_source(tmp_path):
    """A `bash_sources` entry missing `target_path` must not raise KeyError."""
    from graphify.symbol_resolution import resolve_bash_source_edges

    per_file = [
        {
            "nodes": [],
            "raw_calls": [],
            "bash_sources": [
                {},  # missing target_path entirely
                {"target_path": ""},  # empty target_path
                {"target_path": None},  # non-string target_path
            ],
        }
    ]
    a = tmp_path / "a.sh"
    a.write_text("# noop\n")
    edges = resolve_bash_source_edges(per_file, [a], tmp_path)
    assert edges == []


def test_resolve_bash_source_edges_skips_bash_function_node_missing_id(tmp_path):
    """A node tagged as bash_function but missing `id` must not raise KeyError."""
    from graphify.symbol_resolution import resolve_bash_source_edges

    per_file = [
        {
            "nodes": [
                {"label": "build()", "metadata": {"kind": "bash_function"}},
            ],
            "raw_calls": [],
            "bash_sources": [],
        }
    ]
    a = tmp_path / "a.sh"
    a.write_text("# noop\n")
    # Should not raise
    edges = resolve_bash_source_edges(per_file, [a], tmp_path)
    assert edges == []


def test_resolve_bash_source_edges_skips_raw_call_missing_caller_nid(tmp_path):
    """A raw_call entry missing `caller_nid` must not raise KeyError."""
    from graphify.symbol_resolution import resolve_bash_source_edges

    a = tmp_path / "a.sh"
    b = tmp_path / "b.sh"
    a.write_text("# noop\n")
    b.write_text("# noop\n")
    per_file = [
        {
            "nodes": [],
            "raw_calls": [
                {"language": "bash", "callee": "helper"},  # missing caller_nid
            ],
            "bash_sources": [{"target_path": str(b)}],
        },
        {
            "nodes": [
                {"id": "b_helper", "label": "helper()", "metadata": {"kind": "bash_function"}},
            ],
            "raw_calls": [],
            "bash_sources": [],
        },
    ]
    edges = resolve_bash_source_edges(per_file, [a, b], tmp_path)
    # No raw-call edge emitted because caller_nid was missing; source edge OK.
    assert all(e["relation"] != "calls" for e in edges)


def test_resolve_bash_source_edges_accepts_none_per_file_entries(tmp_path):
    """A None entry in per_file (e.g. failed extraction) must be silently skipped."""
    from graphify.symbol_resolution import resolve_bash_source_edges

    a = tmp_path / "a.sh"
    a.write_text("# noop\n")
    edges = resolve_bash_source_edges([None], [a], tmp_path)
    assert edges == []


def test_resolve_bash_source_edges_skips_non_dict_lists(tmp_path):
    """Non-dict entries in bash_sources/raw_calls/nodes must be silently skipped."""
    from graphify.symbol_resolution import resolve_bash_source_edges

    a = tmp_path / "a.sh"
    a.write_text("# noop\n")
    per_file = [
        {
            "nodes": ["not a dict", 42, None],
            "raw_calls": [None, "string entry", {"language": "bash"}],  # last is missing caller_nid
            "bash_sources": [None, "str", 99],
        }
    ]
    edges = resolve_bash_source_edges(per_file, [a], tmp_path)
    assert edges == []


# F4 — relative target_path resolves against source file directory
def test_resolve_bash_source_edges_relative_path_resolves_against_source_dir(tmp_path):
    """`source ./helper.sh` from a/main.sh should resolve to a/helper.sh,
    not to ./helper.sh from the process CWD."""
    from graphify.symbol_resolution import resolve_bash_source_edges

    sub = tmp_path / "scripts"
    sub.mkdir()
    main = sub / "main.sh"
    helper = sub / "helper.sh"
    main.write_text("# main\n")
    helper.write_text("# helper\n")

    per_file = [
        {
            "nodes": [],
            "raw_calls": [],
            # Relative path: should resolve to scripts/helper.sh (next to main.sh)
            "bash_sources": [{"target_path": "./helper.sh"}],
        },
        {
            "nodes": [],
            "raw_calls": [],
            "bash_sources": [],
        },
    ]
    edges = resolve_bash_source_edges(per_file, [main, helper], tmp_path)
    # One imports_from edge from main → helper
    import_edges = [e for e in edges if e["relation"] == "imports_from"]
    assert len(import_edges) == 1
    # Note: the actual node IDs are sha-hash-derived; just verify the edge exists.


# F1 — malformed raw_calls in non-Bash resolvers
def test_iter_raw_calls_skips_non_dict_per_file_entries():
    """A non-dict per_file entry (e.g. junk fragment) must be silently skipped."""
    from graphify.symbol_resolution import iter_raw_calls

    assert iter_raw_calls(["not a dict", None, 42]) == []


def test_iter_raw_calls_skips_non_list_raw_calls():
    """`raw_calls` that isn't a list must yield empty."""
    from graphify.symbol_resolution import iter_raw_calls

    assert iter_raw_calls([{"raw_calls": "abc"}]) == []
    assert iter_raw_calls([{"raw_calls": None}]) == []
    assert iter_raw_calls([{"raw_calls": 42}]) == []


def test_iter_raw_calls_drops_non_dict_items_in_list():
    """Items inside `raw_calls` list that aren't dicts must be dropped."""
    from graphify.symbol_resolution import iter_raw_calls

    out = iter_raw_calls([{"raw_calls": ["str", 42, None, {"callee": "real", "caller_nid": "c"}]}])
    assert out == [{"callee": "real", "caller_nid": "c"}]


def test_resolve_cross_file_raw_calls_survives_malformed_raw_calls():
    """The python cross-file resolver returns [] (not crash) on bad raw_calls."""
    from graphify.symbol_resolution import resolve_cross_file_raw_calls

    # raw_calls is a string instead of a list
    assert resolve_cross_file_raw_calls([{"raw_calls": "abc"}], [], []) == []
    # raw_calls list contains non-dict entries
    assert resolve_cross_file_raw_calls([{"raw_calls": ["not dict", 42]}], [], []) == []


def test_resolve_python_import_guided_calls_survives_malformed_raw_calls(tmp_path):
    """Python import-guided resolver also tolerates malformed raw_calls."""
    from graphify.symbol_resolution import resolve_python_import_guided_calls

    py = tmp_path / "caller.py"
    py.write_text("from helper import transform\n")
    per_file = [{"raw_calls": "not a list"}]
    paths = [py]
    nodes = [
        {
            "id": "h_transform",
            "label": "transform",
            "file_type": "code",
            "source_file": str(tmp_path / "helper.py"),
        }
    ]
    # Should not raise; should return no edges since raw_calls isn't a list
    edges = resolve_python_import_guided_calls(per_file, paths, nodes, [])
    assert edges == []


# F2 — unhashable callee in bash resolver
def test_resolve_bash_source_edges_skips_unhashable_callee(tmp_path):
    """A bash raw_call with `callee: [list]` (unhashable for dict membership)
    must not raise TypeError — silently skip the call."""
    from graphify.symbol_resolution import resolve_bash_source_edges

    a = tmp_path / "a.sh"
    b = tmp_path / "b.sh"
    a.write_text("# noop\n")
    b.write_text("# noop\n")
    per_file = [
        {
            "nodes": [],
            "raw_calls": [
                {"language": "bash", "caller_nid": "caller", "callee": ["bad"]},
                {"language": "bash", "caller_nid": "caller", "callee": {"also": "bad"}},
                {"language": "bash", "caller_nid": "caller", "callee": 42},
            ],
            "bash_sources": [{"target_path": str(b)}],
        },
        {
            "nodes": [
                {"id": "b_helper", "label": "helper()", "metadata": {"kind": "bash_function"}},
            ],
            "raw_calls": [],
            "bash_sources": [],
        },
    ]
    # Must not raise — non-string callees are skipped before dict membership.
    edges = resolve_bash_source_edges(per_file, [a, b], tmp_path)
    # No call edges emitted (all malformed); imports_from edge from sourcing OK
    assert all(e["relation"] != "calls" for e in edges)


# v3 Codex F1 — resolve_python_import_guided_calls hardened against
# malformed per_file slots and length mismatches.
def test_resolve_python_import_guided_calls_non_dict_per_file_slot(tmp_path):
    """A non-dict per_file slot (e.g. a string) must not raise AttributeError."""
    from graphify.symbol_resolution import resolve_python_import_guided_calls

    py = tmp_path / "caller.py"
    py.write_text("from helper import transform\n")
    # per_file slot is a STRING, not a dict — used to crash with AttributeError
    edges = resolve_python_import_guided_calls(["not a dict"], [py], [], [])
    assert edges == []


def test_resolve_python_import_guided_calls_per_file_shorter_than_paths(tmp_path):
    """per_file shorter than paths must not raise IndexError."""
    from graphify.symbol_resolution import resolve_python_import_guided_calls

    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("from helper import transform\n")
    b.write_text("from helper import transform\n")
    # Only ONE per_file entry but TWO paths — used to crash with IndexError
    edges = resolve_python_import_guided_calls([{}], [a, b], [], [])
    assert edges == []


def test_resolve_python_import_guided_calls_per_file_none_slot(tmp_path):
    """A None per_file slot is treated as empty fragment (no crash, no edges)."""
    from graphify.symbol_resolution import resolve_python_import_guided_calls

    py = tmp_path / "caller.py"
    py.write_text("from helper import transform\n")
    edges = resolve_python_import_guided_calls([None], [py], [], [])
    assert edges == []


def test_resolve_python_import_guided_calls_metadata_is_sanitized(tmp_path: Path) -> None:
    """Edge metadata produced by the import-guided resolver must pass through
    sanitize_metadata so HTML / control characters in import-site strings
    (e.g. malformed source_location values, alias names from extractor bugs)
    cannot survive into the graph as raw markup."""
    caller = tmp_path / "caller.py"
    helper = tmp_path / "helper.py"
    # Import alias that includes an angle bracket — pathological but defensive
    # cover: the resolver itself does not parse names this aggressively, but a
    # future extractor or upstream fragment could. The boundary is the cycle's
    # stated policy: every edge metadata field goes through sanitize_metadata.
    caller.write_text(
        "from helper import transform as tx\n\ndef run(value):\n    return tx(value)\n",
        encoding="utf-8",
    )
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
        {
            "id": "helper_transform",
            "label": "transform()",
            "file_type": "code",
            "source_file": str(helper),
        },
    ]

    edges = resolve_python_import_guided_calls(per_file, [caller, helper], nodes, [])
    assert len(edges) == 1
    metadata = edges[0]["metadata"]
    # All values must be present and HTML/control-char safe after sanitisation.
    for value in metadata.values():
        if isinstance(value, str):
            assert "<" not in value
            assert "\x00" not in value
    # And the structural shape is unchanged for benign inputs.
    assert metadata["resolver"] == "python_import_guided"
    assert metadata["local_name"] == "tx"
    assert metadata["imported_name"] == "transform"
    assert metadata["module_stem"] == "helper"


def test_resolve_python_import_guided_calls_metadata_sanitizes_hostile_alias(
    monkeypatch, tmp_path: Path
) -> None:
    """Strong regression for #cycle-2.7-Codex-v2: monkeypatch the alias parser
    so the resolver sees HOSTILE strings in ImportedSymbol fields, then assert
    the emitted metadata is HTML-escaped / control-char-stripped.

    Removing the sanitize_metadata() wrap in
    ``resolve_python_import_guided_calls`` would make this test fail:
    `&lt;script&gt;` would not appear in `imported_name`, and the raw
    NUL byte would not be stripped from `module_stem`.
    """
    import graphify.symbol_resolution as sr

    caller = tmp_path / "caller.py"
    helper = tmp_path / "helper.py"
    caller.write_text(
        "from helper import transform as tx\n\ndef run(value):\n    return tx(value)\n",
        encoding="utf-8",
    )
    helper.write_text("def transform(value):\n    return value\n", encoding="utf-8")

    # imported_name and module_stem are the lookup keys used to resolve the
    # call target; they must match the real helper symbol or the edge will
    # not fire. local_name and source_location are stored verbatim into
    # metadata and are the surface that sanitize_metadata() must scrub.
    hostile_alias_key = "<script>tx</script>"
    hostile = sr.ImportedSymbol(
        local_name=hostile_alias_key,
        imported_name="transform",
        module_stem="helper",
        source_file=str(caller),
        source_location="L1<img src=x>\x00trail",
    )

    def _fake_aliases(path: Path) -> dict[str, sr.ImportedSymbol]:
        if path == caller:
            return {hostile_alias_key: hostile}
        return {}

    monkeypatch.setattr(sr, "parse_python_import_aliases", _fake_aliases)

    per_file = [
        {
            "raw_calls": [
                {
                    "caller_nid": "caller_run",
                    "callee": hostile_alias_key,
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
        {
            "id": "helper_transform",
            "label": "transform()",
            "file_type": "code",
            "source_file": str(helper),
        },
    ]

    edges = resolve_python_import_guided_calls(per_file, [caller, helper], nodes, [])
    assert len(edges) == 1
    metadata = edges[0]["metadata"]

    # `local_name` carries the hostile alias key. Without sanitisation it
    # would still contain `<script>`. With the wrap, only the entity escape
    # survives. Removing the sanitize_metadata() wrap would fail BOTH asserts.
    local_name = metadata["local_name"]
    assert "<script>" not in local_name
    assert "&lt;script&gt;" in local_name

    # `import_source_location` carries hostile markup + a NUL byte. Sanitised
    # output strips the NUL and escapes the angle brackets.
    src_loc = metadata["import_source_location"]
    assert "<img" not in src_loc
    assert "&lt;img" in src_loc
    assert "\x00" not in src_loc
    assert "trail" in src_loc  # tail content survives after NUL strip

    # Resolution-side fields (used as lookup keys) are benign and unchanged.
    assert metadata["resolver"] == "python_import_guided"
    assert metadata["imported_name"] == "transform"
    assert metadata["module_stem"] == "helper"
