"""Tests for the `claude-cli` backend (#855/#856).

Mocks subprocess.run + shutil.which so the suite runs on CI without
the `claude` binary or a live network call.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from graphify import llm

_ENVELOPE = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": json.dumps({
        "nodes": [
            {"id": "foo_module", "label": "Foo", "file_type": "document", "source_file": "foo.md"},
            {"id": "foo_greet", "label": "greet", "file_type": "code", "source_file": "foo.md"},
        ],
        "edges": [
            {"source": "foo_module", "target": "foo_greet",
             "relation": "references", "confidence": "EXTRACTED", "confidence_score": 1.0},
        ],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }),
    "stop_reason": "end_turn",
    "usage": {
        "input_tokens": 6,
        "output_tokens": 11,
        "cache_read_input_tokens": 17837,
        "cache_creation_input_tokens": 30800,
    },
    "modelUsage": {"claude-opus-4-7[1m]": {"inputTokens": 6, "outputTokens": 11}},
}


@pytest.fixture
def fake_claude(monkeypatch):
    completed = MagicMock(returncode=0, stdout=json.dumps(_ENVELOPE), stderr="")
    monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)
    with patch("shutil.which", return_value="/fake/bin/claude"), \
         patch("subprocess.run", return_value=completed) as run:
        yield run


def test_returns_parsed_nodes_and_edges(fake_claude):
    result = llm._call_claude_cli("dummy", max_tokens=8192)
    assert len(result["nodes"]) == 2
    assert len(result["edges"]) == 1


def test_token_accounting_includes_cache(fake_claude):
    result = llm._call_claude_cli("dummy", max_tokens=8192)
    assert result["input_tokens"] == 6 + 17837 + 30800
    assert result["output_tokens"] == 11
    assert result["model"] == "claude-opus-4-7[1m]"
    assert result["finish_reason"] == "stop"


def test_finish_reason_length_on_max_tokens(monkeypatch):
    envelope = dict(_ENVELOPE, stop_reason="max_tokens")
    completed = MagicMock(returncode=0, stdout=json.dumps(envelope), stderr="")
    monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)
    with patch("shutil.which", return_value="/fake/bin/claude"), \
         patch("subprocess.run", return_value=completed):
        result = llm._call_claude_cli("dummy", max_tokens=8192)
    assert result["finish_reason"] == "length"


def test_raises_when_cli_missing():
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="Claude Code CLI not found"):
            llm._call_claude_cli("dummy", max_tokens=8192)


def test_raises_on_nonzero_exit():
    completed = MagicMock(returncode=2, stdout="", stderr="auth failed")
    with patch("shutil.which", return_value="/fake/bin/claude"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="exited 2"):
            llm._call_claude_cli("dummy", max_tokens=8192)


def test_raises_on_garbage_envelope():
    completed = MagicMock(returncode=0, stdout="not json", stderr="")
    with patch("shutil.which", return_value="/fake/bin/claude"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="unparseable JSON envelope"):
            llm._call_claude_cli("dummy", max_tokens=8192)


def test_extract_files_direct_dispatches_to_claude_cli(tmp_path, fake_claude):
    f = tmp_path / "foo.md"
    f.write_text("# Foo\n\nThe greet() helper formats a name.\n")
    result = llm.extract_files_direct(files=[f], backend="claude-cli", root=tmp_path)
    assert fake_claude.called
    assert len(result["nodes"]) == 2


def test_backend_registered_with_zero_cost():
    assert "claude-cli" in llm.BACKENDS
    pricing = llm.BACKENDS["claude-cli"]["pricing"]
    assert pricing["input"] == 0.0
    assert pricing["output"] == 0.0
    assert llm.estimate_cost("claude-cli", 1_000_000, 1_000_000) == 0.0


def test_no_session_persistence_flag_in_subprocess(fake_claude):
    llm._call_claude_cli("dummy", max_tokens=8192)
    call_args = fake_claude.call_args[0][0]
    assert "--no-session-persistence" in call_args
