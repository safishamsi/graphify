"""Shared-secret authentication for worker/internal HTTP routes."""
from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from depos.settings import internal_api_key as _internal_api_key


def internal_credentials_match(
    x_depos_internal_key: str | None,
    authorization: str | None,
) -> bool:
    """True if internal key is configured and matches (for hybrid routes)."""
    expected = _internal_api_key()
    if not expected:
        return False
    if x_depos_internal_key and secrets.compare_digest(x_depos_internal_key, expected):
        return True
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
            if secrets.compare_digest(token, expected):
                return True
    return False


def require_internal(
    x_depos_internal_key: Annotated[str | None, Header(alias="X-DepOS-Internal-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Validate internal API key from header or ``Authorization: Bearer <key>``.

    - If ``DEPOS_INTERNAL_API_KEY`` is unset, internal routes are allowed
      without credentials (local development only — do not expose publicly).
    - If the env var is set, callers must supply a matching value.
    """
    expected = _internal_api_key()
    if not expected:
        return
    if internal_credentials_match(x_depos_internal_key, authorization):
        return
    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing internal credentials "
        "(X-DepOS-Internal-Key or Authorization: Bearer <DEPOS_INTERNAL_API_KEY>).",
    )
