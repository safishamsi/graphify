# Direct LLM backend for semantic extraction — supports Claude, Kimi K2.6,
# Gemini, and OpenAI.
# Used by `graphify extract . --backend gemini` and the benchmark scripts.
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
        "max_tokens": 16384,
    },
    "kimi": {
        "base_url": "https://api.moonshot.ai/v1",
        "default_model": "kimi-k2.6",
        "env_key": "MOONSHOT_API_KEY",
        "pricing": {"input": 0.74, "output": 4.66},  # USD per 1M tokens
        "temperature": None,  # kimi-k2.6 enforces its own fixed temperature; sending any value raises 400
        "max_tokens": 16384,
    },
    "ollama": {
        "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "default_model": os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"),
        "env_key": "OLLAMA_API_KEY",
        "pricing": {"input": 0.0, "output": 0.0},
        "temperature": 0,
        "max_tokens": 16384,
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-3-flash-preview",
        "env_keys": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "model_env_key": "GRAPHIFY_GEMINI_MODEL",
        "pricing": {"input": 0.50, "output": 3.00},  # USD per 1M tokens
        "temperature": 0,
        "reasoning_effort": "low",
        "max_completion_tokens": 16384,
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4.1-mini",
        "env_key": "OPENAI_API_KEY",
        "model_env_key": "GRAPHIFY_OPENAI_MODEL",
        "pricing": {"input": 0.40, "output": 1.60},  # USD per 1M tokens
        "temperature": 0,
    },
    "bedrock": {
        "default_model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "model_env_key": "GRAPHIFY_BEDROCK_MODEL",
        "pricing": {"input": 3.0, "output": 15.0},  # USD per 1M tokens
        "temperature": 0,
        "max_tokens": 16384,
    },
    "claude-cli": {
        # Routes through the locally-installed `claude` CLI (Claude Code) using
        # `-p --output-format json`. Authenticates via the user's existing
        # Pro/Max subscription instead of a separate ANTHROPIC_API_KEY — costs
        # are billed to the plan, not pay-as-you-go API credit.
        "default_model": "claude-code-plan",
        "pricing": {"input": 0.0, "output": 0.0},
        "temperature": 0,
        "max_tokens": 16384,
    },
}


def _resolve_max_tokens(default: int) -> int:
    """Honour GRAPHIFY_MAX_OUTPUT_TOKENS env var override, else use backend default."""
    raw = os.environ.get("GRAPHIFY_MAX_OUTPUT_TOKENS", "").strip()
    if raw:
        try:
            v = int(raw)
            if v > 0:
                return v
        except ValueError:
            pass
    return default

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
{"nodes":[{"id":"stem_entity","label":"Human Readable Name","file_type":"code|document|paper|image|rationale|concept","source_file":"relative/path","source_location":null,"source_url":null,"captured_at":null,"author":null,"contributor":null}],"edges":[{"source":"node_id","target":"node_id","relation":"calls|implements|references|cites|conceptually_related_to|shares_data_with|semantically_similar_to","confidence":"EXTRACTED|INFERRED|AMBIGUOUS","confidence_score":1.0,"source_file":"relative/path","source_location":null,"weight":1.0}],"hyperedges":[],"input_tokens":0,"output_tokens":0}
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


_LLM_JSON_MAX_BYTES = 10 * 1024 * 1024  # 10 MB hard cap before json.loads (F-016)


def _parse_llm_json(raw: str) -> dict:
    """Strip optional markdown fences and parse JSON. Returns empty fragment on failure.

    Caps the input at `_LLM_JSON_MAX_BYTES` so a hostile or runaway model
    response cannot exhaust memory inside `json.loads` (F-016).
    """
    if len(raw) > _LLM_JSON_MAX_BYTES:
        print(
            f"[graphify] LLM response exceeds {_LLM_JSON_MAX_BYTES} bytes "
            f"({len(raw)} bytes); refusing to parse and dropping chunk.",
            file=sys.stderr,
        )
        return {"nodes": [], "edges": [], "hyperedges": []}
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


