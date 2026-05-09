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


# ---------------------------------------------------------------------------
# Hollow-response detection: empty / null / unparseable content from a
# successful HTTP call must route into the same bisection path as a true
# `finish_reason="length"` truncation, not be silently dropped.
# ---------------------------------------------------------------------------


def test_response_is_hollow_flags_empty_string():
    assert llm._response_is_hollow("", {"nodes": [], "edges": [], "hyperedges": []})


def test_response_is_hollow_flags_none_content():
    assert llm._response_is_hollow(None, {"nodes": [], "edges": [], "hyperedges": []})


def test_response_is_hollow_flags_whitespace_only():
    assert llm._response_is_hollow("   \n\t  ", {"nodes": [], "edges": [], "hyperedges": []})


def test_response_is_hollow_flags_parsed_but_no_nodes_or_edges():
    # Content was non-empty (e.g. model said `{"sorry": "I cannot"}` or returned
    # `{}` literally) but the parsed result has nothing usable.
    assert llm._response_is_hollow('{"sorry": "I cannot"}', {})
    assert llm._response_is_hollow("{}", {"nodes": [], "edges": [], "hyperedges": []})


def test_response_is_hollow_accepts_real_extraction():
    parsed = {"nodes": [{"id": "x"}], "edges": [], "hyperedges": []}
    assert not llm._response_is_hollow('{"nodes":[{"id":"x"}]}', parsed)
    parsed = {"nodes": [], "edges": [{"source": "a", "target": "b"}], "hyperedges": []}
    assert not llm._response_is_hollow('{"edges":[...]}', parsed)


def _fake_openai_response(content, *, finish_reason="stop", prompt_tokens=100, completion_tokens=0):
    """Build a minimal stand-in for an `openai` SDK ChatCompletion response."""
    class _Usage:
        def __init__(self):
            self.prompt_tokens = prompt_tokens
            self.completion_tokens = completion_tokens

    class _Message:
        def __init__(self):
            self.content = content

    class _Choice:
        def __init__(self):
            self.message = _Message()
            self.finish_reason = finish_reason

    class _Resp:
        def __init__(self):
            self.choices = [_Choice()]
            self.usage = _Usage()

    return _Resp()


def _install_fake_openai(monkeypatch, fake_resp):
    """Inject a stub `openai` module so `_call_openai_compat` can run without
    the real SDK installed. The function does `from openai import OpenAI`
    inside its body, so we satisfy that lookup via `sys.modules`."""
    import sys
    import types

    class _FakeOpenAI:
        def __init__(self, *_, **__):
            self.chat = self
            self.completions = self
        def create(self, **__):
            return fake_resp

    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = _FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)


def test_call_openai_compat_relabels_empty_content_as_length(monkeypatch):
    # Simulates an overwhelmed Ollama: HTTP 200, empty content, finish_reason
    # "stop", zero completion tokens. Pre-fix this would silently return an
    # empty fragment and the chunk would be dropped. Post-fix `finish_reason`
    # is rewritten to "length" so the adaptive retry layer bisects.
    fake_resp = _fake_openai_response("", finish_reason="stop", completion_tokens=0)
    _install_fake_openai(monkeypatch, fake_resp)

    result = llm._call_openai_compat(
        "http://localhost:11434/v1", "ollama", "qwen2.5-coder:7b",
        "user msg", temperature=0, max_completion_tokens=8192, backend="ollama",
    )
    assert result["finish_reason"] == "length", (
        "empty content from a 'successful' call must be re-labelled so the "
        "adaptive retry layer treats it as a truncation and bisects the chunk"
    )


def test_call_openai_compat_relabels_none_content_as_length(monkeypatch):
    fake_resp = _fake_openai_response(None, finish_reason="stop")
    _install_fake_openai(monkeypatch, fake_resp)

    result = llm._call_openai_compat(
        "http://localhost:11434/v1", "ollama", "qwen2.5-coder:7b",
        "u", temperature=0, max_completion_tokens=8192, backend="ollama",
    )
    assert result["finish_reason"] == "length"


def test_call_openai_compat_relabels_unparseable_json_as_length(monkeypatch):
    # A half-generated response: `{"nodes": [{"id":` parses to {} (empty
    # fragment) via _parse_llm_json's JSONDecodeError fallback. That is also
    # hollow and must trigger bisection.
    fake_resp = _fake_openai_response('{"nodes": [{"id":', finish_reason="stop", completion_tokens=20)
    _install_fake_openai(monkeypatch, fake_resp)

    result = llm._call_openai_compat(
        "http://localhost:11434/v1", "ollama", "qwen2.5-coder:7b",
        "u", temperature=0, max_completion_tokens=8192, backend="ollama",
    )
    assert result["finish_reason"] == "length"


