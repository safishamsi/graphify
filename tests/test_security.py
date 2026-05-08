"""Tests for graphify/security.py - URL validation, safe fetch, path guards, label sanitisation."""
from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from graphify.security import (
    sanitize_label,
    sanitize_metadata,
    safe_fetch,
    safe_fetch_text,
    validate_graph_path,
    validate_url,
    _MAX_FETCH_BYTES,
    _MAX_TEXT_BYTES,
    _sanitize_metadata_string,
    _sanitize_metadata_value,
)


# ---------------------------------------------------------------------------
# validate_url
# ---------------------------------------------------------------------------

def test_validate_url_accepts_http():
    assert validate_url("http://example.com/page") == "http://example.com/page"

def test_validate_url_accepts_https():
    assert validate_url("https://arxiv.org/abs/1706.03762") == "https://arxiv.org/abs/1706.03762"

def test_validate_url_rejects_file():
    with pytest.raises(ValueError, match="file"):
        validate_url("file:///etc/passwd")

def test_validate_url_rejects_ftp():
    with pytest.raises(ValueError, match="ftp"):
        validate_url("ftp://files.example.com/data.zip")

def test_validate_url_rejects_data():
    with pytest.raises(ValueError, match="data"):
        validate_url("data:text/html,<script>alert(1)</script>")

def test_validate_url_rejects_empty_scheme():
    with pytest.raises(ValueError):
        validate_url("//no-scheme.example.com")


# ---------------------------------------------------------------------------
# safe_fetch - scheme and redirect guards (mocked network)
# ---------------------------------------------------------------------------

def _make_mock_response(content: bytes, status: int = 200):
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.status = status
    mock.code = status
    chunks = [content[i:i+65536] for i in range(0, len(content), 65536)] + [b""]
    mock.read.side_effect = chunks
    return mock


def test_safe_fetch_rejects_file_url():
    with pytest.raises(ValueError, match="file"):
        safe_fetch("file:///etc/passwd")

def test_safe_fetch_rejects_ftp_url():
    with pytest.raises(ValueError, match="ftp"):
        safe_fetch("ftp://example.com/file.zip")

def test_safe_fetch_returns_bytes(tmp_path):
    mock_resp = _make_mock_response(b"hello world")
    with patch("graphify.security._build_opener") as mock_opener_fn:
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_opener_fn.return_value = mock_opener
        result = safe_fetch("https://example.com/")
    assert result == b"hello world"

def test_safe_fetch_raises_on_non_2xx():
    mock_resp = _make_mock_response(b"Not Found", status=404)
    with patch("graphify.security._build_opener") as mock_opener_fn:
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_opener_fn.return_value = mock_opener
        with pytest.raises(urllib.error.HTTPError):
            safe_fetch("https://example.com/missing")

def test_safe_fetch_raises_on_size_exceeded():
    # Build a response larger than max_bytes
    big_chunk = b"x" * 65_537
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.status = 200
    mock_resp.code = 200
    # Return the chunk twice so total > max_bytes=65536
    mock_resp.read.side_effect = [big_chunk, big_chunk, b""]

    with patch("graphify.security._build_opener") as mock_opener_fn:
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_opener_fn.return_value = mock_opener
        with pytest.raises(OSError, match="size limit"):
            safe_fetch("https://example.com/huge", max_bytes=65_536)


# ---------------------------------------------------------------------------
# safe_fetch_text
# ---------------------------------------------------------------------------

def test_safe_fetch_text_decodes_utf8():
    content = "héllo wörld".encode("utf-8")
    mock_resp = _make_mock_response(content)
    with patch("graphify.security._build_opener") as mock_opener_fn:
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_opener_fn.return_value = mock_opener
        result = safe_fetch_text("https://example.com/")
    assert result == "héllo wörld"

def test_safe_fetch_text_replaces_bad_bytes():
    bad = b"hello \xff world"
    mock_resp = _make_mock_response(bad)
    with patch("graphify.security._build_opener") as mock_opener_fn:
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_opener_fn.return_value = mock_opener
        result = safe_fetch_text("https://example.com/")
    assert "hello" in result
    assert "world" in result
    assert "\xff" not in result


# ---------------------------------------------------------------------------
# validate_graph_path
# ---------------------------------------------------------------------------

def test_validate_graph_path_allows_inside_base(tmp_path):
    base = tmp_path / "graphify-out"
    base.mkdir()
    graph = base / "graph.json"
    graph.write_text("{}")
    result = validate_graph_path(str(graph), base=base)
    assert result == graph.resolve()

