"""Regression tests for install-time instruction strings.

These strings live in graphify/__main__.py and are written into project-local
files (CLAUDE.md, AGENTS.md, GEMINI.md, .cursor/rules/, .kiro/steering/, etc.)
or into in-process hook payloads. Earlier versions of graphify told every
assistant to "ALWAYS read graphify-out/GRAPH_REPORT.md before answering" —
which silently increased per-question token usage in Claude Code sessions
(issue #580). This file locks in the query-first policy so a future revert
or partial change is caught by CI.
"""
from __future__ import annotations
import json

from graphify.__main__ import (
    _SETTINGS_HOOK,
    _CLAUDE_MD_SECTION,
    _AGENTS_MD_SECTION,
    _GEMINI_MD_SECTION,
    _GEMINI_HOOK,
    _VSCODE_INSTRUCTIONS_SECTION,
    _ANTIGRAVITY_RULES,
    _KIRO_STEERING,
    _CURSOR_RULE,
    _OPENCODE_PLUGIN_JS,
    _DEVIN_RULES,
)


# All install-surface text rendered as plain strings, in one place.
# Hook constants are dicts/JSON; serialize them so we can do substring checks
# against the actual payload text the assistant will receive.
_INSTALL_TEXTS: dict[str, str] = {
    "_SETTINGS_HOOK": json.dumps(_SETTINGS_HOOK),
    "_CLAUDE_MD_SECTION": _CLAUDE_MD_SECTION,
    "_AGENTS_MD_SECTION": _AGENTS_MD_SECTION,
    "_GEMINI_MD_SECTION": _GEMINI_MD_SECTION,
    "_GEMINI_HOOK": json.dumps(_GEMINI_HOOK),
    "_VSCODE_INSTRUCTIONS_SECTION": _VSCODE_INSTRUCTIONS_SECTION,
    "_ANTIGRAVITY_RULES": _ANTIGRAVITY_RULES,
    "_KIRO_STEERING": _KIRO_STEERING,
    "_CURSOR_RULE": _CURSOR_RULE,
    "_OPENCODE_PLUGIN_JS": _OPENCODE_PLUGIN_JS,
    "_DEVIN_RULES": _DEVIN_RULES,
}


def test_every_install_surface_recommends_graphify_query():
    """All ten install surfaces must point the assistant at `graphify query`
    as the first action for codebase questions. This is the load-bearing
    fix for issue #580 — the alternative (reading GRAPH_REPORT.md) costs
    ~10x more tokens per question and made the project worse-than-baseline
    in real Claude Code sessions."""
    missing: list[str] = []
    for name, text in _INSTALL_TEXTS.items():
        if "graphify query" not in text:
            missing.append(name)
    assert not missing, (
        f"these install surfaces no longer mention `graphify query`: {missing}. "
        f"If you removed it intentionally, consider whether issue #580 is back."
    )


def test_no_install_surface_demands_reading_the_full_report_first():
    """The pre-fix instructions told assistants to read GRAPH_REPORT.md as
    their first action for codebase questions. The new policy demotes the
    report to a fallback; any phrasing that puts reading the report BEFORE
    other actions for codebase questions is a regression of issue #580.

    Uses regex patterns instead of literal strings so a future revert that
    rephrases ("MUST read", "Always consult", "first task is to open ...")
    is also caught. Note: bare 'ALWAYS' is NOT banned because
    ``alwaysApply: true`` (Cursor) and ``trigger: always_on`` (Antigravity)
    are legitimate platform metadata, not the bug.
    """
    import re
    banned = [
        # "read ... GRAPH_REPORT.md ... before"
        re.compile(r"read[^.\n]{0,80}GRAPH_REPORT\.md[^.\n]{0,80}before", re.IGNORECASE),
        # "first tool call ... GRAPH_REPORT" (VS Code variant)
        re.compile(r"first\s+tool\s+call[^.\n]{0,80}GRAPH_REPORT", re.IGNORECASE),
        # "ALWAYS read ... GRAPH_REPORT" (catches the literal old text and minor variants)
        re.compile(r"always\s+read[^.\n]{0,80}GRAPH_REPORT", re.IGNORECASE),
    ]
    hits: list[tuple[str, str]] = []
    for name, text in _INSTALL_TEXTS.items():
        for pattern in banned:
            m = pattern.search(text)
            if m:
                hits.append((name, m.group(0)))
    assert not hits, (
        f"banned report-first phrasing reappeared: {hits}. "
        f"This regresses issue #580."
    )


def test_report_is_still_referenced_as_fallback():
    """The fix demotes GRAPH_REPORT.md, it doesn't delete the reference.
    Most install surfaces should still mention the report as the deep-dive
    artifact so users know it exists for broad architecture review.
    (Hook payloads may or may not name the report; check the MD sections
    explicitly — those are the rule lists assistants follow.)"""
    md_section_texts = {
        "_CLAUDE_MD_SECTION": _CLAUDE_MD_SECTION,
        "_AGENTS_MD_SECTION": _AGENTS_MD_SECTION,
        "_GEMINI_MD_SECTION": _GEMINI_MD_SECTION,
        "_VSCODE_INSTRUCTIONS_SECTION": _VSCODE_INSTRUCTIONS_SECTION,
        "_ANTIGRAVITY_RULES": _ANTIGRAVITY_RULES,
        "_KIRO_STEERING": _KIRO_STEERING,
        "_CURSOR_RULE": _CURSOR_RULE,
        "_DEVIN_RULES": _DEVIN_RULES,
    }
    missing: list[str] = []
    for name, text in md_section_texts.items():
        if "GRAPH_REPORT.md" not in text:
            missing.append(name)
    assert not missing, (
        f"these install sections no longer mention GRAPH_REPORT.md at all: {missing}. "
        f"The fix should demote the report, not delete the reference — users need to know "
        f"it's available for broad-architecture queries."
    )


def test_agents_section_does_not_skip_dirty_graph_output():
    assert "Dirty graphify-out/ files are expected" in _AGENTS_MD_SECTION
    assert "not a reason to skip graphify" in _AGENTS_MD_SECTION


def test_how_it_works_clarifies_code_only_semantic_extraction():
    from pathlib import Path
    doc = (Path(__file__).parent.parent / "docs" / "how-it-works.md").read_text(encoding="utf-8")
    assert "Code files are not sent to the LLM semantic extractor" in doc
    assert "code files, Pass 3 is skipped entirely" in doc
    assert "docs, papers, images, and transcripts" in doc
