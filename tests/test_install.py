"""Tests for graphify install --platform routing."""
import os
from pathlib import Path
import sys
from unittest.mock import patch
import pytest


PLATFORMS = {
    "claude": (".claude/skills/aag/SKILL.md",),
    "codex": (".agents/skills/aag/SKILL.md",),
    "opencode": (".config/opencode/skills/aag/SKILL.md",),
    "claw": (".openclaw/skills/aag/SKILL.md",),
    "droid": (".factory/skills/aag/SKILL.md",),
    "trae": (".trae/skills/aag/SKILL.md",),
    "trae-cn": (".trae-cn/skills/aag/SKILL.md",),
    "windows": (".claude/skills/aag/SKILL.md",),
}


def _install(tmp_path, platform):
    from graphify.__main__ import install
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        with patch("graphify.__main__.Path.home", return_value=tmp_path):
            install(platform=platform)
    finally:
        os.chdir(old_cwd)


def test_install_default_claude(tmp_path):
    _install(tmp_path, "claude")
    assert (tmp_path / ".claude" / "skills" / "aag" / "SKILL.md").exists()


def test_install_codex(tmp_path):
    _install(tmp_path, "codex")
    assert (tmp_path / ".agents" / "skills" / "aag" / "SKILL.md").exists()


def test_install_opencode(tmp_path):
    _install(tmp_path, "opencode")
    assert (tmp_path / ".config" / "opencode" / "skills" / "aag" / "SKILL.md").exists()


def test_install_positional_platform_opencode(tmp_path, monkeypatch):
    from graphify.__main__ import main
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["graphify", "install", "opencode"])
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        main()
    assert (tmp_path / ".config" / "opencode" / "skills" / "aag" / "SKILL.md").exists()
    assert not (tmp_path / ".claude" / "skills" / "aag" / "SKILL.md").exists()


def test_install_help_does_not_install_default(tmp_path, monkeypatch, capsys):
    from graphify.__main__ import main
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["graphify", "install", "opencode", "--help"])
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        main()
    out = capsys.readouterr().out
    assert "Usage: graphify install" in out
    assert "opencode" in out
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".config").exists()


def test_install_claw(tmp_path):
    _install(tmp_path, "claw")
    assert (tmp_path / ".openclaw" / "skills" / "aag" / "SKILL.md").exists()


def test_install_droid(tmp_path):
    _install(tmp_path, "droid")
    assert (tmp_path / ".factory" / "skills" / "aag" / "SKILL.md").exists()


def test_install_trae(tmp_path):
    _install(tmp_path, "trae")
    assert (tmp_path / ".trae" / "skills" / "aag" / "SKILL.md").exists()


def test_install_trae_cn(tmp_path):
    _install(tmp_path, "trae-cn")
    assert (tmp_path / ".trae-cn" / "skills" / "aag" / "SKILL.md").exists()


def test_install_windows(tmp_path):
    _install(tmp_path, "windows")
    assert (tmp_path / ".claude" / "skills" / "aag" / "SKILL.md").exists()


def test_install_unknown_platform_exits(tmp_path):
    with pytest.raises(SystemExit):
        _install(tmp_path, "unknown")


def test_codex_skill_contains_spawn_agent():
    """Codex skill file must reference spawn_agent (via build-codex.md)."""
    import graphify
    skill_dir = Path(graphify.__file__).parent
    main_skill = (skill_dir / "skill-codex.md").read_text()
    assert "build-codex.md" in main_skill
    build_skill = (skill_dir / "skills" / "build-codex.md").read_text()
    assert "spawn_agent" in build_skill


def test_opencode_skill_contains_mention():
    """OpenCode skill file must reference @mention (via build-opencode.md)."""
    import graphify
    skill_dir = Path(graphify.__file__).parent
    main_skill = (skill_dir / "skill-opencode.md").read_text()
    assert "build-opencode.md" in main_skill
    build_skill = (skill_dir / "skills" / "build-opencode.md").read_text()
    assert "@mention" in build_skill


def test_claw_skill_is_sequential():
    """OpenClaw skill file must describe sequential extraction (via build-claw.md)."""
    import graphify
    skill_dir = Path(graphify.__file__).parent
    main_skill = (skill_dir / "skill-claw.md").read_text()
    assert "build-claw.md" in main_skill
    build_skill = (skill_dir / "skills" / "build-claw.md").read_text()
    assert "sequential" in build_skill.lower()
    assert "spawn_agent" not in build_skill
    assert "@mention" not in build_skill


