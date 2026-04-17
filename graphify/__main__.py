"""graphify CLI - `graphify install` sets up the Claude Code skill."""
from __future__ import annotations
import json
import re
import shutil
import sys
from pathlib import Path

_SKILL_REGISTRATION = (
    "\n# graphify\n"
    "- **graphify** (`~/.claude/skills/graphify/SKILL.md`) "
    "- any input to knowledge graph. Trigger: `/graphify`\n"
    "When the user types `/graphify`, invoke the Skill tool "
    "with `skill: \"graphify\"` before doing anything else.\n"
)


def _bundled_skill() -> Path:
    """Path to the skill.md bundled with this package."""
    return Path(__file__).parent / "skill.md"


def install() -> None:
    skill_src = _bundled_skill()
    if not skill_src.exists():
        print("error: skill.md not found in package - reinstall graphify", file=sys.stderr)
        sys.exit(1)

    # Copy skill to ~/.claude/skills/graphify/SKILL.md
    skill_dst = Path.home() / ".claude" / "skills" / "graphify" / "SKILL.md"
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(skill_src, skill_dst)
    print(f"  skill installed  →  {skill_dst}")

    # Register in ~/.claude/CLAUDE.md
    claude_md = Path.home() / ".claude" / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text()
        if "graphify" in content:
            print(f"  CLAUDE.md        →  already registered (no change)")
        else:
            claude_md.write_text(content.rstrip() + _SKILL_REGISTRATION)
            print(f"  CLAUDE.md        →  skill registered in {claude_md}")
    else:
        claude_md.parent.mkdir(parents=True, exist_ok=True)
        claude_md.write_text(_SKILL_REGISTRATION.lstrip())
        print(f"  CLAUDE.md        →  created at {claude_md}")

    print()
    print("Done. Open Claude Code in any directory and type:")
    print()
    print("  /graphify .")
    print()


_CLAUDE_MD_SECTION = """\
## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
"""

_CLAUDE_MD_MARKER = "## graphify"


def claude_install(project_dir: Path | None = None) -> None:
    """Write the graphify section to the local CLAUDE.md."""
    target = (project_dir or Path(".")) / "CLAUDE.md"

    if target.exists():
        content = target.read_text()
        if _CLAUDE_MD_MARKER in content:
            print("graphify already configured in CLAUDE.md")
            return
        new_content = content.rstrip() + "\n\n" + _CLAUDE_MD_SECTION
    else:
        new_content = _CLAUDE_MD_SECTION

    target.write_text(new_content)
    print(f"graphify section written to {target.resolve()}")
    print()
    print("Claude Code will now check the knowledge graph before answering")
    print("codebase questions and rebuild it after code changes.")


_COPILOT_INSTRUCTIONS = """\
## graphify knowledge graph

This project has a graphify knowledge graph at graphify-out/.

- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files, run: python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"
"""

_COPILOT_MARKER = "## graphify knowledge graph"


def vscode_install(project_dir: Path | None = None) -> None:
    """Write graphify context to .github/copilot-instructions.md."""
    base = (project_dir or Path(".")).resolve()
    github_dir = base / ".github"
    github_dir.mkdir(exist_ok=True)
    target = github_dir / "copilot-instructions.md"

    if target.exists():
        content = target.read_text()
        if _COPILOT_MARKER in content:
            print("graphify already configured in .github/copilot-instructions.md")
            return
        target.write_text(content.rstrip() + "\n\n" + _COPILOT_INSTRUCTIONS)
    else:
        target.write_text(_COPILOT_INSTRUCTIONS)

    print(f"graphify instructions written to {target}")
    print()
    print("GitHub Copilot Chat will now use the knowledge graph when answering")
    print("questions about this codebase.")


def claude_uninstall(project_dir: Path | None = None) -> None:
    """Remove the graphify section from the local CLAUDE.md."""
    target = (project_dir or Path(".")) / "CLAUDE.md"

    if not target.exists():
        print("No CLAUDE.md found in current directory - nothing to do")
        return

    content = target.read_text()
    if _CLAUDE_MD_MARKER not in content:
        print("graphify section not found in CLAUDE.md - nothing to do")
        return

    # Remove the ## graphify section: from the marker to the next ## heading or EOF
    cleaned = re.sub(
        r"\n*## graphify\n.*?(?=\n## |\Z)",
        "",
        content,
        flags=re.DOTALL,
    ).rstrip()
    if cleaned:
        target.write_text(cleaned + "\n")
    else:
        target.unlink()
        print(f"CLAUDE.md was empty after removal - deleted {target.resolve()}")
        return

    print(f"graphify section removed from {target.resolve()}")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: graphify <command>")
        print()
        print("Commands:")
        print("  install                 copy skill to ~/.claude/skills/ and register in CLAUDE.md")
        print("  vscode install          write graphify context to .github/copilot-instructions.md")
        print("  benchmark [graph.json]  measure token reduction vs naive full-corpus approach")
        print("  hook install            install post-commit git hook (auto-rebuilds graph on commit)")
        print("  hook uninstall          remove post-commit git hook")
        print("  hook status             check if hook is installed")
        print("  claude install          write graphify section to local CLAUDE.md")
        print("  claude uninstall        remove graphify section from local CLAUDE.md")
        print()
        return

    cmd = sys.argv[1]
    if cmd == "install":
        install()
    elif cmd == "vscode":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            vscode_install()
        else:
            print("Usage: graphify vscode install", file=sys.stderr)
            sys.exit(1)
    elif cmd == "claude":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            claude_install()
        elif subcmd == "uninstall":
            claude_uninstall()
        else:
            print("Usage: graphify claude [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "hook":
        from graphify.hooks import install as hook_install, uninstall as hook_uninstall, status as hook_status
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            print(hook_install(Path(".")))
        elif subcmd == "uninstall":
            print(hook_uninstall(Path(".")))
        elif subcmd == "status":
            print(hook_status(Path(".")))
        else:
            print("Usage: graphify hook [install|uninstall|status]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "benchmark":
        from graphify.benchmark import run_benchmark, print_benchmark
        graph_path = sys.argv[2] if len(sys.argv) > 2 else "graphify-out/graph.json"
        # Try to load corpus_words from detect output
        corpus_words = None
        detect_path = Path(".graphify_detect.json")
        if detect_path.exists():
            try:
                detect_data = json.loads(detect_path.read_text())
                corpus_words = detect_data.get("total_words")
            except Exception:
                pass
        result = run_benchmark(graph_path, corpus_words=corpus_words)
        print_benchmark(result)
    else:
        print(f"error: unknown command '{cmd}'", file=sys.stderr)
        print("Run 'graphify --help' for usage.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
