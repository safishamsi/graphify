import os
import re
from pathlib import Path
import fnmatch

from graphify.detect.constants import _SKIP_DIRS, _VCS_MARKERS


def _is_noise_dir(part: str) -> bool:
    """Return True if this directory name looks like a venv, cache, or dep dir."""
    if part in _SKIP_DIRS:
        return True
    # Catch *_venv, *_repo/site-packages patterns
    if part.endswith("_venv") or part.endswith("_env"):
        return True
    if part.endswith(".egg-info"):
        return True
    return False

def _parse_gitignore_line(raw: str) -> str:
    """Parse one raw line from a .graphifyignore file per gitignore spec.

    - Strip newline chars
    - Strip inline comments (whitespace + # suffix), but only when # is
      preceded by whitespace — so path#with#hash.py is preserved
    - Unescape \\# to literal #
    - Remove trailing spaces unless escaped with backslash
    - Strip leading whitespace
    - Return empty string for blank lines and full-line comments
    """
    line = raw.rstrip("\n\r")
    line = line.lstrip()
    if not line or line.startswith("#"):
        return ""
    # Strip inline comments: require whitespace before # (gitignore extension)
    line = re.sub(r"\s+#+[^\\].*$", "", line)
    # Unescape \# → literal #
    line = line.replace("\\#", "#")
    # Remove unescaped trailing spaces (per gitignore spec)
    line = re.sub(r"(?<!\\) +$", "", line)
    return line

def _find_vcs_root(start: Path) -> Path | None:
    """Walk upward from start; return the first directory containing a VCS marker."""
    current = start.resolve()
    home = Path.home()
    while True:
        if any((current / m).exists() for m in _VCS_MARKERS):
            return current
        parent = current.parent
        if parent == current or current == home:
            return None
        current = parent

def _load_graphifyignore(root: Path) -> list[tuple[Path, str]]:
    """Read .graphifyignore files and return (anchor_dir, pattern) pairs.

    Patterns are returned outer-first so that inner (closer) rules are
    appended last and win via last-match-wins semantics — matching gitignore
    behavior exactly.

    Walk ceiling: the nearest VCS root if inside a repo, otherwise the scan
    root itself (hermetic — no leakage across unrelated sibling projects).
    """
    root = root.resolve()
    ceiling = _find_vcs_root(root) or root

    # Collect ancestor dirs from ceiling down to root (outer → inner)
    dirs: list[Path] = []
    current = root
    while True:
        dirs.append(current)
        if current == ceiling:
            break
        current = current.parent
    dirs.reverse()  # ceiling first, scan root last

    patterns: list[tuple[Path, str]] = []
    for d in dirs:
        # Prefer .graphifyignore; fall back to .gitignore so projects that already
        # maintain a .gitignore get sensible defaults without duplicating it (#945).
        ignore_file = d / ".graphifyignore"
        if not ignore_file.exists():
            ignore_file = d / ".gitignore"
        if ignore_file.exists():
            for raw in ignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = _parse_gitignore_line(raw)
                if line:
                    patterns.append((d, line))
    return patterns

