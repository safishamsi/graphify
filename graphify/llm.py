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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# `_read_files` truncates each file at this many characters before joining into
# the user message. Token estimates use the same cap so packing matches reality.
_FILE_CHAR_CAP = 20_000
# `_read_files` also wraps each file in a `=== {rel} ===\n...\n\n` separator;
# this is roughly the per-file overhead in characters that the prompt adds.
_PER_FILE_OVERHEAD_CHARS = 80
# Coarse fallback used only when `tiktoken` is not installed. 1 token ≈ 4 chars
# is the standard heuristic for English/code on BPE tokenizers.
_CHARS_PER_TOKEN = 4


def _get_tokenizer():
    """Return a tiktoken encoder for accurate token counts, or None if tiktoken
    is not installed. We use `cl100k_base` (GPT-4 / GPT-3.5-turbo) as a proxy:
    Kimi-K2 ships a tiktoken-based tokenizer with very similar BPE behaviour,
    and Claude's tokenizer has a comparable token-to-char ratio for prose/code.
    Estimates only need to be within ~5%, not exact.
    """
    try:
        import tiktoken
    except ImportError:
        return None
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:  # network failure on first-use download, etc.
        return None


# Cached at import time. None if tiktoken is unavailable; consumers must handle.
_TOKENIZER = _get_tokenizer()

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
    resp = client.chat.completions.create(**kwargs)
    result = _parse_llm_json(resp.choices[0].message.content or "{}")
    result["input_tokens"] = resp.usage.prompt_tokens if resp.usage else 0
    result["output_tokens"] = resp.usage.completion_tokens if resp.usage else 0
    result["model"] = model
    # `finish_reason == "length"` means the model hit max_completion_tokens
    # mid-generation. The JSON we got back is truncated; callers should
    # treat this as a signal to retry with smaller input.
    result["finish_reason"] = resp.choices[0].finish_reason
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
    # Normalise Anthropic's `stop_reason` to the OpenAI-compat `finish_reason`
    # vocabulary so the adaptive-retry layer doesn't have to know which
    # backend produced the result.
    result["finish_reason"] = "length" if resp.stop_reason == "max_tokens" else "stop"
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


