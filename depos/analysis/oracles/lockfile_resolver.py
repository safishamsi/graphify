"""Declared-vs-resolved version oracle."""
from __future__ import annotations

from depos.analysis.oracles.pep440 import satisfies as pep440_satisfies
from depos.analysis.oracles.semver import satisfies as semver_satisfies
from depos.analysis.schemas import OracleResult


def lookup(question: dict) -> OracleResult:
    declared_range = str(question.get("declared_range") or "")
    resolved_version = str(question.get("resolved_version") or "")
    if not declared_range or not resolved_version:
        return OracleResult(found=False, conclusion="insufficient_evidence", detail="missing_range_or_version", source="lockfile_resolver")
    ok = pep440_satisfies(declared_range, resolved_version) or semver_satisfies(declared_range, resolved_version)
    return OracleResult(
        found=True,
        conclusion="pass" if ok else "fail",
        detail=f"{resolved_version} {'matches' if ok else 'does_not_match'} {declared_range}",
        source="lockfile_resolver",
    )


__all__ = ["lookup"]
