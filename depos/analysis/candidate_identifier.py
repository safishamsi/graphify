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
from depos.graph_relations import CONSUMES_PAYLOAD
from depos.graph_relations import HTTP_CALLS_ROUTE
from depos.graph_relations import PRODUCES_PAYLOAD
from depos.graph_relations import TASK_CONSUMES
from depos.graph_relations import TASK_ENQUEUES
from depos.analysis.schemas import (
    AnalysisMode,
    Candidate,
    ChangeManifest,
    ChangeManifestEntry,
    SeedType,
)

_QUEUE_RELATIONS = {TASK_ENQUEUES, TASK_CONSUMES, PRODUCES_PAYLOAD, CONSUMES_PAYLOAD}
_AI_SEED_KEYWORDS = (
    "auth",
    "guard",
    "permission",
    "policy",
    "rls",
    "session",
    "token",
    "admin",
    "queue",
    "task",
    "webhook",
    "callback",
    "delete",
    "update",
)
_NOISY_AST_KINDS = {
    "identifier",
    "string",
    "string_fragment",
    "dotted_name",
    "argument_list",
    "parameters",
    "formal_parameters",
    "import_clause",
    "named_imports",
    "pair",
}


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
        matched = list(by_path.get(key, []))
        if not matched:
            suffix = f"/{key}"
            for source_path, node_ids in by_path.items():
                if source_path.endswith(suffix):
                    matched.extend(node_ids)
        entry.node_ids = list(dict.fromkeys(entry.node_ids + matched))
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
        if not entry.node_ids and entry.path:
            scope_id = f"file:{entry.path}"
            out.append(
                Candidate(
                    candidate_id=_candidate_id(scope_id, SeedType.diff_anchor, entry.path),
                    scope_id=scope_id,
                    seed_type=SeedType.diff_anchor,
                    priority_score=0.88 + (0.05 if entry.migration_change else 0.0),
                    analysis_mode=mode,
                    extra={
                        "path": entry.path,
                        "migration_change": entry.migration_change,
                        "file_only": True,
                        "removed_entity_references": 1,
                    },
                )
            )
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


def _node_text(attrs: dict[str, Any]) -> str:
    parts = [
        str(attrs.get("label") or ""),
        str(attrs.get("source_file") or ""),
        str(attrs.get("route_pattern") or ""),
        str(attrs.get("http_method") or ""),
        str(attrs.get("entity_kind") or ""),
    ]
    return " ".join(p for p in parts if p).lower()


def _is_seedable_node(attrs: dict[str, Any]) -> bool:
    if attrs.get("synthetic_entity"):
        return True
    if attrs.get("is_fastapi_route") or attrs.get("http_call_sites"):
        return True
    ast_kind = str(attrs.get("ast_kind") or attrs.get("kind") or "").lower()
    if ast_kind in _NOISY_AST_KINDS:
        return False
    label = str(attrs.get("label") or "").strip()
    if len(label) <= 1:
        return False
    return bool(attrs.get("source_file") or label)


def _is_public_route_node(attrs: dict[str, Any]) -> bool:
    if attrs.get("is_fastapi_route"):
        return True
    source_file = str(attrs.get("source_file") or "").replace("\\", "/").lower()
    if source_file.endswith(("/route.ts", "/route.tsx", "/route.js", "/route.jsx")):
        return True
    return bool(attrs.get("http_method") and attrs.get("route_pattern"))


def _is_auth_boundary_node(attrs: dict[str, Any]) -> bool:
    source_file = str(attrs.get("source_file") or "").replace("\\", "/").lower()
    label = str(attrs.get("label") or "").lower()
    auth_path = any(part in source_file for part in ("/auth/", "/middleware", "auth.py"))
    auth_label = any(token in label for token in ("auth", "jwt", "session", "token"))
    return auth_path or auth_label


def _is_queue_surface_node(graph: nx.DiGraph, node_id: str) -> bool:
    for _, _, data in graph.in_edges(node_id, data=True):
        if data.get("relation") in _QUEUE_RELATIONS:
            return True
    for _, _, data in graph.out_edges(node_id, data=True):
        if data.get("relation") in _QUEUE_RELATIONS:
            return True
    return False


