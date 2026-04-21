"""Tests for watch.py - file watcher helpers (no watchdog required)."""
import json
import time
from pathlib import Path
import pytest

from graphify.watch import _notify_only, _rebuild_code, _WATCHED_EXTENSIONS


# --- _notify_only ---

def test_notify_only_creates_flag(tmp_path):
    _notify_only(tmp_path)
    flag = tmp_path / "graphify-out" / "needs_update"
    assert flag.exists()
    assert flag.read_text() == "1"

def test_notify_only_creates_flag_dir(tmp_path):
    # graphify-out dir does not exist yet
    assert not (tmp_path / "graphify-out").exists()
    _notify_only(tmp_path)
    assert (tmp_path / "graphify-out").is_dir()

def test_notify_only_idempotent(tmp_path):
    _notify_only(tmp_path)
    _notify_only(tmp_path)
    flag = tmp_path / "graphify-out" / "needs_update"
    assert flag.read_text() == "1"


# --- _WATCHED_EXTENSIONS ---

def test_watched_extensions_includes_code():
    assert ".py" in _WATCHED_EXTENSIONS
    assert ".ts" in _WATCHED_EXTENSIONS
    assert ".go" in _WATCHED_EXTENSIONS
    assert ".rs" in _WATCHED_EXTENSIONS

def test_watched_extensions_includes_docs():
    assert ".md" in _WATCHED_EXTENSIONS
    assert ".txt" in _WATCHED_EXTENSIONS
    assert ".pdf" in _WATCHED_EXTENSIONS

def test_watched_extensions_includes_images():
    assert ".png" in _WATCHED_EXTENSIONS
    assert ".jpg" in _WATCHED_EXTENSIONS

def test_watched_extensions_excludes_noise():
    assert ".json" not in _WATCHED_EXTENSIONS
    assert ".pyc" not in _WATCHED_EXTENSIONS
    assert ".log" not in _WATCHED_EXTENSIONS


# --- watch() import error without watchdog ---

def test_watch_raises_without_watchdog(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "watchdog.observers" or name == "watchdog.events":
            raise ImportError("mocked missing watchdog")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    from graphify.watch import watch
    with pytest.raises(ImportError, match="watchdog not installed"):
        watch(tmp_path)


def test_rebuild_code_preserves_non_code_cross_edges(tmp_path):
    code_file = tmp_path / "a.py"
    code_file.write_text("def f():\n    return 1\n", encoding="utf-8")

    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "graph.json").write_text(json.dumps({
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {"id": "legacy_code", "label": "a.py", "file_type": "code", "source_file": str(code_file)},
            {"id": "a_f", "label": "f()", "file_type": "code", "source_file": str(code_file)},
            {"id": "doc1", "label": "Design Doc", "file_type": "document", "source_file": "docs/design.md"},
        ],
        "links": [
            {
                "source": "doc1",
                "target": "a_f",
                "relation": "references",
                "confidence": "EXTRACTED",
                "source_file": "docs/design.md",
            }
        ],
    }), encoding="utf-8")

    assert _rebuild_code(tmp_path) is True

    graph = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    links = graph.get("links", graph.get("edges", []))
    assert any(node["id"] == "doc1" for node in graph["nodes"])
    assert any(
        edge.get("_src") == "doc1" and edge.get("_tgt") == "a_f"
        for edge in links
    )


def test_rebuild_code_report_keeps_full_detect_counts(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("# Notes\n\nConnected to the code graph.\n", encoding="utf-8")

    assert _rebuild_code(tmp_path) is True

    report = (tmp_path / "graphify-out" / "GRAPH_REPORT.md").read_text(encoding="utf-8")
    assert "2 files" in report
