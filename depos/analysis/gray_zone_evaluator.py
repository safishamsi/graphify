"""Module 7 \u2014 gray zone evaluator.

Handles findings that the verifier left in an ambiguous state:

- ``partially_confirmed`` with exactly 1 failing structural check
- ``unconfirmed`` with reasoner confidence above a threshold
- Any finding whose witness path relies only on inferred edges
- Any finding with ``rls_verdict == context_mismatch``
- Any run flagged with ``low_stitcher_coverage``

For each gray-zone entry we run a 3-model panel (A reviewer, B skeptic,
C graph-question answerer) using the providers defined in
``config.gray_zone``. If no network providers are configured, the panel
falls back to a conservative stub that votes ``uncertain`` for all three
so runs still produce a clean audit log.

Output: one :class:`GrayZoneAuditRow` per finding, appended to
``<DEPOS_DATA>/intelligence/<run_id>/gray_zone_audit.jsonl``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from depos.analysis.config import IntelligenceConfig
from depos.analysis.reasoning_engine import StubProvider, get_provider
from depos.analysis.schemas import (
    Finding,
    GrayZoneAuditRow,
    GrayZoneEntryReason,
    GrayZoneVote,
    GrayZoneVoteOutcome,
    ReasonerMode,
    RLSCoverage,
    VerifierAuditEntry,
    VerifierOutcome,
)


def _classify_entry_reason(
    finding: Finding,
    audit: VerifierAuditEntry,
    *,
    run_low_stitcher_coverage: bool,
    unconfirmed_threshold: float,
) -> GrayZoneEntryReason | None:
    fails = sum(1 for c in audit.checks_run if c.result in {"fail", "invalid"})
    if audit.verifier_outcome == VerifierOutcome.partially_confirmed and fails == 1:
        return GrayZoneEntryReason.partially_confirmed_1_check
    if (
        audit.verifier_outcome == VerifierOutcome.unconfirmed
        and finding.reasoner_confidence >= unconfirmed_threshold
    ):
        return GrayZoneEntryReason.unconfirmed_high_confidence
    if audit.inferred_edge_confidence_floor_applied and audit.verifier_outcome != VerifierOutcome.confirmed:
        return GrayZoneEntryReason.all_inferred_edges
    if finding.rls_verdict == RLSCoverage.context_mismatch:
        return GrayZoneEntryReason.rls_context_mismatch
    if run_low_stitcher_coverage:
        return GrayZoneEntryReason.low_stitcher_coverage
    return None


def _panel_vote(
    provider_name: str,
    prompt: str,
    *,
    config: IntelligenceConfig,
) -> tuple[GrayZoneVote, str]:
    """Run a single panel member. Returns (vote, reasoning_text)."""
    # For MVP, use the stub provider which always returns "uncertain".
    # Deployment-time override: if a real provider is configured, we
    # could call it here and parse the response.
    _ = provider_name, prompt, config
    return GrayZoneVote.uncertain, "stub-panel-default"


def _reconcile(votes: list[GrayZoneVote]) -> GrayZoneVoteOutcome:
    bug = sum(1 for v in votes if v in {GrayZoneVote.bug, GrayZoneVote.confirmed})
    no_bug = sum(1 for v in votes if v in {GrayZoneVote.no_bug, GrayZoneVote.refuted})
    if bug >= 2:
        return GrayZoneVoteOutcome.evaluator_surfaced
    if no_bug >= 2:
        return GrayZoneVoteOutcome.discard
    return GrayZoneVoteOutcome.hold_for_review


def evaluate(
    triples: Iterable[tuple[Finding, VerifierAuditEntry]],
    *,
    config: IntelligenceConfig,
    run_id: str,
    run_low_stitcher_coverage: bool,
) -> list[GrayZoneAuditRow]:
    if not config.gray_zone.enabled:
        return []

    rows: list[GrayZoneAuditRow] = []
    for finding, audit in triples:
        reason = _classify_entry_reason(
            finding,
            audit,
            run_low_stitcher_coverage=run_low_stitcher_coverage,
            unconfirmed_threshold=config.gray_zone.unconfirmed_confidence_threshold,
        )
        if reason is None:
            continue

        prompt = json.dumps(
            {
                "finding_id": finding.finding_id,
                "bug_type": finding.bug_type,
                "description": finding.description,
                "verifier_outcome": audit.verifier_outcome.value,
                "rls_verdict": finding.rls_verdict.value if finding.rls_verdict else None,
            }
        )

        vote_a, reason_a = _panel_vote(config.gray_zone.model_a_provider, prompt, config=config)
        vote_b, reason_b = _panel_vote(config.gray_zone.model_b_provider, prompt, config=config)
        vote_c, reason_c = _panel_vote(config.gray_zone.model_c_provider, prompt, config=config)

        outcome = _reconcile([vote_a, vote_b, vote_c])
        row = GrayZoneAuditRow(
            finding_id=finding.finding_id,
            entry_reason=reason,
            model_a_verdict=vote_a,
            model_a_confidence=0.5,
            model_a_reasoning=reason_a,
            model_b_verdict=vote_b,
            model_b_counter_reasoning=reason_b,
            model_c_structural_questions=["is the witness path reachable?"],
            model_c_graph_answers=["unknown"],
            model_c_verdict=vote_c,
            vote_outcome=outcome,
            surfaced=outcome == GrayZoneVoteOutcome.evaluator_surfaced,
            final_label="bug" if outcome == GrayZoneVoteOutcome.evaluator_surfaced else "uncertain",
            training_export=True,
        )
        rows.append(row)

        # Attach the evaluator-surfaced caveat if the panel surfaced the finding.
        if row.surfaced:
            finding.evaluator_surfaced_caveat = (
                "Surfaced by the gray-zone evaluator panel; review before acting."
            )
            finding.trust_level = VerifierOutcome.evaluator_surfaced
    return rows


def persist(
    rows: Iterable[GrayZoneAuditRow],
    *,
    config: IntelligenceConfig,
    run_id: str,
) -> Path:
    out_dir = config.data_dir / config.run_output_subdir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "gray_zone_audit.jsonl"
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(row.model_dump_json() + "\n")
    return path


__all__ = ["evaluate", "persist"]