def _response_is_hollow(raw_content: str | None, parsed: dict) -> bool:
    """Detect a successful HTTP response that yielded no usable extraction.

    A local model under load (most often Ollama) can return HTTP 200 with an
    empty / null `message.content`, with whitespace, or with a half-generated
    JSON prefix that fails to parse. All of these collapse to a "successful"
    call producing zero nodes and zero edges. Without this check the chunk
    is silently dropped from the corpus because no exception is raised and
    `finish_reason` is `"stop"` rather than `"length"`. By flagging the
    result as hollow, callers can re-route it through the same bisection
    path used for context-window overflow and `finish_reason="length"`.
    """
    if raw_content is None or not raw_content.strip():
        return True
    nodes = parsed.get("nodes")
    edges = parsed.get("edges")
    hyperedges = parsed.get("hyperedges")
    return not nodes and not edges and not hyperedges


def _backend_env_keys(backend: str) -> list[str]:
    """Return accepted API-key environment variables for a backend."""
    cfg = BACKENDS[backend]
    keys = cfg.get("env_keys")
    if keys:
        return list(keys)
    env_key = cfg.get("env_key")
    if env_key:
        return [env_key]
    return []


def _get_backend_api_key(backend: str) -> str:
    """Return the first configured API key for backend, or an empty string."""
    for env_key in _backend_env_keys(backend):
        value = os.environ.get(env_key)
        if value:
            return value
    return ""


def _format_backend_env_keys(backend: str) -> str:
    """Return user-facing accepted API-key variable names."""
    keys = _backend_env_keys(backend)
    return " or ".join(keys) if keys else "AWS_PROFILE or AWS_REGION"


def _default_model_for_backend(backend: str) -> str:
    """Return configured model override or backend default model."""
    cfg = BACKENDS[backend]
    model_env_key = cfg.get("model_env_key")
    if model_env_key:
        model = os.environ.get(model_env_key)
        if model:
            return model
    return cfg["default_model"]


