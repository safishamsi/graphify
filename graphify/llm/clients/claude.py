import json
import sys
from graphify.llm.core import _EXTRACTION_SYSTEM, _parse_llm_json, _response_is_hollow

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
        encoding="utf-8",  # Force UTF-8 — prevents UnicodeEncodeError on Windows cp1252
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
