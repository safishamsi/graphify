"""Tests for graphify claude install / uninstall commands."""
from pathlib import Path
import pytest
from graphify.__main__ import claude_install, claude_uninstall, _CLAUDE_MD_MARKER, _CLAUDE_MD_SECTION


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------

def test_install_creates_claude_md(tmp_path):
    """Creates CLAUDE.md when none exists."""
    claude_install(tmp_path)
    target = tmp_path / "CLAUDE.md"
    assert target.exists()
    assert _CLAUDE_MD_MARKER in target.read_text()


def test_install_contains_expected_rules(tmp_path):
    """Written section includes the three rules."""
    claude_install(tmp_path)
    content = (tmp_path / "CLAUDE.md").read_text()
    assert "GRAPH_REPORT.md" in content
    assert "wiki/index.md" in content
    assert "graphify update" in content


def test_install_appends_to_existing_claude_md(tmp_path):
    """Appends to an existing CLAUDE.md without clobbering it."""
    target = tmp_path / "CLAUDE.md"
    target.write_text("# Existing content\n\nSome rules here.\n")
    claude_install(tmp_path)
    content = target.read_text()
    assert "Existing content" in content
    assert _CLAUDE_MD_MARKER in content


def test_install_is_idempotent(tmp_path, capsys):
    """Running install twice does not duplicate the section."""
    claude_install(tmp_path)
    claude_install(tmp_path)
    content = (tmp_path / "CLAUDE.md").read_text()
    assert content.count(_CLAUDE_MD_MARKER) == 1
    captured = capsys.readouterr()
    assert "already configured" in captured.out


def test_install_idempotent_message(tmp_path, capsys):
    """Second install prints the 'already configured' message."""
    claude_install(tmp_path)
    capsys.readouterr()  # clear first call output
    claude_install(tmp_path)
    out = capsys.readouterr().out
    assert "already configured" in out


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------

def test_uninstall_removes_section(tmp_path):
    """Removes the graphify section after it was installed."""
    claude_install(tmp_path)
    claude_uninstall(tmp_path)
    target = tmp_path / "CLAUDE.md"
    # File may or may not exist depending on whether it was empty
    if target.exists():
        assert _CLAUDE_MD_MARKER not in target.read_text()


def test_uninstall_preserves_other_content(tmp_path):
    """Uninstall keeps pre-existing content outside the graphify section."""
    target = tmp_path / "CLAUDE.md"
    target.write_text("# My Project\n\nSome rules.\n")
    claude_install(tmp_path)
    claude_uninstall(tmp_path)
    assert target.exists()
    content = target.read_text()
    assert "My Project" in content
    assert "Some rules" in content
    assert _CLAUDE_MD_MARKER not in content


def test_uninstall_no_op_when_not_installed(tmp_path, capsys):
    """Uninstall on a CLAUDE.md without graphify section prints a message and exits cleanly."""
    target = tmp_path / "CLAUDE.md"
    target.write_text("# Other stuff\n")
    claude_uninstall(tmp_path)
    out = capsys.readouterr().out
    assert "not found" in out or "nothing to do" in out


def test_uninstall_no_op_when_no_file(tmp_path, capsys):
    """Uninstall when no CLAUDE.md exists prints a message and exits cleanly."""
    claude_uninstall(tmp_path)
    out = capsys.readouterr().out
    assert "No CLAUDE.md" in out or "nothing to do" in out


# ---------------------------------------------------------------------------
# settings.json PreToolUse hook
# ---------------------------------------------------------------------------

def test_install_creates_settings_json(tmp_path):
    """claude_install also writes .claude/settings.json with PreToolUse hook."""
    import json
    claude_install(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.exists()
    settings = json.loads(settings_path.read_text())
    hooks = settings.get("hooks", {}).get("PreToolUse", [])
    assert any("Glob|Grep" in h.get("matcher", "") for h in hooks)


def test_install_settings_json_idempotent(tmp_path):
    """Running claude_install twice does not duplicate the PreToolUse hook."""
    import json
    claude_install(tmp_path)
    claude_install(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text())
    hooks = settings.get("hooks", {}).get("PreToolUse", [])
    glob_grep_hooks = [h for h in hooks if "Glob|Grep" in h.get("matcher", "")]
    assert len(glob_grep_hooks) == 1


def test_uninstall_removes_settings_hook(tmp_path):
    """claude_uninstall removes the PreToolUse hook from settings.json."""
    import json
    claude_install(tmp_path)
    claude_uninstall(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {}).get("PreToolUse", [])
        assert not any("Glob|Grep" in h.get("matcher", "") for h in hooks)