def test_all_skill_files_exist_in_package():
    """All installable platform skill files must be present in the installed package."""
    import graphify
    pkg = Path(graphify.__file__).parent
    for name in ("skill.md", "skill-codex.md", "skill-opencode.md", "skill-claw.md", "skill-windows.md", "skill-droid.md", "skill-trae.md"):
        assert (pkg / name).exists(), f"Missing: {name}"


def test_claude_install_registers_claude_md(tmp_path):
    """Claude platform install writes CLAUDE.md; others do not."""
    _install(tmp_path, "claude")
    assert (tmp_path / ".claude" / "CLAUDE.md").exists()


def test_codex_install_does_not_write_claude_md(tmp_path):
    _install(tmp_path, "codex")
    assert not (tmp_path / ".claude" / "CLAUDE.md").exists()


# --- always-on AGENTS.md install/uninstall tests ---

def _agents_install(tmp_path, platform):
    from graphify.__main__ import _agents_install as _install_fn
    _install_fn(tmp_path, platform)


def _agents_uninstall(tmp_path, platform=""):
    from graphify.__main__ import _agents_uninstall as _uninstall_fn
    _uninstall_fn(tmp_path, platform=platform)


def test_codex_agents_install_writes_agents_md(tmp_path):
    _agents_install(tmp_path, "codex")
    agents_md = tmp_path / "AGENTS.md"
    assert agents_md.exists()
    assert "graphify" in agents_md.read_text()
    assert "GRAPH_REPORT.md" in agents_md.read_text()


def test_opencode_agents_install_writes_agents_md(tmp_path):
    _agents_install(tmp_path, "opencode")
    assert (tmp_path / "AGENTS.md").exists()


def test_claw_agents_install_writes_agents_md(tmp_path):
    _agents_install(tmp_path, "claw")
    assert (tmp_path / "AGENTS.md").exists()


def test_agents_install_idempotent(tmp_path):
    """Installing twice does not duplicate the section."""
    _agents_install(tmp_path, "codex")
    _agents_install(tmp_path, "codex")
    content = (tmp_path / "AGENTS.md").read_text()
    assert content.count("## aag") == 1


def test_agents_install_appends_to_existing(tmp_path):
    """Installs into an existing AGENTS.md without overwriting other content."""
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# Existing rules\n\nDo not break things.\n")
    _agents_install(tmp_path, "codex")
    content = agents_md.read_text()
    assert "Do not break things." in content
    assert "## aag" in content


def test_agents_uninstall_removes_section(tmp_path):
    _agents_install(tmp_path, "codex")
    _agents_uninstall(tmp_path)
    agents_md = tmp_path / "AGENTS.md"
    # File deleted when it only contained graphify section
    assert not agents_md.exists()


def test_agents_uninstall_preserves_other_content(tmp_path):
    """Uninstall keeps pre-existing content."""
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# Existing rules\n\nDo not break things.\n")
    _agents_install(tmp_path, "codex")
    _agents_uninstall(tmp_path)
    assert agents_md.exists()
    content = agents_md.read_text()
    assert "Do not break things." in content
    assert "## aag" not in content


def test_agents_uninstall_no_op_when_not_installed(tmp_path, capsys):
    _agents_uninstall(tmp_path)
    out = capsys.readouterr().out
    assert "nothing to do" in out


# --- OpenCode plugin tests ---

def test_opencode_agents_install_writes_plugin(tmp_path):
    """opencode install writes .opencode/plugins/graphify.js."""
    _agents_install(tmp_path, "opencode")
    plugin = tmp_path / ".opencode" / "plugins" / "graphify.js"
    assert plugin.exists()
    assert "tool.execute.before" in plugin.read_text()


def test_opencode_agents_install_registers_plugin_in_config(tmp_path):
    """opencode install registers the plugin in .opencode/opencode.json."""
    _agents_install(tmp_path, "opencode")
    config_file = tmp_path / ".opencode" / "opencode.json"
    assert config_file.exists()
    import json as _json
    config = _json.loads(config_file.read_text())
    assert any("graphify.js" in p for p in config.get("plugin", []))


