"""Tests for the Ollama backend additions in graphify/llm.py."""
from __future__ import annotations

from graphify.llm import detect_backend, BACKENDS


def test_ollama_in_backends():
    assert "ollama" in BACKENDS
    assert BACKENDS["ollama"]["pricing"]["input"] == 0.0
    assert BACKENDS["ollama"]["pricing"]["output"] == 0.0
    assert "max_tokens" in BACKENDS["ollama"]


def test_detect_backend_ollama(monkeypatch):
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    assert detect_backend() == "ollama"


def test_detect_backend_kimi_beats_ollama(monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert detect_backend() == "kimi"


def test_detect_backend_claude_beats_ollama(monkeypatch):
    # ANTHROPIC_API_KEY (paid, intentional) should win over OLLAMA_BASE_URL
    # (env-driven, easy to set accidentally) -- security fix F-002/F-029.
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert detect_backend() == "claude"


def test_detect_backend_none_without_envvars(monkeypatch):
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert detect_backend() is None


def test_ollama_api_key_sentinel(monkeypatch):
    """extract_files_direct with backend=ollama and no OLLAMA_API_KEY should use sentinel 'ollama' not raise."""
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    from unittest.mock import patch
    from pathlib import Path
    import tempfile

    fake_result = {
        "nodes": [],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 10,
        "finish_reason": "stop",
    }
    with patch("graphify.llm._call_openai_compat", return_value=fake_result) as mock_call:
        from graphify.llm import extract_files_direct
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1\n")
            tmp = Path(f.name)
        try:
            extract_files_direct([tmp], backend="ollama", root=tmp.parent)
            # Should have called _call_openai_compat with api_key="ollama"
            assert mock_call.called
            call_kwargs = mock_call.call_args
            api_key_used = call_kwargs.args[1] if call_kwargs.args else call_kwargs.kwargs.get("api_key", "")
            assert api_key_used == "ollama"
        finally:
            tmp.unlink(missing_ok=True)
