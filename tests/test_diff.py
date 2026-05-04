"""Tests for the `graphify diff` CLI command."""
import json
import sys
import pytest
from pathlib import Path
from unittest.mock import patch

try:
    import networkx  # noqa: F401
    _HAS_NETWORKX = True
except ImportError:
    _HAS_NETWORKX = False

requires_networkx = pytest.mark.skipif(not _HAS_NETWORKX, reason="networkx not installed")


def _run_main(argv):
    """Run graphify.__main__.main() with the given argv, capture stdout."""
    import io
    from graphify.__main__ import main
    buf = io.StringIO()
    exit_code = 0
    with patch("sys.argv", argv), patch("sys.stdout", buf):
        try:
            main()
        except SystemExit as e:
            exit_code = e.code or 0
    return buf.getvalue(), exit_code


def _make_graph_json(tmp_path, name, nodes, edges):
    data = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [{"id": n, "label": n} for n in nodes],
        "links": [
            {"source": s, "target": t, "relation": r, "confidence": "EXTRACTED", "weight": 1.0}
            for s, t, r in edges
        ],
    }
    p = tmp_path / name
    p.write_text(json.dumps(data))
    return p


@requires_networkx
def test_diff_no_changes(tmp_path):
    """diff of identical graphs reports 'no changes'."""
    nodes = ["alpha", "beta"]
    edges = [("alpha", "beta", "calls")]
    old = _make_graph_json(tmp_path, "old.json", nodes, edges)
    new = _make_graph_json(tmp_path, "new.json", nodes, edges)
    out, code = _run_main(["graphify", "diff", str(old), str(new)])
    assert code == 0
    assert "no changes" in out


@requires_networkx
def test_diff_new_node(tmp_path):
    """diff detects a newly added node."""
    old = _make_graph_json(tmp_path, "old.json", ["alpha"], [])
    new = _make_graph_json(tmp_path, "new.json", ["alpha", "gamma"], [])
    out, code = _run_main(["graphify", "diff", str(old), str(new)])
    assert code == 0
    assert "gamma" in out
    assert "New nodes" in out


@requires_networkx
def test_diff_removed_node(tmp_path):
    """diff detects a removed node."""
    old = _make_graph_json(tmp_path, "old.json", ["alpha", "beta"], [])
    new = _make_graph_json(tmp_path, "new.json", ["alpha"], [])
    out, code = _run_main(["graphify", "diff", str(old), str(new)])
    assert code == 0
    assert "beta" in out
    assert "Removed nodes" in out


@requires_networkx
def test_diff_new_edge(tmp_path):
    """diff detects a new edge."""
    old = _make_graph_json(tmp_path, "old.json", ["a", "b"], [])
    new = _make_graph_json(tmp_path, "new.json", ["a", "b"], [("a", "b", "imports")])
    out, code = _run_main(["graphify", "diff", str(old), str(new)])
    assert code == 0
    assert "New edges" in out
    assert "imports" in out


def test_diff_missing_file(tmp_path):
    """diff exits with error when a file does not exist."""
    old = _make_graph_json(tmp_path, "old.json", ["a"], [])
    with pytest.raises(SystemExit) as exc:
        with patch("sys.argv", ["graphify", "diff", str(old), str(tmp_path / "missing.json")]):
            from graphify.__main__ import main
            main()
    assert exc.value.code != 0


def test_diff_missing_args(tmp_path):
    """diff with fewer than 2 positional args exits with error."""
    with pytest.raises(SystemExit) as exc:
        with patch("sys.argv", ["graphify", "diff", str(tmp_path / "only_one.json")]):
            from graphify.__main__ import main
            main()
    assert exc.value.code != 0
