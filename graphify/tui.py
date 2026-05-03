"""
tui.py — Interactive Terminal UI for .graphifyignore initialisation.
Triggered automatically on first run and re-openable via: graphify ignore

Controls:
  UP/DOWN or k/j  Navigate        SPACE  Toggle include/exclude
  E               Expand/collapse dir    A  Include all visible
  N               Exclude all visible    F  Toggle files in cursor dir
  R               Reset to defaults      I  Show/hide auto-ignored
  /               Filter mode            ESC  Clear filter
  ENTER           Save & exit            Q  Quit without saving
  ?               Toggle help
"""
from __future__ import annotations

import logging
import os
import select
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("graphify.tui")

_BUILD_MS_PER_FILE: int = 200
_GETCH_TIMEOUT: float = 0.05
_WARN_FILE_COUNT: int = 500
_CRIT_FILE_COUNT: int = 2000
_MIN_ROWS: int = 8
_MIN_COLS: int = 40
_SCAN_MAX_DEPTH: int = 4

_G = "\033[32m"
_DI = "\033[2m"
_Y = "\033[33m"
_B = "\033[1m"
_CY = "\033[36m"
_R = "\033[0m"
_M = "\033[35m"


def _clear_screen() -> None:
    os.system("cls" if sys.platform == "win32" else "clear")


def _term_size() -> tuple[int, int]:
    try:
        sz = os.get_terminal_size()
        return sz.lines, sz.columns
    except OSError:
        return 24, 80


def _load_ignore_constants() -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    try:
        from graphify import ingest as _ingest
        dirs = getattr(_ingest, "IGNORE_DIRS", None)
        exts = getattr(_ingest, "IGNORE_EXTS", None)
        dots = getattr(_ingest, "VISIBLE_DOTFILES", None)
        if dirs and exts:
            return frozenset(dirs), frozenset(exts), frozenset(dots) if dots else _DEFAULT_VISIBLE_DOTFILES
    except ImportError:
        pass
    return _DEFAULT_IGNORE_DIRS, _DEFAULT_IGNORE_EXTS, _DEFAULT_VISIBLE_DOTFILES


_DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset({
    "venv", ".venv", "env", ".env", "ENV", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", ".eggs", "htmlcov", ".hypothesis",
    "node_modules", ".yarn", ".npm", ".next", ".nuxt", ".parcel-cache",
    ".turbo", "coverage",
    ".git", ".hg", ".svn", ".bzr", "_darcs",
    "dist", "build", "target", "out", "bin", "obj", ".build",
    "cmake-build-debug", "cmake-build-release", "Debug", "Release", "x64", "x86",
    ".idea", ".vscode", ".vs", ".fleet", ".zed", ".nova", ".kdev4", ".metadata", ".settings",
    ".gradle", "gradle", ".bundle", "vendor", "_build", "deps", ".elixir_ls",
    ".stack-work", "dist-newstyle", ".cabal-sandbox", ".build", ".swiftpm",
    ".dart_tool", ".pub", ".bloop", ".metals",
    "Library", "Temp", "Obj", "Logs", "Binaries", "DerivedDataCache",
    "Intermediate", "Saved", ".Rproj.user", ".ipynb_checkpoints",
    "migrations", "__snapshots__", "graphify-out", ".graphify",
    ".cache", "tmp", "temp", "logs", "log",
})

_DEFAULT_IGNORE_EXTS: frozenset[str] = frozenset({
    ".pyc", ".pyo", ".pyd", ".so", ".dylib", ".dll", ".egg",
    ".o", ".obj", ".a", ".lib", ".exe", ".out", ".class", ".jar",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".bmp", ".tiff", ".raw", ".psd", ".ai", ".eps", ".heic",
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm",
    ".mp3", ".wav", ".aac", ".ogg", ".flac", ".wma", ".m4a",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar", ".tgz",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp", ".db", ".sqlite", ".sqlite3", ".mdb", ".accdb",
    ".lock", ".sum", ".hash", ".map", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".bin", ".dat", ".pak", ".wasm", ".whl", ".gem",
})

