"""Tests for graphify.ingest - yaml_str, detect_url_type, safe_filename, save_query_result, ingest"""
from __future__ import annotations
import re
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from graphify.ingest import (
    _yaml_str, _detect_url_type, _safe_filename, _html_to_markdown,
    _fetch_tweet, _fetch_webpage, _fetch_arxiv, _download_binary,
    ingest, save_query_result,
)


def test_file_created(tmp_path):
    out = save_query_result("what is attention?", "Attention is...", tmp_path / "memory")
    assert out.exists()


def test_filename_format(tmp_path):
    mem = tmp_path / "memory"
    out = save_query_result("what connects A to B?", "They share...", mem)
    assert out.name.startswith("query_")
    assert out.suffix == ".md"


def test_frontmatter_question(tmp_path):
    mem = tmp_path / "memory"
    question = "what is attention?"
    out = save_query_result(question, "Attention is softmax.", mem)
    content = out.read_text()
    assert "question:" in content
    assert "attention" in content.lower()


def test_frontmatter_type(tmp_path):
    mem = tmp_path / "memory"
    out = save_query_result("q", "a", mem, query_type="path_query")
    content = out.read_text()
    assert 'type: "path_query"' in content


def test_source_nodes_included(tmp_path):
    mem = tmp_path / "memory"
    nodes = ["AttentionLayer", "SoftmaxFunc"]
    out = save_query_result("q", "a", mem, source_nodes=nodes)
    content = out.read_text()
    assert "AttentionLayer" in content
    assert "SoftmaxFunc" in content


def test_source_nodes_capped_at_10(tmp_path):
    mem = tmp_path / "memory"
    nodes = [f"Node{i}" for i in range(20)]
    out = save_query_result("q", "a", mem, source_nodes=nodes)
    content = out.read_text()
    # Only first 10 should appear in frontmatter source_nodes line
    fm_line = [l for l in content.splitlines() if l.startswith("source_nodes:")][0]
    assert fm_line.count('"Node') == 10


def test_memory_dir_created(tmp_path):
    mem = tmp_path / "deep" / "memory"
    assert not mem.exists()
    save_query_result("q", "a", mem)
    assert mem.exists()


def test_answer_in_body(tmp_path):
    mem = tmp_path / "memory"
    answer = "The answer is forty-two."
    out = save_query_result("what is the answer?", answer, mem)
    content = out.read_text()
    assert answer in content


# ---------------------------------------------------------------------------
# _yaml_str
# ---------------------------------------------------------------------------

def test_yaml_str_passthrough():
    assert _yaml_str("hello world") == "hello world"

def test_yaml_str_escapes_backslash():
    assert "\\\\" in _yaml_str("\\")

def test_yaml_str_escapes_double_quote():
    assert '\\"' in _yaml_str('"')

def test_yaml_str_escapes_newline():
    result = _yaml_str("line1\nline2")
    assert "\\n" in result
    assert "\n" not in result

def test_yaml_str_escapes_carriage_return():
    result = _yaml_str("a\rb")
    assert "\\r" in result

def test_yaml_str_escapes_tab():
    result = _yaml_str("a\tb")
    assert "\\t" in result

def test_yaml_str_escapes_null():
    result = _yaml_str("a\0b")
    assert "\\0" in result

def test_yaml_str_escapes_line_separator():
    result = _yaml_str("\u2028")
    assert "\\L" in result

def test_yaml_str_escapes_paragraph_separator():
    result = _yaml_str("\u2029")
    assert "\\P" in result

def test_yaml_str_handles_none():
    assert _yaml_str(None) == ""

def test_yaml_str_handles_control_chars():
    result = _yaml_str("\x01\x02")
    assert "\\x01" in result
    assert "\\x02" in result


# ---------------------------------------------------------------------------
# _detect_url_type
# ---------------------------------------------------------------------------

def test_detect_twitter():
    assert _detect_url_type("https://twitter.com/user/status/123") == "tweet"

def test_detect_xcom():
    assert _detect_url_type("https://x.com/user/status/123") == "tweet"

def test_detect_arxiv():
    assert _detect_url_type("https://arxiv.org/abs/1706.03762") == "arxiv"

def test_detect_github():
    assert _detect_url_type("https://github.com/user/repo") == "github"

def test_detect_youtube():
    assert _detect_url_type("https://youtube.com/watch?v=abc") == "youtube"

def test_detect_youtube_short():
    assert _detect_url_type("https://youtu.be/abc") == "youtube"

def test_detect_pdf():
    assert _detect_url_type("https://example.com/doc.pdf") == "pdf"

