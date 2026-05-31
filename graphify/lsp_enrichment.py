"""Config-gated LSP enrichment orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from graphify.ast_lsp import (
    preserve_unresolved_calls,
    without_unresolved_calls,
    write_lsp_exchange,
)
from graphify.enrichment import load_enrichments, merge_enrichments
from graphify.lsp_cache import lsp_cache_key, restore_lsp_cache, save_lsp_cache
from graphify.pipeline_hooks import (
    ENRICHMENT_DIR,
    load_hook_state,
    run_lsp_hooks,
)

LSP_ENRICHMENT_SUBDIR = "lsp"
_LSP_CONTEXT_PREFIX = "lsp_definition"
_LSP_EDGE_METADATA_KEYS = {
    "definition_file",
    "definition_range",
    "definition_uri",
    "receiver_type",
    "receiver_type_confidence",
}


@dataclass(frozen=True)
class LspEnrichmentSummary:
    enabled: bool
    unresolved_path: Path | None = None
    unresolved_count: int = 0
    languages: tuple[str, ...] = ()
    ran_hooks: tuple[str, ...] = ()
    merged_files: int = 0
    merged_nodes: int = 0
    merged_edges: int = 0
    cache_hit: bool = False
    cache_enabled: bool = False

    def log_lines(self, prefix: str) -> list[str]:
        if not self.enabled:
            return []
        lines = [
            f"{prefix} LSP exchange: {self.unresolved_path} — "
            f"{self.unresolved_count} unresolved call(s)"
        ]
        if self.ran_hooks:
            lines.append(f"{prefix} LSP hooks ran: {', '.join(self.ran_hooks)}")
        elif self.cache_hit:
            lines.append(f"{prefix} LSP enrichment cache hit")
        if self.merged_files:
            lines.append(
                f"{prefix} Merged {self.merged_files} LSP enrichment file(s): "
                f"{self.merged_nodes} nodes, {self.merged_edges} edges"
            )
        return lines

    def brief_line(self) -> str | None:
        if not self.enabled:
            return None
        return f"LSP: {self.unresolved_count} unresolved calls, {self.merged_edges} enriched edges"


def _context_values(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if value:
        return [str(value)]
    return []


def _without_lsp_contexts(value):
    contexts = [
        context for context in _context_values(value)
        if not context.startswith(_LSP_CONTEXT_PREFIX)
    ]
    if not contexts:
        return None
    return contexts if isinstance(value, list) else contexts[0]


def _without_lsp_edge_data(edge: dict) -> dict | None:
    context = _without_lsp_contexts(edge.get("context")) if "context" in edge else None
    if "context" in edge and context is None:
        return None
    clean = {
        key: value for key, value in edge.items()
        if not key.startswith("lsp_") and key not in _LSP_EDGE_METADATA_KEYS
    }
    if "context" in clean:
        clean["context"] = context
    if "contexts" in clean:
        context_values = [
            context for context in _context_values(clean["contexts"])
            if not context.startswith(_LSP_CONTEXT_PREFIX)
        ]
        primary_context = clean.get("context")
        if primary_context:
            context_values.append(str(primary_context))
        contexts = sorted(set(context_values))
        if len(contexts) > 1:
            clean["contexts"] = contexts
        else:
            clean.pop("contexts", None)
    return clean


def _is_lsp_enrichment(metadata: dict) -> bool:
    return (
        metadata.get("generated_by") == "graphify-lsp-promotion"
        or metadata.get("source") == "lsp_evidence"
        or str(metadata.get("path", "")).startswith(f"{ENRICHMENT_DIR}/{LSP_ENRICHMENT_SUBDIR}")
        or any(str(key).startswith("lsp_") for key in metadata)
    )


def _without_lsp_edges(extraction: dict) -> dict:
    clean = dict(extraction)
    for edge_key in ("edges", "links"):
        if edge_key not in extraction:
            continue
        edges = []
        for edge in extraction.get(edge_key, []):
            stripped = _without_lsp_edge_data(edge)
            if stripped is not None:
                edges.append(stripped)
        clean[edge_key] = edges
    if "enrichments" in extraction:
        clean["enrichments"] = [
            metadata for metadata in extraction.get("enrichments", [])
            if not _is_lsp_enrichment(metadata)
        ]
    return clean


def apply_lsp_enrichment(
    extraction: dict,
    *,
    root: Path,
    graphify_out: Path,
    source_files: Iterable[str | Path] | None = None,
    evict_sources: set[str] | None = None,
) -> tuple[dict, LspEnrichmentSummary]:
    """Run configured LSP hook chains and merge produced graph fragments.

    If the repository has no enabled ``lsp`` config, this is a no-op except for
    removing internal ``unresolved_calls`` from the graph payload.
    """
    hook_state = load_hook_state(root)
    if not hook_state.lsp_enabled:
        return without_unresolved_calls(_without_lsp_edges(extraction)), LspEnrichmentSummary(enabled=False)
    config = hook_state.config

    working = _without_lsp_edges(extraction)
    if evict_sources is not None:
        working = preserve_unresolved_calls(
            working,
            graphify_out=graphify_out,
            evict_sources=evict_sources,
        )

    unresolved_path, languages = write_lsp_exchange(
        graphify_out,
        working,
        root=root,
        source_files=source_files,
    )
    enrichment_dir = graphify_out / ENRICHMENT_DIR / LSP_ENRICHMENT_SUBDIR
    if enrichment_dir.exists():
        for stale in enrichment_dir.glob("*.json"):
            stale.unlink()
    lsp_config = config.get("lsp", {}) if isinstance(config.get("lsp"), dict) else {}
    source_files_list = list(source_files or [])
    cache_enabled = (
        lsp_config.get("cache", True) is not False
        and evict_sources is None
        and bool(source_files_list)
    )
    cache_key = (
        lsp_cache_key(
            root=root,
            source_files=source_files_list,
            unresolved_calls_path=unresolved_path,
            config=config,
        )
        if cache_enabled
        else None
    )
    cache_hit = bool(cache_key and restore_lsp_cache(graphify_out, cache_key, enrichment_dir))
    if cache_hit:
        ran_hooks: list[str] = []
    else:
        ran_hooks = run_lsp_hooks(
            root=root,
            graphify_out=graphify_out,
            languages=languages,
            unresolved_calls_path=unresolved_path,
            enrichment_dir=enrichment_dir,
            state=hook_state,
        )
        if cache_key:
            save_lsp_cache(graphify_out, cache_key, enrichment_dir)

    merged = without_unresolved_calls(working)
    merged_files = merged_nodes = merged_edges = 0
    if enrichment_dir.exists():
        chunks = load_enrichments([enrichment_dir])
        if chunks:
            merged = merge_enrichments(merged, chunks)
            merged_files = len(list(enrichment_dir.glob("*.json")))
            merged_nodes = sum(len(chunk.get("nodes", [])) for chunk in chunks)
            merged_edges = sum(len(chunk.get("edges", [])) for chunk in chunks)

    return merged, LspEnrichmentSummary(
        enabled=True,
        unresolved_path=unresolved_path,
        unresolved_count=len(working.get("unresolved_calls", [])),
        languages=tuple(sorted(languages)),
        ran_hooks=tuple(ran_hooks),
        merged_files=merged_files,
        merged_nodes=merged_nodes,
        merged_edges=merged_edges,
        cache_hit=cache_hit,
        cache_enabled=cache_enabled,
    )
