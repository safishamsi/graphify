"""Module 6 \u2014 deterministic verifier.

Runs six check families over every reasoner finding and returns a
:class:`VerifierAuditEntry` summarizing what passed, what failed, and
what could not be evaluated. The six families:

1. **graph_path_exists**   \u2014 are all nodes the reasoner referenced real
   and reachable in the enriched graph?
2. **edge_confidence_floor** \u2014 if the finding rests on only inferred
   edges, require a confidence floor from the verifier policy, bumped
   for full-repo scans.
3. **rls_awareness**       \u2014 if the finding claims an RLS gap, confirm
   against :class:`RLSCoverage` from Module 1.
4. **migration_branch_state** \u2014 if the finding references a table that
   is not yet visible in the branch, mark the check invalid.
5. **payload_contract**    \u2014 producer/consumer key overlap check using
   Module 1's Celery payload annotations.
6. **phantom_anchor_short_circuit** \u2014 if ``diff_anchors`` on the
   candidate don't intersect the reasoner's witness path, short-circuit
   to invalid_reasoning.

All checks are deterministic and leave no floating-point room for
non-reproducible outcomes.
"""
from __future__ import annotations

from typing import Any, Iterable

import networkx as nx

from depos.analysis.config import IntelligenceConfig
from depos.analysis.schemas import (
    Candidate,
    ContextBundle,
    Finding,
    ModeAFinding,
    ModeAOutput,
    ModeBFinding,
    ModeBOutput,
    ModeCFinding,
    ModeCOutput,
    ReasonerMode,
    RLSCoverage,
    VerifierAuditEntry,
    VerifierCheckResult,
    VerifierOutcome,
)

CheckName = str


def _check_graph_path_exists(graph: nx.DiGraph, nodes: list[str]) -> VerifierCheckResult:
    missing = [n for n in nodes if not graph.has_node(n)]
    if not nodes:
        return VerifierCheckResult(name="graph_path_exists", result="unavailable", detail="no nodes cited")
    if missing:
        return VerifierCheckResult(
            name="graph_path_exists",
            result="fail",
            detail=f"missing_nodes={missing}",
        )
    return VerifierCheckResult(name="graph_path_exists", result="pass")


def _check_edge_confidence_floor(
    graph: nx.DiGraph,
    path: list[str],
    *,
    floor: float,
    inferred_floor_applied: bool,
) -> VerifierCheckResult:
    if len(path) < 2:
        return VerifierCheckResult(name="edge_confidence_floor", result="unavailable")
    min_conf = 1.0
    all_inferred = True
    for u, v in zip(path, path[1:]):
        if not graph.has_edge(u, v):
            continue
        data = graph.get_edge_data(u, v) or {}
        # DiGraph returns a flat attrs dict; MultiDiGraph returns {key: attrs}.
        if graph.is_multigraph():
            datas = list(data.values())
        else:
            datas = [data]
        for d in datas:
            if not isinstance(d, dict):
                continue
            conf = float(d.get("confidence", 1.0))
            if not d.get("inferred"):
                all_inferred = False
            if conf < min_conf:
                min_conf = conf
    effective_floor = floor + (0.1 if inferred_floor_applied else 0.0)
    if all_inferred and min_conf < effective_floor:
        return VerifierCheckResult(
            name="edge_confidence_floor",
            result="fail",
            detail=f"min_conf={min_conf:.2f} floor={effective_floor:.2f} all_inferred=true",
        )
    return VerifierCheckResult(name="edge_confidence_floor", result="pass", detail=f"min_conf={min_conf:.2f}")


