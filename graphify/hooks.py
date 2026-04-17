# git hook integration - install/uninstall graphify post-commit hook
from __future__ import annotations
import subprocess
from pathlib import Path

_HOOK_MARKER = "# graphify-hook"

_HOOK_SCRIPT = """\
#!/bin/bash
# graphify-hook
# Auto-rebuilds the knowledge graph after each commit (code files only, no LLM needed).
# Installed by: graphify hook install

CHANGED=$(git diff --name-only HEAD~1 HEAD 2>/dev/null || git diff --name-only HEAD 2>/dev/null)
if [ -z "$CHANGED" ]; then
    exit 0
fi

export GRAPHIFY_CHANGED="$CHANGED"
python3 -c "
import os, sys
from pathlib import Path

CODE_EXTS = {
    '.py', '.ts', '.js', '.go', '.rs', '.java', '.cpp', '.c', '.rb', '.swift',
    '.kt', '.cs', '.scala', '.php', '.cc', '.cxx', '.hpp', '.h', '.kts',
}

changed_raw = os.environ.get('GRAPHIFY_CHANGED', '')
changed = [Path(f.strip()) for f in changed_raw.strip().splitlines() if f.strip()]
code_changed = [f for f in changed if f.suffix.lower() in CODE_EXTS and f.exists()]

if not code_changed:
    sys.exit(0)

print(f'[graphify hook] {len(code_changed)} code file(s) changed - rebuilding graph...')

try:
    from graphify.watch import _rebuild_code
    _rebuild_code(Path('.'))
except Exception as exc:
    print(f'[graphify hook] Rebuild failed: {exc}')
    sys.exit(0)
"
"""


def _git_root(path: Path) -> Path | None:
    """Walk up to find .git directory."""
    current = path.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def _hooks_dir(root: Path) -> Path:
    """Return the active hooks directory for this repo.

    Respects core.hooksPath if set (e.g. repos using Husky). Falls back to
    .git/hooks so we never write hooks into the wrong location.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "config", "core.hooksPath"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            custom = result.stdout.strip()
            if custom:
                p = Path(custom)
                if not p.is_absolute():
                    p = root / p
                p.mkdir(parents=True, exist_ok=True)
                return p
    except (OSError, FileNotFoundError):
        pass
    d = root / ".git" / "hooks"
    d.mkdir(exist_ok=True)
    return d


def install(path: Path = Path(".")) -> str:
    """Install graphify post-commit hook in the nearest git repo.

    Returns a message describing what was done.
    """
    root = _git_root(path)
    if root is None:
        raise RuntimeError(f"No git repository found at or above {path.resolve()}")

    hooks_dir = _hooks_dir(root)
    hook_path = hooks_dir / "post-commit"

    if hook_path.exists():
        content = hook_path.read_text()
        if _HOOK_MARKER in content:
            return f"graphify hook already installed at {hook_path}"
        # Append to existing hook
        hook_path.write_text(content.rstrip() + "\n\n" + _HOOK_SCRIPT)
        return f"graphify hook appended to existing post-commit hook at {hook_path}"

    hook_path.write_text(_HOOK_SCRIPT)
    hook_path.chmod(0o755)
    return f"graphify hook installed at {hook_path}"


def uninstall(path: Path = Path(".")) -> str:
    """Remove graphify post-commit hook."""
    root = _git_root(path)
    if root is None:
        raise RuntimeError(f"No git repository found at or above {path.resolve()}")

    hook_path = _hooks_dir(root) / "post-commit"
    if not hook_path.exists():
        return "No post-commit hook found - nothing to remove."

    content = hook_path.read_text()
    if _HOOK_MARKER not in content:
        return "graphify hook not found in post-commit - nothing to remove."

    # Strip everything from our marker onwards
    before = content.split(_HOOK_MARKER)[0].rstrip()
    # 'before' is empty or just a shebang line if the whole file was ours
    non_empty = [l for l in before.splitlines() if l.strip() and not l.startswith("#!")]
    if not non_empty:
        hook_path.unlink()
        return f"Removed post-commit hook at {hook_path}"
    else:
        hook_path.write_text(before + "\n")
        return f"graphify hook removed from {hook_path} (other hook content preserved)"


def status(path: Path = Path(".")) -> str:
    """Check if graphify hook is installed."""
    root = _git_root(path)
    if root is None:
        return "Not in a git repository."
    hook_path = _hooks_dir(root) / "post-commit"
    if not hook_path.exists():
        return "graphify hook: not installed"
    if _HOOK_MARKER in hook_path.read_text():
        return f"graphify hook: installed at {hook_path}"
    return "graphify hook: not installed (post-commit exists but graphify hook not found)"
