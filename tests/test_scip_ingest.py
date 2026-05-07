"""Comprehensive tests for graphify.scip_ingest."""
from __future__ import annotations

import pytest

from graphify.scip_ingest import (
    _build_scip_metadata,
    _make_scip_node_id,
    _scip_kind_to_file_type,
    ingest_scip_json,
)


# ---------------------------------------------------------------------------
# Valid JSON parsing — full-document smoke tests
# ---------------------------------------------------------------------------


def test_ingest_empty_doc_returns_empty_lists() -> None:
    """Empty dict input produces empty nodes and edges."""
    result = ingest_scip_json({})
    assert result == {"nodes": [], "edges": []}


def test_ingest_dict_without_documents_key() -> None:
    """documents key not present → no processing → empty result."""
    result = ingest_scip_json({"metadata": "some meta"})
    assert result == {"nodes": [], "edges": []}


def test_ingest_documents_not_a_list_is_skipped() -> None:
    """When documents is not a list, ingestion stops and returns empty."""
    result = ingest_scip_json({"documents": "not_a_list"})
    assert result == {"nodes": [], "edges": []}


def test_ingest_documents_empty_list() -> None:
    """Empty documents list produces empty nodes and edges."""
    result = ingest_scip_json({"documents": []})
    assert result == {"nodes": [], "edges": []}


