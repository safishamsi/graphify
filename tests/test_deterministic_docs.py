"""Comprehensive tests for graphify.deterministic_docs."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from graphify.deterministic_docs import (
    DocTag,
    _docstring_start_line,
    _is_google_section_header,
    _normalise_space,
    _parse_google_item,
    _parse_google_sections,
    _parse_restructured_tags,
    _tag_label,
    _tag_relation,
    enrich_python_doc_tags,
    inspectable_docstring,
    parse_doc_tags,
)


# ---------------------------------------------------------------------------
# DocTag — creation and immutability
# ---------------------------------------------------------------------------


def test_doc_tag_creation_with_all_fields() -> None:
    """All fields are stored correctly on the frozen dataclass."""
    tag = DocTag(
        kind="param",
        name="path",
        description="file path to inspect",
        line=42,
        raw=":param path: file path to inspect",
    )
    assert tag.kind == "param"
    assert tag.name == "path"
    assert tag.description == "file path to inspect"
    assert tag.line == 42
    assert tag.raw == ":param path: file path to inspect"


def test_doc_tag_is_frozen() -> None:
    """DocTag is a frozen dataclass — mutation should raise an error."""
    tag = DocTag(kind="param", name="x", description="desc", line=1, raw="raw")
    with pytest.raises(Exception):
        tag.kind = "returns"  # type: ignore[misc]


def test_doc_tag_equality_by_value() -> None:
    """Two DocTags with identical fields compare equal."""
    a = DocTag(kind="param", name="x", description="d", line=1, raw="r")
    b = DocTag(kind="param", name="x", description="d", line=1, raw="r")
    assert a == b
    assert not (a != b)


def test_doc_tag_inequality_when_fields_differ() -> None:
    """DocTags with different fields do not compare equal."""
    a = DocTag(kind="param", name="x", description="d", line=1, raw="r")
    b = DocTag(kind="param", name="y", description="d", line=1, raw="r")
    assert a != b


# ---------------------------------------------------------------------------
# _normalise_space
# ---------------------------------------------------------------------------


def test_normalise_space_collapses_multiple_spaces() -> None:
    assert _normalise_space("a   b  c") == "a b c"


def test_normalise_space_collapses_tabs_and_newlines() -> None:
    assert _normalise_space("\ta\tb\nc  d") == "a b c d"


def test_normalise_space_strips_leading_and_trailing() -> None:
    assert _normalise_space("   hello world   ") == "hello world"


def test_normalise_space_preserves_empty_to_empty() -> None:
    assert _normalise_space("") == ""


def test_normalise_space_preserves_single_char() -> None:
    assert _normalise_space("x") == "x"


# ---------------------------------------------------------------------------
# inspectable_docstring
# ---------------------------------------------------------------------------


def test_inspectable_docstring_returns_empty_for_none() -> None:
    assert inspectable_docstring(None) == ""


def test_inspectable_docstring_returns_empty_for_empty_string() -> None:
    assert inspectable_docstring("") == ""


def test_inspectable_docstring_returns_empty_for_whitespace_only() -> None:
    assert inspectable_docstring("   \n  \n\t\n") == ""


def test_inspectable_docstring_preserves_single_line() -> None:
    assert inspectable_docstring("hello world") == "hello world"


def test_inspectable_docstring_strips_blank_lines_at_start() -> None:
    result = inspectable_docstring("\n\n   actual content\n")
    assert result == "actual content"


def test_inspectable_docstring_strips_blank_lines_at_end() -> None:
    result = inspectable_docstring("actual content\n\n   \n")
    assert result == "actual content"


def test_inspectable_docstring_strips_common_indentation() -> None:
    doc = (
        "Summary line.\n"
        "\n"
        "    Indented detail line.\n"
        "    Another indented line.\n"
    )
    result = inspectable_docstring(doc)
    lines = result.splitlines()
    assert lines[0] == "Summary line."
    assert lines[1] == ""
    assert lines[2] == "Indented detail line."
    assert lines[3] == "Another indented line."


def test_inspectable_docstring_preserves_partial_indentation() -> None:
    """When lines have different indentation, minimal common indent is stripped."""
    doc = "summary\n    deeply indented\n  slightly indented\n"
    result = inspectable_docstring(doc)
    lines = result.splitlines()
    assert lines[0] == "summary"
    # Minimum indent of lines after first with content is 2 → strip 2
    assert lines[1] == "  deeply indented"
    assert lines[2] == "slightly indented"


def test_inspectable_docstring_preserves_second_line_blank() -> None:
    doc = "Summary.\n\nMore text."
    result = inspectable_docstring(doc)
    assert result == "Summary.\n\nMore text."


# ---------------------------------------------------------------------------
# _is_google_section_header
# ---------------------------------------------------------------------------


def test_is_google_section_header_args_alias() -> None:
    assert _is_google_section_header("Args:") == "param"
    assert _is_google_section_header("Arguments:") == "param"
    assert _is_google_section_header("Parameters:") == "param"
    assert _is_google_section_header("Params:") == "param"


def test_is_google_section_header_returns_alias() -> None:
    assert _is_google_section_header("Returns:") == "returns"
    assert _is_google_section_header("Return:") == "returns"


def test_is_google_section_header_raises_alias() -> None:
    assert _is_google_section_header("Raises:") == "raises"
    assert _is_google_section_header("Raise:") == "raises"


def test_is_google_section_header_yields_alias() -> None:
    assert _is_google_section_header("Yields:") == "yields"
    assert _is_google_section_header("Yield:") == "yields"


def test_is_google_section_header_case_insensitive() -> None:
    assert _is_google_section_header("ARGS:") == "param"
    assert _is_google_section_header("returns:") == "returns"
    assert _is_google_section_header("RetURNs") == "returns"


def test_is_google_section_header_without_colon() -> None:
    """Header works with or without trailing colon."""
    assert _is_google_section_header("Args") == "param"


def test_is_google_section_header_returns_none_for_unknown() -> None:
    assert _is_google_section_header("Notes:") is None
    assert _is_google_section_header("Examples:") is None
    assert _is_google_section_header("Description") is None


def test_is_google_section_header_returns_none_for_whitespace() -> None:
    assert _is_google_section_header("   ") is None
    assert _is_google_section_header("") is None


# ---------------------------------------------------------------------------
# _parse_google_item
# ---------------------------------------------------------------------------


def test_parse_google_item_param_with_type() -> None:
    tag = _parse_google_item("param", "path (str): the file path", 5)
    assert tag is not None
    assert tag.kind == "param"
    assert tag.name == "path"
    assert tag.description == "the file path Type: str"
    assert tag.line == 5


def test_parse_google_item_param_without_type() -> None:
    tag = _parse_google_item("param", "name: the user name", 3)
    assert tag is not None
    assert tag.kind == "param"
    assert tag.name == "name"
    assert tag.description == "the user name"
    assert tag.line == 3


def test_parse_google_item_param_dash_separator() -> None:
    tag = _parse_google_item("param", "path - the file path", 10)
    assert tag is not None
    assert tag.kind == "param"
    assert tag.name == "path"
    assert tag.description == "the file path"


def test_parse_google_item_returns_with_type() -> None:
    tag = _parse_google_item("returns", "int: the exit code", 8)
    assert tag is not None
    assert tag.kind == "returns"
    assert tag.name == "return"
    assert tag.description == "the exit code Type: int"


def test_parse_google_item_returns_without_type() -> None:
    tag = _parse_google_item("returns", "the result object", 8)
    assert tag is not None
    assert tag.kind == "returns"
    assert tag.name == "return"
    assert tag.description == "the result object"


def test_parse_google_item_yields() -> None:
    tag = _parse_google_item("yields", "int: the next value", 12)
    assert tag is not None
    assert tag.kind == "yields"
    assert tag.name == "yield"
    assert tag.description == "the next value Type: int"


def test_parse_google_item_raises_with_colon() -> None:
    tag = _parse_google_item("raises", "ValueError: invalid input", 15)
    assert tag is not None
    assert tag.kind == "raises"
    assert tag.name == "ValueError"
    assert tag.description == "invalid input"


def test_parse_google_item_raises_with_dash() -> None:
    tag = _parse_google_item("raises", "ValueError - invalid input", 15)
    assert tag is not None
    assert tag.kind == "raises"
    assert tag.name == "ValueError"
    assert tag.description == "invalid input"


def test_parse_google_item_raises_fallback() -> None:
    """When raise item has no colon/dash, first word is name and full text is description."""
    tag = _parse_google_item("raises", "IOError something went wrong", 20)
    assert tag is not None
    assert tag.kind == "raises"
    assert tag.name == "IOError"
    assert tag.description == "IOError something went wrong"


def test_parse_google_item_returns_none_for_empty_text() -> None:
    assert _parse_google_item("param", "   ", 1) is None
    assert _parse_google_item("param", "", 1) is None


def test_parse_google_item_returns_none_for_param_unknown_format() -> None:
    """When param text doesn't match known patterns, returns None."""
    assert _parse_google_item("param", "just some text", 1) is None


