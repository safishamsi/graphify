from __future__ import annotations
import json
import re
from pathlib import Path

from graphify.installers.core import _replace_or_append_section

_CLAUDE_MD_SECTION = """\
## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
"""

_CLAUDE_MD_MARKER = "## graphify"

_SETTINGS_HOOK = {
    "matcher": "Bash",
    "hooks": [
        {
            "type": "command",
            "command": (
                "CMD=$(python3 -c \""
                "import json,sys; d=json.load(sys.stdin); "
                "print(d.get('tool_input',d).get('command',''))\" 2>/dev/null || true); "
                "case \"$CMD\" in "
                r"*grep*|*rg\ *|*ripgrep*|*find\ *|*fd\ *|*ack\ *|*ag\ *) "
                "  [ -f graphify-out/graph.json ] && "
                r"""  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"graphify: knowledge graph at graphify-out/. For focused questions, run `graphify query \"<question>\"` (scoped subgraph, usually much smaller than GRAPH_REPORT.md) instead of grepping raw files. Read GRAPH_REPORT.md only for broad architecture context."}}' """
                "  || true ;; "
                "esac"
            ),
        }
    ],
}

def _skill_registration(skill_path: str = "~/.claude/skills/graphify/SKILL.md") -> str:
    return (
        "\n# graphify\n"
        f"- **graphify** (`{skill_path}`) "
        "- any input to knowledge graph. Trigger: `/graphify`\n"
        "When the user types `/graphify`, invoke the Skill tool "
        "with `skill: \"graphify\"` before doing anything else.\n"
    )

def _remove_claude_skill_registration(project_dir: Path) -> None:
    claude_md = project_dir / "CLAUDE.md"
    if not claude_md.exists():
        return
    content = claude_md.read_text(encoding="utf-8")
    if "# graphify" not in content:
        return
    cleaned = re.sub(r"(?:\A|\n)# graphify\n.*?(?=\n# |\Z)", "", content, flags=re.DOTALL).rstrip()
    if cleaned:
        claude_md.write_text(cleaned + "\n", encoding="utf-8")
        print(f"  CLAUDE.md        ->  graphify skill registration removed from {claude_md}")
    else:
        claude_md.unlink()
        print(f"  CLAUDE.md        ->  deleted {claude_md}")

def claude_install(project_dir: Path | None = None) -> None:
    target = (project_dir or Path(".")) / "CLAUDE.md"

    if target.exists():
        content = target.read_text(encoding="utf-8")
        new_content = _replace_or_append_section(
            content, _CLAUDE_MD_MARKER, _CLAUDE_MD_SECTION
        )
    else:
        new_content = _CLAUDE_MD_SECTION

    if target.exists() and new_content == target.read_text(encoding="utf-8"):
        print(f"graphify already configured in {target.resolve()} (no change)")
    else:
        target.write_text(new_content, encoding="utf-8")
        print(f"graphify section written to {target.resolve()}")

    _install_claude_hook(project_dir or Path("."))

    print()
    print("Claude Code will now check the knowledge graph before answering")
    print("codebase questions and rebuild it after code changes.")

def _install_claude_hook(project_dir: Path) -> None:
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})
    pre_tool = hooks.setdefault("PreToolUse", [])

    hooks["PreToolUse"] = [h for h in pre_tool if not (h.get("matcher") in ("Glob|Grep", "Bash") and "graphify" in str(h))]
    hooks["PreToolUse"].append(_SETTINGS_HOOK)
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print(f"  .claude/settings.json  ->  PreToolUse hook registered")

def _uninstall_claude_hook(project_dir: Path) -> None:
    settings_path = project_dir / ".claude" / "settings.json"
    if not settings_path.exists():
        return
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    pre_tool = settings.get("hooks", {}).get("PreToolUse", [])
    filtered = [h for h in pre_tool if not (h.get("matcher") in ("Glob|Grep", "Bash") and "graphify" in str(h))]
    if len(filtered) == len(pre_tool):
        return
    settings["hooks"]["PreToolUse"] = filtered
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print(f"  .claude/settings.json  ->  PreToolUse hook removed")

def claude_uninstall(project_dir: Path | None = None) -> None:
    target = (project_dir or Path(".")) / "CLAUDE.md"

    if not target.exists():
        print("No CLAUDE.md found in current directory - nothing to do")
        return

    content = target.read_text(encoding="utf-8")
    if _CLAUDE_MD_MARKER not in content:
        print("graphify section not found in CLAUDE.md - nothing to do")
        return

    cleaned = re.sub(
        r"(?:\A|\n)## graphify\n.*?(?=\n## |\Z)",
        "",
        content,
        flags=re.DOTALL,
    ).rstrip()
    if cleaned:
        target.write_text(cleaned + "\n", encoding="utf-8")
        print(f"graphify section removed from {target.resolve()}")
    else:
        target.unlink()
        print(f"CLAUDE.md was empty after removal - deleted {target.resolve()}")

    _uninstall_claude_hook(project_dir or Path("."))
