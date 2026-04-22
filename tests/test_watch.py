"""Tests for watch.py - file watcher helpers (no watchdog required)."""
import time
from pathlib import Path
from unittest.mock import patch
import pytest

from graphify.watch import _notify_only, _WATCHED_EXTENSIONS, check_update


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

# --- check_update ---

def test_check_update_no_flag_returns_true(tmp_path):
    """When needs_update flag does not exist, check_update returns True without calling _rebuild_code."""
    with patch("graphify.watch._rebuild_code") as mock_rebuild:
        result = check_update(tmp_path)
    assert result is True
    mock_rebuild.assert_not_called()


def test_check_update_with_flag_calls_rebuild(tmp_path):
    """When needs_update flag exists, check_update calls _rebuild_code and returns its result."""
    flag = tmp_path / "graphify-out" / "needs_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1")

    with patch("graphify.watch._rebuild_code", return_value=True) as mock_rebuild:
        result = check_update(tmp_path)

    assert result is True
    mock_rebuild.assert_called_once_with(tmp_path)


def test_check_update_with_flag_returns_false_on_rebuild_failure(tmp_path):
    """When needs_update flag exists and _rebuild_code fails, check_update returns False."""
    flag = tmp_path / "graphify-out" / "needs_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1")

    with patch("graphify.watch._rebuild_code", return_value=False) as mock_rebuild:
        result = check_update(tmp_path)

    assert result is False
    mock_rebuild.assert_called_once_with(tmp_path)