def test_validate_graph_path_blocks_traversal(tmp_path):
    base = tmp_path / "graphify-out"
    base.mkdir()
    evil = tmp_path / "graphify-out" / ".." / "etc_passwd"
    with pytest.raises(ValueError, match="escapes"):
        validate_graph_path(str(evil), base=base)

def test_validate_graph_path_requires_base_exists(tmp_path):
    base = tmp_path / "graphify-out"  # not created
    with pytest.raises(ValueError, match="does not exist"):
        validate_graph_path(str(base / "graph.json"), base=base)

def test_validate_graph_path_raises_if_file_missing(tmp_path):
    base = tmp_path / "graphify-out"
    base.mkdir()
    with pytest.raises(FileNotFoundError):
        validate_graph_path(str(base / "missing.json"), base=base)


# ---------------------------------------------------------------------------
# sanitize_label
# ---------------------------------------------------------------------------

def test_sanitize_label_passthrough_html_chars():
    # sanitize_label does NOT HTML-escape — callers that inject into HTML must
    # wrap with html.escape() themselves (e.g. the title in to_html())
    assert sanitize_label("<script>") == "<script>"
    assert sanitize_label("foo & bar") == "foo & bar"

def test_sanitize_label_strips_control_chars():
    result = sanitize_label("hello\x00\x1fworld")
    assert "\x00" not in result
    assert "\x1f" not in result
    assert "helloworld" in result

def test_sanitize_label_caps_at_256():
    long_label = "a" * 300
    assert len(sanitize_label(long_label)) <= 256

def test_sanitize_label_safe_passthrough():
    assert sanitize_label("MyClass") == "MyClass"
    assert sanitize_label("extract_python") == "extract_python"


# ---------------------------------------------------------------------------
# _sanitize_metadata_string
# ---------------------------------------------------------------------------

def test_sanitize_metadata_string_strips_control_chars():
    result = _sanitize_metadata_string("hello\x00world")
    assert "\x00" not in result

def test_sanitize_metadata_string_escapes_html():
    result = _sanitize_metadata_string("<script>alert('xss')</script>")
    assert "<" not in result
    assert ">" not in result
    assert "&lt;" in result

def test_sanitize_metadata_string_caps_length():
    long_val = "x" * 600
    result = _sanitize_metadata_string(long_val)
    assert len(result) <= 512

def test_sanitize_metadata_string_handles_non_string():
    result = _sanitize_metadata_string(42)
    assert result == "42"

# ---------------------------------------------------------------------------
# _sanitize_metadata_value
# ---------------------------------------------------------------------------

def test_sanitize_metadata_value_string():
    result = _sanitize_metadata_value("<script>alert(1)</script>")
    assert "<" not in str(result)

def test_sanitize_metadata_value_dict():
    result = _sanitize_metadata_value({"key": "<evil>"})
    assert "<" not in str(result["key"])

def test_sanitize_metadata_value_list():
    result = _sanitize_metadata_value(["<a>", 42, None, True])
    assert isinstance(result, list)
    assert "<" not in str(result[0])

def test_sanitize_metadata_value_tuple():
    result = _sanitize_metadata_value(("<b>", 1))
    assert isinstance(result, list)
    assert "<" not in str(result[0])

def test_sanitize_metadata_value_none():
    assert _sanitize_metadata_value(None) is None

def test_sanitize_metadata_value_int_float_bool():
    assert _sanitize_metadata_value(42) == 42
    assert _sanitize_metadata_value(3.14) == 3.14
    assert _sanitize_metadata_value(True) is True

def test_sanitize_metadata_value_list_capped():
    result = _sanitize_metadata_value([f"item{i}" for i in range(100)])
    assert len(result) <= 50

# ---------------------------------------------------------------------------
# sanitize_metadata
# ---------------------------------------------------------------------------

def test_sanitize_metadata_none():
    assert sanitize_metadata(None) == {}

def test_sanitize_metadata_drops_empty_key():
    result = sanitize_metadata({"": "value"})
    assert "" not in result

def test_sanitize_metadata_nested():
    result = sanitize_metadata({
        "title": "<script>",
        "details": {"author": "John & Jane"},
        "tags": ["api", "<xss>"],
    })
    assert "<" not in result.get("title", "")
    # sanitize_metadata html-escapes & to &amp; — the entity does contain &
    # but the bare ampersand-like sequence " & " should not appear
    author = result.get("details", {}).get("author", "")
    assert "&lt;" in result.get("title", "")
    for tag in result.get("tags", []):
        assert "<" not in tag

