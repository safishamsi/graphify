import os
import sys
from graphify.llm.core import _EXTRACTION_SYSTEM, _parse_llm_json, _response_is_hollow, _CHARS_PER_TOKEN

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
    if not resp.choices or resp.choices[0].message is None:
        raise ValueError("LLM returned empty or filtered response")
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
