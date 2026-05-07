"""
tui.py — Interactive Terminal UI for .graphifyignore initialisation.
Triggered automatically on first run and re-openable via: graphify ignore

Controls:
  UP/DOWN or k/j  Navigate        SPACE  Toggle include/exclude
  E or RIGHT      Lock-expand dir  LEFT  Collapse dir / jump to parent
  A               Include all visible    N  Exclude all visible
  F               Toggle files in cursor dir
  R               Reset to defaults      I  Show/hide auto-ignored
  /               Filter mode            ESC  Clear filter
  ENTER           Save & exit            Q  Quit without saving
  ?               Toggle help
"""
from __future__ import annotations

import fnmatch
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
_MAX_FILE_SIZE: int = 1024 * 1024

_G = "\033[32m"
_DI = "\033[2m"
_Y = "\033[33m"
_B = "\033[1m"
_CY = "\033[36m"
_R = "\033[0m"
_M = "\033[35m"
_W = "\033[97m"
_BG_CY = "\033[46m"
_BG_BL = "\033[44m"


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


_ALWAYS_IGNORE_DIRS: frozenset[str] = frozenset({
    "venv", ".venv", "env", ".env", "ENV", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", ".eggs", "htmlcov", ".hypothesis",
    "node_modules", ".yarn", ".npm", ".next", ".nuxt", ".parcel-cache",
    ".turbo", "coverage", ".nyc_output",
    ".git", ".hg", ".svn", ".bzr", "_darcs", ".git-rewrite",
    "dist", "build", "target", "out", "bin", "obj", ".build",
    "cmake-build-debug", "cmake-build-release", "Debug", "Release", "x64", "x86",
    ".idea", ".vscode", ".vs", ".fleet", ".zed", ".nova", ".kdev4", ".metadata", ".settings",
    ".gradle", "gradle", ".bundle", "vendor", "_build", "deps", ".elixir_ls",
    ".stack-work", "dist-newstyle", ".cabal-sandbox", ".swiftpm",
    ".dart_tool", ".pub", ".bloop", ".metals",
    "Library", "Temp", "Obj", "Logs", "Binaries", "DerivedDataCache",
    "Intermediate", "Saved", ".Rproj.user", ".ipynb_checkpoints",
    "migrations", "__snapshots__", "graphify-out", ".graphify",
    ".cache", "tmp", "temp", "logs", "log", ".tmp",
})