_DEFAULT_VISIBLE_DOTFILES: frozenset[str] = frozenset({
    ".graphifyignore", ".env", ".envrc", ".python-version",
    ".nvmrc", ".ruby-version", ".node-version",
})

_DEFAULT_IGNORE_FILES: frozenset[str] = frozenset({
    ".gitignore", ".gitattributes", ".gitmodules",
    "LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING", "COPYING.txt",
    "CHANGELOG.md", "CHANGELOG.txt", "CHANGES.md", "HISTORY.md",
    "CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "AUTHORS", "CONTRIBUTORS",
    "SECURITY.md", "SUPPORT.md", "FUNDING.yml",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Gemfile.lock", "composer.lock", "Cargo.lock", "poetry.lock", "Pipfile.lock",
    "uv.lock", "bun.lockb",
    ".env", ".env.local", ".env.development", ".env.production", ".env.test",
    ".DS_Store", "Thumbs.db", "desktop.ini",
    ".editorconfig", ".prettierrc", ".eslintrc", ".stylelintrc",
    "Makefile", "CMakeLists.txt", "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "requirements-dev.txt", "requirements-test.txt", "dev-requirements.txt",
})
_DEFAULT_IGNORE_FILES_LOWER: frozenset[str] = frozenset(f.lower() for f in _DEFAULT_IGNORE_FILES)

IGNORE_DIRS, IGNORE_EXTS, VISIBLE_DOTFILES = _load_ignore_constants()


def _detect_language(project_root: Path) -> str:
    try:
        from graphify import detect as _detect
        fn = getattr(_detect, "detect_language", None)
        if callable(fn):
            return fn(project_root)
    except ImportError:
        pass
    indicators = {
        "Python": ["pyproject.toml", "setup.py", "requirements.txt", "Pipfile"],
        "JavaScript": ["package.json", "yarn.lock", "package-lock.json"],
        "TypeScript": ["tsconfig.json"],
        "Go": ["go.mod"],
        "Rust": ["Cargo.toml"],
        "Java": ["pom.xml", "build.gradle"],
    }
    for lang, files in indicators.items():
        if any((project_root / f).exists() for f in files):
            return lang
    return "Unknown"


_LANG_MANIFESTS: dict[str, list[str]] = {
    "Python": ["pyproject.toml", "setup.py", "requirements.txt"],
    "JavaScript": ["package.json"],
    "TypeScript": ["tsconfig.json", "package.json"],
    "Go": ["go.mod"],
    "Rust": ["Cargo.toml"],
    "Java": ["pom.xml", "build.gradle"],
}


def _default_excluded(path: Path, project_root: Path) -> bool:
    try:
        parts = path.relative_to(project_root).parts
    except ValueError:
        return False
    for part in parts:
        clean = part.rstrip("/")
        if clean in IGNORE_DIRS or clean.endswith((".egg-info", ".dist-info")):
            return True
    if path.is_file():
        if path.suffix.lower() in IGNORE_EXTS:
            return True
        if path.name.lower() in _DEFAULT_IGNORE_FILES_LOWER:
            return True
    for part in parts:
        if part.startswith(".") and part not in VISIBLE_DOTFILES:
            return True
    return False


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _estimate_build_time(tracked: list[Entry]) -> float:
    return max(1.0, len(tracked) * _BUILD_MS_PER_FILE / 1000.0) if tracked else 0.0


