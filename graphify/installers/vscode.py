from __future__ import annotations
import shutil
import re
from pathlib import Path
from graphify.installers.core import _replace_or_append_section, __version__

_VSCODE_INSTRUCTIONS_MARKER = "## graphify"
_VSCODE_INSTRUCTIONS_SECTION = """\
## graphify

For any question about this repo's architecture, structure, components, or how to add/modify/find
code, your first action should be `graphify query "<question>"` when `graphify-out/graph.json`
exists. Use `graphify path "<A>" "<B>"` for relationship questions and `graphify explain "<concept>"`
for focused-concept questions. These return a scoped subgraph, usually much smaller than the full
report or raw grep output.

Triggers: "how do I…", "where is…", "what does … do", "add/modify a <component>",
"explain the architecture", or anything that depends on how files or classes relate.

If `graphify-out/wiki/index.md` exists, use it for broad navigation. Read `graphify-out/GRAPH_REPORT.md`
only for broad architecture review or when query/path/explain do not surface enough context. Only read
source files when (a) modifying/debugging specific code, (b) the graph lacks the needed detail, or
(c) the graph is missing or stale.

Type `/graphify` in Copilot Chat to build or update the graph.
"""


def vscode_install(project_dir: Path | None = None) -> None:
    # We must go up two directories (installers -> graphify -> root)
    skill_src = Path(__file__).parent.parent / "skills" / "skill-vscode.md"
    if not skill_src.exists():
        skill_src = Path(__file__).parent.parent / "skills" / "skill-copilot.md"
    skill_dst = Path.home() / ".copilot" / "skills" / "graphify" / "SKILL.md"
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(skill_src, skill_dst)
    (skill_dst.parent / ".graphify_version").write_text(__version__, encoding="utf-8")
    print(f"  skill installed  ->  {skill_dst}")

    instructions = (project_dir or Path(".")) / ".github" / "copilot-instructions.md"
    instructions.parent.mkdir(parents=True, exist_ok=True)
    if instructions.exists():
        content = instructions.read_text(encoding="utf-8")
        new_content = _replace_or_append_section(
            content, _VSCODE_INSTRUCTIONS_MARKER, _VSCODE_INSTRUCTIONS_SECTION
        )
        if new_content == content:
            print(f"  {instructions}  ->  already configured (no change)")
        else:
            instructions.write_text(new_content, encoding="utf-8")
            print(f"  {instructions}  ->  graphify section {'updated' if _VSCODE_INSTRUCTIONS_MARKER in content else 'added'}")
    else:
        instructions.write_text(_VSCODE_INSTRUCTIONS_SECTION, encoding="utf-8")
        print(f"  {instructions}  ->  created")

    print()
    print("VS Code Copilot Chat configured. Type /graphify in the chat panel to build the graph.")
    print("Note: for GitHub Copilot CLI (terminal), use: graphify copilot install")


def vscode_uninstall(project_dir: Path | None = None) -> None:
    skill_dst = Path.home() / ".copilot" / "skills" / "graphify" / "SKILL.md"
    if skill_dst.exists():
        skill_dst.unlink()
        print(f"  skill removed    ->  {skill_dst}")
    version_file = skill_dst.parent / ".graphify_version"
    if version_file.exists():
        version_file.unlink()
    for d in (skill_dst.parent, skill_dst.parent.parent, skill_dst.parent.parent.parent):
        try:
            d.rmdir()
        except OSError:
            break

    instructions = (project_dir or Path(".")) / ".github" / "copilot-instructions.md"
    if not instructions.exists():
        return
    content = instructions.read_text(encoding="utf-8")
    if _VSCODE_INSTRUCTIONS_MARKER not in content:
        return
    cleaned = re.sub(r"\n*## graphify\n.*?(?=\n## |\Z)", "", content, flags=re.DOTALL).rstrip()
    if cleaned:
        instructions.write_text(cleaned + "\n", encoding="utf-8")
        print(f"  graphify section removed from {instructions}")
    else:
        instructions.unlink()
        print(f"  {instructions}  ->  deleted (was empty after removal)")