def test_parse_google_item_returns_none_for_unknown_section() -> None:
    assert _parse_google_item("notes", "some text", 1) is None


# ---------------------------------------------------------------------------
# _parse_restructured_tags
# ---------------------------------------------------------------------------


def test_parse_restructured_tags_basic_param() -> None:
    lines = [":param path: file path to inspect"]
    tags = _parse_restructured_tags(lines, 10)
    assert len(tags) == 1
    assert tags[0].kind == "param"
    assert tags[0].name == "path"
    assert tags[0].description == "file path to inspect"
    assert tags[0].line == 10


def test_parse_restructured_tags_param_with_type() -> None:
    lines = [
        ":param path: file path to inspect",
        ":type path: pathlib.Path",
    ]
    tags = _parse_restructured_tags(lines, 20)
    assert len(tags) == 1
    assert tags[0].kind == "param"
    assert tags[0].name == "path"
    assert tags[0].description == "file path to inspect Type: pathlib.Path"


def test_parse_restructured_tags_type_before_param() -> None:
    """Type line before param line should still be matched."""
    lines = [
        ":type path: pathlib.Path",
        ":param path: file path",
    ]
    tags = _parse_restructured_tags(lines, 1)
    assert len(tags) == 1
    assert tags[0].name == "path"
    assert "Type: pathlib.Path" in tags[0].description


