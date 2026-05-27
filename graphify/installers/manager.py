from __future__ import annotations
import sys
from pathlib import Path

from .core import _PLATFORM_CONFIG, _copy_skill_file, _print_project_git_add_hint, _project_scope_root, _refresh_all_version_stamps, _remove_skill_file
from .claude import claude_install, claude_uninstall, _remove_claude_skill_registration
from .gemini import gemini_install, gemini_uninstall
from .cursor import _cursor_install, _cursor_uninstall
from .vscode import vscode_uninstall
from .kiro import _kiro_install, _kiro_uninstall
from .agents import _agents_install, _agents_uninstall
from .opencode import _install_opencode_plugin, _uninstall_opencode_plugin
from .codex import _uninstall_codex_hook
from .antigravity import _antigravity_uninstall

def _print_install_usage() -> None:
    platforms = ", ".join([*_PLATFORM_CONFIG, "gemini", "cursor"])
    print("Usage: graphify install [--project] [--platform P|P]")
    print(f"Platforms: {platforms}")

def install(platform_name: str = "claude", *, project: bool = False, project_dir: Path | None = None) -> None:
    if platform_name == "gemini":
        gemini_install(project_dir=project_dir, project=project)
        return
    if platform_name == "cursor":
        _cursor_install(Path("."))
        return
    if platform_name == "antigravity" and sys.platform == "win32":
        platform_name = "antigravity-windows"
    if platform_name not in _PLATFORM_CONFIG:
        print(
            f"error: unknown platform '{platform_name}'. Choose from: {', '.join(_PLATFORM_CONFIG)}, gemini, cursor",
            file=sys.stderr,
        )
        sys.exit(1)

    cfg = _PLATFORM_CONFIG[platform_name]
    project_dir = project_dir or Path(".")
    skill_dst = _copy_skill_file(platform_name, project=project, project_dir=project_dir)

    if cfg.get("claude_md"):
        # We can just delegate to claude_install which handles both global and project scope implicitly
        # Wait, the original `install` function had logic to append to CLAUDE.md and `_skill_registration`.
        # Since claude_install expects the project_dir, we can use it.
        # But `claude_install` handles PreToolUse hook as well. Let's just use it.
        # However, `install` handles Windows which also uses CLAUDE.md.
        if platform_name in ("claude", "windows"):
            claude_install(project_dir if project else None)

    if platform_name == "opencode":
        _install_opencode_plugin(project_dir if project else Path("."))

    if project:
        _print_project_git_add_hint([_project_scope_root(skill_dst, project_dir)])
    else:
        _refresh_all_version_stamps()

    print()
    print("Done. Open your AI coding assistant and type:")
    print()
    print("  /graphify .")
    print()

def _project_install(platform_name: str, project_dir: Path | None = None) -> None:
    project_dir = project_dir or Path(".")
    if platform_name in ("claude", "windows"):
        install(platform_name=platform_name, project=True, project_dir=project_dir)
        claude_install(project_dir)
        _print_project_git_add_hint([project_dir / ".claude", project_dir / "CLAUDE.md"])
    elif platform_name == "gemini":
        gemini_install(project_dir, project=True)
    elif platform_name == "cursor":
        _cursor_install(project_dir)
        _print_project_git_add_hint([project_dir / ".cursor"])
    elif platform_name == "kiro":
        _kiro_install(project_dir)
        _print_project_git_add_hint([project_dir / ".kiro"])
    elif platform_name in ("aider", "codex", "opencode", "claw", "droid", "trae", "trae-cn", "hermes"):
        skill_dst = _copy_skill_file(platform_name, project=True, project_dir=project_dir)
        _agents_install(project_dir, platform_name)
        hint_paths = [_project_scope_root(skill_dst, project_dir), project_dir / "AGENTS.md"]
        if platform_name == "opencode":
            hint_paths.append(project_dir / ".opencode")
        elif platform_name == "codex":
            hint_paths.append(project_dir / ".codex")
        _print_project_git_add_hint(hint_paths)
    elif platform_name in ("copilot", "pi", "antigravity", "kimi"):
        skill_dst = _copy_skill_file(platform_name, project=True, project_dir=project_dir)
        _print_project_git_add_hint([_project_scope_root(skill_dst, project_dir)])
    else:
        install(platform_name=platform_name, project=True, project_dir=project_dir)

def _project_uninstall(platform_name: str, project_dir: Path | None = None) -> None:
    project_dir = project_dir or Path(".")
    if platform_name in ("claude", "windows"):
        _remove_skill_file(platform_name, project=True, project_dir=project_dir)
        _remove_claude_skill_registration(project_dir)
        claude_uninstall(project_dir)
    elif platform_name == "gemini":
        gemini_uninstall(project_dir, project=True)
    elif platform_name == "cursor":
        _cursor_uninstall(project_dir)
    elif platform_name == "kiro":
        _kiro_uninstall(project_dir)
    elif platform_name in ("aider", "codex", "opencode", "claw", "droid", "trae", "trae-cn", "hermes"):
        _remove_skill_file(platform_name, project=True, project_dir=project_dir)
        _agents_uninstall(project_dir, platform=platform_name)
        if platform_name == "codex":
            _uninstall_codex_hook(project_dir)
    elif platform_name == "antigravity":
        _remove_skill_file(platform_name, project=True, project_dir=project_dir)
        _antigravity_uninstall(project_dir)
    elif platform_name in ("copilot", "pi", "kimi"):
        removed = _remove_skill_file(platform_name, project=True, project_dir=project_dir)
        if not removed:
            print("nothing to remove")
    else:
        _remove_skill_file(platform_name, project=True, project_dir=project_dir)

def _project_uninstall_all(project_dir: Path | None = None) -> None:
    project_dir = project_dir or Path(".")
    print("Uninstalling project-scoped graphify files...\n")
    for platform_name in _PLATFORM_CONFIG:
        _project_uninstall(platform_name, project_dir)
    for platform_name in ("gemini", "cursor"):
        _project_uninstall(platform_name, project_dir)
    print("\nDone.")

def uninstall_all(project_dir: Path | None = None, purge: bool = False) -> None:
    pd = project_dir or Path(".")
    print("Uninstalling graphify from all detected platforms...\n")

    claude_uninstall(pd)
    gemini_uninstall(pd)
    vscode_uninstall(pd)
    _cursor_uninstall(pd)
    _kiro_uninstall(pd)
    _antigravity_uninstall(pd)
    _agents_uninstall(pd)
    _uninstall_opencode_plugin(pd)
    _uninstall_codex_hook(pd)

    try:
        from graphify.hooks import uninstall as hook_uninstall
        result = hook_uninstall(pd)
        if result:
            print(result)
    except Exception:
        pass

    if purge:
        import shutil as _shutil
        out = pd / "graphify-out"
        if out.exists():
            _shutil.rmtree(out)
            print(f"\n  graphify-out/  ->  deleted (--purge)")
        else:
            print("\n  graphify-out/  ->  not found (nothing to purge)")

    print("\nDone. Run 'pip uninstall graphifyy' to remove the package itself.")
