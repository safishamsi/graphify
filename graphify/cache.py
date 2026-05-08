# per-file extraction cache - skip unchanged files on re-run
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path

# Output directory name — override with GRAPHIFY_OUT env var for worktrees or
# shared-output setups. Accepts a relative name ("graphify-out-feature") or an
# absolute path ("/shared/graphify-out").
_GRAPHIFY_OUT = os.environ.get("GRAPHIFY_OUT", "graphify-out")

# Known cache kinds — used by cache_dir, cached_files, clear_cache, etc.
# Phase 7: centralized list for cache-kind validation and iteration.
_KNOWN_CACHE_KINDS = ["ast", "semantic"]


def _body_content(content: bytes) -> bytes:
    """Strip YAML frontmatter from Markdown content, returning only the body."""
    text = content.decode(errors="replace")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].encode()
    return content


def _normalize_path(path: Path) -> Path:
    """Normalize path for consistent cache keys across Windows path spellings."""
    import sys
    if sys.platform != "win32":
        return path
    s = str(path)
    if s.startswith("\\\\?\\"):
        s = s[4:]  # strip extended-length prefix \\?\
    return Path(os.path.normcase(s))


def file_hash(path: Path, root: Path = Path(".")) -> str:
    """SHA256 of file contents + path relative to root.

    Using a relative path (not absolute) makes cache entries portable across
    machines and checkout directories, so shared caches and CI work correctly.
    Falls back to the resolved absolute path if the file is outside root.

    For Markdown files (.md), only the body below the YAML frontmatter is hashed,
    so metadata-only changes (e.g. reviewed, status, tags) do not invalidate the cache.
    """
    p = _normalize_path(Path(path))
    root = _normalize_path(Path(root))
    if not p.is_file():
        raise IsADirectoryError(f"file_hash requires a file, got: {p}")
    raw = p.read_bytes()
    content = _body_content(raw) if p.suffix.lower() == ".md" else raw
    h = hashlib.sha256()
    h.update(content)
    h.update(b"\x00")
    try:
        rel = p.resolve().relative_to(Path(root).resolve())
        h.update(str(rel).encode())
    except ValueError:
        h.update(str(p.resolve()).encode())
    return h.hexdigest()


def cache_dir(root: Path = Path("."), kind: str = "ast") -> Path:
    """Returns graphify-out/cache/{kind}/ - creates it if needed.

    kind is "ast" or "semantic". Separate subdirectories prevent semantic cache
    entries from overwriting AST cache entries for the same source_file (#582).
    """
    _out = Path(_GRAPHIFY_OUT)
    base = _out if _out.is_absolute() else Path(root).resolve() / _out
    d = base / "cache" / kind
    d.mkdir(parents=True, exist_ok=True)
    return d


def _relativize_source_value(value: str, root: Path) -> str:
    """Store source_file values relative to root when possible.

    The cache key was already portable, but the cached payload still leaked
    absolute source_file paths (#777). This helper fixes the serialized payload.
    """
    if not value:
        return value
    root = root.resolve()
    p = Path(value)
    if not p.is_absolute():
        return value
    try:
        return str(p.resolve().relative_to(root))
    except ValueError:
        return value


def _load_source_value(value: str, root: Path, current_path: Path | None = None) -> str:
    """Normalize cached source_file values on load.

    Relative cache entries stay relative, which matches the final graph output
    and the cross-file resolver's existing relative-path handling. Legacy
    absolute entries inside root are migrated to relative values. Legacy entries
    outside root came from another checkout; for per-file caches, the current
    source path is the only trustworthy replacement.
    """
    if not value:
        return value
    root = root.resolve()
    p = Path(value)
    if not p.is_absolute():
        return value
    try:
        return str(p.resolve().relative_to(root))
    except ValueError:
        if current_path is not None:
            try:
                return str(current_path.resolve().relative_to(root))
            except ValueError:
                return str(current_path.resolve())
        return value


def _rewrite_result_source_files(
    result: dict,
    root: Path,
    *,
    for_cache: bool,
    current_path: Path | None = None,
) -> dict:
    """Copy a cached extraction result and rewrite source_file fields.

    The copy prevents cache normalization from mutating the in-memory result
    that extract() is still using during the current process.
    """
    rewritten = copy.deepcopy(result)
    for bucket in ("nodes", "edges", "hyperedges"):
        for item in rewritten.get(bucket, []) or []:
            source_file = item.get("source_file")
            if source_file:
                if for_cache:
                    item["source_file"] = _relativize_source_value(str(source_file), root)
                else:
                    item["source_file"] = _load_source_value(str(source_file), root, current_path)
    return rewritten