def test_parse_restructured_tags_multiple_params() -> None:
    lines = [
        ":param a: first param",
        ":param b: second param",
    ]
    tags = _parse_restructured_tags(lines, 5)
    assert len(tags) == 2
    names = {t.name for t in tags}
    assert names == {"a", "b"}


def test_parse_restructured_tags_returns() -> None:
    lines = [":returns: extracted graph fragment"]
    tags = _parse_restructured_tags(lines, 1)
    assert len(tags) == 1
    assert tags[0].kind == "returns"
    assert tags[0].name == "return"
    assert tags[0].description == "extracted graph fragment"


def test_parse_restructured_tags_return_alternative_spelling() -> None:
    lines = [":return: extracted fragment"]
    tags = _parse_restructured_tags(lines, 1)
    assert len(tags) == 1
    assert tags[0].kind == "returns"


def test_parse_restructured_tags_returns_with_rtype() -> None:
    lines = [
        ":returns: extracted graph fragment",
        ":rtype: dict",
    ]
    tags = _parse_restructured_tags(lines, 30)
    assert len(tags) == 1
    assert tags[0].description == "extracted graph fragment Type: dict"


def test_parse_restructured_tags_rtype_without_returns() -> None:
    """rtype without returns should NOT produce a returns tag."""
    lines = [":rtype: dict"]
    tags = _parse_restructured_tags(lines, 1)
    return_tags = [t for t in tags if t.kind == "returns"]
    assert len(return_tags) == 0


def test_parse_restructured_tags_raises() -> None:
    lines = [":raises ValueError: when the input is invalid"]
    tags = _parse_restructured_tags(lines, 42)
    assert len(tags) == 1
    assert tags[0].kind == "raises"
    assert tags[0].name == "ValueError"
    assert tags[0].description == "when the input is invalid"
    assert tags[0].line == 42


def test_parse_restructured_tags_raise_alternative_spelling() -> None:
    lines = [":raise ValueError: something"]
    tags = _parse_restructured_tags(lines, 1)
    assert len(tags) == 1
    assert tags[0].kind == "raises"


def test_parse_restructured_tags_multiple_raises() -> None:
    lines = [
        ":raises ValueError: bad value",
        ":raises IOError: file not found",
    ]
    tags = _parse_restructured_tags(lines, 1)
    assert len(tags) == 2
    assert all(t.kind == "raises" for t in tags)


def test_parse_restructured_tags_skips_empty_lines() -> None:
    lines = [
        "",
        ":param x: desc",
        "",
        ":raises ValueError: bad",
        "",
    ]
    tags = _parse_restructured_tags(lines, 1)
    assert len(tags) == 2


def test_parse_restructured_tags_empty_input() -> None:
    assert _parse_restructured_tags([], 1) == []


def test_parse_restructured_tags_no_tags_recognized() -> None:
    lines = ["This is just some prose.", "No structured tags here."]
    assert _parse_restructured_tags(lines, 1) == []


def test_parse_restructured_tags_param_with_colon_in_description() -> None:
    """Description text containing a colon should not break parsing."""
    lines = [":param key: key:value format string"]
    tags = _parse_restructured_tags(lines, 1)
    assert len(tags) == 1
    assert tags[0].name == "key"
    assert tags[0].description == "key:value format string"


# ---------------------------------------------------------------------------
# _parse_google_sections
# ---------------------------------------------------------------------------


