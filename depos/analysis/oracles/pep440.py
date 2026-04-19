"""PEP 440 matcher for Python package versions."""
from __future__ import annotations

from depos.analysis.schemas import OracleResult


def satisfies(range_spec: str, version: str) -> bool:
    try:
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version
    except Exception:
        return False
    try:
        return Version(version) in SpecifierSet(range_spec)
    except Exception:
        return False


def lookup(question: dict) -> OracleResult:
    range_spec = str(question.get("declared_range") or question.get("range") or "")
    version = str(question.get("resolved_version") or question.get("version") or "")
    if not range_spec or not version:
        return OracleResult(found=False, conclusion="insufficient_evidence", detail="missing_range_or_version", source="pep440")
    ok = satisfies(range_spec, version)
    return OracleResult(
        found=True,
        conclusion="pass" if ok else "fail",
        detail=f"{version} {'matches' if ok else 'does_not_match'} {range_spec}",
        source="pep440",
    )


__all__ = ["lookup", "satisfies"]