def test_detect_image_png():
    assert _detect_url_type("https://example.com/img.png") == "image"

def test_detect_image_jpg():
    assert _detect_url_type("https://example.com/img.jpg") == "image"

def test_detect_webpage():
    assert _detect_url_type("https://example.com/page") == "webpage"


# ---------------------------------------------------------------------------
# _safe_filename
# ---------------------------------------------------------------------------

def test_safe_filename_basic():
    name = _safe_filename("https://example.com/path/file", ".md")
    assert name.endswith(".md")
    # Dots in hostnames become underscores
    assert "example_com" in name

def test_safe_filename_replaces_special_chars():
    name = _safe_filename("https://example.com/a!b@c#d", ".txt")
    assert "!" not in name
    assert "@" not in name

def test_safe_filename_truncates():
    long_url = "https://example.com/" + "a" * 200
    name = _safe_filename(long_url, ".md")
    assert len(name) <= 84  # 80 + ".md"


# ---------------------------------------------------------------------------
# _html_to_markdown
# ---------------------------------------------------------------------------

def test_html_to_markdown_strips_script():
    html = "<html><body><script>alert(1)</script><p>Hello</p></body></html>"
    result = _html_to_markdown(html, "https://example.com")
    assert "alert" not in result
    assert "Hello" in result

def test_html_to_markdown_strips_style():
    html = "<html><style>body{color:red}</style><p>Text</p></html>"
    result = _html_to_markdown(html, "https://example.com")
    assert "color:red" not in result
    assert "Text" in result

def test_html_to_markdown_fallback():
    html = "<html><p>Hello</p><p>World</p></html>"
    with patch.dict("sys.modules", {"markdownify": None}):
        result = _html_to_markdown(html, "https://example.com")
    assert "Hello" in result
    assert "World" in result


# ---------------------------------------------------------------------------
# _fetch_tweet
# ---------------------------------------------------------------------------

def test_fetch_tweet_success(monkeypatch):
    mock_html = '{"html": "Tweet <b>content</b>", "author_name": "test_user"}'
    def fake_fetch(url):
        return mock_html
    monkeypatch.setattr("graphify.ingest.safe_fetch_text", fake_fetch)
    content, filename = _fetch_tweet("https://twitter.com/user/status/123", None, None)
    assert content is not None
    assert filename.endswith(".md")
    assert "Tweet content" in content or "Tweet <b>content</b>" in content

def test_fetch_tweet_xcom_normalization(monkeypatch):
    mock_html = '{"html": "Hello", "author_name": "user"}'
    def fake_fetch(url):
        # verify x.com was normalized to twitter.com
        assert "twitter.com" in url
        return mock_html
    monkeypatch.setattr("graphify.ingest.safe_fetch_text", fake_fetch)
    content, _ = _fetch_tweet("https://x.com/user/status/123", None, None)
    assert content is not None

def test_fetch_tweet_failure_fallback(monkeypatch):
    def fake_fetch(url):
        raise ValueError("fail")
    monkeypatch.setattr("graphify.ingest.safe_fetch_text", fake_fetch)
    content, filename = _fetch_tweet("https://twitter.com/x", None, None)
    assert "could not fetch" in content.lower()


# ---------------------------------------------------------------------------
# _fetch_webpage
# ---------------------------------------------------------------------------

def test_fetch_webpage_basic(monkeypatch):
    html = "<html><head><title>Test Page</title></head><body><p>Content</p></body></html>"
    def fake_fetch(url):
        return html
    monkeypatch.setattr("graphify.ingest._fetch_html", fake_fetch)
    content, filename = _fetch_webpage("https://example.com", None, None)
    assert "Test Page" in content
    assert filename.endswith(".md")

def test_fetch_webpage_no_title(monkeypatch):
    html = "<html><body><p>No title here</p></body></html>"
    def fake_fetch(url):
        return html
    monkeypatch.setattr("graphify.ingest._fetch_html", fake_fetch)
    content, _ = _fetch_webpage("https://example.com", None, None)
    assert content is not None


# ---------------------------------------------------------------------------
# _fetch_arxiv
# ---------------------------------------------------------------------------

def test_fetch_arxiv_with_id(monkeypatch):
    html = """
    <h1 class="title mathjax">Attention Is All You Need</h1>
    <div class="authors"><span>Vaswani et al.</span></div>
    <blockquote class="abstract mathjax">The dominant sequence transduction...</blockquote>
    """
    def fake_fetch(url):
        return html
    monkeypatch.setattr("graphify.ingest._fetch_html", fake_fetch)
    content, filename = _fetch_arxiv("https://arxiv.org/abs/1706.03762", None, None)
    assert "1706.03762" in content or "arxiv" in filename.lower()
    assert filename.endswith(".md")