def _file_type_breakdown(entries: list[Entry]) -> dict[str, int]:
    ext_map = {
        ".py": "Python", ".pyx": "Cython", ".pyi": "Python",
        ".js": "JS", ".mjs": "JS", ".jsx": "JS", ".cjs": "JS",
        ".ts": "TS", ".tsx": "TS",
        ".go": "Go", ".rs": "Rust", ".java": "Java",
        ".kt": "Kotlin", ".swift": "Swift", ".scala": "Scala",
        ".rb": "Ruby", ".php": "PHP", ".ex": "Elixir", ".exs": "Elixir",
        ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++", ".cc": "C++",
        ".cs": "C#", ".fs": "F#",
        ".r": "R", ".jl": "Julia", ".lua": "Lua", ".pl": "Perl",
        ".md": "Markdown", ".rst": "Markdown", ".txt": "Text",
        ".toml": "Config", ".yaml": "Config", ".yml": "Config",
        ".json": "Config", ".cfg": "Config", ".ini": "Config",
        ".xml": "Config", ".properties": "Config",
    }
    counts: dict[str, int] = {}
    for e in entries:
        if e.effective_excluded or e.is_dir:
            continue
        label = ext_map.get(e.path.suffix.lower(), "Other")
        counts[label] = counts.get(label, 0) + 1
    return counts


@dataclass
class Entry:
    path: Path
    relative: str
    is_dir: bool
    excluded: bool
    auto: bool
    user: bool = False
    expanded: bool = False
    children: list[Entry] = field(default_factory=list)
    depth: int = 0
    parent: Entry | None = None

    @property
    def effective_excluded(self) -> bool:
        if self.excluded:
            return True
        p = self.parent
        while p:
            if p.excluded:
                return True
            p = p.parent
        return False

    @property
    def effective_auto(self) -> bool:
        if self.excluded:
            return self.auto
        p = self.parent
        while p:
            if p.excluded:
                return p.auto
            p = p.parent
        return False

    @property
    def icon(self) -> str:
        if not self.is_dir or not self.children:
            return " "
        return "▼" if self.expanded else "▶"

    @property
    def check(self) -> str:
        return "[-]" if self.effective_excluded else "[+]"

    @property
    def color(self) -> str:
        if self.effective_excluded:
            return _Y if self.user else _DI
        return _G

    def reset(self, project_root: Path) -> None:
        self.excluded = _default_excluded(self.path, project_root)
        self.auto = self.excluded
        self.user = False
        for c in self.children:
            c.reset(project_root)


def scan_directory(project_root: Path, max_depth: int = _SCAN_MAX_DEPTH) -> list[Entry]:
    def _scan(path: Path, depth: int) -> list[Entry]:
        result: list[Entry] = []
        try:
            items = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            logger.warning("Permission denied scanning %s", path)
            return []
        for item in items:
            if item.name in (".", "..") or item.is_symlink():
                continue
            rel = _safe_relative(item, project_root)
            is_dir = item.is_dir()
            excluded = _default_excluded(item, project_root)
            entry = Entry(
                path=item, relative=rel, is_dir=is_dir,
                excluded=excluded, auto=excluded, depth=depth,
            )
            if is_dir and depth < max_depth:
                entry.children = _scan(item, depth + 1)
                for c in entry.children:
                    c.parent = entry
            result.append(entry)
        return result

    return _scan(project_root, 0)


def _flatten(entries: list[Entry]) -> list[Entry]:
    result: list[Entry] = []
    stack = list(reversed(entries))
    while stack:
        e = stack.pop()
        result.append(e)
        if e.is_dir and e.children:
            stack.extend(reversed(e.children))
    return result


def _visible_flatten(entries: list[Entry]) -> list[Entry]:
    result: list[Entry] = []
    stack = list(reversed(entries))
    while stack:
        e = stack.pop()
        result.append(e)
        if e.is_dir and e.expanded and e.children:
            stack.extend(reversed(e.children))
    return result


