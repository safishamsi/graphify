"""Tests for the direct LLM backend (Claude / Kimi)."""
from unittest.mock import MagicMock, patch


def _mock_response(content: str = '{"nodes":[],"edges":[]}', completion_tokens: int = 10):
    """Build a fake OpenAI ChatCompletion response."""
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    resp.usage = MagicMock(prompt_tokens=100, completion_tokens=completion_tokens)
    return resp


def test_kimi_call_disables_thinking():
    """kimi-k2.6 is a reasoning model: when thinking is enabled and the chunk
    is large, all of max_completion_tokens is consumed by reasoning_content,
    leaving content empty and graphify parsing zero nodes. Disable thinking on
    Moonshot endpoints so content is always populated for structured extraction.
    """
    from graphify.llm import _call_openai_compat

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response()

    with patch("openai.OpenAI", return_value=fake_client):
        _call_openai_compat(
            base_url="https://api.moonshot.ai/v1",
            api_key="sk-test",
            model="kimi-k2.6",
            user_message="=== example.py ===\ndef hello(): pass\n",
            temperature=None,
        )

    kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert "extra_body" in kwargs, "moonshot calls must pass extra_body to disable thinking"
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


def test_non_moonshot_call_does_not_disable_thinking():
    """The thinking-disabled flag is Moonshot-specific extra_body. Other
    OpenAI-compatible providers (real OpenAI, Together, Groq, etc.) don't
    accept it and would 400. Only set it for Moonshot URLs."""
    from graphify.llm import _call_openai_compat

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response()

    with patch("openai.OpenAI", return_value=fake_client):
        _call_openai_compat(
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            model="gpt-4o",
            user_message="hi",
            temperature=0,
        )

    kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert "extra_body" not in kwargs, "non-Moonshot calls must not pass thinking flag"
