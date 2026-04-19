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
    from depos.db import IntelligenceDetectorStat, IntelligenceFinding, IntelligenceRun

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
        pipeline_version=getattr(body, "pipeline_version", "0"),
        ingest_errors=list(getattr(body, "ingest_errors", [])),
        universes_present=list(getattr(body, "universes_present", [])),
        enabled_detectors=list(getattr(body, "enabled_detectors", [])),
        reasoner_run_health=getattr(body, "reasoner_run_health", "ok"),
        reasoner_health_reason=getattr(body, "reasoner_health_reason", ""),
        reasoner_attempts=int(getattr(body, "reasoner_attempts", 0) or 0),
        reasoner_successes=int(getattr(body, "reasoner_successes", 0) or 0),
        reasoner_failures=int(getattr(body, "reasoner_failures", 0) or 0),
        reasoner_failure_breakdown=dict(getattr(body, "reasoner_failure_breakdown", {}) or {}),
        evidence_summary=dict(getattr(body, "evidence_summary", {}) or {}),
        bundles_built=int(getattr(body, "bundles_built", 0) or 0),
        bundles_sent_to_reasoner=int(getattr(body, "bundles_sent_to_reasoner", 0) or 0),
        bundles_skipped_low_evidence=int(getattr(body, "bundles_skipped_low_evidence", 0) or 0),
        dataset_path_resolution=dict(getattr(body, "dataset_path_resolution", {}) or {}),
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
                detector_name=getattr(f, "detector_name", "legacy"),
                detector_version=getattr(f, "detector_version", "0"),
                pipeline_version=getattr(f, "pipeline_version", getattr(body, "pipeline_version", "0")),
                severity=getattr(f, "severity", "medium"),
            )
        )
    for stat in getattr(body, "detector_stats", []):
        session.add(
            IntelligenceDetectorStat(
                run_id=run.id,
                detector_name=stat.detector_name,
                detector_version=stat.detector_version,
                candidates_emitted=stat.candidates_emitted,
                verified_confirmed=stat.verified_confirmed,
                verified_invalid=stat.verified_invalid,
                mean_latency_ms=stat.mean_latency_ms,
                errors=list(stat.errors),
            )
        )
    return run
