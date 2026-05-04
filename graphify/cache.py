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


def file_hash(path: Path, extra_key: bytes = b"") -> str:
    """SHA256 of file contents + resolved path + optional extra key.

    For Markdown files (.md), only the body below the YAML frontmatter is hashed,
    so metadata-only changes (e.g. reviewed, status, tags) do not invalidate the cache.
    extra_key allows callers to mix in additional context (e.g. a tsconfig
    hash) so that cache entries are invalidated when that context changes.
    """
    p = Path(path)
    raw = p.read_bytes()
    content = _body_content(raw) if p.suffix.lower() == ".md" else raw
    h = hashlib.sha256()
    h.update(content)
    h.update(b"\x00")
    h.update(str(p.resolve()).encode())
    if extra_key:
        h.update(b"\x00")
        h.update(extra_key)
    return h.hexdigest()


def cache_dir(root: Path = Path(".")) -> Path:
    """Returns graphify-out/cache/ - creates it if needed."""
    d = Path(root) / "graphify-out" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_cached(path: Path, root: Path = Path("."), extra_key: bytes = b"") -> dict | None:
    """Return cached extraction for this file if hash matches, else None.

    Cache key: SHA256 of file contents + resolved path + extra_key.
    extra_key should include any external context the extraction depends on
    (e.g. a hash of the effective tsconfig.json for JS/TS files).
    Cache value: stored as graphify-out/cache/{hash}.json
    Returns None if no cache entry or file has changed.
    """
    try:
        h = file_hash(path, extra_key)
    except OSError:
        return None
    entry = cache_dir(root) / f"{h}.json"
    if not entry.exists():
        return None
    try:
        return json.loads(entry.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def save_cached(path: Path, result: dict, root: Path = Path("."), extra_key: bytes = b"") -> None:
    """Save extraction result for this file.

    Stores as graphify-out/cache/{hash}.json where hash = SHA256 of current
    file contents + resolved path + extra_key.  extra_key must match the value
    used in load_cached so that lookups and stores are consistent.
    result should be a dict with 'nodes' and 'edges' lists.
    """
    h = file_hash(path, extra_key)
    entry = cache_dir(root) / f"{h}.json"
    tmp = entry.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(result))
        os.replace(tmp, entry)
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
        if p.exists():
            save_cached(p, result, root)
            saved += 1
    return saved
