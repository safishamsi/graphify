from __future__ import annotations

import json
from pathlib import Path

from graphify.build import build_from_json

from depos.analysis.ast_normalize import normalize_dataset_dir
from depos.analysis.candidate_identifier import identify_candidates
from depos.analysis.config import IntelligenceConfig
from depos.analysis.context_bundle import build_bundle
from depos.analysis.schemas import AnalysisMode


def _write_ast(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_normalize_dataset_dir_emits_entity_graph(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    dataset_dir = tmp_path / "dataset"
    repo_root.mkdir()
    dataset_dir.mkdir()

    main_path = repo_root / "backend" / "app" / "main.py"
    auth_path = repo_root / "backend" / "app" / "services" / "auth.py"
    main_path.parent.mkdir(parents=True)
    auth_path.parent.mkdir(parents=True)
    main_path.write_text(
        "from app.services.auth import verify_token\n\n"
        "def handle_request():\n"
        "    return verify_token()\n",
        encoding="utf-8",
    )
    auth_path.write_text(
        "def verify_token():\n"
        "    return True\n",
        encoding="utf-8",
    )

    _write_ast(
        dataset_dir / "backend_app_main.py.json",
        {
            "commit_sha": "abc123",
            "nodes": [
                {"id": "ast:abc123:backend/app/main.py:0:68:module", "kind": "module", "label": "module", "span": {"start": {"line": 1}, "end": {"line": 4}}},
                {"id": "ast:abc123:backend/app/main.py:0:42:import_from_statement", "kind": "import_from_statement", "label": "from app.services.auth import verify_token", "span": {"start": {"line": 1}, "end": {"line": 1}}},
                {"id": "ast:abc123:backend/app/main.py:44:68:function_definition", "kind": "function_definition", "label": "def handle_request():\n    return verify_token()", "span": {"start": {"line": 3}, "end": {"line": 4}}},
                {"id": "ast:abc123:backend/app/main.py:48:62:identifier", "kind": "identifier", "label": "handle_request", "span": {"start": {"line": 3}, "end": {"line": 3}}},
                {"id": "ast:abc123:backend/app/main.py:63:68:call", "kind": "call", "label": "verify_token()", "span": {"start": {"line": 4}, "end": {"line": 4}}},
            ],
            "edges": [
                {"source_id": "ast:abc123:backend/app/main.py:0:68:module", "target_id": "ast:abc123:backend/app/main.py:0:42:import_from_statement", "type": "child"},
                {"source_id": "ast:abc123:backend/app/main.py:0:68:module", "target_id": "ast:abc123:backend/app/main.py:44:68:function_definition", "type": "child"},
                {"source_id": "ast:abc123:backend/app/main.py:44:68:function_definition", "target_id": "ast:abc123:backend/app/main.py:48:62:identifier", "type": "child"},
                {"source_id": "ast:abc123:backend/app/main.py:44:68:function_definition", "target_id": "ast:abc123:backend/app/main.py:63:68:call", "type": "child"},
            ],
        },
    )
    _write_ast(
        dataset_dir / "backend_app_services_auth.py.json",
        {
            "commit_sha": "abc123",
            "nodes": [
                {"id": "ast:abc123:backend/app/services/auth.py:0:32:module", "kind": "module", "label": "module", "span": {"start": {"line": 1}, "end": {"line": 2}}},
                {"id": "ast:abc123:backend/app/services/auth.py:0:32:function_definition", "kind": "function_definition", "label": "def verify_token():\n    return True", "span": {"start": {"line": 1}, "end": {"line": 2}}},
                {"id": "ast:abc123:backend/app/services/auth.py:4:16:identifier", "kind": "identifier", "label": "verify_token", "span": {"start": {"line": 1}, "end": {"line": 1}}},
            ],
            "edges": [
                {"source_id": "ast:abc123:backend/app/services/auth.py:0:32:module", "target_id": "ast:abc123:backend/app/services/auth.py:0:32:function_definition", "type": "child"},
                {"source_id": "ast:abc123:backend/app/services/auth.py:0:32:function_definition", "target_id": "ast:abc123:backend/app/services/auth.py:4:16:identifier", "type": "child"},
            ],
        },
    )

    extraction = normalize_dataset_dir(dataset_dir, repo_root=repo_root)
    graph = build_from_json(extraction, directed=True)

    function_nodes = {
        nid: attrs for nid, attrs in graph.nodes(data=True) if attrs.get("entity_kind") == "function"
    }
    assert any(attrs.get("label") == "handle_request()" for attrs in function_nodes.values())
    assert any(attrs.get("label") == "verify_token()" for attrs in function_nodes.values())

    import_edges = [(u, v, d) for u, v, d in graph.edges(data=True) if d.get("relation") == "IMPORTS"]
    assert import_edges

    call_edges = [(u, v, d) for u, v, d in graph.edges(data=True) if d.get("relation") == "CALLS"]
    assert call_edges
    assert any("handle_request" in graph.nodes[u].get("label", "") for u, _, _ in call_edges)
    assert any("verify_token" in graph.nodes[v].get("label", "") for _, v, _ in call_edges)


def test_build_bundle_falls_back_to_embedded_text() -> None:
    import networkx as nx

    graph = nx.DiGraph()
    graph.add_node(
        "entity:function:demo",
        label="verify_token()",
        source_file="missing.py",
        start_line=10,
        end_line=12,
        embedded_text="def verify_token():\n    return True",
        synthetic_entity=True,
        entity_kind="function",
    )
    config = IntelligenceConfig()
    candidates, _ = identify_candidates(
        graph,
        config=IntelligenceConfig(enable_ai_driven_seeds=True),
        mode=AnalysisMode.full_repo_scan,
    )
    bundle = build_bundle(graph, candidates[0], config=config)
    assert bundle.code_snippets
    assert "verify_token" in bundle.code_snippets[0].text
