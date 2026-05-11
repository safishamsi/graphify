"""Shared graph build pipeline helpers.

This module keeps the orchestration boundary out of agent skill snippets and
CLI glue. ``graphify.extract.extract`` stays deterministic AST extraction;
configured enrichments run here after AST and semantic fragments are merged.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from graphify.lsp_enrichment import LspEnrichmentSummary, apply_lsp_enrichment


def empty_extraction() -> dict:
    return {
        "nodes": [],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }


def merge_ast_semantic(ast_result: dict | None, sem_result: dict | None) -> dict:
    """Merge AST and semantic extraction fragments into one build payload."""
    ast = ast_result or {}
    sem = sem_result or {}
    return {
        "nodes": list(ast.get("nodes", [])) + list(sem.get("nodes", [])),
        "edges": list(ast.get("edges", [])) + list(sem.get("edges", [])),
        "hyperedges": list(ast.get("hyperedges", [])) + list(sem.get("hyperedges", [])),
        "unresolved_calls": list(ast.get("unresolved_calls", [])) + list(sem.get("unresolved_calls", [])),
        "enrichments": list(ast.get("enrichments", [])) + list(sem.get("enrichments", [])),
        "input_tokens": ast.get("input_tokens", 0) + sem.get("input_tokens", 0),
        "output_tokens": ast.get("output_tokens", 0) + sem.get("output_tokens", 0),
    }


def _root_from_marker(graphify_out: Path) -> Path | None:
    for marker in (graphify_out / ".graphify_root", Path(".graphify_root")):
        try:
            if marker.exists():
                raw = marker.read_text(encoding="utf-8").strip()
                if raw:
                    return Path(raw).expanduser().resolve()
        except OSError:
            continue
    return None


def resolve_pipeline_root(root: str | Path | None = None, *, graphify_out: str | Path | None = None) -> Path:
    """Resolve the project root for configured enrichment hooks.

    Agent skill snippets often carry a literal ``INPUT_PATH`` placeholder. When
    that was not substituted, fall back to the persisted graph root or cwd.
    """
    out = Path(graphify_out) if graphify_out is not None else Path("graphify-out")
    if root is not None and str(root) not in ("", "INPUT_PATH"):
        candidate = Path(root).expanduser()
        try:
            return candidate.resolve()
        except OSError:
            pass
    return _root_from_marker(out) or Path(".").resolve()


def infer_source_files(extraction: dict, *, root: str | Path | None = None) -> list[Path]:
    """Infer source files from an extraction payload for enrichment/cache keys."""
    resolved_root = Path(root).expanduser().resolve() if root is not None else Path(".").resolve()
    seen: set[str] = set()
    files: list[Path] = []
    for bucket in ("unresolved_calls", "nodes", "edges"):
        for item in extraction.get(bucket, []):
            if not isinstance(item, dict):
                continue
            source = item.get("source_file")
            if not source:
                continue
            key = str(source).replace("\\", "/")
            if key in seen:
                continue
            seen.add(key)
            path = Path(str(source))
            files.append(path if path.is_absolute() else resolved_root / path)
    return files


def apply_configured_enrichments(
    extraction: dict,
    *,
    root: str | Path | None = None,
    graphify_out: str | Path = "graphify-out",
    source_files: Iterable[str | Path] | None = None,
    evict_sources: set[str] | None = None,
) -> tuple[dict, LspEnrichmentSummary]:
    """Apply repo-configured post-AST enrichments to a build payload."""
    out = Path(graphify_out)
    resolved_root = resolve_pipeline_root(root, graphify_out=out)
    sources = list(source_files) if source_files is not None else infer_source_files(extraction, root=resolved_root)
    return apply_lsp_enrichment(
        extraction,
        root=resolved_root,
        graphify_out=out,
        source_files=sources,
        evict_sources=evict_sources,
    )


def finalize_extraction_for_build(
    extraction: dict,
    *,
    root: str | Path | None = None,
    graphify_out: str | Path = "graphify-out",
    source_files: Iterable[str | Path] | None = None,
    evict_sources: set[str] | None = None,
) -> tuple[dict, LspEnrichmentSummary]:
    """Return the payload that should be passed to ``build_from_json``/``build``."""
    return apply_configured_enrichments(
        extraction,
        root=root,
        graphify_out=graphify_out,
        source_files=source_files,
        evict_sources=evict_sources,
    )


def finalize_extraction_files(
    *,
    ast_path: str | Path,
    semantic_path: str | Path,
    output_path: str | Path,
    root: str | Path | None = None,
    graphify_out: str | Path = "graphify-out",
    source_files: Iterable[str | Path] | None = None,
    evict_sources: set[str] | None = None,
) -> tuple[dict, LspEnrichmentSummary, dict]:
    """Load AST/semantic sidecars, finalize them, and write the build payload."""
    ast = json.loads(Path(ast_path).read_text(encoding="utf-8"))
    sem_file = Path(semantic_path)
    semantic = (
        json.loads(sem_file.read_text(encoding="utf-8"))
        if sem_file.exists()
        else empty_extraction()
    )
    merged = merge_ast_semantic(ast, semantic)
    finalized, lsp_summary = finalize_extraction_for_build(
        merged,
        root=root,
        graphify_out=graphify_out,
        source_files=source_files,
        evict_sources=evict_sources,
    )
    Path(output_path).write_text(json.dumps(finalized, indent=2), encoding="utf-8")
    stats = {
        "ast_nodes": len(ast.get("nodes", [])),
        "semantic_nodes": len(semantic.get("nodes", [])),
        "total_nodes": len(finalized.get("nodes", [])),
        "total_edges": len(finalized.get("edges", [])),
    }
    return finalized, lsp_summary, stats
