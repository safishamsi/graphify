# file discovery, type classification, and corpus health checks
from __future__ import annotations
import json
import os
import re
from enum import Enum
from pathlib import Path

import pathspec


class FileType(str, Enum):
    CODE = "code"
    DOCUMENT = "document"
    PAPER = "paper"
    IMAGE = "image"
    VIDEO = "video"


from . import paths as _paths


CODE_EXTENSIONS = {'.py', '.ts', '.js', '.jsx', '.tsx', '.mjs', '.ejs', '.go', '.rs', '.java', '.cpp', '.cc', '.cxx', '.c', '.h', '.hpp', '.rb', '.swift', '.kt', '.kts', '.cs', '.scala', '.php', '.lua', '.toc', '.zig', '.ps1', '.ex', '.exs', '.m', '.mm', '.jl', '.vue', '.svelte', '.dart', '.v', '.sv'}
DOC_EXTENSIONS = {'.md', '.mdx', '.txt', '.rst', '.html'}
PAPER_EXTENSIONS = {'.pdf'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
OFFICE_EXTENSIONS = {'.docx', '.xlsx'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v', '.mp3', '.wav', '.m4a', '.ogg'}

CORPUS_WARN_THRESHOLD = 50_000    # words - below this, warn "you may not need a graph"
CORPUS_UPPER_THRESHOLD = 500_000  # words - above this, warn about token cost
FILE_COUNT_UPPER = 200             # files - above this, warn about token cost

# Files that may contain secrets - skip silently
_SENSITIVE_PATTERNS = [
    re.compile(r'(^|[\\/])\.(env|envrc)(\.|$)', re.IGNORECASE),
    re.compile(r'\.(pem|key|p12|pfx|cert|crt|der|p8)$', re.IGNORECASE),
    re.compile(r'(credential|secret|passwd|password|token|private_key)', re.IGNORECASE),
    re.compile(r'(id_rsa|id_dsa|id_ecdsa|id_ed25519)(\.pub)?$'),
    re.compile(r'(\.netrc|\.pgpass|\.htpasswd)$', re.IGNORECASE),
    re.compile(r'(aws_credentials|gcloud_credentials|service.account)', re.IGNORECASE),
]

# Signals that a .md/.txt file is actually a converted academic paper
_PAPER_SIGNALS = [
    re.compile(r'\barxiv\b', re.IGNORECASE),
    re.compile(r'\bdoi\s*:', re.IGNORECASE),
    re.compile(r'\babstract\b', re.IGNORECASE),
    re.compile(r'\bproceedings\b', re.IGNORECASE),
    re.compile(r'\bjournal\b', re.IGNORECASE),
    re.compile(r'\bpreprint\b', re.IGNORECASE),
    re.compile(r'\\cite\{'),          # LaTeX citation
    re.compile(r'\[\d+\]'),           # Numbered citation [1], [23] (inline)
    re.compile(r'\[\n\d+\n\]'),       # Numbered citation spread across lines (markdown conversion)
    re.compile(r'eq\.\s*\d+|equation\s+\d+', re.IGNORECASE),
    re.compile(r'\d{4}\.\d{4,5}'),   # arXiv ID like 1706.03762
    re.compile(r'\bwe propose\b', re.IGNORECASE),   # common academic phrasing
    re.compile(r'\bliterature\b', re.IGNORECASE),   # "from the literature"
]
_PAPER_SIGNAL_THRESHOLD = 3  # need at least this many signals to call it a paper


def _is_sensitive(path: Path) -> bool:
    """Return True if this file likely contains secrets and should be skipped."""
    name = path.name
    return any(p.search(name) for p in _SENSITIVE_PATTERNS)


def _looks_like_paper(path: Path) -> bool:
    """Heuristic: does this text file read like an academic paper?"""
    try:
        # Only scan first 3000 chars for speed
        text = path.read_text(encoding="utf-8", errors="ignore")[:3000]
        hits = sum(1 for pattern in _PAPER_SIGNALS if pattern.search(text))
        return hits >= _PAPER_SIGNAL_THRESHOLD
    except Exception:
        return False


_ASSET_DIR_MARKERS = {".imageset", ".xcassets", ".appiconset", ".colorset", ".launchimage"}


def classify_file(path: Path) -> FileType | None:
    # Compound extensions must be checked before simple suffix lookup
    if path.name.lower().endswith(".blade.php"):
        return FileType.CODE
    ext = path.suffix.lower()
    if ext in CODE_EXTENSIONS:
        return FileType.CODE
    if ext in PAPER_EXTENSIONS:
        # PDFs inside Xcode asset catalogs are vector icons, not papers
        if any(part.endswith(tuple(_ASSET_DIR_MARKERS)) for part in path.parts):
            return None
        return FileType.PAPER
    if ext in IMAGE_EXTENSIONS:
        return FileType.IMAGE
    if ext in DOC_EXTENSIONS:
        # Check if it's a converted paper
        if _looks_like_paper(path):
            return FileType.PAPER
        return FileType.DOCUMENT
    if ext in OFFICE_EXTENSIONS:
        return FileType.DOCUMENT
    if ext in VIDEO_EXTENSIONS:
        return FileType.VIDEO
    return None


def extract_pdf_text(path: Path) -> str:
    """Extract plain text from a PDF file using pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n".join(pages)
    except Exception:
        return ""


def docx_to_markdown(path: Path) -> str:
    """Convert a .docx file to markdown text using python-docx."""
    try:
        from docx import Document
        from docx.oxml.ns import qn
        doc = Document(str(path))
        lines = []
        for para in doc.paragraphs:
            style = para.style.name if para.style else ""
            text = para.text.strip()
            if not text:
                lines.append("")
                continue
            if style.startswith("Heading 1"):
                lines.append(f"# {text}")
            elif style.startswith("Heading 2"):
                lines.append(f"## {text}")
            elif style.startswith("Heading 3"):
                lines.append(f"### {text}")
            elif style.startswith("List"):
                lines.append(f"- {text}")
            else:
                lines.append(text)
        # Tables
        for table in doc.tables:
            rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            if not rows:
                continue
            header = "| " + " | ".join(rows[0]) + " |"
            sep = "| " + " | ".join("---" for _ in rows[0]) + " |"
            lines.extend([header, sep])
            for row in rows[1:]:
                lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)
    except ImportError:
        return ""
    except Exception:
        return ""


def xlsx_to_markdown(path: Path) -> str:
    """Convert an .xlsx file to markdown text using openpyxl."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        sections = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = []
            for row in ws.iter_rows(values_only=True):
                # Skip entirely empty rows
                if all(cell is None for cell in row):
                    continue
                rows.append([str(cell) if cell is not None else "" for cell in row])
            if not rows:
                continue
            sections.append(f"## Sheet: {sheet_name}")
            if len(rows) >= 1:
                header = "| " + " | ".join(rows[0]) + " |"
                sep = "| " + " | ".join("---" for _ in rows[0]) + " |"
                sections.extend([header, sep])
                for row in rows[1:]:
                    sections.append("| " + " | ".join(row) + " |")
        wb.close()
        return "\n".join(sections)
    except ImportError:
        return ""
    except Exception:
        return ""


def convert_office_file(path: Path, out_dir: Path) -> Path | None:
    """Convert a .docx or .xlsx to a markdown sidecar in out_dir.

    Returns the path of the converted .md file, or None if conversion failed
    or the required library is not installed.
    """
    ext = path.suffix.lower()
    if ext == ".docx":
        text = docx_to_markdown(path)
    elif ext == ".xlsx":
        text = xlsx_to_markdown(path)
    else:
        return None

    if not text.strip():
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    # Use a stable name derived from the original path to avoid collisions
    import hashlib
    name_hash = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:8]
    out_path = out_dir / f"{path.stem}_{name_hash}.md"
    out_path.write_text(
        f"<!-- converted from {path.name} -->\n\n{text}",
        encoding="utf-8",
    )
    return out_path


def count_words(path: Path) -> int:
    try:
        ext = path.suffix.lower()
        if ext == ".pdf":
            return len(extract_pdf_text(path).split())
        if ext == ".docx":
            return len(docx_to_markdown(path).split())
        if ext == ".xlsx":
            return len(xlsx_to_markdown(path).split())
        return len(path.read_text(encoding="utf-8", errors="ignore").split())
    except Exception:
        return 0


# Built-in noise prepended to every ignore chain. A user `!`-rule overrides
# any of these via last-match-wins. Build-output dirs (dist/, build/, ...) are
# intentionally NOT listed — those are project-specific and belong in .gitignore.
_BUILTIN_NOISE_PATTERNS: tuple[str, ...] = (
    ".*",
    "__pycache__/",
    "venv/", "env/",
    "*_venv/", "*_env/",
    "*.egg-info/",
    "site-packages/", "lib64/",
    "node_modules/",
    ".graphify/",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.lock", "poetry.lock", "Gemfile.lock",
    "composer.lock", "go.sum", "go.work.sum",
)
_BUILTIN_NOISE_SPEC = pathspec.GitIgnoreSpec.from_lines(_BUILTIN_NOISE_PATTERNS)

# Pruning shortcut for the .gitignore-discovery walk only — descending into
# node_modules just to look for nested ignore files would dominate detect() time.
_DISCOVERY_SKIP_DIRS = frozenset({
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".graphify",
})


AnchoredSpec = tuple[Path, "pathspec.PathSpec"]


def _respect_gitignore() -> bool:
    """Return True unless the user has opted out of .gitignore honoring."""
    flag = os.environ.get("GRAPHIFY_RESPECT_GITIGNORE", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def _load_ignore_file(ignore_file: Path) -> "pathspec.PathSpec | None":
    """Compile a single ignore file into a gitwildmatch PathSpec, or None on read failure."""
    try:
        text = ignore_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    spec = pathspec.GitIgnoreSpec.from_lines(text.splitlines())
    return spec if spec.patterns else None


def _collect_ignore_files(root: Path, names: tuple[str, ...]) -> list[Path]:
    """Every ignore file (matching any of *names*) that affects *root*, in evaluation order.

    Outer-first by depth, then by *names* order within an anchor — combined with
    last-match-wins in :func:`_is_ignored`, a later name overrides an earlier
    co-located one. Walks up to the nearest ``.git`` so repo-level rules apply
    on subdirectories, then walks down through *root* for nested rules.
    """
    root = root.resolve()

    chain: list[Path] = []
    cursor = root
    while True:
        chain.append(cursor)
        if (cursor / ".git").exists():
            break
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    chain.reverse()

    files: list[Path] = []
    for anc in chain:
        for name in names:
            f = anc / name
            if f.exists():
                files.append(f)

    if root.is_dir():
        seen = set(files)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _DISCOVERY_SKIP_DIRS]
            dp = Path(dirpath)
            for name in names:
                if name in filenames:
                    f = dp / name
                    if f not in seen:
                        seen.add(f)
                        files.append(f)

    return files


def _load_ignore_specs(
    root: Path, names: tuple[str, ...]
) -> list[AnchoredSpec]:
    """Load every ignore file matching *names* into anchored PathSpecs."""
    specs: list[AnchoredSpec] = []
    for ignore_file in _collect_ignore_files(root, names):
        spec = _load_ignore_file(ignore_file)
        if spec is not None:
            specs.append((ignore_file.parent.resolve(), spec))
    return specs


def _load_gitignore(root: Path) -> list[AnchoredSpec]:
    """Every .gitignore affecting *root*, in evaluation order. Skipped if GRAPHIFY_RESPECT_GITIGNORE=0."""
    if not _respect_gitignore():
        return []
    return _load_ignore_specs(root, (".gitignore",))


def _load_graphifyignore(root: Path) -> list[AnchoredSpec]:
    """Every .graphifyignore affecting *root*, in evaluation order. Same syntax as .gitignore."""
    return _load_ignore_specs(root, (".graphifyignore",))


def _is_ignored(
    path: Path,
    specs: list[AnchoredSpec],
    *,
    is_dir: bool = False,
) -> bool:
    """Last-match-wins across the spec chain. Pass *is_dir* True so dir-only patterns fire.

    *path* must be absolute and resolved. Each spec is anchored to its source file's
    directory; patterns outside that subtree don't apply. A re-include via ``!`` cannot
    rescue a file from a parent dir that was already pruned — the caller enforces this
    by not descending into ignored dirs.
    """
    state = False
    for anchor, spec in specs:
        try:
            rel = path.relative_to(anchor).as_posix()
        except ValueError:
            continue
        if is_dir and not rel.endswith("/"):
            rel = rel + "/"
        result = spec.check_file(rel)
        if result.include is not None:
            state = result.include
    return state


def detect(root: Path, *, follow_symlinks: bool = False) -> dict:
    root = root.resolve()
    files: dict[FileType, list[str]] = {
        FileType.CODE: [],
        FileType.DOCUMENT: [],
        FileType.PAPER: [],
        FileType.IMAGE: [],
        FileType.VIDEO: [],
    }
    total_words = 0

    skipped_sensitive: list[str] = []
    ignore_names = (".graphifyignore",)
    if _respect_gitignore():
        ignore_names = (".gitignore",) + ignore_names
    user_specs = _load_ignore_specs(root, ignore_names)
    ignore_patterns: list[AnchoredSpec] = [(root, _BUILTIN_NOISE_SPEC), *user_specs]

    # memory dir scans without ignore filtering — its contents are wanted
    # even though it lives under .graphify/ which the noise spec prunes.
    memory_dir = _paths.memory_dir(root)
    scan_paths: list[tuple[Path, list[AnchoredSpec]]] = [(root, ignore_patterns)]
    if memory_dir.exists():
        scan_paths.append((memory_dir, []))

    seen: set[Path] = set()
    all_files: list[Path] = []

    for scan_root, scan_specs in scan_paths:
        for dirpath, dirnames, filenames in os.walk(scan_root, followlinks=follow_symlinks):
            dp = Path(dirpath)
            if follow_symlinks and os.path.islink(dirpath):
                real = os.path.realpath(dirpath)
                parent_real = os.path.realpath(os.path.dirname(dirpath))
                if parent_real == real or parent_real.startswith(real + os.sep):
                    dirnames.clear()
                    continue
            dirnames[:] = [d for d in dirnames if not _is_ignored(dp / d, scan_specs, is_dir=True)]
            for fname in filenames:
                p = dp / fname
                if p in seen or _is_ignored(p, scan_specs):
                    continue
                seen.add(p)
                all_files.append(p)

    converted_dir = _paths.converted_dir(root)

    for p in all_files:
        if _is_sensitive(p):
            skipped_sensitive.append(str(p))
            continue
        ftype = classify_file(p)
        if ftype:
            # Office files: convert to markdown sidecar so subagents can read them
            if p.suffix.lower() in OFFICE_EXTENSIONS:
                md_path = convert_office_file(p, converted_dir)
                if md_path:
                    files[ftype].append(str(md_path))
                    total_words += count_words(md_path)
                else:
                    # Conversion failed (library not installed) - skip with note
                    skipped_sensitive.append(str(p) + " [office conversion failed - pip install graphifyy[office]]")
                continue
            files[ftype].append(str(p))
            if ftype != FileType.VIDEO:
                total_words += count_words(p)

    total_files = sum(len(v) for v in files.values())
    needs_graph = total_words >= CORPUS_WARN_THRESHOLD

    # Determine warning - lower bound, upper bound, or sensitive files skipped
    warning: str | None = None
    if not needs_graph:
        warning = (
            f"Corpus is ~{total_words:,} words - fits in a single context window. "
            f"You may not need a graph."
        )
    elif total_words >= CORPUS_UPPER_THRESHOLD or total_files >= FILE_COUNT_UPPER:
        warning = (
            f"Large corpus: {total_files} files · ~{total_words:,} words. "
            f"Semantic extraction will be expensive (many Claude tokens). "
            f"Consider running on a subfolder, or use --no-semantic to run AST-only."
        )

    return {
        "files": {k.value: v for k, v in files.items()},
        "total_files": total_files,
        "total_words": total_words,
        "needs_graph": needs_graph,
        "warning": warning,
        "skipped_sensitive": skipped_sensitive,
        "graphifyignore_patterns": sum(len(spec.patterns) for _, spec in user_specs),
    }


def load_manifest(manifest_path: str | Path | None = None) -> dict[str, float]:
    """Load the file mtime manifest from a previous run."""
    if manifest_path is None:
        manifest_path = _paths.manifest_path()
    try:
        return json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_manifest(files: dict[str, list[str]], manifest_path: str | Path | None = None) -> None:
    """Save current file mtimes for the next --update diff."""
    if manifest_path is None:
        manifest_path = _paths.manifest_path()
    manifest: dict[str, float] = {}
    for file_list in files.values():
        for f in file_list:
            try:
                manifest[f] = Path(f).stat().st_mtime
            except OSError:
                pass  # file deleted between detect() and manifest write - skip it
    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
    Path(manifest_path).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def detect_incremental(root: Path, manifest_path: str | Path | None = None) -> dict:
    """Like detect(), but returns only new or modified files since the last run.

    Compares current file mtimes against the stored manifest.
    Use for --update mode: re-extract only what changed, merge into existing graph.
    """
    full = detect(root)
    manifest = load_manifest(manifest_path)

    if not manifest:
        # No previous run - treat everything as new
        full["incremental"] = True
        full["new_files"] = full["files"]
        full["unchanged_files"] = {k: [] for k in full["files"]}
        full["new_total"] = full["total_files"]
        return full

    new_files: dict[str, list[str]] = {k: [] for k in full["files"]}
    unchanged_files: dict[str, list[str]] = {k: [] for k in full["files"]}

    for ftype, file_list in full["files"].items():
        for f in file_list:
            stored_mtime = manifest.get(f)
            try:
                current_mtime = Path(f).stat().st_mtime
            except Exception:
                current_mtime = 0
            if stored_mtime is None or current_mtime > stored_mtime:
                new_files[ftype].append(f)
            else:
                unchanged_files[ftype].append(f)

    # Files in manifest that no longer exist - their cached nodes are now ghost nodes
    current_files = {f for flist in full["files"].values() for f in flist}
    deleted_files = [f for f in manifest if f not in current_files]

    new_total = sum(len(v) for v in new_files.values())
    full["incremental"] = True
    full["new_files"] = new_files
    full["unchanged_files"] = unchanged_files
    full["new_total"] = new_total
    full["deleted_files"] = deleted_files
    return full
