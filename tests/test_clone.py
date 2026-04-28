"""Tests for graphify/__main__._clone_repo argument hardening.

The clone path historically passed user-supplied `--branch <branch>` and
`<git_url>` straight to `git` without a `--` separator, and without rejecting
branch names that look like CLI flags. That made the surface a candidate for
argument injection (e.g. `--upload-pack=evilcmd`).

These tests assert the hardened behaviour:
  * `branch` starting with `-` is rejected before any git invocation.
  * The constructed argv contains a `--` separator before positional refs.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from graphify.__main__ import _clone_repo


def test_clone_rejects_branch_starting_with_dash(tmp_path, monkeypatch, capsys):
    """A branch name like `--upload-pack=evilcmd` must be rejected before
    any subprocess.run is called."""
    called: list[list[str]] = []

    def fake_run(*args, **kwargs):
        called.append(list(args[0]) if args else [])
        raise AssertionError("subprocess.run must not run when branch is rejected")

    monkeypatch.setattr("subprocess.run", fake_run)

    out = tmp_path / "dest"
    with pytest.raises(SystemExit):
        _clone_repo(
            "https://github.com/example/repo",
            branch="--upload-pack=evilcmd",
            out_dir=out,
        )
    err = capsys.readouterr().err
    assert "refusing branch name" in err
    assert called == []


def test_clone_argv_uses_double_dash_separator(tmp_path, monkeypatch):
    """Verify the constructed argv places `--` before positional URL/dest so
    a future url-like flag cannot be reinterpreted as a git option."""
    captured: list[list[str]] = []

    class _Result:
        returncode = 0
        stderr = ""

    def fake_run(cmd, *_args, **_kwargs):
        captured.append(list(cmd))
        return _Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    out = tmp_path / "dest"
    _clone_repo("https://github.com/example/repo", branch="main", out_dir=out)

    assert captured, "expected a git invocation"
    cmd = captured[0]
    assert cmd[:4] == ["git", "clone", "--depth", "1"]
    assert "--branch" in cmd and "main" in cmd
    # Must contain a literal `--` before the URL/dest pair.
    assert "--" in cmd
    sep = cmd.index("--")
    assert cmd[sep + 1].endswith("repo.git")
    assert Path(cmd[sep + 2]) == out
