"""Data-only graph enrichment loading.

Enrichments are graph fragments produced by external tools, such as an LSP
injector. Graphify only reads JSON here; it does not execute plugin code.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from graphify.lsp_promotion import promote_lsp_evidence, promote_lsp_evidence_documents


_LARGE_DEBUG_METADATA_KEYS = {
    "empty_definition_calls",
    "error_details",
    "missing_source_file_details",
    "server_stderr_tail",
    "unmapped_definitions",
}


def _metadata_summary(raw: dict) -> dict:
    metadata: dict = {}
    for key, value in raw.items():
        if key in _LARGE_DEBUG_METADATA_KEYS:
            if isinstance(value, list):
                metadata[f"{key}_count"] = len(value)
            continue
        if key == "server_command":
            if isinstance(value, list):
                metadata["server_command_count"] = len(value)
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            metadata[key] = value
        elif isinstance(value, list):
            if len(value) <= 20 and all(isinstance(item, (str, int, float, bool)) or item is None for item in value):
                metadata[key] = value
            else:
                metadata[f"{key}_count"] = len(value)
        elif isinstance(value, dict):
            simple = {
                k: v for k, v in value.items()
                if isinstance(v, (str, int, float, bool)) or v is None
            }
            if len(simple) == len(value) and len(simple) <= 20:
                metadata[key] = simple
            else:
                metadata[f"{key}_keys"] = sorted(str(k) for k in value.keys())[:20]
    return metadata


def _json_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(p for p in path.iterdir() if p.is_file() and p.suffix == ".json")
    raise FileNotFoundError(f"enrichment path not found: {path}")


def _read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: enrichment JSON must be an object")
    return data


def _list_field(data: dict, key: str, path: Path) -> list:
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{path}: '{key}' must be a list")
    return value


def _display_path(path: Path) -> str:
    parts = path.parts
    if len(parts) >= 3 and parts[-3] == "enrichment":
        return str(Path(*parts[-3:]))
    return path.name


def _metadata(data: dict, path: Path, nodes: list, edges: list, hyperedges: list) -> dict:
    raw = data.get("metadata", {})
    metadata = _metadata_summary(raw) if isinstance(raw, dict) else {}
    for key in (
        "source",
        "generated_by",
        "generator",
        "version",
        "language",
        "lsp_server",
        "created_at",
    ):
        if key in data and key not in metadata:
            metadata[key] = data[key]
    metadata.setdefault("path", _display_path(path))
    metadata["nodes"] = len(nodes)
    metadata["edges"] = len(edges)
    metadata["hyperedges"] = len(hyperedges)
    return metadata


def _lsp_aggregate_metadata(entries: list[tuple[Path, dict]], edges: list, promotion_summary: dict) -> dict:
    languages = sorted({
        str(data.get("language") or data.get("metadata", {}).get("language"))
        for _path, data in entries
        if data.get("language") or data.get("metadata", {}).get("language")
    })
    resolvers = sorted({
        str(
            data.get("lsp_resolver")
            or data.get("metadata", {}).get("resolver_name")
            or data.get("metadata", {}).get("hook_name")
        )
        for _path, data in entries
        if data.get("lsp_resolver") or data.get("metadata", {}).get("resolver_name") or data.get("metadata", {}).get("hook_name")
    })
    servers = sorted({
        str(data.get("lsp_server") or data.get("metadata", {}).get("lsp_server"))
        for _path, data in entries
        if data.get("lsp_server") or data.get("metadata", {}).get("lsp_server")
    })
    metadata = {
        "generated_by": "graphify-lsp-promotion",
        "source": "lsp_evidence",
        "path": _display_path(entries[0][0].parent if len(entries) > 1 else entries[0][0]),
        "sidecar_count": len(entries),
        "nodes": 0,
        "edges": len(edges),
        "hyperedges": 0,
        "promotion": promotion_summary,
    }
    if languages:
        metadata["language"] = languages[0] if len(languages) == 1 else languages
    if resolvers:
        metadata["lsp_resolvers"] = resolvers
        metadata["lsp_resolver_count"] = len(resolvers)
    if servers:
        metadata["lsp_servers"] = servers
        metadata["lsp_server_count"] = len(servers)

    for key in (
        "calls_seen",
        "language_calls",
        "candidate_calls",
        "requests_sent",
        "definitions_seen",
        "evidence_records",
        "empty_definition_results",
        "missing_source_files",
    ):
        total = 0
        seen = False
        for _path, data in entries:
            raw = data.get("metadata", {}).get(key)
            if isinstance(raw, (int, float)):
                total += raw
                seen = True
        if seen:
            metadata[key] = total

    for key in (
        "request_concurrency",
        "request_timeout",
        "root",
        "root_uri",
        "server_cwd",
        "settle_seconds",
    ):
        values = []
        for _path, data in entries:
            value = data.get("metadata", {}).get(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                values.append(value)
        unique_values = []
        for value in values:
            if value not in unique_values:
                unique_values.append(value)
        if len(unique_values) == 1:
            metadata[key] = unique_values[0]
        elif unique_values:
            metadata[key] = unique_values

    errors = 0
    for _path, data in entries:
        raw = data.get("metadata", {}).get("errors")
        if isinstance(raw, list):
            errors += len(raw)
        elif isinstance(raw, (int, float)):
            errors += int(raw)
    metadata["errors"] = errors
    return metadata


def _load_lsp_evidence_enrichments(entries: list[tuple[Path, dict]]) -> dict:
    edges, promotion_summary = promote_lsp_evidence_documents(data for _path, data in entries)
    return {
        "nodes": [],
        "edges": edges,
        "hyperedges": [],
        "enrichments": [_lsp_aggregate_metadata(entries, edges, promotion_summary)],
        "input_tokens": 0,
        "output_tokens": 0,
    }


def load_enrichment(path: Path) -> dict:
    """Load one enrichment JSON file as an extraction-shaped graph fragment."""
    data = _read_json(path)

    nodes = _list_field(data, "nodes", path)
    promotion_summary: dict = {}
    if "lsp_evidence" in data:
        edges, promotion_summary = promote_lsp_evidence(data)
    else:
        edges = _list_field(data, "edges", path)
        if not edges and "links" in data:
            edges = _list_field(data, "links", path)
    hyperedges = _list_field(data, "hyperedges", path)
    metadata = _metadata(data, path, nodes, edges, hyperedges)
    if promotion_summary:
        metadata["promotion"] = promotion_summary

    return {
        "nodes": nodes,
        "edges": edges,
        "hyperedges": hyperedges,
        "enrichments": [metadata],
        "input_tokens": 0,
        "output_tokens": 0,
    }


def load_enrichments(paths: Iterable[Path]) -> list[dict]:
    """Load enrichment JSON files from files or directories, preserving order."""
    chunks: list[dict] = []
    lsp_entries: list[tuple[Path, dict]] = []
    for path in paths:
        for json_path in _json_files(path):
            data = _read_json(json_path)
            if "lsp_evidence" in data:
                lsp_entries.append((json_path, data))
            else:
                chunks.append(load_enrichment(json_path))
    if lsp_entries:
        chunks.append(_load_lsp_evidence_enrichments(lsp_entries))
    return chunks


def merge_enrichments(base: dict, enrichments: Iterable[dict]) -> dict:
    """Append enrichment chunks to an extraction dict."""
    merged = {
        "nodes": list(base.get("nodes", [])),
        "edges": list(base.get("edges", [])),
        "hyperedges": list(base.get("hyperedges", [])),
        "enrichments": list(base.get("enrichments", [])),
        "input_tokens": base.get("input_tokens", 0),
        "output_tokens": base.get("output_tokens", 0),
    }
    for enrichment in enrichments:
        merged["nodes"].extend(enrichment.get("nodes", []))
        merged["edges"].extend(enrichment.get("edges", []))
        merged["hyperedges"].extend(enrichment.get("hyperedges", []))
        merged["enrichments"].extend(enrichment.get("enrichments", []))
        merged["input_tokens"] += enrichment.get("input_tokens", 0)
        merged["output_tokens"] += enrichment.get("output_tokens", 0)
    return merged
