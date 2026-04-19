"""Subcommand implementations for ``depos-intel analyze``.

Kept thin on purpose. Heavy lifting lives in the intelligence modules:
:mod:`depos.enrichment.semantic_edges`, :mod:`depos.analysis.*`. The CLI
layer is responsible for:

- Constructing a :class:`GraphSource` from the CLI flags.
- Orchestrating Module 1 \u2192 Module 7.
- Writing output artifacts (``violations.json``, audit jsonl files) under
  ``<DEPOS_DATA>/intelligence/<run_id>/`` with caveats attached at write
  time (single output-layer responsibility).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from depos.analysis.config import IntelligenceConfig, load_config_from_env
from depos.analysis.detectors import get_detector, list_detectors, load_builtin
from depos.analysis.schemas import (
    AnalysisMode,
    Candidate,
    ContextBundle,
    Finding,
    RunResult,
    SeedType,
    RunMetadata,
    StitcherCoverageReport,
    VerifierOutcome,
)
from depos.graph_source import GraphifySource, GraphSource, InMemoryGraphSource


# ---------------------------------------------------------------------------
# Graph source construction
# ---------------------------------------------------------------------------

def _build_graph_source(args) -> GraphSource:
    path = getattr(args, "path", None)
    graph_json = getattr(args, "graph_json", None) or getattr(args, "cpg_path", None)
    if graph_json:
        gj = Path(graph_json)
        # Prefer GraphifySource JSON loader for production; keep the test
        # fixture loader for files authored as node-link fixtures.
        if gj.exists():
            return GraphifySource(graph_json_path=gj)
        raise SystemExit(f"graph json not found: {gj}")
    if path:
        return GraphifySource(root=Path(path))
    raise SystemExit("provide --path or --graph-json")


def _run_output_dir(config: IntelligenceConfig, run_id: str) -> Path:
    out = config.data_dir / config.run_output_subdir / run_id
    out.mkdir(parents=True, exist_ok=True)
    return out


def _source_repo_root(source: GraphSource) -> Path | None:
    meta = source.get_source_metadata()
    repo_path = meta.get("repo_path")
    if repo_path:
        return Path(repo_path)
    return None


# ---------------------------------------------------------------------------
# coverage (Module 1 only, no reasoning)
# ---------------------------------------------------------------------------

def run_coverage(args) -> int:
    config = load_config_from_env()
    source = _build_graph_source(args)
    graph = source.get_graph()

    # Module 1 is built incrementally; import what exists and gracefully skip
    # probes whose code has not landed yet.
    try:
        from depos.enrichment.semantic_edges import enrich_graph
    except ImportError:
        enrich_graph = None

    if enrich_graph is None:
        report = StitcherCoverageReport()
    else:
        _, report = enrich_graph(graph, config=config, repo_root=_source_repo_root(source))

    # Emit as structured JSON so scripts can consume it.
    print(json.dumps(report.model_dump(), indent=2, default=str))
    return 0


# ---------------------------------------------------------------------------
# repo / diff / replay (placeholders wired to run output-layer caveats)
# ---------------------------------------------------------------------------

def _new_run_metadata(
    config: IntelligenceConfig,
    source: GraphSource,
    *,
    mode: AnalysisMode,
) -> RunMetadata:
    return RunMetadata(
        run_id=uuid.uuid4().hex,
        analysis_mode=mode,
        provider=config.reasoner.provider,
        token_estimator=config.bundles.token_estimator,
        graph_source_metadata=source.get_source_metadata(),
    )


def _write_violations(
    out_dir: Path,
    result: RunResult | list[Finding],
    run_meta: RunMetadata | None = None,
) -> None:
    if isinstance(result, list):
        assert run_meta is not None
        result = RunResult(findings=result, detector_stats=[], ingest_reports=[], run_metadata=run_meta)
    payload: dict[str, Any] = {
        "run_id": result.run_metadata.run_id,
        "run_metadata": result.run_metadata.model_dump(mode="json"),
        "ingest_reports": [report.model_dump(mode="json") for report in result.ingest_reports],
        "detector_stats": [stat.model_dump(mode="json") for stat in result.detector_stats],
        "findings": [f.model_dump(mode="json") for f in result.findings],
    }
    (out_dir / "violations.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _detector_policy_from_args(args) -> dict[str, Any]:
    load_builtin()
    policy: dict[str, Any] = {"enabled": [], "disabled": [], "severity_overrides": {}}
    for raw in getattr(args, "detectors", []) or []:
        if not raw or "=" not in raw:
            continue
        kind, value = raw.split("=", 1)
        names = [item.strip() for item in value.split(",") if item.strip()]
        if kind == "include":
            policy["enabled"].extend(names)
        elif kind == "exclude":
            policy["disabled"].extend(names)
    if getattr(args, "no_reasoner", False):
        policy["disabled"].extend(spec.name for spec in list_detectors() if spec.requires_reasoner)
    policy["enabled"] = sorted(set(policy["enabled"]))
    policy["disabled"] = sorted(set(policy["disabled"]))
    if not policy["enabled"] and not policy["disabled"] and not policy["severity_overrides"]:
        return {}
    return policy


def _attach_run_caveats(findings: list[Finding], run_meta: RunMetadata) -> None:
    """Single point where run-level caveats are attached to every finding.

    Individual modules MUST NOT write caveat strings; they only set
    ``run_metadata`` flags and this layer formats user-facing text.
    """
    if run_meta.low_stitcher_coverage:
        caveat = (
            "Stitcher coverage dropped below the configured threshold for this run. "
            "Findings are not suppressed, but cross-component signals may be incomplete."
        )
        for f in findings:
            f.low_stitcher_coverage_caveat = caveat


def run_repo(args) -> int:
    config = load_config_from_env()
    source = _build_graph_source(args)
    run_meta = _new_run_metadata(config, source, mode=AnalysisMode.full_repo_scan)
    out_dir = _run_output_dir(config, run_meta.run_id)

    result = _run_pipeline(source, config, run_meta, detector_policy=_detector_policy_from_args(args))
    _attach_run_caveats(result.findings, run_meta)
    _write_violations(out_dir, result)
    payload: dict[str, Any] = {"run_id": run_meta.run_id, "output_dir": str(out_dir), "findings": len(result.findings)}
    if getattr(args, "print_detector_stats", False):
        payload["detector_stats"] = [row.model_dump(mode="json") for row in result.detector_stats]
    print(json.dumps(payload, indent=2))
    return 0


def run_diff(args) -> int:
    config = load_config_from_env()
    source = _build_graph_source(args)
    run_meta = _new_run_metadata(config, source, mode=AnalysisMode.diff_aware)
    out_dir = _run_output_dir(config, run_meta.run_id)

    diff_path = getattr(args, "diff_path", None)
    if diff_path:
        run_meta.head_ref = Path(diff_path).stem

    result = _run_pipeline(source, config, run_meta, diff_path=diff_path, detector_policy=_detector_policy_from_args(args))
    _attach_run_caveats(result.findings, run_meta)
    _write_violations(out_dir, result)
    payload: dict[str, Any] = {"run_id": run_meta.run_id, "output_dir": str(out_dir), "findings": len(result.findings)}
    if getattr(args, "print_detector_stats", False):
        payload["detector_stats"] = [row.model_dump(mode="json") for row in result.detector_stats]
    print(json.dumps(payload, indent=2))
    return 0


def run_replay(args) -> int:
    config = load_config_from_env()
    queue_path = Path(args.queue)
    if not queue_path.exists():
        raise SystemExit(f"queue file not found: {queue_path}")

    run_meta = RunMetadata(
        run_id=uuid.uuid4().hex,
        analysis_mode=AnalysisMode.diff_aware,
        provider=config.reasoner.provider,
        token_estimator=config.bundles.token_estimator,
    )
    out_dir = _run_output_dir(config, run_meta.run_id)

    now = datetime.now(tz=timezone.utc)
    stale_days = config.replay_stale_threshold_days
    findings: list[Finding] = []
    stale_count = 0
    with queue_path.open(encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            queued_at_s = row.get("queued_at")
            queued_at = None
            if queued_at_s:
                try:
                    queued_at = datetime.fromisoformat(queued_at_s.replace("Z", "+00:00"))
                except ValueError:
                    queued_at = None
            is_stale = queued_at is not None and (now - queued_at).days > stale_days

            # Try to re-run the reasoner if the Module 4 wiring is in place;
            # otherwise just surface a placeholder "replayed" audit row.
            try:
                from depos.analysis.reasoning_engine import replay_one  # type: ignore
            except ImportError:
                replay_one = None
            if replay_one is not None:
                for f in replay_one(row, config=config):
                    if is_stale:
                        f.stale_diff_replay_caveat = (
                            f"Queue entry is older than {stale_days} days; treat replay as stale."
                        )
                        stale_count += 1
                    findings.append(f)

    _attach_run_caveats(findings, run_meta)
    _write_violations(out_dir, findings, run_meta)
    print(json.dumps(
        {"run_id": run_meta.run_id, "output_dir": str(out_dir), "findings": len(findings), "stale_flagged": stale_count},
        indent=2,
    ))
    return 0


def run_score_bundles(args) -> int:
    from depos.analysis.graphcodebert import load_bundles, persist_scores, score_bundles

    bundles_path = Path(args.bundles_json)
    if not bundles_path.exists():
        raise SystemExit(f"bundles json not found: {bundles_path}")
    bundles = load_bundles(bundles_path)
    rows = score_bundles(
        bundles,
        model_name=args.model_name,
        cache_dir=args.cache_dir,
        device=args.device,
        local_files_only=bool(args.local_files_only),
    )
    out_path = Path(args.output) if getattr(args, "output", None) else bundles_path.parent / "bundle-scores.json"
    persist_scores(rows, out_path)
    print(json.dumps({"bundles": len(bundles), "scores": len(rows), "output": str(out_path)}, indent=2))
    return 0


def run_normalize_dataset(args) -> int:
    from graphify.build import build_from_json

    from depos.analysis.ast_normalize import normalize_dataset_dir
    from depos.snapshot import persist_graph_json

    dataset_dir = Path(args.dataset_dir)
    if not dataset_dir.exists():
        raise SystemExit(f"dataset dir not found: {dataset_dir}")
    repo_root = Path(args.repo_root) if getattr(args, "repo_root", None) else None
    extraction = normalize_dataset_dir(dataset_dir, repo_root=repo_root)
    if getattr(args, "extraction_output", None):
        extraction_path = Path(args.extraction_output)
        extraction_path.parent.mkdir(parents=True, exist_ok=True)
        extraction_path.write_text(json.dumps(extraction, indent=2), encoding="utf-8")
    graph = build_from_json(extraction, directed=True)
    out_path = Path(args.output)
    persist_graph_json(graph, out_path)
    print(
        json.dumps(
            {
                "dataset_dir": str(dataset_dir),
                "repo_root": str(repo_root) if repo_root is not None else None,
                "nodes": len(extraction.get("nodes", [])),
                "edges": len(extraction.get("edges", [])),
                "output": str(out_path),
                "extraction_output": str(args.extraction_output) if getattr(args, "extraction_output", None) else None,
            },
            indent=2,
        )
    )
    return 0


def _normalize_dataset_to_graph(
    *,
    dataset_dir: Path,
    repo_root: Path | None,
    graph_output: Path,
    extraction_output: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    from graphify.build import build_from_json

    from depos.analysis.ast_normalize import normalize_dataset_dir
    from depos.snapshot import persist_graph_json

    extraction = normalize_dataset_dir(dataset_dir, repo_root=repo_root)
    if extraction_output is not None:
        extraction_output.parent.mkdir(parents=True, exist_ok=True)
        extraction_output.write_text(json.dumps(extraction, indent=2), encoding="utf-8")
    graph = build_from_json(extraction, directed=True)
    persist_graph_json(graph, graph_output)
    return extraction, graph_output


def _build_dataset_candidates_and_bundles(
    *,
    graph_json: Path,
    config: IntelligenceConfig,
    candidates_output: Path,
    bundles_output: Path,
    max_bundles: int | None = None,
) -> tuple[list[Candidate], list[dict[str, Any]], dict[str, Any]]:
    from depos.analysis.candidate_identifier import identify_candidates
    from depos.analysis.context_bundle import build_bundle

    graph = InMemoryGraphSource.from_node_link_json(graph_json).get_graph()
    candidates, manifest = identify_candidates(
        graph,
        config=config,
        mode=AnalysisMode.full_repo_scan,
        manual_manifest={"entries": []},
        repo_root=None,
    )
    candidates_output.parent.mkdir(parents=True, exist_ok=True)
    candidates_output.write_text(
        json.dumps(
            {
                "resolved_via": manifest.resolved_via,
                "candidate_count": len(candidates),
                "candidates": [c.model_dump(mode="json") for c in candidates],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    selected = candidates[: max_bundles] if max_bundles is not None else candidates
    bundles = [build_bundle(graph, candidate, config=config).model_dump(mode="json") for candidate in selected]
    bundles_output.parent.mkdir(parents=True, exist_ok=True)
    bundles_output.write_text(json.dumps(bundles, indent=2), encoding="utf-8")
    return candidates, bundles, {"resolved_via": manifest.resolved_via}


def _candidate_from_bundle(bundle: ContextBundle, row: dict[str, Any], *, mode: AnalysisMode) -> Candidate:
    diff_anchors = [str(anchor.get("node_id", "")) for anchor in bundle.diff_anchors if anchor.get("node_id")]
    return Candidate(
        candidate_id=bundle.candidate_id,
        scope_id=bundle.scope_id,
        seed_type=SeedType.ai_driven,
        priority_score=float(row.get("graphcodebert_score", 0.0)),
        diff_anchors=diff_anchors,
        analysis_mode=mode,
        extra={
            "graphcodebert_score": float(row.get("graphcodebert_score", 0.0)),
            "graphcodebert_pattern": str(row.get("graphcodebert_pattern", "")),
            "top_patterns": list(row.get("top_patterns", [])),
            "bundle_pipeline_synthetic_candidate": True,
        },
    )


def _attach_score_hints(findings: list[Finding], score_map: dict[str, dict[str, Any]]) -> None:
    for finding in findings:
        candidate_id = finding.finding_id.split(":", 1)[0]
        row = score_map.get(candidate_id)
        if row is None:
            continue
        pattern = str(row.get("graphcodebert_pattern", "")).strip()
        score = float(row.get("graphcodebert_score", 0.0))
        if pattern:
            hint = f"GraphCodeBERT triage: {pattern} ({score:.3f})."
            if finding.recommended_fix:
                finding.recommended_fix = f"{hint} {finding.recommended_fix}"
            else:
                finding.recommended_fix = hint


def _execute_bundle_pipeline(args, *, emit_summary: bool = True) -> dict[str, Any]:
    from depos.analysis.graphcodebert import load_bundles, persist_scores, score_bundles
    from depos.analysis.gray_zone_evaluator import evaluate as evaluate_gray_zone
    from depos.analysis.reasoning_engine import run_all_modes
    from depos.analysis.verifier import verify_all

    config = load_config_from_env()
    if getattr(args, "provider", None):
        config.reasoner.provider = args.provider

    bundles_path = Path(args.bundles_json)
    if not bundles_path.exists():
        raise SystemExit(f"bundles json not found: {bundles_path}")
    bundles_raw = load_bundles(bundles_path)
    graph_json = Path(args.graph_json) if getattr(args, "graph_json", None) else Path("graphify-out/dataset-node-link.json")
    if not graph_json.exists():
        raise SystemExit(f"graph json not found: {graph_json}")

    if getattr(args, "scores_json", None):
        scores_path = Path(args.scores_json)
        if not scores_path.exists():
            raise SystemExit(f"scores json not found: {scores_path}")
        score_rows = json.loads(scores_path.read_text(encoding="utf-8"))
    else:
        score_rows = score_bundles(
            bundles_raw,
            model_name=args.model_name,
            cache_dir=args.cache_dir,
            device=args.device,
            local_files_only=bool(args.local_files_only),
        )
        scores_path = bundles_path.parent / "bundle-scores.json"
        persist_scores(score_rows, scores_path)

    score_map = {str(row.get("bundle_id", "")): row for row in score_rows if isinstance(row, dict)}
    selected_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for bundle_row in bundles_raw:
        row = score_map.get(str(bundle_row.get("bundle_id", "")))
        if row is None:
            continue
        score = float(row.get("graphcodebert_score", 0.0))
        if args.min_score is not None and score < args.min_score:
            continue
        selected_pairs.append((bundle_row, row))
    selected_pairs.sort(key=lambda pair: (-float(pair[1].get("graphcodebert_score", 0.0)), str(pair[0].get("bundle_id", ""))))
    selected_pairs = selected_pairs[: max(0, int(args.top_n))]

    run_meta = RunMetadata(
        run_id=uuid.uuid4().hex,
        analysis_mode=AnalysisMode.full_repo_scan,
        provider=config.reasoner.provider,
        token_estimator=config.bundles.token_estimator,
        ranking_phase=1,
        graph_source_metadata={
            "source_type": "bundles_json",
            "bundles_json": str(bundles_path),
            "scores_json": str(scores_path),
            "graph_json": str(graph_json),
        },
    )
    out_dir = Path(args.output_dir) if getattr(args, "output_dir", None) else _run_output_dir(config, run_meta.run_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    graph = InMemoryGraphSource.from_node_link_json(graph_json).get_graph()
    all_findings: list[Finding] = []
    all_audits = []
    bundle_trace: list[dict[str, Any]] = []

    for bundle_row, score_row in selected_pairs:
        bundle = ContextBundle.model_validate(bundle_row)
        candidate = _candidate_from_bundle(bundle, score_row, mode=run_meta.analysis_mode)
        graph_hint = {
            "score": float(score_row.get("graphcodebert_score", 0.0)),
            "pattern": str(score_row.get("graphcodebert_pattern", "")),
            "top_patterns": list(score_row.get("top_patterns", [])),
        }
        reasoner_outputs = run_all_modes(
            bundle,
            config=config,
            run_id=run_meta.run_id,
            ranking_phase=run_meta.ranking_phase,
            graphcodebert_hint=graph_hint,
        )
        audits, findings = verify_all(
            graph=graph,
            candidate=candidate,
            bundle=bundle,
            reasoner_outputs=reasoner_outputs,
            config=config,
            full_repo_scan=True,
        )
        all_audits.extend(audits)
        all_findings.extend(findings)
        bundle_trace.append(
            {
                "bundle_id": bundle.bundle_id,
                "candidate_id": bundle.candidate_id,
                "graphcodebert_score": graph_hint["score"],
                "graphcodebert_pattern": graph_hint["pattern"],
                "reasoner_modes_returned": sorted(mode.value for mode in reasoner_outputs.keys()),
                "findings": len(findings),
            }
        )

    _attach_score_hints(all_findings, {str(row.get("candidate_id", "")): row for row in score_rows if isinstance(row, dict)})
    gray_rows = evaluate_gray_zone(
        zip(all_findings, all_audits),
        config=config,
        run_id=run_meta.run_id,
        run_low_stitcher_coverage=False,
        graph=graph,
    )
    gray_path = out_dir / "gray_zone_audit.jsonl"
    with gray_path.open("w", encoding="utf-8") as fp:
        for row in gray_rows:
            fp.write(row.model_dump_json() + "\n")

    _write_violations(out_dir, all_findings, run_meta)
    (out_dir / "bundle_pipeline_trace.json").write_text(json.dumps(bundle_trace, indent=2), encoding="utf-8")
    summary = {
        "run_id": run_meta.run_id,
        "output_dir": str(out_dir),
        "selected_bundles": len(selected_pairs),
        "findings": len(all_findings),
        "gray_zone_rows": len(gray_rows),
    }
    if emit_summary:
        print(json.dumps(summary, indent=2))
    return summary


def run_bundle_pipeline(args) -> int:
    _execute_bundle_pipeline(args, emit_summary=True)
    return 0


def run_dataset_pipeline(args) -> int:
    from depos.analysis.graphcodebert import persist_scores, score_bundles

    config = load_config_from_env()
    if getattr(args, "provider", None):
        config.reasoner.provider = args.provider

    dataset_dir = Path(args.dataset_dir)
    if not dataset_dir.exists():
        raise SystemExit(f"dataset dir not found: {dataset_dir}")
    repo_root = Path(args.repo_root) if getattr(args, "repo_root", None) else None
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    graph_output = out_dir / "dataset-normalized-node-link.json"
    extraction_output = out_dir / "dataset-normalized-extraction.json" if getattr(args, "write_extraction", False) else None
    candidates_output = out_dir / "candidates.json"
    bundles_output = out_dir / "bundles.json"
    scores_output = out_dir / "bundle-scores.json"
    final_run_dir = out_dir / "gemma4-run"

    extraction, graph_json = _normalize_dataset_to_graph(
        dataset_dir=dataset_dir,
        repo_root=repo_root,
        graph_output=graph_output,
        extraction_output=extraction_output,
    )

    candidates, bundles, manifest_meta = _build_dataset_candidates_and_bundles(
        graph_json=graph_json,
        config=config,
        candidates_output=candidates_output,
        bundles_output=bundles_output,
        max_bundles=getattr(args, "max_bundles", None),
    )

    score_rows = score_bundles(
        bundles,
        model_name=args.model_name,
        cache_dir=args.cache_dir,
        device=args.device,
        local_files_only=bool(args.local_files_only),
    )
    persist_scores(score_rows, scores_output)

    class _BundlePipelineArgs:
        pass

    pipeline_args = _BundlePipelineArgs()
    pipeline_args.bundles_json = str(bundles_output)
    pipeline_args.scores_json = str(scores_output)
    pipeline_args.graph_json = str(graph_json)
    pipeline_args.output_dir = str(final_run_dir)
    pipeline_args.top_n = int(args.top_n)
    pipeline_args.min_score = args.min_score
    pipeline_args.provider = getattr(args, "provider", None)
    pipeline_args.model_name = args.model_name
    pipeline_args.cache_dir = args.cache_dir
    pipeline_args.device = args.device
    pipeline_args.local_files_only = bool(args.local_files_only)
    pipeline_summary = _execute_bundle_pipeline(pipeline_args, emit_summary=False)

    print(
        json.dumps(
            {
                "dataset_dir": str(dataset_dir),
                "repo_root": str(repo_root) if repo_root is not None else None,
                "normalized_nodes": len(extraction.get("nodes", [])),
                "normalized_edges": len(extraction.get("edges", [])),
                "resolved_via": manifest_meta["resolved_via"],
                "candidates": len(candidates),
                "bundles": len(bundles),
                "scores": len(score_rows),
                "intermediates": {
                    "graph_json": str(graph_output),
                    "candidates_json": str(candidates_output),
                    "bundles_json": str(bundles_output),
                    "scores_json": str(scores_output),
                    "extraction_json": str(extraction_output) if extraction_output is not None else None,
                },
                "pipeline": pipeline_summary,
                "final_output_dir": str(final_run_dir),
            },
            indent=2,
        )
    )
    return 0


# ---------------------------------------------------------------------------
# Pipeline orchestration (thin wrapper; real work is in analysis modules)
# ---------------------------------------------------------------------------

def _run_pipeline(
    source: GraphSource,
    config: IntelligenceConfig,
    run_meta: RunMetadata,
    *,
    diff_path: str | None = None,
    detector_policy: dict[str, Any] | None = None,
) -> RunResult:
    graph = source.get_graph()

    try:
        from depos.enrichment.semantic_edges import enrich_graph
    except ImportError:
        enrich_graph = None

    if enrich_graph is not None:
        repo_root = _source_repo_root(source)
        graph, coverage = enrich_graph(graph, config=config, repo_root=repo_root)
        run_meta.stitcher_coverage = coverage
        run_meta.low_stitcher_coverage = coverage.low_coverage
    else:
        repo_root = _source_repo_root(source)

    try:
        from depos.analysis.pipeline import run_modules_2_through_7  # type: ignore
    except ImportError:
        return RunResult(findings=[], detector_stats=[], ingest_reports=[], run_metadata=run_meta)

    return run_modules_2_through_7(
        graph,
        config=config,
        run_meta=run_meta,
        diff_path=diff_path,
        repo_root=repo_root,
        detector_policy=detector_policy,
    )


def run_detectors_list(args) -> int:
    load_builtin()
    rows = [
        {
            "name": spec.name,
            "version": spec.version,
            "universe": spec.universe.value,
            "requires_reasoner": spec.requires_reasoner,
            "severity_default": spec.severity_default,
        }
        for spec in sorted(list_detectors(), key=lambda row: row.name)
    ]
    if getattr(args, "json", False):
        print(json.dumps({"detectors": rows}, indent=2))
        return 0
    for row in rows:
        print(
            f"{row['name']}  v{row['version']}  "
            f"{row['universe']}  "
            f"reasoner={str(row['requires_reasoner']).lower()}  "
            f"severity={row['severity_default']}"
        )
    return 0


def run_detectors_explain(args) -> int:
    load_builtin()
    spec = get_detector(args.name)
    payload = spec.model_dump(mode="json")
    payload["example_witness"] = spec.tree[0].then.witness_template if spec.tree else []
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
        return 0
    print(json.dumps(payload, indent=2))
    return 0
