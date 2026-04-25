"""File- and repo-level summaries (LLM add-on)."""
from __future__ import annotations

import json
import logging
from collections import defaultdict

from pydantic import BaseModel, Field, ValidationError

from depos.analysis.config import IntelligenceConfig
from depos.analysis.reasoning_engine import OpenAIProvider, ProviderError
from depos.intent_context.json_util import parse_json_object
from depos.intent_context.schemas import IntentChunkRecord, IntentFileSummary, IntentRepoSummary

logger = logging.getLogger(__name__)


class _FileEnv(BaseModel):
    summary: str = ""
    bullet_claims: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)


class _RepoEnv(BaseModel):
    summary: str = ""
    themes: list[str] = Field(default_factory=list)


def summarize_files(
    config: IntelligenceConfig,
    chunks: list[IntentChunkRecord],
) -> tuple[list[IntentFileSummary], int, int, int]:
    """One LLM call per file (batched text). Returns (summaries, extra_calls, tin, tout)."""
    icfg = config.intent_context
    key = config.reasoner.openai_api_key
    if not key or not chunks:
        return [], 0, 0, 0
    model = icfg.intent_openai_model or config.reasoner.openai_model
    provider = OpenAIProvider(key, model=model, response_path=config.reasoner.openai_response_path)
    by_file: dict[str, list[IntentChunkRecord]] = defaultdict(list)
    for c in chunks:
        by_file[c.source_relpath].append(c)

    out: list[IntentFileSummary] = []
    calls = 0
    tin = 0
    tout = 0
    max_tok = min(icfg.max_tokens_per_call, 2048)

    for rel, file_chunks in sorted(by_file.items()):
        allowed = {c.chunk_id for c in file_chunks}
        body = json.dumps(
            [
                {
                    "chunk_id": c.chunk_id,
                    "headings": c.heading_stack,
                    "text": c.text[:8000],
                }
                for c in file_chunks
            ],
            indent=1,
        )[:40000]
        prompt = (
            "Summarize intent for one documentation file. Output JSON only: "
            '{"summary": "...", "bullet_claims": ["..."], "chunk_ids": ["..."]} '
            "chunk_ids must be from the list only.\n\nFILE_CHUNKS:\n"
            f"{body}"
        )
        tin += len(prompt) // 4
        try:
            raw, _ = provider.complete(prompt, max_tokens=max_tok)
        except ProviderError as e:
            logger.warning("file summary failed for %s: %s", rel, e)
            continue
        calls += 1
        tout += len(raw) // 4
        try:
            data = parse_json_object(raw)
            env = _FileEnv.model_validate(data)
        except (ValueError, ValidationError) as e:
            logger.warning("file summary parse %s: %s", rel, e)
            continue
        cids = [x for x in env.chunk_ids if x in allowed]
        out.append(
            IntentFileSummary(
                source_relpath=rel,
                summary=env.summary.strip()[:4000],
                bullet_claims=[b[:500] for b in env.bullet_claims[:24]],
                chunk_ids=cids or list(allowed)[:8],
            )
        )
    return out, calls, tin, tout


def summarize_repo(
    config: IntelligenceConfig,
    file_summaries: list[IntentFileSummary],
) -> tuple[IntentRepoSummary | None, int, int, int]:
    if not config.reasoner.openai_api_key or not file_summaries:
        return None, 0, 0, 0
    icfg = config.intent_context
    model = icfg.intent_openai_model or config.reasoner.openai_model
    provider = OpenAIProvider(
        config.reasoner.openai_api_key,
        model=model,
        response_path=config.reasoner.openai_response_path,
    )
    compact = [
        {"file": s.source_relpath, "summary": s.summary[:1200], "bullets": s.bullet_claims[:8]}
        for s in file_summaries[:80]
    ]
    prompt = (
        "You consolidate repo-level documentation intent. Output JSON only: "
        '{"summary": "...", "themes": ["..."]}\n\nFILES:\n'
        f"{json.dumps(compact, indent=1)[:60000]}"
    )
    tin = len(prompt) // 4
    max_tok = min(icfg.max_tokens_per_call, 2048)
    try:
        raw, _ = provider.complete(prompt, max_tokens=max_tok)
    except ProviderError as e:
        logger.warning("repo summary failed: %s", e)
        return None, 0, tin, 0
    tout = len(raw) // 4
    try:
        data = parse_json_object(raw)
        env = _RepoEnv.model_validate(data)
    except (ValueError, ValidationError):
        return None, 1, tin, tout
    return (
        IntentRepoSummary(
            summary=env.summary.strip()[:8000],
            themes=[t[:200] for t in env.themes[:32]],
            file_relpaths=[s.source_relpath for s in file_summaries],
        ),
        1,
        tin,
        tout,
    )