def test_parse_google_sections_basic_args() -> None:
    lines = [
        "Args:",
        "    path: the file path",
        "    name: the user name",
    ]
    tags = _parse_google_sections(lines, 10)
    assert len(tags) == 2
    names = {t.name for t in tags}
    assert names == {"path", "name"}


def test_parse_google_sections_args_with_types() -> None:
    lines = [
        "Args:",
        "    path (str): the file path",
        "    count (int): the count",
    ]
    tags = _parse_google_sections(lines, 1)
    assert len(tags) == 2
    assert all("Type:" in t.description for t in tags)


def test_parse_google_sections_returns() -> None:
    lines = [
        "Returns:",
        "    int: the exit code",
    ]
    tags = _parse_google_sections(lines, 5)
    assert len(tags) == 1
    assert tags[0].kind == "returns"
    assert tags[0].name == "return"


def test_parse_google_sections_raises() -> None:
    lines = [
        "Raises:",
        "    ValueError: invalid input",
    ]
    tags = _parse_google_sections(lines, 1)
    assert len(tags) == 1
    assert tags[0].kind == "raises"
    assert tags[0].name == "ValueError"


def test_parse_google_sections_continuation_lines() -> None:
    """Lines indented with 4+ spaces that don't start a new item are appended to the previous item."""
    lines = [
        "Args:",
        "    name: the user name that is",
        "        very long and wraps to",
        "        the next line",
    ]
    tags = _parse_google_sections(lines, 1)
    assert len(tags) == 1
    assert tags[0].name == "name"
    assert "very long and wraps to the next line" in tags[0].description


def test_parse_google_sections_multiple_sections() -> None:
    lines = [
        "Args:",
        "    x: first param",
        "Returns:",
        "    str: the result",
        "Raises:",
        "    ValueError: bad value",
    ]
    tags = _parse_google_sections(lines, 1)
    kinds = {t.kind for t in tags}
    assert kinds == {"param", "returns", "raises"}
    assert len(tags) == 3


def test_parse_google_sections_empty_input() -> None:
    assert _parse_google_sections([], 1) == []


def test_parse_google_sections_no_sections() -> None:
    lines = ["This is some prose.", "More text here."]
    assert _parse_google_sections(lines, 1) == []


def test_parse_google_sections_text_before_section_is_skipped() -> None:
    lines = [
        "Some free text before sections.",
        "Args:",
        "    x: a param",
    ]
    tags = _parse_google_sections(lines, 1)
    assert len(tags) == 1
    assert tags[0].name == "x"


def test_parse_google_sections_params_section_alias() -> None:
    lines = [
        "Params:",
        "    x: a param",
    ]
    tags = _parse_google_sections(lines, 1)
    assert len(tags) == 1
    assert tags[0].kind == "param"


def test_parse_google_sections_skip_items_outside_sections() -> None:
    """Items without an active section header are skipped."""
    lines = [
        "    x: this has no section header",
        "Args:",
        "    y: a real param",
    ]
    tags = _parse_google_sections(lines, 1)
    assert len(tags) == 1
    assert tags[0].name == "y"


def test_parse_google_sections_yields_section() -> None:
    lines = [
        "Yields:",
        "    int: next value",
    ]
    tags = _parse_google_sections(lines, 1)
    assert len(tags) == 1
    assert tags[0].kind == "yields"


def test_parse_google_sections_tab_indented_items() -> None:
    lines = [
        "Args:",
        "\tpath: file path",
    ]
    tags = _parse_google_sections(lines, 1)
    assert len(tags) == 1
    assert tags[0].name == "path"


def test_parse_google_sections_line_numbers_tracked() -> None:
    lines = [
        "Args:",
        "    x: param desc",
    ]
    tags = _parse_google_sections(lines, 50)
    assert tags[0].line == 51  # offset 1 from base_line 50
    assert tags[0].raw == "x: param desc"


# ---------------------------------------------------------------------------
# parse_doc_tags (public API)
# ---------------------------------------------------------------------------


def test_parse_doc_tags_returns_empty_list_for_none() -> None:
    assert parse_doc_tags(None, 1) == []


def test_parse_doc_tags_returns_empty_list_for_empty_string() -> None:
    assert parse_doc_tags("", 1) == []


def test_parse_doc_tags_returns_empty_list_for_whitespace_only() -> None:
    assert parse_doc_tags("   \n  \n  ", 1) == []


def test_parse_doc_tags_detects_restructured_tags() -> None:
    docstring = (
        "Process the input.\n"
        "\n"
        ":param data: the input data\n"
        ":returns: processed result\n"
    )
    tags = parse_doc_tags(docstring, 100)
    assert len(tags) >= 2
    kinds = {t.kind for t in tags}
    assert "param" in kinds
    assert "returns" in kinds