def _cascade(entry: Entry, excluded: bool) -> None:
    for child in entry.children:
        child.excluded = excluded
        child.user = True
        child.auto = False
        if child.is_dir and child.children:
            _cascade(child, excluded)


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
            if not e.excluded:
                continue
            if e.is_dir:
                if e.path in excluded_dirs:
                    continue
                excluded_dirs.add(e.path)
            parent_excluded = any(e.path.is_relative_to(d) for d in excluded_dirs if d != e.path)
            if parent_excluded:
                continue

            if e.auto and not e.user:
                if e.is_dir:
                    auto_dirs.add(e.path.name + "/")
                elif e.path.suffix:
                    auto_exts.add("*" + e.path.suffix.lower())
                else:
                    auto_paths.append(e.relative)
            else:
                user_paths.append(e.relative + ("/" if e.is_dir else ""))

            if e.is_dir and e.children:
                _collect(e.children)

    _collect(entries)

    def _section(header: str, patterns: set[str] | list[str]) -> None:
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


def _validate_selection(entries: list[Entry], project_root: Path, lang: str) -> list[str]:
    flat = _flatten(entries)
    tracked = [e for e in flat if not e.effective_excluded and not e.is_dir]
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
            if any(e.relative == manifest and e.excluded and not e.auto for e in flat):
                warnings.append(f"{manifest} is excluded — graphify won't detect dependency edges.")

    src_exts: dict[str, tuple[str, ...]] = {
        "Python": (".py",), "JavaScript": (".js", ".mjs"),
        "TypeScript": (".ts", ".tsx"), "Go": (".go",),
        "Rust": (".rs",), "Java": (".java",),
    }
    src = src_exts.get(lang)
    if src and not any(e.path.suffix in src and not e.effective_excluded for e in flat):
        warnings.append(f"No {lang} source files are tracked — the graph will have no code structure.")

    return warnings


def auto_init(project_root: Path) -> Path:
    entries = scan_directory(project_root)
    lang = _detect_language(project_root)
    warns = _validate_selection(entries, project_root, lang)
    for w in warns:
        logger.info("auto-init: %s", w)
    dest = _write_graphifyignore(project_root, entries)
    flat = _flatten(entries)
    tracked = sum(1 for e in flat if not e.effective_excluded and not e.is_dir)
    ignored = sum(1 for e in flat if e.effective_excluded)
    print(f"  Auto-ignored {ignored} items in {lang} project ({tracked} tracked).")
    print(f"  Saved: {dest}")
    return dest


def _try_questionary(project_root: Path, entries: list[Entry]) -> bool:
    try:
        import questionary
    except ImportError:
        return False

    def _choices(elist: list[Entry], prefix: str = "") -> list:
        out: list = []
        for e in elist:
            name = e.relative.split("/")[-1] + ("/" if e.is_dir else "")
            tag = "  (auto)" if e.auto else ""
            out.append(questionary.Choice(
                title=f"{prefix}{name}{tag}",
                value=e.relative,
                checked=not e.excluded,
            ))
            if e.is_dir and e.children:
                out.extend(_choices(e.children, prefix + "  "))
        return out

    choices = _choices(entries)
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

    def _apply(elist: list[Entry]) -> None:
        for e in elist:
            e.excluded = e.relative not in selected_set
            if e.is_dir and e.children:
                _apply(e.children)

    _apply(entries)
    return True


def _getch() -> str:
    import termios, tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch == "\x1b":
            seq = ""
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], _GETCH_TIMEOUT)
                if not ready:
                    break
                seq += sys.stdin.read(1)
            if not seq:
                return "\x1b"
            mapping = {
                "[A": "UP", "[B": "DOWN", "[C": "RIGHT", "[D": "LEFT",
                "OA": "UP", "OB": "DOWN", "OC": "RIGHT", "OD": "LEFT",
                "[5~": "PAGEUP", "[6~": "PAGEDOWN",
                "[H": "HOME", "[F": "END", "OH": "HOME", "OF": "END",
            }
            for prefix, name in mapping.items():
                if seq.startswith(prefix):
                    return name
            return f"\\x1b{seq}"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _confirm(message: str) -> bool:
    print(f"\n  {_Y}{message}{_R} ", end="", flush=True)
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


