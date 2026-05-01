"""
File discovery, type classification, and corpus health checks.

This module provides the core logic for scanning directories, identifying 
relevant files for the knowledge graph, and handling incremental updates 
while respecting exclusion rules and built-in noise filters.
"""
from __future__ import annotations
import json
import os
import re
from enum import Enum
from pathlib import Path


class FileType(str, Enum):
    """Enumeration of supported file categories for graph extraction."""
    CODE = "code"
    DOCUMENT = "document"
    PAPER = "paper"
    IMAGE = "image"
    VIDEO = "video"


_MANIFEST_PATH = "graphify-out/manifest.json"

# Supported extensions for automated classification
CODE_EXTENSIONS = {'.py', '.ts', '.js', '.jsx', '.tsx', '.mjs', '.ejs', '.go', '.rs', '.java', '.cpp', '.cc', '.cxx', '.c', '.h', '.hpp', '.rb', '.swift', '.kt', '.kts', '.cs', '.scala', '.php', '.lua', '.toc', '.zig', '.ps1', '.ex', '.exs', '.m', '.mm', '.jl', '.vue', '.svelte', '.dart', '.v', '.sv', '.sql'}
DOC_EXTENSIONS = {'.md', '.mdx', '.txt', '.rst', '.html', '.yaml', '.yml'}
PAPER_EXTENSIONS = {'.pdf'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
OFFICE_EXTENSIONS = {'.docx', '.xlsx'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v', '.mp3', '.wav', '.m4a', '.ogg'}

# Corpus size thresholds for user warnings
CORPUS_WARN_THRESHOLD = 50_000    # words - below this, warn "you may not need a graph"
CORPUS_UPPER_THRESHOLD = 500_000  # words - above this, warn about token cost
FILE_COUNT_UPPER = 200             # files - above this, warn about token cost

# Patterns for identifying files likely containing secrets or credentials
_SENSITIVE_PATTERNS = [
    re.compile(r'(^|[\\/])\.(env|envrc)(\.|$)', re.IGNORECASE),
    re.compile(r'\.(pem|key|p12|pfx|cert|crt|der|p8)$', re.IGNORECASE),
    re.compile(r'(credential|secret|passwd|password|token|private_key)', re.IGNORECASE),
    re.compile(r'(id_rsa|id_dsa|id_ecdsa|id_ed25519)(\.pub)?$'),
    re.compile(r'(\.netrc|\.pgpass|\.htpasswd)$', re.IGNORECASE),
    re.compile(r'(aws_credentials|gcloud_credentials|service.account)', re.IGNORECASE),
]

# Textual markers identifying converted markdown files as academic papers
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
_PAPER_SIGNAL_THRESHOLD = 3  # minimum matches required for paper classification


def _is_sensitive(path: Path) -> bool:
    """
    Check if a file likely contains sensitive information or secrets.

    Parameters
    ----------
    path : Path
        The file path to check.

    Returns
    -------
    bool
        True if the file matches known sensitive patterns, False otherwise.
    """
    name = path.name
    return any(p.search(name) for p in _SENSITIVE_PATTERNS)


def _looks_like_paper(path: Path) -> bool:
    """
    Heuristically determine if a text file represents an academic paper.

    Parameters
    ----------
    path : Path
        The file path to evaluate.

    Returns
    -------
    bool
        True if the file content contains sufficient academic markers.
    """
    try:
        # Scan initial segment for performance
        text = path.read_text(encoding="utf-8", errors="ignore")[:3000]
        hits = sum(1 for pattern in _PAPER_SIGNALS if pattern.search(text))
        return hits >= _PAPER_SIGNAL_THRESHOLD
    except Exception:
        return False


_ASSET_DIR_MARKERS = {".imageset", ".xcassets", ".appiconset", ".colorset", ".launchimage"}


def classify_file(path: Path) -> FileType | None:
    """
    Determine the type of a file based on its extension and content.

    Parameters
    ----------
    path : Path
        The file path to classify.

    Returns
    -------
    FileType or None
        The detected file category, or None if unknown.
    """
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
    """
    Extract plain text from a PDF file using pypdf.

    Parameters
    ----------
    path : Path
        Path to the PDF file.

    Returns
    -------
    str
        Extracted text content.
    """
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
    """
    Convert a .docx file to markdown text using python-docx.

    Parameters
    ----------
    path : Path
        Path to the .docx file.

    Returns
    -------
    str
        Converted markdown content.
    """
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
    """
    Convert an .xlsx file to markdown text using openpyxl.

    Parameters
    ----------
    path : Path
        Path to the .xlsx file.

    Returns
    -------
    str
        Converted markdown content.
    """
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        sections = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = []
            for row in ws.iter_rows(values_only=True):
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


def xlsx_extract_structure(path: Path) -> dict:
    """
    Extract structural nodes (sheets, tables, headers) from an .xlsx file.

    Parameters
    ----------
    path : Path
        Path to the .xlsx file.

    Returns
    -------
    dict
        A dictionary containing extracted 'nodes' and 'edges'.
    """
    def _nid(*parts: str) -> str:
        return re.sub(r"[^a-z0-9_]", "_", "_".join(p.lower() for p in parts).strip("_"))

    try:
        import openpyxl
    except ImportError:
        return {"nodes": [], "edges": []}

    try:
        wb = openpyxl.load_workbook(str(path), read_only=False, data_only=True)
    except Exception:
        return {"nodes": [], "edges": []}

    stem = re.sub(r"[^a-z0-9]", "_", path.stem.lower())
    str_path = str(path)
    file_nid = _nid(str_path)
    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "document",
                           "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen: set[str] = {file_nid}

    def _add(nid: str, label: str) -> None:
        if nid not in seen:
            seen.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "document",
                           "source_file": str_path, "source_location": None})

    def _edge(src: str, tgt: str, relation: str) -> None:
        edges.append({"source": src, "target": tgt, "relation": relation,
                       "confidence": "EXTRACTED", "source_file": str_path,
                       "source_location": None, "weight": 1.0})

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        sheet_nid = _nid(stem, sheet_name)
        _add(sheet_nid, f"{sheet_name} (sheet)")
        _edge(file_nid, sheet_nid, "contains")

        # Named Excel Tables (ListObjects)
        if hasattr(ws, "tables"):
            for tbl in ws.tables.values():
                tbl_nid = _nid(stem, sheet_name, tbl.name)
                _add(tbl_nid, tbl.name)
                _edge(sheet_nid, tbl_nid, "contains")
                # Column headers from table header row
                ref = tbl.ref  # e.g. "A1:D10"
                if ref:
                    try:
                        from openpyxl.utils import range_boundaries
                        min_col, min_row, max_col, _ = range_boundaries(ref)
                        header_row = list(ws.iter_rows(min_row=min_row, max_row=min_row,
                                                       min_col=min_col, max_col=max_col,
                                                       values_only=True))
                        if header_row:
                            for col_name in header_row[0]:
                                if col_name:
                                    col_nid = _nid(stem, tbl.name, str(col_name))
                                    _add(col_nid, str(col_name))
                                    _edge(tbl_nid, col_nid, "contains")
                    except Exception:
                        pass
        else:
            # Fallback: first non-empty row as column headers
            for row in ws.iter_rows(max_row=1, values_only=True):
                for cell in row:
                    if cell:
                        col_nid = _nid(stem, sheet_name, str(cell))
                        _add(col_nid, str(cell))
                        _edge(sheet_nid, col_nid, "contains")
                break

    try:
        wb.close()
    except Exception:
        pass

    return {"nodes": nodes, "edges": edges}