def test_parse_doc_tags_detects_google_style_tags() -> None:
    docstring = (
        "Process the input.\n"
        "\n"
        "Args:\n"
        "    data: the input data\n"
        "Returns:\n"
        "    str: the result\n"
    )
    tags = parse_doc_tags(docstring, 1)
    assert len(tags) >= 2


def test_parse_doc_tags_dedup_by_kind_name_line() -> None:
    """Tags with the same (kind, name) at different lines are NOT deduplicated.

    The dedup key is (kind, name, line). Tags at different lines are distinct
    and both are kept; only exact (kind, name, line) collisions are removed.
    """
    docstring = (
        "Args:\n"
        "    x: first try\n"
        "Args:\n"
        "    x: first try\n"
    )
    tags = parse_doc_tags(docstring, 1)
    x_tags = [t for t in tags if t.name == "x"]
    # Both are kept because they're on different lines (line 2 and line 4)
    assert len(x_tags) == 2


def test_parse_doc_tags_handles_normal_indentation() -> None:
    docstring = (
        '    """Process data.\n'
        "\n"
        "    :param data: the data\n"
        '    """'
    )
    tags = parse_doc_tags(docstring, 1)
    assert len(tags) == 1
    assert tags[0].name == "data"


def test_parse_doc_tags_base_line_offset() -> None:
    """base_line is added to the offset of each matched line."""
    docstring = ":param x: description"
    tags = parse_doc_tags(docstring, 500)
    assert tags[0].line == 500


def test_parse_doc_tags_plain_prose_returns_empty() -> None:
    docstring = "This is just a free-text description with no structured tags."
    assert parse_doc_tags(docstring, 1) == []


def test_parse_doc_tags_mixed_rest_and_google() -> None:
    """A docstring with both reST and Google-style sections returns both."""
    docstring = (
        ":param x: reST param\n"
        "\n"
        "Args:\n"
        "    y: google param\n"
    )
    tags = parse_doc_tags(docstring, 1)
    names = {t.name for t in tags}
    assert "x" in names
    assert "y" in names


# ---------------------------------------------------------------------------
# _docstring_start_line
# ---------------------------------------------------------------------------


def test_docstring_start_line_class_with_docstring() -> None:
    code = "class Foo:\n    '''Class doc.'''\n    pass\n"
    tree = ast.parse(code)
    cls = tree.body[0]
    assert isinstance(cls, ast.ClassDef)
    line = _docstring_start_line(cls)
    assert line == 2  # The docstring Expr node is on line 2


def test_docstring_start_line_function_with_docstring() -> None:
    code = "def foo():\n    '''Func doc.'''\n    pass\n"
    tree = ast.parse(code)
    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef)
    line = _docstring_start_line(func)
    assert line == 2


def test_docstring_start_line_node_without_docstring() -> None:
    code = "def foo():\n    x = 1\n"
    tree = ast.parse(code)
    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef)
    line = _docstring_start_line(func)
    assert line == 1  # Falls back to node lineno


def test_docstring_start_line_module_with_docstring() -> None:
    code = "'''Module doc.'''\n\nx = 1\n"
    tree = ast.parse(code)
    line = _docstring_start_line(tree)
    assert line == 1


# ---------------------------------------------------------------------------
# _tag_label
# ---------------------------------------------------------------------------


def test_tag_label_format_with_description() -> None:
    tag = DocTag(kind="param", name="path", description="the file path", line=1, raw="raw")
    assert _tag_label(tag) == "param path: the file path"


def test_tag_label_format_without_description() -> None:
    tag = DocTag(kind="returns", name="return", description="", line=1, raw="raw")
    assert _tag_label(tag) == "returns return"


def test_tag_label_truncates_long_descriptions() -> None:
    long_desc = "A" * 200
    tag = DocTag(kind="param", name="x", description=long_desc, line=1, raw="raw")
    label = _tag_label(tag)
    assert len(label) <= 160


# ---------------------------------------------------------------------------
# _tag_relation
# ---------------------------------------------------------------------------


def test_tag_relation_param() -> None:
    tag = DocTag(kind="param", name="x", description="d", line=1, raw="r")
    assert _tag_relation(tag) == "documents_parameter"


def test_tag_relation_returns() -> None:
    tag = DocTag(kind="returns", name="return", description="d", line=1, raw="r")
    assert _tag_relation(tag) == "documents_return"


def test_tag_relation_yields() -> None:
    tag = DocTag(kind="yields", name="yield", description="d", line=1, raw="r")
    assert _tag_relation(tag) == "documents_yield"


