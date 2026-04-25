"""OpenAI-backed intent unit extraction (llm_v0)."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from depos.analysis.config import IntentContextConfig, IntelligenceConfig
from depos.analysis.reasoning_engine import OpenAIProvider, ProviderError
from depos.intent_context.json_util import parse_json_object
from depos.intent_context.schemas import IntentChunkRecord, IntentEvidence, IntentUnit, IntentUnitKind

logger = logging.getLogger(__name__)

_VALID_KINDS: frozenset[str] = frozenset(
    {
        "invariant",
        "ownership",
        "security_policy",
        "api_contract_narrative",
        "data_model",
        "unknown",
    }
)


class _LlmEvidence(BaseModel):
    chunk_id: str = ""
    start_line: int | None = None
    end_line: int | None = None


class _LlmUnitDraft(BaseModel):
    unit_id: str | None = None
    kind: str = "unknown"
    natural_language: str = ""
    scope_hints: list[str] = Field(default_factory=list)
    evidence: list[_LlmEvidence] = Field(default_factory=list)
    confidence: float = 0.5


class _LlmUnitsEnvelope(BaseModel):
    units: list[_LlmUnitDraft] = Field(default_factory=list)


def _map_kind(raw: str) -> IntentUnitKind:
    k = (raw or "unknown").strip().lower()
    if k in _VALID_KINDS:
        return k  # type: ignore[return-value]
    return "unknown"


def _draft_to_unit(d: _LlmUnitDraft, allowed_chunk_ids: set[str]) -> IntentUnit | None:
    ev: list[IntentEvidence] = []
    for e in d.evidence:
        if e.chunk_id not in allowed_chunk_ids:
            continue
        ev.append(
            IntentEvidence(
                chunk_id=e.chunk_id,
                start_line=e.start_line,
                end_line=e.end_line,
            )
        )
    if not ev:
        return None
    nl = (d.natural_language or "").strip()
    if not nl:
        return None
    uid = (d.unit_id or "").strip() or hashlib.sha256(nl.encode()).hexdigest()[:24]
    return IntentUnit(
        unit_id=uid[:128],
        kind=_map_kind(d.kind),
        natural_language=nl[:2000],
        scope_hints=[str(x) for x in d.scope_hints][:32],
        evidence=ev,
        extractor="llm_v0",
        confidence=max(0.0, min(1.0, float(d.confidence or 0.5))),
    )


_UNITS_PROMPT_HEAD = """You extract software intent claims from documentation chunks.
Output a single JSON object with key "units" (array). Each element:
- unit_id: stable short id (or omit, server will hash)
- kind: one of invariant | ownership | security_policy | api_contract_narrative | data_model | unknown
- natural_language: one concise sentence
- scope_hints: optional string array (paths, services)
- evidence: array of {chunk_id, start_line?, end_line?} — chunk_id MUST be from the provided chunks only
- confidence: 0.0–1.0

Rules: only cite chunk_ids listed below. No prose outside JSON."""


def extract_units_llm_batched(
    config: IntelligenceConfig,
    chunks: list[IntentChunkRecord],
    *,
    batch_size: int = 6,
) -> tuple[list[IntentUnit], int, int, int]:
    """Return (units, calls, est_tokens_in, est_tokens_out)."""
    icfg = config.intent_context
    api_key = config.reasoner.openai_api_key
    if not api_key:
        return [], 0, 0, 0
    model = icfg.intent_openai_model or config.reasoner.openai_model
    provider = OpenAIProvider(
        api_key,
        model=model,
        response_path=config.reasoner.openai_response_path,
    )
    all_units: list[IntentUnit] = []
    calls = 0
    tin = 0
    tout = 0
    max_tok = min(icfg.max_tokens_per_call, config.reasoner.default_max_tokens * 4)

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        allowed = {c.chunk_id for c in batch}
        payload = [
            {
                "chunk_id": c.chunk_id,
                "source_relpath": c.source_relpath,
                "heading_stack": c.heading_stack,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "text": c.text[:12000],
            }
            for c in batch
        ]
        prompt = (
            f"{_UNITS_PROMPT_HEAD}\n\nCHUNKS_JSON:\n{json.dumps(payload, indent=2)[: icfg.max_input_bytes_per_repo // 4]}"
        )
        est_in = len(prompt) // 4
        tin += est_in
        try:
            raw, meta = provider.complete(prompt, max_tokens=max_tok)
        except ProviderError as e:
            logger.warning("llm_v0 batch failed: %s", e)
            continue
        calls += 1
        tout += len(raw) // 4
        try:
            data = parse_json_object(raw)
            env = _LlmUnitsEnvelope.model_validate(data)
        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            logger.warning("llm_v0 parse failed: %s", e)
            continue
        for d in env.units:
            u = _draft_to_unit(d, allowed)
            if u:
                all_units.append(u)
    return all_units, calls, tin, tout