def test_opencode_agents_install_merges_existing_config(tmp_path):
    """opencode install preserves existing .opencode/opencode.json keys."""
    import json as _json
    config_file = tmp_path / ".opencode" / "opencode.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(_json.dumps({"model": "claude-opus-4-5", "plugin": []}))
    _agents_install(tmp_path, "opencode")
    config = _json.loads(config_file.read_text())
    assert config["model"] == "claude-opus-4-5"
    assert any("graphify.js" in p for p in config["plugin"])


def test_opencode_agents_uninstall_removes_plugin(tmp_path):
    """opencode uninstall removes the plugin file and deregisters from opencode.json."""
    import json as _json
    _agents_install(tmp_path, "opencode")
    _agents_uninstall(tmp_path, platform="opencode")
    plugin = tmp_path / ".opencode" / "plugins" / "graphify.js"
    assert not plugin.exists()
    config_file = tmp_path / ".opencode" / "opencode.json"
    if config_file.exists():
        config = _json.loads(config_file.read_text())
        assert not any("graphify.js" in p for p in config.get("plugin", []))


# ── Cursor ────────────────────────────────────────────────────────────────────

def test_cursor_install_writes_rule(tmp_path):
    """cursor install writes .cursor/rules/aag.mdc."""
    from graphify.__main__ import _cursor_install
    _cursor_install(tmp_path)
    rule = tmp_path / ".cursor" / "rules" / "aag.mdc"
    assert rule.exists()
    content = rule.read_text()
    assert "alwaysApply: true" in content
    assert "graphify-out/GRAPH_REPORT.md" in content


def test_cursor_install_idempotent(tmp_path):
    """cursor install does not overwrite an existing rule file."""
    from graphify.__main__ import _cursor_install
    _cursor_install(tmp_path)
    rule = tmp_path / ".cursor" / "rules" / "aag.mdc"
    original = rule.read_text()
    _cursor_install(tmp_path)
    assert rule.read_text() == original


def test_cursor_uninstall_removes_rule(tmp_path):
    """cursor uninstall removes the rule file."""
    from graphify.__main__ import _cursor_install, _cursor_uninstall
    _cursor_install(tmp_path)
    _cursor_uninstall(tmp_path)
    rule = tmp_path / ".cursor" / "rules" / "aag.mdc"
    assert not rule.exists()


def test_cursor_uninstall_noop_if_not_installed(tmp_path):
    """cursor uninstall does nothing if rule was never written."""
    from graphify.__main__ import _cursor_uninstall
    _cursor_uninstall(tmp_path)  # should not raise


# ── Gemini CLI ────────────────────────────────────────────────────────────────

def test_gemini_install_writes_gemini_md(tmp_path):
    from graphify.__main__ import gemini_install
    gemini_install(tmp_path)
    md = tmp_path / "GEMINI.md"
    assert md.exists()
    assert "graphify-out/GRAPH_REPORT.md" in md.read_text()

def test_gemini_install_writes_hook(tmp_path):
    import json as _json
    from graphify.__main__ import gemini_install
    gemini_install(tmp_path)
    settings = _json.loads((tmp_path / ".gemini" / "settings.json").read_text())
    hooks = settings["hooks"]["BeforeTool"]
    assert any("graphify" in str(h) for h in hooks)

def test_gemini_install_idempotent(tmp_path):
    from graphify.__main__ import gemini_install
    gemini_install(tmp_path)
    gemini_install(tmp_path)
    md = tmp_path / "GEMINI.md"
    assert md.read_text().count("## aag") == 1

def test_gemini_install_merges_existing_gemini_md(tmp_path):
    from graphify.__main__ import gemini_install
    (tmp_path / "GEMINI.md").write_text("# My project rules\n")
    gemini_install(tmp_path)
    content = (tmp_path / "GEMINI.md").read_text()
    assert "# My project rules" in content
    assert "graphify-out/GRAPH_REPORT.md" in content

def test_gemini_uninstall_removes_section(tmp_path):
    from graphify.__main__ import gemini_install, gemini_uninstall
    gemini_install(tmp_path)
    gemini_uninstall(tmp_path)
    md = tmp_path / "GEMINI.md"
    assert not md.exists()

def test_gemini_uninstall_removes_hook(tmp_path):
    import json as _json
    from graphify.__main__ import gemini_install, gemini_uninstall
    gemini_install(tmp_path)
    gemini_uninstall(tmp_path)
    settings_path = tmp_path / ".gemini" / "settings.json"
    if settings_path.exists():
        settings = _json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {}).get("BeforeTool", [])
        assert not any("graphify" in str(h) for h in hooks)

