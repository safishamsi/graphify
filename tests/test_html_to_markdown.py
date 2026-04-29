"""Tests for graphify.ingest._html_to_markdown and HTML→markdown ingestion path."""
from __future__ import annotations

import importlib.util
import sys

import pytest

from graphify.ingest import _html_to_markdown, _fetch_webpage

# markdownify is an optional dependency (declared in the `pdf`/`all` extras).
# Tests that assert markdownify-specific output are gated behind this marker so
# the suite still runs cleanly on a base install (`pip install -e .`).
_HAS_MARKDOWNIFY = importlib.util.find_spec("markdownify") is not None
requires_markdownify = pytest.mark.skipif(
    not _HAS_MARKDOWNIFY,
    reason="markdownify not installed (optional 'pdf' extra)",
)


# --- Direct conversion tests ---------------------------------------------------

def test_basic_paragraph():
    out = _html_to_markdown("<p>Hello world</p>", "http://example.com")
    assert "Hello world" in out
    assert "<p>" not in out


@requires_markdownify
def test_heading_atx_style():
    out = _html_to_markdown("<h1>Title</h1>", "http://example.com")
    assert "# Title" in out
    # Confirm we did NOT get setext (===) style
    assert "===" not in out


@requires_markdownify
def test_links_preserved():
    html = '<p>See <a href="https://example.com/x">x</a> for more.</p>'
    out = _html_to_markdown(html, "http://example.com")
    assert "[x](https://example.com/x)" in out


def test_images_dropped():
    html = '<p>before</p><img src="https://example.com/cat.png" alt="cat"><p>after</p>'
    out = _html_to_markdown(html, "http://example.com")
    assert "before" in out
    assert "after" in out
    # Image should not appear as markdown image syntax or as a raw tag
    assert "![" not in out
    assert "<img" not in out
    assert "cat.png" not in out


def test_script_and_style_stripped():
    html = (
        "<style>.x{color:red}</style>"
        "<script>alert(1)</script>"
        "<p>visible content</p>"
    )
    out = _html_to_markdown(html, "http://example.com")
    assert "visible content" in out
    assert "alert" not in out
    assert "color:red" not in out


@requires_markdownify
def test_bullet_list():
    html = "<ul><li>alpha</li><li>beta</li></ul>"
    out = _html_to_markdown(html, "http://example.com")
    assert "- alpha" in out
    assert "- beta" in out


@requires_markdownify
def test_no_body_wrapping():
    long_text = "word " * 50  # ~250 chars on one line
    html = f"<p>{long_text.strip()}</p>"
    out = _html_to_markdown(html, "http://example.com")
    # The single paragraph should survive as one logical line (no hard wrap at 80 cols).
    # Find the line containing 'word' and assert it's not chopped.
    longest = max((len(line) for line in out.splitlines() if "word" in line), default=0)
    assert longest > 200, f"output appears wrapped: longest 'word' line = {longest}"


def test_empty_html():
    out = _html_to_markdown("", "http://example.com")
    assert out.strip() == ""


def test_malformed_html_no_exception():
    # markdownify / bs4 should be lenient; our regex fallback must also be.
    html = "<p>unclosed <span>nested <b>bold"
    out = _html_to_markdown(html, "http://example.com")
    assert "unclosed" in out
    assert "nested" in out
    assert "bold" in out


# --- Fallback path -------------------------------------------------------------

def test_fallback_when_markdownify_missing(monkeypatch):
    """If markdownify cannot be imported, the regex-strip fallback must still
    return readable plain text without raising."""
    # Force ImportError for the lazy `from markdownify import markdownify`
    monkeypatch.setitem(sys.modules, "markdownify", None)
    html = (
        "<style>.x{color:red}</style>"
        "<script>alert(1)</script>"
        "<h1>Title</h1><p>body text here</p>"
    )
    out = _html_to_markdown(html, "http://example.com")
    assert "Title" in out
    assert "body text here" in out
    # Stripped noise
    assert "alert" not in out
    assert "color:red" not in out
    # Fallback returns plain text (no markdown headings)
    assert "<" not in out


def test_fallback_basic_text_extraction(monkeypatch):
    """Fallback path must extract readable text from a realistic HTML mix
    (heading + list + paragraph), with all tags removed. Runs unconditionally
    so base installs (`pip install -e .`) still get end-to-end coverage of
    the regex-strip path."""
    monkeypatch.setitem(sys.modules, "markdownify", None)
    html = "<h1>T</h1><ul><li>a</li><li>b</li></ul><p>p</p>"
    out = _html_to_markdown(html, "http://example.com")
    for token in ("T", "a", "b", "p"):
        assert token in out, f"missing {token!r} in fallback output: {out!r}"
    assert "<" not in out


# --- Integration with _fetch_webpage ------------------------------------------

@requires_markdownify
def test_fetch_webpage_uses_converter(monkeypatch):
    """End-to-end smoke for the only caller of _html_to_markdown."""
    canned_html = (
        "<html><head><title>Example Page</title></head>"
        "<body><h1>Heading</h1><p>Paragraph with "
        '<a href="https://example.com/link">a link</a>.</p></body></html>'
    )
    monkeypatch.setattr("graphify.ingest._fetch_html", lambda url: canned_html)

    content, filename = _fetch_webpage(
        "https://example.com/page",
        author=None,
        contributor="tester",
    )

    # Frontmatter (string values may be quoted or unquoted depending on impl)
    assert "https://example.com/page" in content
    assert "type: webpage" in content
    assert "Example Page" in content  # title
    assert "tester" in content  # contributor

    # Converted markdown body
    assert "# Heading" in content
    assert "[a link](https://example.com/link)" in content

    # Filename safe
    assert filename.endswith(".md")
    assert "/" not in filename


# --- Regression guard ----------------------------------------------------------

def test_html2text_not_referenced_in_source():
    """Prevent accidental reintroduction of the GPL-3.0 dependency."""
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    # Only check shippable code + dependency manifest. Skip docs/skill files
    # (which may reference html2text in historical context only) and tests.
    targets = list((repo_root / "graphify").rglob("*.py"))
    targets.append(repo_root / "pyproject.toml")
    for path in targets:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "html2text" in text:
            offenders.append(str(path.relative_to(repo_root)))
    assert not offenders, (
        "html2text references found (GPL-3.0, must not return): "
        + ", ".join(offenders)
    )
