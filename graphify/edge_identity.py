"""Stable edge identity helpers and schema constants for MultiDiGraph support.

The node-link ``"key"`` field is reserved schema — it identifies a parallel edge
and must never be stored as an ordinary edge attribute.  All callers that build or
load graphs should use :func:`strip_schema_key` before passing attrs to
``G.add_edge`` so the ``key`` kwarg is never duplicated.
"""

from __future__ import annotations

import hashlib
import json as _json

SCHEMA_KEY_FIELD = "key"


def make_stable_key(
    relation: str | None,
    source_file: str | None,
    source_location: str | None,
) -> str:
    """Return a collision-safe deterministic edge key from semantic identity fields.

    Uses SHA-256 over a canonical JSON payload with explicit field names so that
    delimiter characters in field values cannot produce false collisions.  The key
    format is ``"edge:v1:<sha256hex>"``.

    Two edges with the same relation, file, and location always produce the same
    key; any difference in those three fields produces a different key.
    """
    payload = _json.dumps(
        {
            "relation": relation if relation is not None else "unknown",
            "source_file": source_file if source_file is not None else "",
            "source_location": source_location if source_location is not None else "",
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return f"edge:v1:{digest}"


def strip_schema_key(attrs: dict) -> tuple[str | None, dict]:
    """Separate the ``"key"`` schema field from edge attribute kwargs.

    Returns ``(key_value, cleaned_attrs)`` where ``cleaned_attrs`` is a new dict
    with ``SCHEMA_KEY_FIELD`` removed.  The original *attrs* dict is not mutated.

    Use before ``G.add_edge(u, v, key=key_value, **cleaned_attrs)`` to avoid
    passing ``key`` twice (once as the positional schema arg and once inside attrs).
    """
    key_val = attrs.get(SCHEMA_KEY_FIELD)
    cleaned = {k: v for k, v in attrs.items() if k != SCHEMA_KEY_FIELD}
    return key_val, cleaned
