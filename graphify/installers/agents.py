from __future__ import annotations
import re
from pathlib import Path
from graphify.installers.core import _replace_or_append_section

_AGENTS_MD_SECTION = """\
## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
"""

_AGENTS_MD_MARKER = "## graphify"

def _agents_install(project_dir: Path, platform: str) -> None:
    target = (project_dir or Path(".")) / "AGENTS.md"

    if target.exists():
        content = target.read_text(encoding="utf-8")
        new_content = _replace_or_append_section(
            content, _AGENTS_MD_MARKER, _AGENTS_MD_SECTION
        )
    else:
        new_content = _AGENTS_MD_SECTION

    if target.exists() and new_content == target.read_text(encoding="utf-8"):
        print(f"graphify already configured in {target.resolve()} (no change)")
    else:
        target.write_text(new_content, encoding="utf-8")
        print(f"graphify section written to {target.resolve()}")

    if platform == "codex":
        from graphify.installers.codex import _install_codex_hook
        _install_codex_hook(project_dir or Path("."))
    elif platform == "opencode":
        from graphify.installers.opencode import _install_opencode_plugin
        _install_opencode_plugin(project_dir or Path("."))

    print()
    print(f"{platform.capitalize()} will now check the knowledge graph before answering")
    print("codebase questions and rebuild it after code changes.")
    if platform not in ("codex", "opencode"):
        print()
        print("Note: unlike Claude Code, there is no PreToolUse hook equivalent for")
        print(f"{platform.capitalize()} — the AGENTS.md rules are the always-on mechanism.")


def _agents_uninstall(project_dir: Path, platform: str = "") -> None:
    target = (project_dir or Path(".")) / "AGENTS.md"

    if not target.exists():
        print("No AGENTS.md found in current directory - nothing to do")
        return

    content = target.read_text(encoding="utf-8")
    if _AGENTS_MD_MARKER not in content:
        print("graphify section not found in AGENTS.md - nothing to do")
        return

    cleaned = re.sub(
        r"\n*## graphify\n.*?(?=\n## |\Z)",
        "",
        content,
        flags=re.DOTALL,
    ).rstrip()
    if cleaned:
        target.write_text(cleaned + "\n", encoding="utf-8")
        print(f"graphify section removed from {target.resolve()}")
    else:
        target.unlink()
        print(f"AGENTS.md was empty after removal - deleted {target.resolve()}")

    if platform == "opencode":
        from graphify.installers.opencode import _uninstall_opencode_plugin
        _uninstall_opencode_plugin(project_dir or Path("."))
