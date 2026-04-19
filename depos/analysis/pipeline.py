"""Pipeline that orchestrates Modules 2\u20137 against a Module 1 enriched graph.

Kept as a thin composition layer so each module is independently
testable. The CLI layer is responsible for writing user-facing outputs;
this module returns a :class:`RunResult` plus the side effects of
writing module-specific audit files (reasoner queue, gray-zone audit,
observability JSONL).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

import networkx as nx

from depos.analysis.candidate_identifier import resolve_change_manifest
from depos.analysis.config import IntelligenceConfig
from depos.analysis.context_bundle import build_bundle
from depos.analysis.detectors import PIPELINE_VERSION, get_detector, list_detectors, load_builtin, run_all
from depos.analysis.gray_zone_evaluator import evaluate as evaluate_gray_zone
from depos.analysis.gray_zone_evaluator import persist as persist_gray_zone
from depos.analysis.observability import emit_event, timed_stage
from depos.analysis.ranker import rank, serialize_examples
from depos.analysis.reasoning_engine import run_all_modes
from depos.analysis.schemas import (
    AnalysisMode,
    Finding,
    IngestReport,
    RankerDiffFeatures,
    RankerInput,
    ReasonerCallStats,
    RunResult,
    RunMetadata,
    Universe,
    VerifierOutcome,
)
from depos.analysis.verifier import verify_all


# Mirrors depos.analysis.context_bundle._QUALITY_RANK so we can compare bundle
# evidence quality without reaching into a private symbol.
_QUALITY_RANK = {"missing": 0, "label_only": 1, "embedded": 2, "full": 3}


def _dominant_quality(evidence) -> str:
    if evidence.snippets_full > 0:
        return "full"
    if evidence.snippets_embedded > 0:
        return "embedded"
    if evidence.snippets_label_only > 0:
        return "label_only"
    return "missing"


def _reasoner_health_reason(stats: ReasonerCallStats, bundles_sent: int) -> str:
    if bundles_sent == 0 or stats.attempts == 0:
        return "no_bundles_sent_to_reasoner" if bundles_sent == 0 else ""
    if stats.successes == 0:
        worst_reason = max(stats.by_reason.items(), key=lambda kv: kv[1])[0] if stats.by_reason else "unknown"
        return f"all_calls_failed:{worst_reason}"
    if stats.successes / stats.attempts < 0.5:
        worst_reason = max(stats.by_reason.items(), key=lambda kv: kv[1])[0] if stats.by_reason else "unknown"
        return f"majority_failed:{worst_reason}"
    return ""


def _emit_progress(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _build_ranker_input(candidate, bundle) -> RankerInput:
    cross_lang = len(bundle.cross_language_seams)
    changed_nodes = len(candidate.diff_anchors) + len([c for c in bundle.call_chain_in if c.get("depth", 0) == 1])
    unresolved = int(candidate.extra.get("unresolved_symbol_count", 0))
    removed_refs = int(candidate.extra.get("removed_entity_references", 0))
    detector_meta = candidate.extra.get("detector") if isinstance(candidate.extra.get("detector"), dict) else {}
    oracle_hints = dict(detector_meta.get("oracle_hints") or candidate.extra.get("oracle_hints") or {})
    missing_guard_signals = int(oracle_hints.get("missing_guard_signals", candidate.extra.get("missing_guard_signals", 0)) or 0)
    graphcodebert_score = float(candidate.extra.get("graphcodebert_score", 0.0) or 0.0)
    features = RankerDiffFeatures(
        changed_nodes_on_path=changed_nodes,
        cross_lang_seams_on_path=cross_lang,
        unresolved_symbols=unresolved,
        removed_entities_referenced=removed_refs,
        missing_guard_signals=missing_guard_signals,
        graphcodebert_score=graphcodebert_score,
    )
    return RankerInput(
        candidate_id=candidate.candidate_id,
        candidate_path=candidate.diff_anchors,
        edge_sequence=[s.relation for s in bundle.cross_language_seams],
        node_attrs={},
        diff_features=features,
    )


def _load_ingest_reports(graph: nx.DiGraph) -> list[IngestReport]:
    rows = graph.graph.get("run_metadata", {}).get("ingest_reports") or []
    return [IngestReport.model_validate(row) for row in rows if isinstance(row, dict)]


def _universes_present(graph: nx.DiGraph) -> list[Universe]:
    seen = {Universe.code}
    for _, attrs in graph.nodes(data=True):
        raw = attrs.get("universe")
        if not raw:
            continue
        try:
            seen.add(Universe(str(raw)))
        except ValueError:
            continue
    return sorted(seen, key=lambda value: value.value)


def _prepare_run_metadata(
    graph: nx.DiGraph,
    *,
    run_meta: RunMetadata,
    detector_policy: dict[str, Any] | None,
) -> None:
    from depos.analysis.detectors.policy import load_policy

    load_builtin()
    policy = load_policy(detector_policy)
    run_meta.pipeline_version = PIPELINE_VERSION
    run_meta.detector_versions = {spec.name: spec.version for spec in list_detectors()}
    run_meta.enabled_detectors = sorted(policy.enabled) if policy.enabled else sorted(
        spec.name for spec in list_detectors() if spec.enabled_by_default and spec.name not in policy.disabled
    )
    run_meta.disabled_detectors = sorted(policy.disabled)
    run_meta.universes_present = _universes_present(graph)
    ingest_reports = _load_ingest_reports(graph)
    run_meta.ingest_errors = [error for report in ingest_reports for error in report.errors]
    extra_errors = graph.graph.get("run_metadata", {}).get("ingest_errors") or []
    run_meta.ingest_errors.extend(error for error in extra_errors if isinstance(error, dict))


def _score_graphcodebert(
    bundles: list[dict[str, Any]],
    *,
    config: IntelligenceConfig,
    run_id: str,
    progress: Callable[[str], None] | None = None,
) -> dict[str, dict[str, Any]]:
    if not config.ranker.use_graphcodebert or not bundles:
        if config.ranker.use_graphcodebert and not bundles:
            _emit_progress(progress, "GraphCodeBERT: enabled, but no bundles were available to score.")
        return {}
    _emit_progress(progress, f"GraphCodeBERT: scoring {len(bundles)} bundles.")
    try:
        from depos.analysis.graphcodebert import score_bundles
    except Exception as exc:  # noqa: BLE001
        emit_event(config, run_id, "graphcodebert_skipped", reason=str(exc))
        _emit_progress(progress, f"GraphCodeBERT: skipped ({exc}).")
        return {}
    rows = score_bundles(
        bundles,
        model_name=config.ranker.graphcodebert_model_name,
        cache_dir=config.ranker.graphcodebert_cache_dir,
        device=config.ranker.graphcodebert_device,
        local_files_only=config.ranker.graphcodebert_local_files_only,
    )
    emit_event(config, run_id, "graphcodebert_scored", bundles=len(rows))
    _emit_progress(progress, f"GraphCodeBERT: scored {len(rows)} bundles.")
    return {str(row.get("candidate_id", "")): row for row in rows if isinstance(row, dict)}


def run_modules_2_through_7(
    graph: nx.DiGraph,
    *,
    config: IntelligenceConfig,
    run_meta: RunMetadata,
    diff_path: Optional[str] = None,
    repo_root: Optional[Path] = None,
    detector_policy: dict[str, Any] | None = None,
    progress: Callable[[str], None] | None = None,
) -> RunResult:
    mode = run_meta.analysis_mode
    _emit_progress(progress, f"Pipeline: preparing run metadata for {mode.value} mode.")
    _prepare_run_metadata(graph, run_meta=run_meta, detector_policy=detector_policy)
    _emit_progress(
        progress,
        f"Pipeline: enabled detectors={len(run_meta.enabled_detectors)} disabled={len(run_meta.disabled_detectors)} universes={','.join(u.value for u in run_meta.universes_present)}.",
    )

    # Module 2 \u2014 candidates
    _emit_progress(progress, "Module 2: resolving change manifest.")
    manifest = resolve_change_manifest(
        graph,
        diff_path=diff_path,
        repo_root=repo_root,
    )
    _emit_progress(progress, f"Module 2: manifest resolved via {manifest.resolved_via}.")
    _emit_progress(progress, "Module 2: running detectors.")
    with timed_stage(config, run_meta.run_id, "detector_run"):
        candidates, detector_stats = run_all(graph, manifest, mode, config, detector_policy)
    _emit_progress(progress, f"Module 2: detectors emitted {len(candidates)} candidates.")
    if not candidates:
        for stat in detector_stats:
            stat.run_id = run_meta.run_id
        _emit_progress(progress, "Pipeline: no candidates emitted; stopping after Module 2.")
        return RunResult(findings=[], detector_stats=detector_stats, ingest_reports=_load_ingest_reports(graph), run_metadata=run_meta)

    all_findings: list[Finding] = []
    all_audits = []
    ranker_inputs: list[RankerInput] = []
    labels: dict[str, tuple[str, str]] = {}
    full_repo_scan = mode == AnalysisMode.full_repo_scan
    detector_stats_by_name = {row.detector_name: row for row in detector_stats}
    reasoner_stats = ReasonerCallStats()
    bundles_sent_to_reasoner = 0
    bundles_skipped_low_evidence = 0
    evidence_quality_counts: dict[str, int] = {"full": 0, "embedded": 0, "label_only": 0, "missing": 0}
    quality_floor_name = config.bundles.min_evidence_quality_for_reasoner
    quality_floor = _QUALITY_RANK.get(quality_floor_name, _QUALITY_RANK["embedded"])
    score_floor = float(config.bundles.min_evidence_score_for_reasoner)

    # Track dropped-from-budget nodes back into the manifest.
    picked_anchors = {anchor for candidate in candidates for anchor in candidate.diff_anchors}
    for entry in manifest.entries:
        entry.dropped_from_budget = [node_id for node_id in entry.node_ids if node_id not in picked_anchors]

    bundles = {}
    bundle_rows: list[dict[str, Any]] = []
    _emit_progress(progress, f"Module 3: building {len(candidates)} context bundles.")
    with timed_stage(config, run_meta.run_id, "bundle_build", candidates=len(candidates)):
        for candidate in candidates:
            bundle = build_bundle(graph, candidate, config=config)
            bundles[candidate.candidate_id] = bundle
            bundle_rows.append(bundle.model_dump(mode="json"))
            quality = _dominant_quality(bundle.evidence)
            evidence_quality_counts[quality] = evidence_quality_counts.get(quality, 0) + 1
    _emit_progress(progress, f"Module 3: built {len(bundle_rows)} bundles.")

    graphcodebert_scores = _score_graphcodebert(
        bundle_rows,
        config=config,
        run_id=run_meta.run_id,
        progress=progress,
    )

    # Modules 3 \u2192 6 per-candidate.
    total_candidates = len(candidates)
    for index, candidate in enumerate(candidates, start=1):
        bundle = bundles[candidate.candidate_id]
        if candidate.candidate_id in graphcodebert_scores:
            candidate.extra["graphcodebert_score"] = float(graphcodebert_scores[candidate.candidate_id].get("graphcodebert_score", 0.0))
            candidate.extra["graphcodebert_pattern"] = str(graphcodebert_scores[candidate.candidate_id].get("graphcodebert_pattern", ""))

        detector_meta = candidate.extra.get("detector") if isinstance(candidate.extra.get("detector"), dict) else {}
        detector_name = str(detector_meta.get("detector_name") or "legacy")
        _emit_progress(progress, f"Candidate {index}/{total_candidates}: detector={detector_name} candidate_id={candidate.candidate_id}.")
        requires_reasoner = False
        if detector_name != "legacy":
            try:
                requires_reasoner = bool(get_detector(detector_name).requires_reasoner)
            except Exception:  # noqa: BLE001
                requires_reasoner = False
        reasoner_out = {}
        if requires_reasoner:
            evidence = bundle.evidence
            quality = _dominant_quality(evidence)
            passes_quality = _QUALITY_RANK.get(quality, 0) >= quality_floor
            passes_score = evidence.evidence_score >= score_floor
            if not (passes_quality and passes_score):
                bundles_skipped_low_evidence += 1
                _emit_progress(
                    progress,
                    f"Module 4: skipped reasoner for candidate {index}/{total_candidates} "
                    f"(evidence_quality={quality}, score={evidence.evidence_score:.2f} "
                    f"< floor quality={quality_floor_name}/score={score_floor:.2f}).",
                )
            else:
                bundles_sent_to_reasoner += 1
                _emit_progress(progress, f"Module 4: running reasoner for candidate {index}/{total_candidates}.")
                bundle_stats = ReasonerCallStats()
                with timed_stage(config, run_meta.run_id, "reasoner_run", candidate_id=candidate.candidate_id):
                    reasoner_out = run_all_modes(
                        bundle,
                        config=config,
                        run_id=run_meta.run_id,
                        ranking_phase=run_meta.ranking_phase,
                        graphcodebert_hint=graphcodebert_scores.get(candidate.candidate_id),
                        stats=bundle_stats,
                    )
                reasoner_stats.merge(bundle_stats)
                _emit_progress(
                    progress,
                    f"Module 4: reasoner returned {len(reasoner_out)} mode outputs for "
                    f"candidate {index}/{total_candidates} "
                    f"({bundle_stats.successes}/{bundle_stats.attempts} calls succeeded).",
                )
        else:
            _emit_progress(progress, f"Module 4: skipped reasoner for candidate {index}/{total_candidates} (mechanical detector).")
        _emit_progress(progress, f"Module 6: verifying candidate {index}/{total_candidates}.")
        audits, findings = verify_all(
            graph=graph,
            candidate=candidate,
            bundle=bundle,
            reasoner_outputs=reasoner_out,
            config=config,
            full_repo_scan=full_repo_scan,
        )
        _emit_progress(progress, f"Module 6: candidate {index}/{total_candidates} produced {len(findings)} findings and {len(audits)} audits.")
        all_findings.extend(findings)
        all_audits.extend(audits)
        ranker_inputs.append(_build_ranker_input(candidate, bundle))
        stat = detector_stats_by_name.get(detector_name)
        if stat is not None:
            stat.verified_confirmed += sum(1 for audit in audits if audit.verifier_outcome == VerifierOutcome.confirmed)
            stat.verified_invalid += sum(1 for audit in audits if audit.verifier_outcome == VerifierOutcome.invalid_reasoning)
        # Derive label for ranker training data.
        if any(a.verifier_outcome == VerifierOutcome.confirmed for a in audits):
            labels[candidate.candidate_id] = ("suspicious", "verifier_confirmed")
        elif audits and all(a.verifier_outcome == VerifierOutcome.invalid_reasoning for a in audits):
            labels[candidate.candidate_id] = ("not_suspicious", "verifier_contradicted")

    # Module 5 \u2014 rank and serialize phase-0 training rows.
    _emit_progress(progress, f"Module 5: ranking {len(ranker_inputs)} candidates and writing training rows.")
    scores = rank(ranker_inputs, config=config)
    score_map = {s.candidate_id: s for s in scores}
    for f in all_findings:
        candidate_id = f.finding_id.split(":", 1)[0]
        s = score_map.get(candidate_id)
        if s is not None:
            f.ranking_phase = s.ranking_phase
    serialize_examples(
        ranker_inputs,
        labels,
        config=config,
        run_id=run_meta.run_id,
        repo_id=run_meta.repo_id,
        base_ref=run_meta.base_ref,
        head_ref=run_meta.head_ref,
    )
    _emit_progress(progress, f"Module 5: serialized {len(scores)} rank rows.")

    # Module 7 \u2014 gray-zone evaluator.
    _emit_progress(progress, f"Module 7: evaluating gray-zone cases across {len(all_findings)} findings.")
    gray_rows = evaluate_gray_zone(
        zip(all_findings, all_audits),
        config=config,
        run_id=run_meta.run_id,
        run_low_stitcher_coverage=run_meta.low_stitcher_coverage,
        graph=graph,
    )
    persist_gray_zone(gray_rows, config=config, run_id=run_meta.run_id)
    _emit_progress(progress, f"Module 7: wrote {len(gray_rows)} gray-zone audit rows.")

    for stat in detector_stats:
        stat.run_id = run_meta.run_id

    bundles_built = len(bundle_rows)
    health = reasoner_stats.health()
    health_reason = _reasoner_health_reason(reasoner_stats, bundles_sent_to_reasoner)
    evidence_summary = {
        "bundles_built": bundles_built,
        "bundles_sent_to_reasoner": bundles_sent_to_reasoner,
        "bundles_skipped_low_evidence": bundles_skipped_low_evidence,
        "by_quality": evidence_quality_counts,
        "min_evidence_quality_for_reasoner": quality_floor_name,
        "min_evidence_score_for_reasoner": score_floor,
    }
    run_meta.reasoner_call_stats = reasoner_stats
    run_meta.reasoner_run_health = health
    run_meta.reasoner_health_reason = health_reason
    run_meta.bundles_built = bundles_built
    run_meta.bundles_sent_to_reasoner = bundles_sent_to_reasoner
    run_meta.bundles_skipped_low_evidence = bundles_skipped_low_evidence
    run_meta.evidence_summary = evidence_summary

    result = RunResult(
        findings=all_findings,
        detector_stats=detector_stats,
        ingest_reports=_load_ingest_reports(graph),
        run_metadata=run_meta,
        reasoner_call_stats=reasoner_stats,
        evidence_summary=evidence_summary,
    )
    _emit_progress(
        progress,
        f"Pipeline: completed with {len(all_findings)} findings. "
        f"reasoner_run_health={health} (attempts={reasoner_stats.attempts}, "
        f"successes={reasoner_stats.successes}, failures={reasoner_stats.failures}).",
    )
    return result


__all__ = ["run_modules_2_through_7"]
