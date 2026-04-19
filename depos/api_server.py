"""FastAPI server for depOS (CI analyze, LLM export, org CRUD).

Tenant routes use Supabase JWT (``Authorization: Bearer``). Internal worker
routes ``/v1/snapshot``, ``/v1/federation/preview``, ``/v1/drift`` require
``DEPOS_INTERNAL_API_KEY`` when set. Production requires that key, explicit
CORS, and ``DEPOS_GRAPH_BUCKET`` — see ``depos.settings.validate_production_config``.
"""
from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import desc, select, text

from depos.blast import drift_edge_jaccard
from depos.db import (
    AuditLog,
    CISignal,
    GraphSnapshot,
    IntelligenceDetectorStat,
    IntelligenceFinding,
    IntelligenceRun,
    Organization,
    OrganizationMember,
    Repository,
    get_engine,
    get_session,
)
from depos.export_llm import build_llm_export
from depos.federation import merge_repo_graphs
from depos.fusion import attach_diagnostics
from depos.internal_auth import internal_credentials_match, require_internal
from depos.intelligence_store import persist_intelligence_run
from depos.ownership import cross_owner_warnings, parse_codeowners
from depos.postci import correlate_ci_failure, store_signal
from depos.settings import cors_allow_origins, validate_production_config
from depos.snapshot import (
    build_graph_for_root,
    graph_to_node_link,
    load_graph_json,
    load_graph_json_from_dict,
    persist_graph_json,
)

_DATA = Path(os.environ.get("DEPOS_DATA", "depos-data"))
_DATA.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    validate_production_config()
    get_engine()
    yield


