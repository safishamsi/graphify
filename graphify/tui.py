"""
tui.py — Interactive Terminal UI for .graphifyignore initialisation.
Triggered automatically on first run and re-openable via: graphify ignore

Controls (raw TUI):
  UP/DOWN    Navigate   SPACE  Toggle include/exclude   E  Expand/collapse dir
  A          Include all visible    N  Exclude all visible    F  Toggle files in dir
  R          Reset to defaults      I  Show/hide auto-ignored   /  Filter mode
  ESC        Clear filter           ENTER  Save & exit          Q  Quit without saving
  ?          Toggle help
"""
from __future__ import annotations

import logging
import os
import select
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("graphify.tui")

_BUILD_MS_PER_FILE: int   = 200
_GETCH_TIMEOUT:     float = 0.05
_WARN_FILE_COUNT:   int   = 500
_CRIT_FILE_COUNT:   int   = 2000
_MIN_ROWS:          int   = 12
_MIN_COLS:          int   = 40
_SCAN_MAX_DEPTH:    int   = 3

# ── ANSI ──────────────────────────────────────────────────────────────────────
_G  = "\033[32m"
_DI = "\033[2m"
_Y  = "\033[33m"
_B  = "\033[1m"
_CY = "\033[36m"
_R  = "\033[0m"
_RE = "\033[31m"


def _clear_screen() -> None:
    os.system("cls" if sys.platform == "win32" else "clear")


def _term_size() -> tuple[int, int]:
    try:
        sz = os.get_terminal_size()
        return sz.lines, sz.columns
    except OSError:
        return 24, 80


# ── Ignore constants ──────────────────────────────────────────────────────────

def _load_ignore_constants() -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    try:
        from graphify import ingest as _ingest
        dirs  = getattr(_ingest, "IGNORE_DIRS", None)
        exts  = getattr(_ingest, "IGNORE_EXTS", None)
        dots  = getattr(_ingest, "VISIBLE_DOTFILES", None)
        if dirs and exts:
            return frozenset(dirs), frozenset(exts), frozenset(dots) if dots else _DEFAULT_VISIBLE_DOTFILES
    except ImportError:
        pass
    return _DEFAULT_IGNORE_DIRS, _DEFAULT_IGNORE_EXTS, _DEFAULT_VISIBLE_DOTFILES


_DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset({
    "venv", ".venv", "env", ".env", "ENV",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", ".yarn", ".npm",
    ".git", ".hg", ".svn",
    "dist", "build", "target", "out", "bin", "obj",
    ".tox", ".eggs",
    ".idea", ".vscode", ".vs",
    "migrations", "__snapshots__",
    "graphify-out", ".graphify",
    ".cache", "tmp", "temp",
    "coverage", ".coverage",
    "logs", "log",
})

_DEFAULT_IGNORE_EXTS: frozenset[str] = frozenset({
    ".pyc", ".pyo", ".pyd", ".so", ".dylib", ".dll",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".mp4", ".mp3", ".mov", ".avi", ".wav",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".pdf", ".docx", ".xlsx", ".pptx",
    ".db", ".sqlite", ".sqlite3",
    ".lock", ".sum",
})

_DEFAULT_VISIBLE_DOTFILES: frozenset[str] = frozenset({
    ".gitignore", ".graphifyignore", ".env", ".envrc", ".python-version",
})

IGNORE_DIRS, IGNORE_EXTS, VISIBLE_DOTFILES = _load_ignore_constants()


# ── Language detection ────────────────────────────────────────────────────────

def _detect_language(project_root: Path) -> str:
    try:
        from graphify import detect as _detect
        fn = getattr(_detect, "detect_language", None)
        if callable(fn):
            return fn(project_root)
    except ImportError:
        pass
    indicators = {
        "Python":     ["pyproject.toml", "setup.py", "requirements.txt", "Pipfile"],
        "JavaScript": ["package.json", "yarn.lock", "package-lock.json"],
        "TypeScript": ["tsconfig.json"],
        "Go":         ["go.mod"],
        "Rust":       ["Cargo.toml"],
        "Java":       ["pom.xml", "build.gradle"],
    }
    for lang, files in indicators.items():
        if any((project_root / f).exists() for f in files):
            return lang
    return "Unknown"


