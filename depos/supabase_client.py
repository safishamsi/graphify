"""Supabase client factories.

- :func:`service_client` — uses ``SUPABASE_SERVICE_ROLE_KEY``; bypasses RLS.
  For snapshot, federation, and intelligence-run writes from the backend.
- :func:`user_client` — uses ``SUPABASE_ANON_KEY`` and injects the caller's
  JWT via PostgREST auth; RLS enforced as the authenticated user.

Both raise :class:`RuntimeError` if the corresponding env var is missing,
so the FastAPI route handler fails fast rather than silently degrading
to anonymous access.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

try:
    from supabase import Client, create_client
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "depos.supabase_client requires the [supabase] optional extra. "
        'Install with: pip install -e ".[supabase]"'
    ) from exc


def _supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL")
    if not url:
        raise RuntimeError("SUPABASE_URL is not set.")
    return url


@lru_cache(maxsize=1)
def service_client() -> Client:
    """Cached service-role client. Bypasses RLS — use only for server-side
    operations that do not have a per-user context (Celery workers,
    federation runs, snapshot writes)."""
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not set.")
    return create_client(_supabase_url(), key)


def user_client(jwt: Optional[str]) -> Client:
    """Anon-key client with the caller's JWT installed, so PostgREST
    evaluates RLS as the user. Pass the raw access token (no ``Bearer``
    prefix). ``None`` returns an unauthenticated anon-key client."""
    key = os.environ.get("SUPABASE_ANON_KEY")
    if not key:
        raise RuntimeError("SUPABASE_ANON_KEY is not set.")
    client = create_client(_supabase_url(), key)
    if jwt:
        # Supabase-py sets PostgREST auth for subsequent `.from_(...)` calls.
        client.postgrest.auth(jwt)
    return client
