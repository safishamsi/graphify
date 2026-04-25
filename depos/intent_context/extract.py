"""Extractor entrypoints (rules_v0 always; llm_v0 from ``llm_v0`` module when enabled)."""
from __future__ import annotations

from depos.intent_context.rules_v0 import extract_rules_v0

__all__ = ["extract_rules_v0"]
