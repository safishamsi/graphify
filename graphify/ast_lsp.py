"""AST facts prepared for external LSP resolvers.

This module owns the mapping layer between graphify's AST extraction shape and
the JSON exchange format consumed by external LSP hook chains.
"""
from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Iterable


UNRESOLVED_CALLS_FILE = "unresolved_calls.json"

_SOURCE_LOCATION_RE = re.compile(r"\bL(\d+)\b")

_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".scala": "scala",
    ".php": "php",
    ".lua": "lua",
    ".luau": "lua",
    ".zig": "zig",
    ".ps1": "powershell",
    ".ex": "elixir",
    ".exs": "elixir",
    ".m": "objc",
    ".mm": "objc",
    ".jl": "julia",
    ".vue": "vue",
    ".svelte": "svelte",
    ".dart": "dart",
    ".v": "verilog",
    ".sv": "verilog",
    ".sql": "sql",
    ".r": "r",
    ".f": "fortran",
    ".F": "fortran",
    ".f90": "fortran",
    ".F90": "fortran",
    ".f95": "fortran",
    ".F95": "fortran",
    ".pas": "pascal",
    ".pp": "pascal",
}


def language_for_path(path: str | Path | None) -> str | None:
    if path is None:
        return None
    return _LANGUAGE_BY_SUFFIX.get(Path(str(path)).suffix)


def without_unresolved_calls(extraction: dict) -> dict:
    clean = dict(extraction)
    clean.pop("unresolved_calls", None)
    return clean


def load_unresolved_calls(graphify_out: Path) -> list[dict]:
    path = graphify_out / UNRESOLVED_CALLS_FILE
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]
    if isinstance(data, dict):
        calls = data.get("unresolved_calls", [])
        if isinstance(calls, list):
            return [c for c in calls if isinstance(c, dict)]
    return []


def _source_line(item: dict) -> int | None:
    raw = item.get("source_location")
    if not isinstance(raw, str):
        return None
    match = _SOURCE_LOCATION_RE.search(raw)
    if not match:
        return None
    return int(match.group(1))


def _source_languages(source_files: Iterable[str | Path] | None) -> set[str]:
    if source_files is None:
        return set()
    return {
        language
        for path in source_files
        for language in [language_for_path(path)]
        if language
    }


def _call_identity(call: dict, ordinal: int) -> str:
    """Stable-ish callsite id for LSP sidecar joins.

    The ordinal is included only as a tie-breaker for duplicate calls on the
    same line/range. The semantic fields keep the id stable across unrelated
    graph rebuild noise.
    """
    identity = {
        "source_file": call.get("source_file"),
        "source_location": call.get("source_location"),
        "caller": call.get("caller") or call.get("caller_nid"),
        "callee": call.get("callee"),
        "receiver": call.get("receiver"),
        "call_shape": call.get("call_shape"),
        "callee_range": call.get("callee_range"),
        "ordinal": ordinal,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "call_" + hashlib.sha1(encoded).hexdigest()[:16]


def _copy_calls_with_language(unresolved_calls: Iterable[dict]) -> tuple[list[dict], set[str]]:
    calls: list[dict] = []
    languages: set[str] = set()
    for ordinal, raw in enumerate(unresolved_calls):
        if not isinstance(raw, dict):
            continue
        call = dict(raw)
        language = call.get("language") or language_for_path(call.get("source_file"))
        if language:
            call["language"] = language
            languages.add(language)
        call.setdefault("call_id", _call_identity(call, ordinal))
        calls.append(call)
    return calls, languages


def symbol_index(nodes: Iterable[dict]) -> list[dict]:
    """Return a compact source-position index for LSP definition mapping."""
    symbols: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        source_file = node.get("source_file")
        if not node_id or not source_file:
            continue
        key = (str(node_id), str(source_file))
        if key in seen:
            continue
        seen.add(key)
        symbol = {
            "id": node_id,
            "label": node.get("label"),
            "source_file": source_file,
            "source_location": node.get("source_location"),
        }
        source_line = _source_line(node)
        if source_line is not None:
            symbol["source_line"] = source_line
        language = node.get("language") or language_for_path(source_file)
        if language:
            symbol["language"] = language
        if "file_type" in node:
            symbol["file_type"] = node["file_type"]
        symbols.append(symbol)
    return symbols


def write_lsp_exchange(
    graphify_out: Path,
    extraction: dict,
    *,
    root: Path,
    source_files: Iterable[str | Path] | None = None,
) -> tuple[Path, set[str]]:
    """Write unresolved calls and symbol index for external LSP resolvers."""
    graphify_out.mkdir(parents=True, exist_ok=True)
    calls, call_languages = _copy_calls_with_language(extraction.get("unresolved_calls", []))
    symbols = symbol_index(extraction.get("nodes", []))
    symbol_languages = {
        str(symbol["language"])
        for symbol in symbols
        if symbol.get("language")
    }
    languages = call_languages | symbol_languages | _source_languages(source_files)
    payload = {
        "schema_version": 1,
        "generated_by": "graphify",
        "languages": sorted(languages),
        "count": len(calls),
        "symbol_count": len(symbols),
        "unresolved_calls": calls,
        "symbols": symbols,
    }
    path = graphify_out / UNRESOLVED_CALLS_FILE
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path, languages


def preserve_unresolved_calls(
    extraction: dict,
    *,
    graphify_out: Path,
    evict_sources: set[str],
) -> dict:
    """Carry unresolved calls for unchanged files across incremental rebuilds."""
    preserved = [
        call for call in load_unresolved_calls(graphify_out)
        if not evict_sources or call.get("source_file") not in evict_sources
    ]
    if not preserved:
        return extraction
    merged = dict(extraction)
    merged["unresolved_calls"] = list(extraction.get("unresolved_calls", [])) + preserved
    return merged
