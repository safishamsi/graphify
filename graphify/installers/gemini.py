from __future__ import annotations
import json
import re
from pathlib import Path

from graphify.installers.core import _replace_or_append_section, _copy_skill_file, _print_project_git_add_hint, _project_scope_root, _remove_skill_file

_GEMINI_MD_SECTION = """\
## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
"""

_GEMINI_MD_MARKER = "## graphify"

_GEMINI_HOOK = {
    "matcher": "read_file|list_directory",
    "hooks": [
        {
            "type": "command",
            "command": (
                'python -c "'
                "import sys,pathlib,json;"
                "e=pathlib.Path('graphify-out/graph.json').exists();"
                "d={'decision':'allow'};"
                "e and d.update({'additionalContext':'graphify: knowledge graph at graphify-out/. For focused questions, run `graphify query \"<question>\"` (scoped subgraph, usually much smaller than GRAPH_REPORT.md) instead of grepping raw files. Read GRAPH_REPORT.md only for broad architecture context.'});"
                "sys.stdout.write(json.dumps(d))"
                '"'
            ),
        }
    ],
}

def gemini_install(project_dir: Path | None = None, *, project: bool = False) -> None:
    project_dir = project_dir or Path(".")
    skill_dst = _copy_skill_file("gemini", project=project, project_dir=project_dir)

    target = project_dir / "GEMINI.md"

    if target.exists():
        content = target.read_text(encoding="utf-8")
        new_content = _replace_or_append_section(
            content, _GEMINI_MD_MARKER, _GEMINI_MD_SECTION
        )
    else:
        new_content = _GEMINI_MD_SECTION

    if target.exists() and new_content == target.read_text(encoding="utf-8"):
        print(f"graphify already configured in {target.resolve()} (no change)")
    else:
        target.write_text(new_content, encoding="utf-8")
        print(f"graphify section written to {target.resolve()}")

    _install_gemini_hook(project_dir)
    if project:
        _print_project_git_add_hint([_project_scope_root(skill_dst, project_dir), project_dir / "GEMINI.md", project_dir / ".gemini"])
    print()
    print("Gemini CLI will now check the knowledge graph before answering")
    print("codebase questions and rebuild it after code changes.")

def _install_gemini_hook(project_dir: Path) -> None:
    settings_path = project_dir / ".gemini" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    except json.JSONDecodeError:
        settings = {}
    before_tool = settings.setdefault("hooks", {}).setdefault("BeforeTool", [])
    settings["hooks"]["BeforeTool"] = [h for h in before_tool if "graphify" not in str(h)]
    settings["hooks"]["BeforeTool"].append(_GEMINI_HOOK)
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print("  .gemini/settings.json  ->  BeforeTool hook registered")

def _uninstall_gemini_hook(project_dir: Path) -> None:
    settings_path = project_dir / ".gemini" / "settings.json"
    if not settings_path.exists():
        return
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    before_tool = settings.get("hooks", {}).get("BeforeTool", [])
    filtered = [h for h in before_tool if "graphify" not in str(h)]
    if len(filtered) == len(before_tool):
        return
    settings["hooks"]["BeforeTool"] = filtered
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print("  .gemini/settings.json  ->  BeforeTool hook removed")

def gemini_uninstall(project_dir: Path | None = None, *, project: bool = False) -> None:
    project_dir = project_dir or Path(".")
    _remove_skill_file("gemini", project=project, project_dir=project_dir)

    target = project_dir / "GEMINI.md"
    if not target.exists():
        print("No GEMINI.md found in current directory - nothing to do")
        return
    content = target.read_text(encoding="utf-8")
    if _GEMINI_MD_MARKER not in content:
        print("graphify section not found in GEMINI.md - nothing to do")
        return
    cleaned = re.sub(r"\n*## graphify\n.*?(?=\n## |\Z)", "", content, flags=re.DOTALL).rstrip()
    if cleaned:
        target.write_text(cleaned + "\n", encoding="utf-8")
        print(f"graphify section removed from {target.resolve()}")
    else:
        target.unlink()
        print(f"GEMINI.md was empty after removal - deleted {target.resolve()}")
    _uninstall_gemini_hook(project_dir)
