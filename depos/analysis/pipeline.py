"""Pipeline that orchestrates Modules 2\u20137 against a Module 1 enriched graph.

Kept as a thin composition layer so each module is independently
testable. The CLI layer is responsible for writing user-facing outputs;
this module returns a :class:`RunResult` plus the side effects of
writing module-specific audit files (reasoner queue, gray-zone audit,
observability JSONL).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

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
    RunResult,
    RunMetadata,
    Universe,
    VerifierOutcome,
)
from depos.analysis.verifier import verify_all


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
) -> dict[str, dict[str, Any]]:
    if not config.ranker.use_graphcodebert or not bundles:
        return {}
    try:
        from depos.analysis.graphcodebert import score_bundles
    except Exception as exc:  # noqa: BLE001
        emit_event(config, run_id, "graphcodebert_skipped", reason=str(exc))
        return {}
    rows = score_bundles(
        bundles,
        model_name=config.ranker.graphcodebert_model_name,
        cache_dir=config.ranker.graphcodebert_cache_dir,
        device=config.ranker.graphcodebert_device,
        local_files_only=config.ranker.graphcodebert_local_files_only,
    )
    emit_event(config, run_id, "graphcodebert_scored", bundles=len(rows))
    return {str(row.get("candidate_id", "")): row for row in rows if isinstance(row, dict)}


def run_modules_2_through_7(
    graph: nx.DiGraph,
    *,
    config: IntelligenceConfig,
    run_meta: RunMetadata,
    diff_path: Optional[str] = None,
    repo_root: Optional[Path] = None,
    detector_policy: dict[str, Any] | None = None,
) -> RunResult:
    mode = run_meta.analysis_mode
    _prepare_run_metadata(graph, run_meta=run_meta, detector_policy=detector_policy)

    # Module 2 \u2014 candidates
    manifest = resolve_change_manifest(
        graph,
        diff_path=diff_path,
        repo_root=repo_root,
    )
    with timed_stage(config, run_meta.run_id, "detector_run"):
        candidates, detector_stats = run_all(graph, manifest, mode, config, detector_policy)
    if not candidates:
        for stat in detector_stats:
            stat.run_id = run_meta.run_id
        return RunResult(findings=[], detector_stats=detector_stats, ingest_reports=_load_ingest_reports(graph), run_metadata=run_meta)

    all_findings: list[Finding] = []
    all_audits = []
    ranker_inputs: list[RankerInput] = []
    labels: dict[str, tuple[str, str]] = {}
    full_repo_scan = mode == AnalysisMode.full_repo_scan
    detector_stats_by_name = {row.detector_name: row for row in detector_stats}

    # Track dropped-from-budget nodes back into the manifest.
    picked_anchors = {anchor for candidate in candidates for anchor in candidate.diff_anchors}
    for entry in manifest.entries:
        entry.dropped_from_budget = [node_id for node_id in entry.node_ids if node_id not in picked_anchors]

    bundles = {}
    bundle_rows: list[dict[str, Any]] = []
    with timed_stage(config, run_meta.run_id, "bundle_build", candidates=len(candidates)):
        for candidate in candidates:
            bundle = build_bundle(graph, candidate, config=config)
            bundles[candidate.candidate_id] = bundle
            bundle_rows.append(bundle.model_dump(mode="json"))

    graphcodebert_scores = _score_graphcodebert(bundle_rows, config=config, run_id=run_meta.run_id)

    # Modules 3 \u2192 6 per-candidate.
    for candidate in candidates:
        bundle = bundles[candidate.candidate_id]
        if candidate.candidate_id in graphcodebert_scores:
            candidate.extra["graphcodebert_score"] = float(graphcodebert_scores[candidate.candidate_id].get("graphcodebert_score", 0.0))
            candidate.extra["graphcodebert_pattern"] = str(graphcodebert_scores[candidate.candidate_id].get("graphcodebert_pattern", ""))

        detector_meta = candidate.extra.get("detector") if isinstance(candidate.extra.get("detector"), dict) else {}
        detector_name = str(detector_meta.get("detector_name") or "legacy")
        requires_reasoner = False
        if detector_name != "legacy":
            try:
                requires_reasoner = bool(get_detector(detector_name).requires_reasoner)
            except Exception:  # noqa: BLE001
                requires_reasoner = False
        reasoner_out = {}
        if requires_reasoner:
            with timed_stage(config, run_meta.run_id, "reasoner_run", candidate_id=candidate.candidate_id):
                reasoner_out = run_all_modes(
                    bundle,
                    config=config,
                    run_id=run_meta.run_id,
                    ranking_phase=run_meta.ranking_phase,
                    graphcodebert_hint=graphcodebert_scores.get(candidate.candidate_id),
                )
        audits, findings = verify_all(
            graph=graph,
            candidate=candidate,
            bundle=bundle,
            reasoner_outputs=reasoner_out,
            config=config,
            full_repo_scan=full_repo_scan,
        )
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

    # Module 7 \u2014 gray-zone evaluator.
    gray_rows = evaluate_gray_zone(
        zip(all_findings, all_audits),
        config=config,
        run_id=run_meta.run_id,
        run_low_stitcher_coverage=run_meta.low_stitcher_coverage,
        graph=graph,
    )
    persist_gray_zone(gray_rows, config=config, run_id=run_meta.run_id)

    for stat in detector_stats:
        stat.run_id = run_meta.run_id
    result = RunResult(
        findings=all_findings,
        detector_stats=detector_stats,
        ingest_reports=_load_ingest_reports(graph),
        run_metadata=run_meta,
    )
    return result


__all__ = ["run_modules_2_through_7"]