_LANG_MANIFESTS: dict[str, list[str]] = {
    "Python":     ["pyproject.toml", "setup.py", "requirements.txt"],
    "JavaScript": ["package.json"],
    "TypeScript": ["tsconfig.json", "package.json"],
    "Go":         ["go.mod"],
    "Rust":       ["Cargo.toml"],
    "Java":       ["pom.xml", "build.gradle"],
}


# ── Heuristics ────────────────────────────────────────────────────────────────

def _default_excluded(path: Path, project_root: Path) -> bool:
    try:
        parts = path.relative_to(project_root).parts
    except ValueError:
        return False
    for part in parts:
        clean = part.rstrip("/")
        if clean in IGNORE_DIRS or clean.endswith(".egg-info"):
            return True
    if path.is_file() and path.suffix.lower() in IGNORE_EXTS:
        return True
    for part in parts:
        if part.startswith(".") and part not in VISIBLE_DOTFILES:
            return True
    return False


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _estimate_build_time(tracked: list[Entry]) -> float:
    return max(1.0, len(tracked) * _BUILD_MS_PER_FILE / 1000.0) if tracked else 0.0


def _file_type_breakdown(entries: list[Entry]) -> dict[str, int]:
    ext_map = {
        ".py": "Python", ".pyx": "Cython",
        ".js": "JS", ".mjs": "JS", ".jsx": "JS",
        ".ts": "TS", ".tsx": "TS",
        ".go": "Go", ".rs": "Rust", ".java": "Java",
        ".md": "Markdown", ".rst": "Markdown",
        ".toml": "Config", ".yaml": "Config", ".yml": "Config",
        ".json": "Config", ".cfg": "Config", ".ini": "Config",
    }
    counts: dict[str, int] = {}
    for e in entries:
        if e.excluded or e.is_dir:
            continue
        label = ext_map.get(e.path.suffix.lower(), "Other")
        counts[label] = counts.get(label, 0) + 1
    return counts


# ── Entry model ───────────────────────────────────────────────────────────────

@dataclass
class Entry:
    path:         Path
    relative:     str
    is_dir:       bool
    excluded:     bool
    auto_detected: bool
    expanded:     bool = False
    children:     list[Entry] = field(default_factory=list)
    depth:        int = 0

    @property
    def icon(self) -> str:
        return ("▼" if self.expanded else "▶") if self.is_dir else " "

    @property
    def check(self) -> str:
        return "[ ]" if self.excluded else "[X]"

    @property
    def color(self) -> str:
        return _DI if self.excluded else _G

    def reset_to_default(self, project_root: Path) -> None:
        self.excluded = _default_excluded(self.path, project_root)
        self.auto_detected = self.excluded
        for child in self.children:
            child.reset_to_default(project_root)


# ── Directory scanner ─────────────────────────────────────────────────────────