def load_cached(path: Path, root: Path = Path("."), kind: str = "ast") -> dict | None:
    """Return cached extraction for this file if hash matches, else None."""
    try:
        h = file_hash(path, root)
    except OSError:
        return None
    entry = cache_dir(root, kind) / f"{h}.json"
    if entry.exists():
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
            return _rewrite_result_source_files(data, Path(root), for_cache=False, current_path=path)
        except (json.JSONDecodeError, OSError):
            return None
    if kind == "ast":
        legacy = Path(root).resolve() / _GRAPHIFY_OUT / "cache" / f"{h}.json"
        if legacy.exists():
            try:
                data = json.loads(legacy.read_text(encoding="utf-8"))
                return _rewrite_result_source_files(data, Path(root), for_cache=False, current_path=path)
            except (json.JSONDecodeError, OSError):
                return None
    return None


def save_cached(path: Path, result: dict, root: Path = Path("."), kind: str = "ast") -> None:
    """Save extraction result for this file with portable source_file fields."""
    p = Path(path)
    if not p.is_file():
        return
    h = file_hash(p, root)
    target_dir = cache_dir(root, kind)
    entry = target_dir / f"{h}.json"
    portable_result = _rewrite_result_source_files(result, Path(root), for_cache=True)
    fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=f"{h}.", suffix=".tmp")
    try:
        os.write(fd, json.dumps(portable_result, sort_keys=True).encode())
        os.close(fd)
        try:
            os.replace(tmp_path, entry)
        except PermissionError:
            import shutil
            shutil.copy2(tmp_path, entry)
            os.unlink(tmp_path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def cached_files(root: Path = Path(".")) -> set[str]:
    """Return set of file hashes that have a valid cache entry (any kind)."""
    base = Path(root).resolve() / _GRAPHIFY_OUT / "cache"
    hashes: set[str] = set()
    # Legacy flat entries
    if base.is_dir():
        hashes.update(p.stem for p in base.glob("*.json"))
    # Namespaced entries
    for kind in _KNOWN_CACHE_KINDS:
        d = base / kind
        if d.is_dir():
            hashes.update(p.stem for p in d.glob("*.json"))
    return hashes


def clear_cache(root: Path = Path(".")) -> None:
    """Delete all cache entries (ast/, semantic/, and legacy flat entries)."""
    base = Path(root).resolve() / _GRAPHIFY_OUT / "cache"
    # Legacy flat entries
    if base.is_dir():
        for f in base.glob("*.json"):
            f.unlink()
    # Namespaced entries
    for kind in _KNOWN_CACHE_KINDS:
        d = base / kind
        if d.is_dir():
            for f in d.glob("*.json"):
                f.unlink()


def check_semantic_cache(
    files: list[str],
    root: Path = Path("."),
) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    """Check semantic extraction cache for a list of absolute file paths.

    Returns (cached_nodes, cached_edges, cached_hyperedges, uncached_files).
    Uncached files need Claude extraction; cached files are merged directly.
    """
    cached_nodes: list[dict] = []
    cached_edges: list[dict] = []
    cached_hyperedges: list[dict] = []
    uncached: list[str] = []

    for fpath in files:
        result = load_cached(Path(fpath), root, kind="semantic")
        if result is not None:
            cached_nodes.extend(result.get("nodes", []))
            cached_edges.extend(result.get("edges", []))
            cached_hyperedges.extend(result.get("hyperedges", []))
        else:
            uncached.append(fpath)

    return cached_nodes, cached_edges, cached_hyperedges, uncached


def save_semantic_cache(
    nodes: list[dict],
    edges: list[dict],
    hyperedges: list[dict] | None = None,
    root: Path = Path("."),
) -> int:
    """Save semantic extraction results to cache, keyed by source_file.

    Groups nodes and edges by source_file, then saves one cache entry per file
    under cache/semantic/ (separate from AST entries in cache/ast/) to prevent
    hash-key collisions (#582).
    Returns the number of files cached.
    """
    from collections import defaultdict

    by_file: dict[str, dict] = defaultdict(lambda: {"nodes": [], "edges": [], "hyperedges": []})
    for n in nodes:
        src = n.get("source_file", "")
        if src:
            by_file[src]["nodes"].append(n)
    for e in edges:
        src = e.get("source_file", "")
        if src:
            by_file[src]["edges"].append(e)
    for h in (hyperedges or []):
        src = h.get("source_file", "")
        if src:
            by_file[src]["hyperedges"].append(h)

    saved = 0
    for fpath, result in by_file.items():
        p = Path(fpath)
        if not p.is_absolute():
            p = Path(root) / p
        if p.is_file():
            save_cached(p, result, root, kind="semantic")
            saved += 1
    return saved
