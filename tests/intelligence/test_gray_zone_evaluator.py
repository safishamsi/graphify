from __future__ import annotations

import networkx as nx

from depos.analysis.config import IntelligenceConfig
from depos.analysis.gray_zone_evaluator import evaluate
from depos.analysis.schemas import (
    Finding,
    GrayZoneEntryReason,
    GrayZoneVoteOutcome,
    ReasonerMode,
    RLSCoverage,
    VerifierAuditEntry,
    VerifierCheckResult,
    VerifierOutcome,
)


def _finding(
    *,
    confidence: float = 0.8,
    rls_verdict: RLSCoverage | None = None,
    witness_path: list[str] | None = None,
) -> Finding:
    return Finding(
        finding_id="cand_x:A:test",
        trust_level=VerifierOutcome.unconfirmed,
        mode=ReasonerMode.A,
        verifier_outcome=VerifierOutcome.unconfirmed,
        bug_type="missing_guard",
        description="Potential missing guard on route",
        reasoner_confidence=confidence,
        rls_verdict=rls_verdict,
        witness_path=witness_path or [],
        affected_components=["auth_wrapper", "route_handler"],
        missing_guard="auth",
        pack_manifest_id="pack_1",
    )


def _audit(
    *,
    outcome: VerifierOutcome,
    checks: list[VerifierCheckResult],
) -> VerifierAuditEntry:
    return VerifierAuditEntry(
        finding_id="cand_x:A:test",
        verifier_outcome=outcome,
        checks_run=checks,
        pack_manifest_id="pack_1",
        reasoner_mode=ReasonerMode.A,
    )


def test_gray_zone_routes_partially_confirmed_single_pass() -> None:
    config = IntelligenceConfig()
    finding = _finding(confidence=0.6)
    audit = _audit(
        outcome=VerifierOutcome.partially_confirmed,
        checks=[
            VerifierCheckResult(name="graph_path_exists", result="pass"),
            VerifierCheckResult(name="edge_confidence_floor", result="fail", detail="min_conf=0.4 floor=0.8"),
            VerifierCheckResult(name="payload_contract", result="unavailable"),
        ],
    )

    rows = evaluate(
        [(finding, audit)],
        config=config,
        run_id="testrun",
        run_low_stitcher_coverage=False,
        graph=nx.DiGraph(),
    )

    assert len(rows) == 1
    assert rows[0].entry_reason == GrayZoneEntryReason.partially_confirmed_1_check


def test_gray_zone_marks_all_inferred_edges_and_holds_when_model_b_dissents() -> None:
    config = IntelligenceConfig()
    graph = nx.DiGraph()
    graph.add_edge("a", "b", inferred=False, confidence=1.0)
    finding = _finding(confidence=0.91, witness_path=["a", "b"])
    audit = _audit(
        outcome=VerifierOutcome.unconfirmed,
        checks=[
            VerifierCheckResult(name="edge_confidence_floor", result="fail", detail="min_conf=0.6 floor=0.8 all_inferred=true"),
        ],
    )

    rows = evaluate(
        [(finding, audit)],
        config=config,
        run_id="testrun",
        run_low_stitcher_coverage=False,
        graph=graph,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.entry_reason == GrayZoneEntryReason.unconfirmed_high_confidence
    assert row.vote_outcome == GrayZoneVoteOutcome.hold_for_review
    assert row.surfaced is False
    assert "model_b_dissented" in row.model_b_counter_reasoning


def test_gray_zone_surfaces_only_as_evaluator_surfaced_never_confirmed() -> None:
    config = IntelligenceConfig()
    graph = nx.DiGraph()
    graph.add_edge("a", "b", inferred=False, confidence=1.0)
    finding = _finding(confidence=0.9, witness_path=["a", "b"])
    audit = _audit(
        outcome=VerifierOutcome.unconfirmed,
        checks=[
            VerifierCheckResult(name="graph_path_exists", result="unavailable"),
            VerifierCheckResult(name="edge_confidence_floor", result="unavailable"),
        ],
    )

    rows = evaluate(
        [(finding, audit)],
        config=config,
        run_id="testrun",
        run_low_stitcher_coverage=True,
        graph=graph,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.vote_outcome == GrayZoneVoteOutcome.evaluator_surfaced
    assert row.surfaced is True
    assert finding.trust_level == VerifierOutcome.evaluator_surfaced
    assert finding.verifier_outcome == VerifierOutcome.unconfirmed
    assert "not graph-confirmed" in (finding.evaluator_surfaced_caveat or "")
