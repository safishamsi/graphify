# Direct LLM backend for semantic extraction — supports Claude and Kimi K2.6.
# Used by `graphify . --backend kimi` and the benchmark scripts.
# The default graphify pipeline uses Claude Code subagents via skill.md;
# this module provides a direct API path for non-Claude-Code environments.
from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

BACKENDS: dict[str, dict] = {
    "claude": {
        "base_url": "https://api.anthropic.com",
        "default_model": "claude-sonnet-4-6",
        "env_key": "ANTHROPIC_API_KEY",
        "pricing": {"input": 3.0, "output": 15.0},  # USD per 1M tokens
        "temperature": 0,
    },
    "kimi": {
        "base_url": "https://api.moonshot.ai/v1",
        "default_model": "kimi-k2.6",
        "env_key": "MOONSHOT_API_KEY",
        "pricing": {"input": 0.74, "output": 4.66},  # USD per 1M tokens
        "temperature": None,  # kimi-k2.6 enforces its own fixed temperature; sending any value raises 400
    },
}

_EXTRACTION_SYSTEM = """\
You are a graphify semantic extraction agent. Extract a knowledge graph fragment from the files provided.
Output ONLY valid JSON — no explanation, no markdown fences, no preamble.

Rules:
- EXTRACTED: relationship explicit in source (import, call, citation, reference)
- INFERRED: reasonable inference (shared data structure, implied dependency)
- AMBIGUOUS: uncertain — flag for review, do not omit

Node ID format: lowercase, only [a-z0-9_], no dots or slashes.
Format: {stem}_{entity} where stem = filename without extension, entity = symbol name (both normalised).

Output exactly this schema:
{"nodes":[{"id":"stem_entity","label":"Human Readable Name","file_type":"code|document|paper|image|concept","source_file":"relative/path","source_location":null,"source_url":null,"captured_at":null,"author":null,"contributor":null}],"edges":[{"source":"node_id","target":"node_id","relation":"calls|implements|references|cites|conceptually_related_to|shares_data_with|semantically_similar_to","confidence":"EXTRACTED|INFERRED|AMBIGUOUS","confidence_score":1.0,"source_file":"relative/path","source_location":null,"weight":1.0}],"hyperedges":[],"input_tokens":0,"output_tokens":0}
"""


def _read_files(paths: list[Path], root: Path) -> str:
    """Return file contents formatted for the extraction prompt."""
    parts: list[str] = []
    for p in paths:
        try:
            rel = p.relative_to(root)
        except ValueError:
            rel = p
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        parts.append(f"=== {rel} ===\n{content[:20000]}")
    return "\n\n".join(parts)


def _parse_llm_json(raw: str) -> dict:
    """Strip optional markdown fences and parse JSON. Returns empty fragment on failure."""
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError as exc:
        print(f"[graphify] LLM returned invalid JSON, skipping chunk: {exc}", file=sys.stderr)
        return {"nodes": [], "edges": [], "hyperedges": []}


