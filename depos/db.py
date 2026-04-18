"""SQLite persistence for orgs, repos, audit (MVP)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import Float, Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(512), default="")


class Repository(Base):
    __tablename__ = "repositories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    slug: Mapped[str] = mapped_column(String(512), index=True)
    enabled_for_analysis: Mapped[bool] = mapped_column(Boolean, default=True)
    include_in_federated: Mapped[bool] = mapped_column(Boolean, default=True)
    org: Mapped[Organization] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    action: Mapped[str] = mapped_column(String(128))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CISignal(Base):
    __tablename__ = "ci_signals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_slug: Mapped[str] = mapped_column(String(512), index=True)
    head_sha: Mapped[str] = mapped_column(String(64), index=True)
    check_conclusion: Mapped[str] = mapped_column(String(32), default="")
    predicted_files: Mapped[str] = mapped_column(Text, default="[]")
    overlap_score: Mapped[float] = mapped_column(Float, default=0.0)


_engine = None
_SessionLocal = None


def get_engine(db_path: Path | None = None):
    global _engine
    if _engine is None:
        path = db_path or Path("depos-data/depos.db")
        path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{path.resolve()}", echo=False)
        Base.metadata.create_all(_engine)
    return _engine


def get_session_factory(db_path: Path | None = None):
    global _SessionLocal
    engine = get_engine(db_path)
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _SessionLocal


def get_session(db_path: Path | None = None):
    return get_session_factory(db_path)()


def init_db(engine) -> None:
    Base.metadata.create_all(engine)
