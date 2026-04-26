"""Tests for graphify/paths.py — configurable home directory."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from graphify import paths


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Ensure GRAPHIFY_HOME doesn't leak between tests."""
    monkeypatch.delenv(paths.ENV_HOME, raising=False)
    yield


def test_default_home_name_is_dotgraphify():
    """Fresh-install default is .graphify (no env var, no legacy dir)."""
    assert paths.home_name() == ".graphify"
    assert paths.DEFAULT_HOME_NAME == ".graphify"


def test_legacy_home_name_constant():
    """LEGACY_HOME_NAME exposes the old default for migration tooling."""
    assert paths.LEGACY_HOME_NAME == "graphify-out"


def test_env_override(monkeypatch):
    """GRAPHIFY_HOME env var fully overrides the default name."""
    monkeypatch.setenv(paths.ENV_HOME, "graphify-out")
    assert paths.home_name() == "graphify-out"

    monkeypatch.setenv(paths.ENV_HOME, ".my-graph")
    assert paths.home_name() == ".my-graph"


def test_blank_env_falls_back_to_default(monkeypatch):
    """Empty/whitespace-only env values are ignored (treated as unset)."""
    monkeypatch.setenv(paths.ENV_HOME, "")
    assert paths.home_name() == ".graphify"

    monkeypatch.setenv(paths.ENV_HOME, "   ")
    assert paths.home_name() == ".graphify"


def test_home_resolves_under_root(tmp_path):
    """home(root) returns an absolute path under the given root."""
    h = paths.home(tmp_path)
    assert h == (tmp_path / ".graphify").resolve()


def test_cache_dir_creates_and_resolves(tmp_path):
    """cache_dir() resolves to <home>/cache and creates it by default."""
    cd = paths.cache_dir(tmp_path)
    assert cd == (tmp_path / ".graphify" / "cache").resolve()
    assert cd.is_dir()


def test_cache_dir_no_create(tmp_path):
    """cache_dir(create=False) does NOT create the directory."""
    cd = paths.cache_dir(tmp_path, create=False)
    assert not cd.exists()


def test_subpath_helpers(tmp_path):
    """All sub-path helpers compose against the resolved home dir."""
    base = (tmp_path / ".graphify").resolve()
    assert paths.manifest_path(tmp_path) == base / "manifest.json"
    assert paths.memory_dir(tmp_path) == base / "memory"
    assert paths.converted_dir(tmp_path) == base / "converted"
    assert paths.graph_path(tmp_path) == base / "graph.json"
    assert paths.report_path(tmp_path) == base / "GRAPH_REPORT.md"
    assert paths.cost_path(tmp_path) == base / "cost.json"
    assert paths.needs_update_path(tmp_path) == base / "needs_update"


def test_subpath_helpers_follow_env(tmp_path, monkeypatch):
    """Changing GRAPHIFY_HOME at runtime changes every helper."""
    monkeypatch.setenv(paths.ENV_HOME, "build-graph")
    base = (tmp_path / "build-graph").resolve()
    assert paths.home(tmp_path) == base
    assert paths.cache_dir(tmp_path).parent == base
    assert paths.graph_path(tmp_path) == base / "graph.json"


def test_has_legacy_layout_true(tmp_path):
    """has_legacy_layout returns True when graphify-out exists and .graphify doesn't."""
    (tmp_path / "graphify-out").mkdir()
    assert paths.has_legacy_layout(tmp_path) is True


def test_has_legacy_layout_false_when_both_exist(tmp_path):
    """If both legacy and current dirs exist, no migration needed (or pending)."""
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / ".graphify").mkdir()
    assert paths.has_legacy_layout(tmp_path) is False


def test_has_legacy_layout_false_when_no_legacy(tmp_path):
    """No legacy dir → nothing to migrate."""
    assert paths.has_legacy_layout(tmp_path) is False


def test_has_legacy_layout_false_when_env_set(tmp_path, monkeypatch):
    """If user pinned GRAPHIFY_HOME explicitly, leave them alone."""
    (tmp_path / "graphify-out").mkdir()
    monkeypatch.setenv(paths.ENV_HOME, "graphify-out")
    assert paths.has_legacy_layout(tmp_path) is False


# ---------------------------------------------------------------------------
# auto_migrate — invoked at the start of every install entry point so an
# upgrading user's directory rename happens in lockstep with the CLAUDE.md /
# hook / skill-file rewrites those install commands trigger.
# ---------------------------------------------------------------------------


def test_auto_migrate_renames_legacy_dir(tmp_path):
    """Bare graphify-out/ next to no .graphify/ → renamed to .graphify/."""
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    assert paths.auto_migrate(tmp_path) is True
    assert not (tmp_path / "graphify-out").exists()
    assert (tmp_path / ".graphify" / "graph.json").is_file()


def test_auto_migrate_noop_no_legacy(tmp_path):
    """No legacy dir → nothing to do."""
    assert paths.auto_migrate(tmp_path) is False


def test_auto_migrate_noop_when_target_already_exists(tmp_path):
    """Both layouts present → conservative refusal; user runs migrate-home --force."""
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / ".graphify").mkdir()
    assert paths.auto_migrate(tmp_path) is False
    assert (tmp_path / "graphify-out").exists()
    assert (tmp_path / ".graphify").exists()


def test_auto_migrate_noop_when_env_set(tmp_path, monkeypatch):
    """User pinned GRAPHIFY_HOME → leave the existing layout untouched."""
    (tmp_path / "graphify-out").mkdir()
    monkeypatch.setenv(paths.ENV_HOME, "graphify-out")
    assert paths.auto_migrate(tmp_path) is False
    assert (tmp_path / "graphify-out").exists()
