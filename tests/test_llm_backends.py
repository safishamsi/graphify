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
