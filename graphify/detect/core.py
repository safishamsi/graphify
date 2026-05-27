# file discovery, type classification, and corpus health checks
from __future__ import annotations
import json
import os
from pathlib import Path

from graphify.google_workspace import (
    GOOGLE_WORKSPACE_EXTENSIONS,
    convert_google_workspace_file,
    google_workspace_enabled,
)

from .constants import (
    OFFICE_EXTENSIONS, CORPUS_WARN_THRESHOLD, CORPUS_UPPER_THRESHOLD,
    FILE_COUNT_UPPER, _MANIFEST_PATH, _SKIP_FILES,
)

from .ignore import (
    _is_noise_dir, _parse_gitignore_line, _load_graphifyignore,
    _is_ignored, _load_graphifyinclude,
)
from .languages import (
    FileType, _is_sensitive, classify_file,
)
from .documents import (
    xlsx_to_markdown, convert_office_file, count_words,
)




def _auto_follow_symlinks(root: Path) -> bool:
    """Auto-detect: ``True`` if ``root`` has any direct symlinked child.

    Allows "fake working dir" patterns (e.g. a folder full of symlinks pointing
    at scattered source dirs across the user's machine) to work transparently
    without the caller having to know to pass ``follow_symlinks=True``.

    Override is always possible by passing an explicit ``follow_symlinks=True``
    or ``follow_symlinks=False`` to :func:`detect` / :func:`detect_incremental`.
    """
    try:
        for p in root.iterdir():
            if p.is_symlink():
                return True
    except (OSError, PermissionError):
        pass
    return False


def detect(root: Path, *, follow_symlinks: bool | None = None, google_workspace: bool | None = None, extra_excludes: list[str] | None = None) -> dict:
    root = root.resolve()
    if follow_symlinks is None:
        follow_symlinks = _auto_follow_symlinks(root)
    google_workspace = google_workspace_enabled() if google_workspace is None else google_workspace
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
    # CLI --exclude patterns are anchored at the scan root and appended last
    # so they win over any .graphifyignore/.gitignore rules (#947).
    if extra_excludes:
        for pat in extra_excludes:
            line = _parse_gitignore_line(pat)
            if line:
                ignore_patterns.append((root, line))
    _load_graphifyinclude(root)

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
                # Prune noise dirs in-place so os.walk never descends into them.
                # Dot dirs are allowed — users often want .github/, .claude/, etc.
                # Framework caches (.next, .nuxt, …) are caught by _is_noise_dir.
                # When negation patterns (!) exist, skip directory-level ignore
                # pruning so negated files inside can still be reached.
                has_negation = any(p.startswith("!") for _, p in ignore_patterns)
                dirnames[:] = [
                    d for d in dirnames
                    if not _is_noise_dir(d)
                    and (has_negation or not _is_ignored(dp / d, root, ignore_patterns))
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
            # Skip files inside our own converted/ dir (avoid re-processing sidecars)
            if str(p).startswith(str(converted_dir)):
                continue
        if _is_ignored(p, root, ignore_patterns):
            continue
        if _is_sensitive(p):
            skipped_sensitive.append(str(p))
            continue
        ftype = classify_file(p)
        if ftype:
            if p.suffix.lower() in GOOGLE_WORKSPACE_EXTENSIONS:
                if not google_workspace:
                    skipped_sensitive.append(
                        str(p)
                        + " [Google Workspace shortcut skipped - pass --google-workspace "
                        "or set GRAPHIFY_GOOGLE_WORKSPACE=1]"
                    )
                    continue
                try:
                    md_path = convert_google_workspace_file(p, converted_dir, xlsx_to_markdown=xlsx_to_markdown)
                except Exception as exc:
                    skipped_sensitive.append(str(p) + f" [Google Workspace export failed: {exc}]")
                    continue
                if md_path:
                    if _is_ignored(md_path, root, ignore_patterns):
                        continue
                    files[ftype].append(str(md_path))
                    total_words += count_words(md_path)
                else:
                    skipped_sensitive.append(str(p) + " [Google Workspace export produced no readable text]")
                continue
            # Office files: convert to markdown sidecar so subagents can read them
            if p.suffix.lower() in OFFICE_EXTENSIONS:
                md_path = convert_office_file(p, converted_dir)
                if md_path:
                    if _is_ignored(md_path, root, ignore_patterns):
                        continue
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
            f"Consider running on a subfolder."
        )

    return {
        "files": {k.value: v for k, v in files.items()},
        "total_files": total_files,
        "total_words": total_words,
        "needs_graph": needs_graph,
        "warning": warning,
        "skipped_sensitive": skipped_sensitive,
        "graphifyignore_patterns": len(ignore_patterns),
        "scan_root": str(root.resolve()),
    }


