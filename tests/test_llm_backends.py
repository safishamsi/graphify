"""Tests for direct semantic-extraction backend selection."""

from pathlib import Path
from unittest.mock import MagicMock, patch

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
    pytest.importorskip('openai')
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    source = tmp_path / "note.md"
    source.write_text("# Architecture\n\nThe runner emits a snapshot.\n")
    expected_json = '{"nodes":[],"edges":[],"hyperedges":[]}'

    with patch("openai.OpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        mock_resp = mock_client.chat.completions.create.return_value
        mock_resp.choices = [type("Choice", (), {
            "message": type("Msg", (), {"content": expected_json})(),
            "finish_reason": "stop",
        })()]
        mock_resp.usage = type("Usage", (), {"prompt_tokens": 1, "completion_tokens": 1})()

        result = llm.extract_files_direct([source], backend="gemini", root=tmp_path)
        assert result["nodes"] == []
        assert result["edges"] == []

    # Verify OpenAI client was created with correct base_url and api_key
    assert mock_openai.call_args.kwargs["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert mock_openai.call_args.kwargs["api_key"] == "google-key"
    # Verify chat.completions.create arguments
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gemini-3-flash-preview"
    assert call_kwargs["temperature"] == 0
    assert call_kwargs["reasoning_effort"] == "low"
    assert call_kwargs["max_completion_tokens"] == 16384
    assert "=== note.md ===" in call_kwargs["messages"][1]["content"]


def test_gemini_model_can_be_overridden_by_env(tmp_path, monkeypatch):
    pytest.importorskip('openai')
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    monkeypatch.setenv("GRAPHIFY_GEMINI_MODEL", "gemini-3.1-pro-preview")
    source = tmp_path / "note.md"
    source.write_text("# Architecture\n")
    expected_json = '{"nodes":[],"edges":[],"hyperedges":[]}'

    with patch("openai.OpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        mock_resp = mock_client.chat.completions.create.return_value
        mock_resp.choices = [type("Choice", (), {
            "message": type("Msg", (), {"content": expected_json})(),
            "finish_reason": "stop",
        })()]
        mock_resp.usage = type("Usage", (), {"prompt_tokens": 1, "completion_tokens": 1})()
        llm.extract_files_direct([source], backend="gemini", root=tmp_path)

    assert mock_client.chat.completions.create.call_args.kwargs["model"] == "gemini-3.1-pro-preview"


def test_missing_gemini_key_names_both_supported_env_vars(monkeypatch):
    _clear_backend_env(monkeypatch)

    with pytest.raises(ValueError) as exc:
        llm.extract_files_direct([Path("missing.md")], backend="gemini")

    assert "GEMINI_API_KEY or GOOGLE_API_KEY" in str(exc.value)


# ---------------------------------------------------------------------------
# Additional backend detection
# ---------------------------------------------------------------------------

def test_kimi_backend_detected(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("MOONSHOT_API_KEY", "kimi-key")
    assert llm.detect_backend() == "kimi"
    assert llm._get_backend_api_key("kimi") == "kimi-key"


def test_claude_backend_detected(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-key")
    assert llm.detect_backend() == "claude"


def test_no_backend_returns_none(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    assert llm.detect_backend() is None


def test_ollama_backend_via_env(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    assert llm.detect_backend() == "ollama"


def test_bedrock_backend_via_aws_profile(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("AWS_PROFILE", "myprofile")
    assert llm.detect_backend() == "bedrock"


def test_backend_prefers_gemini_over_ollama(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    assert llm.detect_backend() == "gemini"


# ---------------------------------------------------------------------------
# _backend_env_keys / _get_backend_api_key
# ---------------------------------------------------------------------------

def test_backend_env_keys_openai():
    keys = llm._backend_env_keys("openai")
    assert "OPENAI_API_KEY" in keys


def test_backend_env_keys_unknown():
    with pytest.raises(KeyError):
        llm._backend_env_keys("nonexistent")


def test_get_backend_api_key_empty(monkeypatch):
    _clear_backend_env(monkeypatch)
    assert llm._get_backend_api_key("openai") == ""


# ---------------------------------------------------------------------------
# _parse_llm_json
# ---------------------------------------------------------------------------

def test_parse_llm_json_plain():
    result = llm._parse_llm_json('{"nodes": [{"id": "a"}], "edges": [], "hyperedges": []}')
    assert result["nodes"] == [{"id": "a"}]


def test_parse_llm_json_with_fences():
    raw = '```json\n{"nodes": [], "edges": [], "hyperedges": []}\n```'
    result = llm._parse_llm_json(raw)
    assert result["nodes"] == []


def test_parse_llm_json_invalid():
    result = llm._parse_llm_json("not json at all")
    assert result == {"nodes": [], "edges": [], "hyperedges": []}


# ---------------------------------------------------------------------------
# _call_llm mock
# ---------------------------------------------------------------------------

def test_call_llm_unknown_backend():
    with pytest.raises(ValueError, match="Unknown backend"):
        llm._call_llm("test prompt", backend="nonexistent")


def test_call_llm_missing_key(monkeypatch):
    _clear_backend_env(monkeypatch)
    with pytest.raises(ValueError, match="No API key"):
        llm._call_llm("test prompt", backend="openai")


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------

def test_estimate_cost_openai():
    cost = llm.estimate_cost("openai", 1000, 500)
    # OpenAI: $0.40/1M input, $1.60/1M output (actual pricing in BACKENDS)
    expected = (1000 * 0.4 + 500 * 1.6) / 1_000_000
    assert cost == pytest.approx(expected)


def test_estimate_cost_unknown_backend():
    assert llm.estimate_cost("nonexistent", 1000, 500) == 0.0


# ---------------------------------------------------------------------------
# _validate_ollama_base_url
# ---------------------------------------------------------------------------

def test_validate_ollama_localhost_ok(capsys):
    llm._validate_ollama_base_url("http://localhost:11434/v1")
    out, err = capsys.readouterr()
    assert "WARNING" not in out
    assert "WARNING" not in err


def test_validate_ollama_loopback_ok(capsys):
    llm._validate_ollama_base_url("http://127.0.0.1:11434/v1")
    out, err = capsys.readouterr()
    assert "WARNING" not in out
    assert "WARNING" not in err


def test_validate_ollama_remote_warns(capsys):
    llm._validate_ollama_base_url("http://192.168.1.100:11434/v1")
    _, err = capsys.readouterr()
    assert "WARNING" in err
    assert "non-loopback" in err


def test_validate_ollama_unexpected_scheme_warns(capsys):
    llm._validate_ollama_base_url("ftp://localhost:11434/v1")
    _, err = capsys.readouterr()
    assert "WARNING" in err
    assert "unexpected scheme" in err


def test_validate_ollama_unparseable_warns(capsys):
    llm._validate_ollama_base_url("not a url at all !!!")
    _, err = capsys.readouterr()
    assert "WARNING" in err


# ---------------------------------------------------------------------------
# _merge_into
# ---------------------------------------------------------------------------

def test_merge_into_basic():
    merged = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    llm._merge_into(merged, {"nodes": [{"id": "a"}], "edges": [{"source": "a", "target": "b"}], "hyperedges": [], "input_tokens": 10, "output_tokens": 20})
    assert merged["nodes"] == [{"id": "a"}]
    assert merged["edges"] == [{"source": "a", "target": "b"}]
    assert merged["input_tokens"] == 10
    assert merged["output_tokens"] == 20


def test_merge_into_empty_result():
    merged = {"nodes": [{"id": "x"}], "edges": [], "hyperedges": [], "input_tokens": 5, "output_tokens": 3}
    llm._merge_into(merged, {})
    assert merged["nodes"] == [{"id": "x"}]  # unchanged


# ---------------------------------------------------------------------------
# _call_llm - ollama no-key fallback path
# ---------------------------------------------------------------------------

def test_call_llm_ollama_no_key(capsys, monkeypatch):
    """_call_llm with ollama and no OLLAMA_API_KEY uses placeholder key."""
    pytest.importorskip('openai')
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    with patch("openai.OpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        mock_resp = mock_client.chat.completions.create.return_value
        mock_resp.choices = [type("Choice", (), {"message": type("Msg", (), {"content": "resp"})()})()]
        result = llm._call_llm("test", backend="ollama", max_tokens=100)
        assert result == "resp"


# ---------------------------------------------------------------------------
# _call_openai_compat - mocked via openai.OpenAI
# ---------------------------------------------------------------------------

def test_call_openai_compat_basic():
    pytest.importorskip('openai')
    with patch("openai.OpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        mock_resp = mock_client.chat.completions.create.return_value
        mock_resp.choices = [type("Choice", (), {"message": type("Msg", (), {"content": '{"nodes":[],"edges":[],"hyperedges":[]}'})(), "finish_reason": "stop"})()]
        mock_resp.usage = type("Usage", (), {"prompt_tokens": 100, "completion_tokens": 50})()
        result = llm._call_openai_compat("http://test", "key", "model", "prompt", temperature=0.2, reasoning_effort="low", backend="openai")
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["finish_reason"] == "stop"


def test_call_openai_compat_temperature_none():
    pytest.importorskip('openai')
    with patch("openai.OpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        mock_resp = mock_client.chat.completions.create.return_value
        mock_resp.choices = [type("Choice", (), {"message": type("Msg", (), {"content": '{"nodes":[],"edges":[],"hyperedges":[]}'})(), "finish_reason": "stop"})()]
        mock_resp.usage = None
        result = llm._call_openai_compat("http://test", "key", "model", "p", temperature=None, backend="kimi")
        assert result["input_tokens"] == 0


def test_call_openai_compat_ollama_small_output_warning(capsys):
    pytest.importorskip('openai')
    with patch("openai.OpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        mock_resp = mock_client.chat.completions.create.return_value
        mock_resp.choices = [type("Choice", (), {"message": type("Msg", (), {"content": '{"nodes":[],"edges":[],"hyperedges":[]}'})(), "finish_reason": "stop"})()]
        mock_resp.usage = type("Usage", (), {"prompt_tokens": 10, "completion_tokens": 3})()
        llm._call_openai_compat("http://localhost:11434/v1", "key", "model", "p", backend="ollama")
        _, err = capsys.readouterr()
        assert "ollama returned very few tokens" in err


# ---------------------------------------------------------------------------
# _call_claude - mocked via sys.modules injection
# ---------------------------------------------------------------------------

def _cleanup_injected_modules():
    """Remove fake modules injected by _inject_fake_* helpers to prevent
    cross-test pollution when a higher-level mock fails and the real
    backend function tries to import the faked module."""
    import sys
    for mod in ("anthropic", "boto3", "botocore", "botocore.exceptions"):
        sys.modules.pop(mod, None)


def _inject_fake_anthropic():
    """Inject a fake anthropic module into sys.modules for mocking."""
    import sys
    if "anthropic" not in sys.modules:
        sys.modules["anthropic"] = MagicMock()
    return sys.modules["anthropic"]


def test_call_claude_basic():
    fake = _inject_fake_anthropic()
    with patch.object(fake, "Anthropic") as mock_anthropic:
        mock_client = mock_anthropic.return_value
        mock_resp = mock_client.messages.create.return_value
        mock_resp.content = [type("Block", (), {"text": '{"nodes":[],"edges":[],"hyperedges":[]}'})()]
        mock_resp.usage = type("Usage", (), {"input_tokens": 200, "output_tokens": 80})()
        mock_resp.stop_reason = "end_turn"
        result = llm._call_claude("fake-key", "claude-sonnet-4-6", "prompt")
        assert result["input_tokens"] == 200
        assert result["output_tokens"] == 80
        assert result["finish_reason"] == "stop"


def test_call_claude_max_tokens_truncated():
    fake = _inject_fake_anthropic()
    with patch.object(fake, "Anthropic") as mock_anthropic:
        mock_client = mock_anthropic.return_value
        mock_resp = mock_client.messages.create.return_value
        mock_resp.content = [type("Block", (), {"text": '{"nodes":[],"edges":[],"hyperedges":[]}'})()]
        mock_resp.usage = type("Usage", (), {"input_tokens": 10, "output_tokens": 5})()
        mock_resp.stop_reason = "max_tokens"
        result = llm._call_claude("fake-key", "claude-sonnet-4-6", "p")
        assert result["finish_reason"] == "length"


def test_call_claude_empty_content():
    fake = _inject_fake_anthropic()
    with patch.object(fake, "Anthropic") as mock_anthropic:
        mock_client = mock_anthropic.return_value
        mock_resp = mock_client.messages.create.return_value
        mock_resp.content = []
        mock_resp.usage = None
        mock_resp.stop_reason = "end_turn"
        result = llm._call_claude("fake-key", "claude-sonnet-4-6", "p")
        # empty content -> "{}" -> json.loads gives {}, no 'nodes' key
        assert result["finish_reason"] == "stop"
        assert result["input_tokens"] == 0


# ---------------------------------------------------------------------------
# _call_bedrock - mocked via sys.modules injection
# ---------------------------------------------------------------------------

def _inject_fake_boto3():
    """Inject fake boto3 + botocore modules into sys.modules."""
    import sys
    class FakeClientError(Exception):
        def __init__(self, error_response, operation_name):
            self.response = error_response
            self.operation_name = operation_name
    if "boto3" not in sys.modules:
        fake_boto3 = MagicMock()
        fake_bc_exc = MagicMock()
        fake_bc_exc.ClientError = FakeClientError
        # IMPORTANT: botocore.exceptions must resolve through the botocore
        # module chain.  _call_bedrock does "import botocore.exceptions"
        # which binds botocore to sys.modules["botocore"]; then accessing
        # botocore.exceptions must yield our injected exceptions mock.
        fake_botocore = MagicMock(exceptions=fake_bc_exc)
        sys.modules["boto3"] = fake_boto3
        sys.modules["botocore"] = fake_botocore
        sys.modules["botocore.exceptions"] = fake_bc_exc
    return sys.modules["boto3"], sys.modules["botocore.exceptions"]


def test_call_bedrock_basic(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    fake_boto3, _ = _inject_fake_boto3()
    with patch.object(fake_boto3, "Session") as mock_session:
        mock_sess = mock_session.return_value
        mock_client = mock_sess.client.return_value
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": '{"nodes":[],"edges":[],"hyperedges":[]}'}]}},
            "usage": {"inputTokens": 30, "outputTokens": 10},
            "stopReason": "end_turn",
        }
        result = llm._call_bedrock("test-model", "prompt")
        assert result["input_tokens"] == 30
        assert result["output_tokens"] == 10
        assert result["finish_reason"] == "stop"


def test_call_bedrock_max_tokens_truncated(monkeypatch):
    monkeypatch.setenv("AWS_PROFILE", "test")
    fake_boto3, _ = _inject_fake_boto3()
    with patch.object(fake_boto3, "Session") as mock_session:
        mock_sess = mock_session.return_value
        mock_client = mock_sess.client.return_value
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "{}"}]}},
            "usage": {},
            "stopReason": "max_tokens",
        }
        result = llm._call_bedrock("model", "p")
        assert result["finish_reason"] == "length"


def test_call_bedrock_client_error(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    fake_boto3, fake_bc_exc = _inject_fake_boto3()
    with patch.object(fake_boto3, "Session") as mock_session:
        mock_sess = mock_session.return_value
        mock_client = mock_sess.client.return_value
        mock_client.converse.side_effect = fake_bc_exc.ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Not authorized"}}, "Converse"
        )
        with pytest.raises(RuntimeError, match="Bedrock API error"):
            llm._call_bedrock("model", "p")


# ---------------------------------------------------------------------------
# extract_files_direct - ollama no-key warning / claude/bedrock branches
# ---------------------------------------------------------------------------

def test_extract_files_direct_ollama_no_key_warns(tmp_path, capsys, monkeypatch):
    pytest.importorskip('openai')
    _clear_backend_env(monkeypatch)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    source = tmp_path / "note.md"
    source.write_text("test")
    expected_json = '{"nodes":[],"edges":[],"hyperedges":[]}'
    with patch("openai.OpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        mock_resp = mock_client.chat.completions.create.return_value
        mock_resp.choices = [type("Choice", (), {
            "message": type("Msg", (), {"content": expected_json})(),
            "finish_reason": "stop",
        })()]
        mock_resp.usage = type("Usage", (), {"prompt_tokens": 0, "completion_tokens": 0})()
        llm.extract_files_direct([source], backend="ollama", root=tmp_path)
    _, err = capsys.readouterr()
    assert "no OLLAMA_API_KEY" in err


def test_extract_files_direct_unknown_backend():
    with pytest.raises(ValueError, match="Unknown backend"):
        llm.extract_files_direct([], backend="nope")


def test_extract_files_direct_claude_branch(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    _cleanup_injected_modules()  # ensure no MagicMock pollution from prior tests
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    source = tmp_path / "x.py"
    source.write_text("x=1")
    result = {"nodes": [], "edges": [], "hyperedges": []}
    with patch("graphify.llm._call_claude", return_value=result) as call:
        llm.extract_files_direct([source], backend="claude", root=tmp_path)
    assert call.called


def test_extract_files_direct_bedrock_branch(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    _cleanup_injected_modules()  # ensure no MagicMock pollution from prior tests
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    source = tmp_path / "x.py"
    source.write_text("x=1")
    result = {"nodes": [], "edges": [], "hyperedges": []}
    with patch("graphify.llm._call_bedrock", return_value=result) as call:
        llm.extract_files_direct([source], backend="bedrock", root=tmp_path)
    assert call.called


# ---------------------------------------------------------------------------
# _extract_with_adaptive_retry
# ---------------------------------------------------------------------------

def test_adaptive_retry_no_truncation(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    source = tmp_path / "a.py"
    source.write_text("x=1")
    expected = {"nodes": [{"id": "x"}], "edges": [], "hyperedges": [], "finish_reason": "stop"}
    with patch("graphify.llm.extract_files_direct", return_value=expected):
        result = llm._extract_with_adaptive_retry([source], backend="openai", api_key="k", model="m", root=tmp_path, max_depth=3)
        assert result["nodes"] == [{"id": "x"}]


def test_adaptive_retry_single_file_truncation(tmp_path, capsys, monkeypatch):
    _clear_backend_env(monkeypatch)
    source = tmp_path / "a.py"
    source.write_text("x=1")
    truncated = {"nodes": [], "edges": [], "hyperedges": [], "finish_reason": "length"}
    with patch("graphify.llm.extract_files_direct", return_value=truncated):
        result = llm._extract_with_adaptive_retry([source], backend="openai", api_key="k", model="m", root=tmp_path, max_depth=3)
    _, err = capsys.readouterr()
    assert "single-file" in err


def test_adaptive_retry_multi_file_recursive(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    a = tmp_path / "a.py"
    a.write_text("a=1")
    b = tmp_path / "b.py"
    b.write_text("b=2")
    call_count = 0

    def side_effect(files, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count >= 3:
            return {"nodes": [{"id": f"n{call_count}"}], "edges": [], "hyperedges": [], "finish_reason": "stop"}
        return {"nodes": [], "edges": [], "hyperedges": [], "finish_reason": "length"}

    with patch("graphify.llm.extract_files_direct", side_effect=side_effect):
        result = llm._extract_with_adaptive_retry([a, b], backend="openai", api_key="k", model="m", root=tmp_path, max_depth=3)
    assert result["finish_reason"] == "stop"
    assert call_count >= 3


def test_adaptive_retry_max_depth_exceeded(tmp_path, capsys, monkeypatch):
    _clear_backend_env(monkeypatch)
    a = tmp_path / "a.py"
    a.write_text("a=1")
    b = tmp_path / "b.py"
    b.write_text("b=2")
    truncated = {"nodes": [], "edges": [], "hyperedges": [], "finish_reason": "length"}
    with patch("graphify.llm.extract_files_direct", return_value=truncated):
        result = llm._extract_with_adaptive_retry([a, b], backend="openai", api_key="k", model="m", root=tmp_path, max_depth=0)
    _, err = capsys.readouterr()
    assert "still truncated" in err


# ---------------------------------------------------------------------------
# extract_corpus_parallel
# ---------------------------------------------------------------------------

def test_extract_corpus_parallel_single_worker(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    a = tmp_path / "a.py"
    a.write_text("a=1")
    chunk_result = {"nodes": [{"id": "a"}], "edges": [], "hyperedges": [], "input_tokens": 5, "output_tokens": 3}
    with patch("graphify.llm._extract_with_adaptive_retry", return_value=chunk_result):
        result = llm.extract_corpus_parallel([a], backend="openai", api_key="k", root=tmp_path, max_concurrency=1)
    assert len(result["nodes"]) == 1


def test_extract_corpus_parallel_with_token_budget(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    a = tmp_path / "a.py"
    a.write_text("a=1")
    chunk_result = {"nodes": [{"id": "a"}], "edges": [], "hyperedges": [], "input_tokens": 2, "output_tokens": 1}
    with patch("graphify.llm._extract_with_adaptive_retry", return_value=chunk_result):
        result = llm.extract_corpus_parallel([a], backend="openai", api_key="k", root=tmp_path, max_concurrency=1, token_budget=10000)
    assert len(result["nodes"]) == 1


def test_extract_corpus_parallel_chunk_error_skipped(tmp_path, capsys, monkeypatch):
    _clear_backend_env(monkeypatch)
    a = tmp_path / "a.py"
    a.write_text("a=1")
    with patch("graphify.llm._extract_with_adaptive_retry", side_effect=RuntimeError("boom")):
        result = llm.extract_corpus_parallel([a], backend="openai", api_key="k", root=tmp_path, max_concurrency=1)
    _, err = capsys.readouterr()
    assert "failed" in err
    assert result["nodes"] == []


def test_extract_corpus_parallel_callback_fires(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    a = tmp_path / "a.py"
    a.write_text("a=1")
    calls = []
    chunk_result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    with patch("graphify.llm._extract_with_adaptive_retry", return_value=chunk_result):
        llm.extract_corpus_parallel([a], backend="openai", api_key="k", root=tmp_path, max_concurrency=1,
                                    on_chunk_done=lambda idx, total, res: calls.append(idx))
    assert calls == [0]


def test_extract_corpus_parallel_legacy_chunk_size(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    files = [tmp_path / f"f{i}.py" for i in range(10)]
    for f in files:
        f.write_text(f"# file {f.name}")
    chunk_result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    with patch("graphify.llm._extract_with_adaptive_retry", return_value=chunk_result):
        result = llm.extract_corpus_parallel(files, backend="openai", api_key="k", root=tmp_path, max_concurrency=1, token_budget=None, chunk_size=4)
    assert len(result["nodes"]) == 0  # all mocked


# ---------------------------------------------------------------------------
# _estimate_file_tokens - tiktoken absent fallback
# ---------------------------------------------------------------------------

def test_estimate_file_tokens_no_tiktoken(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_TOKENIZER", None)
    f = tmp_path / "mod.py"
    f.write_text("x" * 400)
    tokens = llm._estimate_file_tokens(f)
    assert 110 <= tokens <= 140


def test_estimate_file_tokens_no_tiktoken_unreadable(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_TOKENIZER", None)
    assert llm._estimate_file_tokens(tmp_path / "nope.py") == 0


# ---------------------------------------------------------------------------
# _get_tokenizer -> import error / encoding error paths
# ---------------------------------------------------------------------------

def test_get_tokenizer_import_error():
    with patch.dict("sys.modules", {"tiktoken": None}):
        with patch("builtins.__import__", side_effect=ImportError):
            result = llm._get_tokenizer()
            assert result is None


def test_get_tokenizer_encoding_error():
    import sys
    fake_tiktoken = type(sys)("tiktoken")
    fake_tiktoken.get_encoding = lambda _: (_ for _ in ()).throw(Exception("network error"))
    with patch.dict("sys.modules", {"tiktoken": fake_tiktoken}):
        result = llm._get_tokenizer()
        assert result is None


# ---------------------------------------------------------------------------
# _read_files - relative_to ValueError fallback
# ---------------------------------------------------------------------------

def test_read_files_value_error_fallback(tmp_path):
    a = tmp_path / "a.py"
    a.write_text("x=1")
    with patch.object(Path, "relative_to", side_effect=ValueError):
        result = llm._read_files([a], Path("/unrelated"))
    assert "=== " in result


# ---------------------------------------------------------------------------
# _pack_chunks_by_tokens - small budget splits
# ---------------------------------------------------------------------------

def test_pack_chunks_by_tokens_small_budget_splits(tmp_path):
    files = []
    for i in range(5):
        f = tmp_path / f"f{i}.py"
        f.write_text("x=1")
        files.append(f)
    chunks = llm._pack_chunks_by_tokens(files, token_budget=1)
    assert len(chunks) >= 2


# ---------------------------------------------------------------------------
# _resolve_max_tokens - env override via extract_files_direct
# ---------------------------------------------------------------------------

def test_extract_files_direct_respects_max_tokens_env(tmp_path, monkeypatch):
    pytest.importorskip('openai')
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("GRAPHIFY_MAX_OUTPUT_TOKENS", "2048")
    source = tmp_path / "x.py"
    source.write_text("x=1")
    expected_json = '{"nodes":[],"edges":[],"hyperedges":[]}'
    with patch("openai.OpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        mock_resp = mock_client.chat.completions.create.return_value
        mock_resp.choices = [type("Choice", (), {
            "message": type("Msg", (), {"content": expected_json})(),
            "finish_reason": "stop",
        })()]
        mock_resp.usage = type("Usage", (), {"prompt_tokens": 0, "completion_tokens": 0})()
        llm.extract_files_direct([source], backend="openai", root=tmp_path)
    assert mock_client.chat.completions.create.call_args.kwargs["max_completion_tokens"] == 2048


# ---------------------------------------------------------------------------
# _resolve_max_tokens — invalid env value (lines 108-109)
# ---------------------------------------------------------------------------

def test_resolve_max_tokens_invalid_env_value():
    """When GRAPHIFY_MAX_OUTPUT_TOKENS is non-integer, fall back to default."""
    with patch.dict("os.environ", {"GRAPHIFY_MAX_OUTPUT_TOKENS": "abc"}):
        result = llm._resolve_max_tokens(4096)
    assert result == 4096


def test_resolve_max_tokens_zero_or_negative():
    """Zero or negative value in GRAPHIFY_MAX_OUTPUT_TOKENS falls back."""
    with patch.dict("os.environ", {"GRAPHIFY_MAX_OUTPUT_TOKENS": "0"}):
        assert llm._resolve_max_tokens(4096) == 4096
    with patch.dict("os.environ", {"GRAPHIFY_MAX_OUTPUT_TOKENS": "-5"}):
        assert llm._resolve_max_tokens(4096) == 4096


# ---------------------------------------------------------------------------
# _read_files — OSError skip (lines 139-140)
# ---------------------------------------------------------------------------

def test_read_files_unreadable_file(tmp_path):
    """OSError on a file is skipped via continue."""
    a = tmp_path / "good.py"
    a.write_text("x=1")
    b = tmp_path / "bad.py"
    b.write_text("y=2")
    # Make b unreadable by mocking read_text
    with patch.object(Path, "read_text", side_effect=[a.read_text(), OSError("permission")]):
        result = llm._read_files([a, b], tmp_path)
    assert "good.py" in result
    assert "bad.py" not in result


# ---------------------------------------------------------------------------
# _parse_llm_json — oversized response (lines 155-160)
# ---------------------------------------------------------------------------

def test_parse_llm_json_oversized():
    """A response larger than _LLM_JSON_MAX_BYTES returns empty fragment."""
    big = "x" * (llm._LLM_JSON_MAX_BYTES + 100)
    result = llm._parse_llm_json(big)
    assert result == {"nodes": [], "edges": [], "hyperedges": []}


# ---------------------------------------------------------------------------
# _call_openai_compat — missing openai (lines 225-227)
# ---------------------------------------------------------------------------

def test_call_openai_compat_missing_openai():
    """Missing openai package raises ImportError with helpful message."""
    with patch.dict("sys.modules", {"openai": None}):
        with patch("builtins.__import__", side_effect=ImportError):
            with pytest.raises(ImportError, match="openai"):
                llm._call_openai_compat("http://x", "k", "m", "p")


def test_call_openai_compat_missing_openai_kimi():
    """Missing openai with kimi backend suggests graphifyy[kimi]."""
    with patch.dict("sys.modules", {"openai": None}):
        with patch("builtins.__import__", side_effect=ImportError):
            with pytest.raises(ImportError, match=r"graphifyy\[kimi\]"):
                llm._call_openai_compat("http://x", "k", "m", "p", backend="kimi")


# ---------------------------------------------------------------------------
# _call_openai_compat — moonshot base_url extra_body (line 247)
# ---------------------------------------------------------------------------

def test_call_openai_compat_moonshot_extra_body():
    pytest.importorskip('openai')
    """When base_url contains 'moonshot', extra_body thinking:disabled is set."""
    with patch("openai.OpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        mock_resp = mock_client.chat.completions.create.return_value
        mock_resp.choices = [type("Choice", (), {
            "message": type("Msg", (), {"content": '{"nodes":[],"edges":[],"hyperedges":[]}'})(),
            "finish_reason": "stop"
        })()]
        mock_resp.usage = type("Usage", (), {"prompt_tokens": 10, "completion_tokens": 5})()
        llm._call_openai_compat("https://api.moonshot.cn/v1", "key", "model", "p")
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "extra_body" in call_kwargs
        assert call_kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


# ---------------------------------------------------------------------------
# _call_claude — missing anthropic (lines 272-273)
# ---------------------------------------------------------------------------

def test_call_claude_missing_anthropic():
    """Missing anthropic raises ImportError with install hint."""
    import sys
    if "anthropic" in sys.modules:
        del sys.modules["anthropic"]
    with patch.dict("sys.modules", {"anthropic": None}):
        with patch("builtins.__import__", side_effect=ImportError):
            with pytest.raises(ImportError, match="anthropic"):
                llm._call_claude("k", "m", "p")


# ---------------------------------------------------------------------------
# _call_bedrock — missing boto3 (lines 301-302)
# ---------------------------------------------------------------------------

def test_call_bedrock_missing_boto3():
    """Missing boto3 raises ImportError with install hint."""
    import sys
    for mod in ("boto3", "botocore", "botocore.exceptions"):
        sys.modules.pop(mod, None)
    with patch.dict("sys.modules", {"boto3": None, "botocore": None}):
        with patch("builtins.__import__", side_effect=ImportError):
            with pytest.raises(ImportError, match="boto3"):
                llm._call_bedrock("m", "p")


# ---------------------------------------------------------------------------
# _estimate_file_tokens — OSError with tiktoken (lines 407-408)
# ---------------------------------------------------------------------------

def test_estimate_file_tokens_unreadable_with_tiktoken(tmp_path):
    """When tiktoken is available but file is unreadable, return 0."""
    f = tmp_path / "mod.py"
    f.write_text("content")
    # Set _TOKENIZER to a non-None mock so we take the tiktoken branch
    fake_enc = MagicMock()
    with patch.object(llm, "_TOKENIZER", fake_enc):
        with patch.object(Path, "read_text", side_effect=OSError("perm")):
            result = llm._estimate_file_tokens(f)
    assert result == 0


# ---------------------------------------------------------------------------
# extract_corpus_parallel — ThreadPoolExecutor branch (lines 614-624)
# ---------------------------------------------------------------------------

def test_extract_corpus_parallel_threadpool_error_skipped(tmp_path, capsys, monkeypatch):
    _clear_backend_env(monkeypatch)
    """Chunk error in ThreadPoolExecutor prints warning and continues."""
    a = tmp_path / "a.py"
    a.write_text("a=1")
    b = tmp_path / "b.py"
    b.write_text("b=2")
    with patch("graphify.llm._extract_with_adaptive_retry",
               side_effect=RuntimeError("boom")):
        result = llm.extract_corpus_parallel(
            [a, b], backend="openai", api_key="k",
            root=tmp_path, max_concurrency=2,
            token_budget=None, chunk_size=1
        )
    _, err = capsys.readouterr()
    assert "failed" in err
    assert result["nodes"] == []


def test_extract_corpus_parallel_threadpool_callback_fires(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    """on_chunk_done callback fires in ThreadPoolExecutor branch."""
    a = tmp_path / "a.py"
    a.write_text("a=1")
    b = tmp_path / "b.py"
    b.write_text("b=2")
    calls = []
    chunk_result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    with patch("graphify.llm._extract_with_adaptive_retry", return_value=chunk_result):
        llm.extract_corpus_parallel(
            [a, b], backend="openai", api_key="k",
            root=tmp_path, max_concurrency=2,
            token_budget=None, chunk_size=1,
            on_chunk_done=lambda idx, total, res: calls.append(idx)
        )
    assert len(calls) == 2
    assert set(calls) == {0, 1}


# ---------------------------------------------------------------------------
# _call_llm — claude branch (lines 664-674)
# ---------------------------------------------------------------------------

def test_call_llm_claude_branch(monkeypatch):
    """_call_llm dispatches to Claude when backend=claude."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-key")
    fake = MagicMock()
    import sys
    sys.modules["anthropic"] = fake
    try:
        mock_client = fake.Anthropic.return_value
        mock_resp = mock_client.messages.create.return_value
        mock_resp.content = [type("Block", (), {"text": "Claude response"})()]
        result = llm._call_llm("test prompt", backend="claude", max_tokens=100)
        assert result == "Claude response"
    finally:
        sys.modules.pop("anthropic", None)


# ---------------------------------------------------------------------------
# _call_llm — bedrock branch (lines 677-690)
# ---------------------------------------------------------------------------

def test_call_llm_bedrock_branch(monkeypatch):
    """_call_llm dispatches to Bedrock when backend=bedrock and AWS_PROFILE is set."""
    monkeypatch.setenv("AWS_PROFILE", "test-profile")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    fake_boto3, _ = _inject_fake_boto3()
    with patch.object(fake_boto3, "Session") as mock_session:
        mock_sess = mock_session.return_value
        mock_client = mock_sess.client.return_value
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "Bedrock response"}]}},
        }
        result = llm._call_llm("test prompt", backend="bedrock", max_tokens=100)
        assert result == "Bedrock response"


# ---------------------------------------------------------------------------
# _call_llm — missing openai import (lines 695-696)
# ---------------------------------------------------------------------------

def test_call_llm_missing_openai(monkeypatch):
    """Missing openai in _call_llm raises ImportError."""
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    with patch.dict("sys.modules", {"openai": None}):
        with patch("builtins.__import__", side_effect=ImportError):
            with pytest.raises(ImportError, match="openai"):
                llm._call_llm("prompt", backend="openai")


# ---------------------------------------------------------------------------
# _call_llm — reasoning_effort and extra_body (lines 706-709)
# ---------------------------------------------------------------------------

def test_call_llm_reasoning_effort(monkeypatch):
    pytest.importorskip('openai')
    """_call_llm passes reasoning_effort when config has it."""
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    with patch("openai.OpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        mock_resp = mock_client.chat.completions.create.return_value
        mock_resp.choices = [type("Choice", (), {
            "message": type("Msg", (), {"content": "response"})()
        })()]
        # Gemini backend has reasoning_effort in its config
        llm._call_llm("prompt", backend="gemini", max_tokens=100)
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "reasoning_effort" in call_kwargs


def test_call_llm_moonshot_extra_body(monkeypatch):
    pytest.importorskip('openai')
    """_call_llm adds extra_body thinking:disabled for moonshot base URLs."""
    monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-key")
    with patch("openai.OpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        mock_resp = mock_client.chat.completions.create.return_value
        mock_resp.choices = [type("Choice", (), {
            "message": type("Msg", (), {"content": "response"})()
        })()]
        llm._call_llm("prompt", backend="kimi", max_tokens=100)
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "extra_body" in call_kwargs
        assert call_kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


# ---------------------------------------------------------------------------
# _validate_ollama_base_url — unparseable URL (lines 732-737)
# ---------------------------------------------------------------------------

def test_validate_ollama_base_url_unparseable_exception():
    """Unparseable URL triggers the except Exception warning branch."""
    # _validate_ollama_base_url does `from urllib.parse import urlparse` locally
    import urllib.parse
    with patch.object(urllib.parse, "urlparse", side_effect=Exception("parse error")):
        llm._validate_ollama_base_url("http://bad")