app = FastAPI(title="depOS API", version="0.3.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


def _get_auth_dependency():
    from depos.auth import AuthContext, require_user  # noqa: WPS433

    return require_user, AuthContext


try:
    require_user, AuthContext = _get_auth_dependency()
    _AUTH_AVAILABLE = True
except RuntimeError:
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


def _auth_dep():
    def stub() -> Any:
        _assert_auth_available()

    return Depends(require_user) if _AUTH_AVAILABLE else Depends(stub)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class SnapshotRequest(BaseModel):
    root: str = Field(description="Absolute path to repo root")
    out_json: str | None = Field(None, description="Optional path to write graph.json")


class GraphSnapshotPrepareBody(BaseModel):
    repo_slug: str
    git_sha: str = Field(min_length=7, max_length=64)


class GraphSnapshotCompleteBody(BaseModel):
    expected_sha256: str | None = Field(None, description="If set, must match uploaded bytes")


class CIAnalyzeRequest(BaseModel):
    org_slug: str
    repo_slug: str
    graph_snapshot_id: UUID | None = None
    root: str | None = Field(
        None,
        description="Server-local checkout; only with X-DepOS-Internal-Key matching DEPOS_INTERNAL_API_KEY",
    )
    changed_files: list[str] = Field(default_factory=list)
    sarif: dict[str, Any] | None = None
    hop_depth: int = 2
    codeowners_content: str | None = None

    @model_validator(mode="after")
    def _graph_source(self) -> "CIAnalyzeRequest":
        has_root = bool(self.root and str(self.root).strip())
        if not has_root and self.graph_snapshot_id is None:
            raise ValueError("graph_snapshot_id is required unless root is provided for internal workers")
        return self


class PostCIRequest(BaseModel):
    repo_slug: str
    head_sha: str
    predicted_files: list[str]
    failed_paths: list[str] | None = None
    check_conclusion: str = "success"
    org_slug: str | None = None
    graph_snapshot_id: UUID | None = None


class OrgCreate(BaseModel):
    slug: str
    name: str = ""


class RepoToggle(BaseModel):
    org_slug: str
    repo_slug: str
    enabled_for_analysis: bool = True
    include_in_federated: bool = True


class FederationSnapshotsBody(BaseModel):
    org_slug: str
    snapshot_ids: dict[str, str] = Field(description="repo_slug -> graph_snapshots.id")
    allowed: list[str] | None = None


class DriftSnapshotsBody(BaseModel):
    org_slug: str
    graph_a_snapshot_id: UUID
    graph_b_snapshot_id: UUID


class IntelligenceFindingIn(BaseModel):
    trust_level: Literal["confirmed", "partially_confirmed", "evaluator_surfaced"]
    mode: Literal["A", "B", "C"] | None = None
    bug_type: str = ""
    description: str = ""
    affected_components: list[Any] = Field(default_factory=list)
    witness_path: list[Any] = Field(default_factory=list)
    missing_guard: str | None = None
    recommended_fix: str | None = None
    reasoner_confidence: float = 0.0
    ranking_phase: int = 0
    verifier_outcome: str = ""
    verifier_checks_passed: list[Any] = Field(default_factory=list)
    verifier_checks_inconclusive: list[Any] = Field(default_factory=list)
    rls_verdict: str | None = None
    migration_state_facts: dict[str, Any] = Field(default_factory=dict)
    caveats: dict[str, Any] = Field(default_factory=dict)
    detector_name: str = "legacy"
    detector_version: str = "0"
    pipeline_version: str = "0"
    severity: Literal["info", "low", "medium", "high", "critical"] = "medium"


class IntelligenceDetectorStatIn(BaseModel):
    detector_name: str
    detector_version: str
    candidates_emitted: int = 0
    verified_confirmed: int = 0
    verified_invalid: int = 0
    mean_latency_ms: float = 0.0
    errors: list[Any] = Field(default_factory=list)


class IntelligenceRunCreate(BaseModel):
    repo_slug: str
    base_ref: str | None = None
    head_ref: str | None = None
    analysis_mode: Literal["diff_aware", "full_repo_scan"]
    provider: str | None = None
    low_stitcher_coverage: bool = False
    token_estimator: str = "chars4"
    ranking_phase: int = 0
    status: Literal["running", "succeeded", "partial_reasoning", "failed"] = "succeeded"
    pack_manifest_id: str | None = None
    pipeline_version: str = "0"
    ingest_errors: list[Any] = Field(default_factory=list)
    universes_present: list[Any] = Field(default_factory=list)
    enabled_detectors: list[str] = Field(default_factory=list)
    detector_policy: dict[str, Any] | None = None
    detector_stats: list[IntelligenceDetectorStatIn] = Field(default_factory=list)
    findings: list[IntelligenceFindingIn] = Field(default_factory=list)
    # Reasoner health surfaced from RunMetadata. Optional so older callers
    # keep working; defaults below match a clean run.
    reasoner_run_health: Literal["ok", "degraded", "failed"] = "ok"
    reasoner_health_reason: str = ""
    reasoner_attempts: int = 0
    reasoner_successes: int = 0
    reasoner_failures: int = 0
    reasoner_failure_breakdown: dict[str, Any] = Field(default_factory=dict)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    bundles_built: int = 0
    bundles_sent_to_reasoner: int = 0
    bundles_skipped_low_evidence: int = 0
    dataset_path_resolution: dict[str, Any] = Field(default_factory=dict)


class DetectorPolicyBody(BaseModel):
    enabled: list[str] = Field(default_factory=list)
    disabled: list[str] = Field(default_factory=list)
    severity_overrides: dict[str, str] = Field(default_factory=dict)


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


def _internal_ok(request: Request) -> bool:
    return internal_credentials_match(
        request.headers.get("X-DepOS-Internal-Key"),
        request.headers.get("Authorization"),
    )


def _load_snapshots_graphs(
    session,
    org_id: UUID,
    user_id: UUID,
    snapshot_ids: dict[str, str],
) -> dict[str, Any]:
    _assert_member(session, org_id, user_id)
    graphs: dict[str, Any] = {}
    from depos.graph_storage import download_graph_json_bytes

    for repo_slug, sid in snapshot_ids.items():
        try:
            uid = UUID(str(sid))
        except ValueError as exc:
            raise HTTPException(400, f"invalid snapshot id for {repo_slug}") from exc
        snap = session.scalars(
            select(GraphSnapshot).where(
                GraphSnapshot.id == uid,
                GraphSnapshot.org_id == org_id,
                GraphSnapshot.status == "ready",
            )
        ).first()
        if not snap:
            raise HTTPException(404, f"snapshot not found or not ready: {repo_slug}")
        raw = download_graph_json_bytes(snap.storage_path)
        graphs[repo_slug] = load_graph_json_from_dict(json.loads(raw.decode("utf-8")))
    return graphs


# ---------------------------------------------------------------------------
# Health (public)
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, Any]:
    session = get_session()
    try:
        session.execute(text("SELECT 1"))
    finally:
        session.close()
    out: dict[str, Any] = {"status": "ready", "database": True}
    try:
        from depos.graph_storage import storage_bucket_configured, verify_bucket_exists

        if storage_bucket_configured():
            out["storage"] = verify_bucket_exists()
        else:
            out["storage"] = None
    except Exception:
        out["storage"] = None
    return out