def _md5_file(path: Path) -> str:
    """MD5 of file contents streamed in 64KB chunks — for change detection only."""
    import hashlib as _hl
    h = _hl.md5(usedforsecurity=False)
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def load_manifest(manifest_path: str = _MANIFEST_PATH) -> dict:
    """Load the manifest from a previous run. Returns {} on any error."""
    try:
        return json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_manifest(
    files: dict[str, list[str]],
    manifest_path: str = _MANIFEST_PATH,
    *,
    kind: str = "both",
) -> None:
    """Save current file mtimes + content hashes for change detection.

    kind="ast"      — written by `graphify update` (AST-only rebuild). Stamps
                      ast_hash; preserves an existing semantic_hash only when
                      the file content is unchanged (mtime + hash match).
    kind="semantic" — written by `graphify extract` after semantic extraction.
                      Stamps semantic_hash; preserves existing ast_hash.
    kind="both"     — full pipeline: stamps both hashes (default).
    """
    existing = load_manifest(manifest_path)

    def _normalise_entry(entry):
        if isinstance(entry, (int, float)):
            return {"mtime": entry, "ast_hash": "", "semantic_hash": ""}
        if isinstance(entry, dict) and "hash" in entry and "ast_hash" not in entry:
            return {"mtime": entry.get("mtime", 0), "ast_hash": entry["hash"], "semantic_hash": ""}
        if isinstance(entry, dict):
            return entry
        return None

    # Seed from the existing manifest so incremental callers passing a subset
    # of files don't silently erase entries for untouched files (#917).
    # Prune entries whose file no longer exists on disk — those are genuine
    # deletions that detect_incremental() should treat as gone.
    manifest: dict[str, dict] = {}
    for f, entry in existing.items():
        normalised = _normalise_entry(entry)
        if normalised is None:
            continue
        try:
            if Path(f).exists():
                manifest[f] = normalised
        except OSError:
            continue

    for file_list in files.values():
        for f in file_list:
            try:
                p = Path(f)
                mtime = p.stat().st_mtime
                h = _md5_file(p)
            except OSError:
                continue  # file deleted between detect() and manifest write
            prev = _normalise_entry(existing.get(f, {})) or {}
            entry: dict = {"mtime": mtime}
            if kind in ("ast", "both"):
                entry["ast_hash"] = h
            else:
                entry["ast_hash"] = prev.get("ast_hash", "")
            if kind in ("semantic", "both"):
                entry["semantic_hash"] = h
            else:
                # Preserve semantic_hash only when content is unchanged
                entry["semantic_hash"] = prev.get("semantic_hash", "") if h == prev.get("ast_hash", "") else ""
            manifest[f] = entry
    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
    Path(manifest_path).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def detect_incremental(
    root: Path,
    manifest_path: str = _MANIFEST_PATH,
    *,
    follow_symlinks: bool | None = None,
    google_workspace: bool | None = None,
    kind: str = "semantic",
    extra_excludes: list[str] | None = None,
) -> dict:
    """Like detect(), but returns only new or modified files since the last run.

    kind="semantic" (default for extract): a file is "changed" when its
        semantic_hash is missing or its content has changed since the last
        semantic extraction pass. Use this for `graphify extract` so that
        files touched by `graphify update` (AST-only) are re-extracted
        semantically.
    kind="ast": a file is "changed" when its ast_hash is missing or its
        content has changed. Use this for `graphify update`.

    Fast path: mtime unchanged + hash matches → unchanged (free, no disk IO
    beyond stat). Slow path: mtime bumped → compare MD5 against the relevant
    hash field before re-extracting.

    Backwards compatible with legacy manifests storing plain float mtime values
    or {mtime, hash} dicts (treated as ast_hash only; semantic_hash = miss).

    The ``follow_symlinks`` flag is forwarded to :func:`detect` so corpora that
    rely on symlinked sub-trees (e.g. a ``state_of_truth/`` symlink pointing to a
    directory outside the scan root) are scanned consistently between full and
    incremental runs. ``None`` (default) means auto-detect: ``True`` when ``root``
    contains at least one direct symlinked child, ``False`` otherwise.
    """
    full = detect(root, follow_symlinks=follow_symlinks, google_workspace=google_workspace, extra_excludes=extra_excludes)
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
            stored = manifest.get(f)
            try:
                current_mtime = Path(f).stat().st_mtime
            except Exception:
                current_mtime = 0

            # Legacy manifest: plain float value — treat as ast_hash only
            if isinstance(stored, (int, float)):
                changed = stored is None or current_mtime > stored
            elif isinstance(stored, dict):
                # Normalise legacy {mtime, hash} to new schema
                if "hash" in stored and "ast_hash" not in stored:
                    stored = {"mtime": stored.get("mtime", 0), "ast_hash": stored["hash"], "semantic_hash": ""}
                hash_key = "semantic_hash" if kind == "semantic" else "ast_hash"
                stored_hash = stored.get(hash_key, "")
                # Missing semantic_hash means update ran but extract hasn't — always re-extract
                if not stored_hash:
                    changed = True
                else:
                    stored_mtime = stored.get("mtime")
                    if stored_mtime is None or current_mtime != stored_mtime:
                        # mtime bumped — verify with content hash before re-extracting
                        changed = _md5_file(Path(f)) != stored_hash
                    else:
                        changed = False
            else:
                changed = True  # unknown format, re-extract to be safe

            if changed:
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
