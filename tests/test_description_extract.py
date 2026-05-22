"""Tests for _extract_description in graphify.extract."""
import pytest
from pathlib import Path
from textwrap import dedent


@pytest.fixture
def tmp_py(tmp_path):
    """Helper to write a Python file and return its path."""
    def _write(content):
        p = tmp_path / "sample.py"
        p.write_text(dedent(content), encoding="utf-8")
        return p
    return _write


def _extract(path):
    """Run extraction and return nodes with descriptions."""
    from graphify.extract import extract_python
    result = extract_python(path)
    return {n["label"]: n.get("description", "") for n in result["nodes"]}


def test_python_docstring_extraction(tmp_py):
    path = tmp_py('''
        def validate_token(token):
            """Validates JWT tokens for API authentication."""
            return True
    ''')
    nodes = _extract(path)
    assert "validate_token()" in nodes
    assert "Validates JWT tokens" in nodes["validate_token()"]


def test_python_class_docstring(tmp_py):
    path = tmp_py('''
        class SessionManager:
            """Manages user session lifecycle and expiry."""
            pass
    ''')
    nodes = _extract(path)
    assert "SessionManager" in nodes
    assert "session lifecycle" in nodes["SessionManager"]


def test_leading_comment_extraction(tmp_py):
    path = tmp_py('''
        # Reads configuration from YAML files on disk
        def load_config():
            pass
    ''')
    nodes = _extract(path)
    assert "load_config()" in nodes
    assert "configuration" in nodes["load_config()"] or "YAML" in nodes["load_config()"]


def test_decorative_separator_filtered(tmp_py):
    path = tmp_py('''
        # ──────────────────────────────────────
        def boring_func():
            pass
    ''')
    nodes = _extract(path)
    # Decorative comment should NOT become a description
    assert nodes.get("boring_func()", "") == ""


def test_no_description_returns_empty(tmp_py):
    path = tmp_py('''
        def simple():
            return 42
    ''')
    nodes = _extract(path)
    assert nodes.get("simple()", "") == ""


def test_truncation_200_chars(tmp_py):
    long_doc = "A" * 300
    path = tmp_py(f'''
        def long_doc_func():
            """{long_doc}"""
            pass
    ''')
    nodes = _extract(path)
    desc = nodes.get("long_doc_func()", "")
    assert len(desc) <= 203  # 200 + "..."
    assert desc.endswith("...")


def test_multiline_docstring_collapsed(tmp_py):
    path = tmp_py('''
        def multi():
            """First line.
            Second line.
            Third line."""
            pass
    ''')
    nodes = _extract(path)
    desc = nodes.get("multi()", "")
    # Newlines should be collapsed to spaces
    assert "\n" not in desc
    if desc:
        assert "First line" in desc