# ---------------------------------------------------------------------------
# Internal graph / analysis endpoints (paths on server)
# ---------------------------------------------------------------------------


@app.post("/v1/snapshot", dependencies=[Depends(require_internal)])
def snapshot(req: SnapshotRequest) -> dict[str, Any]:
    root = Path(req.root)
    if not root.is_dir():
        raise HTTPException(400, "root must be a directory")
    _, G = build_graph_for_root(root, directed=True)
    out = Path(req.out_json) if req.out_json else _DATA / "graphs" / f"{root.name}.json"
    persist_graph_json(G, out)
    return {"ok": True, "nodes": G.number_of_nodes(), "edges": G.number_of_edges(), "graph_path": str(out)}


@app.post("/v1/federation/preview", dependencies=[Depends(require_internal)])
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


@app.post("/v1/drift", dependencies=[Depends(require_internal)])
def drift(body: dict[str, Any]) -> dict[str, Any]:
    p1 = Path(body["graph_a"])
    p2 = Path(body["graph_b"])
    g1 = load_graph_json(p1)
    g2 = load_graph_json(p2)
    return {"jaccard_edges": drift_edge_jaccard(g1, g2)}


# ---------------------------------------------------------------------------
# Tenant federation / drift (snapshots in Storage)
# ---------------------------------------------------------------------------


@app.post("/v1/federation/snapshots")
def federation_snapshots(body: FederationSnapshotsBody, user: Any = _auth_dep()) -> dict[str, Any]:
    _assert_auth_available()
    session = get_session()
    try:
        org = _org_by_slug(session, body.org_slug)
        graphs = _load_snapshots_graphs(session, org.id, user.user_id, body.snapshot_ids)
        merged = merge_repo_graphs(graphs, allowed_repos=set(body.allowed) if body.allowed else None)
        return {
            "nodes": merged.number_of_nodes(),
            "edges": merged.number_of_edges(),
            "graph": graph_to_node_link(merged),
        }
    finally:
        session.close()


@app.post("/v1/drift/snapshots")
def drift_snapshots(body: DriftSnapshotsBody, user: Any = _auth_dep()) -> dict[str, Any]:
    _assert_auth_available()
    session = get_session()
    try:
        org = _org_by_slug(session, body.org_slug)
        _assert_member(session, org.id, user.user_id)
        from depos.graph_storage import download_graph_json_bytes

        def _load_one(snap_id: UUID):
            snap = session.scalars(
                select(GraphSnapshot).where(
                    GraphSnapshot.id == snap_id,
                    GraphSnapshot.org_id == org.id,
                    GraphSnapshot.status == "ready",
                )
            ).first()
            if not snap:
                raise HTTPException(404, "snapshot not found or not ready")
            raw = download_graph_json_bytes(snap.storage_path)
            return load_graph_json_from_dict(json.loads(raw.decode("utf-8")))

        g1 = _load_one(body.graph_a_snapshot_id)
        g2 = _load_one(body.graph_b_snapshot_id)
        return {"jaccard_edges": drift_edge_jaccard(g1, g2)}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Graph snapshots (prepare / complete)
