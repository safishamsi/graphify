"""Tests for hooks.py - git hook install/uninstall."""
import os
import subprocess
from pathlib import Path
import pytest
from graphify.hooks import install, uninstall, status, _HOOK_MARKER, _CHECKOUT_MARKER


def _make_git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    return tmp_path


def test_install_creates_hook(tmp_path):
    repo = _make_git_repo(tmp_path)
    result = install(repo)
    hook = repo / ".git" / "hooks" / "post-commit"
    assert hook.exists()
    assert _HOOK_MARKER in hook.read_text()
    assert "installed" in result


def test_install_is_executable(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    hook = repo / ".git" / "hooks" / "post-commit"
    if os.name == "nt":
        assert hook.read_text(encoding="utf-8").startswith("#!/bin/sh\n")
    else:
        assert hook.stat().st_mode & 0o111  # executable bit set


def test_install_idempotent(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    result = install(repo)
    assert "already installed" in result
    # marker appears only once
    hook = repo / ".git" / "hooks" / "post-commit"
    assert hook.read_text().count(_HOOK_MARKER) == 1


def test_install_appends_to_existing_hook(tmp_path):
    repo = _make_git_repo(tmp_path)
    hook = repo / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/bash\necho existing\n")
    hook.chmod(0o755)
    install(repo)
    content = hook.read_text()
    assert "existing" in content
    assert _HOOK_MARKER in content


def test_uninstall_removes_hook(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    result = uninstall(repo)
    hook = repo / ".git" / "hooks" / "post-commit"
    assert not hook.exists()
    assert "removed" in result.lower()


def test_uninstall_no_hook(tmp_path):
    repo = _make_git_repo(tmp_path)
    result = uninstall(repo)
    assert "nothing to remove" in result


def test_status_installed(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    result = status(repo)
    assert "installed" in result


def test_status_not_installed(tmp_path):
    repo = _make_git_repo(tmp_path)
    result = status(repo)
    assert "not installed" in result


def test_no_git_repo_raises(tmp_path):
    with pytest.raises(RuntimeError, match="No git repository"):
        install(tmp_path / "not_a_repo")


def test_install_creates_post_checkout_hook(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    hook = repo / ".git" / "hooks" / "post-checkout"
    assert hook.exists()
    assert _CHECKOUT_MARKER in hook.read_text()


def test_install_post_checkout_is_executable(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    hook = repo / ".git" / "hooks" / "post-checkout"
    if os.name == "nt":
        assert hook.read_text(encoding="utf-8").startswith("#!/bin/sh\n")
    else:
        assert hook.stat().st_mode & 0o111


def test_uninstall_removes_post_checkout_hook(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    uninstall(repo)
    hook = repo / ".git" / "hooks" / "post-checkout"
    assert not hook.exists()


def test_status_shows_both_hooks(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    result = status(repo)
    assert "post-commit" in result
    assert "post-checkout" in result
    assert result.count("installed") >= 2


def test_hook_skips_head_on_exe():
    """Hook script must skip shebang extraction for .exe binaries (Windows)."""
    from graphify.hooks import _PYTHON_DETECT
    assert "*.exe) _SHEBANG=" in _PYTHON_DETECT or '*.exe)' in _PYTHON_DETECT


def test_hook_check_no_additionalContext(tmp_path):
    """graphify hook-check must not emit additionalContext — Codex Desktop rejects it."""
    import sys
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "graph.json").write_text("{}", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "graphify", "hook-check"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


# --- Coverage targets: lines 160-177, 208, 218-219, 240, 253 ---

def test_hooks_dir_custom_hooks_path(tmp_path):
    """Custom core.hooksPath in git config should be respected."""
    repo = _make_git_repo(tmp_path)
    custom_dir = tmp_path / "custom_hooks"
    # Set custom hooksPath in git config
    subprocess.run(
        ["git", "config", "core.hooksPath", str(custom_dir.relative_to(repo))],
        cwd=repo, check=True, capture_output=True,
    )
    from graphify.hooks import _hooks_dir
    result = _hooks_dir(repo)
    assert custom_dir.exists()
    assert result == custom_dir


def test_hooks_dir_custom_hooks_path_absolute(tmp_path):
    """Absolute custom hooksPath should be respected."""
    repo = _make_git_repo(tmp_path)
    custom_dir = tmp_path / "abs_hooks"
    subprocess.run(
        ["git", "config", "core.hooksPath", str(custom_dir)],
        cwd=repo, check=True, capture_output=True,
    )
    from graphify.hooks import _hooks_dir
    result = _hooks_dir(repo)
    assert custom_dir.exists()
    assert result == custom_dir


def test_hooks_dir_custom_path_outside_repo_falls_back(tmp_path):
    """Custom hooksPath that escapes repo root should fall back to .git/hooks."""
    repo = _make_git_repo(tmp_path)
    # Set hooksPath to something outside the repo
    subprocess.run(
        ["git", "config", "core.hooksPath", "../outside"],
        cwd=repo, check=True, capture_output=True,
    )
    from graphify.hooks import _hooks_dir
    result = _hooks_dir(repo)
    expected = repo / ".git" / "hooks"
    assert result == expected


def test_hooks_dir_config_error_falls_back(tmp_path, capsys):
    """Corrupt git config should fall back and print warning to stderr."""
    repo = _make_git_repo(tmp_path)
    # Corrupt the git config
    (repo / ".git" / "config").write_text("this is not valid ini[[[")
    from graphify.hooks import _hooks_dir
    result = _hooks_dir(repo)
    expected = repo / ".git" / "hooks"
    assert result == expected
    captured = capsys.readouterr()
    assert "could not read core.hooksPath" in captured.err


def test_uninstall_hook_not_present(tmp_path):
    """_uninstall_hook returns appropriate message when marker not in content."""
    repo = _make_git_repo(tmp_path)
    hook = repo / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\necho other hook\n")
    from graphify.hooks import _uninstall_hook, _HOOK_MARKER, _HOOK_MARKER_END
    msg = _uninstall_hook(repo / ".git" / "hooks", "post-commit", _HOOK_MARKER, _HOOK_MARKER_END)
    assert "not found" in msg.lower()


def test_uninstall_hook_preserves_other_content(tmp_path):
    """_uninstall_hook should preserve non-graphify hook content."""
    repo = _make_git_repo(tmp_path)
    hook = repo / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\necho existing\n\n" + "# graphify-hook-start\n...\n# graphify-hook-end\n")
    from graphify.hooks import _uninstall_hook, _HOOK_MARKER, _HOOK_MARKER_END
    msg = _uninstall_hook(repo / ".git" / "hooks", "post-commit", _HOOK_MARKER, _HOOK_MARKER_END)
    content = hook.read_text()
    assert "echo existing" in content
    assert _HOOK_MARKER not in content
    assert "other hook content preserved" in msg


def test_uninstall_no_git_repo_raises(tmp_path):
    """uninstall() should raise RuntimeError when not in a git repo."""
    from graphify.hooks import uninstall
    with pytest.raises(RuntimeError, match="No git repository"):
        uninstall(tmp_path / "not_a_repo")


def test_status_no_git_repo(tmp_path):
    """status() returns 'Not in a git repository.' when not in a git repo."""
    from graphify.hooks import status
    result = status(tmp_path / "not_a_repo")
    assert result == "Not in a git repository."
