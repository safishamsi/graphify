"""graphify CLI - `graphify install` sets up the Claude Code skill."""
from __future__ import annotations
import json
import platform
import re
import shutil
import sys
from pathlib import Path

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("graphifyy")
except Exception:
    __version__ = "unknown"


def _check_skill_version(skill_dst: Path) -> None:
    """Warn if the installed skill is from an older graphify version."""
    version_file = skill_dst.parent / ".graphify_version"
    if not version_file.exists():
        return
    installed = version_file.read_text(encoding="utf-8").strip()
    if installed != __version__:
        print(f"  warning: skill is from graphify {installed}, package is {__version__}. Run 'graphify install' to update.")


def _refresh_all_version_stamps() -> None:
    """After a successful install, update .graphify_version in all other known skill dirs.

    Prevents stale-version warnings from platforms that were installed previously
    but not explicitly re-installed during this upgrade.
    """
    for cfg in _PLATFORM_CONFIG.values():
        vf = Path.home() / cfg["skill_dst"]
        vf = vf.parent / ".graphify_version"
        if vf.exists():
            vf.write_text(__version__, encoding="utf-8")

_SETTINGS_HOOK = {
    "matcher": "Glob|Grep",
    "hooks": [
        {
            "type": "command",
            "command": (
                "[ -f graphify-out/graph.json ] && "
                r"""echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"graphify: Knowledge graph exists. Read graphify-out/GRAPH_REPORT.md for god nodes and community structure before searching raw files."}}' """
                "|| true"
            ),
        }
    ],
}

_SKILL_REGISTRATION = (
    "\n# graphify\n"
    "- **graphify** (`~/.claude/skills/graphify/SKILL.md`) "
    "- any input to knowledge graph. Trigger: `/graphify`\n"
    "When the user types `/graphify`, invoke the Skill tool "
    "with `skill: \"graphify\"` before doing anything else.\n"
)


