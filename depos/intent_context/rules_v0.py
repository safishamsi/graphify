"""Deterministic intent unit extraction (MUST/SHALL-style cues)."""
from __future__ import annotations

import hashlib
import re
import uuid

from depos.intent_context.schemas import IntentEvidence, IntentUnit, IntentUnitKind

_STRONG = re.compile(
    r"\b(MUST|SHALL|SHOULD NOT|MUST NOT|NEVER|ALWAYS|FORBIDDEN)\b\s*[:-]?\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_RFC = re.compile(r"\bshall\b.{0,200}", re.IGNORECASE)


def _unit_id_from(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()[:24]


def _guess_kind(text: str) -> IntentUnitKind:
    t = text.lower()
    if any(x in t for x in ("auth", "password", "token", "rls", "encrypt", "secret")):
        return "security_policy"
    if any(x in t for x in ("api", "http", "endpoint", "request", "response", "json")):
        return "api_contract_narrative"
    if any(x in t for x in ("owner", "team", "responsible", "on-call")):
        return "ownership"
    if any(x in t for x in ("schema", "table", "migration", "database", "model")):
        return "data_model"
    if "must" in t or "shall" in t or "never" in t or "always" in t:
        return "invariant"
    return "unknown"


def extract_rules_v0(chunk: str, *, chunk_id: str, start_line: int) -> list[IntentUnit]:
    units: list[IntentUnit] = []
    lines = chunk.split("\n")
    for i, line in enumerate(lines):
        abs_line = start_line + i
        for m in _STRONG.finditer(line):
            cue = m.group(1).upper()
            tail = (m.group(2) or "").strip()
            nl = f"{cue}: {tail}".strip() if tail else cue
            if len(nl) > 500:
                nl = nl[:497] + "..."
            uid = _unit_id_from(f"rules:{chunk_id}:{abs_line}:{nl[:80]}")
            units.append(
                IntentUnit(
                    unit_id=uid,
                    kind=_guess_kind(nl),
                    natural_language=nl,
                    evidence=[IntentEvidence(chunk_id=chunk_id, start_line=abs_line, end_line=abs_line)],
                    extractor="rules_v0",
                    confidence=0.55,
                )
            )
    body = "\n".join(lines)
    if _RFC.search(body) and not units:
        uid = str(uuid.uuid4())
        units.append(
            IntentUnit(
                unit_id=uid,
                kind="invariant",
                natural_language="RFC-style obligation language detected (review manually).",
                evidence=[
                    IntentEvidence(
                        chunk_id=chunk_id,
                        start_line=start_line,
                        end_line=start_line + len(lines) - 1,
                    )
                ],
                extractor="rules_v0",
                confidence=0.35,
            )
        )
    return units
