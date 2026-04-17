# per-file extraction cache - skip unchanged files on re-run
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def file_hash(path: Path) -> str:
    """SHA256 of file contents, hex digest."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
        h = file_hash(path)
    except OSError:
        return None
    entry = cache_dir(root) / f"{h}.json"
    if not entry.exists():
        return None
    try:
        return json.loads(entry.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def save_cached(path: Path, result: dict, root: Path = Path(".")) -> None:
    """Save extraction result for this file.

    Stores as graphify-out/cache/{hash}.json where hash = SHA256 of current file contents.
    result should be a dict with 'nodes' and 'edges' lists.
    """
    h = file_hash(path)
    entry = cache_dir(root) / f"{h}.json"
    entry.write_text(json.dumps(result))


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
) -> tuple[list[dict], list[dict], list[str]]:
    """Check semantic extraction cache for a list of absolute file paths.

    Returns (cached_nodes, cached_edges, uncached_files).
    Uncached files need Claude extraction; cached files are merged directly.
    """
    cached_nodes: list[dict] = []
    cached_edges: list[dict] = []
    uncached: list[str] = []

    for fpath in files:
        result = load_cached(Path(fpath), root)
        if result is not None:
            cached_nodes.extend(result.get("nodes", []))
            cached_edges.extend(result.get("edges", []))
        else:
            uncached.append(fpath)

    return cached_nodes, cached_edges, uncached


def save_semantic_cache(
    nodes: list[dict],
    edges: list[dict],
    root: Path = Path("."),
) -> int:
    """Save semantic extraction results to cache, keyed by source_file.

    Groups nodes and edges by source_file, then saves one cache entry per file.
    Returns the number of files cached.
    """
    from collections import defaultdict

    by_file: dict[str, dict] = defaultdict(lambda: {"nodes": [], "edges": []})
    for n in nodes:
        src = n.get("source_file", "")
        if src:
            by_file[src]["nodes"].append(n)
    for e in edges:
        src = e.get("source_file", "")
        if src:
            by_file[src]["edges"].append(e)

    saved = 0
    for fpath, result in by_file.items():
        p = Path(fpath)
        if p.exists():
            save_cached(p, result, root)
            saved += 1
    return saved
