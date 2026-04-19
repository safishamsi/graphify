"""Small semver matcher for detector verification."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from depos.analysis.schemas import OracleResult


@dataclass(frozen=True, order=True)
class _Version:
    major: int
    minor: int
    patch: int


def _parse(version: str) -> _Version | None:
    try:
        core = version.strip().split("-", 1)[0].split("+", 1)[0]
        parts = [int(piece) for piece in core.split(".")]
    except ValueError:
        return None
    while len(parts) < 3:
        parts.append(0)
    return _Version(*parts[:3])


def _match_one(spec: str, version: _Version) -> bool:
    spec = spec.strip()
    if not spec or spec == "*":
        return True
    if spec.startswith("^"):
        base = _parse(spec[1:])
        return base is not None and version >= base and version < _Version(base.major + 1, 0, 0)
    if spec.startswith("~"):
        base = _parse(spec[1:])
        return base is not None and version >= base and version < _Version(base.major, base.minor + 1, 0)
    for prefix, op in ((">=", lambda a, b: a >= b), ("<=", lambda a, b: a <= b), (">", lambda a, b: a > b), ("<", lambda a, b: a < b)):
        if spec.startswith(prefix):
            base = _parse(spec[len(prefix) :])
            return base is not None and op(version, base)
    if spec.startswith("="):
        base = _parse(spec[1:])
        return base is not None and version == base
    base = _parse(spec)
    return base is not None and version == base


def satisfies(range_spec: str, version: str) -> bool:
    parsed = _parse(version)
    if parsed is None:
        return False
    parts = [piece.strip() for piece in range_spec.replace("||", ",").split(",") if piece.strip()]
    if not parts:
        return True
    return all(_match_one(piece, parsed) for piece in parts)


def lookup(question: dict) -> OracleResult:
    range_spec = str(question.get("declared_range") or question.get("range") or "")
    version = str(question.get("resolved_version") or question.get("version") or "")
    if not range_spec or not version:
        return OracleResult(found=False, conclusion="insufficient_evidence", detail="missing_range_or_version", source="semver")
    ok = satisfies(range_spec, version)
    return OracleResult(
        found=True,
        conclusion="pass" if ok else "fail",
        detail=f"{version} {'matches' if ok else 'does_not_match'} {range_spec}",
        source="semver",
    )


__all__ = ["lookup", "satisfies"]