def test_tag_relation_raises() -> None:
    tag = DocTag(kind="raises", name="ValueError", description="d", line=1, raw="r")
    assert _tag_relation(tag) == "documents_exception"


def test_tag_relation_unknown_falls_back_to_documents() -> None:
    tag = DocTag(kind="note", name="info", description="d", line=1, raw="r")
    assert _tag_relation(tag) == "documents"


# ---------------------------------------------------------------------------
# enrich_python_doc_tags — integration tests
# ---------------------------------------------------------------------------


def _make_id(*parts: str) -> str:
    """Simple id factory for tests."""
    return "_".join(parts)


def _file_stem(p: Path) -> str:
    """Simple file stem extractor for tests."""
    return p.stem


def test_enrich_python_doc_tags_adds_nodes_and_edges(tmp_path: Path) -> None:
    """A python file with structured docstring tags produces nodes and edges."""
    src = tmp_path / "example.py"
    src.write_text(
        '''"""Example module with tags.

:param path: file path
:returns: result dict
"""

def process(path: str) -> dict:
    """Process a path.

    Args:
        path: the path to process
    Returns:
        dict: processing result
    """
    return {"path": path}
''',
        encoding="utf-8",
    )

    # Pre-populate result with owner nodes so tags can be attached
    result: dict = {
        "nodes": [
            {"id": _make_id(str(src)), "label": "example.py", "file_type": "file"},
            {"id": _make_id("example", "process"), "label": "process()", "file_type": "code"},
        ],
        "edges": [],
    }

    enrich_python_doc_tags(src, result, make_id=_make_id, file_stem=_file_stem)

    nodes = result["nodes"]
    edges = result["edges"]

    # Should have added doc_tag nodes beyond the 2 owner nodes
    doc_tag_nodes = [n for n in nodes if n.get("file_type") == "doc_tag"]
    assert len(doc_tag_nodes) >= 2  # param + returns for module, param + returns for function

    # Check node structure
    for node in doc_tag_nodes:
        assert "id" in node
        assert "label" in node
        assert node["file_type"] == "doc_tag"
        assert "metadata" in node
        assert "doc_kind" in node["metadata"]
        assert "doc_name" in node["metadata"]

    # Edges should be present (two per tag: documents + documents_*)
    assert len(edges) >= 4


def test_enrich_python_doc_tags_skips_when_owner_not_in_nodes(
    tmp_path: Path,
) -> None:
    """Tags for an owner not present in existing nodes are skipped."""
    src = tmp_path / "orphan.py"
    src.write_text(
        '"""Module with tags but no owner node."""\n'
        "\n"
        "def func():\n"
        '    """Has param but func not in result nodes."""\n'
        "    pass\n",
        encoding="utf-8",
    )

    result: dict = {
        "nodes": [],  # No owner nodes present
        "edges": [],
    }

    enrich_python_doc_tags(src, result, make_id=_make_id, file_stem=_file_stem)

    # No new nodes or edges should be added since no owners match
    assert len(result["nodes"]) == 0
    assert len(result["edges"]) == 0


def test_enrich_python_doc_tags_handles_missing_file(tmp_path: Path) -> None:
    """A non-existent file (OSError) should be handled gracefully."""
    missing = tmp_path / "does_not_exist.py"

    result: dict = {"nodes": [], "edges": []}
    # Should not raise — just return early
    enrich_python_doc_tags(missing, result, make_id=_make_id, file_stem=_file_stem)

    assert result["nodes"] == []
    assert result["edges"] == []


def test_enrich_python_doc_tags_handles_syntax_error(tmp_path: Path) -> None:
    """A file with invalid Python syntax should not cause an exception."""
    src = tmp_path / "broken.py"
    src.write_text("this is not valid python !!! {[[", encoding="utf-8")

    result: dict = {"nodes": [], "edges": []}
    enrich_python_doc_tags(src, result, make_id=_make_id, file_stem=_file_stem)

    assert result["nodes"] == []
    assert result["edges"] == []


def test_enrich_python_doc_tags_no_docstrings(tmp_path: Path) -> None:
    """A valid Python file with no docstrings produces no extra nodes/edges."""
    src = tmp_path / "nodoc.py"
    src.write_text("x = 1\ny = 2\n", encoding="utf-8")

    result: dict = {"nodes": [], "edges": []}
    enrich_python_doc_tags(src, result, make_id=_make_id, file_stem=_file_stem)

    assert result["nodes"] == []
    assert result["edges"] == []