def scan_directory(project_root: Path, max_depth: int = _SCAN_MAX_DEPTH) -> list[Entry]:
    entries: list[Entry] = []
    try:
        items = sorted(project_root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        logger.warning("Permission denied scanning %s", project_root)
        return []
    for item in items:
        if item.name.startswith(".") and item.name not in VISIBLE_DOTFILES:
            continue
        if item.is_symlink():
            continue
        excluded = _default_excluded(item, project_root)
        entries.append(Entry(
            path=item,
            relative=_safe_relative(item, project_root),
            is_dir=item.is_dir(),
            excluded=excluded,
            auto_detected=excluded,
        ))
    return entries


def _expand_entry(entry: Entry, project_root: Path) -> None:
    if not entry.is_dir or entry.children:
        return
    try:
        items = sorted(entry.path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        logger.debug("Permission denied expanding %s", entry.path)
        return
    for item in items:
        if any(part.startswith(".") and part not in VISIBLE_DOTFILES for part in item.parts):
            continue
        if item.is_symlink():
            continue
        is_auto = _default_excluded(item, project_root)
        entry.children.append(Entry(
            path=item,
            relative=_safe_relative(item, project_root),
            is_dir=item.is_dir(),
            excluded=entry.excluded or is_auto,
            auto_detected=is_auto,
            depth=entry.depth + 1,
        ))


# ── Flatten (iterative, recursion-safe) ──────────────────────────────────────

def _flatten(entries: list[Entry]) -> list[Entry]:
    result: list[Entry] = []
    stack = list(entries)
    while stack:
        e = stack.pop()
        result.append(e)
        if e.is_dir and e.children:
            stack.extend(reversed(e.children))
    return result


def _visible_flatten(entries: list[Entry]) -> list[Entry]:
    result: list[Entry] = []
    stack = list(entries)
    while stack:
        e = stack.pop()
        result.append(e)
        if e.is_dir and e.expanded and e.children:
            stack.extend(reversed(e.children))
    return result


def _cascade(entry: Entry, excluded: bool, project_root: Path) -> None:
    for child in entry.children:
        if excluded:
            child.excluded = True
        else:
            child.excluded = _default_excluded(child.path, project_root)
            child.auto_detected = child.excluded
        if child.is_dir and child.children:
            _cascade(child, child.excluded, project_root)


# ── .graphifyignore writer (DRY: deduped patterns) ──────────────────────────

def _write_graphifyignore(project_root: Path, entries: list[Entry]) -> Path:
    lines = [
        "# .graphifyignore — generated by graphify init",
        "# Syntax: one pattern per line. Same format as .gitignore.",
        "",
    ]

    auto_dirs: set[str] = set()
    auto_exts: set[str] = set()
    auto_paths: list[str] = []
    user_paths: list[str] = []

    excluded_dirs: set[Path] = set()

    def _collect(elist: list[Entry]) -> None:
        for e in elist:
            if e.excluded:
                if e.is_dir:
                    if e.path in excluded_dirs:
                        continue
                    excluded_dirs.add(e.path)
                parent_excluded = any(e.path.is_relative_to(d) for d in excluded_dirs if d != e.path)
                if parent_excluded:
                    continue

                if e.auto_detected:
                    if e.is_dir:
                        auto_dirs.add(e.path.name + "/")
                    elif e.path.suffix:
                        auto_exts.add("*" + e.path.suffix.lower())
                    else:
                        auto_paths.append(e.relative)
                else:
                    user_paths.append(e.relative + ("/**" if e.is_dir else ""))
            if e.is_dir and e.children:
                _collect(e.children)

    _collect(entries)

    def _section(header: str, patterns: list[str] | set[str]) -> None:
        if patterns:
            lines.append(f"# {header}")
            lines.extend(sorted(patterns))
            lines.append("")

    _section("Auto-detected directories (environments, caches, build outputs)", auto_dirs)
    _section("Auto-detected file types (binaries, media, archives)", auto_exts)
    _section("Auto-detected specific paths", auto_paths)
    _section("User-selected exclusions", user_paths)

    dest = project_root / ".graphifyignore"
    try:
        dest.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to write .graphifyignore: %s", exc)
        raise
    return dest


# ── Validation ───────────────────────────────────────────────────────────────

def _validate_selection(entries: list[Entry], project_root: Path, lang: str) -> list[str]:
    flat = _flatten(entries)
    tracked = [e for e in flat if not e.excluded]
    n = len(tracked)
    warnings: list[str] = []

    if n < 3:
        warnings.append(f"Only {n} file(s) selected — graph will be too sparse to be useful.")
    if n > _CRIT_FILE_COUNT:
        warnings.append(f"Very large selection ({n} files) — may cause OOM in low-memory environments.")
    elif n > _WARN_FILE_COUNT:
        warnings.append(f"Large selection ({n} files) — initial build may take several minutes.")

    for manifest in _LANG_MANIFESTS.get(lang, []):
        if (project_root / manifest).exists():
            if any(e.relative == manifest and e.excluded and not e.auto_detected for e in flat):
                warnings.append(f"{manifest} is excluded — graphify won't detect dependency edges.")

    src_exts: dict[str, tuple[str, ...]] = {
        "Python": (".py",), "JavaScript": (".js", ".mjs"),
        "TypeScript": (".ts", ".tsx"), "Go": (".go",),
        "Rust": (".rs",), "Java": (".java",),
    }
    src = src_exts.get(lang)
    if src and not any(e.path.suffix in src and not e.excluded for e in flat):
        warnings.append(f"No {lang} source files are tracked — the graph will have no code structure.")

    return warnings


# ── Auto mode ─────────────────────────────────────────────────────────────────

def auto_init(project_root: Path) -> Path:
    entries = scan_directory(project_root)
    lang = _detect_language(project_root)
    warns = _validate_selection(entries, project_root, lang)
    for w in warns:
        logger.info("auto-init: %s", w)
    dest = _write_graphifyignore(project_root, entries)
    flat = _flatten(entries)
    tracked = sum(1 for e in flat if not e.excluded)
    ignored = sum(1 for e in flat if e.excluded)
    print(f"  Auto-ignored {ignored} items in {lang} project ({tracked} tracked).")
    print(f"  Saved: {dest}")
    return dest


# ── Questionary fallback ──────────────────────────────────────────────────────

def _try_questionary(project_root: Path, entries: list[Entry]) -> bool:
    try:
        import questionary
    except ImportError:
        return False

    choices = [
        questionary.Choice(
            title=f"{'  ' * e.depth}{e.relative}{'/' if e.is_dir else ''}{'  (auto)' if e.auto_detected else ''}",
            value=e.relative,
            checked=not e.excluded,
        )
        for e in entries
    ]

    try:
        selected = questionary.checkbox(
            "Select items to INCLUDE in the knowledge graph (SPACE to toggle, ENTER to confirm):",
            choices=choices,
        ).ask()
    except (KeyboardInterrupt, Exception) as exc:
        logger.debug("questionary interrupted: %s", exc)
        return False

    if selected is None:
        return False

    selected_set = set(selected)
    for e in entries:
        e.excluded = e.relative not in selected_set
    return True


# ── Raw TUI — POSIX input ─────────────────────────────────────────────────────

def _getch() -> str:
    import termios, tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            if select.select([sys.stdin], [], [], _GETCH_TIMEOUT)[0]:
                ch2 = sys.stdin.read(1)
                if ch2 == "[" and select.select([sys.stdin], [], [], _GETCH_TIMEOUT)[0]:
                    ch3 = sys.stdin.read(1)
                    rest = ""
                    while select.select([sys.stdin], [], [], 0.02)[0]:
                        rest += sys.stdin.read(1)
                    return ch + ch2 + ch3 + rest
                return ch + ch2
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _confirm(message: str) -> bool:
    print(f"  {_Y}{message}{_R} ", end="", flush=True)
    try:
        import termios, tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        print(ch)
        return ch.lower() in ("y", "\r", "\n")
    except Exception:
        return True


# ── Raw TUI — render + event loop ────────────────────────────────────────────

def _raw_tui(project_root: Path, entries: list[Entry]) -> bool:
    cursor = 0
    filter_str = ""
    filtering = False
    show_ignored = True
    show_help = False
    lang = _detect_language(project_root)

    def _visible() -> list[Entry]:
        flat = _visible_flatten(entries)
        if not show_ignored:
            flat = [e for e in flat if not (e.excluded and e.auto_detected)]
        if filter_str:
            flat = [e for e in flat if filter_str.lower() in e.relative.lower()]
        return flat

    def _render() -> None:
        nonlocal cursor
        _clear_screen()
        visible = _visible()
        rows, _ = _term_size()
        content_rows = max(3, rows - 10)
        n = len(visible)

        print(f"{_B}{_CY}  Graphify — Select scope{_R}  ({lang} project detected)")
        if filtering:
            hint = f"  {_CY}FILTER{_R}  type to filter  ESC/Enter to exit  UP/DOWN to navigate"
        elif show_help:
            hint = f"  {_CY}HELP{_R}  press ? to close"
        else:
            hint = (f"  {_DI}UP/DOWN:nav  SPACE:toggle  E:expand  A:all  N:none  F:files  "
                    f"R:reset  I:ignored  /:filter  ?:help  ENTER:save  Q:quit{_R}")
        print(hint)
        print(f"  {'─' * 62}")

        if n == 0:
            cursor = 0
        else:
            cursor = max(0, min(n - 1, cursor))

        if n > 0:
            start = max(0, min(cursor - content_rows // 2, n - content_rows))
            end = min(n, start + content_rows)
            for i, e in enumerate(visible[start:end]):
                abs_i = start + i
                is_cur = abs_i == cursor
                prefix = f"  {_Y}>{_R}" if is_cur else "   "
                color = _Y if is_cur else e.color
                indent = "  " * e.depth
                name = e.relative.split("/")[-1] + ("/" if e.is_dir else "")
                tag = f"  {_DI}(auto){_R}" if e.auto_detected else ""
                if e.excluded and not e.auto_detected and e.depth > 0:
                    if any(pe.path == e.path.parent and pe.excluded for pe in entries):
                        tag = f"  {_DI}(inherited){_R}"
                print(f"{prefix} {color}{e.check}{_R} {indent}{e.icon} {color}{name}{_R}{tag}")
        else:
            print(f"  {_DI}No items match filter{_R}")

        if filter_str:
            print(f"\n  {_CY}Filter: {filter_str}{_R}  (ESC to clear)")

        if show_help:
            print()
            for line in (
                f"  {_B}Key Bindings{_R}",
                "  UP / DOWN   Navigate",
                "  SPACE       Toggle include / exclude",
                "  E           Expand / collapse directory",
                "  A           Include all visible",
                "  N           Exclude all visible",
                "  F           Toggle files in cursor directory (not subdirs)",
                "  R           Reset to smart defaults",
                "  I           Show / hide auto-ignored items",
                "  /           Filter mode",
                "  ESC         Clear filter",
                "  ENTER       Save .graphifyignore",
                "  Q           Quit without saving",
                "  ?           Toggle this help",
            ):
                print(line)

        all_flat = _flatten(entries)
        tracked = [e for e in all_flat if not e.excluded and not e.is_dir]
        ignored = sum(1 for e in all_flat if e.excluded)
        breakdown = _file_type_breakdown(all_flat)
        bkd_str = ", ".join(f"{k}: {v}" for k, v in sorted(breakdown.items(), key=lambda x: -x[1]))
        est = _estimate_build_time(tracked)
        print(f"\n  {_G}Tracked: {len(tracked)}{_R}  {_DI}Ignored: {ignored}{_R}  |  {bkd_str or 'no source files'}")
        print(f"  Est. build: {est:.0f}s  |  {'showing' if show_ignored else 'hiding'} auto-ignored")

    while True:
        _render()
        ch = _getch()
        visible = _visible()
        n = len(visible)

        if filtering:
            if ch == "\x1b":
                filtering, filter_str = False, ""
            elif ch in ("\r", "\n"):
                filtering = False
            elif ch in ("\x7f", "\x08"):
                filter_str = filter_str[:-1]
            elif len(ch) == 1 and ch.isprintable():
                filter_str += ch
            elif ch == "\x1b[A" and n > 0:
                cursor = max(0, cursor - 1)
            elif ch == "\x1b[B" and n > 0:
                cursor = min(n - 1, cursor + 1)
            continue

        if ch == "\x1b[A" and n > 0:
            cursor = max(0, cursor - 1)
        elif ch == "\x1b[B" and n > 0:
            cursor = min(n - 1, cursor + 1)
        elif ch == " " and 0 <= cursor < n:
            e = visible[cursor]
            e.excluded = not e.excluded
            e.auto_detected = False
            if e.is_dir and e.expanded and e.children:
                _cascade(e, e.excluded, project_root)
        elif ch.lower() == "e" and 0 <= cursor < n:
            e = visible[cursor]
            if e.is_dir:
                if not e.expanded:
                    _expand_entry(e, project_root)
                e.expanded = not e.expanded
        elif ch.lower() == "a":
            for e in visible:
                e.excluded, e.auto_detected = False, False
        elif ch.lower() == "n":
            for e in visible:
                e.excluded = True
        elif ch.lower() == "f" and 0 <= cursor < n:
            e = visible[cursor]
            if e.is_dir and e.expanded and e.children:
                new_state = any(c.excluded for c in e.children if not c.is_dir)
                for c in e.children:
                    if not c.is_dir:
                        c.excluded = not new_state
        elif ch.lower() == "r":
            for e in _flatten(entries):
                e.reset_to_default(project_root)
        elif ch.lower() == "i":
            show_ignored = not show_ignored
        elif ch == "/":
            filtering, filter_str = True, ""
        elif ch == "\x1b":
            if filter_str:
                filter_str = ""
        elif ch == "?":
            show_help = not show_help
        elif ch in ("\r", "\n"):
            warns = _validate_selection(entries, project_root, lang)
            if warns:
                print()
                for w in warns:
                    print(f"  {_Y}Warning:{_R} {w}")
                print()
            if _confirm("Save .graphifyignore? [Y/n]"):
                return True
        elif ch.lower() == "q":
            if _confirm("Quit without saving? [y/N]"):
                return False


# ── Public entry point ────────────────────────────────────────────────────────

def interactive_init(project_root: Path) -> Path | None:
    entries = scan_directory(project_root)
    lang = _detect_language(project_root)

    if not sys.stdin.isatty() or os.environ.get("GRAPHIFY_AUTO"):
        print(f"  Non-interactive — applying smart defaults for {lang} project.")
        return auto_init(project_root)

    rows, cols = _term_size()
    if rows < _MIN_ROWS or cols < _MIN_COLS:
        print(f"  Terminal too small ({cols}×{rows}) — using auto-detection.")
        return auto_init(project_root)

    auto_count = sum(1 for e in entries if e.auto_detected)
    print(f"\n  {_B}{_CY}Graphify Init{_R} — {lang} project")
    print(f"  {_DI}Auto-detected {auto_count} standard exclusion(s).{_R}\n")

    saved = _try_questionary(project_root, entries)

    if not saved:
        try:
            import termios
            confirmed = _raw_tui(project_root, entries)
            if not confirmed:
                print("\n  Aborted — no changes made.")
                return None
            saved = True
        except (ImportError, AttributeError):
            print("  Terminal not supported — using auto-detection.")
            return auto_init(project_root)

    if saved:
        dest = _write_graphifyignore(project_root, entries)
        flat = _flatten(entries)
        tracked = sum(1 for e in flat if not e.excluded and not e.is_dir)
        ignored = sum(1 for e in flat if e.excluded)
        print(f"\n  Saved: {dest}")
        print(f"  Tracking {_G}{tracked}{_R} files, ignoring {_DI}{ignored}{_R} items.\n")
        for w in _validate_selection(entries, project_root, lang):
            print(f"  {_CY}Note:{_R} {w}")
        print()
        return dest

    return None


__all__ = ["interactive_init", "auto_init", "Entry", "scan_directory"]
