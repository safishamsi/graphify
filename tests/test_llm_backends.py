"""Tests for direct semantic-extraction backend selection."""

from pathlib import Path
from unittest.mock import patch

import pytest

from graphify import llm


def _clear_backend_env(monkeypatch):
    for env_key in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "MOONSHOT_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(env_key, raising=False)


def test_gemini_accepts_gemini_api_key(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    assert llm.detect_backend() == "gemini"
    assert llm._get_backend_api_key("gemini") == "gemini-key"


def test_gemini_accepts_google_api_key(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")

    assert llm.detect_backend() == "gemini"
    assert llm._get_backend_api_key("gemini") == "google-key"


def test_backend_detection_prefers_gemini(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    assert llm.detect_backend() == "gemini"


def test_openai_backend_detected(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    assert llm.detect_backend() == "openai"
    assert llm._get_backend_api_key("openai") == "openai-key"


def test_extract_files_direct_routes_gemini_through_openai_compat(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    source = tmp_path / "note.md"
    source.write_text("# Architecture\n\nThe runner emits a snapshot.\n")
    result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    with patch("graphify.llm._call_openai_compat", return_value=result) as call:
        assert llm.extract_files_direct([source], backend="gemini", root=tmp_path) is result

    assert call.call_args.args[:4] == (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "google-key",
        "gemini-3-flash-preview",
        "=== note.md ===\n# Architecture\n\nThe runner emits a snapshot.\n",
    )
    assert call.call_args.kwargs["temperature"] == 0
    assert call.call_args.kwargs["reasoning_effort"] == "low"
    assert call.call_args.kwargs["max_completion_tokens"] == 16384


def test_gemini_model_can_be_overridden_by_env(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    monkeypatch.setenv("GRAPHIFY_GEMINI_MODEL", "gemini-3.1-pro-preview")
    source = tmp_path / "note.md"
    source.write_text("# Architecture\n")
    result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    with patch("graphify.llm._call_openai_compat", return_value=result) as call:
        llm.extract_files_direct([source], backend="gemini", root=tmp_path)

    assert call.call_args.args[2] == "gemini-3.1-pro-preview"


def test_missing_gemini_key_names_both_supported_env_vars(monkeypatch):
    _clear_backend_env(monkeypatch)

    with pytest.raises(ValueError) as exc:
        llm.extract_files_direct([Path("missing.md")], backend="gemini")

    assert "GEMINI_API_KEY or GOOGLE_API_KEY" in str(exc.value)


# ---------------------------------------------------------------------------
# Adaptive retry: context-window overflow recovery
# ---------------------------------------------------------------------------


def _ok(nodes=None, edges=None, model="m"):
    return {
        "nodes": nodes or [],
        "edges": edges or [],
        "hyperedges": [],
        "input_tokens": 1,
        "output_tokens": 1,
        "model": model,
        "finish_reason": "stop",
    }


def test_looks_like_context_exceeded_matches_common_messages():
    msgs = [
        "Error code: 400 - {'error': 'Context size has been exceeded.'}",
        "n_keep: 22374 >= n_ctx: 4096",
        "context_length_exceeded: This model's maximum context length is 8192 tokens",
        "exceeds the available context size",
        "The prompt is too long for this model.",
    ]
    for m in msgs:
        assert llm._looks_like_context_exceeded(RuntimeError(m)), m


def test_looks_like_context_exceeded_ignores_unrelated_errors():
    for m in ["timeout", "rate limit", "401 unauthorized", "connection refused"]:
        assert not llm._looks_like_context_exceeded(RuntimeError(m)), m


def test_adaptive_retry_splits_on_context_exceeded(tmp_path):
    files = [tmp_path / f"f{i}.md" for i in range(4)]
    for f in files:
        f.write_text("hello")

    calls = {"n": 0}

    def fake_extract(chunk, *_, **__):
        calls["n"] += 1
        # First call (whole chunk) fails with context overflow; recursive
        # halves succeed. This is the same shape LM Studio / vLLM / OpenAI
        # produce when a chunk overflows the model's context window.
        if len(chunk) == 4:
            raise RuntimeError("Error 400: Context size has been exceeded.")
        return _ok(nodes=[{"id": f.stem} for f in chunk])

    with patch("graphify.llm.extract_files_direct", side_effect=fake_extract):
        result = llm._extract_with_adaptive_retry(
            files, backend="kimi", api_key="k", model="m", root=tmp_path, max_depth=3
        )

    assert len(result["nodes"]) == 4
    assert calls["n"] == 3  # 1 failure + 2 halves


def test_adaptive_retry_gives_up_on_single_file_overflow(tmp_path):
    f = tmp_path / "huge.md"
    f.write_text("x")

    def fake_extract(*_, **__):
        raise RuntimeError("context_length_exceeded")

    with patch("graphify.llm.extract_files_direct", side_effect=fake_extract):
        result = llm._extract_with_adaptive_retry(
            [f], backend="kimi", api_key="k", model="m", root=tmp_path, max_depth=3
        )

    # Single-file overflow returns an empty fragment instead of raising — the
    # caller can keep going on the rest of the corpus.
    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["finish_reason"] == "stop"


def test_adaptive_retry_re_raises_unrelated_errors(tmp_path):
    f = tmp_path / "f.md"
    f.write_text("x")

    def fake_extract(*_, **__):
        raise RuntimeError("rate limit hit")

    with patch("graphify.llm.extract_files_direct", side_effect=fake_extract):
        with pytest.raises(RuntimeError, match="rate limit"):
            llm._extract_with_adaptive_retry(
                [f], backend="kimi", api_key="k", model="m", root=tmp_path, max_depth=3
            )