def _is_ignored(path: Path, root: Path, patterns: list[tuple[Path, str]]) -> bool:
    """Return True if the path should be ignored per .graphifyignore patterns.

    Uses gitignore last-match-wins semantics: all patterns are evaluated in
    order; the final matching pattern determines the result. Negation patterns
    (starting with !) un-ignore a previously ignored path.

    Enforces gitignore's parent-exclusion rule: a ! pattern cannot re-include
    a file whose ancestor directory is already excluded.
    """
    if not patterns:
        return False

    def _eval(target: Path) -> bool:
        """Apply last-match-wins to a single target path."""
        def _matches(rel: str, p: str) -> bool:
            parts = rel.split("/")
            if fnmatch.fnmatch(rel, p):
                return True
            if fnmatch.fnmatch(target.name, p):
                return True
            for i, part in enumerate(parts):
                if fnmatch.fnmatch(part, p):
                    return True
                if fnmatch.fnmatch("/".join(parts[:i + 1]), p):
                    return True
            return False

        result = False
        for anchor, pattern in patterns:
            negated = pattern.startswith("!")
            raw = pattern[1:] if negated else pattern
            anchored = raw.startswith("/")
            p = raw.strip("/")
            if not p:
                continue

            matched = False
            if anchored:
                try:
                    rel_anchor = str(target.relative_to(anchor)).replace(os.sep, "/")
                    matched = _matches(rel_anchor, p)
                except ValueError:
                    pass
            else:
                try:
                    rel = str(target.relative_to(root)).replace(os.sep, "/")
                    matched = _matches(rel, p)
                except ValueError:
                    pass
                if not matched and anchor != root:
                    try:
                        rel_anchor = str(target.relative_to(anchor)).replace(os.sep, "/")
                        matched = _matches(rel_anchor, p)
                    except ValueError:
                        pass

            if matched:
                result = not negated  # last match wins; ! flips to un-ignore
        return result

    # Gitignore parent-exclusion rule: a ! re-include cannot rescue a file
    # whose ancestor directory is already excluded. Walk ancestors top-down;
    # if any ancestor is excluded, the file is excluded regardless of later
    # ! patterns targeting the file or a sub-path.
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        return _eval(path)

    ancestor = root
    for part in rel_parts[:-1]:
        ancestor = ancestor / part
        if _eval(ancestor):
            return True
    return _eval(path)

def _load_graphifyinclude(root: Path) -> list[tuple[Path, str]]:
    """Read .graphifyinclude allowlist patterns from root and ancestors.

    Include patterns opt matching hidden files/dirs into traversal. Sensitive
    files and hard-skipped noise directories are still excluded later.
    Uses the same VCS-root ceiling logic as _load_graphifyignore.
    """
    root = root.resolve()
    ceiling = _find_vcs_root(root) or root

    dirs: list[Path] = []
    current = root
    while True:
        dirs.append(current)
        if current == ceiling:
            break
        current = current.parent
    dirs.reverse()

    patterns: list[tuple[Path, str]] = []
    for d in dirs:
        include_file = d / ".graphifyinclude"
        if include_file.exists():
            for raw in include_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = _parse_gitignore_line(raw)
                if line:
                    patterns.append((d, line))
    return patterns

def _is_included(path: Path, root: Path, patterns: list[tuple[Path, str]]) -> bool:
    """Return True if path matches any .graphifyinclude allowlist pattern."""
    if not patterns:
        return False

    def _matches(rel: str, p: str) -> bool:
        parts = rel.split("/")
        if fnmatch.fnmatch(rel, p):
            return True
        if fnmatch.fnmatch(path.name, p):
            return True
        for i, part in enumerate(parts):
            if fnmatch.fnmatch(part, p):
                return True
            if fnmatch.fnmatch("/".join(parts[:i + 1]), p):
                return True
        return False

    for anchor, pattern in patterns:
        anchored = pattern.startswith("/")
        p = pattern.strip("/")
        if not p:
            continue
        if anchored:
            try:
                rel_anchor = str(path.relative_to(anchor)).replace(os.sep, "/")
                if _matches(rel_anchor, p):
                    return True
            except ValueError:
                pass
        else:
            try:
                rel = str(path.relative_to(root)).replace(os.sep, "/")
                if _matches(rel, p):
                    return True
            except ValueError:
                pass
            if anchor != root:
                try:
                    rel_anchor = str(path.relative_to(anchor)).replace(os.sep, "/")
                    if _matches(rel_anchor, p):
                        return True
                except ValueError:
                    pass
    return False

def _could_contain_included_path(path: Path, root: Path, patterns: list[tuple[Path, str]]) -> bool:
    """Return True if a directory may contain files matched by .graphifyinclude."""
    if not patterns:
        return False

    rels: list[str] = []
    try:
        rels.append(str(path.relative_to(root)).replace(os.sep, "/"))
    except ValueError:
        pass
    for anchor, _ in patterns:
        if anchor != root:
            try:
                rels.append(str(path.relative_to(anchor)).replace(os.sep, "/"))
            except ValueError:
                pass

    for rel in rels:
        rel = rel.strip("/")
        if not rel:
            return True
        for _, pattern in patterns:
            p = pattern.strip("/")
            if not p:
                continue
            if p == rel or p.startswith(rel + "/"):
                return True
            if fnmatch.fnmatch(rel, p):
                return True
    return False
