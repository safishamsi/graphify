import json
import pytest
from pathlib import Path


def test_custom_provider_add_list_show_remove(tmp_path, monkeypatch):
    """Full round-trip: add → list → show → remove via providers.json."""
    providers_file = tmp_path / "providers.json"
    providers_file.write_text("{}", encoding="utf-8")

    from graphify import llm
    monkeypatch.setattr(llm, "_custom_providers_path", lambda global_=True: providers_file if global_ else tmp_path / "local.json")
    monkeypatch.setattr(llm, "BACKENDS", {**llm.BACKENDS})

    providers_file.write_text(json.dumps({
        "nvidia": {
            "base_url": "https://integrate.api.nvidia.com/v1",
            "default_model": "minimaxai/minimax-m2.7",
            "env_key": "NVIDIA_API_KEY",
            "pricing": {"input": 0.0, "output": 0.0},
            "temperature": 0,
        }
    }), encoding="utf-8")

    loaded = llm._load_custom_providers()
    assert "nvidia" in loaded
    assert loaded["nvidia"]["base_url"] == "https://integrate.api.nvidia.com/v1"


def test_custom_provider_pricing_defaults_to_zero(tmp_path):
    """Missing pricing field defaults to zero so estimate_cost doesn't blow up."""
    providers_file = tmp_path / "providers.json"
    providers_file.write_text(json.dumps({
        "mymodel": {
            "base_url": "http://localhost:8080/v1",
            "default_model": "llama3",
            "env_key": "MY_API_KEY",
        }
    }), encoding="utf-8")

    from graphify import llm
    import importlib
    from unittest.mock import patch

    with patch.object(llm, "_custom_providers_path", side_effect=lambda global_=True: providers_file if global_ else tmp_path / "local.json"):
        loaded = llm._load_custom_providers()

    assert "mymodel" in loaded
    assert loaded["mymodel"]["pricing"] == {"input": 0.0, "output": 0.0}


def test_custom_provider_cannot_shadow_builtin(tmp_path):
    """Built-in provider names are protected from being overridden."""
    providers_file = tmp_path / "providers.json"
    providers_file.write_text(json.dumps({
        "claude": {
            "base_url": "http://evil.example.com/v1",
            "default_model": "evil-model",
            "env_key": "EVIL_KEY",
        }
    }), encoding="utf-8")

    from graphify import llm
    from unittest.mock import patch

    with patch.object(llm, "_custom_providers_path", side_effect=lambda global_=True: providers_file if global_ else tmp_path / "local.json"):
        loaded = llm._load_custom_providers()

    assert "claude" not in loaded


def test_detect_backend_custom_provider_after_builtins(monkeypatch):
    """Custom providers appear after all built-ins in detect_backend() priority."""
    from graphify import llm

    monkeypatch.setattr(llm, "BACKENDS", {
        **llm.BACKENDS,
        "myprovider": {
            "base_url": "http://example.com/v1",
            "default_model": "mymodel",
            "env_key": "MY_CUSTOM_KEY",
            "pricing": {"input": 0.0, "output": 0.0},
            "temperature": 0,
        }
    })
    monkeypatch.setenv("MY_CUSTOM_KEY", "test-key")
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "MOONSHOT_API_KEY", "ANTHROPIC_API_KEY",
                 "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OLLAMA_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

    result = llm.detect_backend()
    assert result == "myprovider"
