"""Postgres (Supabase) persistence for orgs, repos, audit, CI signals, and
intelligence-layer run artifacts.

Migrations in ``supabase/migrations/*.sql`` own the authoritative schema;
these SQLAlchemy models mirror that schema for read/write access from the
FastAPI backend. We deliberately do NOT call ``Base.metadata.create_all``
here — running migrations is the only legitimate way to evolve the schema.

Environment:
    DATABASE_URL   Supabase Postgres connection string (required). For local
                   development use the URL printed by ``supabase start``.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


def _uuid_column(*args, **kw) -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), *args, **kw)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(256), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    detector_policy: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = _uuid_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    org_id: Mapped[uuid.UUID] = _uuid_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = _uuid_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(32), default="member", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("role in ('owner','admin','member')", name="organization_members_role_check"),
    )


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = _uuid_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    enabled_for_analysis: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_in_federated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    org: Mapped[Organization] = relationship()

    __table_args__ = (UniqueConstraint("org_id", "slug", name="repositories_org_slug_unique"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = _uuid_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = _uuid_column(nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class CISignal(Base):
    __tablename__ = "ci_signals"

    id: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    org_id: Mapped[uuid.UUID | None] = _uuid_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    graph_snapshot_id: Mapped[uuid.UUID | None] = _uuid_column(
        ForeignKey("graph_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    repo_slug: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    head_sha: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    check_conclusion: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    predicted_files: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    overlap_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class GraphSnapshot(Base):
    __tablename__ = "graph_snapshots"

    id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = _uuid_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    repo_slug: Mapped[str] = mapped_column(String(512), nullable=False)
    git_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    byte_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[uuid.UUID | None] = _uuid_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("status in ('pending','ready','failed')", name="graph_snapshots_status_check"),
    )


class IntelligenceRun(Base):
    __tablename__ = "intelligence_runs"

    id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = _uuid_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    repo_slug: Mapped[str] = mapped_column(String(512), nullable=False)
    base_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    head_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    analysis_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    low_stitcher_coverage: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    token_estimator: Mapped[str] = mapped_column(String(64), default="chars4", nullable=False)
    ranking_phase: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    pack_manifest_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pipeline_version: Mapped[str] = mapped_column(String(64), default="0", nullable=False)
    ingest_errors: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    universes_present: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    enabled_detectors: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    reasoner_run_health: Mapped[str] = mapped_column(String(16), default="ok", nullable=False)
    reasoner_health_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reasoner_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reasoner_successes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reasoner_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reasoner_failure_breakdown: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    evidence_summary: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    bundles_built: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bundles_sent_to_reasoner: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bundles_skipped_low_evidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dataset_path_resolution: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IntelligenceFinding(Base):
    __tablename__ = "intelligence_findings"

    id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = _uuid_column(ForeignKey("intelligence_runs.id", ondelete="CASCADE"), index=True)
    trust_level: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str | None] = mapped_column(String(4), nullable=True)
    bug_type: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    affected_components: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    witness_path: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    missing_guard: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoner_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ranking_phase: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verifier_outcome: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    verifier_checks_passed: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    verifier_checks_inconclusive: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    rls_verdict: Mapped[str | None] = mapped_column(String(64), nullable=True)
    migration_state_facts: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    caveats: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    detector_name: Mapped[str] = mapped_column(String(128), default="legacy", nullable=False)
    detector_version: Mapped[str] = mapped_column(String(64), default="0", nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(64), default="0", nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class IntelligenceDetectorStat(Base):
    __tablename__ = "intelligence_detector_stats"

    run_id: Mapped[uuid.UUID] = _uuid_column(ForeignKey("intelligence_runs.id", ondelete="CASCADE"), primary_key=True)
    detector_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    detector_version: Mapped[str] = mapped_column(String(64), nullable=False)
    candidates_emitted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verified_confirmed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verified_invalid: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mean_latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    errors: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)


_engine = None
_SessionLocal = None


def _database_url() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Run Supabase locally (`supabase start`) and "
            "set DATABASE_URL to the Postgres URL (see .env.example), or use your "
            "hosted project's connection string."
        )
    scheme = urlparse(url).scheme.lower()
    if scheme in ("postgres", "postgresql") or scheme.startswith("postgresql+"):
        return url
    raise RuntimeError(
        "DATABASE_URL must be a PostgreSQL URL for Supabase (e.g. postgres://, "
        "postgresql://, or postgresql+psycopg://). See Project Settings → Database."
    )


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            _database_url(), echo=False, future=True, pool_pre_ping=True
        )
    return _engine


def get_session_factory():
    global _SessionLocal
    engine = get_engine()
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _SessionLocal


def get_session():
    return get_session_factory()()


def reset_engine_for_tests() -> None:
    """Unit tests that swap DATABASE_URL between runs call this to drop the
    cached engine/sessionmaker so the next ``get_engine()`` picks up the new
    URL."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