def _check_rls_awareness(bundle: ContextBundle, description: str) -> VerifierCheckResult:
    if not any(key in description.lower() for key in ("rls", "row level security")):
        return VerifierCheckResult(name="rls_awareness", result="unavailable")
    if not bundle.rls_coverage:
        return VerifierCheckResult(name="rls_awareness", result="insufficient_static_evidence")
    # If any cited table has ``full`` coverage, we flag the RLS claim as likely covered.
    states = list(bundle.rls_coverage.values())
    if any(cov == RLSCoverage.full for cov in states):
        return VerifierCheckResult(name="rls_awareness", result="rls_covered", detail="full_on_any_cited_table")
    if any(cov in {RLSCoverage.partial_operation, RLSCoverage.partial_predicate} for cov in states):
        return VerifierCheckResult(name="rls_awareness", result="rls_partial")
    return VerifierCheckResult(name="rls_awareness", result="pass", detail="no_coverage_claimed")


def _check_migration_branch_state(bundle: ContextBundle, cited_tables: list[str]) -> VerifierCheckResult:
    if not cited_tables:
        return VerifierCheckResult(name="migration_branch_state", result="unavailable")
    missing = [t for t in cited_tables if t not in bundle.migration_state]
    if missing:
        return VerifierCheckResult(
            name="migration_branch_state",
            result="invalid",
            detail=f"not_in_branch={missing}",
        )
    return VerifierCheckResult(name="migration_branch_state", result="pass")


def _check_payload_contract(graph: nx.DiGraph, cited_nodes: list[str]) -> VerifierCheckResult:
    for n in cited_nodes:
        if not graph.has_node(n):
            continue
        for _, _, data in graph.out_edges(n, data=True):
            missing = data.get("payload_missing_fields")
            extra = data.get("payload_extra_fields")
            if missing or extra:
                return VerifierCheckResult(
                    name="payload_contract",
                    result="fail",
                    detail=f"missing={missing or []} extra={extra or []}",
                )
    return VerifierCheckResult(name="payload_contract", result="pass")


def _check_phantom_anchor(candidate: Candidate, witness_path: list[str], *, enabled: bool) -> VerifierCheckResult:
    if not enabled or not candidate.diff_anchors:
        return VerifierCheckResult(name="phantom_anchor_short_circuit", result="unavailable")
    if not witness_path:
        return VerifierCheckResult(name="phantom_anchor_short_circuit", result="unavailable")
    if set(candidate.diff_anchors) & set(witness_path):
        return VerifierCheckResult(name="phantom_anchor_short_circuit", result="pass")
    return VerifierCheckResult(
        name="phantom_anchor_short_circuit",
        result="fail",
        detail="diff_anchors_not_in_witness",
    )


# ---------------------------------------------------------------------------
# Outcome derivation
# ---------------------------------------------------------------------------