def test_ingest_single_symbol_no_relationships() -> None:
    """A single symbol with no relationships yields one node and zero edges."""
    doc = {
        "documents": [
            {
                "relative_path": "src/main.py",
                "language": "python",
                "symbols": [
                    {
                        "symbol": "python/main.py:MainClass#",
                        "kind": "class",
                        "display_name": "MainClass",
                        "documentation": ["The main class"],
                        "relationships": [],
                        "occurrences": [{"range": [5, 0, 5, 9], "symbol": "python/main.py:MainClass#"}],
                    }
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert len(result["nodes"]) == 1
    assert len(result["edges"]) == 0

    node = result["nodes"][0]
    assert node["label"] == "MainClass"
    assert node["file_type"] == "code"
    assert node["source_file"] == "src/main.py"
    assert node["source_location"] == "L5"
    assert node["metadata"]["scip_symbol"] == "python/main.py:MainClass#"
    assert node["metadata"]["scip_kind"] == "class"
    assert node["metadata"]["scip_description"] == "The main class"


def test_ingest_symbol_without_display_name_uses_suffix() -> None:
    """When display_name is missing, label falls back to the portion after #."""
    doc = {
        "documents": [
            {
                "relative_path": "lib/helper.py",
                "symbols": [
                    {
                        "symbol": "python/helper.py:compute#run()",
                        "kind": "function",
                        "occurrences": [],
                        "relationships": [],
                    }
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert result["nodes"][0]["label"] == "run()"


def test_ingest_symbol_without_hash_uses_full_symbol_as_label() -> None:
    """When symbol has no #, the label is the full symbol id."""
    doc = {
        "documents": [
            {
                "relative_path": "lib/helper.py",
                "symbols": [
                    {
                        "symbol": "SimpleFunction",
                        "kind": "function",
                        "occurrences": [],
                        "relationships": [],
                    }
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert result["nodes"][0]["label"] == "SimpleFunction"


def test_ingest_symbol_without_occurrences_has_empty_source_location() -> None:
    """When occurrences list is empty, source_location is empty string."""
    doc = {
        "documents": [
            {
                "relative_path": "lib/a.py",
                "symbols": [
                    {
                        "symbol": "python/lib/a.py:Foo#",
                        "kind": "class",
                        "occurrences": [],
                        "relationships": [],
                    }
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert result["nodes"][0]["source_location"] == ""


def test_ingest_symbol_without_occurrences_key() -> None:
    """When occurrences key is missing entirely, falls back to empty source_location."""
    doc = {
        "documents": [
            {
                "relative_path": "lib/a.py",
                "symbols": [
                    {
                        "symbol": "python/lib/a.py:Foo#",
                        "kind": "class",
                        "relationships": [],
                    }
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert result["nodes"][0]["source_location"] == ""


def test_ingest_multiple_symbols_in_one_document() -> None:
    """Multiple symbols in a single document all become nodes."""
    doc = {
        "documents": [
            {
                "relative_path": "src/mod.py",
                "symbols": [
                    {"symbol": "python/mod.py:A#", "kind": "class", "display_name": "A", "occurrences": [], "relationships": []},
                    {"symbol": "python/mod.py:B#", "kind": "function", "display_name": "B", "occurrences": [], "relationships": []},
                    {"symbol": "python/mod.py:C#", "kind": "variable", "display_name": "C", "occurrences": [], "relationships": []},
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert len(result["nodes"]) == 3
    labels = {n["label"] for n in result["nodes"]}
    assert labels == {"A", "B", "C"}


def test_ingest_multiple_documents() -> None:
    """Symbols from multiple documents all become nodes."""
    doc = {
        "documents": [
            {
                "relative_path": "a.py",
                "symbols": [
                    {"symbol": "A#", "kind": "class", "occurrences": [], "relationships": []},
                ],
            },
            {
                "relative_path": "b.py",
                "symbols": [
                    {"symbol": "B#", "kind": "function", "occurrences": [], "relationships": []},
                ],
            },
        ]
    }
    result = ingest_scip_json(doc)
    assert len(result["nodes"]) == 2

    paths = {n["source_file"] for n in result["nodes"]}
    assert paths == {"a.py", "b.py"}


# ---------------------------------------------------------------------------
# Reference/definition resolution — relationship → edge mapping
# ---------------------------------------------------------------------------


def _make_symbol_doc(symbol_id: str, kind: str, rels: list[dict]) -> dict[str, object]:
    """Helper to build a minimal SCIP document with one symbol."""
    return {
        "documents": [
            {
                "relative_path": "src/main.py",
                "symbols": [
                    {
                        "symbol": symbol_id,
                        "kind": kind,
                        "display_name": symbol_id.split("#")[-1].strip("()"),
                        "occurrences": [{"range": [10, 0, 10, 20], "symbol": symbol_id}],
                        "relationships": rels,
                    }
                ],
            }
        ]
    }


def test_ingest_is_reference_emits_scip_ref_edge() -> None:
    """is_reference → relation 'scip_ref'."""
    doc = _make_symbol_doc(
        "python/main.py:MyClass#run()",
        "function",
        [{"symbol": "python/main.py:Helper#help()", "is_reference": True}],
    )
    result = ingest_scip_json(doc)
    assert len(result["edges"]) == 1
    assert result["edges"][0]["relation"] == "scip_ref"


def test_ingest_is_definition_emits_scip_def_edge() -> None:
    """is_definition → relation 'scip_def'."""
    doc = _make_symbol_doc(
        "python/main.py:MyClass#run()",
        "function",
        [{"symbol": "python/main.py:Base#run()", "is_definition": True}],
    )
    result = ingest_scip_json(doc)
    assert result["edges"][0]["relation"] == "scip_def"


def test_ingest_is_implementation_emits_scip_impl_edge() -> None:
    """is_implementation → relation 'scip_impl' (takes priority over is_definition)."""
    doc = _make_symbol_doc(
        "python/main.py:MyClass#run()",
        "function",
        [{"symbol": "python/main.py:Base#run()", "is_implementation": True, "is_definition": True}],
    )
    result = ingest_scip_json(doc)
    assert result["edges"][0]["relation"] == "scip_impl"


def test_ingest_is_type_definition_emits_scip_typed_edge() -> None:
    """is_type_definition → relation 'scip_typed'."""
    doc = _make_symbol_doc(
        "python/main.py:MyClass#run()",
        "function",
        [{"symbol": "python/main.py:Base#run()", "is_type_definition": True}],
    )
    result = ingest_scip_json(doc)
    assert result["edges"][0]["relation"] == "scip_typed"


def test_ingest_relationship_priority_order() -> None:
    """Implementation > TypeDefinition > Definition > Reference."""
    doc = _make_symbol_doc(
        "python/main.py:MyClass#run()",
        "function",
        [
            {
                "symbol": "python/main.py:Base#run()",
                "is_implementation": True,
                "is_type_definition": True,
                "is_definition": True,
                "is_reference": True,
            }
        ],
    )
    result = ingest_scip_json(doc)
    assert result["edges"][0]["relation"] == "scip_impl"


def test_ingest_relationship_no_boolean_flags_defaults_to_ref() -> None:
    """When none of is_* flags are set, relation defaults to 'scip_ref'."""
    doc = _make_symbol_doc(
        "python/main.py:MyClass#run()",
        "function",
        [{"symbol": "python/main.py:Other#"}],
    )
    result = ingest_scip_json(doc)
    assert result["edges"][0]["relation"] == "scip_ref"


def test_ingest_multiple_relationships_on_one_symbol() -> None:
    """A symbol with multiple relationships emits one edge per relationship."""
    doc = _make_symbol_doc(
        "python/main.py:MyClass#run()",
        "function",
        [
            {"symbol": "python/main.py:Base#run()", "is_definition": True},
            {"symbol": "python/main.py:Helper#help()", "is_reference": True},
        ],
    )
    result = ingest_scip_json(doc)
    assert len(result["edges"]) == 2
    relations = {e["relation"] for e in result["edges"]}
    assert relations == {"scip_def", "scip_ref"}


def test_ingest_relationship_without_target_symbol_is_skipped() -> None:
    """Relationship with empty or missing symbol field is ignored."""
    doc = _make_symbol_doc(
        "python/main.py:MyClass#run()",
        "function",
        [
            {"symbol": "", "is_reference": True},
            {"is_reference": True},
        ],
    )
    result = ingest_scip_json(doc)
    assert len(result["edges"]) == 0


def test_ingest_duplicate_edges_are_deduplicated() -> None:
    """The same source→target→relation→location edge is only emitted once."""
    doc = _make_symbol_doc(
        "python/main.py:MyClass#run()",
        "function",
        [
            {"symbol": "python/main.py:Helper#help()", "is_reference": True},
            {"symbol": "python/main.py:Helper#help()", "is_reference": True},
        ],
    )
    result = ingest_scip_json(doc)
    assert len(result["edges"]) == 1


# ---------------------------------------------------------------------------
# Edge emission — edge dict structure
# ---------------------------------------------------------------------------


def test_ingest_edge_structure_complete() -> None:
    """Verify every field in the emitted edge dict."""
    doc = _make_symbol_doc(
        "python/main.py:MyClass#run()",
        "function",
        [{"symbol": "python/main.py:Helper#help()", "is_reference": True}],
    )
    result = ingest_scip_json(doc)
    edge = result["edges"][0]
    assert edge["confidence"] == "EXTRACTED"
    assert edge["confidence_score"] == 1.0
    assert edge["weight"] == 1.0
    assert edge["context"] == "scip"
    assert edge["source_file"] == "src/main.py"
    assert edge["source_location"] == "L10"
    assert "scip_relationship" in edge["metadata"]


def test_ingest_edge_source_location_from_first_occurrence() -> None:
    """source_location on edges uses the line from the first occurrence range[0]."""
    doc = {
        "documents": [
            {
                "relative_path": "src/mod.py",
                "symbols": [
                    {
                        "symbol": "python/mod.py:Foo#bar()",
                        "kind": "function",
                        "occurrences": [
                            {"range": [42, 0, 42, 10], "symbol": "python/mod.py:Foo#bar()"},
                            {"range": [99, 0, 99, 10], "symbol": "python/mod.py:Foo#bar()"},
                        ],
                        "relationships": [
                            {"symbol": "python/mod.py:Baz#", "is_reference": True}
                        ],
                    }
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert result["edges"][0]["source_location"] == "L42"
    assert result["nodes"][0]["source_location"] == "L42"


def test_ingest_node_id_contains_source_file_and_symbol_suffix() -> None:
    """Node id is derived from source_file and symbol suffix."""
    doc = _make_symbol_doc(
        "python/main.py:MyClass#run()",
        "function",
        [],
    )
    result = ingest_scip_json(doc)
    node_id = result["nodes"][0]["id"]
    # Should start with scip_ and contain the suffix
    assert node_id.startswith("scip_")
    assert "run" in node_id


def test_ingest_node_id_is_deterministic() -> None:
    """Same input produces the same node id."""
    doc = _make_symbol_doc(
        "python/main.py:MyClass#run()",
        "function",
        [],
    )
    result1 = ingest_scip_json(doc)
    result2 = ingest_scip_json(doc)
    assert result1["nodes"][0]["id"] == result2["nodes"][0]["id"]


def test_ingest_node_id_differs_by_source_file() -> None:
    """Same symbol in different files produces different node ids."""
    doc1 = {
        "documents": [
            {"relative_path": "a.py", "symbols": [{"symbol": "F#", "kind": "class", "occurrences": [], "relationships": []}]}
        ]
    }
    doc2 = {
        "documents": [
            {"relative_path": "b.py", "symbols": [{"symbol": "F#", "kind": "class", "occurrences": [], "relationships": []}]}
        ]
    }
    id1 = ingest_scip_json(doc1)["nodes"][0]["id"]
    id2 = ingest_scip_json(doc2)["nodes"][0]["id"]
    assert id1 != id2


def test_ingest_duplicate_symbols_in_same_file_are_deduplicated() -> None:
    """The same symbol appearing twice in a document yields only one node."""
    doc = {
        "documents": [
            {
                "relative_path": "src/main.py",
                "symbols": [
                    {"symbol": "F#", "kind": "class", "occurrences": [], "relationships": []},
                    {"symbol": "F#", "kind": "class", "occurrences": [], "relationships": []},
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert len(result["nodes"]) == 1


# ---------------------------------------------------------------------------
# Invalid JSON / non-dict input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_input", [
    None,
    "a string",
    42,
    3.14,
    True,
    [],
    [1, 2, 3],
])
def test_ingest_non_dict_input_returns_empty(bad_input: object) -> None:
    """Non-dict inputs are guarded and return empty nodes/edges."""
    result = ingest_scip_json(bad_input)
    assert result == {"nodes": [], "edges": []}


def test_ingest_document_item_not_a_dict_is_skipped() -> None:
    """Non-dict entries in the documents list are silently skipped."""
    doc = {
        "documents": [
            "not_a_dict",
            123,
            None,
            {
                "relative_path": "valid.py",
                "symbols": [{"symbol": "F#", "kind": "class", "occurrences": [], "relationships": []}],
            },
        ]
    }
    result = ingest_scip_json(doc)
    assert len(result["nodes"]) == 1


def test_ingest_symbol_item_not_a_dict_is_skipped() -> None:
    """Non-dict entries in the symbols list are silently skipped."""
    doc = {
        "documents": [
            {
                "relative_path": "src/main.py",
                "symbols": [
                    "not_a_dict",
                    42,
                    None,
                    {"symbol": "python/main.py:Valid#", "kind": "class", "display_name": "Valid", "occurrences": [], "relationships": []},
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["label"] == "Valid"


def test_ingest_symbol_without_symbol_id_is_skipped() -> None:
    """A symbol dict with empty or missing 'symbol' field produces no node."""
    doc = {
        "documents": [
            {
                "relative_path": "src/main.py",
                "symbols": [
                    {"kind": "class", "occurrences": [], "relationships": []},
                    {"symbol": "", "kind": "class", "occurrences": [], "relationships": []},
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert len(result["nodes"]) == 0


def test_ingest_relationship_item_not_a_dict_is_skipped() -> None:
    """Non-dict entries in the relationships list are silently skipped."""
    doc = _make_symbol_doc(
        "python/main.py:MyClass#run()",
        "function",
        [
            "not_a_dict",
            42,
            None,
            {"symbol": "python/main.py:Helper#help()", "is_reference": True},
        ],
    )
    result = ingest_scip_json(doc)
    assert len(result["edges"]) == 1


# ---------------------------------------------------------------------------
# Empty documents / missing keys
# ---------------------------------------------------------------------------


def test_ingest_document_without_symbols_key() -> None:
    """Document dict without 'symbols' key is treated as empty list."""
    doc = {
        "documents": [
            {"relative_path": "src/main.py", "language": "python"}
        ]
    }
    result = ingest_scip_json(doc)
    assert result == {"nodes": [], "edges": []}


def test_ingest_document_with_symbols_not_a_list() -> None:
    """When symbols is not a list, that document is skipped."""
    doc = {
        "documents": [
            {"relative_path": "src/main.py", "symbols": "not_a_list"}
        ]
    }
    result = ingest_scip_json(doc)
    assert result == {"nodes": [], "edges": []}


def test_ingest_symbol_without_kind_defaults_to_unknown() -> None:
    """When kind is missing, metadata uses 'unknown'."""
    doc = {
        "documents": [
            {
                "relative_path": "src/main.py",
                "symbols": [
                    {"symbol": "F#", "occurrences": [], "relationships": []}
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert result["nodes"][0]["metadata"]["scip_kind"] == "unknown"


# ---------------------------------------------------------------------------
# Path validation / edge cases
# ---------------------------------------------------------------------------


def test_ingest_default_source_file_is_empty_string() -> None:
    """When no relative_path is given on document, source_file defaults to ''."""
    doc = {
        "documents": [
            {
                "symbols": [
                    {"symbol": "F#", "kind": "class", "occurrences": [], "relationships": []}
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert result["nodes"][0]["source_file"] == ""


def test_ingest_source_file_falls_back_to_function_param() -> None:
    """The source_file param provides a fallback when doc has no relative_path."""
    doc = {
        "documents": [
            {
                "symbols": [
                    {"symbol": "F#", "kind": "class", "occurrences": [], "relationships": []}
                ],
            }
        ]
    }
    result = ingest_scip_json(doc, source_file="fallback.scip")
    assert result["nodes"][0]["source_file"] == "fallback.scip"


def test_ingest_document_relative_path_overrides_source_file_param() -> None:
    """Document relative_path takes precedence over the source_file parameter."""
    doc = {
        "documents": [
            {
                "relative_path": "explicit.py",
                "symbols": [
                    {"symbol": "F#", "kind": "class", "occurrences": [], "relationships": []}
                ],
            }
        ]
    }
    result = ingest_scip_json(doc, source_file="fallback.scip")
    assert result["nodes"][0]["source_file"] == "explicit.py"


def test_ingest_document_without_language_defaults_to_function_param() -> None:
    """When doc has no language field, uses the language function parameter."""
    doc = {
        "documents": [
            {
                "relative_path": "src/main.ts",
                "symbols": [
                    {"symbol": "F#", "kind": "class", "occurrences": [], "relationships": []}
                ],
            }
        ]
    }
    result = ingest_scip_json(doc, language="typescript")
    # language is passed to _ingest_symbol but not directly exposed on nodes.
    # Verify that the node was still created (language defaults don't break ingestion).
    assert len(result["nodes"]) == 1


def test_ingest_symbol_with_short_range_uses_first_element_as_line() -> None:
    """A range list with exactly 2 elements (minimum required) sets sourceline from range[0]."""
    doc = {
        "documents": [
            {
                "relative_path": "src/mod.py",
                "symbols": [
                    {
                        "symbol": "python/mod.py:F#",
                        "kind": "class",
                        "occurrences": [{"range": [7, 0], "symbol": "python/mod.py:F#"}],
                        "relationships": [],
                    }
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert result["nodes"][0]["source_location"] == "L7"


def test_ingest_symbol_with_non_dict_occurrence_is_skipped() -> None:
    """Only the first occurrence is used; if it is not a dict, sourceline stays 0."""
    doc = {
        "documents": [
            {
                "relative_path": "src/mod.py",
                "symbols": [
                    {
                        "symbol": "python/mod.py:F#",
                        "kind": "class",
                        "occurrences": ["bad", 123, None, {"range": [15, 0, 15, 5], "symbol": "python/mod.py:F#"}],
                        "relationships": [],
                    }
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    # The first occurrence "bad" is not a dict → range parsing skipped → source_location stays empty
    assert result["nodes"][0]["source_location"] == ""


def test_ingest_symbol_with_non_list_range_falls_back_to_zero() -> None:
    """When range is not a list, sourceline stays 0 (empty source_location)."""
    doc = {
        "documents": [
            {
                "relative_path": "src/mod.py",
                "symbols": [
                    {
                        "symbol": "F#",
                        "kind": "class",
                        "occurrences": [{"range": "not_a_list", "symbol": "F#"}],
                        "relationships": [],
                    }
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert result["nodes"][0]["source_location"] == ""


def test_ingest_symbol_with_documentation_becomes_description() -> None:
    """The first element of documentation[] becomes scip_description metadata."""
    doc = {
        "documents": [
            {
                "relative_path": "src/mod.py",
                "symbols": [
                    {
                        "symbol": "F#",
                        "kind": "class",
                        "documentation": ["First line", "Second line"],
                        "occurrences": [],
                        "relationships": [],
                    }
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert result["nodes"][0]["metadata"]["scip_description"] == "First line"


def test_ingest_symbol_with_empty_documentation_skips_description() -> None:
    """When documentation[0] is empty string, scip_description is omitted."""
    doc = {
        "documents": [
            {
                "relative_path": "src/mod.py",
                "symbols": [
                    {
                        "symbol": "F#",
                        "kind": "class",
                        "documentation": [""],
                        "occurrences": [],
                        "relationships": [],
                    }
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert "scip_description" not in result["nodes"][0]["metadata"]


def test_ingest_symbol_without_documentation_omits_description() -> None:
    """When documentation key is missing, scip_description is not in metadata."""
    doc = {
        "documents": [
            {
                "relative_path": "src/mod.py",
                "symbols": [
                    {
                        "symbol": "F#",
                        "kind": "class",
                        "occurrences": [],
                        "relationships": [],
                    }
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert "scip_description" not in result["nodes"][0]["metadata"]


def test_ingest_symbol_without_relationships_key_still_creates_node() -> None:
    """Missing relationships key — symbol still becomes a node."""
    doc = {
        "documents": [
            {
                "relative_path": "src/mod.py",
                "symbols": [
                    {"symbol": "F#", "kind": "class", "occurrences": []}
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert len(result["nodes"]) == 1
    assert len(result["edges"]) == 0


# ---------------------------------------------------------------------------
# _make_scip_node_id — node id generation
# ---------------------------------------------------------------------------


def test_make_scip_node_id_with_hash_separator() -> None:
    """Symbol with # uses suffix after last #."""
    node_id = _make_scip_node_id("python/main.py:MyClass#run()", "src/main.py")
    assert node_id.startswith("scip_")
    assert "run" in node_id
    # Should NOT contain raw parentheses
    assert "(" not in node_id
    assert ")" not in node_id


def test_make_scip_node_id_without_hash() -> None:
    """Symbol without # uses the full symbol (sanitised) as suffix."""
    node_id = _make_scip_node_id("SimpleSymbol", "src/mod.py")
    assert node_id.startswith("scip_")
    assert "simplesymbol" in node_id.lower()


def test_make_scip_node_id_special_characters_are_sanitised() -> None:
    """Non-alphanumeric characters are replaced with underscores."""
    node_id = _make_scip_node_id("foo.bar#baz!@qux", "test.py")
    # Everything after last # becomes: baz!@qux → baz__qux
    assert "scip_baz__qux" in node_id


def test_make_scip_node_id_deterministic() -> None:
    """Same inputs always produce the same id."""
    a = _make_scip_node_id("python/main.py:Foo#bar", "src/a.py")
    b = _make_scip_node_id("python/main.py:Foo#bar", "src/a.py")
    assert a == b


def test_make_scip_node_id_source_file_affects_hash() -> None:
    """Different source_file produces different hash."""
    a = _make_scip_node_id("F#", "a.py")
    b = _make_scip_node_id("F#", "b.py")
    assert a != b


def test_make_scip_node_id_symbol_affects_hash() -> None:
    """Different symbol produces different hash."""
    a = _make_scip_node_id("A#", "f.py")
    b = _make_scip_node_id("B#", "f.py")
    assert a != b


def test_make_scip_node_id_empty_after_sanitisation_falls_back() -> None:
    """If sanitised suffix is empty, uses just the hash."""
    node_id = _make_scip_node_id("#", "src/f.py")
    # The suffix after # is empty string, so node_id should be scip_<hash>
    assert node_id.startswith("scip_")
    # Verify it's just scip_ + 12 hex chars
    import re
    assert re.match(r"^scip_[0-9a-f]{12}$", node_id)


# ---------------------------------------------------------------------------
# _scip_kind_to_file_type — always returns "code"
# ---------------------------------------------------------------------------


def test_scip_kind_to_file_type_always_code() -> None:
    """Any kind string maps to 'code'."""
    assert _scip_kind_to_file_type("class") == "code"
    assert _scip_kind_to_file_type("function") == "code"
    assert _scip_kind_to_file_type("variable") == "code"
    assert _scip_kind_to_file_type("") == "code"
    assert _scip_kind_to_file_type("arbitrary_string") == "code"


# ---------------------------------------------------------------------------
# _build_scip_metadata — metadata dict construction
# ---------------------------------------------------------------------------


def test_build_scip_metadata_with_description() -> None:
    """All three fields present when description is non-empty."""
    meta = _build_scip_metadata("sym_id", "class", "A sample description")
    assert meta == {
        "scip_symbol": "sym_id",
        "scip_kind": "class",
        "scip_description": "A sample description",
    }


def test_build_scip_metadata_without_description() -> None:
    """scip_description is omitted when description is empty string."""
    meta = _build_scip_metadata("sym_id", "class", "")
    assert meta == {
        "scip_symbol": "sym_id",
        "scip_kind": "class",
    }
    assert "scip_description" not in meta


# ---------------------------------------------------------------------------
# Edge-case: very large symbol count
# ---------------------------------------------------------------------------


def test_ingest_many_symbols() -> None:
    """Ingestion handles a large number of symbols gracefully."""
    symbols = [
        {"symbol": f"S{i}#", "kind": "class", "occurrences": [], "relationships": []}
        for i in range(100)
    ]
    doc = {"documents": [{"relative_path": "big.py", "symbols": symbols}]}
    result = ingest_scip_json(doc)
    assert len(result["nodes"]) == 100
    assert len(result["edges"]) == 0


# ---------------------------------------------------------------------------
# Edge-case: relationship with missing source_location (line 0)
# ---------------------------------------------------------------------------


def test_ingest_edge_with_zero_sourceline_has_empty_location() -> None:
    """When sourceline is 0, source_location on edge is empty string."""
    doc = {
        "documents": [
            {
                "relative_path": "src/mod.py",
                "symbols": [
                    {
                        "symbol": "A#",
                        "kind": "class",
                        "occurrences": [],  # no occurrences → sourceline 0
                        "relationships": [
                            {"symbol": "B#", "is_reference": True}
                        ],
                    }
                ],
            }
        ]
    }
    result = ingest_scip_json(doc)
    assert result["edges"][0]["source_location"] == ""