def test_call_openai_compat_preserves_real_finish_reason(monkeypatch):
    # A genuine extraction with real nodes must NOT be re-labelled.
    fake_resp = _fake_openai_response(
        '{"nodes":[{"id":"a"}],"edges":[],"hyperedges":[]}',
        finish_reason="stop",
        completion_tokens=200,
    )
    _install_fake_openai(monkeypatch, fake_resp)

    result = llm._call_openai_compat(
        "http://localhost:11434/v1", "k", "m",
        "u", temperature=0, max_completion_tokens=8192, backend="kimi",
    )
    assert result["finish_reason"] == "stop"
    assert result["nodes"] == [{"id": "a"}]


# ---------------------------------------------------------------------------
# Ollama context-window fix (#798): num_ctx + keep_alive in extra_body,
# serial execution by default.
# ---------------------------------------------------------------------------


def _install_capturing_openai(monkeypatch):
    """Like _install_fake_openai but records kwargs passed to create()."""
    import sys
    import types

    captured = {}

    class _FakeOpenAI:
        def __init__(self, *_, **__):
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            captured.update(kwargs)
            return _fake_openai_response(
                '{"nodes":[{"id":"x"}],"edges":[],"hyperedges":[]}',
                finish_reason="stop",
                completion_tokens=100,
            )

    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = _FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    return captured


def test_ollama_extra_body_sets_num_ctx_and_keep_alive(monkeypatch):
    captured = _install_capturing_openai(monkeypatch)
    monkeypatch.delenv("GRAPHIFY_OLLAMA_NUM_CTX", raising=False)
    monkeypatch.delenv("GRAPHIFY_OLLAMA_KEEP_ALIVE", raising=False)

    llm._call_openai_compat(
        "http://localhost:11434/v1", "ollama", "qwen2.5-coder:7b",
        "user msg", temperature=0, max_completion_tokens=8192, backend="ollama",
    )

    assert "extra_body" in captured, "extra_body must be sent to Ollama"
    eb = captured["extra_body"]
    # num_ctx is now dynamic: derived from message size, not hardcoded 131072
    assert "num_ctx" in eb.get("options", {}), "num_ctx must be present"
    assert eb["options"]["num_ctx"] >= 8192, "num_ctx must be at least the floor value"
    assert eb.get("keep_alive") == "30m", "default keep_alive must be 30m"


def test_ollama_num_ctx_scales_with_small_token_budget(monkeypatch):
    # Regression for #798 follow-up: with --token-budget 8192, the old hardcoded
    # 131072 forced Ollama to allocate 128k KV-cache slots on a 31B model, causing
    # VRAM exhaustion by chunk 4. num_ctx must now reflect actual chunk size.
    captured = _install_capturing_openai(monkeypatch)
    monkeypatch.delenv("GRAPHIFY_OLLAMA_NUM_CTX", raising=False)
    monkeypatch.delenv("GRAPHIFY_OLLAMA_KEEP_ALIVE", raising=False)

    # Simulate an 8k-token chunk: ~32k chars of content
    small_chunk_msg = "x" * 32_000

    llm._call_openai_compat(
        "http://localhost:11434/v1", "ollama", "qwen2.5-coder:7b",
        small_chunk_msg, temperature=0, max_completion_tokens=16384, backend="ollama",
    )

    num_ctx = captured["extra_body"]["options"]["num_ctx"]
    # Should be far less than 131072 for an 8k input — VRAM-friendly
    assert num_ctx < 131072, (
        f"num_ctx={num_ctx} is too large for a small chunk; "
        "this wastes VRAM and causes OOM on large models (#798)"
    )
    # But still large enough to fit input + output
    assert num_ctx >= 8192, "num_ctx must cover at least the output cap"


def test_ollama_num_ctx_env_override(monkeypatch):
    captured = _install_capturing_openai(monkeypatch)
    monkeypatch.setenv("GRAPHIFY_OLLAMA_NUM_CTX", "65536")
    monkeypatch.delenv("GRAPHIFY_OLLAMA_KEEP_ALIVE", raising=False)

    llm._call_openai_compat(
        "http://localhost:11434/v1", "ollama", "qwen2.5-coder:7b",
        "u", temperature=0, max_completion_tokens=8192, backend="ollama",
    )

    assert captured["extra_body"]["options"]["num_ctx"] == 65536