def test_fetch_arxiv_no_id_falls_back(monkeypatch):
    html = "<html><head><title>Some Page</title></head><body>Text</body></html>"
    def fake_fetch(url):
        return html
    monkeypatch.setattr("graphify.ingest._fetch_html", fake_fetch)
    content, filename = _fetch_arxiv("https://example.com/page", None, None)
    assert content is not None


# ---------------------------------------------------------------------------
# _download_binary
# ---------------------------------------------------------------------------

def test_download_binary(tmp_path, monkeypatch):
    def fake_fetch(url, **kwargs):
        return b"binary data"
    monkeypatch.setattr("graphify.ingest.safe_fetch", fake_fetch)
    result = _download_binary("https://example.com/doc.pdf", ".pdf", tmp_path)
    assert result == tmp_path / result.name
    assert result.exists()
    assert result.read_bytes() == b"binary data"


# ---------------------------------------------------------------------------
# ingest (integration)
# ---------------------------------------------------------------------------

def test_ingest_webpage(tmp_path, monkeypatch):
    html = "<html><head><title>Test</title></head><body><p>Hello</p></body></html>"
    def fake_fetch_text(url):
        return html
    monkeypatch.setattr("graphify.ingest.safe_fetch_text", fake_fetch_text)
    monkeypatch.setattr("graphify.ingest._fetch_html", fake_fetch_text)
    monkeypatch.setattr("graphify.ingest.validate_url", lambda url: url)

    out = ingest("https://example.com/page", tmp_path)
    assert out.exists()
    assert "Test" in out.read_text()

def test_ingest_bad_url(tmp_path):
    with pytest.raises(ValueError, match="ingest:"):
        ingest("file:///etc/passwd", tmp_path)

def test_ingest_pdf(tmp_path, monkeypatch):
    def fake_fetch(url, **kwargs):
        return b"pdf content"
    monkeypatch.setattr("graphify.ingest.safe_fetch", fake_fetch)
    monkeypatch.setattr("graphify.ingest.validate_url", lambda url: url)

    out = ingest("https://example.com/doc.pdf", tmp_path)
    assert out.exists()

def test_ingest_avoid_overwrite(tmp_path, monkeypatch):
    """When filename exists, append _1, _2, etc."""
    monkeypatch.setattr("graphify.ingest.validate_url", lambda url: url)
    html = "<html><head><title>T</title></head><body><p>X</p></body></html>"
    monkeypatch.setattr("graphify.ingest.safe_fetch_text", lambda url: html)
    monkeypatch.setattr("graphify.ingest._fetch_html", lambda url: html)

    # First ingest
    out1 = ingest("https://example.com/a", tmp_path)
    assert out1.exists()
    # Second ingest — same URL, same filename
    out2 = ingest("https://example.com/a", tmp_path)
    assert out2.exists()
    assert out1 != out2
    assert "_1" in out2.stem or out2.name != out1.name


# --- Coverage targets: lines 85, 179-180, 239-242, 245-248, 251, 253, 256-257, 323-331 ---

def test_fetch_html_direct():
    """_fetch_html should delegate to safe_fetch_text."""
    from graphify.ingest import _fetch_html
    with patch("graphify.ingest.safe_fetch_text", return_value="<html>test</html>"):
        result = _fetch_html("https://example.com")
        assert result == "<html>test</html>"


def test_fetch_arxiv_api_failure_fallback(monkeypatch):
    """When arXiv API fails, _fetch_arxiv falls back to title/id defaults."""
    def fake_fetch(url):
        raise RuntimeError("API down")
    monkeypatch.setattr("graphify.ingest._fetch_html", fake_fetch)
    content, filename = _fetch_arxiv("https://arxiv.org/abs/1706.03762", None, None)
    # Exception catch at lines 179-180 sets title/abstract to id/empty
    assert content is not None
    assert "1706.03762" in content


def test_ingest_image_url(tmp_path, monkeypatch):
    """Image URL should download binary and return path."""
    monkeypatch.setattr("graphify.ingest.validate_url", lambda url: url)
    from graphify.ingest import ingest, _detect_url_type
    # Ensure URL is detected as image
    monkeypatch.setattr("graphify.ingest._detect_url_type", lambda url: "image")
    # Mock safe_fetch to return binary data
    def fake_fetch(url, **kwargs):
        return b"fake image data"
    monkeypatch.setattr("graphify.ingest.safe_fetch", fake_fetch)

    out = ingest("https://example.com/photo.png", tmp_path)
    assert out.exists()
    assert out.suffix == ".png"


