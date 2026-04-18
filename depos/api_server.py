"""FastAPI server for depOS (CI analyze, LLM export, org CRUD)."""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select

from depos.blast import drift_edge_jaccard
from depos.db import AuditLog, Organization, Repository, get_engine, get_session
from depos.export_llm import build_llm_export
from depos.federation import merge_repo_graphs
from depos.fusion import attach_diagnostics
from depos.ownership import cross_owner_warnings, parse_codeowners
from depos.postci import correlate_ci_failure, store_signal
from depos.snapshot import build_graph_for_root, graph_to_node_link, load_graph_json, persist_graph_json

_DATA = Path(os.environ.get("DEPOS_DATA", "depos-data"))
_DATA.mkdir(parents=True, exist_ok=True)
_DB = _DATA / "depos.db"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    get_engine(_DB)
    yield


app = FastAPI(title="depOS API", version="0.1.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("DEPOS_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SnapshotRequest(BaseModel):
    root: str = Field(description="Absolute path to repo root")
    out_json: str | None = Field(None, description="Optional path to write graph.json")


class CIAnalyzeRequest(BaseModel):
    root: str
    changed_files: list[str] = Field(default_factory=list)
    sarif: dict[str, Any] | None = None
    hop_depth: int = 2
    codeowners_content: str | None = None


class PostCIRequest(BaseModel):
    repo_slug: str
    head_sha: str
    predicted_files: list[str]
    failed_paths: list[str] | None = None
    check_conclusion: str = "success"


class OrgCreate(BaseModel):
    slug: str
    name: str = ""


class RepoToggle(BaseModel):
    org_slug: str
    repo_slug: str
    enabled_for_analysis: bool = True
    include_in_federated: bool = True


@app.post("/v1/snapshot")
def snapshot(req: SnapshotRequest) -> dict[str, Any]:
    root = Path(req.root)
    if not root.is_dir():
        raise HTTPException(400, "root must be a directory")
    _, G = build_graph_for_root(root, directed=True)
    out = Path(req.out_json) if req.out_json else _DATA / "graphs" / f"{root.name}.json"
    persist_graph_json(G, out)
    return {"ok": True, "nodes": G.number_of_nodes(), "edges": G.number_of_edges(), "graph_path": str(out)}


@app.post("/v1/ci/analyze")
def ci_analyze(req: CIAnalyzeRequest) -> dict[str, Any]:
    root = Path(req.root)
    if not root.is_dir():
        raise HTTPException(400, "root must be a directory")
    _, G = build_graph_for_root(root, directed=True)
    attach_diagnostics(G, req.sarif, repo_root=root)
    export = build_llm_export(G, changed_files=req.changed_files, hop_depth=req.hop_depth)
    blast = export.blast_radius
    warnings: list[str] = []
    if req.codeowners_content and blast:
        rules = parse_codeowners(req.codeowners_content)
        files = [G.nodes[n].get("source_file", "") for n in blast.impacted_node_ids if n in G]
        warnings = cross_owner_warnings([f for f in files if f], rules, root=root)
        blast.cross_owner_warnings = warnings
    return json.loads(export.model_dump_json())


@app.post("/v1/ci/postci")
def ci_postci(req: PostCIRequest) -> dict[str, Any]:
    payload = correlate_ci_failure(
        req.predicted_files,
        req.failed_paths,
        check_conclusion=req.check_conclusion,
    )
    session = get_session(_DB)
    store_signal(session, req.repo_slug, req.head_sha, {**payload, "predicted_files": req.predicted_files})
    session.close()
    return payload


@app.post("/v1/orgs")
def create_org(body: OrgCreate) -> dict[str, Any]:
    session = get_session(_DB)
    o = Organization(slug=body.slug, name=body.name)
    session.add(o)
    session.commit()
    oid = o.id
    session.close()
    return {"id": oid, "slug": body.slug}


@app.get("/v1/orgs/{slug}/repos")
def list_repos(slug: str) -> dict[str, Any]:
    session = get_session(_DB)
    org = session.scalars(select(Organization).where(Organization.slug == slug)).first()
    if not org:
        session.close()
        raise HTTPException(404, "org not found")
    rows = session.scalars(select(Repository).where(Repository.org_id == org.id)).all()
    out = [
        {
            "slug": r.slug,
            "enabled_for_analysis": r.enabled_for_analysis,
            "include_in_federated": r.include_in_federated,
        }
        for r in rows
    ]
    session.close()
    return {"repos": out}


@app.patch("/v1/repos/toggle")
def toggle_repo(body: RepoToggle) -> dict[str, Any]:
    session = get_session(_DB)
    org = session.scalars(select(Organization).where(Organization.slug == body.org_slug)).first()
    if not org:
        session.close()
        raise HTTPException(404, "org not found")
    r = session.scalars(
        select(Repository).where(Repository.org_id == org.id, Repository.slug == body.repo_slug)
    ).first()
    if not r:
        r = Repository(org_id=org.id, slug=body.repo_slug)
        session.add(r)
    r.enabled_for_analysis = body.enabled_for_analysis
    r.include_in_federated = body.include_in_federated
    session.add(
        AuditLog(
            org_id=org.id,
            action="repo_toggle",
            detail=json.dumps(body.model_dump()),
        )
    )
    session.commit()
    session.close()
    return {"ok": True}


@app.post("/v1/federation/preview")
def federation_preview(
    repo_paths: dict[str, str],
    allowed: list[str] | None = None,
) -> dict[str, Any]:
    graphs: dict[str, Any] = {}
    for slug, p in repo_paths.items():
        if allowed and slug not in allowed:
            continue
        graphs[slug] = load_graph_json(Path(p))
    merged = merge_repo_graphs(graphs, allowed_repos=set(allowed) if allowed else None)
    return {"nodes": merged.number_of_nodes(), "edges": merged.number_of_edges(), "graph": graph_to_node_link(merged)}


@app.post("/v1/drift")
def drift(body: dict[str, Any]) -> dict[str, Any]:
    p1 = Path(body["graph_a"])
    p2 = Path(body["graph_b"])
    g1 = load_graph_json(p1)
    g2 = load_graph_json(p2)
    return {"jaccard_edges": drift_edge_jaccard(g1, g2)}


def main() -> None:
    import uvicorn

    uvicorn.run("depos.api_server:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), reload=False)


if __name__ == "__main__":
    main()
