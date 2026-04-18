from __future__ import annotations

from pathlib import Path

import networkx as nx

from depos.analysis.config import IntelligenceConfig
from depos.enrichment.semantic_edges import PRODUCES_PAYLOAD, ROUTE_GUARDED_BY_RLS, enrich_graph


def test_enrich_graph_uses_repo_root_for_relative_python_and_migrations(tmp_path: Path) -> None:
    worker_path = tmp_path / "apps" / "worker" / "tasks.py"
    route_path = tmp_path / "backend" / "routers" / "repos.py"
    migration_path = tmp_path / "supabase" / "migrations" / "20260418010101_init.sql"

    worker_path.parent.mkdir(parents=True, exist_ok=True)
    route_path.parent.mkdir(parents=True, exist_ok=True)
    migration_path.parent.mkdir(parents=True, exist_ok=True)

    worker_path.write_text(
        "@shared_task\n"
        "def sync_repo(repo_id, force=False):\n"
        "    return repo_id\n\n"
        "def enqueue_sync():\n"
        "    sync_repo.delay(repo_id=1)\n",
        encoding="utf-8",
    )
    route_path.write_text(
        "from fastapi import APIRouter\n\n"
        "router = APIRouter()\n\n"
        "@router.get('/repos/{repo_id}')\n"
        "def list_repos(repo_id: int):\n"
        "    sql = 'select * from repos where id = 1'\n"
        "    return {'id': repo_id}\n",
        encoding="utf-8",
    )
    migration_path.write_text(
        "create table public.repos(id bigint primary key);\n"
        "alter table public.repos enable row level security;\n"
        "create policy repos_select on repos for select using (true);\n",
        encoding="utf-8",
    )

    graph = nx.DiGraph()
    graph.add_node("py:worker:task", label="sync_repo()", source_file="apps/worker/tasks.py")
    graph.add_node("py:worker:file", label="tasks.py", source_file="apps/worker/tasks.py")
    graph.add_node("py:route:list", label="list_repos()", source_file="backend/routers/repos.py")

    config = IntelligenceConfig(migration_glob="supabase/migrations/*.sql")
    enriched, coverage = enrich_graph(graph, config=config, repo_root=tmp_path)

    payload_edges = [
        (u, v, data)
        for u, v, data in enriched.edges(data=True)
        if data.get("relation") == PRODUCES_PAYLOAD
    ]
    rls_edges = [
        (u, v, data)
        for u, v, data in enriched.edges(data=True)
        if data.get("relation") == ROUTE_GUARDED_BY_RLS
    ]

    assert payload_edges, "expected Celery payload edges to be emitted from relative source paths"
    assert rls_edges, "expected RLS edges to be emitted from relative source paths"
    assert coverage.migration_files_found == 1
