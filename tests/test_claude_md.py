"""Tests for graphify claude install / uninstall commands."""
import json
import subprocess
import sys
from graphify.__main__ import claude_install, claude_uninstall, _CLAUDE_MD_MARKER


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
    assert "graphify query" in content
    assert "Use grep/find/ls/read only after graphify" in content
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
    """Running install twice refreshes the section without duplicating it."""
    claude_install(tmp_path)
    claude_install(tmp_path)
    content = (tmp_path / "CLAUDE.md").read_text()
    assert content.count(_CLAUDE_MD_MARKER) == 1
    captured = capsys.readouterr()
    assert "refreshed" in captured.out


def test_install_idempotent_message(tmp_path, capsys):
    """Second install prints the refresh message."""
    claude_install(tmp_path)
    capsys.readouterr()  # clear first call output
    claude_install(tmp_path)
    out = capsys.readouterr().out
    assert "refreshed" in out


def test_install_refreshes_existing_graphify_section(tmp_path):
    """Existing stale graphify section is replaced while other content stays intact."""
    target = tmp_path / "CLAUDE.md"
    target.write_text(
        "# Project rules\n\n"
        "Keep this.\n\n"
        "## graphify\n\n"
        "Old graphify text.\n\n"
        "## Other\n\n"
        "Keep this too.\n"
    )

    claude_install(tmp_path)

    content = target.read_text()
    assert "Old graphify text" not in content
    assert "Keep this." in content
    assert "## Other" in content
    assert "Use grep/find/ls/read only after graphify" in content


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
    """claude_install writes UserPromptSubmit reminder and PreToolUse guard."""
    claude_install(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    guard_path = tmp_path / ".claude" / "hooks" / "graphify-guard.py"
    assert settings_path.exists()
    assert guard_path.exists()
    settings = json.loads(settings_path.read_text())
    hooks = settings.get("hooks", {})
    assert any("graphify" in str(h) for h in hooks.get("UserPromptSubmit", []))
    assert any(h.get("matcher") == "Bash|Grep|Glob|Read|LS" for h in hooks.get("PreToolUse", []))


def test_install_settings_json_idempotent(tmp_path):
    """Running claude_install twice does not duplicate graphify hooks."""
    claude_install(tmp_path)
    claude_install(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text())
    hooks = settings.get("hooks", {})
    prompt_hooks = [h for h in hooks.get("UserPromptSubmit", []) if "graphify" in str(h)]
    guard_hooks = [h for h in hooks.get("PreToolUse", []) if "graphify" in str(h)]
    assert len(prompt_hooks) == 1
    assert len(guard_hooks) == 1


def test_install_preserves_unrelated_settings_hooks(tmp_path):
    """Installing graphify keeps non-graphify Claude hooks in place."""
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "echo keep me"}],
                },
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "echo old graphify hook"}],
                },
            ]
        }
    }))

    claude_install(tmp_path)

    settings = json.loads(settings_path.read_text())
    pre_tool = settings["hooks"]["PreToolUse"]
    assert any("keep me" in str(h) for h in pre_tool)
    assert not any("old graphify hook" in str(h) for h in pre_tool)
    assert any("graphify-guard.py" in str(h) for h in pre_tool)


def test_uninstall_removes_settings_hook(tmp_path):
    """claude_uninstall removes graphify hooks and guard script."""
    claude_install(tmp_path)
    claude_uninstall(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    guard_path = tmp_path / ".claude" / "hooks" / "graphify-guard.py"
    assert not guard_path.exists()
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {})
        assert "graphify" not in str(hooks.get("UserPromptSubmit", []))
        assert "graphify" not in str(hooks.get("PreToolUse", []))


def test_guard_blocks_raw_search_until_graph_used(tmp_path):
    """The generated guard blocks raw search before graphify is used."""
    claude_install(tmp_path)
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text('{"nodes":[],"edges":[]}')
    guard_path = tmp_path / ".claude" / "hooks" / "graphify-guard.py"

    blocked = subprocess.run(
        [sys.executable, str(guard_path)],
        input=json.dumps({
            "session_id": "blocked",
            "tool_name": "Bash",
            "tool_input": {"command": 'grep -r "xml" verframe/src'},
        }),
        text=True,
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    assert blocked.returncode == 2
    assert "raw file search/read/list blocked" in blocked.stderr


def test_guard_allows_raw_search_after_graph_used(tmp_path):
    """After graphify query is used in a session, targeted raw reads are allowed."""
    claude_install(tmp_path)
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text('{"nodes":[],"edges":[]}')
    guard_path = tmp_path / ".claude" / "hooks" / "graphify-guard.py"

    graph_use = subprocess.run(
        [sys.executable, str(guard_path)],
        input=json.dumps({
            "session_id": "allowed",
            "tool_name": "Bash",
            "tool_input": {"command": 'graphify query "xml export" --budget 4000'},
        }),
        text=True,
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    assert graph_use.returncode == 0

    raw_search = subprocess.run(
        [sys.executable, str(guard_path)],
        input=json.dumps({
            "session_id": "allowed",
            "tool_name": "Bash",
            "tool_input": {"command": 'grep -r "xml" verframe/src'},
        }),
        text=True,
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    assert raw_search.returncode == 0


def test_guard_treats_windows_graph_report_read_as_graph_use(tmp_path):
    """Windows-style graph report paths count as graph usage."""
    claude_install(tmp_path)
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text('{"nodes":[],"edges":[]}')
    guard_path = tmp_path / ".claude" / "hooks" / "graphify-guard.py"

    graph_read = subprocess.run(
        [sys.executable, str(guard_path)],
        input=json.dumps({
            "session_id": "windows-report",
            "tool_name": "Read",
            "tool_input": {"file_path": "graphify-out\\GRAPH_REPORT.md"},
        }),
        text=True,
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    assert graph_read.returncode == 0

    raw_search = subprocess.run(
        [sys.executable, str(guard_path)],
        input=json.dumps({
            "session_id": "windows-report",
            "tool_name": "Bash",
            "tool_input": {"command": 'grep -r "xml" verframe/src'},
        }),
        text=True,
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    assert raw_search.returncode == 0


def test_guard_allows_windows_claude_hook_reads(tmp_path):
    """Windows-style .claude paths are internal guard reads, not raw exploration."""
    claude_install(tmp_path)
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text('{"nodes":[],"edges":[]}')
    guard_path = tmp_path / ".claude" / "hooks" / "graphify-guard.py"

    hook_read = subprocess.run(
        [sys.executable, str(guard_path)],
        input=json.dumps({
            "session_id": "windows-claude",
            "tool_name": "Read",
            "tool_input": {"file_path": ".claude\\hooks\\graphify-guard.py"},
        }),
        text=True,
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    assert hook_read.returncode == 0