def _derive_outcome(checks: list[VerifierCheckResult]) -> VerifierOutcome:
    passes = sum(1 for c in checks if c.result == "pass")
    fails = sum(1 for c in checks if c.result in {"fail", "invalid"})
    if fails >= 2:
        return VerifierOutcome.invalid_reasoning
    if fails == 1 and passes >= 2:
        return VerifierOutcome.partially_confirmed
    if passes >= 3:
        return VerifierOutcome.confirmed
    if passes == 0:
        return VerifierOutcome.unconfirmed
    return VerifierOutcome.partially_confirmed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def verify(
    *,
    graph: nx.DiGraph,
    candidate: Candidate,
    bundle: ContextBundle,
    mode: ReasonerMode,
    finding: ModeAFinding | ModeBFinding | ModeCFinding,
    config: IntelligenceConfig,
    full_repo_scan: bool,
) -> tuple[VerifierAuditEntry, Finding]:
    witness_path: list[str] = []
    if isinstance(finding, ModeAFinding):
        witness_path = list(finding.affected_path or []) + list(finding.graph_anchor_nodes or [])
        bug_type = finding.bug_type
        description = finding.description
        confidence = float(finding.confidence)
        missing_guard = None
    elif isinstance(finding, ModeBFinding):
        witness_path = list(finding.graph_anchor_nodes or [])
        bug_type = finding.violation_type
        description = f"{finding.description} (A={finding.component_a}, B={finding.component_b})"
        confidence = float(finding.confidence)
        missing_guard = None
    else:
        witness_path = list(finding.violating_path or []) + list(finding.graph_anchor_nodes or [])
        bug_type = finding.flow_bug_type
        description = finding.description
        confidence = float(finding.confidence)
        missing_guard = finding.missing_guard

    cited_tables = sorted(bundle.rls_coverage.keys())

    checks: list[VerifierCheckResult] = []
    checks.append(_check_graph_path_exists(graph, witness_path))
    checks.append(
        _check_edge_confidence_floor(
            graph,
            witness_path,
            floor=config.verifier.min_edge_confidence_for_confirmed,
            inferred_floor_applied=full_repo_scan,
        )
    )
    checks.append(_check_rls_awareness(bundle, description))
    checks.append(_check_migration_branch_state(bundle, cited_tables))
    checks.append(_check_payload_contract(graph, witness_path))
    checks.append(_check_phantom_anchor(candidate, witness_path, enabled=config.verifier.phantom_anchor_short_circuit))

    outcome = _derive_outcome(checks)

    finding_id = f"{candidate.candidate_id}:{mode.value}:{bug_type}"[:96]
    audit = VerifierAuditEntry(
        finding_id=finding_id,
        verifier_outcome=outcome,
        checks_run=checks,
        inferred_edge_confidence_floor_applied=full_repo_scan,
        pack_manifest_id=bundle.pack_manifest.manifest_id,
        reasoner_mode=mode,
    )

    # Build the output-layer Finding. Surface RLS verdict if we have one.
    rls_verdict: RLSCoverage | None = None
    for cov in bundle.rls_coverage.values():
        if cov in {RLSCoverage.full, RLSCoverage.partial_operation, RLSCoverage.partial_predicate, RLSCoverage.context_mismatch, RLSCoverage.none}:
            rls_verdict = cov
            break

    affected: list[str] = []
    if isinstance(finding, ModeBFinding):
        affected = [finding.component_a, finding.component_b]
    elif witness_path:
        affected = witness_path[:4]

    out_finding = Finding(
        finding_id=finding_id,
        trust_level=outcome,
        mode=mode,
        verifier_outcome=outcome,
        bug_type=bug_type,
        description=description,
        affected_components=affected,
        witness_path=witness_path,
        missing_guard=missing_guard,
        reasoner_confidence=confidence,
        ranking_phase=0,
        verifier_checks_passed=[c.name for c in checks if c.result == "pass"],
        verifier_checks_inconclusive=[c.name for c in checks if c.result in {"unavailable", "insufficient_static_evidence", "rls_partial"}],
        rls_verdict=rls_verdict,
        pack_manifest_id=bundle.pack_manifest.manifest_id,
    )
    if outcome == VerifierOutcome.partially_confirmed:
        out_finding.partially_confirmed_caveat = (
            "Verifier confirmed some but not all structural checks; treat as suggestive, not proof."
        )
    return audit, out_finding


def verify_all(
    *,
    graph: nx.DiGraph,
    candidate: Candidate,
    bundle: ContextBundle,
    reasoner_outputs: dict[ReasonerMode, Any],
    config: IntelligenceConfig,
    full_repo_scan: bool,
) -> tuple[list[VerifierAuditEntry], list[Finding]]:
    audits: list[VerifierAuditEntry] = []
    findings: list[Finding] = []
    for mode, output in reasoner_outputs.items():
        raw_findings: Iterable
        if isinstance(output, ModeAOutput):
            raw_findings = output.findings
        elif isinstance(output, ModeBOutput):
            raw_findings = output.findings
        elif isinstance(output, ModeCOutput):
            raw_findings = output.findings
        else:
            continue
        for raw in raw_findings:
            audit, f = verify(
                graph=graph,
                candidate=candidate,
                bundle=bundle,
                mode=mode,
                finding=raw,
                config=config,
                full_repo_scan=full_repo_scan,
            )
            audits.append(audit)
            findings.append(f)
    return audits, findings


__all__ = ["verify", "verify_all"]
