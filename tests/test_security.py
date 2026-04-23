"""Tests for graphify/security.py - URL validation, safe fetch, path guards, label sanitisation."""
from __future__ import annotations

import json
import socket
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from graphify.security import (
    sanitize_label,
    safe_fetch,
    safe_fetch_text,
    validate_graph_path,
    validate_url,
    _MAX_FETCH_BYTES,
    _MAX_TEXT_BYTES,
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
    mock.getheader = MagicMock(return_value=None)
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
    with patch("graphify.security._open_direct") as mock_open:
        mock_conn = MagicMock()
        mock_open.return_value = (mock_conn, mock_resp)
        result = safe_fetch("https://example.com/")
    assert result == b"hello world"

def test_safe_fetch_raises_on_non_2xx():
    mock_resp = _make_mock_response(b"Not Found", status=404)
    with patch("graphify.security._open_direct") as mock_open:
        mock_conn = MagicMock()
        mock_open.return_value = (mock_conn, mock_resp)
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

    with patch("graphify.security._open_direct") as mock_open:
        mock_conn = MagicMock()
        mock_open.return_value = (mock_conn, mock_resp)
        with pytest.raises(OSError, match="size limit"):
            safe_fetch("https://example.com/huge", max_bytes=65_536)


def test_safe_fetch_revalidates_redirect_targets():
    redirect = _make_mock_response(b"", status=302)
    redirect.getheader = MagicMock(return_value="http://127.0.0.1/private")
    with patch("graphify.security._open_direct") as mock_open:
        mock_conn = MagicMock()
        mock_open.return_value = (mock_conn, redirect)
        with pytest.raises(ValueError, match="Blocked private/internal IP"):
            safe_fetch("https://example.com/start")


def test_validate_url_rejects_private_resolution():
    with patch("graphify.security.socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 0))]):
        with pytest.raises(ValueError, match="Blocked private/internal IP"):
            validate_url("https://evil.example/")


def test_validate_url_allows_dns_failure_to_surface_later():
    with patch("graphify.security.socket.getaddrinfo", side_effect=socket.gaierror):
        assert validate_url("https://example.com/") == "https://example.com/"


# ---------------------------------------------------------------------------
# safe_fetch_text
# ---------------------------------------------------------------------------

def test_safe_fetch_text_decodes_utf8():
    content = "héllo wörld".encode("utf-8")
    mock_resp = _make_mock_response(content)
    with patch("graphify.security._open_direct") as mock_open:
        mock_conn = MagicMock()
        mock_open.return_value = (mock_conn, mock_resp)
        result = safe_fetch_text("https://example.com/")
    assert result == "héllo wörld"

def test_safe_fetch_text_replaces_bad_bytes():
    bad = b"hello \xff world"
    mock_resp = _make_mock_response(bad)
    with patch("graphify.security._open_direct") as mock_open:
        mock_conn = MagicMock()
        mock_open.return_value = (mock_conn, mock_resp)
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
