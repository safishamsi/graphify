"""Strict cache for LSP enrichment sidecars."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Iterable


LSP_CACHE_VERSION = "lsp-v1-evidence-promotion"

_WORKSPACE_CONFIG_FILES = (
    ".solargraph.yml",
    "Gemfile",
    "Gemfile.lock",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "tsconfig.json",
    "jsconfig.json",
    "pyproject.toml",
    "pyrightconfig.json",
    "basedpyrightconfig.json",
    "requirements.txt",
    "uv.lock",
)


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _update_file_hash(h: "hashlib._Hash", path: Path, root: Path) -> None:
    h.update(_rel(path, root).encode("utf-8", errors="surrogateescape"))
    h.update(b"\0")
    if not path.exists() or not path.is_file():
        h.update(b"missing")
        h.update(b"\0")
        return
    h.update(b"file")
    h.update(b"\0")
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    h.update(b"\0")


def lsp_cache_key(
    *,
    root: Path,
    source_files: Iterable[str | Path] | None,
    unresolved_calls_path: Path,
    config: dict,
) -> str:
    """Return a conservative cache key for one full LSP enrichment run."""
    h = hashlib.sha256()
    h.update(LSP_CACHE_VERSION.encode("utf-8"))
    h.update(b"\0config\0")
    h.update(json.dumps(config.get("lsp", {}), sort_keys=True, separators=(",", ":")).encode("utf-8"))
    h.update(b"\0exchange\0")
    _update_file_hash(h, unresolved_calls_path, root)

    h.update(b"\0sources\0")
    for item in sorted(str(p) for p in (source_files or [])):
        path = Path(item)
        _update_file_hash(h, path if path.is_absolute() else root / path, root)

    h.update(b"\0workspace-config\0")
    for name in _WORKSPACE_CONFIG_FILES:
        _update_file_hash(h, root / name, root)
    return h.hexdigest()


def _cache_dir(graphify_out: Path, key: str) -> Path:
    return graphify_out / "cache" / "lsp" / key


def restore_lsp_cache(graphify_out: Path, key: str, enrichment_dir: Path) -> bool:
    src = _cache_dir(graphify_out, key)
    if not src.is_dir():
        return False
    json_files = sorted(src.glob("*.json"))
    if not json_files:
        return False
    enrichment_dir.mkdir(parents=True, exist_ok=True)
    for old in enrichment_dir.glob("*.json"):
        old.unlink()
    for path in json_files:
        shutil.copy2(path, enrichment_dir / path.name)
    return True


def save_lsp_cache(graphify_out: Path, key: str, enrichment_dir: Path) -> None:
    if not enrichment_dir.is_dir():
        return
    target = _cache_dir(graphify_out, key)
    target.mkdir(parents=True, exist_ok=True)
    for old in target.glob("*.json"):
        old.unlink()
    for path in sorted(enrichment_dir.glob("*.json")):
        shutil.copy2(path, target / path.name)