def test_enrich_python_doc_tags_preserves_existing_nodes_and_edges(
    tmp_path: Path,
) -> None:
    """Existing nodes and edges in the result are not removed."""
    src = tmp_path / "preserve.py"
    src.write_text(
        '"""Module with param."""\n\n'
        "x = 1\n",
        encoding="utf-8",
    )

    existing_node = {"id": _make_id(str(src)), "label": "preserve.py", "file_type": "file"}
    existing_edge = {
        "source": "a",
        "target": "b",
        "relation": "calls",
        "source_location": "L1",
    }

    result: dict = {
        "nodes": [existing_node],
        "edges": [existing_edge],
    }

    enrich_python_doc_tags(src, result, make_id=_make_id, file_stem=_file_stem)

    # Original node should still be present
    assert existing_node in result["nodes"]
    # Original edge should still be present
    assert existing_edge in result["edges"]


def test_enrich_python_doc_tags_class_with_method_docstring(
    tmp_path: Path,
) -> None:
    """Doc tags from a class method with structured docstring should be extracted."""
    src = tmp_path / "cls_example.py"
    src.write_text(
        '''class Calculator:
    """A simple calculator class."""

    def add(self, a: int, b: int) -> int:
        """Add two numbers.

        Args:
            a: first number
            b: second number
        Returns:
            int: the sum
        Raises:
            ValueError: if a or b is negative
        """
        if a < 0 or b < 0:
            raise ValueError
        return a + b
''',
        encoding="utf-8",
    )

    class_nid = _make_id("cls_example", "Calculator")
    method_nid = _make_id(class_nid, "add")

    result: dict = {
        "nodes": [
            {"id": class_nid, "label": "Calculator", "file_type": "class"},
            {"id": method_nid, "label": "add()", "file_type": "method"},
        ],
        "edges": [],
    }

    enrich_python_doc_tags(src, result, make_id=_make_id, file_stem=_file_stem)

    doc_tag_nodes = [n for n in result["nodes"] if n.get("file_type") == "doc_tag"]
    # Should have 2 params + returns + raises = 4 tags from method
    # plus 0 from class (no structured tags in class docstring)
    assert len(doc_tag_nodes) >= 4

    kinds = {n["metadata"]["doc_kind"] for n in doc_tag_nodes}
    assert kinds >= {"param", "returns", "raises"}


def test_enrich_python_doc_tags_top_level_function(tmp_path: Path) -> None:
    """A top-level function with Google-style Args/Returns should produce tags."""
    src = tmp_path / "func_example.py"
    src.write_text(
        '"""Module doc."""\n'
        "\n"
        "def greet(name: str) -> str:\n"
        '    """Create a greeting.\n'
        "\n"
        "    Args:\n"
        "        name: the person to greet\n"
        "    Returns:\n"
        "        str: a friendly greeting\n"
        '    """\n'
        "    return f'Hello, {name}'\n",
        encoding="utf-8",
    )

    func_nid = _make_id("func_example", "greet")

    result: dict = {
        "nodes": [
            {"id": func_nid, "label": "greet()", "file_type": "code"},
        ],
        "edges": [],
    }

    enrich_python_doc_tags(src, result, make_id=_make_id, file_stem=_file_stem)

    doc_tag_nodes = [n for n in result["nodes"] if n.get("file_type") == "doc_tag"]
    assert len(doc_tag_nodes) == 2  # param: name, returns

    param_node = next(n for n in doc_tag_nodes if n["metadata"]["doc_kind"] == "param")
    assert param_node["metadata"]["doc_name"] == "name"

    return_node = next(n for n in doc_tag_nodes if n["metadata"]["doc_kind"] == "returns")
    assert return_node["metadata"]["owner_kind"] == "function"
    assert return_node["metadata"]["owner_id"] == func_nid


def test_enrich_python_doc_tags_edge_relations(
    tmp_path: Path,
) -> None:
    """Verify that edges have correct relations and two-way connections."""
    src = tmp_path / "edge_test.py"
    src.write_text(
        '"""Module doc.\n\n:param x: a param\n"""\n\n'
        "x = 1\n",
        encoding="utf-8",
    )

    result: dict = {
        "nodes": [
            {"id": _make_id(str(src)), "label": "edge_test.py", "file_type": "file"},
        ],
        "edges": [],
    }

    enrich_python_doc_tags(src, result, make_id=_make_id, file_stem=_file_stem)

    edges = result["edges"]
    assert len(edges) == 2

    relations = {e["relation"] for e in edges}
    assert relations == {"documents", "documents_parameter"}

    contexts = {e.get("context") for e in edges}
    assert contexts == {"docstring_tag"}

    for edge in edges:
        assert edge["confidence"] == "EXTRACTED"
        assert edge["confidence_score"] == 1.0


