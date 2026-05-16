"""Shared graph build pipeline helpers.

This module keeps the orchestration boundary out of agent skill snippets and
CLI glue. ``graphify.extract.extract`` stays deterministic AST extraction;
configured enrichments run here after AST and semantic fragments are merged.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
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


_RUNTIME_NODE_FIELDS = {
    "color",
    "community",
    "community_name",
    "degree",
    "font",
    "norm_label",
    "size",
    "title",
}

_STRUCTURAL_REBUILD_EDGE_RELATIONS = {"contains", "method"}


def _source_key(source: str | Path | None, root: Path) -> str | None:
    if not source:
        return None
    path = Path(str(source))
    if path.is_absolute():
        try:
            source = path.resolve().relative_to(root)
        except ValueError:
            source = path
    return str(source).replace("\\", "/")


def source_keys_from_paths(paths: Iterable[str | Path], root: str | Path) -> set[str]:
    resolved_root = Path(root).resolve()
    keys: set[str] = set()
    for path in paths:
        key = _source_key(path, resolved_root)
        if key:
            keys.add(key)
    return keys


def source_keys_from_payload(payload: dict, root: str | Path) -> set[str]:
    resolved_root = Path(root).resolve()
    keys: set[str] = set()
    for bucket in ("nodes", "edges", "unresolved_calls"):
        for item in payload.get(bucket, []):
            if not isinstance(item, dict):
                continue
            key = _source_key(item.get("source_file"), resolved_root)
            if key:
                keys.add(key)
    return keys


def _label_token(label: object) -> str:
    text = str(label or "").strip()
    text = re.sub(r"\(\)$", "", text)
    return re.sub(r"[^a-zA-Z0-9]+", "", text).lower()


def _label_tail(label: object) -> str:
    text = str(label or "").strip()
    parts = re.split(r"::|#|\.|/", text)
    return _label_token(parts[-1] if parts else text)


def _existing_label_is_richer(existing: object, incoming: object) -> bool:
    if not existing or not incoming or existing == incoming:
        return False
    existing_text = str(existing)
    incoming_token = _label_token(incoming)
    if not incoming_token or len(existing_text) <= len(str(incoming)):
        return False
    if _label_tail(existing_text) == incoming_token:
        return True
    return ("::" in existing_text or "#" in existing_text) and _label_token(existing_text).endswith(incoming_token)


def _same_source_file(left: object, right: object) -> bool:
    # Update inputs are pre-relativized before node merge; normalize separators only.
    if not left or not right:
        return False
    return str(left).replace("\\", "/") == str(right).replace("\\", "/")


def merge_update_node(existing: dict | None, incoming: dict) -> dict:
    """Merge a freshly extracted AST node with an existing graph node.

    AST-only rebuilds should refresh concrete source facts, but they must not
    erase richer semantic labels attached to the same stable node id.
    """
    if not existing:
        return dict(incoming)
    preserve_existing_source = (
        _existing_label_is_richer(existing.get("label"), incoming.get("label"))
        and bool(existing.get("source_file"))
        and bool(incoming.get("source_file"))
        and not _same_source_file(existing.get("source_file"), incoming.get("source_file"))
    )
    merged = {
        key: value
        for key, value in existing.items()
        if key not in _RUNTIME_NODE_FIELDS and key != "id"
    }
    for key, value in incoming.items():
        if key == "id":
            continue
        if key == "label" and _existing_label_is_richer(merged.get("label"), value):
            continue
        if preserve_existing_source and key in {"source_file", "source_location", "source_line"}:
            continue
        if value is None and merged.get(key) not in (None, ""):
            continue
        merged[key] = value
    return {"id": incoming["id"], **merged}


def _select_update_node(existing: dict | None, candidates: list[dict], root: Path) -> dict:
    """Pick the incoming node that best matches an existing exported node.

    Entity ids are not globally collision-proof. During update, prefer the
    candidate from the same source file as the existing graph node so a richer
    semantic label is not accidentally paired with a different AST source.
    """
    if existing:
        existing_source = _source_key(existing.get("source_file"), root)
        if existing_source:
            for candidate in candidates:
                if _source_key(candidate.get("source_file"), root) == existing_source:
                    return candidate
    return candidates[-1]


def _edge_signature(edge: dict, root: Path) -> tuple:
    return (
        edge.get("source"),
        edge.get("target"),
        edge.get("relation"),
        edge.get("context"),
        _source_key(edge.get("source_file"), root),
        edge.get("source_location"),
    )


def _merge_json_lists(*lists: Iterable[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for values in lists:
        for value in values or []:
            if not isinstance(value, dict):
                continue
            key = json.dumps(value, sort_keys=True, separators=(",", ":"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(value)
    return merged


def _is_rebuilt_structural_edge(edge: dict, rebuilt_sources: set[str], root: Path) -> bool:
    source = _source_key(edge.get("source_file"), root)
    if source not in rebuilt_sources:
        return False
    if str(edge.get("context", "")).startswith("lsp_definition"):
        return True
    if edge.get("relation") == "calls":
        # AST calls carry call context; semantic extraction also emits
        # relation="calls" but without this callsite-shaped metadata.
        contexts = edge.get("contexts") or []
        return edge.get("context") == "call" or "call" in contexts
    return edge.get("relation") in _STRUCTURAL_REBUILD_EDGE_RELATIONS


def merge_update_payload(
    existing: dict,
    result: dict,
    *,
    evict_sources: Iterable[str | Path] | None = None,
    rebuilt_sources: Iterable[str | Path] | None = None,
    root: str | Path = ".",
) -> dict:
    """Merge an AST-only update payload into an existing exported graph.

    This is the graphify update merge policy. It is intentionally stricter
    than ``networkx.Graph.update``: same-ID AST nodes are merged with existing
    semantic attrs, freshly rebuilt structural edges replace stale ones, and
    semantic edges/hyperedges are preserved.
    """
    resolved_root = Path(root).resolve()
    evict_source_set = {
        _source_key(source, resolved_root) or str(source)
        for source in (evict_sources or [])
    }
    rebuilt_source_set = {
        _source_key(source, resolved_root) or str(source)
        for source in (rebuilt_sources or [])
    }
    existing_nodes = {
        node.get("id"): node
        for node in existing.get("nodes", [])
        if isinstance(node, dict) and node.get("id")
    }
    incoming_nodes_by_id: dict[str, list[dict]] = defaultdict(list)
    for node in result.get("nodes", []):
        if isinstance(node, dict) and node.get("id"):
            incoming_nodes_by_id[node["id"]].append(node)
    new_nodes = []
    for node_id, candidates in incoming_nodes_by_id.items():
        existing_node = existing_nodes.get(node_id)
        selected = _select_update_node(existing_node, candidates, resolved_root)
        new_nodes.append(merge_update_node(existing_node, selected))
    new_ids = {node["id"] for node in new_nodes}
    preserved_nodes = [
        node for node in existing_nodes.values()
        if node["id"] not in new_ids
        and (
            not evict_source_set
            or _source_key(node.get("source_file"), resolved_root) not in evict_source_set
        )
    ]
    all_ids = new_ids | {node["id"] for node in preserved_nodes}
    new_edge_keys = {
        _edge_signature(edge, resolved_root)
        for edge in result.get("edges", [])
        if isinstance(edge, dict)
    }
    preserved_edges = []
    for edge in existing.get("links", existing.get("edges", [])):
        if not isinstance(edge, dict):
            continue
        if edge.get("source") not in all_ids or edge.get("target") not in all_ids:
            continue
        if _edge_signature(edge, resolved_root) in new_edge_keys:
            continue
        if _is_rebuilt_structural_edge(
            edge,
            rebuilt_source_set | evict_source_set,
            resolved_root,
        ):
            continue
        preserved_edges.append(edge)
    return {
        "nodes": new_nodes + preserved_nodes,
        "edges": list(result.get("edges", [])) + preserved_edges,
        "hyperedges": _merge_json_lists(
            existing.get("hyperedges", []),
            result.get("hyperedges", []),
        ),
        "unresolved_calls": result.get("unresolved_calls", []),
        "enrichments": list(result.get("enrichments", [])),
        "input_tokens": 0,
        "output_tokens": 0,
    }


def _sidecar_path(graphify_out: Path, name: str) -> Path:
    path = graphify_out / name
    return path if path.exists() else Path(name)


def merge_update_files(
    *,
    graph_path: str | Path = "graphify-out/graph.json",
    extraction_path: str | Path | None = None,
    incremental_path: str | Path | None = None,
    root: str | Path = ".",
) -> tuple[dict, dict]:
    """Merge update sidecar files and rewrite the extraction sidecar.

    Agent skill snippets use this instead of raw ``networkx.Graph.update`` so
    update behavior matches the CLI/watch merge policy.
    """
    graph_file = Path(graph_path)
    graphify_out = graph_file.parent
    extract_file = (
        Path(extraction_path)
        if extraction_path is not None
        else _sidecar_path(graphify_out, ".graphify_extract.json")
    )
    incremental_file = (
        Path(incremental_path)
        if incremental_path is not None
        else _sidecar_path(graphify_out, ".graphify_incremental.json")
    )
    resolved_root = Path(root)
    if str(resolved_root) == "INPUT_PATH":
        resolved_root = Path(".")

    existing = json.loads(graph_file.read_text(encoding="utf-8"))
    new_extraction = json.loads(extract_file.read_text(encoding="utf-8"))
    incremental = (
        json.loads(incremental_file.read_text(encoding="utf-8"))
        if incremental_file.exists()
        else {}
    )

    rebuilt_sources: set[str] = set()
    for files in incremental.get("new_files", {}).values():
        rebuilt_sources.update(str(path) for path in files)
    rebuilt_sources.update(source_keys_from_payload(new_extraction, resolved_root))
    deleted = set(str(path) for path in incremental.get("deleted_files", []))

    merged = merge_update_payload(
        existing,
        new_extraction,
        evict_sources=deleted,
        rebuilt_sources=rebuilt_sources,
        root=resolved_root,
    )
    extract_file.write_text(json.dumps(merged), encoding="utf-8")

    manifest_saved = False
    if incremental.get("files"):
        from graphify.detect import save_manifest

        save_manifest(incremental["files"])
        manifest_saved = True

    stats = {
        "nodes": len(merged.get("nodes", [])),
        "edges": len(merged.get("edges", [])),
        "manifest_saved": manifest_saved,
        "extraction_path": str(extract_file),
    }
    return merged, stats


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