def convert_office_file(path: Path, out_dir: Path) -> Path | None:
    """
    Convert a .docx or .xlsx to a markdown sidecar.

    Parameters
    ----------
    path : Path
        The office file to convert.
    out_dir : Path
        The output directory for the converted markdown file.

    Returns
    -------
    Path or None
        Path to the converted file, or None if conversion failed.
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
    """
    Count the number of words in a file.

    Parameters
    ----------
    path : Path
        The file to count words in.

    Returns
    -------
    int
        The word count.
    """
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


# Directory names to always skip - venvs, caches, build artifacts, deps
_SKIP_DIRS = {
    "venv", ".venv", "env", ".env",
    "node_modules", "__pycache__", ".git",
    "dist", "build", "target", "out",
    "site-packages", "lib64",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".eggs", "*.egg-info",
    "graphify-out",  # never treat own output as source input (#524)
}

# Large generated files that are never useful to extract
_SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.lock", "poetry.lock", "Gemfile.lock",
    "composer.lock", "go.sum", "go.work.sum",
}

def _is_noise_dir(part: str) -> bool:
    """
    Check if a directory name matches known noise patterns (e.g., venvs, caches).

    Parameters
    ----------
    part : str
        The directory name to evaluate.

    Returns
    -------
    bool
        True if the directory is considered noise, False otherwise.
    """
    if part in _SKIP_DIRS:
        return True
    # Catch *_venv, *_repo/site-packages patterns
    if part.endswith("_venv") or part.endswith("_env"):
        return True
    if part.endswith(".egg-info"):
        return True
    return False


# POSIX bracket expression names mapped to Python regex character-range equivalents.
# Used by _pattern_to_regex when scanning [[:class:]] patterns.
_POSIX_CLASSES: dict[str, str] = {
    '[:alnum:]':  'a-zA-Z0-9',
    '[:alpha:]':  'a-zA-Z',
    '[:blank:]':  r' \t',
    '[:cntrl:]':  r'\x00-\x1F\x7F',
    '[:digit:]':  '0-9',
    '[:graph:]':  r'\x21-\x7E',
    '[:lower:]':  'a-z',
    '[:print:]':  r'\x20-\x7E',
    '[:punct:]':  r'\x21-\x2F\x3A-\x40\x5B-\x60\x7B-\x7E',
    '[:space:]':  r' \t\r\n\v\f',
    '[:upper:]':  'A-Z',
    '[:xdigit:]': 'A-Fa-f0-9',
}


def _pattern_to_regex(p: str) -> re.Pattern:
    """
    Convert a graphifyignore wildcard pattern to a compiled regular expression.

    Implements wildcard rules where '*' does not cross directory separators 
    but '**' does, following standard ignore specification.

    Parameters
    ----------
    p : str
        The wildcard pattern to convert.

    Returns
    -------
    re.Pattern
        The compiled regular expression matching the pattern's logic.
    """
    # Pre-process: expand POSIX [:class:] names to regex equivalents, but only
    # when they appear inside an open '[', preserving positional correctness.
    chars = []
    in_bracket = False
    i = 0
    while i < len(p):
        if p[i] == '[':
            if in_bracket:
                matched_posix = False
                for posix, py_eq in _POSIX_CLASSES.items():
                    if p.startswith(posix, i):
                        chars.append(py_eq)
                        i += len(posix)
                        matched_posix = True
                        break
                if matched_posix:
                    continue
            in_bracket = True
            chars.append(p[i])
            i += 1
        elif p[i] == ']':
            in_bracket = False
            chars.append(p[i])
            i += 1
        elif p[i] == '\\':
            # Skip the next character so an escaped bracket doesn't toggle state
            chars.append(p[i])
            if i + 1 < len(p):
                chars.append(p[i + 1])
                i += 1
            i += 1
        else:
            chars.append(p[i])
            i += 1
    p = "".join(chars)

    result: list[str] = []
    i = 0
    while i < len(p):
        c = p[i]
        if c == '\\' and i + 1 < len(p):
            result.append(re.escape(p[i + 1]))
            i += 2
        elif c == '*' and i + 1 < len(p) and p[i + 1] == '*':
            # ** is only special at the pattern start or immediately after /. 
            # In any other position it behaves like *.
            preceded_by_slash = (i == 0) or (result and result[-1] == '/')
            if i + 2 < len(p) and p[i + 2] == '/':
                if preceded_by_slash:
                    # **/ at start or after /: zero or more directory segments.
                    if result and result[-1] == '/':
                        result[-1] = '/(?:[^/]+/)*'
                    else:
                        result.append('(?:[^/]+/)*')
                    i += 3
                else:
                    # foo**/ → treat ** as *; / is handled in the next iteration.
                    result.append('[^/]*')
                    i += 2
            else:
                if preceded_by_slash:
                    # /** or leading **: match everything including separators.
                    result.append('.*')
                else:
                    # foo** → treat as foo*.
                    result.append('[^/]*')
                i += 2
        elif c == '*':
            result.append('[^/]*')
            i += 1
        elif c == '?':
            result.append('[^/]')
            i += 1
        elif c == '[':
            # Copy character class until closing ], converting [! to [^ for Python re.
            j = i + 1
            negate = j < len(p) and p[j] == '!'
            if j < len(p) and p[j] in ('!', '^'):
                j += 1
            if j < len(p) and p[j] == ']':
                j += 1
            while j < len(p) and p[j] != ']':
                j += 1
            cls = p[i:j + 1]
            if negate:
                cls = '[^' + cls[2:]  # [!xyz] → [^xyz] for Python re
            
            result.append(cls)
            i = j + 1
        else:
            result.append(re.escape(c))
            i += 1
    return re.compile(''.join(result))


def _match_ignore_pattern(rel: str, pattern: str, is_dir: bool) -> bool:
    """
    Check if a relative path matches an ignore pattern.

    Parameters
    ----------
    rel : str
        The forward-slash relative path to check.
    pattern : str
        The ignore pattern (without leading '!').
    is_dir : bool
        Whether the path represents a directory.

    Returns
    -------
    bool
        True if the path matches the pattern according to ignore rules.
    """
    dir_only = pattern.endswith('/')
    p = pattern.rstrip('/')

    anchored = p.startswith('/') or ('/' in p)
    if p.startswith('/'):
        p = p[1:]

    regex = _pattern_to_regex(p)
    parts = rel.split('/')

    if anchored:
        # Full-path match
        if regex.fullmatch(rel):
            if dir_only and not is_dir:
                return False
            return True
        # Prefix match (ignoring a directory ignores its contents)
        for i in range(1, len(parts)):
            if regex.fullmatch('/'.join(parts[:i])):
                return True
        return False
    else:
        # Basename match
        if regex.fullmatch(parts[-1]):
            if dir_only and not is_dir:
                return False
            return True
        # Directory component match
        for part in parts[:-1]:
            if regex.fullmatch(part):
                return True
        return False


def _trim_trailing_spaces(s: str) -> str:
    """
    Trim trailing spaces exactly as Git's dir.c:trim_trailing_spaces does.
    
    Unescaped trailing spaces are removed. A backslash escapes the next character 
    (including a space), preserving it.
    """
    last_space = -1
    i = 0
    while i < len(s):
        if s[i] == ' ':
            if last_space == -1:
                last_space = i
            i += 1
        elif s[i] == '\\':
            i += 2
            last_space = -1
        else:
            last_space = -1
            i += 1
    if last_space != -1:
        return s[:last_space]
    return s


_VCS_MARKERS = frozenset({".git", ".hg", ".svn", "_darcs", ".fossil"})


def _load_graphifyignore(root: Path) -> list[tuple[Path, str]]:
    """
    Discover and read .graphifyignore files from root and ancestors.

    Boundary rule:
    - VCS root found above scan dir (.git/.hg/.svn): walk up to it and load
      all .graphifyignore files along the way (handles monorepos where a
      global ignore file lives at the repo root).
    - No VCS root above scan dir: treat scan root as the ceiling and load
      only its own .graphifyignore, preventing accidental pickup of
      home-directory-level ignore files for non-VCS projects.

    Parameters
    ----------
    root : Path
        The starting directory for the upward search.

    Returns
    -------
    list of tuple[Path, str]
        A list of (anchor_dir, pattern) pairs ordered from outermost to
        innermost, so that inner patterns take precedence (last-match-wins).
    """
    resolved_root = root.resolve()

    # Walk upward collecting candidates; stop when a VCS root is found.
    candidates: list[Path] = [resolved_root]
    current = resolved_root
    vcs_found = False

    while True:
        parent = current.parent
        if parent == current:
            break  # filesystem root reached without finding VCS
        current = parent
        candidates.append(current)
        if any((current / m).exists() for m in _VCS_MARKERS):
            vcs_found = True
            break

    # No VCS root anywhere above: scan root is the ceiling.
    dirs = candidates if vcs_found else [resolved_root]

    patterns: list[tuple[Path, str]] = []
    for d in reversed(dirs):
        ignore_file = d / ".graphifyignore"
        if ignore_file.exists():
            for line in ignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line and not line.startswith("#"):
                    line = _trim_trailing_spaces(line)
                    if line:
                        patterns.append((d, line))

    return patterns


def _is_path_ignored(path: Path, root: Path, patterns: list[tuple[Path, str]], is_dir: bool | None = None) -> bool:
    """
    Determine if a path is excluded by .graphifyignore patterns.

    Implements ordered semantics where later patterns override earlier ones
    (negation).

    Parameters
    ----------
    path : Path
        The file or directory path to check.
    root : Path
        The scan root directory.
    patterns : list of tuple[Path, str]
        Discovered ignore patterns.
    is_dir : bool, optional
        Whether the path is a directory. If None, it is determined via path.is_dir().

    Returns
    -------
    bool
        True if the path is ignored and not subsequently negated.
    """
    if not patterns:
        return False

    if is_dir is None:
        is_dir = path.is_dir()

    ignored = False

    for anchor, pattern in patterns:
        is_negation = pattern.startswith('!')
        p = pattern[1:] if is_negation else pattern
        if not p.strip('/'):
            continue

        match = False
        # Try path relative to the scan root.
        try:
            rel = str(path.relative_to(root)).replace(os.sep, '/')
            if _match_ignore_pattern(rel, p, is_dir):
                match = True
        except ValueError:
            pass

        # Also try relative to the anchor dir (.graphifyignore's location)
        if not match and anchor != root:
            try:
                rel_anchor = str(path.relative_to(anchor)).replace(os.sep, '/')
                if _match_ignore_pattern(rel_anchor, p, is_dir):
                    match = True
            except ValueError:
                pass

        if match:
            ignored = not is_negation

    return ignored


def detect(root: Path, *, follow_symlinks: bool = False) -> dict:
    """
    Scan a directory for files to include in the graph.

    Parameters
    ----------
    root : Path
        The directory to scan.
    follow_symlinks : bool, default False
        Whether to follow directory symlinks.

    Returns
    -------
    dict
        Categorized files and health metadata.
    """
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
    ignore_patterns = _load_graphifyignore(root)

    # Always include graphify-out/memory/ - query results filed back into the graph
    memory_dir = root / "graphify-out" / "memory"
    scan_paths = [root]
    if memory_dir.exists():
        scan_paths.append(memory_dir)

    seen: set[Path] = set()
    all_files: list[Path] = []

    for scan_root in scan_paths:
        in_memory_tree = memory_dir.exists() and str(scan_root).startswith(str(memory_dir))
        for dirpath, dirnames, filenames in os.walk(scan_root, followlinks=follow_symlinks):
            dp = Path(dirpath)
            if follow_symlinks and os.path.islink(dirpath):
                real = os.path.realpath(dirpath)
                parent_real = os.path.realpath(os.path.dirname(dirpath))
                if parent_real == real or parent_real.startswith(real + os.sep):
                    dirnames.clear()
                    continue
            if not in_memory_tree:
                # Prune noise dirs and ignored dirs in-place.
                # Per standard ignore semantics, we do not descend into ignored directories.
                dirnames[:] = [
                    d for d in dirnames
                    if not d.startswith(".")
                    and not _is_noise_dir(d)
                    and not _is_path_ignored(dp / d, root, ignore_patterns, is_dir=True)
                ]
            for fname in filenames:
                if fname in _SKIP_FILES:
                    continue
                p = dp / fname
                if p not in seen:
                    seen.add(p)
                    all_files.append(p)

    converted_dir = root / "graphify-out" / "converted"

    for p in all_files:
        # For memory dir files, skip hidden/noise filtering
        in_memory = memory_dir.exists() and str(p).startswith(str(memory_dir))
        if not in_memory:
            # Hidden files are already excluded via dir pruning above,
            # but catch hidden files at the root level
            if p.name.startswith("."):
                continue
            # Skip files inside our own converted/ dir (avoid re-processing sidecars)
            if str(p).startswith(str(converted_dir)):
                continue
            # Standard ignore check (files only)
            if _is_path_ignored(p, root, ignore_patterns, is_dir=False):
                continue
        
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
        "graphifyignore_patterns": len(ignore_patterns),
    }


def load_manifest(manifest_path: str = _MANIFEST_PATH) -> dict[str, float]:
    """
    Load the file modification time manifest from a previous run.

    Parameters
    ----------
    manifest_path : str, default _MANIFEST_PATH
        The path to the manifest JSON file.

    Returns
    -------
    dict of str to float
        A mapping of file paths to their last recorded modification timestamps.
    """
    try:
        return json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_manifest(files: dict[str, list[str]], manifest_path: str = _MANIFEST_PATH) -> None:
    """
    Save current file modification times to the manifest.

    Used to enable incremental updates in subsequent runs.

    Parameters
    ----------
    files : dict of str to list of str
        The categorized lists of discovered files.
    manifest_path : str, default _MANIFEST_PATH
        The path where the manifest should be saved.
    """
    manifest: dict[str, float] = {}
    for file_list in files.values():
        for f in file_list:
            try:
                manifest[f] = Path(f).stat().st_mtime
            except OSError:
                pass  # file deleted between detect() and manifest write - skip it
    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
    Path(manifest_path).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def detect_incremental(root: Path, manifest_path: str = _MANIFEST_PATH) -> dict:
    """
    Identify files that have changed or been added since the last run.

    Parameters
    ----------
    root : Path
        The directory to scan.
    manifest_path : str, default _MANIFEST_PATH
        The path to the existing manifest file.

    Returns
    -------
    dict
        A dictionary containing incremental scan results, including new, 
        deleted, and unchanged file lists.
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
