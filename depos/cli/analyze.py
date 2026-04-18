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
from depos.analysis.schemas import (
    AnalysisMode,
    Finding,
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
    findings: list[Finding],
    run_meta: RunMetadata,
) -> None:
    payload: dict[str, Any] = {
        "run_id": run_meta.run_id,
        "run_metadata": run_meta.model_dump(mode="json"),
        "findings": [f.model_dump(mode="json") for f in findings],
    }
    (out_dir / "violations.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


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

    findings: list[Finding] = _run_pipeline(source, config, run_meta)
    _attach_run_caveats(findings, run_meta)
    _write_violations(out_dir, findings, run_meta)
    print(json.dumps({"run_id": run_meta.run_id, "output_dir": str(out_dir), "findings": len(findings)}, indent=2))
    return 0


def run_diff(args) -> int:
    config = load_config_from_env()
    source = _build_graph_source(args)
    run_meta = _new_run_metadata(config, source, mode=AnalysisMode.diff_aware)
    out_dir = _run_output_dir(config, run_meta.run_id)

    diff_path = getattr(args, "diff_path", None)
    if diff_path:
        run_meta.head_ref = Path(diff_path).stem

    findings = _run_pipeline(source, config, run_meta, diff_path=diff_path)
    _attach_run_caveats(findings, run_meta)
    _write_violations(out_dir, findings, run_meta)
    print(json.dumps({"run_id": run_meta.run_id, "output_dir": str(out_dir), "findings": len(findings)}, indent=2))
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


# ---------------------------------------------------------------------------
# Pipeline orchestration (thin wrapper; real work is in analysis modules)
# ---------------------------------------------------------------------------

def _run_pipeline(
    source: GraphSource,
    config: IntelligenceConfig,
    run_meta: RunMetadata,
    *,
    diff_path: str | None = None,
) -> list[Finding]:
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
        return []

    return run_modules_2_through_7(
        graph,
        config=config,
        run_meta=run_meta,
        diff_path=diff_path,
        repo_root=repo_root,
    )
