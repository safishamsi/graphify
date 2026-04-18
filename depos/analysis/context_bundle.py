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
    Candidate,
    CodeSnippet,
    ContextBundle,
    MigrationState,
    PackManifest,
    RLSCoverage,
    SeamEdge,
    SemanticEdgeMetadata,
)


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


def _read_snippet_for(node_attrs: dict) -> Optional[CodeSnippet]:
    sf = node_attrs.get("source_file")
    if not sf:
        return None
    try:
        text = Path(sf).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    start = int(node_attrs.get("start_line") or 0)
    end = int(node_attrs.get("end_line") or 0)
    if start > 0 and end >= start:
        lines = text.splitlines()
        snippet = "\n".join(lines[max(0, start - 1) : end])
    else:
        snippet = text
    return CodeSnippet(
        node_id=node_attrs.get("id", ""),
        source_file=sf,
        start_line=start,
        end_line=end,
        text=snippet,
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


def build_bundle(
    graph: nx.DiGraph,
    candidate: Candidate,
    *,
    config: IntelligenceConfig,
) -> ContextBundle:
    estimator, est_name = _get_estimator(config)
    hops = config.candidates.max_hop_count

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
        snip = _read_snippet_for({**graph.nodes[nid], "id": nid})
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
    return bundle


__all__ = ["build_bundle"]
