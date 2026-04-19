"""JSON Schema validator oracle."""
from __future__ import annotations

from depos.analysis.schemas import OracleResult


def validate_payload(schema: dict, payload) -> OracleResult:
    try:
        import jsonschema
    except Exception:
        return OracleResult(found=False, conclusion="insufficient_evidence", detail="jsonschema_not_installed", source="json_schema")
    try:
        jsonschema.Draft202012Validator(schema).validate(payload)
    except Exception as exc:  # noqa: BLE001
        return OracleResult(found=True, conclusion="fail", detail=str(exc), source="json_schema")
    return OracleResult(found=True, conclusion="pass", detail="schema_valid", source="json_schema")


def lookup(question: dict) -> OracleResult:
    schema = question.get("schema")
    payload = question.get("payload")
    if not isinstance(schema, dict):
        return OracleResult(found=False, conclusion="insufficient_evidence", detail="missing_schema", source="json_schema")
    return validate_payload(schema, payload)


__all__ = ["lookup", "validate_payload"]
