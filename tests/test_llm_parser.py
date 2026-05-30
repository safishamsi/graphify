"""Tests for `_parse_llm_json` robustness and the `_call_claude_cli`
subprocess argv shape introduced in the hollow-response fix.

These tests cover:
- The four parser failure modes described in PR #1062
- The switch from --append-system-prompt to --system-prompt
- The GRAPHIFY_CLAUDE_CLI_MODEL env-var passthrough
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from graphify import llm


# ---------- _parse_llm_json: the four canonical failure modes ----------


def test_preamble_then_fence_is_parsed():
    """Claude often prefixes the JSON with a short preamble before the
    ```json fence. The original parser only stripped fences at offset 0,
    so any preamble caused json.loads to fail and the chunk to be
    dropped as a hollow response. The robust parser handles fences
    anywhere in the text."""
    raw = (
        "Here are the extracted entities:\n\n"
        '```json\n{"nodes": [{"id": "a"}], "edges": []}\n```'
    )
    result = llm._parse_llm_json(raw)
    assert result["nodes"] == [{"id": "a"}]
    assert result["edges"] == []


def test_prose_wrapped_json_without_fence_is_parsed():
    """Some models return prose around bare JSON with no markdown fence.
    The balanced-brace fallback extracts the first complete object."""
    raw = (
        'The extracted graph is {"nodes": [{"id": "b"}], "edges": []}. '
        "Hope this helps!"
    )
    result = llm._parse_llm_json(raw)
    assert result["nodes"] == [{"id": "b"}]


def test_raw_json_still_works():
    """Regression: clean JSON input (the original happy path) must keep
    parsing exactly as before."""
    raw = '{"nodes": [], "edges": [], "hyperedges": []}'
    result = llm._parse_llm_json(raw)
    assert result == {"nodes": [], "edges": [], "hyperedges": []}


def test_total_refusal_returns_empty_fragment():
    """When the model refuses or returns unrelated prose, the parser
    must degrade gracefully — return the empty fragment so the hollow
    detector takes over, never raise."""
    raw = "I cannot extract structured data from this content."
    result = llm._parse_llm_json(raw)
    assert result == {"nodes": [], "edges": [], "hyperedges": []}


# ---------- _parse_llm_json: secondary cases worth pinning ----------


def test_fence_with_uppercase_language_tag():
    raw = '```JSON\n{"nodes": [{"id": "x"}], "edges": []}\n```'
    result = llm._parse_llm_json(raw)
    assert result["nodes"] == [{"id": "x"}]


def test_fence_without_closing_backticks():
    """Truncated response: the model started the fence but ran out of
    tokens before closing it. We should still recover the JSON body."""
    raw = '```json\n{"nodes": [{"id": "y"}], "edges": []}'
    result = llm._parse_llm_json(raw)
    assert result["nodes"] == [{"id": "y"}]


def test_empty_response_returns_empty_fragment():
    assert llm._parse_llm_json("") == {"nodes": [], "edges": [], "hyperedges": []}


# ---------- _call_claude_cli: argv shape ----------


def _make_envelope(result_obj: dict) -> str:
    return json.dumps({
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": json.dumps(result_obj),
        "usage": {"input_tokens": 1, "output_tokens": 1,
                  "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        "modelUsage": {"claude-opus-4-7": {}},
        "stop_reason": "end_turn",
    })


@patch("shutil.which", return_value="/usr/local/bin/claude")
@patch("subprocess.run")
def test_uses_system_prompt_not_append(mock_run, _which):
    """The hollow-response root cause was --append-system-prompt
    layering graphify's extraction prompt on top of Claude Code's
    default interactive-agent prompt. The fix switches to
    --system-prompt (replace) to eliminate the conflict."""
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = _make_envelope({"nodes": [], "edges": [], "hyperedges": []})
    mock_run.return_value.stderr = ""
    llm._call_claude_cli("payload")
    argv = mock_run.call_args.args[0]
    assert "--system-prompt" in argv, f"--system-prompt missing from argv: {argv}"
    assert "--append-system-prompt" not in argv, (
        "--append-system-prompt should have been replaced — it's the root "
        "cause of the hollow-response loop"
    )


@patch("shutil.which", return_value="/usr/local/bin/claude")
@patch("subprocess.run")
def test_model_env_var_adds_model_flag(mock_run, _which, monkeypatch):
    """GRAPHIFY_CLAUDE_CLI_MODEL must be forwarded to claude -p --model."""
    monkeypatch.setenv("GRAPHIFY_CLAUDE_CLI_MODEL", "haiku")
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = _make_envelope({"nodes": [], "edges": [], "hyperedges": []})
    mock_run.return_value.stderr = ""
    llm._call_claude_cli("payload")
    argv = mock_run.call_args.args[0]
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "haiku"


@patch("shutil.which", return_value="/usr/local/bin/claude")
@patch("subprocess.run")
def test_no_model_flag_when_env_var_unset(mock_run, _which, monkeypatch):
    """Default behaviour: when the env var is not set, --model is not
    added so claude-cli's own default kicks in."""
    monkeypatch.delenv("GRAPHIFY_CLAUDE_CLI_MODEL", raising=False)
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = _make_envelope({"nodes": [], "edges": [], "hyperedges": []})
    mock_run.return_value.stderr = ""
    llm._call_claude_cli("payload")
    argv = mock_run.call_args.args[0]
    assert "--model" not in argv
