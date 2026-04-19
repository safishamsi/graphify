"""OpenAPI operation lookup oracle."""
from __future__ import annotations

from depos.analysis.schemas import OracleResult


def lookup(question: dict) -> OracleResult:
    registry = question.get("registry") or {}
    method = str(question.get("method") or "").upper()
    path = str(question.get("path") or "")
    if not method or not path:
        return OracleResult(found=False, conclusion="insufficient_evidence", detail="missing_method_or_path", source="openapi_lookup")
    key = f"{method} {path}"
    row = registry.get(key)
    if row is None:
        return OracleResult(found=False, conclusion="fail", detail=f"operation_not_found:{key}", source="openapi_lookup")
    return OracleResult(found=True, conclusion="pass", detail=key, source="openapi_lookup")


__all__ = ["lookup"]
