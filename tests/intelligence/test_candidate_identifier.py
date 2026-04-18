from __future__ import annotations

import networkx as nx

from depos.analysis.candidate_identifier import identify_candidates
from depos.analysis.config import IntelligenceConfig
from depos.analysis.schemas import AnalysisMode, SeedType


def test_candidate_identifier_seeds_public_surfaces_and_anomalies() -> None:
    graph = nx.DiGraph()
    graph.add_node(
        "py:route:list_repos",
        label="list_repos()",
        source_file="backend/routers/repos.py",
        is_fastapi_route=True,
        http_method="GET",
        route_pattern="/repos/{repo_id}",
    )
    graph.add_node(
        "ts:file:repos",
        label="ReposPage",
        source_file="apps/web/app/repos/page.tsx",
        http_call_sites=[{"url_literal": "/api/missing", "http_method": "GET"}],
    )
    graph.add_node(
        "py:auth:verify",
        label="verify_token()",
        source_file="depos/auth.py",
    )

    config = IntelligenceConfig(enable_ai_driven_seeds=True)
    candidates, manifest = identify_candidates(
        graph,
        config=config,
        mode=AnalysisMode.full_repo_scan,
    )

    assert manifest.entries == []

    seed_types = {candidate.seed_type for candidate in candidates}
    assert SeedType.interface_surface in seed_types
    assert SeedType.graph_anomaly in seed_types
    assert SeedType.ai_driven in seed_types

    route_surface = [c for c in candidates if c.extra.get("surface_type") == "public_route"]
    assert route_surface

    unmatched_http = [c for c in candidates if c.extra.get("anomaly") == "unmatched_http_client_call"]
    assert unmatched_http
    assert unmatched_http[0].extra["urls"] == ["/api/missing"]

    auth_surface = [c for c in candidates if c.extra.get("surface_type") == "auth_boundary"]
    assert auth_surface


def test_candidate_identifier_keeps_file_only_diff_entries() -> None:
    graph = nx.DiGraph()
    config = IntelligenceConfig()
    manual_manifest = {
        "entries": [
            {
                "path": "supabase/migrations/20260418000000_drop_old_table.sql",
                "node_ids": [],
                "migration_change": True,
                "file_change": True,
            }
        ]
    }

    candidates, manifest = identify_candidates(
        graph,
        config=config,
        mode=AnalysisMode.diff_aware,
        manual_manifest=manual_manifest,
    )

    assert len(manifest.entries) == 1
    diff_candidates = [c for c in candidates if c.seed_type == SeedType.diff_anchor]
    assert diff_candidates
    assert diff_candidates[0].extra["file_only"] is True
    assert diff_candidates[0].extra["removed_entity_references"] == 1


def test_candidate_identifier_prefers_synthetic_entities_over_leaf_nodes() -> None:
    graph = nx.DiGraph()
    graph.add_node(
        "leaf:identifier",
        label="auth",
        source_file="frontend/src/auth.ts",
        kind="identifier",
    )
    graph.add_node(
        "entity:function:verify",
        label="verify_token()",
        source_file="backend/app/auth.py",
        synthetic_entity=True,
        entity_kind="function",
        embedded_text="def verify_token():\n    return True",
    )

    candidates, _ = identify_candidates(
        graph,
        config=IntelligenceConfig(enable_ai_driven_seeds=True),
        mode=AnalysisMode.full_repo_scan,
    )

    anchor_ids = {anchor for candidate in candidates for anchor in candidate.diff_anchors}
    assert "entity:function:verify" in anchor_ids
    assert "leaf:identifier" not in anchor_ids
