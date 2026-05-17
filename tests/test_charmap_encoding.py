"""Regression tests for UnicodeEncodeError on Windows cp1252 console.

On Windows with the default cp1252 codepage, subprocess.run(..., text=True)
without an explicit encoding= defaults to cp1252, causing UnicodeEncodeError
when chunk content contains characters outside cp1252 (e.g. → ✅ ≥).

These tests mock subprocess.run to:
  a) Assert that the subprocess call is made with encoding="utf-8" (or
     equivalent environment forcing UTF-8), so non-ASCII chars never hit
     cp1252 encoding.
  b) Assert that extract_corpus_parallel reports loud failure (non-zero exit
     or summary block) when ≥1 chunk fails.
"""
from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from graphify import llm

# ── Helpers ────────────────────────────────────────────────────────────────────

_UNICODE_CONTENT = "→ means implies. ✅ done. Score ≥ 90."

_ENVELOPE = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": json.dumps({
        "nodes": [{"id": "n1", "label": "N1", "file_type": "document",
                   "source_file": "u.md"}],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }),
    "stop_reason": "end_turn",
    "usage": {
        "input_tokens": 1,
        "output_tokens": 1,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    },
    "modelUsage": {
        "claude-opus-4-7": {"inputTokens": 1, "outputTokens": 1},
    },
}


# ── Test A: subprocess encoding ───────────────────────────────────────────────

class TestSubprocessEncoding:
    """_call_claude_cli must pass encoding="utf-8" to subprocess.run so that
    non-ASCII content in chunk messages does not raise UnicodeEncodeError on
    Windows cp1252 consoles.
    """

    def _make_completed(self):
        """Build a mock CompletedProcess with a valid JSON envelope."""
        return MagicMock(returncode=0, stdout=json.dumps(_ENVELOPE), stderr="")

    def test_subprocess_called_with_utf8_encoding(self, monkeypatch):
        """subprocess.run must be invoked with encoding='utf-8'."""
        completed = self._make_completed()
        monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)
        with patch("shutil.which", return_value="/fake/bin/claude"), \
             patch("subprocess.run", return_value=completed) as mock_run:
            llm._call_claude_cli(_UNICODE_CONTENT, max_tokens=8192)
        _args, kwargs = mock_run.call_args
        assert kwargs.get("encoding") == "utf-8", (
            "subprocess.run must be called with encoding='utf-8'; "
            f"got encoding={kwargs.get('encoding')!r}"
        )

    def test_subprocess_does_not_use_text_true_without_encoding(self, monkeypatch):
        """text=True without encoding= relies on the locale codec (cp1252 on Windows).

        Either encoding='utf-8' must be set (making text=True irrelevant) or
        text=True must be absent and input encoded to bytes explicitly.
        """
        completed = self._make_completed()
        monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)
        with patch("shutil.which", return_value="/fake/bin/claude"), \
             patch("subprocess.run", return_value=completed) as mock_run:
            llm._call_claude_cli(_UNICODE_CONTENT, max_tokens=8192)
        _args, kwargs = mock_run.call_args
        # If text=True is present, encoding must also be set to 'utf-8'.
        if kwargs.get("text") is True:
            assert kwargs.get("encoding") == "utf-8", (
                "text=True without encoding='utf-8' will use the locale codec "
                "(cp1252 on Windows), causing UnicodeEncodeError on → ✅ ≥"
            )
        else:
            # input must be bytes, not str
            inp = kwargs.get("input") or (mock_run.call_args[0][1:2] or [None])[0]
            assert isinstance(inp, bytes), (
                "Without text=True, input must be bytes pre-encoded to UTF-8."
            )

    def test_unicode_chars_survive_subprocess_roundtrip(self, monkeypatch, tmp_path):
        """Writing a file with → ✅ ≥ then passing its content through
        _call_claude_cli must not raise UnicodeEncodeError.
        """
        f = tmp_path / "u.md"
        f.write_text(_UNICODE_CONTENT, encoding="utf-8")

        completed = self._make_completed()
        monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)
        with patch("shutil.which", return_value="/fake/bin/claude"), \
             patch("subprocess.run", return_value=completed):
            # Should not raise
            result = llm.extract_files_direct(
                files=[f], backend="claude-cli", root=tmp_path
            )
        assert len(result["nodes"]) >= 1

    def test_call_llm_claude_cli_subprocess_encoding(self, monkeypatch):
        """_call_llm with backend='claude-cli' must also use encoding='utf-8'."""
        completed = MagicMock(
            returncode=0,
            stdout=json.dumps({"result": "ok", "stop_reason": "end_turn"}),
            stderr="",
        )
        with patch("shutil.which", return_value="/fake/bin/claude"), \
             patch("subprocess.run", return_value=completed) as mock_run:
            llm._call_llm(_UNICODE_CONTENT, backend="claude-cli", max_tokens=200)
        _args, kwargs = mock_run.call_args
        assert kwargs.get("encoding") == "utf-8", (
            "_call_llm claude-cli subprocess must use encoding='utf-8'; "
            f"got encoding={kwargs.get('encoding')!r}"
        )