def _estimate_file_tokens(path: Path) -> int:
    """Estimate the prompt-token cost of a single file under `_read_files` rules.

    Uses tiktoken (`cl100k_base`) when available for accurate counts. Falls back
    to the chars/4 heuristic if tiktoken is not installed. Both paths cap at
    `_FILE_CHAR_CAP` to match `_read_files`'s truncation, plus a constant for
    the `=== rel ===` separator. Returns 0 for unreadable paths so they don't
    blow up packing.
    """
    if _TOKENIZER is None:
        try:
            size = path.stat().st_size
        except OSError:
            return 0
        chars = min(size, _FILE_CHAR_CAP) + _PER_FILE_OVERHEAD_CHARS
        return chars // _CHARS_PER_TOKEN

    try:
        content = path.read_text(encoding="utf-8", errors="replace")[:_FILE_CHAR_CAP]
    except OSError:
        return 0
    return len(_TOKENIZER.encode(content)) + (_PER_FILE_OVERHEAD_CHARS // _CHARS_PER_TOKEN)


def _pack_chunks_by_tokens(
    files: list[Path],
    token_budget: int,
) -> list[list[Path]]:
    """Greedily pack files into chunks that fit a token budget.

    Files are first grouped by parent directory so related artifacts share a
    chunk (cross-file edges are more likely to be extracted within a chunk
    than across chunks). Within each directory, files are added one at a
    time; a chunk is closed when adding the next file would exceed the
    budget. A single file larger than the budget gets its own chunk and the
    caller is expected to handle the API error if it actually overflows the
    model's context window — packing can't shrink one big file.
    """
    if token_budget <= 0:
        raise ValueError(f"token_budget must be positive, got {token_budget}")

    by_dir: dict[Path, list[Path]] = {}
    for f in files:
        by_dir.setdefault(f.parent, []).append(f)

    chunks: list[list[Path]] = []
    current: list[Path] = []
    current_tokens = 0

    for directory in sorted(by_dir):
        for path in by_dir[directory]:
            cost = _estimate_file_tokens(path)
            if current and current_tokens + cost > token_budget:
                chunks.append(current)
                current = []
                current_tokens = 0
            current.append(path)
            current_tokens += cost

    if current:
        chunks.append(current)
    return chunks


def _extract_with_adaptive_retry(
    chunk: list[Path],
    backend: str,
    api_key: str | None,
    model: str | None,
    root: Path,
    max_depth: int,
    _depth: int = 0,
) -> dict:
    """Extract a chunk; if the response is truncated (`finish_reason="length"`),
    split the chunk in half and recurse.

    The signal driving the retry is the API's own `finish_reason` — `"length"`
    means the model hit `max_completion_tokens` mid-output. The truncated JSON
    has nothing useful in it (parse fails partway through a string or array),
    so we discard it and re-extract on smaller inputs that produce shorter
    outputs.

    Recursion is capped at `max_depth` to bound worst-case cost. A chunk of N
    files can split into up to 2**max_depth pieces — at depth=3 that's 8x. If
    still truncated at the cap, we surface the (likely empty) result with a
    warning rather than infinite-loop.

    A single-file chunk that truncates is unrecoverable here — we can't make
    one file smaller than itself, so we return what we got and warn.
    """
    result = extract_files_direct(
        chunk, backend=backend, api_key=api_key, model=model, root=root
    )

    if result.get("finish_reason") != "length":
        return result

    if len(chunk) <= 1:
        print(
            f"[graphify] single-file chunk {chunk[0]} truncated at "
            f"max_completion_tokens — partial result kept",
            file=sys.stderr,
        )
        return result

    if _depth >= max_depth:
        print(
            f"[graphify] chunk of {len(chunk)} still truncated at recursion "
            f"depth {_depth} (max {max_depth}) — partial result kept",
            file=sys.stderr,
        )
        return result

    print(
        f"[graphify] chunk of {len(chunk)} truncated at depth {_depth}, "
        f"splitting into halves of {len(chunk) // 2} and "
        f"{len(chunk) - len(chunk) // 2}",
        file=sys.stderr,
    )
    mid = len(chunk) // 2
    left = _extract_with_adaptive_retry(
        chunk[:mid], backend, api_key, model, root, max_depth, _depth + 1
    )
    right = _extract_with_adaptive_retry(
        chunk[mid:], backend, api_key, model, root, max_depth, _depth + 1
    )

    return {
        "nodes": left.get("nodes", []) + right.get("nodes", []),
        "edges": left.get("edges", []) + right.get("edges", []),
        "hyperedges": left.get("hyperedges", []) + right.get("hyperedges", []),
        "input_tokens": left.get("input_tokens", 0) + right.get("input_tokens", 0),
        "output_tokens": left.get("output_tokens", 0) + right.get("output_tokens", 0),
        "model": result.get("model"),
        # Both halves either succeeded or have already surfaced their own
        # truncation warning; the merged result is no longer truncated as a
        # logical unit.
        "finish_reason": "stop",
    }


def extract_corpus_parallel(
    files: list[Path],
    backend: str = "kimi",
    api_key: str | None = None,
    model: str | None = None,
    root: Path = Path("."),
    chunk_size: int = 20,
    on_chunk_done: Callable | None = None,
    token_budget: int | None = 60_000,
    max_concurrency: int = 4,
    max_retry_depth: int = 3,
) -> dict:
    """Extract a corpus in chunks, merging results.

    Chunking strategy:
        - If `token_budget` is set (default 60_000), files are packed to fit
          the budget and grouped by parent directory. This avoids the worst
          case where 20 randomly-grouped files exceed a model's context
          window in a single request.
        - If `token_budget=None`, falls back to the legacy fixed-count
          `chunk_size` packing for backwards compatibility.

    Concurrency:
        - Chunks run in parallel via a thread pool capped at `max_concurrency`
          (default 4 — conservative to stay under provider rate limits).
        - Set `max_concurrency=1` to force sequential execution.

    Adaptive retry on truncation:
        - When the LLM returns `finish_reason="length"` (output truncated at
          `max_completion_tokens`), the chunk is split in half and each half
          re-extracted recursively, up to `max_retry_depth` levels deep
          (default 3 → max 8x expansion of one chunk).
        - This is signal-driven: chunks too dense to fit in one response
          self-heal by splitting until they do, while well-sized chunks pay
          no extra cost. Set `max_retry_depth=0` to disable retries.

    `on_chunk_done(idx, total, chunk_result)` fires once per chunk as it
    completes (in completion order, not submission order). `idx` is the
    chunk's submission index so callers can correlate progress. The
    callback fires once per top-level chunk; recursive splits are merged
    transparently before the callback is invoked.

    Returns merged dict with nodes, edges, hyperedges, input_tokens,
    output_tokens. Failed chunks are logged to stderr and skipped — one bad
    chunk does not abort the run.
    """
    if token_budget is not None:
        chunks = _pack_chunks_by_tokens(files, token_budget=token_budget)
    else:
        chunks = [files[i:i + chunk_size] for i in range(0, len(files), chunk_size)]

    merged: dict = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    total = len(chunks)

    def _run_one(idx: int, chunk: list[Path]) -> tuple[int, dict | None, Exception | None]:
        t0 = time.time()
        try:
            result = _extract_with_adaptive_retry(
                chunk,
                backend=backend,
                api_key=api_key,
                model=model,
                root=root,
                max_depth=max_retry_depth,
            )
            result["elapsed_seconds"] = round(time.time() - t0, 2)
            return idx, result, None
        except Exception as exc:  # noqa: BLE001 — caller-facing surface, log + continue
            return idx, None, exc

    workers = max(1, min(max_concurrency, total))
    if workers == 1:
        # Avoid thread pool overhead for single-worker runs (and keep
        # callback ordering identical to the pre-refactor sequential path).
        for idx, chunk in enumerate(chunks):
            _, result, exc = _run_one(idx, chunk)
            if exc is not None:
                print(f"[graphify] chunk {idx + 1}/{total} failed: {exc}", file=sys.stderr)
                continue
            assert result is not None
            _merge_into(merged, result)
            if callable(on_chunk_done):
                on_chunk_done(idx, total, result)
        return merged

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run_one, idx, chunk) for idx, chunk in enumerate(chunks)]
        for future in as_completed(futures):
            idx, result, exc = future.result()
            if exc is not None:
                print(f"[graphify] chunk {idx + 1}/{total} failed: {exc}", file=sys.stderr)
                continue
            assert result is not None
            _merge_into(merged, result)
            if callable(on_chunk_done):
                on_chunk_done(idx, total, result)
    return merged


def _merge_into(merged: dict, result: dict) -> None:
    """Append a chunk result into the running merged accumulator."""
    merged["nodes"].extend(result.get("nodes", []))
    merged["edges"].extend(result.get("edges", []))
    merged["hyperedges"].extend(result.get("hyperedges", []))
    merged["input_tokens"] += result.get("input_tokens", 0)
    merged["output_tokens"] += result.get("output_tokens", 0)


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
