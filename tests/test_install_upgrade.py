"""Installer-level regression tests for upgrade-in-place behavior (issue #580).

Pre-fix, the installers wrote a "## graphify" section with report-first
instructions and skipped writing if the marker was already present. So users
who installed graphify and then upgraded to the fixed package still had the
old report-first text on disk — the bug stayed live for them.

These tests seed each platform's instruction file with the old report-first
section, run the installer, and assert that the on-disk file now contains
the new query-first wording and does not contain the old report-first text.
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest

import graphify.__main__ as mainmod


# A representative slice of the pre-fix text. Each platform's old install
# wrote a variant of "ALWAYS read graphify-out/GRAPH_REPORT.md before ...".
_OLD_CLAUDE_SECTION = """\
## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- ALWAYS read graphify-out/GRAPH_REPORT.md before reading any source files, running grep/glob searches, or answering codebase questions. The graph is your primary map of the codebase.
- IF graphify-out/wiki/index.md EXISTS, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
"""


_OLD_AGENTS_SECTION = _OLD_CLAUDE_SECTION  # identical pre-fix shape

_OLD_GEMINI_SECTION = _OLD_CLAUDE_SECTION

_OLD_VSCODE_SECTION = """\
## graphify

For any question about this repo's architecture, structure, components, or how to add/modify/find
code, your **first tool call must be** to read `graphify-out/GRAPH_REPORT.md` (if it exists).

Triggers: "how do I…", "where is…", "what does … do", "add/modify a <component>".
"""


_OLD_CURSOR_RULE = """\
---
description: graphify knowledge graph context
alwaysApply: true
---

This project has a graphify knowledge graph at graphify-out/.

- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
"""


_OLD_KIRO_STEERING = """\
---
inclusion: always
---