def test_gemini_uninstall_noop_if_not_installed(tmp_path):
    from graphify.__main__ import gemini_uninstall
    gemini_uninstall(tmp_path)  # should not raise


# --- Hook injection probes must recognize both graph.json and graph.db ---

def test_claude_hook_probes_both_backends():
    """The Claude PreToolUse hook checks for KB existence before injecting
    a reminder. It must trigger for graph.json AND graph.db KBs (regression
    guard: previously only graph.json was probed)."""
    from graphify.__main__ import _get_claude_hook
    cmd = _get_claude_hook()["hooks"][0]["command"]
    assert "graphify-out/graph.json" in cmd
    assert "graphify-out/graph.db" in cmd


def test_gemini_hook_probes_both_backends():
    from graphify.__main__ import _get_gemini_hook
    cmd = _get_gemini_hook()["hooks"][0]["command"]
    assert "graph.json" in cmd
    assert "graph.db" in cmd


def test_opencode_plugin_probes_both_backends():
    from graphify.__main__ import _OPENCODE_PLUGIN_JS
    assert "graph.json" in _OPENCODE_PLUGIN_JS
    assert "graph.db" in _OPENCODE_PLUGIN_JS


# --- pyinstall tests ---

def test_pyinstall_creates_pyaag_skill(tmp_path):
    """pyinstall writes skill to ~/.claude/skills/pyaag/SKILL.md."""
    from graphify.__main__ import pyinstall
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        pyinstall()
    skill = tmp_path / ".claude" / "skills" / "pyaag" / "SKILL.md"
    assert skill.exists()
    content = skill.read_text()
    # Frontmatter is correct
    assert "name: pyaag" in content
    assert "trigger: /pyaag" in content

    # Modular files exist
    assert (skill.parent / "build.md").exists()
    assert (skill.parent / "interact.md").exists()
    
    # Check transformed content in modular files uses resolved python path
    build_content = (skill.parent / "build.md").read_text()
    assert f"{sys.executable} -c" in build_content
    assert "from graphify." in build_content

    interact_content = (skill.parent / "interact.md").read_text()
    assert f"{sys.executable} -m graphify query" in interact_content

    export_content = (skill.parent / "export.md").read_text()
    assert f"{sys.executable} -m graphify export" in export_content

    # Quick start in main skill uses resolved python path (pyinstall mode)
    assert sys.executable in content
    assert "aag eval" not in content
    # /pyaag in usage, not /aag
    assert "/pyaag" in content
    assert "/aag" not in content


def test_pyinstall_registers_claude_md(tmp_path):
    """pyinstall registers pyaag in CLAUDE.md."""
    from graphify.__main__ import pyinstall
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        pyinstall()
    claude_md = tmp_path / ".claude" / "CLAUDE.md"
    assert claude_md.exists()
    content = claude_md.read_text()
    assert "pyaag" in content
    assert "/pyaag" in content


def test_pyinstall_idempotent(tmp_path):
    """Running pyinstall twice does not duplicate CLAUDE.md registration."""
    from graphify.__main__ import pyinstall
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        pyinstall()
        pyinstall()
    claude_md = tmp_path / ".claude" / "CLAUDE.md"
    content = claude_md.read_text()
    assert content.count("# pyaag") == 1  # only one registration block


def test_pyinstall_gemini(tmp_path):
    """pyinstall --platform gemini installs to .gemini (or .agents on Windows) and writes GEMINI.md."""
    from graphify.__main__ import pyinstall
    import os
    import platform
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        with patch("graphify.__main__.Path.home", return_value=tmp_path):
            pyinstall(platform="gemini")
    finally:
        os.chdir(old_cwd)
    
    dot_dir = ".agents" if platform.system() == "Windows" else ".gemini"
    skill = tmp_path / dot_dir / "skills" / "pyaag" / "SKILL.md"
    assert skill.exists()
    content = skill.read_text()
    assert "name: pyaag" in content
    assert "trigger: /pyaag" in content
    
    gemini_md = tmp_path / "GEMINI.md"
    assert gemini_md.exists()
    md_content = gemini_md.read_text()
    assert "## pyaag" in md_content
    assert "pyaag query" in md_content