def test_enrich_python_doc_tags_dedup_pre_existing_edges(
    tmp_path: Path,
) -> None:
    """When the result already has edges for these tags, no duplicates are added."""
    src = tmp_path / "dedup_test.py"
    src.write_text(
        '"""Module doc.\n\n:param x: desc\n"""\n\nx = 1\n',
        encoding="utf-8",
    )

    file_nid = _make_id(str(src))

    # Add a pre-existing edge that would match one of the generated edges
    pre_existing_edge = {
        "source": file_nid,
        "target": _make_id(file_nid, "doc", "param", "x", "3", "1"),
        "relation": "documents_parameter",
        "confidence": "EXTRACTED",
        "confidence_score": 1.0,
        "source_file": str(src),
        "source_location": "L3",
        "weight": 1.0,
        "context": "docstring_tag",
    }

    result: dict = {
        "nodes": [
            {"id": file_nid, "label": "dedup_test.py", "file_type": "file"},
        ],
        "edges": [pre_existing_edge],
    }

    enrich_python_doc_tags(src, result, make_id=_make_id, file_stem=_file_stem)

    # The pre-existing edge with same (source, target, relation, source_location)
    # should prevent a duplicate, but the "documents" edge (different relation)
    # should still be added
    doc_param_edges = [
        e
        for e in result["edges"]
        if e["relation"] == "documents_parameter"
        and e["source"] == file_nid
    ]
    assert len(doc_param_edges) == 1  # No duplicates


def test_enrich_python_doc_tags_handles_empty_module(tmp_path: Path) -> None:
    """An empty Python file should not cause errors."""
    src = tmp_path / "empty.py"
    src.write_text("", encoding="utf-8")

    result: dict = {"nodes": [], "edges": []}
    enrich_python_doc_tags(src, result, make_id=_make_id, file_stem=_file_stem)

    assert result["nodes"] == []
    assert result["edges"] == []


# ---------------------------------------------------------------------------
# Nested scope and edge case handling
# ---------------------------------------------------------------------------


def test_parse_doc_tags_nested_indent_preserved() -> None:
    """Docstrings with unusual but valid indentation still parse correctly."""
    docstring = (
        "Description.\n"
        "    :param x: first\n"
        "        :param y: second\n"
    )
    tags = parse_doc_tags(docstring, 1)
    assert len(tags) >= 1  # At least x should be found


def test_parse_google_item_handles_leading_whitespace_in_text() -> None:
    """_normalise_space is applied, so leading/trailing whitespace is handled."""
    tag = _parse_google_item("param", "   name   :   description   ", 1)
    assert tag is not None
    assert tag.name == "name"
    assert tag.description == "description"


def test_parse_google_sections_multiple_contiguous_sections() -> None:
    """When a new section header appears, previous section is flushed."""
    lines = [
        "Args:",
        "    x: param x",
        "Returns:",
        "    int: result",
    ]
    tags = _parse_google_sections(lines, 1)
    assert len(tags) == 2
    kinds = [t.kind for t in tags]
    assert kinds == ["param", "returns"]


def test_enrich_python_doc_tags_module_doc_only(tmp_path: Path) -> None:
    """Module-level docstring with tags but no function/class docstrings."""
    src = tmp_path / "mod_only.py"
    src.write_text(
        '"""Module description.\n\n:param config: configuration dict\n"""\n\n'
        "CONFIG = {}\n",
        encoding="utf-8",
    )

    result: dict = {
        "nodes": [
            {"id": _make_id(str(src)), "label": "mod_only.py", "file_type": "file"},
        ],
        "edges": [],
    }

    enrich_python_doc_tags(src, result, make_id=_make_id, file_stem=_file_stem)

    doc_tag_nodes = [n for n in result["nodes"] if n.get("file_type") == "doc_tag"]
    assert len(doc_tag_nodes) == 1
    assert doc_tag_nodes[0]["metadata"]["doc_kind"] == "param"
    assert doc_tag_nodes[0]["metadata"]["doc_name"] == "config"


def test_enrich_python_doc_tags_creates_default_keys(tmp_path: Path) -> None:
    """When result dict lacks 'nodes' and 'edges', they are setdefault."""
    src = tmp_path / "defaults.py"
    src.write_text(
        '"""Doc.\n\n:returns: result\n"""\n\nx = 1\n',
        encoding="utf-8",
    )

    result: dict = {}

    enrich_python_doc_tags(src, result, make_id=_make_id, file_stem=_file_stem)

    assert "nodes" in result
    assert "edges" in result
    # No owner nodes in result, so no tags added
    assert result["nodes"] == []
    assert result["edges"] == []
