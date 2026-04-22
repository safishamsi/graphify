from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from depos.analysis.config import IntelligenceConfig
from depos.ingest import ingest_all


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_ingest_all_adds_cross_universe_nodes(tmp_path: Path) -> None:
    _write(tmp_path / ".env", "APP_URL=https://example.com\n")
    _write(tmp_path / "package.json", json.dumps({"dependencies": {"react": "^18.2.0"}}, indent=2))
    _write(tmp_path / "prompts" / "auth_email.md", "---\nprovider: openai\n---\nHello {{user_name}}\n")
    _write(
        tmp_path / "openapi.json",
        json.dumps(
            {
                "openapi": "3.1.0",
                "paths": {
                    "/repos/{repo_id}": {
                        "get": {
                            "operationId": "listRepos",
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
                "components": {
                    "schemas": {
                        "Repo": {
                            "type": "object",
                            "required": ["id"],
                            "properties": {"id": {"type": "string"}},
                        }
                    }
                },
            },
            indent=2,
        ),
    )
    _write(tmp_path / "apps" / "web" / "app" / "dashboard" / "page.tsx", "export default function Page() { return process.env.APP_URL; }\n")
    _write(
        tmp_path / "apps" / "web" / "middleware.ts",
        "export const config = { matcher: '/dashboard' };\nexport function middleware() {}\n",
    )
    _write(tmp_path / "Dockerfile", "FROM node:20 AS build\nCOPY apps/web ./apps/web\n")
    _write(
        tmp_path / ".github" / "workflows" / "ci.yml",
        "jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ${{ secrets.API_TOKEN }}\n",
    )
    _write(
        tmp_path / "docker-compose.yml",
        "services:\n  web:\n    networks:\n      - appnet\n  worker:\n    depends_on:\n      - web\n    networks:\n      - appnet\n",
    )

    graph = nx.DiGraph()
    reports = ingest_all(graph, repo_root=tmp_path, config=IntelligenceConfig())

    modules = {Path(report.module.replace(".", "/")).name for report in reports}
    node_kinds = {str(attrs.get("node_kind") or "") for _, attrs in graph.nodes(data=True)}
    relations = {str(data.get("relation") or "") for _, _, data in graph.edges(data=True)}

    assert len(reports) == 6
    assert {"manifests", "env_config", "prompts", "openapi", "nextjs_routes", "infra"} <= modules
    assert {"package_dep", "env_var", "prompt_template", "openapi_operation", "next_route", "dockerfile_stage"} <= node_kinds
    assert {"DECLARES_DEP", "READS_ENV_VAR", "NEXT_ROUTE_GUARDED_BY_MIDDLEWARE", "STAGE_COPIES_PATH"} <= relations


def test_ingest_all_reports_invalid_package_lock_without_dropping_deps(tmp_path: Path) -> None:
    _write(tmp_path / "package.json", json.dumps({"dependencies": {"react": "^18.2.0"}}, indent=2))
    _write(tmp_path / "package-lock.json", "{not valid json")

    graph = nx.DiGraph()
    reports = ingest_all(graph, repo_root=tmp_path, config=IntelligenceConfig())

    manifest_report = next(report for report in reports if report.module == "depos.ingest.manifests")
    dep_nodes = [attrs for _, attrs in graph.nodes(data=True) if attrs.get("node_kind") == "package_dep"]

    assert any(error.get("kind") == "lockfile_parse_error" for error in manifest_report.errors)
    assert any(str(error.get("path") or "").endswith("package-lock.json") for error in manifest_report.errors)
    assert any(node.get("package_name") == "react" for node in dep_nodes)
