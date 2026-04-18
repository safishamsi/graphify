"""URL normalization + matching for HTTP_CALLS_ROUTE emission.

Pure functions. Not graph-aware. Tested in isolation.

Rules (master prompt):
1. Strip ``/api`` prefix from TS calls if present.
2. Normalize dynamic segments (``{id}``, ``:id``, ``[id]``) to ``{*}``.
3. Align segments by position, not parameter name.
4. Score match confidence (1.0, 0.9, \u22120.1 for inferred method, 0.4 max for
   dynamic URL construction).
5. Edges < 0.6 confidence are NOT emitted.
6. Edges < 0.8 confidence are marked ``inferred: True``.
7. ``inferred: True`` caps verifier outcome at ``partially_confirmed``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Confidence thresholds (fixed by spec).
MIN_EMIT_CONFIDENCE = 0.6
INFERRED_THRESHOLD = 0.8
INFERRED_METHOD_PENALTY = 0.1
DYNAMIC_URL_MAX_CONFIDENCE = 0.4

# Recognize TS/FastAPI dynamic segments.
_TS_BRACE = re.compile(r"\{[^/]+\}")
_TS_COLON = re.compile(r":[A-Za-z_][A-Za-z0-9_]*")
_TS_BRACKET = re.compile(r"\[[^/\]]+\]")
_FAST_BRACE = re.compile(r"\{[^/}:]+(?::[^/}]+)?\}")


def strip_api_prefix(path: str) -> str:
    """Strip a single leading ``/api`` (or ``/api/``) prefix. Idempotent for
    paths that don't start with /api."""
    if not path:
        return path
    p = path
    if p.startswith("/api/"):
        return p[4:]
    if p == "/api":
        return "/"
    return p


def normalize_path(raw: str) -> str:
    """Collapse all dynamic segment styles to ``{*}`` and strip trailing
    slashes (except root)."""
    if not raw:
        return raw
    p = raw.strip()
    # Drop query / fragment.
    p = p.split("?", 1)[0].split("#", 1)[0]
    # Normalize FastAPI-style {name:converter} to {*} first, then plainer forms.
    p = _FAST_BRACE.sub("{*}", p)
    p = _TS_BRACE.sub("{*}", p)
    p = _TS_BRACKET.sub("{*}", p)
    p = _TS_COLON.sub("{*}", p)
    # Collapse double slashes.
    while "//" in p:
        p = p.replace("//", "/")
    # Strip trailing slash (but keep root).
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    return p


def segments(path: str) -> list[str]:
    p = normalize_path(path)
    if not p:
        return []
    return [seg for seg in p.split("/") if seg]


@dataclass(frozen=True)
class NormalizedRoute:
    original: str
    normalized: str
    segments: tuple[str, ...]
    method: Optional[str]


def normalize_route(
    raw: str,
    *,
    method: Optional[str] = None,
    strip_api: bool = False,
) -> NormalizedRoute:
    """Full normalization pipeline. ``strip_api=True`` on the client side
    (TS fetch); leave False for the server side (FastAPI handler)."""
    p = raw
    if strip_api:
        p = strip_api_prefix(p)
    norm = normalize_path(p)
    segs = tuple(segments(norm))
    m = method.upper() if method else None
    return NormalizedRoute(original=raw, normalized=norm, segments=segs, method=m)


@dataclass(frozen=True)
class MatchResult:
    score: float
    match_kind: str  # "exact" | "param_rename" | "dynamic_url" | "none"
    method_matched: bool
    inferred_method: bool
    emit: bool
    inferred: bool


def score_match(
    client: NormalizedRoute,
    server: NormalizedRoute,
    *,
    client_is_dynamic_url: bool = False,
    client_method_inferred: bool = False,
) -> MatchResult:
    """Score the match of a client call against a server route.

    ``client_is_dynamic_url``: the client URL was built from a template
    literal with logic (not a plain string literal). Caps score at 0.4.
    ``client_method_inferred``: the HTTP method was inferred from context,
    not declared. Applies a \u22120.1 penalty.
    """
    # Segment count must match.
    if len(client.segments) != len(server.segments):
        return MatchResult(0.0, "none", False, client_method_inferred, False, False)

    # Method compatibility.
    method_matched = True
    if client.method and server.method and client.method != server.method:
        return MatchResult(0.0, "none", False, client_method_inferred, False, False)
    if not client.method or not server.method:
        method_matched = client.method == server.method

    # Position-by-position alignment.
    exact_hits = 0
    param_hits = 0
    for cs, ss in zip(client.segments, server.segments):
        if cs == ss:
            exact_hits += 1
        elif cs == "{*}" and ss == "{*}":
            exact_hits += 1
        elif cs == "{*}" or ss == "{*}":
            # One side has a named/bracketed param, the other resolved.
            # Parameter-only rename on already-normalized paths shouldn't
            # happen (both collapse to {*}); treat as a param-position hit.
            param_hits += 1
        else:
            return MatchResult(0.0, "none", False, client_method_inferred, False, False)

    total = len(client.segments)
    if exact_hits == total:
        base = 1.0
        kind = "exact"
    elif exact_hits + param_hits == total and param_hits > 0:
        base = 0.9
        kind = "param_rename"
    else:  # pragma: no cover - unreachable given checks above
        return MatchResult(0.0, "none", False, client_method_inferred, False, False)

    if client_method_inferred:
        base -= INFERRED_METHOD_PENALTY

    if client_is_dynamic_url:
        base = min(base, DYNAMIC_URL_MAX_CONFIDENCE)
        kind = "dynamic_url"

    # Pin within [0.0, 1.0] after penalties.
    base = max(0.0, min(1.0, base))

    emit = base >= MIN_EMIT_CONFIDENCE
    inferred = base < INFERRED_THRESHOLD
    return MatchResult(
        score=round(base, 4),
        match_kind=kind,
        method_matched=method_matched,
        inferred_method=client_method_inferred,
        emit=emit,
        inferred=inferred,
    )
