"""Module 2 \u2014 candidate identifier.

Responsibilities:

1. Build / consume a :class:`ChangeManifest` from one of three sources
   (in priority order): CPG/graph diff, git diff, or a manual JSON blob.
2. Seed candidates from 4 sources:
   - ``diff_anchor``     \u2014 nodes touching the change manifest
   - ``interface_surface`` \u2014 cross-language seam edges
   - ``graph_anomaly``   \u2014 structural anomalies (e.g. unused edges,
                            orphan nodes, API handlers without callers)
   - ``ai_driven``       \u2014 placeholder for future AI-driven seeds; kept
                            behind a feature flag so ranking always
                            receives the same shape.
3. Prioritize candidates with a deterministic heuristic: diff anchors
   score highest, interface surfaces second, anomalies third. Ties are
   broken lexically by ``candidate_id`` so replays are reproducible.
4. Deduplicate candidates that cover the same
   (scope_id, seam_edge_set, diff_anchors) tuple.

The identifier is pure: it does not mutate the graph. It returns a list
of :class:`Candidate` along with the resolved :class:`ChangeManifest`.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import networkx as nx

from depos.analysis.config import IntelligenceConfig
from depos.analysis.schemas import (
    AnalysisMode,
    Candidate,
    ChangeManifest,
    ChangeManifestEntry,
    SeedType,
)
from depos.enrichment.semantic_edges import HTTP_CALLS_ROUTE


# ---------------------------------------------------------------------------
# Change manifest resolution
# ---------------------------------------------------------------------------

def _resolve_from_cpg_diff(graph: nx.DiGraph) -> Optional[ChangeManifest]:
    """If the graph carries a ``cpg_diff`` in ``graph.graph`` metadata, use it."""
    cpg = graph.graph.get("cpg_diff")
    if not cpg:
        return None
    entries: list[ChangeManifestEntry] = []
    for row in cpg.get("changes", []):
        entries.append(
            ChangeManifestEntry(
                path=row.get("path"),
                node_ids=list(row.get("node_ids", [])),
                high_churn_file=bool(row.get("high_churn_file", False)),
                migration_change=bool(row.get("migration_change", False)),
                file_change=True,
            )
        )
    return ChangeManifest(entries=entries, resolved_via="cpg_diff") if entries else None


def _resolve_from_git_diff(diff_path: Optional[str], repo_root: Optional[Path]) -> Optional[ChangeManifest]:
    """Parse a diff either from an explicit file path or by invoking ``git diff``
    inside ``repo_root``. Returns ``None`` if no diff is available.
    """
    try:
        if diff_path:
            text = Path(diff_path).read_text(encoding="utf-8", errors="replace")
        else:
            if not repo_root:
                return None
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                return None
            text = result.stdout
    except (OSError, subprocess.SubprocessError):
        return None

    paths = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith(("---", "+++"))]
    # Deduplicate while preserving order.
    seen: set[str] = set()
    uniq: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    entries = [
        ChangeManifestEntry(
            path=p,
            node_ids=[],
            high_churn_file=False,
            migration_change=p.startswith("supabase/migrations/") or "/migrations/" in p,
            file_change=True,
        )
        for p in uniq
    ]
    return ChangeManifest(entries=entries, resolved_via="git") if entries else None


def _attach_graph_nodes(graph: nx.DiGraph, manifest: ChangeManifest) -> ChangeManifest:
    """Populate ``node_ids`` for each entry by scanning the graph for nodes
    whose ``source_file`` matches ``entry.path``.
    """
    by_path: dict[str, list[str]] = {}
    for nid, attrs in graph.nodes(data=True):
        sf = attrs.get("source_file")
        if not sf:
            continue
        by_path.setdefault(str(Path(sf).as_posix()), []).append(nid)
    for entry in manifest.entries:
        if not entry.path:
            continue
        key = str(Path(entry.path).as_posix())
        entry.node_ids = list(dict.fromkeys(entry.node_ids + by_path.get(key, [])))
    return manifest


def resolve_change_manifest(
    graph: nx.DiGraph,
    *,
    diff_path: Optional[str] = None,
    manual_manifest: Optional[dict[str, Any]] = None,
    repo_root: Optional[Path] = None,
) -> ChangeManifest:
    """Return a ChangeManifest using priority: CPG > git > manual > empty.

    Emits ``resolved_via`` so downstream modules know how confident to be.
    """
    manifest = _resolve_from_cpg_diff(graph)
    if manifest is None:
        manifest = _resolve_from_git_diff(diff_path, repo_root)
    if manifest is None and manual_manifest is not None:
        entries = [ChangeManifestEntry.model_validate(e) for e in manual_manifest.get("entries", [])]
        manifest = ChangeManifest(entries=entries, resolved_via="manual")
    if manifest is None:
        manifest = ChangeManifest(entries=[], resolved_via="git")
    return _attach_graph_nodes(graph, manifest)


# ---------------------------------------------------------------------------
# Seed generators
# ---------------------------------------------------------------------------


def _candidate_id(scope_id: str, seed_type: SeedType, *extras: str) -> str:
    h = hashlib.sha1(f"{scope_id}|{seed_type.value}|{'|'.join(extras)}".encode("utf-8")).hexdigest()
    return f"cand_{seed_type.value}_{h[:12]}"


def _diff_anchor_candidates(
    graph: nx.DiGraph,
    manifest: ChangeManifest,
    mode: AnalysisMode,
) -> list[Candidate]:
    out: list[Candidate] = []
    for entry in manifest.entries:
        for node_id in entry.node_ids:
            scope_id = f"file:{entry.path}" if entry.path else f"node:{node_id}"
            out.append(
                Candidate(
                    candidate_id=_candidate_id(scope_id, SeedType.diff_anchor, node_id),
                    scope_id=scope_id,
                    seed_type=SeedType.diff_anchor,
                    priority_score=0.9 + (0.05 if entry.migration_change else 0.0),
                    diff_anchors=[node_id],
                    analysis_mode=mode,
                    extra={"path": entry.path, "migration_change": entry.migration_change},
                )
            )
    return out


def _interface_surface_candidates(graph: nx.DiGraph, mode: AnalysisMode) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[str] = set()
    for u, v, data in graph.edges(data=True):
        rel = data.get("relation")
        if not rel:
            continue
        if data.get("source_system") and data.get("target_system"):
            # cross-system seam edge
            lang_pair = f"{data['source_system']}->{data['target_system']}"
            scope_id = f"seam:{u}->{v}:{rel}"
            if scope_id in seen:
                continue
            seen.add(scope_id)
            edge_id = f"{u}|{v}|{rel}"
            out.append(
                Candidate(
                    candidate_id=_candidate_id(scope_id, SeedType.interface_surface, rel),
                    scope_id=scope_id,
                    seed_type=SeedType.interface_surface,
                    priority_score=0.7 + (0.1 if rel == HTTP_CALLS_ROUTE else 0.0),
                    language_pair=lang_pair,
                    seam_edges=[edge_id],
                    analysis_mode=mode,
                    extra={"relation": rel, "inferred": bool(data.get("inferred", False))},
                )
            )
    return out


def _graph_anomaly_candidates(graph: nx.DiGraph, mode: AnalysisMode) -> list[Candidate]:
    """Very conservative anomaly seeds: FastAPI routes with ZERO incoming
    HTTP_CALLS_ROUTE edges. Avoids flooding the ranker with every orphan
    node in the graph.
    """
    out: list[Candidate] = []
    for nid, attrs in graph.nodes(data=True):
        if not attrs.get("is_fastapi_route"):
            continue
        has_caller = any(
            data.get("relation") == HTTP_CALLS_ROUTE
            for _, _, data in graph.in_edges(nid, data=True)
        )
        if has_caller:
            continue
        scope_id = f"route:unused:{nid}"
        out.append(
            Candidate(
                candidate_id=_candidate_id(scope_id, SeedType.graph_anomaly, nid),
                scope_id=scope_id,
                seed_type=SeedType.graph_anomaly,
                priority_score=0.55,
                analysis_mode=mode,
                extra={
                    "anomaly": "fastapi_route_without_client_calls",
                    "route": attrs.get("route_pattern"),
                    "method": attrs.get("http_method"),
                },
            )
        )
    return out


def _ai_driven_candidates(graph: nx.DiGraph, config: IntelligenceConfig, mode: AnalysisMode) -> list[Candidate]:
    """Placeholder: only emits when ``config.enable_ai_driven_seeds`` is set.
    We honor the flag so Module 4's prompt shape never changes between runs.
    """
    if not getattr(config, "enable_ai_driven_seeds", False):
        return []
    return []


# ---------------------------------------------------------------------------
# Deduplication + prioritization
# ---------------------------------------------------------------------------


def _dedup(candidates: Iterable[Candidate]) -> list[Candidate]:
    seen: dict[tuple[str, tuple[str, ...], tuple[str, ...]], Candidate] = {}
    for cand in candidates:
        key = (
            cand.scope_id,
            tuple(sorted(cand.seam_edges)),
            tuple(sorted(cand.diff_anchors)),
        )
        prior = seen.get(key)
        if prior is None or cand.priority_score > prior.priority_score:
            seen[key] = cand
    return list(seen.values())


def _prioritize(candidates: Sequence[Candidate], budget: int) -> list[Candidate]:
    ordered = sorted(
        candidates,
        key=lambda c: (-c.priority_score, c.candidate_id),
    )
    return list(ordered[:budget])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def identify_candidates(
    graph: nx.DiGraph,
    *,
    config: IntelligenceConfig,
    mode: AnalysisMode,
    diff_path: Optional[str] = None,
    manual_manifest: Optional[dict[str, Any]] = None,
    repo_root: Optional[Path] = None,
) -> tuple[list[Candidate], ChangeManifest]:
    manifest = resolve_change_manifest(
        graph,
        diff_path=diff_path,
        manual_manifest=manual_manifest,
        repo_root=repo_root,
    )

    pool: list[Candidate] = []
    pool.extend(_diff_anchor_candidates(graph, manifest, mode))
    pool.extend(_interface_surface_candidates(graph, mode))
    pool.extend(_graph_anomaly_candidates(graph, mode))
    pool.extend(_ai_driven_candidates(graph, config, mode))
    pool = _dedup(pool)

    budget = config.candidates.max_seeds
    prioritized = _prioritize(pool, budget)

    # Track dropped-from-budget nodes back into the manifest (if diff mode).
    picked_anchors = {a for c in prioritized for a in c.diff_anchors}
    for entry in manifest.entries:
        entry.dropped_from_budget = [n for n in entry.node_ids if n not in picked_anchors]

    return prioritized, manifest


__all__ = ["identify_candidates", "resolve_change_manifest"]
