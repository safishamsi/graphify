"""Tests for the `graphify migrate-home` CLI command."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

GRAPHIFY_ROOT = Path(__file__).resolve().parent.parent


def _run_cli(args: list[str], cwd: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    """Invoke `python -m graphify <args>` with PYTHONPATH pointing at the repo."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(GRAPHIFY_ROOT)
    env.pop("GRAPHIFY_HOME", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "graphify", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_migrate_no_legacy_dir_is_noop(tmp_path):
    """Running migrate when there's no graphify-out/ prints a friendly message."""
    result = _run_cli(["migrate-home"], cwd=tmp_path)
    assert result.returncode == 0
    assert "nothing to migrate" in result.stdout.lower()


def test_migrate_renames_legacy_to_default(tmp_path):
    """graphify-out/ is renamed to .graphify/ when the new dir doesn't exist yet."""
    legacy = tmp_path / "graphify-out"
    legacy.mkdir()
    (legacy / "graph.json").write_text("{}", encoding="utf-8")
    (legacy / "cache").mkdir()
    (legacy / "cache" / "abc.json").write_text("{}", encoding="utf-8")

    result = _run_cli(["migrate-home"], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert not legacy.exists()
    new_home = tmp_path / ".graphify"
    assert (new_home / "graph.json").is_file()
    assert (new_home / "cache" / "abc.json").is_file()


def test_migrate_dry_run_does_not_move(tmp_path):
    """--dry-run announces the rename but leaves the filesystem untouched."""
    legacy = tmp_path / "graphify-out"
    legacy.mkdir()
    (legacy / "graph.json").write_text("{}", encoding="utf-8")

    result = _run_cli(["migrate-home", "--dry-run"], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "[dry-run]" in result.stdout
    assert legacy.exists()
    assert not (tmp_path / ".graphify").exists()


def test_migrate_refuses_when_target_exists(tmp_path):
    """Without --force we refuse to clobber an existing .graphify/."""
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / ".graphify").mkdir()

    result = _run_cli(["migrate-home"], cwd=tmp_path)
    assert result.returncode == 2
    assert "refusing to overwrite" in result.stderr.lower()


def test_migrate_force_merges(tmp_path):
    """--force merges legacy into target without overwriting target files."""
    legacy = tmp_path / "graphify-out"
    new = tmp_path / ".graphify"
    legacy.mkdir()
    new.mkdir()
    (legacy / "old-only.txt").write_text("old", encoding="utf-8")
    (legacy / "shared.txt").write_text("legacy version", encoding="utf-8")
    (new / "shared.txt").write_text("new version", encoding="utf-8")
    (new / "new-only.txt").write_text("new", encoding="utf-8")

    result = _run_cli(["migrate-home", "--force"], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert not legacy.exists()
    assert (new / "old-only.txt").read_text(encoding="utf-8") == "old"
    assert (new / "new-only.txt").read_text(encoding="utf-8") == "new"
    # Conflict resolution: target wins.
    assert (new / "shared.txt").read_text(encoding="utf-8") == "new version"


def test_migrate_respects_env_target(tmp_path):
    """If GRAPHIFY_HOME points elsewhere, migrate moves into that name."""
    legacy = tmp_path / "graphify-out"
    legacy.mkdir()
    (legacy / "graph.json").write_text("{}", encoding="utf-8")

    result = _run_cli(
        ["migrate-home"],
        cwd=tmp_path,
        env_extra={"GRAPHIFY_HOME": "build-graph"},
    )
    assert result.returncode == 0, result.stderr
    assert not legacy.exists()
    assert (tmp_path / "build-graph" / "graph.json").is_file()
    # Default name should NOT be created when env is set.
    assert not (tmp_path / ".graphify").exists()