graphify: A knowledge graph of this project lives in `graphify-out/`. \
If `graphify-out/GRAPH_REPORT.md` exists, read it before answering architecture questions, \
tracing dependencies, or searching files — it contains god nodes, community structure, \
and surprising connections the graph found.
"""


_OLD_HOOK_PAYLOAD_SNIPPET = "Read graphify-out/GRAPH_REPORT.md for god nodes and community structure before searching raw files"


def _assert_no_report_first(text: str, ctx: str) -> None:
    assert "ALWAYS read graphify-out/GRAPH_REPORT.md" not in text, (
        f"{ctx}: old 'ALWAYS read' phrasing survived upgrade"
    )
    assert "first tool call must be" not in text, (
        f"{ctx}: old VS Code 'first tool call must be' phrasing survived upgrade"
    )


def _assert_query_first(text: str, ctx: str) -> None:
    assert "graphify query" in text, (
        f"{ctx}: new 'graphify query' guidance missing after upgrade"
    )


def test_claude_install_upgrades_stale_section(tmp_path, monkeypatch):
    """A pre-fix CLAUDE.md gets the new section in place when the user runs
    `graphify claude install` again after upgrading to a fixed package."""
    monkeypatch.chdir(tmp_path)
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# My Project\n\nSome description.\n\n" + _OLD_CLAUDE_SECTION, encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    mainmod.claude_install(tmp_path)

    after = claude_md.read_text(encoding="utf-8")
    _assert_no_report_first(after, "CLAUDE.md")
    _assert_query_first(after, "CLAUDE.md")
    # Pre-existing non-graphify content must be preserved
    assert "# My Project" in after
    assert "Some description." in after


def test_claude_install_upgrades_stale_hook_payload(tmp_path, monkeypatch):
    """The Claude install must also rewrite a stale .claude/settings.json hook
    payload on upgrade. Pre-fix, the install returned early when CLAUDE.md was
    already configured, leaving the old hook in place."""
    monkeypatch.chdir(tmp_path)
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(_OLD_CLAUDE_SECTION, encoding="utf-8")
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    stale_settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "case x in *) "
                                + _OLD_HOOK_PAYLOAD_SNIPPET
                                + " esac"
                            ),
                        }
                    ],
                }
            ]
        }
    }
    settings.write_text(json.dumps(stale_settings), encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    mainmod.claude_install(tmp_path)

    new_settings_text = settings.read_text(encoding="utf-8")
    assert _OLD_HOOK_PAYLOAD_SNIPPET not in new_settings_text, (
        "stale hook payload survived upgrade"
    )
    assert "graphify query" in new_settings_text, (
        "new hook payload should route to `graphify query`"
    )


def test_agents_install_upgrades_stale_section(tmp_path, monkeypatch):
    """Same upgrade behavior for AGENTS.md (Codex / OpenCode / Aider / Trae)."""
    monkeypatch.chdir(tmp_path)
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# Project agents\n\n" + _OLD_AGENTS_SECTION, encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    mainmod._agents_install(tmp_path, platform="codex")

    after = agents_md.read_text(encoding="utf-8")
    _assert_no_report_first(after, "AGENTS.md")
    _assert_query_first(after, "AGENTS.md")
    assert "# Project agents" in after


def test_gemini_install_upgrades_stale_section(tmp_path, monkeypatch):
    """Same upgrade behavior for GEMINI.md."""
    monkeypatch.chdir(tmp_path)
    gemini_md = tmp_path / "GEMINI.md"
    gemini_md.write_text(_OLD_GEMINI_SECTION, encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    mainmod.gemini_install(tmp_path)

    after = gemini_md.read_text(encoding="utf-8")
    _assert_no_report_first(after, "GEMINI.md")
    _assert_query_first(after, "GEMINI.md")


def test_vscode_install_upgrades_stale_section(tmp_path, monkeypatch):
    """Same upgrade behavior for .github/copilot-instructions.md (VS Code)."""
    monkeypatch.chdir(tmp_path)
    instructions = tmp_path / ".github" / "copilot-instructions.md"
    instructions.parent.mkdir(parents=True, exist_ok=True)
    instructions.write_text(_OLD_VSCODE_SECTION, encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    mainmod.vscode_install(tmp_path)

    after = instructions.read_text(encoding="utf-8")
    _assert_no_report_first(after, "copilot-instructions.md")
    _assert_query_first(after, "copilot-instructions.md")


def test_cursor_install_upgrades_stale_rule(tmp_path, monkeypatch):
    """Same upgrade behavior for .cursor/rules/graphify.mdc.
    The Cursor rule file is wholly graphify-owned; overwrite on upgrade."""
    monkeypatch.chdir(tmp_path)
    rule_path = tmp_path / ".cursor" / "rules" / "graphify.mdc"
    rule_path.parent.mkdir(parents=True, exist_ok=True)
    rule_path.write_text(_OLD_CURSOR_RULE, encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    mainmod._cursor_install(tmp_path)

    after = rule_path.read_text(encoding="utf-8")
    assert "read graphify-out/GRAPH_REPORT.md for god nodes and community structure" not in after
    _assert_query_first(after, ".cursor/rules/graphify.mdc")
    # YAML frontmatter must be preserved
    assert "alwaysApply: true" in after


def test_kiro_install_upgrades_stale_steering(tmp_path, monkeypatch):
    """Same upgrade behavior for .kiro/steering/graphify.md (wholly owned)."""
    monkeypatch.chdir(tmp_path)
    steering = tmp_path / ".kiro" / "steering" / "graphify.md"
    steering.parent.mkdir(parents=True, exist_ok=True)
    steering.write_text(_OLD_KIRO_STEERING, encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    # Kiro install copies a skill file too; provide a minimal stand-in
    skill_src = Path(mainmod.__file__).parent / "skill-kiro.md"
    if not skill_src.exists():
        pytest.skip("skill-kiro.md not present in this checkout")

    mainmod._kiro_install(tmp_path)

    after = steering.read_text(encoding="utf-8")
    assert "read it before answering architecture questions" not in after
    _assert_query_first(after, ".kiro/steering/graphify.md")
    assert "inclusion: always" in after  # frontmatter preserved
