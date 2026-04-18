"""Supabase JWT verification for FastAPI.

Two paths:

- **RS256 via JWKS** (default for hosted Supabase projects): fetch the
  project's JWKS from ``${SUPABASE_URL}/auth/v1/keys`` once and cache the
  keys in memory.
- **HS256 via ``SUPABASE_JWT_SECRET``** (local ``supabase start`` and
  older projects): verify with the shared secret.

``SUPABASE_JWT_ALG`` selects the algorithm (``RS256`` default). A failed
verification returns 401; a missing header returns 401; a well-formed
token whose claims are inconsistent (expired, wrong audience, etc.)
returns 401 with a descriptive detail.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

try:  # Soft imports so ``import depos.auth`` never breaks the base package.
    import httpx
    from jose import jwt
    from jose.exceptions import JWTError
except ImportError as exc:  # pragma: no cover - triggered only if [supabase] extra missing
    raise RuntimeError(
        "depos.auth requires the [supabase] optional extra. "
        'Install with: pip install -e ".[supabase]"'
    ) from exc

from fastapi import Header, HTTPException, status


_JWKS_CACHE: dict[str, Any] = {"keys": None, "fetched_at": 0.0}
_JWKS_TTL_SECONDS = 3600


@dataclass
class AuthContext:
    """Validated Supabase JWT claims."""

    user_id: UUID
    email: Optional[str]
    raw_claims: dict[str, Any]

    @property
    def app_metadata(self) -> dict[str, Any]:
        return self.raw_claims.get("app_metadata", {}) or {}

    @property
    def user_metadata(self) -> dict[str, Any]:
        return self.raw_claims.get("user_metadata", {}) or {}


def _algorithm() -> str:
    return os.environ.get("SUPABASE_JWT_ALG", "RS256").upper()


def _audience() -> str:
    return os.environ.get("SUPABASE_JWT_AUDIENCE", "authenticated")


def _issuer() -> Optional[str]:
    base = os.environ.get("SUPABASE_URL")
    return f"{base.rstrip('/')}/auth/v1" if base else None


def _fetch_jwks() -> dict[str, Any]:
    now = time.time()
    if _JWKS_CACHE["keys"] and (now - _JWKS_CACHE["fetched_at"] < _JWKS_TTL_SECONDS):
        return _JWKS_CACHE["keys"]
    base = os.environ.get("SUPABASE_URL")
    if not base:
        raise RuntimeError("SUPABASE_URL must be set to verify RS256 JWTs via JWKS.")
    url = f"{base.rstrip('/')}/auth/v1/keys"
    resp = httpx.get(url, timeout=5.0)
    resp.raise_for_status()
    data = resp.json()
    _JWKS_CACHE["keys"] = data
    _JWKS_CACHE["fetched_at"] = now
    return data


def _verify_token(token: str) -> dict[str, Any]:
    alg = _algorithm()
    options = {"verify_aud": True, "verify_iss": bool(_issuer())}
    kwargs: dict[str, Any] = {"algorithms": [alg], "audience": _audience(), "options": options}
    if _issuer():
        kwargs["issuer"] = _issuer()

    if alg.startswith("HS"):
        secret = os.environ.get("SUPABASE_JWT_SECRET")
        if not secret:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SUPABASE_JWT_SECRET not configured for HS* algorithm.",
            )
        return jwt.decode(token, secret, **kwargs)

    # RS256 via JWKS
    try:
        return jwt.decode(token, _fetch_jwks(), **kwargs)
    except JWTError:
        # JWKS may have rotated; force-refresh once and retry.
        _JWKS_CACHE["keys"] = None
        return jwt.decode(token, _fetch_jwks(), **kwargs)


def _claims_to_context(claims: dict[str, Any]) -> AuthContext:
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token missing 'sub' claim.")
    try:
        user_id = UUID(sub)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token 'sub' is not a UUID.") from exc
    return AuthContext(user_id=user_id, email=claims.get("email"), raw_claims=claims)


def require_user(authorization: str = Header(..., alias="Authorization")) -> AuthContext:
    """FastAPI dependency: verify ``Authorization: Bearer <jwt>`` and return
    an :class:`AuthContext`. Raises 401 on any failure."""
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be 'Bearer <jwt>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = parts[1]
    try:
        claims = _verify_token(token)
    except JWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Supabase JWT: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return _claims_to_context(claims)


def maybe_user(authorization: Optional[str] = Header(None, alias="Authorization")) -> Optional[AuthContext]:
    """Soft dependency: returns ``None`` when no token is provided, but still
    raises 401 on a malformed/invalid token. Use for endpoints that tighten
    behaviour for authenticated callers without rejecting anonymous ones."""
    if not authorization:
        return None
    return require_user(authorization)
