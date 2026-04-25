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


# --- _viz_skip_reason ---

def test_viz_skip_reason_default_off(monkeypatch):
    """No env vars set: never skip, regardless of node count."""
    from graphify.watch import _viz_skip_reason
    monkeypatch.delenv("GRAPHIFY_NO_VIZ", raising=False)
    monkeypatch.delenv("GRAPHIFY_VIZ_NODE_LIMIT", raising=False)
    assert _viz_skip_reason(10) is None
    assert _viz_skip_reason(100_000) is None


def test_viz_skip_reason_no_viz_truthy(monkeypatch):
    """GRAPHIFY_NO_VIZ=1 short-circuits regardless of node count."""
    from graphify.watch import _viz_skip_reason
    monkeypatch.setenv("GRAPHIFY_NO_VIZ", "1")
    monkeypatch.delenv("GRAPHIFY_VIZ_NODE_LIMIT", raising=False)
    reason = _viz_skip_reason(10)
    assert reason is not None and "GRAPHIFY_NO_VIZ" in reason


def test_viz_skip_reason_no_viz_falsy(monkeypatch):
    """GRAPHIFY_NO_VIZ=0 / false / no / empty: do not skip on this flag."""
    from graphify.watch import _viz_skip_reason
    monkeypatch.delenv("GRAPHIFY_VIZ_NODE_LIMIT", raising=False)
    for value in ("0", "false", "FALSE", "no", "", "  "):
        monkeypatch.setenv("GRAPHIFY_NO_VIZ", value)
        assert _viz_skip_reason(10) is None, f"value {value!r} should not trigger skip"


def test_viz_skip_reason_node_limit_exceeded(monkeypatch):
    """GRAPHIFY_VIZ_NODE_LIMIT=5000: skip when node count exceeds limit."""
    from graphify.watch import _viz_skip_reason
    monkeypatch.delenv("GRAPHIFY_NO_VIZ", raising=False)
    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "5000")
    assert _viz_skip_reason(4999) is None
    assert _viz_skip_reason(5000) is None
    reason = _viz_skip_reason(5001)
    assert reason is not None and "5000" in reason and "5001" in reason


def test_viz_skip_reason_node_limit_invalid(monkeypatch):
    """GRAPHIFY_VIZ_NODE_LIMIT=abc: silently treated as unset rather than crashing."""
    from graphify.watch import _viz_skip_reason
    monkeypatch.delenv("GRAPHIFY_NO_VIZ", raising=False)
    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "not-a-number")
    assert _viz_skip_reason(10) is None


def test_viz_skip_reason_no_viz_takes_priority(monkeypatch):
    """When both vars are set, GRAPHIFY_NO_VIZ wins."""
    from graphify.watch import _viz_skip_reason
    monkeypatch.setenv("GRAPHIFY_NO_VIZ", "1")
    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "100")
    reason = _viz_skip_reason(10)  # under the limit but no-viz wins
    assert reason is not None and "GRAPHIFY_NO_VIZ" in reason