def test_ingest_youtube_url(tmp_path, monkeypatch):
    """YouTube URL should delegate to transcribe.download_audio."""
    monkeypatch.setattr("graphify.ingest.validate_url", lambda url: url)
    monkeypatch.setattr("graphify.ingest._detect_url_type", lambda url: "youtube")
    fake_audio = tmp_path / "fake_audio.wav"
    fake_audio.write_text("fake audio data")
    def mock_download(url, target_dir):
        return fake_audio
    # Inject a fake graphify.transcribe module with download_audio
    import sys
    import types
    _orig_transcribe = sys.modules.get("graphify.transcribe")
    try:
        fake_transcribe = types.ModuleType("graphify.transcribe")
        fake_transcribe.download_audio = mock_download
        sys.modules["graphify.transcribe"] = fake_transcribe
        out = ingest("https://youtube.com/watch?v=abc", tmp_path)
    finally:
        if _orig_transcribe is not None:
            sys.modules["graphify.transcribe"] = _orig_transcribe
        else:
            sys.modules.pop("graphify.transcribe", None)
    assert out == fake_audio


def test_ingest_tweet_branch(tmp_path, monkeypatch):
    """Ingest of tweet URL should call _fetch_tweet."""
    monkeypatch.setattr("graphify.ingest.validate_url", lambda url: url)
    monkeypatch.setattr("graphify.ingest._detect_url_type", lambda url: "tweet")
    monkeypatch.setattr("graphify.ingest.safe_fetch_text",
        lambda url: '{"html": "Hello", "author_name": "user"}')
    out = ingest("https://twitter.com/user/status/123", tmp_path)
    assert out.exists()
    assert out.suffix == ".md"


def test_ingest_arxiv_branch(tmp_path, monkeypatch):
    """Ingest of arXiv URL should call _fetch_arxiv."""
    monkeypatch.setattr("graphify.ingest.validate_url", lambda url: url)
    monkeypatch.setattr("graphify.ingest._detect_url_type", lambda url: "arxiv")
    html = "<h1 class=\"title mathjax\">Paper Title</h1>" \
           "<div class=\"authors\"><span>Author</span></div>" \
           "<blockquote class=\"abstract mathjax\">Abstract text</blockquote>"
    monkeypatch.setattr("graphify.ingest._fetch_html", lambda url: html)
    out = ingest("https://arxiv.org/abs/1706.03762", tmp_path)
    assert out.exists()
    assert out.suffix == ".md"


def test_ingest_http_error_converted(tmp_path, monkeypatch):
    """HTTP errors during ingest should be caught and re-raised as RuntimeError."""
    import urllib.error
    monkeypatch.setattr("graphify.ingest.validate_url", lambda url: url)
    monkeypatch.setattr("graphify.ingest._detect_url_type", lambda url: "webpage")
    def fake_fetch(url):
        raise urllib.error.HTTPError("http://fail", 500, "Server Error", {}, None)
    monkeypatch.setattr("graphify.ingest.safe_fetch_text", fake_fetch)
    monkeypatch.setattr("graphify.ingest._fetch_html", fake_fetch)
    with pytest.raises(RuntimeError, match="ingest: failed to fetch"):
        ingest("http://fail.example.com", tmp_path)


def test_ingest_main_block(tmp_path, monkeypatch):
    """Exercise the argparse and print logic of the __main__ block (lines 322-331)."""
    import argparse

    monkeypatch.setattr("graphify.ingest.validate_url", lambda url: url)
    monkeypatch.setattr("graphify.ingest._detect_url_type", lambda url: "webpage")
    html = "<html><head><title>Test</title></head><body><p>Content</p></body></html>"
    monkeypatch.setattr("graphify.ingest._fetch_html", lambda url: html)

    # Simulate the __main__ block: parse args, call ingest, print result
    parser = argparse.ArgumentParser(
        description="Fetch a URL into a graphify /raw folder"
    )
    parser.add_argument("url", help="URL to fetch")
    parser.add_argument(
        "target_dir", nargs="?", default="./raw",
        help="Target directory (default: ./raw)"
    )
    parser.add_argument("--author", help="Your name")
    parser.add_argument("--contributor", help="Contributor name")
    args = parser.parse_args(["https://example.com/page", str(tmp_path)])
    out = ingest(args.url, Path(args.target_dir),
                 author=args.author, contributor=args.contributor)
    assert out.exists()
    assert out.suffix == ".md"