_ALWAYS_IGNORE_EXTS: frozenset[str] = frozenset({
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

_GRAPH_IGNORE_DIRS: frozenset[str] = frozenset({
    "docs", "doc", "documentation", "wiki", "guides", "tutorials",
    "test", "tests", "testing", "__tests__", "test-fixtures", "fixtures",
    "spec", "specs", "e2e", "integration-tests", "unit-tests",
    "examples", "example", "demo", "demos", "samples", "sample",
    "qa", "quality", "benchmark", "benchmarks", "perf", "performance",
    "scripts", "tools", "tooling", "ci", ".github", ".gitlab",
    "stories", "storybook", ".storybook",
    "mocks", "mock", "fake", "fakes", "stubs",
})

_GRAPH_IGNORE_PATTERNS: tuple[str, ...] = (
    "README*", "CHANGELOG*", "CHANGES*", "HISTORY*", "NEWS*",
    "LICENSE*", "LICENCE*", "COPYING*", "AUTHORS*", "CONTRIBUTORS*",
    "CONTRIBUTING*", "CODE_OF_CONDUCT*", "SECURITY*", "SUPPORT*",
    "FUNDING*", "BACKERS*", "CREDITS*", "THANKS*",
    "INSTALL*", "SETUP*", "BUILDING*", "COMPILING*",
    "TODO*", "ROADMAP*", "VERSION*", "RELEASES*",
    "Makefile*", "CMakeLists*", "Dockerfile*", "docker-compose*",
    ".gitignore", ".gitattributes", ".gitmodules", ".gitkeep",
    ".editorconfig", ".prettierrc*", ".eslintrc*", ".stylelintrc*",
    ".babelrc*", ".browserslistrc", ".nvmrc", ".ruby-version", ".python-version",
    ".dockerignore", ".mailmap", ".jscpd.json", ".detect-secrets.cfg",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Gemfile.lock", "composer.lock", "Cargo.lock", "poetry.lock", "Pipfile.lock",
    "uv.lock", "bun.lockb", "Package.resolved",
    ".env*", ".DS_Store", "Thumbs.db", "desktop.ini",
    "*.min.js", "*.min.css", "*.bundle.js", "*.bundle.css",
    "*test*", "*spec*", "*fixture*", "*mock*", "*stub*",
)

_DEFAULT_VISIBLE_DOTFILES: frozenset[str] = frozenset({
    ".graphifyignore", ".env", ".envrc", ".python-version",
    ".nvmrc", ".ruby-version", ".node-version",
})

_DEFAULT_IGNORE_DIRS = _ALWAYS_IGNORE_DIRS | _GRAPH_IGNORE_DIRS
_DEFAULT_IGNORE_EXTS = _ALWAYS_IGNORE_EXTS

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
        "Swift": ["Package.swift"],
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
    "Swift": ["Package.swift"],
}


def _default_excluded(path: Path, project_root: Path) -> bool:
    try:
        parts = path.relative_to(project_root).parts
    except ValueError:
        return False

    name = path.name
    name_lower = name.lower()
    suffix = path.suffix.lower()

    for part in parts:
        clean = part.rstrip("/")
        if clean in _ALWAYS_IGNORE_DIRS or clean.endswith((".egg-info", ".dist-info")):
            return True
        if clean in _GRAPH_IGNORE_DIRS:
            return True

    if suffix in _ALWAYS_IGNORE_EXTS:
        return True

    if path.is_file():
        if name_lower in _DEFAULT_IGNORE_FILES_LOWER:
            return True
        try:
            if path.stat().st_size > _MAX_FILE_SIZE:
                return True
        except OSError:
            pass

    for pattern in _GRAPH_IGNORE_PATTERNS:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(name_lower, pattern.lower()):
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


def _set_node_state(node: Entry, exclude: bool) -> None:
    """
    Atomic tree state setter. Handles intelligent cascading & parent materialization
    so you can un-ignore granular files without un-ignoring their siblings.
    """
    if node.effective_excluded == exclude:
        return
        
    def _casc(n: Entry, excl: bool, usr: bool, auto: bool):
        n.excluded = excl
        n.user = usr
        n.auto = auto
        for c in n.children:
            _casc(c, excl, usr, auto)

    if exclude:
        _casc(node, True, True, False)
    else:
        # User wants to track this node.
        # Ensure all parents up to the root are tracked.
        curr = node
        while curr.parent:
            p = curr.parent
            if p.excluded:
                # Materialize the ignores on siblings before lifting the parent's ignore
                for c in p.children:
                    if c is not curr and c.effective_excluded:
                        _casc(c, True, c.user or p.user, c.auto or p.auto)
                p.excluded = False
                p.user = True
                p.auto = False
            curr = p
        
        # Track the node and cascade
        _casc(node, False, True, False)


def _write_graphifyignore(project_root: Path, entries: list[Entry]) -> Path:
    lines = [
        "# .graphifyignore — generated by graphify init",
        "# Syntax: one pattern per line. Same format as .gitignore.",
        "",
    ]
    
    flat = _flatten(entries)
    
    # Prevent Wildcard Overreach: 
    # Don't use `*.md` if the user explicitly tracked `README.md`.
    tracked_exts = {e.path.suffix.lower() for e in flat if not e.effective_excluded and not e.is_dir and e.path.suffix}
    tracked_dir_names = {e.path.name for e in flat if not e.effective_excluded and e.is_dir}
    
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
                    
                    if e.auto and not e.user and e.path.name not in tracked_dir_names:
                        auto_dirs.add(e.path.name + "/")
                    else:
                        user_paths.append(e.relative + "/")
                else:
                    ext = e.path.suffix.lower()
                    if e.auto and not e.user and ext and ext not in tracked_exts:
                        auto_exts.add("*" + ext)
                    else:
                        auto_paths.append(e.relative) if e.auto and not e.user else user_paths.append(e.relative)
                
                # Crucial Fix: Node is strictly excluded. Ignore children.
                continue
            
            # Crucial Fix: Node is tracked. MUST investigate children for specific ignores!
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
        for e in _flatten(elist):
            target_exclude = e.relative not in selected_set
            if e.excluded != target_exclude:
                _set_node_state(e, target_exclude)

    _apply(entries)
    return True


def _getch() -> str:
    """Read a single keypress; return named strings for special keys."""
    import termios, tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        buf = os.read(fd, 1)
        if not buf:
            return ""
        if buf == b"\x03":
            raise KeyboardInterrupt
        if buf == b"\x1b":
            ready, _, _ = select.select([fd], [], [], _GETCH_TIMEOUT)
            if ready:
                extra = os.read(fd, 10)
                buf += extra
                while True:
                    ready2, _, _ = select.select([fd], [], [], 0.02)
                    if not ready2:
                        break
                    more = os.read(fd, 10)
                    if not more:
                        break
                    buf += more
        ch = buf.decode("latin-1", errors="ignore")
        if len(ch) > 1 and ch[0] == "\x1b":
            seq = ch[1:]
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
            buf = os.read(fd, 1)
            if buf == b"\x03":
                print()
                raise KeyboardInterrupt
            ch = buf.decode("latin-1", errors="ignore")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        print(ch)
        return ch.lower() in ("y", "\r", "\n")
    except KeyboardInterrupt:
        print()
        raise
    except Exception:
        return True


# -----------------------------------------------------------------
#  DETERMINISTIC FRACTAL NAVIGATION MACHINE
# -----------------------------------------------------------------

@dataclass
class NavState:
    cursor_node: Entry | None = None
    locked: Entry | None = None


def _is_in_subtree(node: Entry, ancestor: Entry) -> bool:
    """True if `node` is strictly contained inside `ancestor` or is `ancestor` itself."""
    curr = node
    while curr:
        if curr is ancestor:
            return True
        curr = curr.parent
    return False


def _visible_entries(roots: list[Entry], cursor_node: Entry | None, locked: Entry | None, show_ignored: bool, filter_str: str) -> list[Entry]:
    """
    Builds the flat tree recursively.
    A folder expands automatically if it contains either the `locked` node or the `cursor_node`.
    """
    flat: list[Entry] = []

    def _walk(node: Entry) -> None:
        if filter_str and filter_str.lower() not in node.relative.lower():
            return
        if not show_ignored and node.effective_excluded and node.effective_auto:
            return

        flat.append(node)

        if node.is_dir and node.children:
            should_expand = False
            
            if locked and _is_in_subtree(locked, node):
                should_expand = True
            elif cursor_node and _is_in_subtree(cursor_node, node):
                should_expand = True

            if should_expand:
                for child in node.children:
                    _walk(child)

    for root in roots:
        _walk(root)
    return flat


def _icon(entry: Entry, state: NavState) -> str:
    """Accurately reflect state based on subtree containment."""
    if not entry.is_dir or not entry.children:
        return " "
    if state.locked and _is_in_subtree(state.locked, entry):
        return "▼"
    if state.cursor_node and _is_in_subtree(state.cursor_node, entry):
        return "▼"
    return "▶"


def _get_valid_node(target: Entry | None, fallback_idx: int, roots: list[Entry], locked: Entry | None, show_ignored: bool, filter_str: str) -> Entry | None:
    """Failsafe to prevent cursor index desync when filtering / toggling visibility."""
    vis = _visible_entries(roots, target, locked, show_ignored, filter_str)
    if not vis: return None
    if target in vis: return target
    return vis[max(0, min(fallback_idx, len(vis) - 1))]


def _move_cursor(delta: int, roots: list[Entry], state: NavState, show_ignored: bool, filter_str: str) -> None:
    """
    Moves the cursor while handling Free Navigation skips dynamically.
    Skips the children of an expanded node UNLESS you explicitly locked it.
    """
    visible = _visible_entries(roots, state.cursor_node, state.locked, show_ignored, filter_str)
    if not visible:
        return

    try:
        idx = visible.index(state.cursor_node)
    except ValueError:
        idx = 0

    step = 1 if delta > 0 else -1
    target_idx = idx

    for _ in range(abs(delta)):
        next_idx = target_idx + step

        if step == 1:
            curr_node = visible[target_idx]
            if curr_node.is_dir and not (state.locked and _is_in_subtree(state.locked, curr_node)):
                while 0 <= next_idx < len(visible):
                    if _is_in_subtree(visible[next_idx], curr_node):
                        next_idx += 1
                    else:
                        break

        if 0 <= next_idx < len(visible):
            target_idx = next_idx
        else:
            break

    new_cursor = visible[target_idx]

    if state.locked:
        if not _is_in_subtree(new_cursor, state.locked):
            state.locked = None

    state.cursor_node = new_cursor


# -----------------------------------------------------------------
#  UI RENDERING
# -----------------------------------------------------------------

def _render(state: NavState, entries: list[Entry], visible: list[Entry], cursor_idx: int, show_ignored: bool,
            filter_str: str, lang: str, show_help: bool, filtering: bool, all_flat: list[Entry]) -> None:
    _clear_screen()
    rows, cols = _term_size()
    content_rows = max(2, rows - 10)
    n = len(visible)

    if rows < 14:
        print(f"{_B}{_M}  Graphify — Select scope{_R}  ({lang})")
    else:
        print(f"{_B}{_M}  Graphify — Select files to TRACK in the knowledge graph{_R}")
        if filtering:
            print(f"  {_CY}FILTER{_R}  type to filter  ESC/Enter to exit  UP/DOWN to navigate")
        elif show_help:
            print(f"  {_CY}HELP{_R}  press ? to close")
        else:
            print(f"  {_G}[+]{_R}=tracked  {_DI}[-]{_R}=ignored  {_Y}[-]{_R}=user-ignored  "
                  f"{_DI}UP/DOWN/k/j:nav  SPACE:toggle  E:expand(lock)  A:all  N:none  F:files  "
                  f"R:reset  I:auto-view  /:filter  ?:help  ENTER:save  Q:quit{_R}")
    print(f"  {'─' * min(70, cols - 4)}")

    if n == 0:
        print(f"  {_DI}No items match filter{_R}")
    else:
        start = max(0, min(cursor_idx - content_rows // 2, n - content_rows))
        end = min(n, start + content_rows)

        if start > 0:
            print(f"  {_DI}↑ {start} more{_R}")

        for i, e in enumerate(visible[start:end]):
            abs_i = start + i
            is_cur = abs_i == cursor_idx
            prefix = f"  {_Y}>{_R}" if is_cur else "   "

            inside_locked = state.locked is not None and _is_in_subtree(e, state.locked)
            color = (_BG_BL + _W) if inside_locked else e.color

            indent = "  " * e.depth
            name = e.relative.split("/")[-1]
            if e.is_dir:
                name += "/"

            lock_tag = f"  {_CY}[LOCKED]{_R}" if (e.is_dir and state.locked is e) else ""

            tag = ""
            if e.effective_excluded:
                if e.excluded:
                    tag = f"  {_DI}(auto){_R}" if (e.auto and not e.user) else f"  {_Y}(user){_R}"
                else:
                    tag = f"  {_DI}(inherited){_R}"

            icon = _icon(e, state)
            print(f"{prefix} {color}{e.check}{_R} {indent}{icon} {color}{name}{_R}{lock_tag}{tag}")

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
            "  E                   Expand / collapse directory (LOCK)",
            "  → (RIGHT)           Lock expand folder",
            "  ← (LEFT)            Collapse folder / jump to parent",
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
            "",
            f"  {_CY}Navigation:{_R} folders expand on hover, collapse when leaving",
            f"  {_CY}Lock mode:{_R} press E or → to keep folder expanded, ← or E to collapse",
            f"  {_BG_BL} {_W}Blue bg{_R} = inside a locked folder",
        ):
            print(line)

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


def _raw_tui(project_root: Path, entries: list[Entry]) -> bool:
    filter_str = ""
    filtering = False
    show_ignored = True
    show_help = False
    lang = _detect_language(project_root)
    all_flat = _flatten(entries)

    state = NavState(cursor_node=entries[0] if entries else None)

    try:
        while True:
            visible = _visible_entries(entries, state.cursor_node, state.locked, show_ignored, filter_str)
            if state.cursor_node not in visible and visible:
                state.cursor_node = visible[0]
                visible = _visible_entries(entries, state.cursor_node, state.locked, show_ignored, filter_str)

            try:
                cursor_idx = visible.index(state.cursor_node)
            except ValueError:
                cursor_idx = 0

            _render(state, entries, visible, cursor_idx, show_ignored, filter_str, lang, show_help, filtering, all_flat)
            
            ch = _getch()
            n = len(visible)

            if filtering:
                if ch == "\x1b":
                    filtering, filter_str = False, ""
                    state.cursor_node = _get_valid_node(state.cursor_node, cursor_idx, entries, state.locked, show_ignored, filter_str)
                elif ch in ("\r", "\n"):
                    filtering = False
                elif ch in ("\x7f", "\x08"):
                    filter_str = filter_str[:-1]
                    state.cursor_node = _get_valid_node(state.cursor_node, cursor_idx, entries, state.locked, show_ignored, filter_str)
                elif len(ch) == 1 and ch.isprintable():
                    filter_str += ch
                    state.cursor_node = _get_valid_node(state.cursor_node, cursor_idx, entries, state.locked, show_ignored, filter_str)
                elif ch in ("UP", "k") and n > 0:
                    _move_cursor(-1, entries, state, show_ignored, filter_str)
                elif ch in ("DOWN", "j") and n > 0:
                    _move_cursor(1, entries, state, show_ignored, filter_str)
                continue

            if ch in ("UP", "k") and n > 0:
                _move_cursor(-1, entries, state, show_ignored, filter_str)
            elif ch in ("DOWN", "j") and n > 0:
                _move_cursor(1, entries, state, show_ignored, filter_str)
            elif ch == "PAGEUP" and n > 0:
                _move_cursor(-10, entries, state, show_ignored, filter_str)
            elif ch == "PAGEDOWN" and n > 0:
                _move_cursor(10, entries, state, show_ignored, filter_str)
            elif ch == "HOME" and n > 0:
                _move_cursor(-cursor_idx, entries, state, show_ignored, filter_str)
            elif ch == "END" and n > 0:
                _move_cursor(n - 1 - cursor_idx, entries, state, show_ignored, filter_str)
                
            elif ch == " " and state.cursor_node:
                _set_node_state(state.cursor_node, not state.cursor_node.effective_excluded)
                
            elif ch.lower() == "e" or ch == "RIGHT":
                e = state.cursor_node
                if e and e.is_dir:
                    if state.locked is e:
                        state.locked = None
                    else:
                        state.locked = e
                        
            elif ch == "LEFT":
                e = state.cursor_node
                if e:
                    if state.locked is e:
                        state.locked = None
                        if e.parent: state.cursor_node = e.parent
                    elif e.parent:
                        state.cursor_node = e.parent
                        if state.locked and not _is_in_subtree(state.cursor_node, state.locked):
                            state.locked = None
                        
            elif ch.lower() == "a":
                for e in visible:
                    if e.effective_excluded:
                        _set_node_state(e, False)
                        
            elif ch.lower() == "n":
                for e in visible:
                    if not e.effective_excluded:
                        _set_node_state(e, True)
                        
            elif ch.lower() == "f" and state.cursor_node:
                e = state.cursor_node
                if e.is_dir and e.children:
                    files = [c for c in e.children if not c.is_dir]
                    if files:
                        new_state = not any(f.effective_excluded for f in files)
                        for f in files:
                            _set_node_state(f, new_state)
                            
            elif ch.lower() == "r":
                for e in entries:
                    e.reset(project_root)
                state.locked = None
                state.cursor_node = _get_valid_node(state.cursor_node, cursor_idx, entries, state.locked, show_ignored, filter_str)
                
            elif ch.lower() == "i":
                show_ignored = not show_ignored
                state.cursor_node = _get_valid_node(state.cursor_node, cursor_idx, entries, state.locked, show_ignored, filter_str)
                
            elif ch == "/":
                filtering, filter_str = True, ""
            elif ch == "\x1b":
                if filter_str:
                    filter_str = ""
                    state.cursor_node = _get_valid_node(state.cursor_node, cursor_idx, entries, state.locked, show_ignored, filter_str)
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
    except KeyboardInterrupt:
        _clear_screen()
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
            try:
                confirmed = _raw_tui(project_root, entries)
            except KeyboardInterrupt:
                _clear_screen()
                print("\n  Aborted — no changes made.")
                return None
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