# ---------------------------------------------------------------------------


@app.post("/v1/orgs/{slug}/graph-snapshots/prepare")
def graph_snapshot_prepare(
    slug: str,
    body: GraphSnapshotPrepareBody,
    user: Any = _auth_dep(),
) -> dict[str, Any]:
    _assert_auth_available()
    from depos.graph_storage import create_signed_upload, graph_bucket

    session = get_session()
    try:
        org = _org_by_slug(session, slug)
        _assert_member(session, org.id, user.user_id)
        repo = session.scalars(
            select(Repository).where(Repository.org_id == org.id, Repository.slug == body.repo_slug)
        ).first()
        if not repo or not repo.enabled_for_analysis:
            raise HTTPException(403, "repository not found or analysis disabled")
        sid = uuid.uuid4()
        storage_path = f"{org.id}/{body.repo_slug}/{body.git_sha}/{sid}.json"
        row = GraphSnapshot(
            id=sid,
            org_id=org.id,
            repo_slug=body.repo_slug,
            git_sha=body.git_sha,
            storage_path=storage_path,
            status="pending",
            created_by=user.user_id,
        )
        session.add(row)
        session.commit()
        signed = create_signed_upload(storage_path)
        return {
            "snapshot_id": str(sid),
            "storage_path": storage_path,
            "bucket": graph_bucket(),
            "signed_url": signed.get("signed_url") or signed.get("signedUrl"),
            "token": signed.get("token"),
            "path": signed.get("path"),
        }
    finally:
        session.close()


