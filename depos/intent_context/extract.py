"""Extractor entrypoints (rules_v0, oft_markdown_v0; llm_v0 in ``llm_v0`` module)."""
from __future__ import annotations

from depos.intent_context.oft_markdown_v0 import extract_oft_markdown_v0, oft_prompt_context_snippet
from depos.intent_context.rules_v0 import extract_rules_v0

__all__ = ["extract_rules_v0", "extract_oft_markdown_v0", "oft_prompt_context_snippet"]