_PLATFORM_CONFIG: dict[str, dict] = {
    "claude": {
        "skill_file": "skill.md",
        "skill_dst": Path(".claude") / "skills" / "graphify" / "SKILL.md",
        "claude_md": True,
    },
    "codex": {
        "skill_file": "skill-codex.md",
        "skill_dst": Path(".agents") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "opencode": {
        "skill_file": "skill-opencode.md",
        "skill_dst": Path(".config") / "opencode" / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "aider": {
        "skill_file": "skill-aider.md",
        "skill_dst": Path(".aider") / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "copilot": {
        "skill_file": "skill-copilot.md",
        "skill_dst": Path(".copilot") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "claw": {
        "skill_file": "skill-claw.md",
        "skill_dst": Path(".openclaw") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "droid": {
        "skill_file": "skill-droid.md",
        "skill_dst": Path(".factory") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "trae": {
        "skill_file": "skill-trae.md",
        "skill_dst": Path(".trae") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "trae-cn": {
        "skill_file": "skill-trae.md",
        "skill_dst": Path(".trae-cn") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "hermes": {
        "skill_file": "skill-claw.md",
        "skill_dst": Path(".hermes") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "kiro": {
        "skill_file": "skill-kiro.md",
        "skill_dst": Path(".kiro") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "antigravity": {
        "skill_file": "skill.md",
        "skill_dst": Path(".agent") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "windows": {
        "skill_file": "skill-windows.md",
        "skill_dst": Path(".claude") / "skills" / "graphify" / "SKILL.md",
        "claude_md": True,
    },
}


def install(platform: str = "claude") -> None:
    if platform == "gemini":
        gemini_install()
        return
    if platform == "cursor":
        _cursor_install(Path("."))
        return
    if platform not in _PLATFORM_CONFIG:
        print(
            f"error: unknown platform '{platform}'. Choose from: {', '.join(_PLATFORM_CONFIG)}, gemini, cursor",
            file=sys.stderr,
        )
        sys.exit(1)

    cfg = _PLATFORM_CONFIG[platform]
    skill_src = Path(__file__).parent / cfg["skill_file"]
    if not skill_src.exists():
        print(f"error: {cfg['skill_file']} not found in package - reinstall graphify", file=sys.stderr)
        sys.exit(1)

    skill_dst = Path.home() / cfg["skill_dst"]
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(skill_src, skill_dst)
    (skill_dst.parent / ".graphify_version").write_text(__version__, encoding="utf-8")
    print(f"  skill installed  ->  {skill_dst}")

    if cfg["claude_md"]:
        # Register in ~/.claude/CLAUDE.md (Claude Code only)
        claude_md = Path.home() / ".claude" / "CLAUDE.md"
        if claude_md.exists():
            content = claude_md.read_text(encoding="utf-8")
            if "graphify" in content:
                print(f"  CLAUDE.md        ->  already registered (no change)")
            else:
                claude_md.write_text(content.rstrip() + _SKILL_REGISTRATION, encoding="utf-8")
                print(f"  CLAUDE.md        ->  skill registered in {claude_md}")
        else:
            claude_md.parent.mkdir(parents=True, exist_ok=True)
            claude_md.write_text(_SKILL_REGISTRATION.lstrip(), encoding="utf-8")
            print(f"  CLAUDE.md        ->  created at {claude_md}")

    if platform == "opencode":
        _install_opencode_plugin(Path("."))

    # Refresh version stamps in all other previously-installed skill dirs so
    # stale-version warnings don't fire for platforms not explicitly re-installed.
    _refresh_all_version_stamps()

    print()
    print("Done. Open your AI coding assistant and type:")
    print()
    print("  /graphify .")
    print()


_CLAUDE_MD_SECTION = """\
## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
"""

_CLAUDE_MD_MARKER = "## graphify"

# AGENTS.md section for Codex, OpenCode, and OpenClaw.
# All three platforms read AGENTS.md in the project root for persistent instructions.
_AGENTS_MD_SECTION = """\
## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
"""

_AGENTS_MD_MARKER = "## graphify"

_GEMINI_MD_SECTION = """\
## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
"""

_GEMINI_MD_MARKER = "## graphify"

_GEMINI_HOOK = {
    "matcher": "read_file|list_directory",
    "hooks": [
        {
            "type": "command",
            "command": (
                "[ -f graphify-out/graph.json ] && "
                r"""echo '{"decision":"allow","additionalContext":"graphify: Knowledge graph exists. Read graphify-out/GRAPH_REPORT.md for god nodes and community structure before searching raw files."}' """
                r"""|| echo '{"decision":"allow"}'"""
            ),
        }
    ],
}


def gemini_install(project_dir: Path | None = None) -> None:
    """Copy skill file to ~/.gemini/skills/graphify/, write GEMINI.md section, and install BeforeTool hook."""
    # Copy skill file to ~/.gemini/skills/graphify/SKILL.md
    # On Windows, Gemini CLI prioritises ~/.agents/skills/ over ~/.gemini/skills/
    skill_src = Path(__file__).parent / "skill.md"
    if platform.system() == "Windows":
        skill_dst = Path.home() / ".agents" / "skills" / "graphify" / "SKILL.md"
    else:
        skill_dst = Path.home() / ".gemini" / "skills" / "graphify" / "SKILL.md"
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(skill_src, skill_dst)
    (skill_dst.parent / ".graphify_version").write_text(__version__, encoding="utf-8")
    print(f"  skill installed  ->  {skill_dst}")

    target = (project_dir or Path(".")) / "GEMINI.md"

    if target.exists():
        content = target.read_text(encoding="utf-8")
        if _GEMINI_MD_MARKER in content:
            print("graphify already configured in GEMINI.md")
        else:
            target.write_text(content.rstrip() + "\n\n" + _GEMINI_MD_SECTION, encoding="utf-8")
            print(f"graphify section written to {target.resolve()}")
    else:
        target.write_text(_GEMINI_MD_SECTION, encoding="utf-8")
        print(f"graphify section written to {target.resolve()}")

    _install_gemini_hook(project_dir or Path("."))
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


def gemini_uninstall(project_dir: Path | None = None) -> None:
    """Remove the graphify section from GEMINI.md, uninstall hook, and remove skill file."""
    # Remove skill file (mirror the install path detection)
    if platform.system() == "Windows":
        skill_dst = Path.home() / ".agents" / "skills" / "graphify" / "SKILL.md"
    else:
        skill_dst = Path.home() / ".gemini" / "skills" / "graphify" / "SKILL.md"
    if skill_dst.exists():
        skill_dst.unlink()
        print(f"  skill removed    ->  {skill_dst}")
    version_file = skill_dst.parent / ".graphify_version"
    if version_file.exists():
        version_file.unlink()
    for d in (skill_dst.parent, skill_dst.parent.parent):
        try:
            d.rmdir()
        except OSError:
            break

    target = (project_dir or Path(".")) / "GEMINI.md"
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
    _uninstall_gemini_hook(project_dir or Path("."))


_VSCODE_INSTRUCTIONS_MARKER = "## graphify"
_VSCODE_INSTRUCTIONS_SECTION = """\
## graphify

Before answering architecture or codebase questions, read `graphify-out/GRAPH_REPORT.md` if it exists.
If `graphify-out/wiki/index.md` exists, navigate it for deep questions.
Type `/graphify` in Copilot Chat to build or update the knowledge graph.
"""


def vscode_install(project_dir: Path | None = None) -> None:
    """Install graphify skill for VS Code Copilot Chat + write .github/copilot-instructions.md."""
    skill_src = Path(__file__).parent / "skill-vscode.md"
    if not skill_src.exists():
        skill_src = Path(__file__).parent / "skill-copilot.md"
    skill_dst = Path.home() / ".copilot" / "skills" / "graphify" / "SKILL.md"
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(skill_src, skill_dst)
    (skill_dst.parent / ".graphify_version").write_text(__version__, encoding="utf-8")
    print(f"  skill installed  ->  {skill_dst}")

    instructions = (project_dir or Path(".")) / ".github" / "copilot-instructions.md"
    instructions.parent.mkdir(parents=True, exist_ok=True)
    if instructions.exists():
        content = instructions.read_text(encoding="utf-8")
        if _VSCODE_INSTRUCTIONS_MARKER in content:
            print(f"  {instructions}  ->  already configured (no change)")
        else:
            instructions.write_text(content.rstrip() + "\n\n" + _VSCODE_INSTRUCTIONS_SECTION, encoding="utf-8")
            print(f"  {instructions}  ->  graphify section added")
    else:
        instructions.write_text(_VSCODE_INSTRUCTIONS_SECTION, encoding="utf-8")
        print(f"  {instructions}  ->  created")

    print()
    print("VS Code Copilot Chat configured. Type /graphify in the chat panel to build the graph.")
    print("Note: for GitHub Copilot CLI (terminal), use: graphify copilot install")


def vscode_uninstall(project_dir: Path | None = None) -> None:
    """Remove graphify VS Code Copilot Chat skill and .github/copilot-instructions.md section."""
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


_ANTIGRAVITY_RULES_PATH = Path(".agent") / "rules" / "graphify.md"
_ANTIGRAVITY_WORKFLOW_PATH = Path(".agent") / "workflows" / "graphify.md"

_ANTIGRAVITY_RULES = """\
## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- If the graphify MCP server is active, utilize tools like `query_graph`, `get_node`, and `shortest_path` for precise architecture navigation instead of falling back to `grep`
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
"""

_ANTIGRAVITY_WORKFLOW = """\
# Workflow: graphify
**Command:** /graphify
**Description:** Turn any folder of files into a navigable knowledge graph

## Steps
Follow the graphify skill installed at ~/.agent/skills/graphify/SKILL.md to run the full pipeline.

If no path argument is given, use `.` (current directory).
"""


_KIRO_STEERING = """\
---
inclusion: always
---

graphify: A knowledge graph of this project lives in `graphify-out/`. \
If `graphify-out/GRAPH_REPORT.md` exists, read it before answering architecture questions, \
tracing dependencies, or searching files — it contains god nodes, community structure, \
and surprising connections the graph found. Navigate by graph structure instead of grepping raw files.
"""

_KIRO_STEERING_MARKER = "graphify: A knowledge graph of this project"


def _kiro_install(project_dir: Path) -> None:
    """Write graphify skill + steering file for Kiro IDE/CLI."""
    project_dir = project_dir or Path(".")

    # Skill file → .kiro/skills/graphify/SKILL.md
    skill_src = Path(__file__).parent / "skill-kiro.md"
    skill_dst = project_dir / ".kiro" / "skills" / "graphify" / "SKILL.md"
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    skill_dst.write_text(skill_src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"  {skill_dst.relative_to(project_dir)}  ->  /graphify skill")

    # Steering file → .kiro/steering/graphify.md (always-on)
    steering_dir = project_dir / ".kiro" / "steering"
    steering_dir.mkdir(parents=True, exist_ok=True)
    steering_dst = steering_dir / "graphify.md"
    if steering_dst.exists() and _KIRO_STEERING_MARKER in steering_dst.read_text(encoding="utf-8"):
        print(f"  .kiro/steering/graphify.md  ->  already configured")
    else:
        steering_dst.write_text(_KIRO_STEERING, encoding="utf-8")
        print(f"  .kiro/steering/graphify.md  ->  always-on steering written")

    print()
    print("Kiro will now read the knowledge graph before every conversation.")
    print("Use /graphify to build or update the graph.")


def _kiro_uninstall(project_dir: Path) -> None:
    """Remove graphify skill + steering file for Kiro."""
    project_dir = project_dir or Path(".")
    removed = []

    skill_dst = project_dir / ".kiro" / "skills" / "graphify" / "SKILL.md"
    if skill_dst.exists():
        skill_dst.unlink()
        removed.append(str(skill_dst.relative_to(project_dir)))
        # Remove parent dir if empty
        try:
            skill_dst.parent.rmdir()
        except OSError:
            pass

    steering_dst = project_dir / ".kiro" / "steering" / "graphify.md"
    if steering_dst.exists():
        steering_dst.unlink()
        removed.append(str(steering_dst.relative_to(project_dir)))

    print("Removed: " + (", ".join(removed) if removed else "nothing to remove"))


def _antigravity_install(project_dir: Path) -> None:
    """Install graphify for Google Antigravity: skill + .agent/rules + .agent/workflows."""
    # 1. Copy skill file to ~/.agent/skills/graphify/SKILL.md
    install(platform="antigravity")

    # 1.5. Inject YAML frontmatter for native Antigravity tool discovery
    skill_dst = Path.home() / _PLATFORM_CONFIG["antigravity"]["skill_dst"]
    if skill_dst.exists():
        content = skill_dst.read_text(encoding="utf-8")
        if not content.startswith("---\n"):
            frontmatter = "---\nname: graphify-manager\ndescription: Rebuild the code graph or perform manual CLI queries when MCP server is offline.\n---\n\n"
            skill_dst.write_text(frontmatter + content, encoding="utf-8")

    # 2. Write .agent/rules/graphify.md
    rules_path = project_dir / _ANTIGRAVITY_RULES_PATH
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    if rules_path.exists():
        print(f"graphify rule already exists at {rules_path} (no change)")
    else:
        rules_path.write_text(_ANTIGRAVITY_RULES, encoding="utf-8")
        print(f"graphify rule written to {rules_path.resolve()}")

    # 3. Write .agent/workflows/graphify.md
    wf_path = project_dir / _ANTIGRAVITY_WORKFLOW_PATH
    wf_path.parent.mkdir(parents=True, exist_ok=True)
    if wf_path.exists():
        print(f"graphify workflow already exists at {wf_path} (no change)")
    else:
        wf_path.write_text(_ANTIGRAVITY_WORKFLOW, encoding="utf-8")
        print(f"graphify workflow written to {wf_path.resolve()}")

    print()
    print("Antigravity will now check the knowledge graph before answering")
    print("codebase questions. Run /graphify first to build the graph.")
    print()
    print("To enable full MCP architecture navigation, add this to ~/.gemini/antigravity/mcp_config.json:")
    print('  "graphify": {')
    print('    "command": "uv",')
    print('    "args": ["run", "--with", "graphifyy", "--with", "mcp", "-m", "graphify.serve", "${workspace.path}/graphify-out/graph.json"]')
    print('  }')


def _antigravity_uninstall(project_dir: Path) -> None:
    """Remove graphify Antigravity rules, workflow, and skill files."""
    # Remove rules file
    rules_path = project_dir / _ANTIGRAVITY_RULES_PATH
    if rules_path.exists():
        rules_path.unlink()
        print(f"graphify rule removed from {rules_path.resolve()}")
    else:
        print("No graphify Antigravity rule found - nothing to do")

    # Remove workflow file
    wf_path = project_dir / _ANTIGRAVITY_WORKFLOW_PATH
    if wf_path.exists():
        wf_path.unlink()
        print(f"graphify workflow removed from {wf_path.resolve()}")

    # Remove skill file
    skill_dst = Path.home() / _PLATFORM_CONFIG["antigravity"]["skill_dst"]
    if skill_dst.exists():
        skill_dst.unlink()
        print(f"graphify skill removed from {skill_dst}")
    version_file = skill_dst.parent / ".graphify_version"
    if version_file.exists():
        version_file.unlink()
    for d in (skill_dst.parent, skill_dst.parent.parent, skill_dst.parent.parent.parent):
        try:
            d.rmdir()
        except OSError:
            break


_CURSOR_RULE_PATH = Path(".cursor") / "rules" / "graphify.mdc"
_CURSOR_RULE = """\
---
description: graphify knowledge graph context
alwaysApply: true
---

This project has a graphify knowledge graph at graphify-out/.

- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
"""


def _cursor_install(project_dir: Path) -> None:
    """Write .cursor/rules/graphify.mdc with alwaysApply: true."""
    rule_path = (project_dir or Path(".")) / _CURSOR_RULE_PATH
    rule_path.parent.mkdir(parents=True, exist_ok=True)
    if rule_path.exists():
        print(f"graphify rule already exists at {rule_path} (no change)")
        return
    rule_path.write_text(_CURSOR_RULE, encoding="utf-8")
    print(f"graphify rule written to {rule_path.resolve()}")
    print()
    print("Cursor will now always include the knowledge graph context.")
    print("Run /graphify . first to build the graph if you haven't already.")


def _cursor_uninstall(project_dir: Path) -> None:
    """Remove .cursor/rules/graphify.mdc."""
    rule_path = (project_dir or Path(".")) / _CURSOR_RULE_PATH
    if not rule_path.exists():
        print("No graphify Cursor rule found - nothing to do")
        return
    rule_path.unlink()
    print(f"graphify Cursor rule removed from {rule_path.resolve()}")


# OpenCode tool.execute.before plugin — fires before every tool call.
# Injects a graph reminder into bash command output when graph.json exists.
_OPENCODE_PLUGIN_JS = """\
// graphify OpenCode plugin
// Injects a knowledge graph reminder before bash tool calls when the graph exists.
import { existsSync } from "fs";
import { join } from "path";

export const GraphifyPlugin = async ({ directory }) => {
  let reminded = false;

  return {
    "tool.execute.before": async (input, output) => {
      if (reminded) return;
      if (!existsSync(join(directory, "graphify-out", "graph.json"))) return;

      if (input.tool === "bash") {
        output.args.command =
          'echo "[graphify] Knowledge graph available. Read graphify-out/GRAPH_REPORT.md for god nodes and architecture context before searching files." && ' +
          output.args.command;
        reminded = true;
      }
    },
  };
};
"""

_OPENCODE_PLUGIN_PATH = Path(".opencode") / "plugins" / "graphify.js"
_OPENCODE_CONFIG_PATH = Path("opencode.json")


def _install_opencode_plugin(project_dir: Path) -> None:
    """Write graphify.js plugin and register it in opencode.json."""
    plugin_file = project_dir / _OPENCODE_PLUGIN_PATH
    plugin_file.parent.mkdir(parents=True, exist_ok=True)
    plugin_file.write_text(_OPENCODE_PLUGIN_JS, encoding="utf-8")
    print(f"  {_OPENCODE_PLUGIN_PATH}  ->  tool.execute.before hook written")

    config_file = project_dir / _OPENCODE_CONFIG_PATH
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            config = {}
    else:
        config = {}

    plugins = config.setdefault("plugin", [])
    entry = _OPENCODE_PLUGIN_PATH.as_posix()
    if entry not in plugins:
        plugins.append(entry)
        config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print(f"  {_OPENCODE_CONFIG_PATH}  ->  plugin registered")
    else:
        print(f"  {_OPENCODE_CONFIG_PATH}  ->  plugin already registered (no change)")


def _uninstall_opencode_plugin(project_dir: Path) -> None:
    """Remove graphify.js plugin and deregister from opencode.json."""
    plugin_file = project_dir / _OPENCODE_PLUGIN_PATH
    if plugin_file.exists():
        plugin_file.unlink()
        print(f"  {_OPENCODE_PLUGIN_PATH}  ->  removed")

    config_file = project_dir / _OPENCODE_CONFIG_PATH
    if not config_file.exists():
        return
    try:
        config = json.loads(config_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    plugins = config.get("plugin", [])
    entry = _OPENCODE_PLUGIN_PATH.as_posix()
    if entry in plugins:
        plugins.remove(entry)
        if not plugins:
            config.pop("plugin")
        config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print(f"  {_OPENCODE_CONFIG_PATH}  ->  plugin deregistered")


_CODEX_HOOK = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            "[ -f graphify-out/graph.json ] && "
                            r"""echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"graphify: Knowledge graph exists. Read graphify-out/GRAPH_REPORT.md for god nodes and community structure before searching raw files."}}' """
                            "|| true"
                        ),
                    }
                ],
            }
        ]
    }
}


def _install_codex_hook(project_dir: Path) -> None:
    """Add graphify PreToolUse hook to .codex/hooks.json."""
    hooks_path = project_dir / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)

    if hooks_path.exists():
        try:
            existing = json.loads(hooks_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    else:
        existing = {}

    pre_tool = existing.setdefault("hooks", {}).setdefault("PreToolUse", [])
    existing["hooks"]["PreToolUse"] = [h for h in pre_tool if "graphify" not in str(h)]
    existing["hooks"]["PreToolUse"].extend(_CODEX_HOOK["hooks"]["PreToolUse"])
    hooks_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"  .codex/hooks.json  ->  PreToolUse hook registered")


def _uninstall_codex_hook(project_dir: Path) -> None:
    """Remove graphify PreToolUse hook from .codex/hooks.json."""
    hooks_path = project_dir / ".codex" / "hooks.json"
    if not hooks_path.exists():
        return
    try:
        existing = json.loads(hooks_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    pre_tool = existing.get("hooks", {}).get("PreToolUse", [])
    filtered = [h for h in pre_tool if "graphify" not in str(h)]
    existing["hooks"]["PreToolUse"] = filtered
    hooks_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"  .codex/hooks.json  ->  PreToolUse hook removed")


def _agents_install(project_dir: Path, platform: str) -> None:
    """Write the graphify section to the local AGENTS.md (Codex/OpenCode/OpenClaw)."""
    target = (project_dir or Path(".")) / "AGENTS.md"

    if target.exists():
        content = target.read_text(encoding="utf-8")
        if _AGENTS_MD_MARKER in content:
            print(f"graphify already configured in AGENTS.md")
        else:
            target.write_text(content.rstrip() + "\n\n" + _AGENTS_MD_SECTION, encoding="utf-8")
            print(f"graphify section written to {target.resolve()}")
    else:
        target.write_text(_AGENTS_MD_SECTION, encoding="utf-8")
        print(f"graphify section written to {target.resolve()}")

    if platform == "codex":
        _install_codex_hook(project_dir or Path("."))
    elif platform == "opencode":
        _install_opencode_plugin(project_dir or Path("."))

    print()
    print(f"{platform.capitalize()} will now check the knowledge graph before answering")
    print("codebase questions and rebuild it after code changes.")
    if platform not in ("codex", "opencode"):
        print()
        print("Note: unlike Claude Code, there is no PreToolUse hook equivalent for")
        print(f"{platform.capitalize()} — the AGENTS.md rules are the always-on mechanism.")


def _agents_uninstall(project_dir: Path, platform: str = "") -> None:
    """Remove the graphify section from the local AGENTS.md."""
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
        _uninstall_opencode_plugin(project_dir or Path("."))


def claude_install(project_dir: Path | None = None) -> None:
    """Write the graphify section to the local CLAUDE.md."""
    target = (project_dir or Path(".")) / "CLAUDE.md"

    if target.exists():
        content = target.read_text(encoding="utf-8")
        if _CLAUDE_MD_MARKER in content:
            print("graphify already configured in CLAUDE.md")
            return
        new_content = content.rstrip() + "\n\n" + _CLAUDE_MD_SECTION
    else:
        new_content = _CLAUDE_MD_SECTION

    target.write_text(new_content, encoding="utf-8")
    print(f"graphify section written to {target.resolve()}")

    # Also write Claude Code PreToolUse hook to .claude/settings.json
    _install_claude_hook(project_dir or Path("."))

    print()
    print("Claude Code will now check the knowledge graph before answering")
    print("codebase questions and rebuild it after code changes.")


def _install_claude_hook(project_dir: Path) -> None:
    """Add graphify PreToolUse hook to .claude/settings.json."""
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

    hooks["PreToolUse"] = [h for h in pre_tool if not (h.get("matcher") == "Glob|Grep" and "graphify" in str(h))]
    hooks["PreToolUse"].append(_SETTINGS_HOOK)
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print(f"  .claude/settings.json  ->  PreToolUse hook registered")


def _uninstall_claude_hook(project_dir: Path) -> None:
    """Remove graphify PreToolUse hook from .claude/settings.json."""
    settings_path = project_dir / ".claude" / "settings.json"
    if not settings_path.exists():
        return
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    pre_tool = settings.get("hooks", {}).get("PreToolUse", [])
    filtered = [h for h in pre_tool if not (h.get("matcher") == "Glob|Grep" and "graphify" in str(h))]
    if len(filtered) == len(pre_tool):
        return
    settings["hooks"]["PreToolUse"] = filtered
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print(f"  .claude/settings.json  ->  PreToolUse hook removed")


def claude_uninstall(project_dir: Path | None = None) -> None:
    """Remove the graphify section from the local CLAUDE.md."""
    target = (project_dir or Path(".")) / "CLAUDE.md"

    if not target.exists():
        print("No CLAUDE.md found in current directory - nothing to do")
        return

    content = target.read_text(encoding="utf-8")
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
        target.write_text(cleaned + "\n", encoding="utf-8")
        print(f"graphify section removed from {target.resolve()}")
    else:
        target.unlink()
        print(f"CLAUDE.md was empty after removal - deleted {target.resolve()}")

    _uninstall_claude_hook(project_dir or Path("."))


def main() -> None:
    # Check all known skill install locations for a stale version stamp.
    # Skip during install/uninstall (hook writes trigger a fresh check anyway).
    # Deduplicate paths so platforms sharing the same install dir don't warn twice.
    if not any(arg in ("install", "uninstall") for arg in sys.argv):
        for skill_dst in {Path.home() / cfg["skill_dst"] for cfg in _PLATFORM_CONFIG.values()}:
            _check_skill_version(skill_dst)

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: graphify <command>")
        print()
        print("Commands:")
        print("  install [--platform P]  copy skill to platform config dir (claude|windows|codex|opencode|aider|claw|droid|trae|trae-cn|gemini|cursor|antigravity|hermes|kiro)")
        print("  path \"A\" \"B\"            shortest path between two nodes in graph.json")
        print("    --graph <path>          path to graph.json (default graphify-out/graph.json)")
        print("  explain \"X\"             plain-language explanation of a node and its neighbors")
        print("    --graph <path>          path to graph.json (default graphify-out/graph.json)")
        print("  add <url>               fetch a URL and save it to ./raw, then update the graph")
        print("    --author \"Name\"         tag the author of the content")
        print("    --contributor \"Name\"    tag who added it to the corpus")
        print("    --dir <path>            target directory (default: ./raw)")
        print("  watch <path>            watch a folder and rebuild the graph on code changes")
        print("  update <path>           re-extract code files and update the graph (no LLM needed)")
        print("  cluster-only <path>     rerun clustering on an existing graph.json and regenerate report")
        print("  query \"<question>\"       BFS traversal of graph.json for a question")
        print("    --dfs                   use depth-first instead of breadth-first")
        print("    --budget N              cap output at N tokens (default 2000)")
        print("    --graph <path>          path to graph.json (default graphify-out/graph.json)")
        print("  save-result             save a Q&A result to graphify-out/memory/ for graph feedback loop")
        print("    --question Q            the question asked")
        print("    --answer A              the answer to save")
        print("    --type T                query type: query|path_query|explain (default: query)")
        print("    --nodes N1 N2 ...       source node labels cited in the answer")
        print("    --memory-dir DIR        memory directory (default: graphify-out/memory)")
        print("  edges list              list persistent cross-file edges")
        print("  edges add S R T         add cross-file edge (source relation target)")
        print("    --note \"...\"            optional description")
        print("    --score N               confidence score (default 0.9)")
        print("  edges remove S R T      remove a cross-file edge")
        print("  edges prune             remove edges where nodes no longer exist")
        print("  benchmark [graph.json]  measure token reduction vs naive full-corpus approach")
        print("  hook install            install post-commit/post-checkout git hooks (all platforms)")
        print("  hook uninstall          remove git hooks")
        print("  hook status             check if git hooks are installed")
        print("  gemini install          write GEMINI.md section + BeforeTool hook (Gemini CLI)")
        print("  gemini uninstall        remove GEMINI.md section + BeforeTool hook")
        print("  cursor install          write .cursor/rules/graphify.mdc (Cursor)")
        print("  cursor uninstall        remove .cursor/rules/graphify.mdc")
        print("  claude install          write graphify section to CLAUDE.md + PreToolUse hook (Claude Code)")
        print("  claude uninstall        remove graphify section from CLAUDE.md + PreToolUse hook")
        print("  codex install           write graphify section to AGENTS.md (Codex)")
        print("  codex uninstall         remove graphify section from AGENTS.md")
        print("  opencode install        write graphify section to AGENTS.md + tool.execute.before plugin (OpenCode)")
        print("  opencode uninstall      remove graphify section from AGENTS.md + plugin")
        print("  aider install           write graphify section to AGENTS.md (Aider)")
        print("  aider uninstall         remove graphify section from AGENTS.md")
        print("  copilot install         copy graphify skill to ~/.copilot/skills (GitHub Copilot CLI)")
        print("  copilot uninstall       remove graphify skill from ~/.copilot/skills")
        print("  vscode install          configure VS Code Copilot Chat (skill + .github/copilot-instructions.md)")
        print("  vscode uninstall        remove VS Code Copilot Chat configuration")
        print("  claw install            write graphify section to AGENTS.md (OpenClaw)")
        print("  claw uninstall          remove graphify section from AGENTS.md")
        print("  droid install           write graphify section to AGENTS.md (Factory Droid)")
        print("  droid uninstall        remove graphify section from AGENTS.md")
        print("  trae install            write graphify section to AGENTS.md (Trae)")
        print("  trae uninstall         remove graphify section from AGENTS.md")
        print("  trae-cn install         write graphify section to AGENTS.md (Trae CN)")
        print("  trae-cn uninstall      remove graphify section from AGENTS.md")
        print("  antigravity install     write .agent/rules + .agent/workflows + skill (Google Antigravity)")
        print("  antigravity uninstall   remove .agent/rules, .agent/workflows, and skill")
        print("  hermes install          write skill to ~/.hermes/skills/graphify/ (Hermes)")
        print("  hermes uninstall        remove skill from ~/.hermes/skills/graphify/")
        print("  kiro install            write skill to .kiro/skills/graphify/ + steering file (Kiro IDE/CLI)")
        print("  kiro uninstall          remove skill + steering file")
        print()
        return

    cmd = sys.argv[1]
    if cmd == "install":
        # Default to windows platform on Windows, claude elsewhere
        default_platform = "windows" if platform.system() == "Windows" else "claude"
        chosen_platform = default_platform
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            if args[i].startswith("--platform="):
                chosen_platform = args[i].split("=", 1)[1]
                i += 1
            elif args[i] == "--platform" and i + 1 < len(args):
                chosen_platform = args[i + 1]
                i += 2
            else:
                i += 1
        install(platform=chosen_platform)
    elif cmd == "claude":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            claude_install()
        elif subcmd == "uninstall":
            claude_uninstall()
        else:
            print("Usage: graphify claude [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "gemini":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            gemini_install()
        elif subcmd == "uninstall":
            gemini_uninstall()
        else:
            print("Usage: graphify gemini [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "cursor":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            _cursor_install(Path("."))
        elif subcmd == "uninstall":
            _cursor_uninstall(Path("."))
        else:
            print("Usage: graphify cursor [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "vscode":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            vscode_install()
        elif subcmd == "uninstall":
            vscode_uninstall()
        else:
            print("Usage: graphify vscode [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "copilot":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            install(platform="copilot")
        elif subcmd == "uninstall":
            skill_dst = Path.home() / _PLATFORM_CONFIG["copilot"]["skill_dst"]
            removed = []
            if skill_dst.exists():
                skill_dst.unlink()
                removed.append(f"skill removed: {skill_dst}")
            version_file = skill_dst.parent / ".graphify_version"
            if version_file.exists():
                version_file.unlink()
            for d in (skill_dst.parent, skill_dst.parent.parent, skill_dst.parent.parent.parent):
                try:
                    d.rmdir()
                except OSError:
                    break
            print("; ".join(removed) if removed else "nothing to remove")
        else:
            print("Usage: graphify copilot [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "kiro":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            _kiro_install(Path("."))
        elif subcmd == "uninstall":
            _kiro_uninstall(Path("."))
        else:
            print("Usage: graphify kiro [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd in ("aider", "codex", "opencode", "claw", "droid", "trae", "trae-cn", "hermes"):
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            _agents_install(Path("."), cmd)
        elif subcmd == "uninstall":
            _agents_uninstall(Path("."), platform=cmd)
            if cmd == "codex":
                _uninstall_codex_hook(Path("."))
        else:
            print(f"Usage: graphify {cmd} [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "antigravity":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            _antigravity_install(Path("."))
        elif subcmd == "uninstall":
            _antigravity_uninstall(Path("."))
        else:
            print("Usage: graphify antigravity [install|uninstall]", file=sys.stderr)
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
    elif cmd == "query":
        if len(sys.argv) < 3:
            print("Usage: graphify query \"<question>\" [--dfs] [--budget N] [--graph path]", file=sys.stderr)
            sys.exit(1)
        from graphify.serve import _score_nodes, _bfs, _dfs, _subgraph_to_text
        from graphify.security import sanitize_label
        from networkx.readwrite import json_graph
        question = sys.argv[2]
        use_dfs = "--dfs" in sys.argv
        budget = 2000
        graph_path = "graphify-out/graph.json"
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == "--budget" and i + 1 < len(args):
                try:
                    budget = int(args[i + 1])
                except ValueError:
                    print(f"error: --budget must be an integer", file=sys.stderr)
                    sys.exit(1)
                i += 2
            elif args[i].startswith("--budget="):
                try:
                    budget = int(args[i].split("=", 1)[1])
                except ValueError:
                    print(f"error: --budget must be an integer", file=sys.stderr)
                    sys.exit(1)
                i += 1
            elif args[i] == "--graph" and i + 1 < len(args):
                graph_path = args[i + 1]; i += 2
            else:
                i += 1
        gp = Path(graph_path).resolve()
        if not gp.exists():
            print(f"error: graph file not found: {gp}", file=sys.stderr)
            sys.exit(1)
        if not gp.suffix == ".json":
            print(f"error: graph file must be a .json file", file=sys.stderr)
            sys.exit(1)
        try:
            import json as _json
            import networkx as _nx
            _raw = _json.loads(gp.read_text(encoding="utf-8"))
            try:
                G = json_graph.node_link_graph(_raw, edges="links")
            except TypeError:
                G = json_graph.node_link_graph(_raw)
        except Exception as exc:
            print(f"error: could not load graph: {exc}", file=sys.stderr)
            sys.exit(1)
        terms = [t.lower() for t in question.split() if len(t) > 2]
        scored = _score_nodes(G, terms)
        if not scored:
            print("No matching nodes found.")
            sys.exit(0)
        start = [nid for _, nid in scored[:5]]
        nodes, edges = (_dfs if use_dfs else _bfs)(G, start, depth=2)
        print(_subgraph_to_text(G, nodes, edges, token_budget=budget))
    elif cmd == "save-result":
        # graphify save-result --question Q --answer A --type T [--nodes N1 N2 ...]
        import argparse as _ap
        p = _ap.ArgumentParser(prog="graphify save-result")
        p.add_argument("--question", required=True)
        p.add_argument("--answer", required=True)
        p.add_argument("--type", dest="query_type", default="query")
        p.add_argument("--nodes", nargs="*", default=[])
        p.add_argument("--memory-dir", default="graphify-out/memory")
        opts = p.parse_args(sys.argv[2:])
        from graphify.ingest import save_query_result as _sqr
        out = _sqr(
            question=opts.question,
            answer=opts.answer,
            memory_dir=Path(opts.memory_dir),
            query_type=opts.query_type,
            source_nodes=opts.nodes or None,
        )
        print(f"Saved to {out}")
    elif cmd == "path":
        if len(sys.argv) < 4:
            print("Usage: graphify path \"<source>\" \"<target>\" [--graph path]", file=sys.stderr)
            sys.exit(1)
        from graphify.serve import _score_nodes
        from networkx.readwrite import json_graph
        import networkx as _nx
        source_label = sys.argv[2]
        target_label = sys.argv[3]
        graph_path = "graphify-out/graph.json"
        args = sys.argv[4:]
        for i, a in enumerate(args):
            if a == "--graph" and i + 1 < len(args):
                graph_path = args[i + 1]
        gp = Path(graph_path).resolve()
        if not gp.exists():
            print(f"error: graph file not found: {gp}", file=sys.stderr)
            sys.exit(1)
        _raw = json.loads(gp.read_text(encoding="utf-8"))
        try:
            G = json_graph.node_link_graph(_raw, edges="links")
        except TypeError:
            G = json_graph.node_link_graph(_raw)
        src_scored = _score_nodes(G, [t.lower() for t in source_label.split()])
        tgt_scored = _score_nodes(G, [t.lower() for t in target_label.split()])
        if not src_scored:
            print(f"No node matching '{source_label}' found.", file=sys.stderr)
            sys.exit(1)
        if not tgt_scored:
            print(f"No node matching '{target_label}' found.", file=sys.stderr)
            sys.exit(1)
        src_nid, tgt_nid = src_scored[0][1], tgt_scored[0][1]
        try:
            path_nodes = _nx.shortest_path(G, src_nid, tgt_nid)
        except (_nx.NetworkXNoPath, _nx.NodeNotFound):
            print(f"No path found between '{source_label}' and '{target_label}'.")
            sys.exit(0)
        hops = len(path_nodes) - 1
        segments = []
        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            edata = G.edges[u, v]
            rel = edata.get("relation", "")
            conf = edata.get("confidence", "")
            conf_str = f" [{conf}]" if conf else ""
            if i == 0:
                segments.append(G.nodes[u].get("label", u))
            segments.append(f"--{rel}{conf_str}--> {G.nodes[v].get('label', v)}")
        print(f"Shortest path ({hops} hops):\n  " + " ".join(segments))

    elif cmd == "explain":
        if len(sys.argv) < 3:
            print("Usage: graphify explain \"<node>\" [--graph path]", file=sys.stderr)
            sys.exit(1)
        from graphify.serve import _find_node
        from networkx.readwrite import json_graph
        label = sys.argv[2]
        graph_path = "graphify-out/graph.json"
        args = sys.argv[3:]
        for i, a in enumerate(args):
            if a == "--graph" and i + 1 < len(args):
                graph_path = args[i + 1]
        gp = Path(graph_path).resolve()
        if not gp.exists():
            print(f"error: graph file not found: {gp}", file=sys.stderr)
            sys.exit(1)
        _raw = json.loads(gp.read_text(encoding="utf-8"))
        try:
            G = json_graph.node_link_graph(_raw, edges="links")
        except TypeError:
            G = json_graph.node_link_graph(_raw)
        matches = _find_node(G, label)
        if not matches:
            print(f"No node matching '{label}' found.")
            sys.exit(0)
        nid = matches[0]
        d = G.nodes[nid]
        print(f"Node: {d.get('label', nid)}")
        print(f"  ID:        {nid}")
        print(f"  Source:    {d.get('source_file', '')} {d.get('source_location', '')}".rstrip())
        print(f"  Type:      {d.get('file_type', '')}")
        print(f"  Community: {d.get('community', '')}")
        print(f"  Degree:    {G.degree(nid)}")
        neighbors = list(G.neighbors(nid))
        if neighbors:
            print(f"\nConnections ({len(neighbors)}):")
            for nb in sorted(neighbors, key=lambda n: G.degree(n), reverse=True)[:20]:
                edata = G.edges[nid, nb]
                rel = edata.get("relation", "")
                conf = edata.get("confidence", "")
                print(f"  --> {G.nodes[nb].get('label', nb)} [{rel}] [{conf}]")
            if len(neighbors) > 20:
                print(f"  ... and {len(neighbors) - 20} more")

    elif cmd == "add":
        if len(sys.argv) < 3:
            print("Usage: graphify add <url> [--author Name] [--contributor Name] [--dir ./raw]", file=sys.stderr)
            sys.exit(1)
        from graphify.ingest import ingest as _ingest
        url = sys.argv[2]
        author: str | None = None
        contributor: str | None = None
        target_dir = Path("raw")
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == "--author" and i + 1 < len(args):
                author = args[i + 1]; i += 2
            elif args[i] == "--contributor" and i + 1 < len(args):
                contributor = args[i + 1]; i += 2
            elif args[i] == "--dir" and i + 1 < len(args):
                target_dir = Path(args[i + 1]); i += 2
            else:
                i += 1
        try:
            saved = _ingest(url, target_dir, author=author, contributor=contributor)
            print(f"Saved to {saved}")
            print("Run /graphify --update in your AI assistant to update the graph.")
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)

    elif cmd == "watch":
        watch_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
        if not watch_path.exists():
            print(f"error: path not found: {watch_path}", file=sys.stderr)
            sys.exit(1)
        from graphify.watch import watch as _watch
        try:
            _watch(watch_path)
        except ImportError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)

    elif cmd == "cluster-only":
        watch_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
        graph_json = watch_path / "graphify-out" / "graph.json"
        if not graph_json.exists():
            print(f"error: no graph found at {graph_json} — run /graphify first", file=sys.stderr)
            sys.exit(1)
        from networkx.readwrite import json_graph as _jg
        from graphify.build import build_from_json
        from graphify.cluster import cluster, score_all
        from graphify.analyze import god_nodes, surprising_connections, suggest_questions
        from graphify.report import generate
        from graphify.export import to_json, to_html
        print("Loading existing graph...")
        _raw = json.loads(graph_json.read_text(encoding="utf-8"))
        G = build_from_json(_raw)
        print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        print("Re-clustering...")
        communities = cluster(G)
        cohesion = score_all(G, communities)
        gods = god_nodes(G)
        surprises = surprising_connections(G, communities)
        labels = {cid: f"Community {cid}" for cid in communities}
        questions = suggest_questions(G, communities, labels)
        tokens = {"input": 0, "output": 0}
        report = generate(G, communities, cohesion, labels, gods, surprises,
                          {"warning": "cluster-only mode — file stats not available"},
                          tokens, str(watch_path), suggested_questions=questions)
        out = watch_path / "graphify-out"
        (out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
        to_json(G, communities, str(out / "graph.json"))
        to_html(G, communities, str(out / "graph.html"), community_labels=labels or None)
        print(f"Done — {len(communities)} communities. GRAPH_REPORT.md, graph.json and graph.html updated.")

    elif cmd == "update":
        watch_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
        if not watch_path.exists():
            print(f"error: path not found: {watch_path}", file=sys.stderr)
            sys.exit(1)
        from graphify.watch import _rebuild_code
        print(f"Re-extracting code files in {watch_path} (no LLM needed)...")
        ok = _rebuild_code(watch_path)
        if ok:
            print("Code graph updated. For doc/paper/image changes run /graphify --update in your AI assistant.")
        else:
            print("Nothing to update or rebuild failed — check output above.", file=sys.stderr)
            sys.exit(1)

    elif cmd == "benchmark":
        from graphify.benchmark import run_benchmark, print_benchmark
        graph_path = sys.argv[2] if len(sys.argv) > 2 else "graphify-out/graph.json"
        # Try to load corpus_words from detect output
        corpus_words = None
        detect_path = Path(".graphify_detect.json")
        if detect_path.exists():
            try:
                detect_data = json.loads(detect_path.read_text(encoding="utf-8"))
                corpus_words = detect_data.get("total_words")
            except Exception:
                pass
        result = run_benchmark(graph_path, corpus_words=corpus_words)
        print_benchmark(result)
    elif cmd == "edges":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""

        if subcmd == "list":
            cross_path = Path("graphify-out/cross_edges.json")
            if not cross_path.exists():
                print("No cross_edges.json found. Use 'graphify edges add' to create one.")
                sys.exit(0)
            data = json.loads(cross_path.read_text(encoding="utf-8"))
            edges = data.get("edges", [])
            print(f"{len(edges)} cross-file edge(s):")
            for e in edges:
                conf = e.get("confidence_score", "?")
                note = f" -- {e['note']}" if e.get("note") else ""
                print(f"  {e['source']} --{e['relation']}--> {e['target']} [{conf}]{note}")

        elif subcmd == "add":
            if len(sys.argv) < 6:
                print("Usage: graphify edges add <source> <relation> <target> [--note '...'] [--score 0.95]", file=sys.stderr)
                sys.exit(1)
            source_id = sys.argv[3]
            relation = sys.argv[4]
            target_id = sys.argv[5]
            note = ""
            score = 0.9
            args = sys.argv[6:]
            i = 0
            while i < len(args):
                if args[i] == "--note" and i + 1 < len(args):
                    note = args[i + 1]; i += 2
                elif args[i] == "--score" and i + 1 < len(args):
                    score = float(args[i + 1]); i += 2
                else:
                    i += 1

            # Validate nodes exist in current graph
            graph_path = Path("graphify-out/graph.json")
            if graph_path.exists():
                g = json.loads(graph_path.read_text(encoding="utf-8"))
                node_ids = {n["id"] for n in g.get("nodes", [])}
                if source_id not in node_ids:
                    print(f"Warning: source node '{source_id}' not found in current graph", file=sys.stderr)
                if target_id not in node_ids:
                    print(f"Warning: target node '{target_id}' not found in current graph", file=sys.stderr)

            # Load or create cross_edges.json
            cross_path = Path("graphify-out/cross_edges.json")
            if cross_path.exists():
                data = json.loads(cross_path.read_text(encoding="utf-8"))
            else:
                cross_path.parent.mkdir(parents=True, exist_ok=True)
                data = {"version": 1, "description": "Persistent cross-file edges that survive AST rebuilds", "edges": []}

            # Check for duplicate
            for e in data["edges"]:
                if e["source"] == source_id and e["target"] == target_id and e["relation"] == relation:
                    print(f"Edge already exists: {source_id} --{relation}--> {target_id}")
                    sys.exit(0)

            from datetime import datetime, timezone
            edge = {
                "source": source_id,
                "target": target_id,
                "relation": relation,
                "confidence": "INFERRED",
                "confidence_score": score,
                "source_file": "cross_edges.json",
                "source_location": None,
                "weight": 1.0,
                "origin": "manual",
                "added_at": datetime.now(timezone.utc).isoformat(),
            }
            if note:
                edge["note"] = note

            data["edges"].append(edge)
            cross_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(f"Added: {source_id} --{relation}--> {target_id} [{score}]")
            print(f"Total: {len(data['edges'])} cross-file edge(s)")
            print("Run 'graphify update .' or rebuild to apply.")

        elif subcmd == "remove":
            if len(sys.argv) < 6:
                print("Usage: graphify edges remove <source> <relation> <target>", file=sys.stderr)
                sys.exit(1)
            source_id = sys.argv[3]
            relation = sys.argv[4]
            target_id = sys.argv[5]

            cross_path = Path("graphify-out/cross_edges.json")
            if not cross_path.exists():
                print("No cross_edges.json found.")
                sys.exit(0)

            data = json.loads(cross_path.read_text(encoding="utf-8"))
            before = len(data["edges"])
            data["edges"] = [
                e for e in data["edges"]
                if not (e["source"] == source_id and e["target"] == target_id and e["relation"] == relation)
            ]
            after = len(data["edges"])

            if before == after:
                print(f"Edge not found: {source_id} --{relation}--> {target_id}")
            else:
                cross_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                print(f"Removed: {source_id} --{relation}--> {target_id}")
                print(f"Remaining: {after} cross-file edge(s)")

        elif subcmd == "prune":
            cross_path = Path("graphify-out/cross_edges.json")
            graph_path = Path("graphify-out/graph.json")
            if not cross_path.exists():
                print("No cross_edges.json found.")
                sys.exit(0)
            if not graph_path.exists():
                print("No graph.json found. Build the graph first.", file=sys.stderr)
                sys.exit(1)

            g = json.loads(graph_path.read_text(encoding="utf-8"))
            node_ids = {n["id"] for n in g.get("nodes", [])}
            data = json.loads(cross_path.read_text(encoding="utf-8"))

            before = len(data["edges"])
            data["edges"] = [
                e for e in data["edges"]
                if e["source"] in node_ids and e["target"] in node_ids
            ]
            after = len(data["edges"])

            cross_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            pruned = before - after
            if pruned:
                print(f"Pruned {pruned} stale edge(s) (nodes no longer in graph)")
            print(f"Remaining: {after} cross-file edge(s)")

        else:
            print("Usage: graphify edges <list|add|remove|prune>", file=sys.stderr)
            print("  edges list              list persistent cross-file edges", file=sys.stderr)
            print("  edges add S R T         add cross-file edge (source relation target)", file=sys.stderr)
            print("    --note \"...\"            optional description", file=sys.stderr)
            print("    --score N               confidence score (default 0.9)", file=sys.stderr)
            print("  edges remove S R T      remove a cross-file edge", file=sys.stderr)
            print("  edges prune             remove edges where nodes no longer exist", file=sys.stderr)
            sys.exit(1)

    else:
        print(f"error: unknown command '{cmd}'", file=sys.stderr)
        print("Run 'graphify --help' for usage.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
