"""Shared helpers for builtin detectors."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

import networkx as nx

from depos.analysis.schemas import (
    AnalysisMode,
    Candidate,
    Detector,
    DetectorAction,
    DetectorRule,
    SeedType,
    Universe,
)


def simple_spec(
    *,
    name: str,
    universe: Universe,
    verifier_checks: list[str],
    requires_reasoner: bool = False,
    severity: str = "medium",
    applies_when: str = "True",
) -> Detector:
    return Detector(
        name=name,
        version="0.1.0",
        universe=universe,
        applies_when=applies_when,
        tree=[
            DetectorRule(
                if_="True",
                then=DetectorAction(emit="candidate"),
                description=f"Builtin detector {name}",
            )
        ],
        verifier_checks=verifier_checks,
        requires_reasoner=requires_reasoner,
        severity_default=severity,  # type: ignore[arg-type]
    )


def make_candidate(
    *,
    scope_id: str,
    seed_type: SeedType,
    priority_score: float,
    analysis_mode: AnalysisMode,
    diff_anchors: Iterable[str] | None = None,
    seam_edges: Iterable[str] | None = None,
    language_pair: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Candidate:
    import hashlib

    payload = f"{scope_id}|{seed_type.value}|{sorted(diff_anchors or [])}|{sorted(seam_edges or [])}"
    cid = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return Candidate(
        candidate_id=f"cand_{seed_type.value}_{cid}",
        scope_id=scope_id,
        seed_type=seed_type,
        priority_score=priority_score,
        language_pair=language_pair,
        seam_edges=list(seam_edges or []),
        diff_anchors=list(diff_anchors or []),
        analysis_mode=analysis_mode,
        extra=dict(extra or {}),
    )


def iter_nodes_by_kind(graph: nx.DiGraph, kind: str) -> list[tuple[str, dict[str, Any]]]:
    return [
        (node_id, attrs)
        for node_id, attrs in graph.nodes(data=True)
        if str(attrs.get("node_kind") or attrs.get("kind") or "") == kind
    ]


def incoming_by_relation(graph: nx.DiGraph, node_id: str, relation: str | None = None) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for source, _, data in graph.in_edges(node_id, data=True):
        if relation is None or data.get("relation") == relation:
            out.append((source, dict(data)))
    return out


def outgoing_by_relation(graph: nx.DiGraph, node_id: str, relation: str | None = None) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for _, target, data in graph.out_edges(node_id, data=True):
        if relation is None or data.get("relation") == relation:
            out.append((target, dict(data)))
    return out


def package_groups(graph: nx.DiGraph) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    groups: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for node_id, attrs in iter_nodes_by_kind(graph, "package_dep"):
        pkg = str(attrs.get("package_name") or attrs.get("name") or "").strip()
        if pkg:
            groups[pkg].append((node_id, attrs))
    return groups


__all__ = [
    "incoming_by_relation",
    "iter_nodes_by_kind",
    "make_candidate",
    "outgoing_by_relation",
    "package_groups",
    "simple_spec",
]