def _surface_candidates_for_node(graph: nx.DiGraph, node_id: str, attrs: dict[str, Any], mode: AnalysisMode) -> list[Candidate]:
    out: list[Candidate] = []
    if not _is_seedable_node(attrs):
        return out
    if _is_public_route_node(attrs):
        method = str(attrs.get("http_method") or "ANY").upper()
        route = str(attrs.get("route_pattern") or node_id)
        scope_id = f"surface:http:{method}:{route}"
        out.append(
            Candidate(
                candidate_id=_candidate_id(scope_id, SeedType.interface_surface, node_id),
                scope_id=scope_id,
                seed_type=SeedType.interface_surface,
                priority_score=0.76,
                language_pair="public->service",
                diff_anchors=[node_id],
                analysis_mode=mode,
                extra={"surface_type": "public_route", "route": route, "method": method},
            )
        )
    if _is_queue_surface_node(graph, node_id):
        scope_id = f"surface:queue:{node_id}"
        out.append(
            Candidate(
                candidate_id=_candidate_id(scope_id, SeedType.interface_surface, node_id),
                scope_id=scope_id,
                seed_type=SeedType.interface_surface,
                priority_score=0.72,
                language_pair="producer->queue",
                diff_anchors=[node_id],
                analysis_mode=mode,
                extra={"surface_type": "queue_task"},
            )
        )
    if _is_auth_boundary_node(attrs):
        # In ``full_repo_scan`` the lexical "auth/jwt/session/token" filter
        # used by ``_is_auth_boundary_node`` matches almost every web
        # backend node and floods the candidate pool. We keep the seed so
        # the surface is still investigated, but drop its priority below
        # graph-anomaly seeds so other detector families can compete.
        scope_id = f"surface:auth:{node_id}"
        auth_priority = 0.42 if mode == AnalysisMode.full_repo_scan else 0.68
        out.append(
            Candidate(
                candidate_id=_candidate_id(scope_id, SeedType.interface_surface, node_id),
                scope_id=scope_id,
                seed_type=SeedType.interface_surface,
                priority_score=auth_priority,
                diff_anchors=[node_id],
                analysis_mode=mode,
                extra={"surface_type": "auth_boundary"},
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
    for node_id, attrs in graph.nodes(data=True):
        for cand in _surface_candidates_for_node(graph, node_id, attrs, mode):
            if cand.scope_id in seen:
                continue
            seen.add(cand.scope_id)
            out.append(cand)
    return out


def _node_has_unresolved_signal(attrs: dict[str, Any]) -> bool:
    if "<<unresolved>>" in str(attrs.get("label") or "").lower():
        return True
    categories = attrs.get("diagnostic_categories") or attrs.get("error_categories") or []
    if any(str(cat).lower() == "unresolved" for cat in categories):
        return True
    for err in attrs.get("errors") or []:
        if not isinstance(err, dict):
            continue
        category = str(err.get("category") or "").lower()
        message = str(err.get("message") or "").lower()
        if "unresolved" in category or "unresolved" in message or "cannot find" in message:
            return True
    return False


def _non_self_degree(graph: nx.DiGraph, node_id: str) -> tuple[int, int]:
    incoming = sum(1 for u, _, _ in graph.in_edges(node_id, data=True) if u != node_id)
    outgoing = sum(1 for _, v, _ in graph.out_edges(node_id, data=True) if v != node_id)
    return incoming, outgoing


def _is_dataset_unresolved_node(attrs: dict[str, Any]) -> bool:
    """Detect dataset nodes whose source text could not be resolved.

    Either the normalizer failed to find any matching ``source_root`` (so
    ``source_resolved_via`` is missing/empty), or the snippet collapsed to a
    label (no ``embedded_text``). These nodes are valuable seeds because they
    represent code we know about structurally but cannot inspect, which is the
    exact condition that produced "0 findings" in the Gemma 4 dataset run.
    """
    resolved = str(attrs.get("source_resolved_via") or "").strip().lower()
    if resolved in {"", "missing", "unresolved"}:
        return True
    if not str(attrs.get("embedded_text") or "").strip():
        return True
    return False


def _graph_anomaly_candidates(graph: nx.DiGraph, mode: AnalysisMode) -> list[Candidate]:
    """Structural anomaly seeds kept conservative but broader than a single
    missing-route-client case.
    """
    # In full_repo_scan the diff is empty, so graph anomalies become the most
    # informative deterministic signal we have. Bump them above the lexical
    # auth_boundary surfaces (0.42 in this mode) but keep them below
    # diff-anchored seeds.
    bump = 0.10 if mode == AnalysisMode.full_repo_scan else 0.0
    out: list[Candidate] = []
    for nid, attrs in graph.nodes(data=True):
        if not _is_seedable_node(attrs):
            continue
        if _is_public_route_node(attrs):
            has_caller = any(
                data.get("relation") == HTTP_CALLS_ROUTE
                for _, _, data in graph.in_edges(nid, data=True)
            )
            if not has_caller:
                scope_id = f"route:unused:{nid}"
                out.append(
                    Candidate(
                        candidate_id=_candidate_id(scope_id, SeedType.graph_anomaly, nid),
                        scope_id=scope_id,
                        seed_type=SeedType.graph_anomaly,
                        priority_score=0.55 + bump,
                        analysis_mode=mode,
                        extra={
                            "anomaly": "fastapi_route_without_client_calls",
                            "route": attrs.get("route_pattern"),
                            "method": attrs.get("http_method"),
                        },
                    )
                )

        if attrs.get("http_call_sites"):
            has_route_match = any(
                data.get("relation") == HTTP_CALLS_ROUTE
                for _, _, data in graph.out_edges(nid, data=True)
            )
            if not has_route_match:
                scope_id = f"http:unmatched:{nid}"
                out.append(
                    Candidate(
                        candidate_id=_candidate_id(scope_id, SeedType.graph_anomaly, nid),
                        scope_id=scope_id,
                        seed_type=SeedType.graph_anomaly,
                        priority_score=0.57 + bump,
                        diff_anchors=[nid],
                        analysis_mode=mode,
                        extra={
                            "anomaly": "unmatched_http_client_call",
                            "urls": [site.get("url_literal") for site in attrs.get("http_call_sites", [])],
                            "unresolved_symbol_count": len(attrs.get("http_call_sites", [])),
                        },
                    )
                )

        incoming, outgoing = _non_self_degree(graph, nid)
        if (_is_public_route_node(attrs) or _is_queue_surface_node(graph, nid)) and incoming == 0 and outgoing == 0:
            scope_id = f"surface:orphan:{nid}"
            out.append(
                Candidate(
                    candidate_id=_candidate_id(scope_id, SeedType.graph_anomaly, nid),
                    scope_id=scope_id,
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.53 + bump,
                    diff_anchors=[nid],
                    analysis_mode=mode,
                    extra={"anomaly": "orphan_interface_surface"},
                )
            )

        if _node_has_unresolved_signal(attrs):
            scope_id = f"node:unresolved:{nid}"
            out.append(
                Candidate(
                    candidate_id=_candidate_id(scope_id, SeedType.graph_anomaly, nid),
                    scope_id=scope_id,
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.59 + bump,
                    diff_anchors=[nid],
                    analysis_mode=mode,
                    extra={"anomaly": "unresolved_symbol", "unresolved_symbol_count": 1},
                )
            )

        # ``dataset_unresolved`` — surface dataset nodes whose source text was
        # never read. These look fine structurally but feed empty snippets to
        # the reasoner, so they are exactly the seeds to flag for the operator.
        if mode == AnalysisMode.full_repo_scan and _is_dataset_unresolved_node(attrs):
            scope_id = f"dataset:unresolved:{nid}"
            out.append(
                Candidate(
                    candidate_id=_candidate_id(scope_id, SeedType.graph_anomaly, nid),
                    scope_id=scope_id,
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.50 + bump,
                    diff_anchors=[nid],
                    analysis_mode=mode,
                    extra={
                        "anomaly": "dataset_unresolved_source",
                        "source_resolved_via": str(attrs.get("source_resolved_via") or ""),
                        "source_file": str(attrs.get("source_file") or ""),
                        "has_embedded_text": bool(str(attrs.get("embedded_text") or "").strip()),
                    },
                )
            )
    return out


def _ai_driven_candidates(graph: nx.DiGraph, config: IntelligenceConfig, mode: AnalysisMode) -> list[Candidate]:
    """Deterministic lexical fallback until a real embedding model lands."""
    if not config.enable_ai_driven_seeds:
        return []
    scored: list[tuple[float, str, dict[str, Any]]] = []
    for nid, attrs in graph.nodes(data=True):
        if not _is_seedable_node(attrs):
            continue
        haystack = _node_text(attrs)
        hits = [kw for kw in _AI_SEED_KEYWORDS if kw in haystack]
        if not hits:
            continue
        score = min(0.74, 0.45 + (0.04 * len(hits)) + (0.08 if attrs.get("synthetic_entity") else 0.0))
        extra = {
            "strategy": "lexical_similarity_fallback",
            "keywords": hits,
            "surface_hint": (
                "public_route" if _is_public_route_node(attrs) else
                "queue_task" if _is_queue_surface_node(graph, nid) else
                "auth_boundary" if _is_auth_boundary_node(attrs) else
                "generic"
            ),
        }
        scored.append((score, nid, extra))
    scored.sort(key=lambda row: (-row[0], row[1]))
    out: list[Candidate] = []
    for score, nid, extra in scored[:10]:
        scope_id = f"ai:{nid}"
        out.append(
            Candidate(
                candidate_id=_candidate_id(scope_id, SeedType.ai_driven, nid),
                scope_id=scope_id,
                seed_type=SeedType.ai_driven,
                priority_score=score,
                diff_anchors=[nid],
                analysis_mode=mode,
                extra=extra,
            )
        )
    return out


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
    from depos.analysis.detectors import run_all

    prioritized, _stats = run_all(graph, manifest, mode, config)

    # Track dropped-from-budget nodes back into the manifest (if diff mode).
    picked_anchors = {a for c in prioritized for a in c.diff_anchors}
    for entry in manifest.entries:
        entry.dropped_from_budget = [n for n in entry.node_ids if n not in picked_anchors]

    return prioritized, manifest


__all__ = ["identify_candidates", "resolve_change_manifest"]