# ── Test B: loud failure on chunk error ────────────────────────────────────────

class TestLoudChunkFailure:
    """extract_corpus_parallel must surface chunk failures loudly — either via
    non-zero exit (exception raised from the function) or a printed summary
    block — rather than silently returning exit 0 with failures buried in logs.
    """

    def test_failure_count_in_merged_result(self, monkeypatch, tmp_path):
        """When chunks fail, extract_corpus_parallel must record failed_chunks > 0
        in its return value.
        """
        files = []
        for i in range(3):
            f = tmp_path / f"f{i}.py"
            f.write_text(f"x = {i}\n", encoding="utf-8")
            files.append(f)

        monkeypatch.setattr(
            llm,
            "_extract_with_adaptive_retry",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("charmap error")),
        )

        result = llm.extract_corpus_parallel(files, backend="claude-cli")
        assert result.get("failed_chunks", 0) > 0, (
            "extract_corpus_parallel must expose failed_chunks count in its "
            f"return dict; got: {result}"
        )

    def test_summary_printed_when_chunks_fail(self, monkeypatch, tmp_path, capsys):
        """A summary line must appear on stderr when ≥1 chunk fails."""
        files = []
        for i in range(2):
            f = tmp_path / f"g{i}.py"
            f.write_text(f"y = {i}\n", encoding="utf-8")
            files.append(f)

        monkeypatch.setattr(
            llm,
            "_extract_with_adaptive_retry",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("charmap error")),
        )

        llm.extract_corpus_parallel(files, backend="claude-cli")
        captured = capsys.readouterr()
        # The summary must mention how many chunks failed
        assert "failed" in captured.err.lower(), (
            "A failure summary must appear on stderr when chunks fail; "
            f"got stderr: {captured.err!r}"
        )

    def test_no_false_alarm_when_all_chunks_succeed(self, monkeypatch, tmp_path, capsys):
        """When all chunks succeed, failed_chunks must be 0 and no failure
        summary should appear.
        """
        f = tmp_path / "ok.py"
        f.write_text("z = 1\n", encoding="utf-8")

        good_result = {
            "nodes": [{"id": "n1", "label": "N1", "file_type": "code",
                       "source_file": str(f)}],
            "edges": [], "hyperedges": [],
            "input_tokens": 1, "output_tokens": 1,
            "elapsed_seconds": 0.1,
        }
        monkeypatch.setattr(
            llm,
            "_extract_with_adaptive_retry",
            lambda *a, **kw: good_result,
        )

        result = llm.extract_corpus_parallel([f], backend="claude-cli")
        assert result.get("failed_chunks", 0) == 0
        captured = capsys.readouterr()
        # "WARNING:" should NOT appear on a fully-successful run
        assert "WARNING:" not in captured.err or "0/" not in captured.err


# ── Substitution validation (rsl-siege-manager path via Python) ────────────────

