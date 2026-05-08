"""Tests for graphify/tree_html.py - tree builder and HTML emitter."""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from graphify.tree_html import (
    _common_root,
    _make_truncation_leaf,
    build_tree,
    emit_html,
    write_tree_html,
    DEFAULT_MAX_CHILDREN,
)


# ── _common_root ──────────────────────────────────────────────────

def test_common_root_empty():
    assert _common_root([]) == ""

def test_common_root_single():
    assert _common_root(["a/b/c.py"]) == "a/b/c.py"

def test_common_root_multi_same():
    paths = ["src/module/a.py", "src/module/b.py"]
    assert _common_root(paths) == "src/module"

def test_common_root_no_common():
    paths = ["/foo/a.py", "/bar/b.py"]
    assert _common_root(paths) == "/"


# ── _make_truncation_leaf ─────────────────────────────────────────

def test_truncation_leaf():
    leaf = _make_truncation_leaf(42)
    assert leaf["name"] == "(+42 more)"
    assert leaf["total_count"] == 42
    assert leaf["children"] == []


# ── build_tree ────────────────────────────────────────────────────

def _sample_nodes(*paths_labels):
    """Build node dicts with source_file and label."""
    return [
        {"id": f"n{i}", "label": lbl, "source_file": pth, "file_type": "code"}
        for i, (pth, lbl) in enumerate(paths_labels)
    ]


def test_build_tree_empty_graph():
    tree = build_tree({"nodes": []})
    assert tree["name"] == "(empty graph)"
    assert tree["total_count"] == 0


def test_build_tree_no_source_files():
    nodes = [{"label": "orphan", "source_file": ""}]
    tree = build_tree({"nodes": nodes})
    assert tree["name"] == "(empty graph)"


def test_build_tree_basic():
    nodes = _sample_nodes(
        ("src/main.py", "main"),
        ("src/main.py", "run"),
        ("src/util.py", "helper"),
    )
    tree = build_tree({"nodes": nodes})
    assert tree["total_count"] > 0
    assert len(tree["children"]) >= 1


def test_build_tree_with_root():
    nodes = _sample_nodes(
        ("/home/user/proj/src/a.py", "funcA"),
        ("/home/user/proj/src/b.py", "funcB"),
    )
    tree = build_tree({"nodes": nodes}, root="/home/user/proj")
    assert tree["name"] == "proj"
    assert tree["total_count"] == 2


def test_build_tree_project_label():
    nodes = _sample_nodes(("a.py", "f"))
    tree = build_tree({"nodes": nodes}, project_label="MyProject")
    assert tree["name"] == "MyProject"


def test_build_tree_skips_file_name_nodes():
    """Nodes whose label equals the source filename (and file_type=code) are skipped."""
    nodes = [
        {"id": "n1", "label": "main.py", "source_file": "src/main.py", "file_type": "code"},
        {"id": "n2", "label": "realFunc", "source_file": "src/main.py", "file_type": "code"},
    ]
    tree = build_tree({"nodes": nodes})
    # Only realFunc should appear
    assert tree["total_count"] == 1

def test_build_tree_truncation():
    """When symbols exceed max_children, a (+N more) leaf appears."""
    nodes = _sample_nodes(*[("f.py", f"func{i}") for i in range(50)])
    tree = build_tree({"nodes": nodes}, max_children=10)
    # Should have truncation leaf
    def find_truncation(d):
        for child in d.get("children", []):
            if "(+" in child.get("name", ""):
                return True
            if find_truncation(child):
                return True
        return False
    assert find_truncation(tree)


def test_build_tree_sorts_children():
    nodes = _sample_nodes(
        ("src/z.py", "zFunc"),
        ("src/a.py", "aFunc"),
    )
    tree = build_tree({"nodes": nodes})
    children = tree["children"]
    names = [c["name"] for c in children]
    assert names == sorted(names, key=str.lower)


# ── emit_html ─────────────────────────────────────────────────────

def test_emit_html_basic():
    tree = {"name": "root", "total_count": 1, "children": []}
    html = emit_html(tree, title="Test", header="My Graph")
    assert "<!DOCTYPE html>" in html
    assert "<title>Test</title>" in html
    assert "My Graph" in html
    assert "d3.v7" in html


def test_emit_html_escapes_script_tag():
    tree = {"name": "root", "children": [{"name": "</script><script>alert(1)</script>", "total_count": 1, "children": []}], "total_count": 1}
    html = emit_html(tree, title="T", header="H")
    assert "</script>" not in html or "<\\/" in html


def test_emit_html_escapes_title():
    tree = {"name": "root", "total_count": 0, "children": []}
    html = emit_html(tree, title='<script>alert("xss")</script>', header="H")
    # User-supplied title is HTML-escaped in the <title> tag
    assert "&lt;script&gt;alert" in html
    assert '<script>alert("xss")</script>' not in html


def test_emit_html_preserves_data():
    tree = {"name": "test", "total_count": 5, "children": [
        {"name": "child", "total_count": 2, "children": []}
    ]}
    html = emit_html(tree, title="T", header="H")
    # JSON data should be embedded
    assert '"name":"test"' in html
    assert '"total_count":5' in html


# ── write_tree_html (integration) ─────────────────────────────────

def test_write_tree_html_creates_file(tmp_path):
    graph = {"nodes": []}
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(graph))
    out_path = tmp_path / "tree.html"
    
    result = write_tree_html(graph_path, out_path)
    assert result == out_path
    assert out_path.exists()
    assert "d3.v7" in out_path.read_text()


def test_write_tree_html_with_options(tmp_path):
    nodes = [
        {"id": "n1", "label": "func", "source_file": "src/mod.py", "file_type": "code"},
    ]
    graph = {"nodes": nodes}
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(graph))
    out_path = tmp_path / "tree.html"
    
    write_tree_html(graph_path, out_path, root="src", project_label="MyProj", max_children=100)
    content = out_path.read_text()
    assert "MyProj" in content


def test_write_tree_html_creates_parent_dir(tmp_path):
    graph = {"nodes": []}
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(graph))
    out_path = tmp_path / "deep" / "nested" / "tree.html"
    
    write_tree_html(graph_path, out_path)
    assert out_path.exists()
