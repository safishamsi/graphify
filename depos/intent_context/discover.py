"""Discover intent-bearing files under a repo root."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from depos.analysis.config import IntentContextConfig
from depos.intent_context.classify_path import classify_path
from depos.intent_context.intent_yaml import load_intent_yaml

_DENY_DIR_PARTS = frozenset(
    {
        "node_modules",
        ".git",
        "dist",
        "build",
        "graphify-out",
        ".next",
        "__pycache__",
        ".venv",
        "venv",
        "target",
        ".turbo",
    }
)

_BINARY_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".wasm",
        ".so",
        ".dylib",
        ".dll",
        ".exe",
        ".bin",
        ".mp4",
        ".mp3",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
    }
)

DEFAULT_INTENT_GLOBS: list[str] = [
    "**/*.md",
    "**/*.rst",
    "**/README*",
    "**/CONTRIBUTING*",
    "**/ADR*.md",
    ".github/**/*.md",
]


@dataclass
class DiscoveredFile:
    relpath: str
    abs_path: Path
    byte_length: int
    sha256: str
    path_classification: str
    warnings: list[str]


def _path_denied(path: Path) -> bool:
    return any(part in _DENY_DIR_PARTS for part in path.parts)


def _iter_glob(repo_root: Path, pattern: str) -> list[Path]:
    """Glob from repo root; skip denied dirs (same spirit as depos.ingest.prompts)."""
    seen: set[Path] = set()
    out: list[Path] = []
    if "{" in pattern and "}" in pattern:
        prefix, rest = pattern.split("{", 1)
        choices, tail = rest.split("}", 1)
        for choice in choices.split(","):
            for path in repo_root.glob(f"{prefix}{choice}{tail}"):
                if path.is_file() and path not in seen and not _path_denied(path):
                    seen.add(path)
                    out.append(path)
        return out
    for path in repo_root.glob(pattern):
        if path.is_file() and path not in seen and not _path_denied(path):
            seen.add(path)
            out.append(path)
    return out


def _matches_any_glob(rel_posix: str, globs: list[str]) -> bool:
    from fnmatch import fnmatch

    for g in globs:
        if fnmatch(rel_posix, g) or fnmatch(rel_posix, g.lstrip("./")):
            return True
    return False


def discover_intent_files(
    repo_root: Path,
    icfg: IntentContextConfig,
    *,
    extra_include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
) -> tuple[list[DiscoveredFile], list[str]]:
    """Return discovered files and global warnings (e.g. caps)."""
    repo_root = repo_root.resolve()
    yaml_inc, yaml_exc = load_intent_yaml(repo_root)
    patterns = list(DEFAULT_INTENT_GLOBS)
    patterns.extend(yaml_inc)
    if extra_include_globs:
        patterns.extend(extra_include_globs)
    exc = list(yaml_exc)
    if exclude_globs:
        exc.extend(exclude_globs)

    collected: dict[str, Path] = {}
    for pat in patterns:
        for p in _iter_glob(repo_root, pat):
            rel = p.relative_to(repo_root).as_posix()
            if exc and _matches_any_glob(rel, exc):
                continue
            if p.suffix.lower() in _BINARY_SUFFIXES:
                continue
            collected[rel] = p

    total_bytes = 0
    global_warnings: list[str] = []
    results: list[DiscoveredFile] = []

    for rel in sorted(collected.keys()):
        path = collected[rel]
        try:
            raw = path.read_bytes()
        except OSError as e:
            global_warnings.append(f"{rel}: read error: {e}")
            continue
        blen = len(raw)
        if blen > icfg.max_bytes_per_file:
            global_warnings.append(
                f"{rel}: skipped (size {blen} > max_bytes_per_file {icfg.max_bytes_per_file})"
            )
            continue
        if total_bytes + blen > icfg.max_input_bytes_per_repo:
            global_warnings.append(
                f"repo cap max_input_bytes_per_repo={icfg.max_input_bytes_per_repo} hit; remaining files skipped"
            )
            break
        total_bytes += blen
        h = hashlib.sha256(raw).hexdigest()
        rel_path = Path(rel)
        cls = classify_path(rel_path)
        results.append(
            DiscoveredFile(
                relpath=rel,
                abs_path=path,
                byte_length=blen,
                sha256=h,
                path_classification=cls,
                warnings=[],
            )
        )

    return results, global_warnings
