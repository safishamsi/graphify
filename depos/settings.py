"""Process-wide depOS API settings from environment."""
from __future__ import annotations

import os


def is_production() -> bool:
    return os.environ.get("DEPOS_ENV", "").strip().lower() == "production"


def internal_api_key() -> str | None:
    v = os.environ.get("DEPOS_INTERNAL_API_KEY", "").strip()
    return v or None


def cors_allow_origins() -> list[str]:
    raw = os.environ.get("DEPOS_CORS_ORIGINS")
    if raw is None:
        return ["*"] if not is_production() else []
    raw = raw.strip()
    if not raw:
        return ["*"] if not is_production() else []
    return [o.strip() for o in raw.split(",") if o.strip()]


def validate_production_config() -> None:
    """Raise RuntimeError if production env is inconsistent."""
    if not is_production():
        return
    if not internal_api_key():
        raise RuntimeError(
            "DEPOS_ENV=production requires DEPOS_INTERNAL_API_KEY to be set "
            "(protects /v1/snapshot, /v1/federation/preview, /v1/drift)."
        )
    origins = cors_allow_origins()
    if not origins or origins == ["*"]:
        raise RuntimeError(
            "DEPOS_ENV=production requires DEPOS_CORS_ORIGINS to be an explicit "
            "comma-separated list (not empty and not *)."
        )
    bucket = os.environ.get("DEPOS_GRAPH_BUCKET", "").strip()
    if not bucket:
        raise RuntimeError(
            "DEPOS_ENV=production requires DEPOS_GRAPH_BUCKET for graph snapshot storage."
        )
