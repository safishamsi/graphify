from __future__ import annotations
import os
import platform
import shutil
import sys
from pathlib import Path

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("graphifyy")
except Exception:
    __version__ = "unknown"

_GRAPHIFY_OUT = os.environ.get("GRAPHIFY_OUT", "graphify-out")

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
    "pi": {
        "skill_file": "skill-pi.md",
        "skill_dst": Path(".pi") / "agent" / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "antigravity": {
        "skill_file": "skill.md",
        "skill_dst": Path(".agents") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "antigravity-windows": {
        "skill_file": "skill-windows.md",
        "skill_dst": Path(".agents") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "windows": {
        "skill_file": "skill-windows.md",
        "skill_dst": Path(".claude") / "skills" / "graphify" / "SKILL.md",
        "claude_md": True,
    },
    "kimi": {
        "skill_file": "skill.md",
        "skill_dst": Path(".kimi") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
}

def _default_graph_path() -> str:
    return str(Path(_GRAPHIFY_OUT) / "graph.json")

def _enforce_graph_size_cap_or_exit(gp: Path) -> None:
    from graphify.security import check_graph_file_size_cap
    try:
        check_graph_file_size_cap(gp)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

def _check_skill_version(skill_dst: Path) -> None:
    version_file = skill_dst.parent / ".graphify_version"
    if not version_file.exists():
        return
    if not skill_dst.exists():
        print("  warning: skill dir exists but SKILL.md is missing. Run 'graphify install' to repair.")
        return
    installed = version_file.read_text(encoding="utf-8").strip()
    if installed != __version__:
        print(f"  warning: skill is from graphify {installed}, package is {__version__}. Run 'graphify install' to update.", file=sys.stderr)

def _refresh_all_version_stamps() -> None:
    for cfg in _PLATFORM_CONFIG.values():
        skill_dst = Path.home() / cfg["skill_dst"]
        vf = skill_dst.parent / ".graphify_version"
        if skill_dst.exists():
            vf.write_text(__version__, encoding="utf-8")

def _platform_skill_destination(platform_name: str, *, project: bool = False, project_dir: Path | None = None) -> Path:
    if platform_name == "gemini":
        if project:
            return (project_dir or Path(".")) / ".gemini" / "skills" / "graphify" / "SKILL.md"
        if platform.system() == "Windows":
            return Path.home() / ".agents" / "skills" / "graphify" / "SKILL.md"
        return Path.home() / ".gemini" / "skills" / "graphify" / "SKILL.md"
    cfg = _PLATFORM_CONFIG[platform_name]
    if project:
        return (project_dir or Path(".")) / cfg["skill_dst"]
    if platform_name in ("claude", "windows") and os.environ.get("CLAUDE_CONFIG_DIR"):
        return Path(os.environ["CLAUDE_CONFIG_DIR"]) / "skills" / "graphify" / "SKILL.md"
    return Path.home() / cfg["skill_dst"]

def _copy_skill_file(platform_name: str, *, project: bool = False, project_dir: Path | None = None) -> Path:
    skill_file = "skill.md" if platform_name == "gemini" else _PLATFORM_CONFIG[platform_name]["skill_file"]
    # Skill markdown files live at the graphify package root (graphify/skill.md etc.)
    skill_src = Path(__file__).parent.parent / skill_file
    if not skill_src.exists():
        print(f"error: {skill_file} not found in package - reinstall graphify", file=sys.stderr)
        sys.exit(1)
    skill_dst = _platform_skill_destination(platform_name, project=project, project_dir=project_dir)
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_dst = skill_dst.with_suffix(skill_dst.suffix + ".tmp")
    try:
        shutil.copy(skill_src, tmp_dst)
        os.replace(tmp_dst, skill_dst)
    except Exception:
        try:
            tmp_dst.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    (skill_dst.parent / ".graphify_version").write_text(__version__, encoding="utf-8")
    print(f"  skill installed  ->  {skill_dst}")
    return skill_dst

def _remove_skill_file(platform_name: str, *, project: bool = False, project_dir: Path | None = None) -> bool:
    skill_dst = _platform_skill_destination(platform_name, project=project, project_dir=project_dir)
    removed = False
    if skill_dst.exists():
        skill_dst.unlink()
        print(f"  skill removed    ->  {skill_dst}")
        removed = True
    version_file = skill_dst.parent / ".graphify_version"
    if version_file.exists():
        version_file.unlink()
        removed = True
    for d in (skill_dst.parent, skill_dst.parent.parent, skill_dst.parent.parent.parent):
        try:
            d.rmdir()
        except OSError:
            break
    return removed

def _project_scope_root(path: Path, project_dir: Path) -> Path:
    try:
        rel = path.relative_to(project_dir)
    except ValueError:
        return path
    return project_dir / rel.parts[0] if rel.parts else path

def _print_project_git_add_hint(paths: list[Path]) -> None:
    unique: list[str] = []
    for path in paths:
        text = path.as_posix().rstrip("/")
        if path.exists() and path.is_dir():
            text += "/"
        if text not in unique:
            unique.append(text)
    if not unique:
        return
    print()
    print("Project-scoped install. Add to version control:")
    print(f"  git add {' '.join(unique)}")

def _replace_or_append_section(content: str, marker: str, new_section: str) -> str:
    if marker not in content:
        if content.strip():
            return content.rstrip() + "\n\n" + new_section.lstrip()
        return new_section.lstrip()
    lines = content.split("\n")
    start = next((i for i, line in enumerate(lines) if marker in line), None)
    if start is None:
        return content.rstrip() + "\n\n" + new_section.lstrip()
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    head = "\n".join(lines[:start]).rstrip()
    tail = "\n".join(lines[end:]).lstrip()
    section = new_section.strip()
    parts: list[str] = []
    if head:
        parts.append(head)
    parts.append(section)
    if tail:
        parts.append(tail)
    out = "\n\n".join(parts)
    if not out.endswith("\n"):
        out += "\n"
    return out