@app.post("/v1/orgs/{slug}/graph-snapshots/{snapshot_id}/complete")
def graph_snapshot_complete(
    slug: str,
    snapshot_id: UUID,
    body: GraphSnapshotCompleteBody,
    user: Any = _auth_dep(),
) -> dict[str, Any]:
    _assert_auth_available()
    from depos.graph_storage import download_graph_json_bytes, verify_node_link_json

    session = get_session()
    try:
        org = _org_by_slug(session, slug)
        _assert_member(session, org.id, user.user_id)
        row = session.scalars(
            select(GraphSnapshot).where(GraphSnapshot.id == snapshot_id, GraphSnapshot.org_id == org.id)
        ).first()
        if not row:
            raise HTTPException(404, "snapshot not found")
        if row.status != "pending":
            raise HTTPException(409, f"snapshot status is {row.status}, expected pending")
        try:
            raw = download_graph_json_bytes(row.storage_path)
        except Exception as exc:
            row.status = "failed"
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            raise HTTPException(400, f"could not read uploaded object: {exc}") from exc
        try:
            byte_size, sha = verify_node_link_json(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            row.status = "failed"
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            raise HTTPException(400, f"invalid graph json: {exc}") from exc
        if body.expected_sha256 and body.expected_sha256.lower() != sha.lower():
            row.status = "failed"
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            raise HTTPException(400, "sha256 mismatch")
        row.byte_size = byte_size
        row.content_sha256 = sha
        row.status = "ready"
        row.updated_at = datetime.now(timezone.utc)
        session.commit()
        return {"ok": True, "snapshot_id": str(row.id), "byte_size": byte_size, "content_sha256": sha}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Tenant-scoped (authenticated) endpoints
# ---------------------------------------------------------------------------


@app.post("/v1/ci/analyze")
def ci_analyze(req: CIAnalyzeRequest, request: Request, user: Any = _auth_dep()) -> dict[str, Any]:
    internal = _internal_ok(request)
    has_root = bool(req.root and str(req.root).strip())

    if has_root and not internal:
        raise HTTPException(
            403,
            detail="Using 'root' requires internal credentials (X-DepOS-Internal-Key or Bearer internal key).",
        )

    session = get_session()
    try:
        org = _org_by_slug(session, req.org_slug)
        _assert_member(session, org.id, user.user_id)
        repo = session.scalars(
            select(Repository).where(Repository.org_id == org.id, Repository.slug == req.repo_slug)
        ).first()
        if not repo or not repo.enabled_for_analysis:
            raise HTTPException(403, "repository not found or analysis disabled for this repo")
        org_id = org.id
    finally:
        session.close()

    if has_root and internal:
        root = Path(req.root)  # type: ignore[arg-type]
        if not root.is_dir():
            raise HTTPException(400, "root must be a directory")
        _, G = build_graph_for_root(root, directed=True)
    else:
        assert req.graph_snapshot_id is not None
        session = get_session()
        try:
            snap = session.scalars(
                select(GraphSnapshot).where(
                    GraphSnapshot.id == req.graph_snapshot_id,
                    GraphSnapshot.org_id == org_id,
                    GraphSnapshot.status == "ready",
                )
            ).first()
            if not snap:
                raise HTTPException(404, "graph snapshot not found or not ready")
        finally:
            session.close()
        from depos.graph_storage import download_graph_json_bytes

        raw = download_graph_json_bytes(snap.storage_path)
        G = load_graph_json_from_dict(json.loads(raw.decode("utf-8")))
        root = Path(".")

    attach_diagnostics(G, req.sarif, repo_root=root)
    export = build_llm_export(G, changed_files=req.changed_files, hop_depth=req.hop_depth)
    blast = export.blast_radius
    warnings: list[str] = []
    if req.codeowners_content and blast and has_root and internal:
        rules = parse_codeowners(req.codeowners_content)
        files = [G.nodes[n].get("source_file", "") for n in blast.impacted_node_ids if n in G]
        warnings = cross_owner_warnings([f for f in files if f], rules, root=root)
        blast.cross_owner_warnings = warnings
    elif req.codeowners_content and blast:
        blast.cross_owner_warnings = []
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
        if req.graph_snapshot_id is not None and org_id is not None:
            snap = session.scalars(
                select(GraphSnapshot).where(
                    GraphSnapshot.id == req.graph_snapshot_id,
                    GraphSnapshot.org_id == org_id,
                )
            ).first()
            if not snap:
                raise HTTPException(404, "graph snapshot not found for org")
        store_signal(
            session,
            req.repo_slug,
            req.head_sha,
            {
                **payload,
                "predicted_files": req.predicted_files,
                "org_id": org_id,
                "graph_snapshot_id": req.graph_snapshot_id,
            },
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
    session = get_session()
    try:
        memberships = session.scalars(
            select(OrganizationMember).where(OrganizationMember.user_id == user.user_id)
        ).all()
        orgs = (
            session.scalars(select(Organization).where(Organization.id.in_([m.org_id for m in memberships]))).all()
            if memberships
            else []
        )
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


# ---------------------------------------------------------------------------
# Intelligence runs (persist + list)
# ---------------------------------------------------------------------------


@app.post("/v1/orgs/{slug}/intelligence/runs")
def create_intelligence_run(slug: str, body: IntelligenceRunCreate, user: Any = _auth_dep()) -> dict[str, Any]:
    session = get_session()
    try:
        org = _org_by_slug(session, slug)
        _assert_member(session, org.id, user.user_id, admin_only=True)
        if body.detector_policy is not None:
            org.detector_policy = dict(body.detector_policy)
        run = persist_intelligence_run(session, org_id=org.id, body=body)
        session.commit()
        return {"run_id": str(run.id), "findings": len(body.findings)}
    finally:
        session.close()


@app.get("/v1/orgs/{slug}/intelligence/runs")
def list_intelligence_runs(slug: str, user: Any = _auth_dep()) -> dict[str, Any]:
    session = get_session()
    try:
        org = _org_by_slug(session, slug)
        _assert_member(session, org.id, user.user_id)
        rows = session.scalars(
            select(IntelligenceRun)
            .where(IntelligenceRun.org_id == org.id)
            .order_by(desc(IntelligenceRun.started_at))
            .limit(100)
        ).all()
        return {
            "runs": [
                {
                    "id": str(r.id),
                    "repo_slug": r.repo_slug,
                    "status": r.status,
                    "analysis_mode": r.analysis_mode,
                    "pipeline_version": r.pipeline_version,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                }
                for r in rows
            ]
        }
    finally:
        session.close()


@app.get("/v1/orgs/{slug}/intelligence/runs/{run_id}")
def get_intelligence_run(slug: str, run_id: UUID, user: Any = _auth_dep()) -> dict[str, Any]:
    session = get_session()
    try:
        org = _org_by_slug(session, slug)
        _assert_member(session, org.id, user.user_id)
        run = session.scalars(
            select(IntelligenceRun).where(IntelligenceRun.id == run_id, IntelligenceRun.org_id == org.id)
        ).first()
        if not run:
            raise HTTPException(404, "run not found")
        findings = session.scalars(select(IntelligenceFinding).where(IntelligenceFinding.run_id == run.id)).all()
        stats = session.scalars(select(IntelligenceDetectorStat).where(IntelligenceDetectorStat.run_id == run.id)).all()
        return {
            "run": {
                "id": str(run.id),
                "repo_slug": run.repo_slug,
                "base_ref": run.base_ref,
                "head_ref": run.head_ref,
                "analysis_mode": run.analysis_mode,
                "provider": run.provider,
                "status": run.status,
                "pipeline_version": run.pipeline_version,
                "enabled_detectors": run.enabled_detectors,
                "universes_present": run.universes_present,
                "ingest_errors": run.ingest_errors,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            },
            "detector_stats": [
                {
                    "detector_name": row.detector_name,
                    "detector_version": row.detector_version,
                    "candidates_emitted": row.candidates_emitted,
                    "verified_confirmed": row.verified_confirmed,
                    "verified_invalid": row.verified_invalid,
                    "mean_latency_ms": row.mean_latency_ms,
                    "errors": row.errors,
                }
                for row in stats
            ],
            "findings": [
                {
                    "id": str(f.id),
                    "trust_level": f.trust_level,
                    "mode": f.mode,
                    "bug_type": f.bug_type,
                    "description": f.description,
                    "affected_components": f.affected_components,
                    "witness_path": f.witness_path,
                    "detector_name": f.detector_name,
                    "detector_version": f.detector_version,
                    "pipeline_version": f.pipeline_version,
                    "severity": f.severity,
                    "verifier_outcome": f.verifier_outcome,
                    "reasoner_confidence": f.reasoner_confidence,
                }
                for f in findings
            ],
        }
    finally:
        session.close()


@app.get("/v1/orgs/{slug}/intelligence/detectors")
def list_detector_registry(slug: str, user: Any = _auth_dep()) -> dict[str, Any]:
    from depos.analysis.detectors import list_detectors, load_builtin

    load_builtin()
    session = get_session()
    try:
        org = _org_by_slug(session, slug)
        _assert_member(session, org.id, user.user_id)
        return {
            "policy": org.detector_policy,
            "detectors": [spec.model_dump(mode="json") for spec in sorted(list_detectors(), key=lambda row: row.name)],
        }
    finally:
        session.close()


@app.put("/v1/orgs/{slug}/intelligence/detectors/policy")
def update_detector_policy(slug: str, body: DetectorPolicyBody, user: Any = _auth_dep()) -> dict[str, Any]:
    session = get_session()
    try:
        org = _org_by_slug(session, slug)
        _assert_member(session, org.id, user.user_id, admin_only=True)
        org.detector_policy = body.model_dump(mode="json")
        session.add(
            AuditLog(
                org_id=org.id,
                actor_user_id=user.user_id,
                action="detector_policy_update",
                detail=body.model_dump(mode="json"),
            )
        )
        session.commit()
        return {"ok": True, "policy": org.detector_policy}
    finally:
        session.close()


def main() -> None:
    import uvicorn

    uvicorn.run("depos.api_server:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), reload=False)


if __name__ == "__main__":
    main()
