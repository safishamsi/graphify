# per-file extraction cache - skip unchanged files on re-run
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def _body_content(content: bytes) -> bytes:
    """Strip YAML frontmatter from Markdown content, returning only the body."""
    text = content.decode(errors="replace")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].encode()
    return content


def file_hash(path: Path, root: Path = Path(".")) -> str:
    """SHA256 of file contents + path relative to root.

    Using a relative path (not absolute) makes cache entries portable across
    machines and checkout directories, so shared caches and CI work correctly.
    Falls back to the resolved absolute path if the file is outside root.

    For Markdown files (.md), only the body below the YAML frontmatter is hashed,
    so metadata-only changes (e.g. reviewed, status, tags) do not invalidate the cache.
    """
    p = Path(path)
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


def cache_dir(root: Path = Path(".")) -> Path:
    """Returns graphify-out/cache/ - creates it if needed."""
    d = Path(root).resolve() / "graphify-out" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_cached(path: Path, root: Path = Path(".")) -> dict | None:
    """Return cached extraction for this file if hash matches, else None.

    Cache key: SHA256 of file contents.
    Cache value: stored as graphify-out/cache/{hash}.json
    Returns None if no cache entry or file has changed.
    """
    try:
        h = file_hash(path, root)
    except OSError:
        return None
    entry = cache_dir(root) / f"{h}.json"
    if not entry.exists():
        return None
    try:
        return json.loads(entry.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_cached(path: Path, result: dict, root: Path = Path(".")) -> None:
    """Save extraction result for this file.

    Stores as graphify-out/cache/{hash}.json where hash = SHA256 of current file contents.
    result should be a dict with 'nodes' and 'edges' lists.

    No-ops if `path` is not a regular file. Subagent-produced semantic fragments
    occasionally carry a directory path in `source_file`; skipping them prevents
    IsADirectoryError from aborting the whole batch.
    """
    p = Path(path)
    if not p.is_file():
        return
    h = file_hash(p, root)
    entry = cache_dir(root) / f"{h}.json"
    tmp = entry.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(result), encoding="utf-8")
        try:
            os.replace(tmp, entry)
        except PermissionError:
            # Windows: os.replace can fail with WinError 5 if the target is
            # briefly locked. Fall back to copy-then-delete.
            import shutil
            shutil.copy2(tmp, entry)
            tmp.unlink(missing_ok=True)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def cached_files(root: Path = Path(".")) -> set[str]:
    """Return set of file paths that have a valid cache entry (hash still matches)."""
    d = cache_dir(root)
    return {p.stem for p in d.glob("*.json")}


def clear_cache(root: Path = Path(".")) -> None:
    """Delete all graphify-out/cache/*.json files."""
    d = cache_dir(root)
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
        result = load_cached(Path(fpath), root)
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

    Groups nodes and edges by source_file, then saves one cache entry per file.
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
            save_cached(p, result, root)
            saved += 1
    return saved
