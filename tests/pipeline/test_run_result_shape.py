from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from depos.analysis.config import IntelligenceConfig
from depos.analysis.pipeline import run_modules_2_through_7
from depos.analysis.schemas import AnalysisMode, RunMetadata
from depos.enrichment.semantic_edges import enrich_graph


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_run_result_contains_detector_and_ingest_metadata(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write(repo_root / ".env", "APP_URL=https://example.com\n")
    _write(repo_root / "apps" / "web" / "package.json", json.dumps({"dependencies": {"react": "^18.2.0"}}, indent=2))
    _write(repo_root / "packages" / "ui" / "package.json", json.dumps({"dependencies": {"react": "^17.0.0"}}, indent=2))
    page = repo_root / "apps" / "web" / "app" / "page.tsx"
    _write(page, "export default function Page() { return process.env.MISSING_SECRET; }\n")

    graph = nx.DiGraph()
    graph.add_node("code::page", label="Page", source_file=str(page))

    config = IntelligenceConfig(data_dir=tmp_path / "depos-data")
    enriched, coverage = enrich_graph(graph, config=config, repo_root=repo_root)
    result = run_modules_2_through_7(
        enriched,
        config=config,
        run_meta=RunMetadata(
            run_id="detector-run-result",
            analysis_mode=AnalysisMode.full_repo_scan,
            provider="stub",
            stitcher_coverage=coverage,
            low_stitcher_coverage=coverage.low_coverage,
        ),
        repo_root=repo_root,
    )

    detector_names = {finding.detector_name for finding in result.findings}
    report_modules = {report.module for report in result.ingest_reports}
    stat_names = {stat.detector_name for stat in result.detector_stats if stat.candidates_emitted > 0}

    assert "dep-version-mismatch-across-workspaces" in detector_names
    assert "env-var-referenced-but-undefined" in detector_names
    assert "depos.ingest.manifests" in report_modules
    assert "depos.ingest.env_config" in report_modules
    assert "dep-version-mismatch-across-workspaces" in stat_names
    assert "env-var-referenced-but-undefined" in stat_names
    assert result.run_metadata.pipeline_version == "2.0.0"
    assert {universe.value for universe in result.run_metadata.universes_present} >= {"code", "deps", "env"}