def test_non_ollama_backend_gets_no_num_ctx_extra_body(monkeypatch):
    captured = _install_capturing_openai(monkeypatch)

    llm._call_openai_compat(
        "https://api.openai.com/v1", "sk-test", "gpt-4.1-mini",
        "u", temperature=0, max_completion_tokens=8192, backend="openai",
    )

    eb = captured.get("extra_body")
    assert eb is None or "options" not in eb, "non-ollama backends must not get num_ctx injection"


def test_extract_corpus_parallel_ollama_runs_serially(tmp_path, monkeypatch):
    # With 3 chunks and backend=ollama, ThreadPoolExecutor must NOT be used
    # (workers=1 takes the sequential path). We verify by ensuring all chunks
    # are processed and no pool is spun up.
    files = [tmp_path / f"f{i}.md" for i in range(6)]
    for f in files:
        f.write_text("hello")

    call_order = []

    def fake_extract(chunk, *_, **__):
        call_order.append(len(chunk))
        return _ok(nodes=[{"id": f.stem} for f in chunk])

    monkeypatch.delenv("GRAPHIFY_OLLAMA_PARALLEL", raising=False)

    with patch("graphify.llm.extract_files_direct", side_effect=fake_extract):
        with patch("graphify.llm.ThreadPoolExecutor") as mock_pool:
            result = llm.extract_corpus_parallel(
                files, backend="ollama", api_key="ollama", model="qwen2.5-coder:7b",
                root=tmp_path, token_budget=None, chunk_size=2, max_concurrency=4,
            )

    mock_pool.assert_not_called()
    assert len(result["nodes"]) == 6


def test_extract_corpus_parallel_ollama_parallel_env_restores_concurrency(tmp_path, monkeypatch):
    files = [tmp_path / f"f{i}.md" for i in range(4)]
    for f in files:
        f.write_text("hello")

    monkeypatch.setenv("GRAPHIFY_OLLAMA_PARALLEL", "1")

    with patch("graphify.llm.extract_files_direct", return_value=_ok()):
        with patch("graphify.llm.ThreadPoolExecutor") as mock_pool:
            mock_pool.return_value.__enter__ = lambda s: s
            mock_pool.return_value.__exit__ = lambda s, *a: False
            mock_pool.return_value.submit = lambda fn, *a, **kw: type(
                "F", (), {"result": lambda self: fn(*a, **kw)}
            )()
            try:
                llm.extract_corpus_parallel(
                    files, backend="ollama", api_key="ollama", model="m",
                    root=tmp_path, token_budget=None, chunk_size=2, max_concurrency=4,
                )
            except Exception:
                pass  # mock scaffolding may not be complete; we only care about the call

    mock_pool.assert_called()


def test_adaptive_retry_bisects_on_hollow_ollama_response(tmp_path):
    # End-to-end: an overwhelmed Ollama returns hollow on the full 4-file
    # chunk; halves succeed. The bug being fixed is that pre-fix this
    # produces zero nodes (chunk silently dropped). Post-fix the hollow
    # response is relabelled `finish_reason="length"` and the existing
    # bisection path recovers the full 4 nodes.
    files = [tmp_path / f"f{i}.md" for i in range(4)]
    for f in files:
        f.write_text("hello")

    calls = {"n": 0}

    def fake_extract(chunk, *_, **__):
        calls["n"] += 1
        if len(chunk) == 4:
            # Hollow response: looks successful, finish_reason already
            # rewritten to "length" by _call_openai_compat.
            return {
                "nodes": [], "edges": [], "hyperedges": [],
                "input_tokens": 100, "output_tokens": 0,
                "model": "m", "finish_reason": "length",
            }
        return _ok(nodes=[{"id": f.stem} for f in chunk])

    with patch("graphify.llm.extract_files_direct", side_effect=fake_extract):
        result = llm._extract_with_adaptive_retry(
            files, backend="ollama", api_key="ollama", model="qwen2.5-coder:7b",
            root=tmp_path, max_depth=3,
        )

    assert len(result["nodes"]) == 4, (
        "bisection should recover all 4 nodes from the two halves after the "
        "full chunk came back hollow"
    )
    assert calls["n"] == 3  # 1 hollow + 2 successful halves
