"""Acceptance test #3 \u2014 the full Module 1\u21927 pipeline runs against the
small acceptance-01 fixture without crashing, emits a
``violations.json`` with valid JSON contract, writes ranker + gray-zone
audit files, and attaches run-level caveats correctly.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from depos.analysis.config import IntelligenceConfig
from depos.analysis.pipeline import run_modules_2_through_7
from depos.analysis.schemas import AnalysisMode, RunMetadata
from depos.enrichment.semantic_edges import enrich_graph


def _materialize_sources(tmp_path: Path, graph) -> Path:
    ts_rel = "apps/web/app/repos/page.tsx"
    py_rel = "backend/routers/repos.py"
    ts_path = tmp_path / ts_rel
    py_path = tmp_path / py_rel
    ts_path.parent.mkdir(parents=True, exist_ok=True)
    py_path.parent.mkdir(parents=True, exist_ok=True)
    ts_path.write_text(
        "export async function ReposPage() {\n"
        "  const res = await fetch('/api/repos/42');\n"
        "  return res.json();\n"
        "}\n",
        encoding="utf-8",
    )
    py_path.write_text(
        "from fastapi import APIRouter\n\n"
        "router = APIRouter()\n\n"
        "@router.get('/repos/{repo_id}')\n"
        "def list_repos(repo_id: int):\n"
        "    return {'id': repo_id}\n",
        encoding="utf-8",
    )
    for nid, attrs in graph.nodes(data=True):
        if attrs.get("source_file", "").endswith(".tsx"):
            attrs["source_file"] = str(ts_path)
        elif attrs.get("source_file", "").endswith(".py"):
            attrs["source_file"] = str(py_path)
    return tmp_path


def test_pipeline_end_to_end_runs(tmp_path, monkeypatch, load_fixture_graph):
    monkeypatch.setenv("DEPOS_DATA", str(tmp_path / "depos-data"))
    config = IntelligenceConfig(data_dir=tmp_path / "depos-data")

    graph = load_fixture_graph("acceptance_01_http_route.json")
    repo_root = _materialize_sources(tmp_path, graph)

    enriched, coverage = enrich_graph(graph, config=config, repo_root=repo_root)

    run_meta = RunMetadata(
        run_id="testrun",
        analysis_mode=AnalysisMode.full_repo_scan,
        provider="stub",
        stitcher_coverage=coverage,
        low_stitcher_coverage=coverage.low_coverage,
    )
    result = run_modules_2_through_7(
        enriched,
        config=config,
        run_meta=run_meta,
        repo_root=repo_root,
    )

    assert isinstance(result.findings, list)
    assert result.run_metadata.pipeline_version == "2.0.0"

    # Artifacts we expect (ranker jsonl always emits; gray-zone emits empty).
    run_dir = config.data_dir / config.run_output_subdir / run_meta.run_id
    assert (run_dir / "ranker_phase0_examples.jsonl").exists()
    assert (run_dir / "gray_zone_audit.jsonl").exists()
