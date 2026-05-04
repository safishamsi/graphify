"""Tests for graphify.extract.parse_markdown_sections."""
from pathlib import Path

import pytest

from graphify.extract import parse_markdown_sections


def _write(tmp_path: Path, text: str, name: str = "doc.md") -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_single_top_level_header_spans_whole_file(tmp_path):
    body = "# Only Header\n\nbody line 1\nbody line 2\n"
    p = _write(tmp_path, body)
    sections = parse_markdown_sections(p)
    assert sections == [
        {"label": "Only Header", "level": 1, "start_line": 1, "end_line": 4}
    ]


def test_multiple_headers_at_various_levels(tmp_path):
    body = (
        "# Top\n"          # 1
        "intro\n"          # 2
        "## Sub A\n"       # 3
        "alpha\n"          # 4
        "## Sub B\n"       # 5
        "beta\n"           # 6
        "### Sub B.1\n"    # 7
        "gamma\n"          # 8
        "# Top Two\n"      # 9
        "delta\n"          # 10
    )
    p = _write(tmp_path, body)
    sections = parse_markdown_sections(p)
    # Top spans 1..8 (right before the next H1 on line 9)
    assert {"label": "Top", "level": 1, "start_line": 1, "end_line": 8} in sections
    # Sub A: 3..4 (next H2 begins on line 5)
    assert {"label": "Sub A", "level": 2, "start_line": 3, "end_line": 4} in sections
    # Sub B: 5..8 (next H1 on line 9, no H2 before that)
    assert {"label": "Sub B", "level": 2, "start_line": 5, "end_line": 8} in sections
    # Sub B.1: 7..8
    assert {"label": "Sub B.1", "level": 3, "start_line": 7, "end_line": 8} in sections
    # Top Two: 9..10
    assert {"label": "Top Two", "level": 1, "start_line": 9, "end_line": 10} in sections


def test_nested_headers_outer_spans_through_inner(tmp_path):
    body = (
        "# Outer\n"      # 1
        "intro\n"        # 2
        "## Inner\n"     # 3
        "details\n"      # 4
        "more\n"         # 5
    )
    p = _write(tmp_path, body)
    sections = parse_markdown_sections(p)
    outer = next(s for s in sections if s["label"] == "Outer")
    inner = next(s for s in sections if s["label"] == "Inner")
    # Outer extends through nested section
    assert outer["start_line"] == 1
    assert outer["end_line"] == 5
    assert inner["start_line"] == 3
    assert inner["end_line"] == 5


def test_no_headers_returns_empty_list(tmp_path):
    """Decision under ambiguity: file with no headers returns []. This
    matches the docstring contract and lets callers choose how to handle
    header-less files (e.g., pass through to LLM with no line range)."""
    p = _write(tmp_path, "Just some prose.\nNo headers anywhere.\n")
    assert parse_markdown_sections(p) == []


def test_yaml_frontmatter_is_skipped(tmp_path):
    body = (
        "---\n"            # 1
        "title: foo\n"     # 2
        "tags: [a, b]\n"   # 3
        "---\n"            # 4
        "# First\n"        # 5
        "content\n"        # 6
    )
    p = _write(tmp_path, body)
    sections = parse_markdown_sections(p)
    assert sections == [
        {"label": "First", "level": 1, "start_line": 5, "end_line": 6}
    ]


def test_no_trailing_newline_end_line_correct(tmp_path):
    body = "# Title\nline two\nline three"  # no trailing \n
    p = tmp_path / "doc.md"
    p.write_text(body, encoding="utf-8")
    sections = parse_markdown_sections(p)
    assert sections == [
        {"label": "Title", "level": 1, "start_line": 1, "end_line": 3}
    ]


def test_header_inside_fenced_code_block_is_ignored(tmp_path):
    body = (
        "# Real Header\n"     # 1
        "intro\n"             # 2
        "```python\n"         # 3
        "# not a header\n"    # 4
        "## also not\n"       # 5
        "```\n"               # 6
        "## Real Sub\n"       # 7
        "after\n"             # 8
    )
    p = _write(tmp_path, body)
    sections = parse_markdown_sections(p)
    labels = [s["label"] for s in sections]
    assert "Real Header" in labels
    assert "Real Sub" in labels
    assert "not a header" not in labels
    assert "also not" not in labels
    real_sub = next(s for s in sections if s["label"] == "Real Sub")
    assert real_sub["start_line"] == 7
    assert real_sub["end_line"] == 8


def test_four_backtick_fence_with_inner_triple_fence(tmp_path):
    """A 4-backtick fence may legitimately contain a 3-backtick line as content
    (e.g. a markdown doc demonstrating a python fence). The outer fence must
    NOT be closed by the inner triple-fence line. Headers inside the outer
    block are still ignored, and headers AFTER the real 4-backtick closer
    must be recognized."""
    body = (
        "intro\n"                  # 1
        "````markdown\n"           # 2  outer opener (4 backticks)
        "some text\n"              # 3
        "```python\n"              # 4  inner triple-fence (NOT a closer)
        "# this is code\n"         # 5  must be ignored
        "```\n"                    # 6  inner triple-fence (NOT a closer)
        "more text\n"              # 7
        "````\n"                   # 8  real outer closer (4 backticks)
        "# Real Header\n"          # 9  must be recognized
        "body\n"                   # 10
    )
    p = _write(tmp_path, body)
    sections = parse_markdown_sections(p)
    labels = [s["label"] for s in sections]
    assert "Real Header" in labels, (
        f"4-backtick fence was closed early by inner triple-fence; "
        f"got labels {labels}"
    )
    assert "this is code" not in labels
    real = next(s for s in sections if s["label"] == "Real Header")
    assert real["start_line"] == 9
    assert real["end_line"] == 10


