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


def test_install_default_omits_wiki_rebuild(tmp_path):
    """Without --with-wiki, the post-commit hook must not import or call to_wiki (#549)."""
    repo = _make_git_repo(tmp_path)
    install(repo)
    hook_text = (repo / ".git" / "hooks" / "post-commit").read_text(encoding="utf-8")
    assert "from graphify.wiki import to_wiki" not in hook_text
    assert "Wiki rebuilt" not in hook_text


def test_install_with_wiki_injects_wiki_rebuild(tmp_path):
    """With with_wiki=True, the post-commit hook contains the wiki rebuild block (#549)."""
    repo = _make_git_repo(tmp_path)
    install(repo, with_wiki=True)
    hook_text = (repo / ".git" / "hooks" / "post-commit").read_text(encoding="utf-8")
    assert "from graphify.wiki import to_wiki" in hook_text
    assert "Wiki rebuilt" in hook_text
    # The hook should still rebuild the AST graph first - wiki is additive
    assert "from graphify.watch import _rebuild_code" in hook_text
    # And the install header should record the flag for later debugging
    assert "--with-wiki" in hook_text


def test_install_with_wiki_then_uninstall_clean(tmp_path):
    """A --with-wiki install followed by uninstall must leave no graphify section behind."""
    repo = _make_git_repo(tmp_path)
    install(repo, with_wiki=True)
    uninstall(repo)
    hook = repo / ".git" / "hooks" / "post-commit"
    if hook.exists():
        text = hook.read_text(encoding="utf-8")
        assert _HOOK_MARKER not in text
        assert "from graphify.wiki import to_wiki" not in text


def test_build_hook_script_wiki_block_only_when_requested():
    """_build_hook_script(with_wiki=False) must produce identical script to legacy _HOOK_SCRIPT."""
    from graphify.hooks import _build_hook_script, _HOOK_SCRIPT
    assert _build_hook_script(with_wiki=False) == _HOOK_SCRIPT
    # And with_wiki=True must be a strict superset (wiki block added)
    with_wiki = _build_hook_script(with_wiki=True)
    assert len(with_wiki) > len(_HOOK_SCRIPT)
    assert "to_wiki" in with_wiki and "to_wiki" not in _HOOK_SCRIPT
