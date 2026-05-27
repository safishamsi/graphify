"""Tests for --mode deep / deep_mode semantic extraction."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from graphify import llm


def test_extraction_system_default_has_no_deep_suffix():
    assert "DEEP_MODE" not in llm._extraction_system(deep=False)
    assert llm._extraction_system(deep=False) == llm._EXTRACTION_SYSTEM


def test_extraction_system_deep_appends_deep_mode_instructions():
    deep = llm._extraction_system(deep=True)
    assert deep.startswith(llm._EXTRACTION_SYSTEM)
    assert "DEEP_MODE" in deep
    assert "INFERRED" in deep


def test_extract_files_direct_passes_deep_mode_to_openai_compat(tmp_path):
    source = tmp_path / "note.md"
    source.write_text("# Notes\n")
    result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    with patch("graphify.llm._call_openai_compat", return_value=result) as call:
        llm.extract_files_direct(
            [source],
            backend="gemini",
            api_key="test-key",
            root=tmp_path,
            deep_mode=True,
        )

    assert call.call_args.kwargs["deep_mode"] is True


def test_extract_files_direct_passes_deep_mode_to_claude(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    source = tmp_path / "note.md"
    source.write_text("# Notes\n")
    result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    with patch("graphify.llm._call_claude", return_value=result) as call:
        llm.extract_files_direct([source], backend="claude", root=tmp_path, deep_mode=True)

    assert call.call_args.kwargs["deep_mode"] is True


def test_extract_files_direct_passes_deep_mode_to_claude_cli(tmp_path):
    source = tmp_path / "note.md"
    source.write_text("# Notes\n")
    result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    with patch("graphify.llm._call_claude_cli", return_value=result) as call:
        llm.extract_files_direct([source], backend="claude-cli", root=tmp_path, deep_mode=True)

    assert call.call_args.kwargs["deep_mode"] is True


def test_extract_files_direct_passes_deep_mode_to_bedrock(tmp_path):
    source = tmp_path / "note.md"
    source.write_text("# Notes\n")
    result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    with patch("graphify.llm._call_bedrock", return_value=result) as call:
        llm.extract_files_direct([source], backend="bedrock", root=tmp_path, deep_mode=True)

    assert call.call_args.kwargs["deep_mode"] is True


def test_extract_corpus_parallel_threads_deep_mode(tmp_path):
    source = tmp_path / "note.md"
    source.write_text("# Notes\n")
    seen: list[bool] = []

    def _fake_extract(chunk, **kwargs):
        seen.append(kwargs.get("deep_mode", False))
        return {
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 0,
            "output_tokens": 0,
            "finish_reason": "stop",
        }

    with patch("graphify.llm.extract_files_direct", side_effect=_fake_extract):
        llm.extract_corpus_parallel(
            [source],
            backend="kimi",
            root=tmp_path,
            token_budget=None,
            chunk_size=1,
            max_concurrency=1,
            deep_mode=True,
        )

    assert seen == [True]


def test_call_openai_compat_system_message_includes_deep_mode_when_enabled():
    captured: dict = {}

    class _FakeCompletions:
        def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            choice = type("Choice", (), {})()
            choice.message = type("Msg", (), {"content": '{"nodes":[],"edges":[],"hyperedges":[]}'})()
            choice.finish_reason = "stop"
            resp = type("Resp", (), {})()
            resp.choices = [choice]
            resp.usage = type("Usage", (), {"prompt_tokens": 1, "completion_tokens": 1})()
            return resp

    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        chat = type("Chat", (), {"completions": _FakeCompletions()})()

    fake_openai = type("openai", (), {"OpenAI": _FakeClient})

    with patch.dict("sys.modules", {"openai": fake_openai}):
        llm._call_openai_compat(
            "https://example.com/v1",
            "key",
            "model",
            "user content",
            backend="openai",
            deep_mode=True,
        )

    assert "DEEP_MODE" in captured["messages"][0]["content"]


def test_call_claude_cli_appends_deep_system_prompt_to_command():
    captured: dict = {}

    def _fake_run(args, **kwargs):
        captured["args"] = args
        class _Proc:
            returncode = 0
            stderr = ""
            stdout = '{"result":"{\\"nodes\\":[],\\"edges\\":[],\\"hyperedges\\":[]}","usage":{}}'
        return _Proc()

    with patch("shutil.which", return_value="/usr/bin/claude"):
        with patch("subprocess.run", side_effect=_fake_run):
            llm._call_claude_cli("user message", deep_mode=True)

    assert "--append-system-prompt" in captured["args"]
    prompt = captured["args"][captured["args"].index("--append-system-prompt") + 1]
    assert "DEEP_MODE" in prompt


def test_call_bedrock_includes_deep_system_prompt():
    captured: dict = {}

    class _FakeClient:
        def converse(self, **kwargs):
            captured["system"] = kwargs["system"]
            return {
                "output": {"message": {"content": [{"text": '{"nodes":[],"edges":[],"hyperedges":[]}'}]}},
                "usage": {"inputTokens": 1, "outputTokens": 1},
                "stopReason": "end_turn",
            }

    class _FakeSession:
        def __init__(self, profile_name=None, region_name=None):
            pass

        def client(self, _service):
            return _FakeClient()

    fake_boto3 = type("boto3", (), {"Session": _FakeSession})
    fake_botocore = type("botocore", (), {"exceptions": type("exceptions", (), {"ClientError": Exception})})

    with patch.dict("sys.modules", {"boto3": fake_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore.exceptions}):
        llm._call_bedrock("model", "user message", deep_mode=True)

    assert "DEEP_MODE" in captured["system"][0]["text"]