def _call_openai_compat(
    base_url: str,
    api_key: str,
    model: str,
    user_message: str,
    temperature: float | None = 0,
    reasoning_effort: str | None = None,
    max_completion_tokens: int = 8192,
    *,
    backend: str = "",
) -> dict:
    """Call any OpenAI-compatible API (Kimi, OpenAI, etc.) and return parsed JSON."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        pkg_hint = "graphifyy[kimi]" if backend == "kimi" else "openai"
        raise ImportError(
            "Gemini/Kimi/Ollama/OpenAI-compatible extraction requires the openai package. "
            f"Run: pip install {pkg_hint}"
        ) from exc

    # Local backends (ollama, llama.cpp, vLLM) routinely take >60s for a
    # single chunk on a large model — far longer than the openai SDK's
    # default. Honour GRAPHIFY_API_TIMEOUT (seconds) for explicit override;
    # default to 600s, which is long enough for a 31B model on a 16k chunk
    # but still bounds runaway connections (issue #792 addendum).
    timeout_raw = os.environ.get("GRAPHIFY_API_TIMEOUT", "").strip()
    timeout_s: float = 600.0
    if timeout_raw:
        try:
            v = float(timeout_raw)
            if v > 0:
                timeout_s = v
        except ValueError:
            pass
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_s)
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": _EXTRACTION_SYSTEM},
            {"role": "user", "content": user_message},
        ],
        "max_completion_tokens": max_completion_tokens,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
    # Kimi-k2.6 is a reasoning model — disable thinking so content isn't empty
    if "moonshot" in base_url:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    # Ollama defaults num_ctx to 2048 and silently truncates prompts larger
    # than that — the symptom is hollow 200 OK responses after the first few
    # chunks (#798). We derive num_ctx from the actual prompt size so we don't
    # over-allocate KV-cache VRAM. Over-allocation (e.g. 128k slots for an 8k
    # prompt on a 31B model) exhausts VRAM by chunk 4 and produces the same
    # hollow-200 symptom — just from a different direction (#798 follow-up).
    # Formula: actual input tokens + output cap + system prompt headroom.
    # Capped at 131072 (enough for the default 60k token_budget); env var wins.
    if backend == "ollama":
        num_ctx_raw = os.environ.get("GRAPHIFY_OLLAMA_NUM_CTX", "").strip()
        # Auto-derive num_ctx from actual chunk size regardless — used as the
        # fallback and for the mismatch check below.
        estimated_input = len(user_message) // _CHARS_PER_TOKEN + 400
        auto_num_ctx = min(estimated_input + max_completion_tokens + 2000, 131072)
        auto_num_ctx = max(auto_num_ctx, 8192)
        if num_ctx_raw:
            try:
                num_ctx = int(num_ctx_raw)
            except ValueError:
                # Bad env var: fall through to auto-derivation (not 131072 —
                # hardcoding the cap is what causes OOM on constrained VRAM).
                print(
                    f"[graphify] GRAPHIFY_OLLAMA_NUM_CTX={num_ctx_raw!r} is not a valid integer; "
                    f"using auto-derived value ({auto_num_ctx}).",
                    file=sys.stderr,
                )
                num_ctx = auto_num_ctx
            else:
                # Warn when the pinned value is smaller than the estimated input —
                # Ollama silently truncates the prompt and returns empty responses.
                if num_ctx < estimated_input:
                    print(
                        f"[graphify] warning: GRAPHIFY_OLLAMA_NUM_CTX={num_ctx} is smaller than "
                        f"the estimated chunk input (~{estimated_input} tokens). Ollama will "
                        f"silently truncate the prompt and return empty responses. "
                        f"Try --token-budget {max(1024, num_ctx // 3)} or increase NUM_CTX.",
                        file=sys.stderr,
                    )
        else:
            # Estimate input tokens: user_message chars / 4 (standard BPE
            # heuristic) + 400 for the system prompt, then add output headroom.
            num_ctx = auto_num_ctx
        keep_alive = os.environ.get("GRAPHIFY_OLLAMA_KEEP_ALIVE", "30m")
        kwargs["extra_body"] = {"options": {"num_ctx": num_ctx}, "keep_alive": keep_alive}
    resp = client.chat.completions.create(**kwargs)
    raw_content = resp.choices[0].message.content
    result = _parse_llm_json(raw_content or "{}")
    result["input_tokens"] = resp.usage.prompt_tokens if resp.usage else 0
    result["output_tokens"] = resp.usage.completion_tokens if resp.usage else 0
    result["model"] = model
    # `finish_reason == "length"` means the model hit max_completion_tokens
    # mid-generation. The JSON we got back is truncated; callers should
    # treat this as a signal to retry with smaller input.
    result["finish_reason"] = resp.choices[0].finish_reason
    # An overwhelmed local model (typically Ollama) can return HTTP 200 with
    # empty / null content or unparseable half-generated JSON. The call looks
    # successful, `finish_reason` is `"stop"`, and the chunk would be silently
    # dropped from the corpus. Re-label as `"length"` so the adaptive retry
    # layer bisects the chunk — same recovery as a true truncation.
    if _response_is_hollow(raw_content, result) and result["finish_reason"] != "length":
        print(
            f"[graphify] {backend or 'backend'} returned a hollow response "
            f"(content={'empty' if not (raw_content or '').strip() else 'no nodes/edges'}, "
            f"output_tokens={result['output_tokens']}); "
            "treating as truncation so adaptive retry can bisect the chunk.",
            file=sys.stderr,
        )
        result["finish_reason"] = "length"
    output_tokens = result["output_tokens"]
    if output_tokens < 50 and backend == "ollama":
        print(
            "[graphify] warning: ollama returned very few tokens — likely causes: "
            "(1) VRAM pressure: check `nvidia-smi` and reduce chunk size with "
            "--token-budget (e.g. --token-budget 4096) or set "
            "GRAPHIFY_OLLAMA_NUM_CTX to a smaller value; "
            "(2) model too small for JSON instruction following — "
            "try a larger model with --model (e.g. --model qwen2.5-coder:14b).",
            file=sys.stderr,
        )
    return result


def _call_claude(api_key: str, model: str, user_message: str, max_tokens: int = 8192) -> dict:
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
        max_tokens=max_tokens,
        system=_EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )
    raw_content = resp.content[0].text if resp.content else None
    result = _parse_llm_json(raw_content or "{}")
    result["input_tokens"] = resp.usage.input_tokens if resp.usage else 0
    result["output_tokens"] = resp.usage.output_tokens if resp.usage else 0
    result["model"] = model
    # Normalise Anthropic's `stop_reason` to the OpenAI-compat `finish_reason`
    # vocabulary so the adaptive-retry layer doesn't have to know which
    # backend produced the result.
    result["finish_reason"] = "length" if resp.stop_reason == "max_tokens" else "stop"
    if _response_is_hollow(raw_content, result) and result["finish_reason"] != "length":
        print(
            "[graphify] claude returned a hollow response; treating as "
            "truncation so adaptive retry can bisect the chunk.",
            file=sys.stderr,
        )
        result["finish_reason"] = "length"
    return result


def _call_claude_cli(user_message: str, max_tokens: int = 8192) -> dict:
    """Call Claude via the locally-installed Claude Code CLI (`claude -p`).

    Routes through the user's Claude Code subscription auth instead of a separate
    ANTHROPIC_API_KEY. Useful for Pro/Max subscribers who don't want to provision
    a pay-as-you-go API key just to run graphify's semantic pass.
    """
    import shutil
    import subprocess

    if shutil.which("claude") is None:
        raise RuntimeError(
            "Claude Code CLI not found on $PATH. Install from "
            "https://claude.ai/code and run `claude` once to authenticate."
        )

    proc = subprocess.run(
        [
            "claude", "-p",
            "--output-format", "json",
            "--no-session-persistence",
            "--append-system-prompt", _EXTRACTION_SYSTEM,
        ],
        input=user_message,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude -p exited {proc.returncode}: {proc.stderr.strip()[:500]}"
        )

    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"claude -p produced unparseable JSON envelope: {exc}; "
            f"first 500 chars of stdout: {proc.stdout[:500]!r}"
        ) from exc

    raw_content = envelope.get("result", "")
    result = _parse_llm_json(raw_content or "{}")
    usage = envelope.get("usage") or {}
    result["input_tokens"] = (
        int(usage.get("input_tokens", 0) or 0)
        + int(usage.get("cache_read_input_tokens", 0) or 0)
        + int(usage.get("cache_creation_input_tokens", 0) or 0)
    )
    result["output_tokens"] = int(usage.get("output_tokens", 0) or 0)
    model_usage = envelope.get("modelUsage") or {}
    result["model"] = next(iter(model_usage), "claude-code-plan")
    stop_reason = envelope.get("stop_reason", "")
    result["finish_reason"] = "length" if stop_reason == "max_tokens" else "stop"
    if _response_is_hollow(raw_content, result) and result["finish_reason"] != "length":
        print(
            "[graphify] claude-cli returned a hollow response; treating as "
            "truncation so adaptive retry can bisect the chunk.",
            file=sys.stderr,
        )
        result["finish_reason"] = "length"
    return result


def _call_bedrock(model: str, user_message: str, max_tokens: int = 8192) -> dict:
    """Call AWS Bedrock via boto3 Converse API using the standard AWS credential chain."""
    try:
        import boto3
        import botocore.exceptions
    except ImportError as exc:
        raise ImportError(
            "AWS Bedrock extraction requires boto3. Run: pip install graphifyy[bedrock]"
        ) from exc

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    profile = os.environ.get("AWS_PROFILE")
    session = boto3.Session(profile_name=profile, region_name=region)
    client = session.client("bedrock-runtime")

    try:
        resp = client.converse(
            modelId=model,
            system=[{"text": _EXTRACTION_SYSTEM}],
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
        )
    except botocore.exceptions.ClientError as exc:
        code = exc.response["Error"]["Code"]
        msg = exc.response["Error"]["Message"]
        raise RuntimeError(f"Bedrock API error ({code}): {msg}") from exc

    text = resp.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "{}")
    result = _parse_llm_json(text)
    usage = resp.get("usage", {})
    result["input_tokens"] = usage.get("inputTokens", 0)
    result["output_tokens"] = usage.get("outputTokens", 0)
    result["model"] = model
    result["finish_reason"] = "length" if resp.get("stopReason") == "max_tokens" else "stop"
    if _response_is_hollow(text, result) and result["finish_reason"] != "length":
        print(
            "[graphify] bedrock returned a hollow response; treating as "
            "truncation so adaptive retry can bisect the chunk.",
            file=sys.stderr,
        )
        result["finish_reason"] = "length"
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
    key = api_key or _get_backend_api_key(backend)
    if not key and backend == "ollama":
        # Ollama ignores auth but the OpenAI client library requires a non-empty
        # string. Use a placeholder and surface a visible warning so this never
        # silently routes traffic without the user realising — see F-029.
        ollama_url = os.environ.get("OLLAMA_BASE_URL", cfg.get("base_url", ""))
        _validate_ollama_base_url(ollama_url)
        print(
            "[graphify] WARNING: ollama backend selected with no OLLAMA_API_KEY set; "
            f"sending corpus to {ollama_url}. Set OLLAMA_API_KEY (any non-empty value) "
            "to suppress this warning.",
            file=sys.stderr,
        )
        key = "ollama"
    if not key and backend not in ("bedrock", "claude-cli"):
        raise ValueError(
            f"No API key for backend '{backend}'. "
            f"Set {_format_backend_env_keys(backend)} or pass api_key=."
        )
    mdl = model or _default_model_for_backend(backend)
    user_msg = _read_files(files, root)
    max_out = _resolve_max_tokens(cfg.get("max_tokens", 8192))

    if backend == "claude":
        return _call_claude(key, mdl, user_msg, max_tokens=max_out)
    if backend == "claude-cli":
        return _call_claude_cli(user_msg, max_tokens=max_out)
    if backend == "bedrock":
        return _call_bedrock(mdl, user_msg, max_tokens=max_out)
    return _call_openai_compat(
        cfg["base_url"],
        key,
        mdl,
        user_msg,
        temperature=cfg.get("temperature", 0),
        reasoning_effort=cfg.get("reasoning_effort"),
        max_completion_tokens=cfg.get("max_completion_tokens", max_out),
        backend=backend,
    )


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


_CONTEXT_EXCEEDED_MARKERS = (
    "context size",
    "context length",
    "context_length",
    "context window",
    "n_keep",
    "exceeds the available",
    "n_ctx",
    "maximum context",
    "too many tokens",
    "prompt is too long",
    "context_length_exceeded",
)


def _looks_like_context_exceeded(exc: BaseException) -> bool:
    """Heuristically classify an exception as a context-window overflow.

    Different backends raise different exception types and messages for the
    same underlying problem ("the prompt + max_completion_tokens did not fit
    in the model's context window"). We match on substrings of the stringified
    exception so the retry layer can recover without depending on a specific
    SDK class. False positives are cheap (we'll re-extract on halves and
    likely recover); false negatives are expensive (chunk fails entirely).
    """
    msg = str(exc).lower()
    return any(marker in msg for marker in _CONTEXT_EXCEEDED_MARKERS)


def _extract_with_adaptive_retry(
    chunk: list[Path],
    backend: str,
    api_key: str | None,
    model: str | None,
    root: Path,
    max_depth: int,
    _depth: int = 0,
) -> dict:
    """Extract a chunk; if the response is truncated (`finish_reason="length"`)
    or the API rejects the prompt as too large for the model's context window,
    split the chunk in half and recurse.

    Three signals drive the retry, all funnelled through the same code:

    - `finish_reason == "length"` — the model accepted the input but ran out of
      `max_completion_tokens` mid-output. The truncated JSON is unparseable, so
      we discard it and re-extract on smaller inputs that produce shorter
      outputs.

    - context-window-exceeded API errors — the model rejected the input
      outright (HTTP 400 from LM Studio, llama.cpp, vLLM, OpenAI, etc.).
      Without a retry the whole chunk would fail with no output. Splitting in
      half is the same recovery as for the `length` case and works for the
      same reason.

    - hollow successful responses — the model returned HTTP 200 with empty,
      null, or unparseable content (typical of a local Ollama under load).
      `_call_openai_compat` re-labels these as `finish_reason="length"` so they
      take the same recovery path; without that the chunk would be silently
      dropped from the corpus.

    Recursion is capped at `max_depth` to bound worst-case cost. A chunk of N
    files can split into up to 2**max_depth pieces — at depth=3 that's 8x. If
    still failing at the cap, we surface the (likely empty) result with a
    warning rather than infinite-loop.

    A single-file chunk that overflows is unrecoverable here — we can't make
    one file smaller than itself, so we return what we got and warn.
    """
    try:
        result = extract_files_direct(
            chunk, backend=backend, api_key=api_key, model=model, root=root
        )
    except Exception as exc:  # noqa: BLE001 — re-raise unless it's a known context overflow
        if not _looks_like_context_exceeded(exc):
            raise
        if len(chunk) <= 1:
            print(
                f"[graphify] single-file chunk {chunk[0]} exceeds model context "
                f"and cannot be split further: {exc}",
                file=sys.stderr,
            )
            return {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0, "model": model, "finish_reason": "stop"}
        if _depth >= max_depth:
            print(
                f"[graphify] chunk of {len(chunk)} still overflows context at "
                f"recursion depth {_depth} (max {max_depth}) — dropping",
                file=sys.stderr,
            )
            return {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0, "model": model, "finish_reason": "stop"}
        print(
            f"[graphify] chunk of {len(chunk)} exceeded context at depth "
            f"{_depth} ({type(exc).__name__}); splitting in half and retrying",
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
            "model": model,
            "finish_reason": "stop",
        }

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

    # Ollama serves one request at a time per loaded model on a single GPU.
    # Four concurrent 60k-token requests cause VRAM pressure and hollow
    # responses after 3-4 chunks (#798). Force serial unless the user opts in.
    if backend == "ollama" and os.environ.get("GRAPHIFY_OLLAMA_PARALLEL", "").strip() != "1":
        max_concurrency = 1
    # claude-cli shells out to a Claude Code session; parallel subprocesses conflict
    # over session state. Force serial unless the user explicitly opts in.
    if backend == "claude-cli" and os.environ.get("GRAPHIFY_CLAUDE_CLI_PARALLEL", "").strip() != "1":
        max_concurrency = 1
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


def _call_llm(prompt: str, *, backend: str, max_tokens: int = 200) -> str:
    """Send a plain-text prompt to `backend` and return the model's text reply.

    Used by lightweight callers (e.g. `graphify.dedup` LLM tiebreaker) that
    don't need the full extraction prompt or JSON-shaped output. Mirrors the
    backend dispatch logic of `extract_files_direct` but skips the
    `_EXTRACTION_SYSTEM` prompt and JSON parsing.

    Previously `graphify.dedup` imported a `_call_llm` symbol that did not
    exist in this module, so the LLM tiebreaker silently no-op'd on
    `ImportError` (F-038). Adding the function here re-enables it.
    """
    if backend not in BACKENDS:
        raise ValueError(f"Unknown backend {backend!r}")
    cfg = BACKENDS[backend]
    key = _get_backend_api_key(backend)
    if not key and backend == "ollama":
        ollama_url = os.environ.get("OLLAMA_BASE_URL", cfg.get("base_url", ""))
        _validate_ollama_base_url(ollama_url)
        key = "ollama"
    if not key and backend not in ("bedrock", "claude-cli"):
        raise ValueError(
            f"No API key for backend '{backend}'. Set {_format_backend_env_keys(backend)}."
        )
    mdl = _default_model_for_backend(backend)

    if backend == "claude":
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError("anthropic package required for claude backend") from exc
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=mdl,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text if resp.content else ""

    if backend == "claude-cli":
        import shutil, subprocess
        if shutil.which("claude") is None:
            raise RuntimeError("Claude Code CLI not found on $PATH")
        proc = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--no-session-persistence"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"claude -p exited {proc.returncode}: {proc.stderr.strip()[:500]}")
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"claude -p produced unparseable JSON envelope: {exc}") from exc
        return envelope.get("result", "")

    if backend == "bedrock":
        try:
            import boto3
        except ImportError as exc:
            raise ImportError("boto3 required for bedrock backend") from exc
        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
        profile = os.environ.get("AWS_PROFILE")
        session = boto3.Session(profile_name=profile, region_name=region)
        client = session.client("bedrock-runtime")
        resp = client.converse(
            modelId=mdl,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
        )
        return resp.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")

    # OpenAI-compatible (kimi, openai, gemini, ollama)
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("openai package required for this backend") from exc
    client = OpenAI(api_key=key, base_url=cfg["base_url"])
    kwargs: dict = {
        "model": mdl,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": max_tokens,
    }
    temperature = cfg.get("temperature", 0)
    if temperature is not None:
        kwargs["temperature"] = temperature
    if cfg.get("reasoning_effort"):
        kwargs["reasoning_effort"] = cfg["reasoning_effort"]
    if "moonshot" in cfg["base_url"]:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def estimate_cost(backend: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a given token count using published pricing."""
    if backend not in BACKENDS:
        return 0.0
    p = BACKENDS[backend]["pricing"]
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


def _validate_ollama_base_url(url: str) -> None:
    """Warn (do not raise) if OLLAMA_BASE_URL looks unsafe.

    Sending an entire corpus to a non-loopback http:// endpoint silently leaks
    proprietary code; we surface a visible stderr warning instead of failing
    closed (some users genuinely run Ollama on a LAN host they trust).
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
    except Exception:
        print(
            f"[graphify] WARNING: OLLAMA_BASE_URL={url!r} is not a parseable URL.",
            file=sys.stderr,
        )
        return
    if parsed.scheme not in ("http", "https"):
        print(
            f"[graphify] WARNING: OLLAMA_BASE_URL has unexpected scheme {parsed.scheme!r}; "
            "expected http or https.",
            file=sys.stderr,
        )
        return
    host = (parsed.hostname or "").lower()
    is_loopback = host in ("localhost", "127.0.0.1", "::1") or host.startswith("127.")
    if not is_loopback:
        scheme_note = " (UNENCRYPTED)" if parsed.scheme == "http" else ""
        print(
            f"[graphify] WARNING: OLLAMA_BASE_URL points to non-loopback host {host!r}{scheme_note}. "
            "Your full corpus will be sent to that endpoint. "
            "Set OLLAMA_BASE_URL=http://localhost:11434/v1 to keep extraction local.",
            file=sys.stderr,
        )


def detect_backend() -> str | None:
    """Return the name of whichever backend has an API key set, or None.

    Priority: gemini → kimi → claude → openai → bedrock → ollama (last, opt-in).

    Ollama is intentionally checked LAST so a paid API key (Anthropic/OpenAI/etc.)
    is never silently shadowed by an incidental OLLAMA_BASE_URL in the environment
    — see security finding F-002/F-029. Setting OLLAMA_BASE_URL alongside a paid
    key now keeps you on the paid backend; remove the paid key (or pass
    --backend ollama explicitly) to route to the local model.
    """
    for backend in ("gemini", "kimi", "claude", "openai"):
        if _get_backend_api_key(backend):
            return backend
    if os.environ.get("AWS_PROFILE") or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"):
        return "bedrock"
    ollama_url = os.environ.get("OLLAMA_BASE_URL")
    if ollama_url:
        _validate_ollama_base_url(ollama_url)
        return "ollama"
    return None