def _raw_tui(project_root: Path, entries: list[Entry]) -> bool:
    cursor = 0
    filter_str = ""
    filtering = False
    show_ignored = True
    show_help = False
    lang = _detect_language(project_root)

    def _visible() -> list[Entry]:
        if filter_str:
            flat = _flatten(entries)
            return [e for e in flat if filter_str.lower() in e.relative.lower()]
        flat = _visible_flatten(entries)
        if not show_ignored:
            flat = [e for e in flat if not (e.effective_excluded and e.effective_auto)]
        return flat

    def _render() -> None:
        nonlocal cursor
        _clear_screen()
        visible = _visible()
        rows, cols = _term_size()
        content_rows = max(2, rows - 10)
        n = len(visible)

        if n == 0:
            cursor = 0
        else:
            cursor = max(0, min(n - 1, cursor))

        if rows < 14:
            print(f"{_B}{_M}  Graphify — Select scope{_R}  ({lang})")
            if not filtering and not show_help:
                print(f"  {_G}[+]{_R}=track {_DI}[-]{_R}=ignore {_Y}[-]{_R}=user  {_DI}?:help{_R}")
        else:
            print(f"{_B}{_M}  Graphify — Select files to TRACK in the knowledge graph{_R}")
            if filtering:
                print(f"  {_CY}FILTER{_R}  type to filter  ESC/Enter to exit  UP/DOWN to navigate")
            elif show_help:
                print(f"  {_CY}HELP{_R}  press ? to close")
            else:
                print(f"  {_G}[+]{_R}=tracked  {_DI}[-]{_R}=ignored  {_Y}[-]{_R}=user-ignored  "
                      f"{_DI}UP/DOWN/k/j:nav  SPACE:toggle  E:expand  A:all  N:none  F:files  "
                      f"R:reset  I:auto-view  /:filter  ?:help  ENTER:save  Q:quit{_R}")
        print(f"  {'─' * min(70, cols - 4)}")

        if n == 0:
            print(f"  {_DI}No items match filter{_R}")
        else:
            start = max(0, min(cursor - content_rows // 2, n - content_rows))
            end = min(n, start + content_rows)

            if start > 0:
                print(f"  {_DI}↑ {start} more{_R}")

            for i, e in enumerate(visible[start:end]):
                abs_i = start + i
                is_cur = abs_i == cursor
                prefix = f"  {_Y}>{_R}" if is_cur else "   "
                color = e.color
                indent = "  " * e.depth
                name = e.relative.split("/")[-1]
                if e.is_dir:
                    name += "/"
                tag = ""
                if e.effective_excluded:
                    if e.excluded:
                        if e.auto and not e.user:
                            tag = f"  {_DI}(auto){_R}"
                        else:
                            tag = f"  {_Y}(user){_R}"
                    else:
                        tag = f"  {_DI}(inherited){_R}"
                print(f"{prefix} {color}{e.check}{_R} {indent}{e.icon} {color}{name}{_R}{tag}")

            if end < n:
                print(f"  {_DI}↓ {n - end} more{_R}")

        if filter_str:
            print(f"\n  {_CY}Filter: {filter_str}{_R}  (ESC to clear)")

        if show_help:
            print()
            for line in (
                f"  {_B}Key Bindings{_R}",
                "  UP / DOWN / k / j   Navigate",
                "  SPACE               Toggle include / exclude",
                "  E                   Expand / collapse directory",
                "  A                   Include all visible items",
                "  N                   Exclude all visible items",
                "  F                   Toggle files in cursor directory",
                "  R                   Reset to smart defaults",
                "  I                   Show / hide auto-ignored items",
                "  /                   Filter mode",
                "  ESC                 Clear filter",
                "  ENTER               Save .graphifyignore",
                "  Q                   Quit without saving",
                "  ?                   Toggle this help",
            ):
                print(line)

        all_flat = _flatten(entries)
        tracked = [e for e in all_flat if not e.effective_excluded and not e.is_dir]
        ignored_files = sum(1 for e in all_flat if e.effective_excluded and not e.is_dir)
        ignored_dirs = sum(1 for e in all_flat if e.effective_excluded and e.is_dir)
        breakdown = _file_type_breakdown(all_flat)
        bkd_str = ", ".join(f"{k}:{v}" for k, v in sorted(breakdown.items(), key=lambda x: -x[1]))
        est = _estimate_build_time(tracked)
        print(f"\n  {_G}Tracked files: {len(tracked)}{_R}  "
              f"{_DI}Ignored: {ignored_files} files, {ignored_dirs} dirs{_R}")
        print(f"  {bkd_str or 'no source files'}  |  Est. build: {est:.0f}s  "
              f"|  {'showing' if show_ignored else 'hiding'} auto-ignored")

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
            elif ch in ("UP", "k") and n > 0:
                cursor = max(0, cursor - 1)
            elif ch in ("DOWN", "j") and n > 0:
                cursor = min(n - 1, cursor + 1)
            continue

        if ch in ("UP", "k") and n > 0:
            cursor = max(0, cursor - 1)
        elif ch in ("DOWN", "j") and n > 0:
            cursor = min(n - 1, cursor + 1)
        elif ch == "PAGEUP" and n > 0:
            cursor = max(0, cursor - 10)
        elif ch == "PAGEDOWN" and n > 0:
            cursor = min(n - 1, cursor + 10)
        elif ch == "HOME" and n > 0:
            cursor = 0
        elif ch == "END" and n > 0:
            cursor = n - 1
        elif ch == " " and 0 <= cursor < n:
            e = visible[cursor]
            e.excluded = not e.excluded
            e.user = True
            e.auto = False
            if e.is_dir:
                _cascade(e, e.excluded)
        elif ch.lower() == "e" and 0 <= cursor < n:
            e = visible[cursor]
            if e.is_dir:
                e.expanded = not e.expanded
        elif ch == "RIGHT" and 0 <= cursor < n:
            e = visible[cursor]
            if e.is_dir and not e.expanded:
                e.expanded = True
        elif ch == "LEFT" and 0 <= cursor < n:
            e = visible[cursor]
            if e.is_dir and e.expanded:
                e.expanded = False
        elif ch.lower() == "a":
            for e in visible:
                if e.excluded:
                    e.excluded = False
                    e.user = True
                    e.auto = False
                    if e.is_dir:
                        _cascade(e, False)
        elif ch.lower() == "n":
            for e in visible:
                if not e.excluded:
                    e.excluded = True
                    e.user = True
                    e.auto = False
                    if e.is_dir:
                        _cascade(e, True)
        elif ch.lower() == "f" and 0 <= cursor < n:
            e = visible[cursor]
            if e.is_dir and e.children:
                files = [c for c in e.children if not c.is_dir]
                if files:
                    new_state = not any(f.excluded for f in files)
                    for f in files:
                        f.excluded = new_state
                        f.user = True
                        f.auto = False
        elif ch.lower() == "r":
            for e in _flatten(entries):
                e.reset(project_root)
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

    auto_count = sum(1 for e in _flatten(entries) if e.auto)
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
        tracked = sum(1 for e in flat if not e.effective_excluded and not e.is_dir)
        ignored = sum(1 for e in flat if e.effective_excluded)
        print(f"\n  Saved: {dest}")
        print(f"  Tracking {_G}{tracked}{_R} files, ignoring {_DI}{ignored}{_R} items.\n")
        for w in _validate_selection(entries, project_root, lang):
            print(f"  {_CY}Note:{_R} {w}")
        print()
        return dest

    return None


__all__ = ["interactive_init", "auto_init", "Entry", "scan_directory"]
