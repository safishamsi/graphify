"""Persist intelligence runs and findings (SQLAlchemy session)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from depos.db import IntelligenceRun


def persist_intelligence_run(
    session: "Session",
    *,
    org_id: uuid.UUID,
    body: Any,
) -> "IntelligenceRun":
    """Insert one :class:`~depos.db.IntelligenceRun` and nested findings from a
    Pydantic-like ``body`` (same fields as ``IntelligenceRunCreate``)."""
    from depos.db import IntelligenceFinding, IntelligenceRun

    run = IntelligenceRun(
        org_id=org_id,
        repo_slug=body.repo_slug,
        base_ref=body.base_ref,
        head_ref=body.head_ref,
        analysis_mode=body.analysis_mode,
        provider=body.provider,
        low_stitcher_coverage=body.low_stitcher_coverage,
        token_estimator=body.token_estimator,
        ranking_phase=body.ranking_phase,
        status=body.status,
        pack_manifest_id=body.pack_manifest_id,
        finished_at=datetime.now(timezone.utc) if body.status != "running" else None,
    )
    session.add(run)
    session.flush()
    for f in body.findings:
        session.add(
            IntelligenceFinding(
                run_id=run.id,
                trust_level=f.trust_level,
                mode=f.mode,
                bug_type=f.bug_type,
                description=f.description,
                affected_components=list(f.affected_components),
                witness_path=list(f.witness_path),
                missing_guard=f.missing_guard,
                recommended_fix=f.recommended_fix,
                reasoner_confidence=f.reasoner_confidence,
                ranking_phase=f.ranking_phase,
                verifier_outcome=f.verifier_outcome,
                verifier_checks_passed=list(f.verifier_checks_passed),
                verifier_checks_inconclusive=list(f.verifier_checks_inconclusive),
                rls_verdict=f.rls_verdict,
                migration_state_facts=dict(f.migration_state_facts),
                caveats=dict(f.caveats),
            )
        )
    return run
