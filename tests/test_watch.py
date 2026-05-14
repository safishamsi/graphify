"""Tests for watch.py - file watcher helpers (no watchdog required)."""
import time
from pathlib import Path
import pytest

from graphify.watch import _notify_only, _WATCHED_EXTENSIONS


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

def test_check_update_no_flag_returns_true(tmp_path):
    """check_update returns True and is silent when needs_update flag is absent."""
    from graphify.watch import check_update
    assert check_update(tmp_path) is True


def test_check_update_with_flag_returns_true_and_prints(tmp_path, capsys):
    """check_update returns True and prints notification when flag exists."""
    from graphify.watch import check_update
    flag = tmp_path / "graphify-out" / "needs_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1")
    result = check_update(tmp_path)
    assert result is True
    out = capsys.readouterr().out
    assert "graphify --update" in out


def test_check_update_does_not_clear_flag(tmp_path):
    """check_update never removes the needs_update flag (clearing is LLM's job)."""
    from graphify.watch import check_update
    flag = tmp_path / "graphify-out" / "needs_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1")
    check_update(tmp_path)
    assert flag.exists()


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


def test_rebuild_code_is_idempotent_when_cluster_ids_flap(tmp_path, monkeypatch):
    from graphify import cluster as cluster_mod
    from graphify.watch import _rebuild_code

    src = tmp_path / "app.py"
    src.write_text("def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n", encoding="utf-8")

    calls = {"n": 0}

    def flaky_cluster(G):
        calls["n"] += 1
        nodes = sorted(G.nodes())
        if calls["n"] % 2 == 1:
            return {100: nodes}
        return {7: nodes}

    monkeypatch.setattr(cluster_mod, "cluster", flaky_cluster)
    monkeypatch.setattr(cluster_mod, "score_all", lambda _G, comm: {cid: 1.0 for cid in comm})

    assert _rebuild_code(tmp_path)
    graph_path = tmp_path / "graphify-out" / "graph.json"
    report_path = tmp_path / "graphify-out" / "GRAPH_REPORT.md"
    first_graph = graph_path.read_text(encoding="utf-8")
    first_report = report_path.read_text(encoding="utf-8")

    assert _rebuild_code(tmp_path)
    second_graph = graph_path.read_text(encoding="utf-8")
    second_report = report_path.read_text(encoding="utf-8")

    assert first_graph == second_graph
    assert first_report == second_report


def test_rebuild_code_skips_cluster_when_topology_unchanged(tmp_path, monkeypatch):
    from graphify import cluster as cluster_mod
    from graphify.watch import _rebuild_code

    src = tmp_path / "app.py"
    src.write_text("def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n", encoding="utf-8")

    calls = {"n": 0}

    def cluster_once(G):
        calls["n"] += 1
        if calls["n"] > 1:
            raise AssertionError("cluster() should be skipped when topology is unchanged")
        return {0: sorted(G.nodes())}

    monkeypatch.setattr(cluster_mod, "cluster", cluster_once)
    monkeypatch.setattr(cluster_mod, "score_all", lambda _G, comm: {cid: 1.0 for cid in comm})

    assert _rebuild_code(tmp_path)
    assert _rebuild_code(tmp_path)
    assert calls["n"] == 1
