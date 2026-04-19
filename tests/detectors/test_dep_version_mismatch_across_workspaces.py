from __future__ import annotations

import networkx as nx

from depos.analysis.config import IntelligenceConfig
from depos.analysis.context_bundle import build_bundle
from depos.analysis.detectors import run_all
from depos.analysis.schemas import AnalysisMode, ChangeManifest
from depos.analysis.verifier import verify_all


def _graph(range_a: str, range_b: str) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node(
        "pkg::dep:apps/web::react",
        node_kind="package_dep",
        universe="deps",
        package_name="react",
        declared_range=range_a,
        manifest_id="apps/web/package.json",
        source_file="apps/web/package.json",
    )
    graph.add_node(
        "pkg::dep:packages/ui::react",
        node_kind="package_dep",
        universe="deps",
        package_name="react",
        declared_range=range_b,
        manifest_id="packages/ui/package.json",
        source_file="packages/ui/package.json",
    )
    return graph


def test_dep_version_mismatch_positive() -> None:
    candidates, _ = run_all(_graph("^18.2.0", "^17.0.0"), ChangeManifest(), AnalysisMode.full_repo_scan, IntelligenceConfig())
    assert any(candidate.extra.get("detector", {}).get("detector_name") == "dep-version-mismatch-across-workspaces" for candidate in candidates)


def test_dep_version_mismatch_negative() -> None:
    candidates, _ = run_all(_graph("^18.2.0", "^18.2.0"), ChangeManifest(), AnalysisMode.full_repo_scan, IntelligenceConfig())
    assert all(candidate.extra.get("detector", {}).get("detector_name") != "dep-version-mismatch-across-workspaces" for candidate in candidates)


def test_dep_version_mismatch_verifier_confirms() -> None:
    config = IntelligenceConfig()
    graph = _graph("^18.2.0", "^17.0.0")
    candidates, _ = run_all(graph, ChangeManifest(), AnalysisMode.full_repo_scan, config)
    candidate = next(candidate for candidate in candidates if candidate.extra.get("detector", {}).get("detector_name") == "dep-version-mismatch-across-workspaces")
    bundle = build_bundle(graph, candidate, config=config)
    audits, findings = verify_all(
        graph=graph,
        candidate=candidate,
        bundle=bundle,
        reasoner_outputs={},
        config=config,
        full_repo_scan=True,
    )

    assert audits[0].verifier_outcome.value == "confirmed"
    assert findings[0].detector_name == "dep-version-mismatch-across-workspaces"