def _call_openai_compat(
    base_url: str,
    api_key: str,
    model: str,
    user_message: str,
    temperature: float | None = 0,
) -> dict:
    """Call any OpenAI-compatible API (Kimi, OpenAI, etc.) and return parsed JSON."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError(
            "Kimi/OpenAI-compatible extraction requires the openai package. "
            "Run: pip install openai"
        ) from exc

    client = OpenAI(api_key=api_key, base_url=base_url)
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": _EXTRACTION_SYSTEM},
            {"role": "user", "content": user_message},
        ],
        "max_completion_tokens": 8192,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    # kimi-k2.6 is a reasoning model: it writes its chain-of-thought to
    # `reasoning_content` and the answer to `content`. When reasoning consumes
    # the entire max_completion_tokens budget on large chunks, `content` stays
    # empty and we parse zero nodes while still paying for the input + reasoning
    # tokens. For structured extraction we don't need chain-of-thought, so
    # disable thinking on Moonshot-hosted models.
    if "moonshot" in base_url:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    resp = client.chat.completions.create(**kwargs)
    result = _parse_llm_json(resp.choices[0].message.content or "{}")
    result["input_tokens"] = resp.usage.prompt_tokens if resp.usage else 0
    result["output_tokens"] = resp.usage.completion_tokens if resp.usage else 0
    result["model"] = model
    return result


def _call_claude(api_key: str, model: str, user_message: str) -> dict:
    """Call Anthropic Claude directly (not via OpenAI compat layer)."""
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError(
            "Claude direct extraction requires the anthropic package. "
            "Run: pip install anthropic"
        ) from exc

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=8192,
        system=_EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )
    result = _parse_llm_json(resp.content[0].text if resp.content else "{}")
    result["input_tokens"] = resp.usage.input_tokens if resp.usage else 0
    result["output_tokens"] = resp.usage.output_tokens if resp.usage else 0
    result["model"] = model
    return result


def extract_files_direct(
    files: list[Path],
    backend: str = "kimi",
    api_key: str | None = None,
    model: str | None = None,
    root: Path = Path("."),
) -> dict:
    """Extract semantic nodes/edges from a list of files using the given backend.

    Returns dict with nodes, edges, hyperedges, input_tokens, output_tokens.
    Raises ValueError for unknown backends. Raises ImportError if SDK missing.
    """
    if backend not in BACKENDS:
        raise ValueError(f"Unknown backend {backend!r}. Available: {sorted(BACKENDS)}")

    cfg = BACKENDS[backend]
    key = api_key or os.environ.get(cfg["env_key"], "")
    if not key:
        raise ValueError(
            f"No API key for backend '{backend}'. "
            f"Set {cfg['env_key']} or pass api_key=."
        )
    mdl = model or cfg["default_model"]
    user_msg = _read_files(files, root)

    if backend == "claude":
        return _call_claude(key, mdl, user_msg)
    else:
        return _call_openai_compat(cfg["base_url"], key, mdl, user_msg, temperature=cfg.get("temperature", 0))


def extract_corpus_parallel(
    files: list[Path],
    backend: str = "kimi",
    api_key: str | None = None,
    model: str | None = None,
    root: Path = Path("."),
    chunk_size: int = 20,
    on_chunk_done: Callable | None = None,
) -> dict:
    """Extract a corpus in chunks, merging results.

    on_chunk_done(idx, total, chunk_result) is called after each chunk if provided.
    Returns merged dict with nodes, edges, hyperedges, input_tokens, output_tokens.
    """
    chunks = [files[i:i + chunk_size] for i in range(0, len(files), chunk_size)]
    merged: dict = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}

    for idx, chunk in enumerate(chunks):
        t0 = time.time()
        result = extract_files_direct(chunk, backend=backend, api_key=api_key, model=model, root=root)
        result["elapsed_seconds"] = round(time.time() - t0, 2)
        merged["nodes"].extend(result.get("nodes", []))
        merged["edges"].extend(result.get("edges", []))
        merged["hyperedges"].extend(result.get("hyperedges", []))
        merged["input_tokens"] += result.get("input_tokens", 0)
        merged["output_tokens"] += result.get("output_tokens", 0)
        if callable(on_chunk_done):
            on_chunk_done(idx, len(chunks), result)

    return merged


def estimate_cost(backend: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a given token count using published pricing."""
    if backend not in BACKENDS:
        return 0.0
    p = BACKENDS[backend]["pricing"]
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


def detect_backend() -> str | None:
    """Return the name of whichever backend has an API key set, or None.

    Kimi is checked first (opt-in). Falls back to Claude if ANTHROPIC_API_KEY is set.
    Claude is the default for the skill.md subagent pipeline and is never forced here.
    """
    if os.environ.get("MOONSHOT_API_KEY"):
        return "kimi"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    return None