def test_tilde_fence_does_not_close_backtick_fence(tmp_path):
    """A tilde run inside a backtick-fenced block must not close it.
    Closer character class must match opener character class."""
    body = (
        "# Outer\n"        # 1
        "intro\n"          # 2
        "```\n"            # 3  backtick opener
        "~~~\n"            # 4  tilde line — must NOT close the backtick fence
        "# fake header\n"  # 5  inside fence → ignored
        "~~~\n"            # 6  tilde line — must NOT close
        "```\n"            # 7  real backtick closer
        "## Real Sub\n"    # 8  after real closer → recognized
        "after\n"          # 9
    )
    p = _write(tmp_path, body)
    sections = parse_markdown_sections(p)
    labels = [s["label"] for s in sections]
    assert "Real Sub" in labels
    assert "fake header" not in labels
    real_sub = next(s for s in sections if s["label"] == "Real Sub")
    assert real_sub["start_line"] == 8
    assert real_sub["end_line"] == 9


def test_five_tilde_fence_with_inner_three_tildes(tmp_path):
    """A 5-tilde opener must not be closed by an inner 3-tilde line.
    Mirror of the 4-backtick case for tildes."""
    body = (
        "intro\n"           # 1
        "~~~~~yaml\n"       # 2  outer opener (5 tildes)
        "key: value\n"      # 3
        "~~~\n"             # 4  inner 3-tilde — must NOT close the 5-tilde fence
        "# this is yaml\n"  # 5  inside fence → ignored
        "~~~\n"             # 6  inner 3-tilde — must NOT close
        "more: data\n"      # 7
        "~~~~~\n"           # 8  real outer closer (5 tildes)
        "# Real Header\n"   # 9  after real closer → recognized
        "body\n"            # 10
    )
    p = _write(tmp_path, body)
    sections = parse_markdown_sections(p)
    labels = [s["label"] for s in sections]
    assert "Real Header" in labels, (
        f"5-tilde fence was closed early by inner 3-tilde; got labels {labels}"
    )
    assert "this is yaml" not in labels
    real = next(s for s in sections if s["label"] == "Real Header")
    assert real["start_line"] == 9


def test_fence_with_info_string_does_not_close_block(tmp_path):
    """A line like ``` ```python ``` is an opener (info string allowed) but
    NOT a closer. CommonMark requires closers to be followed only by whitespace.
    Inside a triple-backtick block, an inner ```python line must be content
    and the real ``` closer one line later must close cleanly."""
    body = (
        "intro\n"           # 1
        "```\n"             # 2  outer opener
        "code line A\n"     # 3
        "```python\n"       # 4  info-string line — NOT a valid closer
        "code line B\n"     # 5
        "```\n"             # 6  real closer
        "# Real Header\n"   # 7  after real closer → recognized
        "body\n"            # 8
    )
    p = _write(tmp_path, body)
    sections = parse_markdown_sections(p)
    labels = [s["label"] for s in sections]
    assert "Real Header" in labels, (
        f"info-string line was treated as a closer; got labels {labels}"
    )
    real = next(s for s in sections if s["label"] == "Real Header")
    assert real["start_line"] == 7


def test_four_space_indent_is_not_a_fence(tmp_path):
    """CommonMark: a fence must be indented 0-3 spaces. A line with 4+ spaces
    of indent is a code block, not a fence — so backticks at column 4 must NOT
    open a fence and the following # line must still be a real header."""
    body = (
        "intro\n"           # 1
        "    ```\n"         # 2  4-space indent: indented code block, NOT a fence
        "still code\n"      # 3
        "    ```\n"         # 4  4-space indent: still code, NOT a fence closer
        "# Real Header\n"   # 5  must be recognized
        "body\n"            # 6
    )
    p = _write(tmp_path, body)
    sections = parse_markdown_sections(p)
    labels = [s["label"] for s in sections]
    assert "Real Header" in labels, (
        f"4-space-indented backticks opened a fake fence; got labels {labels}"
    )
    real = next(s for s in sections if s["label"] == "Real Header")
    assert real["start_line"] == 5


def test_three_space_indent_fence_is_valid(tmp_path):
    """A fence indented 0-3 spaces is a real fence. With 3 spaces of indent,
    the backticks open a real code block, headers inside are ignored."""
    body = (
        "intro\n"           # 1
        "   ```python\n"    # 2  3-space indent: valid opener
        "# inside code\n"   # 3
        "   ```\n"          # 4  3-space indent: valid closer
        "# Real Header\n"   # 5
    )
    p = _write(tmp_path, body)
    sections = parse_markdown_sections(p)
    labels = [s["label"] for s in sections]
    assert "Real Header" in labels
    assert "inside code" not in labels
