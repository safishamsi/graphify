"""Tests for graphify install --platform routing."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
import re
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib
import pytest


PLATFORMS = {
    "claude": (".claude/skills/graphify/SKILL.md",),
    "codex": (".agents/skills/graphify/SKILL.md",),
    "opencode": (".config/opencode/skills/graphify/SKILL.md",),
    "aider": (".aider/graphify/SKILL.md",),
    "copilot": (".copilot/skills/graphify/SKILL.md",),
    "vscode": (".copilot/skills/graphify/SKILL.md",),
    "claw": (".openclaw/skills/graphify/SKILL.md",),
    "droid": (".factory/skills/graphify/SKILL.md",),
    "trae": (".trae/skills/graphify/SKILL.md",),
    "trae-cn": (".trae-cn/skills/graphify/SKILL.md",),
    "hermes": (".hermes/skills/graphify/SKILL.md",),
    "kimi": (".kimi/skills/graphify/SKILL.md",),
    "kiro": (".kiro/skills/graphify/SKILL.md",),
    "pi": (".pi/agent/skills/graphify/SKILL.md",),
    "antigravity": (".agent/skills/graphify/SKILL.md",),
    "windows": (".claude/skills/graphify/SKILL.md",),
}


@contextmanager
def _patched_home(tmp_path):
    old_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        with patch("graphify.__main__.Path.home", return_value=tmp_path), patch.dict(os.environ, {}, clear=True):
            yield
    finally:
        os.chdir(old_cwd)


def _install(tmp_path, platform):
    from graphify.__main__ import install
    with _patched_home(tmp_path):
        install(platform=platform)


def _skill_source_text(platform):
    from graphify.__main__ import _platform_skill_source
    return _platform_skill_source(platform).read_text(encoding="utf-8")


def _run_main(tmp_path, argv):
    from graphify.__main__ import main
    with _patched_home(tmp_path), patch.object(sys, "argv", argv):
        result = main()
    assert result in (None, 0)


def test_install_default_claude(tmp_path):
    _install(tmp_path, "claude")
    assert (tmp_path / ".claude" / "skills" / "graphify" / "SKILL.md").exists()


def test_install_codex(tmp_path):
    _install(tmp_path, "codex")
    assert (tmp_path / ".agents" / "skills" / "graphify" / "SKILL.md").exists()


def test_install_opencode(tmp_path):
    _install(tmp_path, "opencode")
    assert (tmp_path / ".config" / "opencode" / "skills" / "graphify" / "SKILL.md").exists()


def test_install_positional_platform_opencode(tmp_path, monkeypatch):
    from graphify.__main__ import main
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["graphify", "install", "opencode"])
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        main()
    assert (tmp_path / ".config" / "opencode" / "skills" / "graphify" / "SKILL.md").exists()
    assert not (tmp_path / ".claude" / "skills" / "graphify" / "SKILL.md").exists()


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
    assert (tmp_path / ".openclaw" / "skills" / "graphify" / "SKILL.md").exists()


def test_install_droid(tmp_path):
    _install(tmp_path, "droid")
    assert (tmp_path / ".factory" / "skills" / "graphify" / "SKILL.md").exists()


def test_install_trae(tmp_path):
    _install(tmp_path, "trae")
    assert (tmp_path / ".trae" / "skills" / "graphify" / "SKILL.md").exists()


def test_install_trae_cn(tmp_path):
    _install(tmp_path, "trae-cn")
    assert (tmp_path / ".trae-cn" / "skills" / "graphify" / "SKILL.md").exists()


def test_install_windows(tmp_path):
    _install(tmp_path, "windows")
    assert (tmp_path / ".claude" / "skills" / "graphify" / "SKILL.md").exists()


def test_install_unknown_platform_exits(tmp_path):
    with pytest.raises(SystemExit):
        _install(tmp_path, "unknown")


def test_legacy_install_parser_keeps_default_platform():
    from graphify.__main__ import _parse_install_args
    assert _parse_install_args([]) == "claude"


def test_legacy_install_parser_uses_windows_default():
    from graphify.__main__ import _parse_install_args
    with patch("graphify.__main__.platform.system", return_value="Windows"):
        assert _parse_install_args([]) == "windows"


def test_legacy_install_parser_accepts_positional_platform():
    from graphify.__main__ import _parse_install_args
    assert _parse_install_args(["codex"]) == "codex"


def test_legacy_install_parser_accepts_platform_flag():
    from graphify.__main__ import _parse_install_args
    assert _parse_install_args(["--platform", "codex"]) == "codex"
    assert _parse_install_args(["--platform=codex"]) == "codex"


def test_named_command_parser_requires_explicit_platform():
    from graphify.__main__ import _parse_named_command_args
    assert _parse_named_command_args([]) == (None, False)


def test_named_command_parser_accepts_platform_and_remove_forms():
    from graphify.__main__ import _parse_named_command_args
    assert _parse_named_command_args(["codex"]) == ("codex", False)
    assert _parse_named_command_args(["install", "codex"]) == ("codex", False)
    assert _parse_named_command_args(["remove", "codex"]) == ("codex", True)
    assert _parse_named_command_args(["codex", "remove"]) == ("codex", True)


def test_cli_skill_codex_installs_user_skill(tmp_path):
    _run_main(tmp_path, ["graphify", "skill", "codex"])
    assert (tmp_path / ".agents" / "skills" / "graphify" / "SKILL.md").exists()


def test_cli_skill_requires_platform(tmp_path):
    from graphify.__main__ import main
    with _patched_home(tmp_path), patch.object(sys, "argv", ["graphify", "skill"]):
        with pytest.raises(SystemExit):
            main()


def test_cli_skill_help_has_no_side_effects(tmp_path, capsys):
    _run_main(tmp_path, ["graphify", "skill", "codex", "--help"])
    captured = capsys.readouterr()
    assert "Usage: graphify skill" in captured.out
    assert not (tmp_path / ".agents").exists()


def test_cli_setup_codex_configures_project(tmp_path):
    _run_main(tmp_path, ["graphify", "setup", "codex"])
    assert (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / ".codex" / "hooks.json").exists()
    config = tomllib.loads((tmp_path / ".codex" / "config.toml").read_text(encoding="utf-8"))
    assert config["features"]["hooks"] is True


def test_cli_setup_codex_migrates_deprecated_hooks_feature(tmp_path):
    config_path = tmp_path / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "[features]\n"
        "codex_hooks = true\n"
        "multi_agent = true\n",
        encoding="utf-8",
    )

    _run_main(tmp_path, ["graphify", "setup", "codex"])

    content = config_path.read_text(encoding="utf-8")
    config = tomllib.loads(content)
    assert config["features"]["hooks"] is True
    assert config["features"]["multi_agent"] is True
    assert "codex_hooks" not in content


def test_cli_setup_requires_platform(tmp_path):
    from graphify.__main__ import main
    with _patched_home(tmp_path), patch.object(sys, "argv", ["graphify", "setup"]):
        with pytest.raises(SystemExit):
            main()


def test_cli_setup_help_has_no_side_effects(tmp_path, capsys):
    _run_main(tmp_path, ["graphify", "setup", "codex", "--help"])
    captured = capsys.readouterr()
    assert "Usage: graphify setup" in captured.out
    assert not (tmp_path / "AGENTS.md").exists()


def test_cli_install_help_has_no_side_effects(tmp_path, capsys):
    _run_main(tmp_path, ["graphify", "install", "codex", "--help"])
    captured = capsys.readouterr()
    assert "Deprecated alias" in captured.out
    assert not (tmp_path / ".agents").exists()


def test_cli_install_positional_platform_is_deprecated_alias(tmp_path, capsys):
    _run_main(tmp_path, ["graphify", "install", "codex"])
    captured = capsys.readouterr()
    assert "deprecated alias" in captured.err
    assert (tmp_path / ".agents" / "skills" / "graphify" / "SKILL.md").exists()


def test_cli_platform_install_is_deprecated_setup_alias(tmp_path, capsys):
    _run_main(tmp_path, ["graphify", "codex", "install"])
    captured = capsys.readouterr()
    assert "deprecated alias" in captured.err
    assert (tmp_path / "AGENTS.md").exists()


@pytest.mark.parametrize("platform, paths", sorted(PLATFORMS.items()))
def test_install_copies_configured_skill_source(tmp_path, platform, paths):
    _install(tmp_path, platform)
    installed = tmp_path / paths[0]
    assert installed.exists()
    assert installed.read_text(encoding="utf-8") == _skill_source_text(platform)


def test_codex_skill_contains_spawn_agent():
    """Codex skill file must reference spawn_agent."""
    import graphify
    skill = (Path(graphify.__file__).parent / "skill-codex.md").read_text()
    assert "spawn_agent" in skill


def test_codex_skill_contains_kimi_fast_path():
    """Codex skill file must document the direct Kimi extraction path."""
    import graphify
    skill = (Path(graphify.__file__).parent / "skill-codex.md").read_text()
    assert "MOONSHOT_API_KEY" in skill
    assert "extract_corpus_parallel" in skill
    assert 'backend="kimi"' in skill


def test_claude_and_codex_skills_share_kimi_fast_path_contract():
    """Both Claude and Codex document the same Kimi fast-path output contract."""
    import graphify
    pkg = Path(graphify.__file__).parent
    for name in ("skill-claude.md", "skill-codex.md"):
        skill = (pkg / name).read_text(encoding="utf-8")
        assert "MOONSHOT_API_KEY" in skill
        assert "extract_corpus_parallel" in skill
        assert 'backend="kimi"' in skill
        assert "graphify-out/.graphify_semantic_new.json" in skill


def test_opencode_skill_contains_mention():
    """OpenCode skill file must reference @mention."""
    import graphify
    skill = (Path(graphify.__file__).parent / "skill-opencode.md").read_text()
    assert "@mention" in skill


def test_claw_skill_is_sequential():
    """OpenClaw skill file must describe sequential extraction."""
    import graphify
    skill = (Path(graphify.__file__).parent / "skill-claw.md").read_text()
    assert "sequential" in skill.lower()
    assert "spawn_agent" not in skill
    assert "@mention" not in skill


def test_all_skill_files_exist_in_package():
    """All installable platform skill files must be present in the installed package."""
    from graphify.__main__ import _PLATFORM_CONFIG, _platform_skill_source
    for platform, cfg in _PLATFORM_CONFIG.items():
        assert cfg["skill_file"].startswith("skill-")
        assert cfg["skill_file"].endswith(".md")
        assert cfg["skill_file"] != "skill.md"
        assert _platform_skill_source(platform).exists(), f"Missing: {cfg['skill_file']}"


def test_all_configured_install_paths_are_home_relative():
    """Platform config should not freeze Path.home() at import time."""
    from graphify.__main__ import _PLATFORM_CONFIG
    for platform, cfg in _PLATFORM_CONFIG.items():
        assert not cfg["skill_dst"].is_absolute(), f"{platform} has absolute skill_dst"


def test_packaged_skill_files_match_source_tree():
    """Every source skill file is declared in package data, with no legacy skill.md alias."""
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    declared = set(pyproject["tool"]["setuptools"]["package-data"]["graphify"])
    source = {p.name for p in (root / "graphify").glob("skill-*.md")}
    assert declared == source
    assert "skill.md" not in declared
    assert not (root / "graphify" / "skill.md").exists()


def test_skill_temp_files_stay_under_graphify_out():
    """No platform skill should write root-level .graphify_* temp files."""
    import graphify
    pkg = Path(graphify.__file__).parent
    legacy_temp = re.compile(
        r"(?<!graphify-out/)\.graphify_"
        r"(python|detect|transcripts|ast|cached|uncached|semantic_new|semantic|extract|analysis|labels|incremental|old|chunk_)"
    )
    for skill_path in pkg.glob("skill-*.md"):
        assert not legacy_temp.search(skill_path.read_text(encoding="utf-8")), skill_path.name


def test_claude_platform_uses_named_skill_source():
    """Claude installs from the explicit Claude skill source file."""
    from graphify.__main__ import _PLATFORM_CONFIG
    assert _PLATFORM_CONFIG["claude"]["skill_file"] == "skill-claude.md"


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


def test_codex_agents_install_cleans_legacy_hooks(tmp_path):
    hooks_path = tmp_path / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(json.dumps({
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "echo graphify legacy prompt"}]},
                {"hooks": [{"type": "command", "command": "echo keep prompt"}]},
            ],
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "graphify hook-check"}]},
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo keep tool"}]},
            ],
        }
    }))

    _agents_install(tmp_path, "codex")

    settings = json.loads(hooks_path.read_text())
    hooks = settings["hooks"]
    assert "legacy prompt" not in str(settings)
    assert "keep prompt" in str(hooks.get("UserPromptSubmit", []))
    assert "keep tool" in str(hooks.get("PreToolUse", []))
    assert "hook-check" not in str(settings)


def test_codex_hook_cleanup_preserves_unrelated_handlers_in_same_group(tmp_path):
    from graphify.__main__ import _uninstall_codex_hook
    hooks_path = tmp_path / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(json.dumps({
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": "graphify hook-check"},
                        {"type": "command", "command": "echo keep same group"},
                    ],
                },
            ],
        }
    }))

    _uninstall_codex_hook(tmp_path)

    settings = json.loads(hooks_path.read_text())
    pre_tool = settings["hooks"]["PreToolUse"]
    assert "graphify" not in str(pre_tool)
    assert "echo keep same group" in str(pre_tool)


def test_codex_uninstall_removes_all_graphify_hooks(tmp_path):
    from graphify.__main__ import _uninstall_codex_hook
    hooks_path = tmp_path / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(json.dumps({
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "echo graphify legacy prompt"}]},
            ],
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "graphify hook-check"}]},
            ],
            "PostToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo keep"}]},
            ],
        }
    }))

    _uninstall_codex_hook(tmp_path)

    settings = json.loads(hooks_path.read_text())
    assert "graphify" not in str(settings)
    assert "keep" in str(settings)


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
    assert content.count("## graphify") == 1


def test_agents_install_appends_to_existing(tmp_path):
    """Installs into an existing AGENTS.md without overwriting other content."""
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# Existing rules\n\nDo not break things.\n")
    _agents_install(tmp_path, "codex")
    content = agents_md.read_text()
    assert "Do not break things." in content
    assert "## graphify" in content


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
    assert "## graphify" not in content


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
    """cursor install writes .cursor/rules/graphify.mdc."""
    from graphify.__main__ import _cursor_install
    _cursor_install(tmp_path)
    rule = tmp_path / ".cursor" / "rules" / "graphify.mdc"
    assert rule.exists()
    content = rule.read_text()
    assert "alwaysApply: true" in content
    assert "graphify-out/GRAPH_REPORT.md" in content


def test_cursor_install_idempotent(tmp_path):
    """cursor install does not overwrite an existing rule file."""
    from graphify.__main__ import _cursor_install
    _cursor_install(tmp_path)
    rule = tmp_path / ".cursor" / "rules" / "graphify.mdc"
    original = rule.read_text()
    _cursor_install(tmp_path)
    assert rule.read_text() == original


def test_cursor_uninstall_removes_rule(tmp_path):
    """cursor uninstall removes the rule file."""
    from graphify.__main__ import _cursor_install, _cursor_uninstall
    _cursor_install(tmp_path)
    _cursor_uninstall(tmp_path)
    rule = tmp_path / ".cursor" / "rules" / "graphify.mdc"
    assert not rule.exists()


def test_cursor_uninstall_noop_if_not_installed(tmp_path):
    """cursor uninstall does nothing if rule was never written."""
    from graphify.__main__ import _cursor_uninstall
    _cursor_uninstall(tmp_path)  # should not raise


# ── Skill-copying special installers ─────────────────────────────────────────

def test_vscode_install_copies_vscode_skill_source(tmp_path):
    from graphify.__main__ import vscode_install
    with _patched_home(tmp_path):
        vscode_install(tmp_path)
    installed = tmp_path / ".copilot" / "skills" / "graphify" / "SKILL.md"
    assert installed.read_text(encoding="utf-8") == _skill_source_text("vscode")


def test_kiro_install_copies_kiro_skill_source(tmp_path):
    from graphify.__main__ import _kiro_install
    _kiro_install(tmp_path)
    installed = tmp_path / ".kiro" / "skills" / "graphify" / "SKILL.md"
    assert installed.read_text(encoding="utf-8") == _skill_source_text("kiro")


def test_antigravity_install_copies_claude_skill_with_frontmatter(tmp_path):
    from graphify.__main__ import _antigravity_install
    with _patched_home(tmp_path):
        _antigravity_install(tmp_path)
    installed = tmp_path / ".agent" / "skills" / "graphify" / "SKILL.md"
    content = installed.read_text(encoding="utf-8")
    assert content.startswith("---\nname: graphify-manager\n")
    source_body = _skill_source_text("antigravity").split("\n---\n", 1)[1].lstrip()
    assert content.endswith(source_body)


# ── Gemini CLI ────────────────────────────────────────────────────────────────

def test_gemini_install_writes_gemini_md(tmp_path):
    from graphify.__main__ import gemini_install
    with _patched_home(tmp_path):
        gemini_install(tmp_path)
    md = tmp_path / "GEMINI.md"
    assert md.exists()
    assert "graphify-out/GRAPH_REPORT.md" in md.read_text()

def test_gemini_install_writes_hook(tmp_path):
    import json as _json
    from graphify.__main__ import gemini_install
    with _patched_home(tmp_path):
        gemini_install(tmp_path)
    settings = _json.loads((tmp_path / ".gemini" / "settings.json").read_text())
    hooks = settings["hooks"]["BeforeTool"]
    assert any("graphify" in str(h) for h in hooks)

def test_gemini_install_copies_claude_skill_source(tmp_path):
    from graphify.__main__ import gemini_install
    with _patched_home(tmp_path):
        gemini_install(tmp_path)
    installed = tmp_path / ".gemini" / "skills" / "graphify" / "SKILL.md"
    assert installed.read_text(encoding="utf-8") == _skill_source_text("claude")

def test_gemini_windows_install_uses_agents_skill_dir(tmp_path):
    from graphify.__main__ import gemini_install
    with _patched_home(tmp_path), patch("graphify.__main__.platform.system", return_value="Windows"):
        gemini_install(tmp_path)
    installed = tmp_path / ".agents" / "skills" / "graphify" / "SKILL.md"
    assert installed.read_text(encoding="utf-8") == _skill_source_text("claude")

def test_gemini_install_idempotent(tmp_path):
    from graphify.__main__ import gemini_install
    with _patched_home(tmp_path):
        gemini_install(tmp_path)
        gemini_install(tmp_path)
    md = tmp_path / "GEMINI.md"
    assert md.read_text().count("## graphify") == 1

def test_gemini_install_merges_existing_gemini_md(tmp_path):
    from graphify.__main__ import gemini_install
    (tmp_path / "GEMINI.md").write_text("# My project rules\n")
    with _patched_home(tmp_path):
        gemini_install(tmp_path)
    content = (tmp_path / "GEMINI.md").read_text()
    assert "# My project rules" in content
    assert "graphify-out/GRAPH_REPORT.md" in content

def test_gemini_uninstall_removes_section(tmp_path):
    from graphify.__main__ import gemini_install, gemini_uninstall
    with _patched_home(tmp_path):
        gemini_install(tmp_path)
        gemini_uninstall(tmp_path)
    md = tmp_path / "GEMINI.md"
    assert not md.exists()

def test_gemini_uninstall_removes_hook(tmp_path):
    import json as _json
    from graphify.__main__ import gemini_install, gemini_uninstall
    with _patched_home(tmp_path):
        gemini_install(tmp_path)
        gemini_uninstall(tmp_path)
    settings_path = tmp_path / ".gemini" / "settings.json"
    if settings_path.exists():
        settings = _json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {}).get("BeforeTool", [])
        assert not any("graphify" in str(h) for h in hooks)

def test_gemini_uninstall_noop_if_not_installed(tmp_path):
    from graphify.__main__ import gemini_uninstall
    with _patched_home(tmp_path):
        gemini_uninstall(tmp_path)  # should not raise
