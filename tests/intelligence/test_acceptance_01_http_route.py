"""Acceptance test #1 \u2014 TS fetch('/api/repos/{id}') links to FastAPI
@router.get('/repos/{repo_id}') via HTTP_CALLS_ROUTE edge.

Uses a committed node-link fixture (no live graphify run) and a pair of
tiny source files that the HTTP probes re-read to lift route metadata.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from depos.analysis.config import IntelligenceConfig
from depos.enrichment.semantic_edges import HTTP_CALLS_ROUTE, enrich_graph


@pytest.fixture
def repo_root(tmp_path: Path, load_fixture_graph) -> Path:
    """Materialize the fixture graph plus the tiny TS + Python source files
    the HTTP probes need to find URL literals and route decorators."""
    # Node-link fixture defines two nodes pointing at these source files.
    graph = load_fixture_graph("acceptance_01_http_route.json")

    # Re-point source_file attrs at files under tmp_path so the probes
    # can read them, then write those files out.
    ts_rel = "apps/web/app/repos/page.tsx"
    py_rel = "backend/routers/repos.py"

    ts_path = tmp_path / ts_rel
    py_path = tmp_path / py_rel
    ts_path.parent.mkdir(parents=True, exist_ok=True)
    py_path.parent.mkdir(parents=True, exist_ok=True)
    ts_path.write_text(
        """export async function ReposPage() {
  const res = await fetch('/api/repos/42');
  return res.json();
}
""",
        encoding="utf-8",
    )
    py_path.write_text(
        """from fastapi import APIRouter

router = APIRouter()

@router.get('/repos/{repo_id}')
def list_repos(repo_id: int):
    return {'id': repo_id}
""",
        encoding="utf-8",
    )

    for nid, attrs in graph.nodes(data=True):
        if attrs.get("source_file", "").endswith(".tsx"):
            attrs["source_file"] = str(ts_path)
        elif attrs.get("source_file", "").endswith(".py"):
            attrs["source_file"] = str(py_path)

    pytest.G = graph  # smuggle the graph out for the test below
    return tmp_path


def test_http_calls_route_edge_emitted(repo_root: Path) -> None:
    graph = pytest.G
    config = IntelligenceConfig()
    enriched, coverage = enrich_graph(graph, config=config, repo_root=repo_root)

    # Find any HTTP_CALLS_ROUTE edges.
    http_edges = [
        (u, v, data)
        for u, v, data in enriched.edges(data=True)
        if data.get("relation") == HTTP_CALLS_ROUTE
    ]
    assert http_edges, "expected at least one HTTP_CALLS_ROUTE edge"
    u, v, data = http_edges[0]

    # Edge metadata checks.
    assert data["source_system"] == "typescript"
    assert data["target_system"] == "python"
    assert data["contract_kind"] == "http"
    assert data["api_method"] == "GET"
    assert data["route_pattern"].endswith("/repos/{*}")
    # Confidence 1.0 with literal URL and inferred method penalty for fetch
    # without an options arg (method default GET is flagged as NOT inferred
    # because fetch() without options uses GET).
    assert data["confidence"] >= 0.8
    assert data["inferred"] is False

    # Coverage report sanity.
    assert coverage.total_fastapi_routes == 1
    assert coverage.linked_routes == 1
    assert coverage.coverage_ratio == 1.0
    assert coverage.low_coverage is False
