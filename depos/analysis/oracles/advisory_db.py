"""File-backed advisory snapshot lookup."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from depos.analysis.schemas import OracleResult


@lru_cache(maxsize=1)
def _load_rows(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    if p.suffix == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        return []
    rows: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def lookup(question: dict) -> OracleResult:
    path = str(question.get("snapshot_path") or "data/advisories/advisories.jsonl")
    ecosystem = str(question.get("ecosystem") or "")
    name = str(question.get("name") or "")
    version = str(question.get("version") or "")
    if not name:
        return OracleResult(found=False, conclusion="insufficient_evidence", detail="missing_name", source="advisory_db")
    rows = _load_rows(path)
    matched = [
        row for row in rows
        if str(row.get("ecosystem") or "") == ecosystem and str(row.get("name") or "") == name and (not version or version in set(str(v) for v in row.get("affected_versions", [])))
    ]
    if not matched:
        return OracleResult(found=False, conclusion="pass", detail=f"no_advisories_for:{name}@{version}", source="advisory_db")
    return OracleResult(
        found=True,
        conclusion="fail",
        detail=";".join(str(row.get("id") or row.get("advisory_id") or "advisory") for row in matched),
        source="advisory_db",
    )


__all__ = ["lookup"]
