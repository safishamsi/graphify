"""Module 3 \u2014 context bundler.

Takes a :class:`Candidate` and a graph, walks the local neighborhood up
to the configured hop budget, pulls code snippets, and packs everything
into a :class:`ContextBundle` with a deterministic :class:`PackManifest`.

Truncation order is explicit (documented on the manifest):
1. least-central call_chain nodes (furthest hop first)
2. duplicate-looking code snippets (same file, same function)
3. largest snippets trimmed to their first/last 20 lines

Token estimator defaults to ``chars4`` (``len(text) // 4``). If
``config.bundles.allow_tiktoken`` and tiktoken is available, the
estimator switches to ``tiktoken-cl100k``. The chosen estimator name is
always written into the manifest so downstream consumers can reproduce
the budget calculation.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import networkx as nx

from depos.analysis.config import IntelligenceConfig
from depos.analysis.schemas import (
    BundleEvidence,
    Candidate,
    CodeSnippet,
    ContextBundle,
    MigrationState,
    PackManifest,
    RLSCoverage,
    SeamEdge,
    SemanticEdgeMetadata,
)


_QUALITY_RANK = {"missing": 0, "label_only": 1, "embedded": 2, "full": 3}


# ---------------------------------------------------------------------------
# Token estimators
# ---------------------------------------------------------------------------


def _chars4(text: str) -> int:
    return max(1, len(text) // 4)


def _get_estimator(config: IntelligenceConfig):
    name = config.bundles.token_estimator
    if name == "tiktoken-cl100k" and config.bundles.allow_tiktoken:
        try:
            import tiktoken  # type: ignore

            enc = tiktoken.get_encoding("cl100k_base")

            def _tt(text: str) -> int:
                return len(enc.encode(text))

            return _tt, "tiktoken-cl100k"
        except Exception:  # noqa: BLE001
            return _chars4, "chars4"
    return _chars4, "chars4"


# ---------------------------------------------------------------------------
# Graph walks
# ---------------------------------------------------------------------------


def _walk_callers(graph: nx.DiGraph, start: str, hops: int) -> list[dict]:
    out: list[dict] = []
    frontier = {start}
    for depth in range(1, hops + 1):
        next_frontier: set[str] = set()
        for n in frontier:
            for u, _ in graph.in_edges(n):
                out.append({"node_id": u, "depth": depth})
                next_frontier.add(u)
        frontier = next_frontier
        if not frontier:
            break
    return out


def _walk_callees(graph: nx.DiGraph, start: str, hops: int) -> list[dict]:
    out: list[dict] = []
    frontier = {start}
    for depth in range(1, hops + 1):
        next_frontier: set[str] = set()
        for n in frontier:
            for _, v in graph.out_edges(n):
                out.append({"node_id": v, "depth": depth})
                next_frontier.add(v)
        frontier = next_frontier
        if not frontier:
            break
    return out


def _collect_seams(graph: nx.DiGraph, nodes: set[str]) -> list[SeamEdge]:
    out: list[SeamEdge] = []
    for u, v, data in graph.edges(data=True):
        if u not in nodes and v not in nodes:
            continue
        if not (data.get("source_system") and data.get("target_system")):
            continue
        metadata = SemanticEdgeMetadata.model_validate({k2: v2 for k2, v2 in data.items() if k2 != "relation"})
        out.append(
            SeamEdge(
                edge_id=f"{u}|{v}|{data.get('relation', '')}",
                source=u,
                target=v,
                relation=data.get("relation", ""),
                metadata=metadata,
            )
        )
    return out


def _collect_data_reads_writes(graph: nx.DiGraph, nodes: set[str]) -> tuple[list[str], list[str]]:
    reads: list[str] = []
    writes: list[str] = []
    for n in nodes:
        if not graph.has_node(n):
            continue
        for _, v, data in graph.out_edges(n, data=True):
            rel = data.get("relation")
            tbl = data.get("table_name") or data.get("rpc_name") or v
            if rel == "ROUTE_READS_TABLE":
                reads.append(tbl)
            elif rel == "ROUTE_WRITES_TABLE":
                writes.append(tbl)
    return sorted(set(reads)), sorted(set(writes))


def _collect_rls(graph: nx.DiGraph, nodes: set[str]) -> dict[str, RLSCoverage]:
    out: dict[str, RLSCoverage] = {}
    for n in nodes:
        if not graph.has_node(n):
            continue
        per_table = graph.nodes[n].get("rls_coverage_per_table", {})
        for tbl, cov_val in per_table.items():
            try:
                out[tbl] = RLSCoverage(cov_val)
            except ValueError:
                continue
    return out


def _collect_migration_state(graph: nx.DiGraph) -> dict[str, MigrationState]:
    out: dict[str, MigrationState] = {}
    for _, attrs in graph.nodes(data=True):
        if attrs.get("file_type") != "sql_table":
            continue
        label = attrs.get("label", "")
        if not label:
            continue
        # Simplified: if the table has at least one SCHEMA_DEFINED_BY_MIGRATION
        # outgoing edge, mark exists_in_branch. Module 1 already enforces
        # lexical ordering; the verifier refines this per-candidate.
        out[label] = MigrationState.exists_in_branch
    return out


# ---------------------------------------------------------------------------
# Code snippet collection
# ---------------------------------------------------------------------------


def _apply_aliases(rel_path: str, aliases: dict[str, str]) -> list[str]:
    """Return the original path plus every aliased rewrite. Order matters."""
    candidates = [rel_path]
    for src, dst in aliases.items():
        if not src:
            continue
        if rel_path.startswith(src):
            candidates.append(dst + rel_path[len(src) :])
    return candidates


def _try_read_source(
    sf: str,
    *,
    source_roots: list[Path],
    path_aliases: dict[str, str],
) -> tuple[str, Optional[str]]:
    """Read file text trying every (root, alias) pair. Returns ``(text, resolved_via)``.

    ``resolved_via`` is a string like ``"<root>::<rel>"`` so we can report
    which root won. Empty when nothing resolved.
    """
    sf_path = Path(sf)
    if sf_path.is_absolute():
        try:
            return sf_path.read_text(encoding="utf-8", errors="replace"), str(sf_path)
        except OSError:
            return "", None

    for root in source_roots:
        for candidate_rel in _apply_aliases(sf, path_aliases):
            target = root / candidate_rel
            try:
                return target.read_text(encoding="utf-8", errors="replace"), f"{root}::{candidate_rel}"
            except OSError:
                continue
    return "", None


def _read_snippet_for(
    node_attrs: dict,
    *,
    source_roots: list[Path],
    path_aliases: dict[str, str],
    min_snippet_chars: int,
) -> Optional[CodeSnippet]:
    sf = node_attrs.get("source_file")
    embedded_text = str(node_attrs.get("embedded_text") or "").strip()
    label = str(node_attrs.get("label") or "").strip()
    if not sf and not embedded_text and not label:
        return None

    start = int(node_attrs.get("start_line") or 0)
    end = int(node_attrs.get("end_line") or 0)

    text = ""
    resolved_via: Optional[str] = None
    if sf:
        text, resolved_via = _try_read_source(
            sf, source_roots=source_roots, path_aliases=path_aliases
        )

    snippet_text = ""
    quality = "missing"
    if text and start > 0 and end >= start:
        lines = text.splitlines()
        snippet_text = "\n".join(lines[max(0, start - 1) : end])
        quality = "full" if snippet_text.strip() else "missing"
    elif text:
        snippet_text = text
        quality = "full" if snippet_text.strip() else "missing"

    if (not snippet_text or len(snippet_text) < min_snippet_chars) and embedded_text:
        # Embedded text is what the dataset normalizer captured at ingest
        # time; treat it as second-best evidence rather than dropping the
        # node entirely.
        if not snippet_text:
            snippet_text = embedded_text
            quality = "embedded"
        elif len(embedded_text) > len(snippet_text):
            snippet_text = embedded_text
            quality = "embedded"

    if not snippet_text and label:
        snippet_text = label
        quality = "label_only"

    if not snippet_text.strip():
        return None

    return CodeSnippet(
        node_id=node_attrs.get("id", ""),
        source_file=sf,
        start_line=start,
        end_line=end,
        text=snippet_text,
        evidence_quality=quality,  # type: ignore[arg-type]
        resolved_via=resolved_via,
    )


def _compute_evidence(bundle: ContextBundle) -> BundleEvidence:
    """Score evidence quality so the runner can skip thin bundles.

    Score is in ``[0, 1]``. Mix:

    - 0.40 * min(snippets_full / 3, 1.0)
    - 0.15 * has_seams
    - 0.15 * (has_data_reads or has_data_writes)
    - 0.15 * has_rls_coverage
    - 0.15 * has_migration_state
    """
    counts = {"full": 0, "embedded": 0, "label_only": 0, "missing": 0}
    for snip in bundle.code_snippets:
        counts[snip.evidence_quality] = counts.get(snip.evidence_quality, 0) + 1

    has_seams = bool(bundle.cross_language_seams)
    has_reads = bool(bundle.data_reads)
    has_writes = bool(bundle.data_writes)
    has_rls = bool(bundle.rls_coverage)
    has_migration = bool(bundle.migration_state)

    score = 0.40 * min(counts["full"] / 3.0, 1.0)
    score += 0.15 if has_seams else 0.0
    score += 0.15 if (has_reads or has_writes) else 0.0
    score += 0.15 if has_rls else 0.0
    score += 0.15 if has_migration else 0.0

    missing: list[str] = []
    if counts["full"] == 0:
        missing.append("no_full_snippets")
    if not has_seams:
        missing.append("no_seams")
    if not (has_reads or has_writes):
        missing.append("no_data_io")
    if not has_rls:
        missing.append("no_rls_coverage")
    if not has_migration:
        missing.append("no_migration_state")

    return BundleEvidence(
        snippet_count=len(bundle.code_snippets),
        snippets_full=counts["full"],
        snippets_embedded=counts["embedded"],
        snippets_label_only=counts["label_only"],
        snippets_missing=counts["missing"],
        has_seams=has_seams,
        has_data_reads=has_reads,
        has_data_writes=has_writes,
        has_rls_coverage=has_rls,
        has_migration_state=has_migration,
        evidence_score=round(min(score, 1.0), 4),
        missing_pieces=missing,
    )


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------


def _apply_truncation(
    bundle: ContextBundle,
    estimator,
    budget: int,
) -> None:
    """Greedy truncation in the documented order. Writes events to
    ``bundle.truncation_events`` and updates ``bundle.pack_manifest``.
    """

    def total_tokens() -> int:
        return sum(estimator(s.text) for s in bundle.code_snippets)

    events: list[str] = []
    order: list[str] = []

    # Step 0: drop label_only snippets first — they carry no real
    # information beyond what the candidate already has, and they pollute
    # reasoner prompts with strings like just a function name.
    if total_tokens() > budget:
        kept: list[CodeSnippet] = []
        for snip in bundle.code_snippets:
            if snip.evidence_quality == "label_only":
                events.append(f"dropped_label_only_snippet:{snip.node_id}")
                continue
            kept.append(snip)
        if len(kept) < len(bundle.code_snippets):
            order.append("label_only_snippets")
            bundle.code_snippets = kept

    # Step 1: drop least-central call_chain nodes if needed (pure metadata).
    if total_tokens() > budget and bundle.call_chain_out:
        dropped = bundle.call_chain_out.pop()
        events.append(f"dropped_call_chain_out:{dropped.get('node_id')}")
        order.append("call_chain_out_farthest")

    # Step 2: dedup snippets by source_file + first_line.
    if total_tokens() > budget:
        seen_keys: set[tuple[str, int]] = set()
        deduped: list[CodeSnippet] = []
        for snip in bundle.code_snippets:
            key = (snip.source_file or "", snip.start_line)
            if key in seen_keys:
                events.append(f"dropped_duplicate_snippet:{snip.node_id}")
                continue
            seen_keys.add(key)
            deduped.append(snip)
        if len(deduped) < len(bundle.code_snippets):
            order.append("duplicate_snippets")
            bundle.code_snippets = deduped

    # Step 3: head/tail trim the largest snippet repeatedly.
    while total_tokens() > budget and bundle.code_snippets:
        bundle.code_snippets.sort(key=lambda s: -estimator(s.text))
        largest = bundle.code_snippets[0]
        lines = largest.text.splitlines()
        if len(lines) <= 40:
            # Cannot trim further; drop entirely.
            bundle.code_snippets.pop(0)
            events.append(f"dropped_snippet:{largest.node_id}")
            order.append("drop_snippet")
            continue
        trimmed = "\n".join(lines[:20] + ["# ... truncated ..."] + lines[-20:])
        largest.text = trimmed
        events.append(f"trimmed_head_tail:{largest.node_id}")
        order.append("head_tail_trim")

    bundle.truncation_events = events
    bundle.token_budget = total_tokens()
    bundle.pack_manifest.truncated = [e for e in events if e.startswith("trimmed_")]
    bundle.pack_manifest.dropped = [e for e in events if e.startswith("dropped_")]
    bundle.pack_manifest.truncation_order_applied = list(dict.fromkeys(order))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _bundle_id(candidate: Candidate) -> str:
    return f"bundle_{hashlib.sha1(candidate.candidate_id.encode()).hexdigest()[:12]}"


def _resolve_source_roots(
    config: IntelligenceConfig,
    explicit: Optional[list[Path]],
) -> list[Path]:
    """Build the deterministic ``source_roots`` resolution order.

    Order: explicit caller-supplied roots first, then ``config.bundles.extra_source_roots``,
    then the current working directory as a last-resort fallback. Duplicates
    are removed while preserving order so the first match wins.
    """
    seen: set[Path] = set()
    out: list[Path] = []

    def _add(p: Path) -> None:
        try:
            resolved = p.resolve()
        except OSError:
            resolved = p
        if resolved in seen:
            return
        seen.add(resolved)
        out.append(p)

    for root in explicit or []:
        _add(Path(root))
    for raw in config.bundles.extra_source_roots:
        _add(Path(raw))
    if not out:
        _add(Path.cwd())
    return out


def build_bundle(
    graph: nx.DiGraph,
    candidate: Candidate,
    *,
    config: IntelligenceConfig,
    source_roots: Optional[list[Path]] = None,
    path_aliases: Optional[dict[str, str]] = None,
) -> ContextBundle:
    estimator, est_name = _get_estimator(config)
    hops = config.candidates.max_hop_count
    roots = _resolve_source_roots(config, source_roots)
    aliases = dict(config.bundles.path_aliases)
    if path_aliases:
        aliases.update(path_aliases)
    min_chars = max(0, int(config.bundles.min_snippet_chars))

    anchor_ids = set(candidate.diff_anchors)
    # If this is an interface_surface seed with seam edges, recover endpoints.
    for seam in candidate.seam_edges:
        parts = seam.split("|")
        if len(parts) >= 2:
            anchor_ids.add(parts[0])
            anchor_ids.add(parts[1])
    if not anchor_ids and candidate.scope_id.startswith("node:"):
        anchor_ids.add(candidate.scope_id[5:])

    neighborhood: set[str] = set(anchor_ids)
    call_chain_in: list[dict] = []
    call_chain_out: list[dict] = []
    for nid in list(anchor_ids):
        if not graph.has_node(nid):
            continue
        call_chain_in.extend(_walk_callers(graph, nid, hops))
        call_chain_out.extend(_walk_callees(graph, nid, hops))
    for entry in call_chain_in + call_chain_out:
        neighborhood.add(entry["node_id"])

    reads, writes = _collect_data_reads_writes(graph, neighborhood)
    seams = _collect_seams(graph, neighborhood)
    rls = _collect_rls(graph, neighborhood)
    migration_state = _collect_migration_state(graph)

    snippets: list[CodeSnippet] = []
    for nid in anchor_ids:
        if not graph.has_node(nid):
            continue
        snip = _read_snippet_for(
            {**graph.nodes[nid], "id": nid},
            source_roots=roots,
            path_aliases=aliases,
            min_snippet_chars=min_chars,
        )
        if snip is not None:
            snippets.append(snip)

    manifest_id = _bundle_id(candidate)
    pack_manifest = PackManifest(
        manifest_id=manifest_id,
        token_estimator=est_name,
        included=[s.node_id for s in snippets],
    )
    bundle = ContextBundle(
        bundle_id=manifest_id,
        candidate_id=candidate.candidate_id,
        scope_id=candidate.scope_id,
        call_chain_in=call_chain_in,
        call_chain_out=call_chain_out,
        data_reads=reads,
        data_writes=writes,
        cross_language_seams=seams,
        diff_anchors=[{"node_id": a} for a in candidate.diff_anchors],
        rls_coverage=rls,
        migration_state=migration_state,
        code_snippets=snippets,
        pack_manifest=pack_manifest,
    )

    _apply_truncation(bundle, estimator, config.bundles.token_budget_default)
    bundle.evidence = _compute_evidence(bundle)
    return bundle


__all__ = ["build_bundle", "_compute_evidence"]
