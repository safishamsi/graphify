"""FastAPI server for depOS (CI analyze, LLM export, org CRUD).

Supabase-backed: tenant-scoped routes require a valid Supabase JWT via
``Authorization: Bearer`` and write through SQLAlchemy against the
Postgres schema defined in ``supabase/migrations/*.sql``. Internal routes
(snapshot, federation, drift) remain unauthenticated for now and rely on
network-level isolation.
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select

from depos.blast import drift_edge_jaccard
from depos.db import (
    AuditLog,
    CISignal,
    Organization,
    OrganizationMember,
    Repository,
    get_engine,
    get_session,
)
from depos.export_llm import build_llm_export
from depos.federation import merge_repo_graphs
from depos.fusion import attach_diagnostics
from depos.ownership import cross_owner_warnings, parse_codeowners
from depos.postci import correlate_ci_failure, store_signal
from depos.snapshot import build_graph_for_root, graph_to_node_link, load_graph_json, persist_graph_json

_DATA = Path(os.environ.get("DEPOS_DATA", "depos-data"))
_DATA.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Connect to Postgres (raises if DATABASE_URL missing unless
    # DEPOS_ALLOW_SQLITE_FALLBACK=1 is explicitly set).
    get_engine()
    yield


app = FastAPI(title="depOS API", version="0.2.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("DEPOS_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_auth_dependency():
    """Lazy import so the base package is importable without the
    [supabase] extra (tests that don't touch protected routes can skip
    the extra install)."""
    from depos.auth import AuthContext, require_user  # noqa: WPS433

    return require_user, AuthContext


try:
    require_user, AuthContext = _get_auth_dependency()
    _AUTH_AVAILABLE = True
except RuntimeError:  # [supabase] extra not installed
    require_user = None  # type: ignore[assignment]
    AuthContext = object  # type: ignore[assignment,misc]
    _AUTH_AVAILABLE = False


def _assert_auth_available() -> None:
    if not _AUTH_AVAILABLE:
        raise HTTPException(
            503,
            detail='Auth not configured: install with pip install -e ".[supabase]" '
            "and set SUPABASE_URL / SUPABASE_JWT_SECRET.",
        )


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

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
    org_slug: str | None = None


class OrgCreate(BaseModel):
    slug: str
    name: str = ""


class RepoToggle(BaseModel):
    org_slug: str
    repo_slug: str
    enabled_for_analysis: bool = True
    include_in_federated: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _org_by_slug(session, slug: str) -> Organization:
    org = session.scalars(select(Organization).where(Organization.slug == slug)).first()
    if not org:
        raise HTTPException(404, "org not found")
    return org


def _assert_member(session, org_id: UUID, user_id: UUID, admin_only: bool = False) -> None:
    row = session.scalars(
        select(OrganizationMember).where(
            OrganizationMember.org_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    ).first()
    if not row:
        raise HTTPException(403, "not a member of this org")
    if admin_only and row.role not in ("owner", "admin"):
        raise HTTPException(403, "admin or owner role required")


# ---------------------------------------------------------------------------
# Internal (unauthenticated) graph / analysis endpoints
# ---------------------------------------------------------------------------

@app.post("/v1/snapshot")
def snapshot(req: SnapshotRequest) -> dict[str, Any]:
    root = Path(req.root)
    if not root.is_dir():
        raise HTTPException(400, "root must be a directory")
    _, G = build_graph_for_root(root, directed=True)
    out = Path(req.out_json) if req.out_json else _DATA / "graphs" / f"{root.name}.json"
    persist_graph_json(G, out)
    return {"ok": True, "nodes": G.number_of_nodes(), "edges": G.number_of_edges(), "graph_path": str(out)}


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
    return {
        "nodes": merged.number_of_nodes(),
        "edges": merged.number_of_edges(),
        "graph": graph_to_node_link(merged),
    }


@app.post("/v1/drift")
def drift(body: dict[str, Any]) -> dict[str, Any]:
    p1 = Path(body["graph_a"])
    p2 = Path(body["graph_b"])
    g1 = load_graph_json(p1)
    g2 = load_graph_json(p2)
    return {"jaccard_edges": drift_edge_jaccard(g1, g2)}


# ---------------------------------------------------------------------------
# Tenant-scoped (authenticated) endpoints
# ---------------------------------------------------------------------------

def _auth_dep():
    """Return the require_user dep if available, otherwise a stub that
    raises 503 so protected routes still declare the dependency."""

    def stub() -> Any:
        _assert_auth_available()

    return Depends(require_user) if _AUTH_AVAILABLE else Depends(stub)


@app.post("/v1/ci/analyze")
def ci_analyze(req: CIAnalyzeRequest, user: Any = _auth_dep()) -> dict[str, Any]:
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
def ci_postci(req: PostCIRequest, user: Any = _auth_dep()) -> dict[str, Any]:
    payload = correlate_ci_failure(
        req.predicted_files,
        req.failed_paths,
        check_conclusion=req.check_conclusion,
    )
    session = get_session()
    try:
        org_id: Optional[UUID] = None
        if req.org_slug:
            org = _org_by_slug(session, req.org_slug)
            _assert_member(session, org.id, user.user_id)
            org_id = org.id
        store_signal(
            session,
            req.repo_slug,
            req.head_sha,
            {**payload, "predicted_files": req.predicted_files, "org_id": org_id},
        )
    finally:
        session.close()
    return payload


@app.post("/v1/orgs")
def create_org(body: OrgCreate, user: Any = _auth_dep()) -> dict[str, Any]:
    session = get_session()
    try:
        o = Organization(slug=body.slug, name=body.name)
        session.add(o)
        session.flush()
        # Caller becomes owner. The DB trigger handle_new_organization also
        # inserts this row via auth.uid(), but SQLAlchemy goes in as
        # service-role, so replicate it explicitly.
        session.add(OrganizationMember(org_id=o.id, user_id=user.user_id, role="owner"))
        session.add(
            AuditLog(org_id=o.id, actor_user_id=user.user_id, action="org_create", detail={"slug": body.slug})
        )
        session.commit()
        oid = o.id
    finally:
        session.close()
    return {"id": str(oid), "slug": body.slug}


@app.get("/v1/orgs/{slug}/repos")
def list_repos(slug: str, user: Any = _auth_dep()) -> dict[str, Any]:
    session = get_session()
    try:
        org = _org_by_slug(session, slug)
        _assert_member(session, org.id, user.user_id)
        rows = session.scalars(select(Repository).where(Repository.org_id == org.id)).all()
        out = [
            {
                "slug": r.slug,
                "enabled_for_analysis": r.enabled_for_analysis,
                "include_in_federated": r.include_in_federated,
            }
            for r in rows
        ]
    finally:
        session.close()
    return {"repos": out}


@app.patch("/v1/repos/toggle")
def toggle_repo(body: RepoToggle, user: Any = _auth_dep()) -> dict[str, Any]:
    session = get_session()
    try:
        org = _org_by_slug(session, body.org_slug)
        _assert_member(session, org.id, user.user_id, admin_only=True)
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
                actor_user_id=user.user_id,
                action="repo_toggle",
                detail=body.model_dump(),
            )
        )
        session.commit()
    finally:
        session.close()
    return {"ok": True}


@app.get("/v1/me")
def me(user: Any = _auth_dep()) -> dict[str, Any]:
    """Quick auth sanity-check endpoint for the UI."""
    session = get_session()
    try:
        memberships = session.scalars(
            select(OrganizationMember).where(OrganizationMember.user_id == user.user_id)
        ).all()
        orgs = session.scalars(
            select(Organization).where(Organization.id.in_([m.org_id for m in memberships]))
        ).all() if memberships else []
        orgs_by_id = {o.id: o for o in orgs}
    finally:
        session.close()
    return {
        "user_id": str(user.user_id),
        "email": getattr(user, "email", None),
        "memberships": [
            {"org_slug": orgs_by_id[m.org_id].slug if m.org_id in orgs_by_id else None, "role": m.role}
            for m in memberships
        ],
    }


def main() -> None:
    import uvicorn

    uvicorn.run("depos.api_server:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), reload=False)


if __name__ == "__main__":
    main()