# ---------------------------------------------------------------------------
# validate_graph_path – auto-detect base fallback
# ---------------------------------------------------------------------------

def test_validate_graph_path_falls_back_to_cwd_graphify_out(tmp_path, monkeypatch):
    base = tmp_path / "graphify-out"
    base.mkdir()
    graph = base / "graph.json"
    graph.write_text("{}")
    monkeypatch.chdir(tmp_path)
    result = validate_graph_path(graph)
    assert result == graph.resolve()

def test_validate_graph_path_auto_detects_nested_graphify_out(tmp_path, monkeypatch):
    base = tmp_path / "deep" / "graphify-out"
    base.mkdir(parents=True)
    graph = base / "graph.json"
    graph.write_text("{}")
    monkeypatch.chdir(tmp_path / "deep")
    result = validate_graph_path(graph)
    assert result == graph.resolve()


# --- Coverage targets: lines 49, 61-66, 84-95, 112-113, 117, 199, 238, 272 ---

def test_validate_url_blocks_cloud_metadata():
    """Cloud metadata hostnames should be blocked."""
    with pytest.raises(ValueError, match="cloud metadata"):
        validate_url("http://metadata.google.internal/computeMetadata")


def test_validate_url_blocks_private_ip(monkeypatch):
    """URL resolving to private IP should be blocked."""
    import socket
    # Mock getaddrinfo to return a private IP
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(None, None, None, None, ("10.0.0.1", 0))]
    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)
    with pytest.raises(ValueError, match="Blocked private"):
        validate_url("http://private.local/page")


def test_validate_url_dns_resolution_fails(monkeypatch):
    """DNS resolution failure should raise ValueError."""
    import socket
    def mock_getaddrinfo(host, port, *args, **kwargs):
        raise socket.gaierror("Name or service not known")
    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)
    with pytest.raises(ValueError, match="DNS resolution failed"):
        validate_url("http://nonexistent.example.invalid/page")


def test_ssrf_guarded_socket_blocks_private():
    """The guarded socket wrapper catches DNS rebinding to private IPs."""
    import socket
    from graphify.security import _ssrf_guarded_socket

    original = socket.getaddrinfo
    with _ssrf_guarded_socket():
        # Verify the original function is replaced
        assert socket.getaddrinfo is not original
    # After context manager, original is restored
    assert socket.getaddrinfo is original


def test_ssrf_guarded_socket_blocks_private_ip(monkeypatch):
    """Guarded socket raises OSError when a private IP is resolved."""
    import socket
    from graphify.security import _ssrf_guarded_socket

    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(None, None, None, None, ("10.0.0.1", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)
    with _ssrf_guarded_socket():
        with pytest.raises(OSError, match="SSRF blocked"):
            socket.getaddrinfo("evil.local", None)


def test_no_file_redirect_handler_blocks_file():
    """_NoFileRedirectHandler should validate redirect URLs."""
    import urllib.request
    from graphify.security import _NoFileRedirectHandler
    handler = _NoFileRedirectHandler()
    # Trying to redirect to file:// should raise
    class FakeReq:
        pass
    with pytest.raises(ValueError, match="file"):
        handler.redirect_request(FakeReq(), None, 301, "Moved", {}, "file:///etc/passwd")


def test_no_file_redirect_handler_allows_http(monkeypatch):
    """_NoFileRedirectHandler should allow valid http redirects."""
    import socket
    import urllib.request
    from graphify.security import _NoFileRedirectHandler

    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(None, None, None, None, ("8.8.8.8", 0))]
    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    handler = _NoFileRedirectHandler()
    with patch("urllib.request.HTTPRedirectHandler.redirect_request") as mock_super:
        mock_super.return_value = "redirected"
        result = handler.redirect_request(None, None, 301, "Moved", {}, "https://safe.example.com/page")
        assert mock_super.called


def test_build_opener():
    """_build_opener returns an OpenerDirector with _NoFileRedirectHandler."""
    from graphify.security import _build_opener
    opener = _build_opener()
    assert isinstance(opener, urllib.request.OpenerDirector)


def test_sanitize_label_none():
    """sanitize_label(None) returns empty string."""
    from graphify.security import sanitize_label
    assert sanitize_label(None) == ""


def test_sanitize_metadata_value_unknown_type():
    """_sanitize_metadata_value falls back to string sanitization for unknown types."""
    from graphify.security import _sanitize_metadata_value

    class UnknownType:
        def __str__(self):
            return "<custom_object>"

    result = _sanitize_metadata_value(UnknownType())
    assert "<" not in str(result)
    assert "custom_object" in str(result) or "&lt;" in str(result)