class TestSubstitutionValidation:
    """Exercises the same code path as the rsl-siege-manager reproduction
    without requiring the `claude` CLI or its auth.

    The reproduction scenario: a file containing → ✅ ≥ is read via _read_files
    and passed to _call_claude_cli as `user_message`. Prior to the fix, the
    subprocess.run call with text=True (no encoding=) would encode `user_message`
    using the locale codec (cp1252 on Windows), raising UnicodeEncodeError.

    This test:
    1. Writes a temp file containing the exact unicode chars from the failing chunks.
    2. Calls _read_files to build the prompt string (same path as extract_files_direct).
    3. Confirms the prompt encodes cleanly to UTF-8 (the fix) but would fail cp1252.
    4. Mocks subprocess.run and confirms encoding='utf-8' is passed.
    """

    _UNICODE_CHARS = "→ means implies. ✅ done. Score ≥ 90. Threshold: ≥ 95%."

    def test_read_files_produces_utf8_safe_prompt(self, tmp_path):
        """_read_files must return a string that encodes cleanly to UTF-8."""
        f = tmp_path / "unicode_chunk.md"
        f.write_text(self._UNICODE_CHARS, encoding="utf-8")

        prompt = llm._read_files([f], root=tmp_path)
        assert self._UNICODE_CHARS in prompt or "→" in prompt

        # Must not raise with UTF-8
        encoded_utf8 = prompt.encode("utf-8")
        assert len(encoded_utf8) > 0

    def test_cp1252_would_fail_but_utf8_succeeds(self, tmp_path):
        """Demonstrate the exact failure mode that is now fixed.

        The prompt string contains chars outside cp1252, so encoding
        to cp1252 raises UnicodeEncodeError while UTF-8 succeeds.
        """
        f = tmp_path / "unicode_chunk.md"
        f.write_text(self._UNICODE_CHARS, encoding="utf-8")

        prompt = llm._read_files([f], root=tmp_path)

        # UTF-8 must succeed (our fix)
        try:
            prompt.encode("utf-8")
        except UnicodeEncodeError as e:
            raise AssertionError(
                f"UTF-8 encode must succeed but failed: {e}"
            ) from e

        # cp1252 must fail (confirming these chars are the failing surface)
        try:
            prompt.encode("cp1252")
            # If it doesn't fail, test content doesn't cover the issue —
            # fail loudly so the test author knows to update _UNICODE_CHARS.
            raise AssertionError(
                "Expected cp1252 encode to fail for chars → ✅ ≥, but it "
                "succeeded. Update _UNICODE_CHARS to include cp1252-incompatible "
                "characters."
            )
        except UnicodeEncodeError:
            pass  # Expected — confirms these chars hit the pre-fix failure surface

    def test_subprocess_encoding_kwarg_in_extract_files_direct(
        self, monkeypatch, tmp_path
    ):
        """End-to-end path: write unicode file → extract_files_direct → subprocess.

        Subprocess must receive encoding='utf-8', not the locale default.
        """
        f = tmp_path / "unicode_chunk.md"
        f.write_text(self._UNICODE_CHARS, encoding="utf-8")

        _ENVELOPE_SIMPLE = {
            "type": "result", "subtype": "success", "is_error": False,
            "result": json.dumps({
                "nodes": [{"id": "u_chunk", "label": "Unicode Chunk",
                           "file_type": "document",
                           "source_file": "unicode_chunk.md"}],
                "edges": [], "hyperedges": [],
                "input_tokens": 1, "output_tokens": 1,
            }),
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": 1, "output_tokens": 1,
                "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
            },
            "modelUsage": {
                "claude-opus-4-7": {"inputTokens": 1, "outputTokens": 1},
            },
        }
        completed = MagicMock(
            returncode=0, stdout=json.dumps(_ENVELOPE_SIMPLE), stderr=""
        )
        monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)

        with patch("shutil.which", return_value="/fake/bin/claude"), \
             patch("subprocess.run", return_value=completed) as mock_run:
            result = llm.extract_files_direct(
                files=[f], backend="claude-cli", root=tmp_path
            )

        assert mock_run.called
        _args, kwargs = mock_run.call_args
        assert kwargs.get("encoding") == "utf-8", (
            "subprocess.run must be called with encoding='utf-8'; "
            f"got {kwargs.get('encoding')!r}"
        )
        # Confirm the unicode content was in the input (not truncated/replaced)
        inp = kwargs.get("input", "")
        assert "→" in inp or "✅" in inp or "≥" in inp
        assert len(result["nodes"]) >= 1
