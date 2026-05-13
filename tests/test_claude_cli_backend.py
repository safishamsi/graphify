"""Tests for the `claude-cli` backend.

This backend shells out to the locally-installed Claude Code CLI (`claude -p`)
so Pro/Max subscribers can run graphify's semantic pass without provisioning
a separate ANTHROPIC_API_KEY. Tests here mock subprocess.run so they do not
require the `claude` binary or a live network call.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from graphify import llm


CLAUDE_ENVELOPE = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": json.dumps({
        "nodes": [
            {"id": "foo_module", "label": "Foo module", "file_type": "document",
             "source_file": "foo.md"},
            {"id": "foo_greet", "label": "greet", "file_type": "code",
             "source_file": "foo.md"},
        ],
        "edges": [
            {"source": "foo_module", "target": "foo_greet",
             "relation": "references", "confidence": "EXTRACTED"},
        ],
    }),
    "stop_reason": "end_turn",
    "usage": {
        "input_tokens": 6,
        "output_tokens": 11,
        "cache_read_input_tokens": 17837,
        "cache_creation_input_tokens": 30800,
    },
    "modelUsage": {
        "claude-opus-4-7[1m]": {
            "inputTokens": 6, "outputTokens": 11,
            "costUSD": 0.2017235,
        }
    },
}


@pytest.fixture
def fake_claude(monkeypatch):
    """Patch shutil.which + subprocess.run so the backend looks like it has a real CLI."""
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = json.dumps(CLAUDE_ENVELOPE)
    completed.stderr = ""
    monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)
    with patch("shutil.which", return_value="/fake/bin/claude"), \
         patch("subprocess.run", return_value=completed) as run:
        yield run


def test_call_claude_cli_returns_parsed_result(fake_claude):
    result = llm._call_claude_cli("dummy user message", max_tokens=8192)
    assert len(result["nodes"]) == 2
    assert len(result["edges"]) == 1
    # Total input tokens = fresh + cache_read + cache_creation (the model processed all of it).
    assert result["input_tokens"] == 6 + 17837 + 30800
    assert result["output_tokens"] == 11
    assert result["model"] == "claude-opus-4-7[1m]"
    assert result["finish_reason"] == "stop"


def test_call_claude_cli_finish_reason_length_on_max_tokens(monkeypatch):
    envelope = dict(CLAUDE_ENVELOPE, stop_reason="max_tokens")
    completed = MagicMock(returncode=0, stdout=json.dumps(envelope), stderr="")
    monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)
    with patch("shutil.which", return_value="/fake/bin/claude"), \
         patch("subprocess.run", return_value=completed):
        result = llm._call_claude_cli("dummy", max_tokens=8192)
    assert result["finish_reason"] == "length"


def test_call_claude_cli_raises_when_cli_missing():
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="Claude Code CLI not found"):
            llm._call_claude_cli("dummy", max_tokens=8192)


def test_call_claude_cli_raises_on_nonzero_exit(monkeypatch):
    completed = MagicMock(returncode=2, stdout="", stderr="auth failed")
    with patch("shutil.which", return_value="/fake/bin/claude"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="exited 2"):
            llm._call_claude_cli("dummy", max_tokens=8192)


def test_call_claude_cli_raises_on_garbage_envelope(monkeypatch):
    completed = MagicMock(returncode=0, stdout="not json", stderr="")
    with patch("shutil.which", return_value="/fake/bin/claude"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="unparseable JSON envelope"):
            llm._call_claude_cli("dummy", max_tokens=8192)


def test_extract_files_direct_dispatches_to_claude_cli(tmp_path, fake_claude):
    """End-to-end through the public extract_files_direct entrypoint — backend dispatch
    must route to `_call_claude_cli` without requiring an ANTHROPIC_API_KEY."""
    f = tmp_path / "foo.md"
    f.write_text("# Foo module\n\nThe greet() helper formats a name.\n")
    result = llm.extract_files_direct(
        files=[f], backend="claude-cli", root=tmp_path,
    )
    assert fake_claude.called
    assert len(result["nodes"]) == 2


def test_claude_cli_backend_registered_with_zero_cost():
    """Pricing must be zero for cost estimation — calls bill against the user's plan,
    not an API key, so the per-call cost is zero from graphify's perspective."""
    assert "claude-cli" in llm.BACKENDS
    pricing = llm.BACKENDS["claude-cli"]["pricing"]
    assert pricing["input"] == 0.0
    assert pricing["output"] == 0.0
    assert llm.estimate_cost("claude-cli", 1_000_000, 1_000_000) == 0.0
