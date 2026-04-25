"""JSON cleanup for LLM responses (fences, trailing commas)."""
from __future__ import annotations

import json
import re

_FENCE_OPEN = re.compile(r"^\s*```(?:json|JSON)?\s*", re.MULTILINE)
_FENCE_CLOSE = re.compile(r"\s*```\s*$", re.MULTILINE)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def strip_llm_json(raw: str) -> str:
    no_open = _FENCE_OPEN.sub("", raw)
    no_close = _FENCE_CLOSE.sub("", no_open)
    return _TRAILING_COMMA.sub(r"\1", no_close).strip()


def parse_json_object(raw: str) -> dict:
    cleaned = strip_llm_json(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first == -1 or last == -1 or last <= first:
            raise
        data = json.loads(cleaned[first : last + 1])
    if not isinstance(data, dict):
        raise ValueError("expected JSON object at top level")
    return data
