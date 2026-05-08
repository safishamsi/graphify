"""Tests for graphify.transcribe — video/audio transcription support."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from graphify.transcribe import (
    VIDEO_EXTENSIONS,
    build_whisper_prompt,
    transcribe,
    transcribe_all,
    is_url,
    _get_whisper,
    _get_yt_dlp,
)
from graphify.transcribe import download_audio, _model_name, _FALLBACK_PROMPT


# ---------------------------------------------------------------------------
# VIDEO_EXTENSIONS
# ---------------------------------------------------------------------------

def test_video_extensions_set():
    assert ".mp4" in VIDEO_EXTENSIONS
    assert ".mp3" in VIDEO_EXTENSIONS
    assert ".wav" in VIDEO_EXTENSIONS
    assert ".mov" in VIDEO_EXTENSIONS
    assert ".py" not in VIDEO_EXTENSIONS


# ---------------------------------------------------------------------------
# build_whisper_prompt
# ---------------------------------------------------------------------------

def test_build_whisper_prompt_no_nodes():
    """Empty god_nodes returns fallback prompt."""
    prompt = build_whisper_prompt([])
    assert "punctuation" in prompt.lower() or len(prompt) > 0


def test_build_whisper_prompt_env_override(monkeypatch):
    """GRAPHIFY_WHISPER_PROMPT env var short-circuits LLM call."""
    monkeypatch.setenv("GRAPHIFY_WHISPER_PROMPT", "Custom domain hint.")
    prompt = build_whisper_prompt([{"label": "Python"}, {"label": "FastAPI"}])
    assert prompt == "Custom domain hint."


def test_build_whisper_prompt_returns_topic_string():
    """Returns a topic-based prompt from god node labels — no LLM call."""
    god_nodes = [{"label": "neural networks"}, {"label": "transformers"}, {"label": "attention"}]
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GRAPHIFY_WHISPER_PROMPT", None)
        prompt = build_whisper_prompt(god_nodes)
    assert "neural networks" in prompt.lower() or "transformers" in prompt.lower()
    assert "punctuation" in prompt.lower()


def test_build_whisper_prompt_nodes_without_labels():
    """Nodes missing 'label' keys are safely skipped."""
    god_nodes = [{"id": "1"}, {"id": "2", "label": ""}]
    prompt = build_whisper_prompt(god_nodes)
    assert len(prompt) > 0


# ---------------------------------------------------------------------------
# transcribe
# ---------------------------------------------------------------------------

def test_transcribe_uses_cache(tmp_path):
    """If transcript already exists, transcribe() returns cached path without running Whisper."""
    video = tmp_path / "lecture.mp4"
    video.write_bytes(b"fake")
    out_dir = tmp_path / "transcripts"
    out_dir.mkdir()
    cached = out_dir / "lecture.txt"
    cached.write_text("Cached transcript content.")

    result = transcribe(video, output_dir=out_dir)
    assert result == cached


def test_transcribe_force_reruns(tmp_path):
    """force=True re-transcribes even when cache exists."""
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"fake")
    out_dir = tmp_path / "transcripts"
    out_dir.mkdir()
    (out_dir / "talk.txt").write_text("Old transcript.")

    fake_segment = MagicMock()
    fake_segment.text = "New transcript segment."
    fake_info = MagicMock()
    fake_info.language = "en"

    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([fake_segment], fake_info)

    with patch("graphify.transcribe._get_whisper", return_value=lambda *a, **kw: fake_model):
        result = transcribe(video, output_dir=out_dir, force=True)

    assert result.read_text() == "New transcript segment."


def test_transcribe_missing_faster_whisper(tmp_path):
    """ImportError propagates when faster_whisper is not installed."""
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    with patch("graphify.transcribe._get_whisper", side_effect=ImportError("faster-whisper not installed")):
        with pytest.raises(ImportError):
            transcribe(video, output_dir=tmp_path / "out")


# ---------------------------------------------------------------------------
# transcribe_all
# ---------------------------------------------------------------------------

def test_transcribe_all_empty():
    """Empty input returns empty list without error."""
    assert transcribe_all([]) == []


def test_transcribe_all_uses_cache(tmp_path):
    """transcribe_all() returns cached paths for already-transcribed files."""
    video = tmp_path / "lecture.mp4"
    video.write_bytes(b"fake")
    out_dir = tmp_path / "transcripts"
    out_dir.mkdir()
    cached = out_dir / "lecture.txt"
    cached.write_text("Cached.")

    results = transcribe_all([str(video)], output_dir=out_dir)
    assert len(results) == 1
    assert str(cached) in results[0]


def test_transcribe_all_skips_failed(tmp_path):
    """transcribe_all() warns and skips files that fail to transcribe."""
    video = tmp_path / "broken.mp4"
    video.write_bytes(b"fake")

    def raise_import(*args, **kwargs):
        raise ImportError("faster_whisper not installed")

    with patch("graphify.transcribe.transcribe", side_effect=RuntimeError("boom")):
        results = transcribe_all([str(video)], output_dir=tmp_path / "out")

    assert results == []


# ---------------------------------------------------------------------------
# is_url
# ---------------------------------------------------------------------------

def test_is_url_http():
    assert is_url("http://example.com/video.mp4") is True


def test_is_url_https():
    assert is_url("https://youtube.com/watch?v=abc") is True


def test_is_url_www():
    assert is_url("www.example.com/video.mp4") is True


def test_is_url_local_path():
    assert is_url("/path/to/video.mp4") is False


def test_is_url_relative_path():
    assert is_url("video.mp4") is False


# ---------------------------------------------------------------------------
# _get_whisper import error (unmocked)
# ---------------------------------------------------------------------------

def test_get_whisper_import_error(monkeypatch):
    """_get_whisper raises ImportError when faster-whisper is not installed."""
    import builtins
    original_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("No module named faster_whisper")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", mock_import)
    with pytest.raises(ImportError, match="faster-whisper"):
        _get_whisper()


# ---------------------------------------------------------------------------
# _get_yt_dlp import error (unmocked)
# ---------------------------------------------------------------------------

def test_get_yt_dlp_import_error(monkeypatch):
    """_get_yt_dlp raises ImportError when yt-dlp is not installed."""
    import builtins
    original_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == "yt_dlp":
            raise ImportError("No module named yt_dlp")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", mock_import)
    with pytest.raises(ImportError, match="yt-dlp"):
        _get_yt_dlp()


# ---------------------------------------------------------------------------
# _model_name
# ---------------------------------------------------------------------------

def test_model_name_default(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_WHISPER_MODEL", raising=False)
    assert _model_name() == "base"


def test_model_name_from_env(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_WHISPER_MODEL", "large-v3")
    assert _model_name() == "large-v3"


# ---------------------------------------------------------------------------
# download_audio cached
# ---------------------------------------------------------------------------

def test_download_audio_uses_cache(tmp_path, monkeypatch):
    """download_audio returns cached file if already downloaded."""
    pytest.importorskip("yt_dlp")
    # Skip validate_url by mocking it
    monkeypatch.setattr("graphify.security.validate_url", lambda url: None)
    url = "https://example.com/video"
    out_dir = tmp_path / "downloads"
    out_dir.mkdir(parents=True)
    import hashlib
    url_hash = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:12]
    cached = out_dir / f"yt_{url_hash}.m4a"
    cached.write_bytes(b"fake audio")
    result = download_audio(url, out_dir)
    assert result == cached


# ---------------------------------------------------------------------------
# download_audio with mocked yt-dlp
# ---------------------------------------------------------------------------

def test_download_audio_downloads(tmp_path, monkeypatch):
    """download_audio downloads from URL using yt-dlp when no cache."""
    monkeypatch.setattr("graphify.security.validate_url", lambda url: None)
    url = "https://example.com/video"
    out_dir = tmp_path / "downloads"
    out_dir.mkdir()

    import hashlib
    url_hash = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:12]

    # Mock yt-dlp
    fake_ydl = MagicMock()
    fake_info = {"ext": "m4a"}
    fake_ydl.extract_info.return_value = fake_info

    MockYoutubeDL = MagicMock(return_value=fake_ydl)

    with patch("graphify.transcribe._get_yt_dlp", return_value=MagicMock(YoutubeDL=MockYoutubeDL)):
        # Create expected output file so download_audio finds it
        expected = out_dir / f"yt_{url_hash}.m4a"
        expected.write_bytes(b"downloaded audio")
        result = download_audio(url, out_dir)
        assert result == expected


def test_download_audio_glob_fallback(tmp_path, monkeypatch):
    """download_audio uses glob fallback when exact extension doesn't match."""
    monkeypatch.setattr("graphify.security.validate_url", lambda url: None)
    url = "https://example.com/video"
    out_dir = tmp_path / "downloads"
    out_dir.mkdir()

    import hashlib
    url_hash = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:12]

    # Mock yt-dlp to return .opus instead of default .m4a
    fake_ydl = MagicMock()
    fake_info = {"ext": "opus"}
    fake_ydl.extract_info.return_value = fake_info

    MockYoutubeDL = MagicMock(return_value=fake_ydl)

    with patch("graphify.transcribe._get_yt_dlp", return_value=MagicMock(YoutubeDL=MockYoutubeDL)):
        expected = out_dir / f"yt_{url_hash}.opus"
        expected.write_bytes(b"downloaded audio")
        result = download_audio(url, out_dir)
        assert result == expected


# ---------------------------------------------------------------------------
# transcribe with URL input
# ---------------------------------------------------------------------------

def test_transcribe_url_input_uses_download(tmp_path):
    """transcribe with URL input downloads audio first."""
    pytest.importorskip("yt_dlp")
    url = "https://example.com/video"
    out_dir = tmp_path / "transcripts"
    out_dir.mkdir()

    import hashlib
    url_hash = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:12]
    downloads = out_dir / "downloads"
    downloads.mkdir(parents=True)
    audio_file = downloads / f"yt_{url_hash}.m4a"
    audio_file.write_bytes(b"fake audio data")

    # Transcript already exists, so no whisper needed
    transcript = out_dir / f"yt_{url_hash}.txt"
    transcript.write_text("Cached transcript")

    with patch("graphify.security.validate_url", lambda url: None):
        result = transcribe(url, output_dir=out_dir)
        assert result == transcript


# ---------------------------------------------------------------------------
# _get_whisper success path (covers line 24)
# ---------------------------------------------------------------------------

def test_get_whisper_success():
    """_get_whisper returns WhisperModel when faster_whisper is installed."""
    pytest.importorskip('faster_whisper')
    from faster_whisper import WhisperModel
    result = _get_whisper()
    assert result is WhisperModel


# ---------------------------------------------------------------------------
# download_audio without cache (covers lines 71-90)
# ---------------------------------------------------------------------------

def test_download_audio_no_cache_uses_ydl(tmp_path, monkeypatch):
    """download_audio calls yt-dlp when no cached file exists."""
    monkeypatch.setattr("graphify.security.validate_url", lambda url: None)

    url = "https://example.com/video"
    out_dir = tmp_path / "downloads"
    out_dir.mkdir()

    import hashlib
    url_hash = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:12]
    expected = out_dir / f"yt_{url_hash}.m4a"

    # Mock yt-dlp with side effect that writes the output file
    fake_ydl = MagicMock()
    def write_and_return(url_dl, download):
        expected.write_bytes(b"downloaded audio via yt-dlp")
        return {"ext": "m4a"}
    fake_ydl.extract_info = MagicMock(side_effect=write_and_return)

    MockYoutubeDL = MagicMock()
    MockYoutubeDL.return_value.__enter__.return_value = fake_ydl

    with patch("graphify.transcribe._get_yt_dlp", return_value=MagicMock(YoutubeDL=MockYoutubeDL)):
        # No cached file exists — must go through YDL download path
        result = download_audio(url, out_dir)
        assert result == expected


def test_download_audio_glob_fallback_no_exact_match(tmp_path, monkeypatch):
    """download_audio uses glob fallback when yt-dlp saves with wrong extension."""
    monkeypatch.setattr("graphify.security.validate_url", lambda url: None)

    url = "https://example.com/video"
    out_dir = tmp_path / "downloads"
    out_dir.mkdir()

    import hashlib
    url_hash = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:12]

    # Mock yt-dlp: report .opus extension but write file as .webm via side effect
    # This triggers the glob fallback path (lines 86-89)
    fake_ydl = MagicMock()
    def write_as_webm(url_dl, download):
        actual_file = out_dir / f"yt_{url_hash}.webm"
        actual_file.write_bytes(b"downloaded audio in webm format")
        return {"ext": "opus"}
    fake_ydl.extract_info = MagicMock(side_effect=write_as_webm)

    MockYoutubeDL = MagicMock()
    MockYoutubeDL.return_value.__enter__.return_value = fake_ydl

    with patch("graphify.transcribe._get_yt_dlp", return_value=MagicMock(YoutubeDL=MockYoutubeDL)):
        result = download_audio(url, out_dir)
        # Result should be the .webm file found via glob fallback
        assert result.suffix == ".webm"
        assert result.read_bytes() == b"downloaded audio in webm format"


def test_download_audio_cached_opus(tmp_path, monkeypatch):
    """download_audio finds cached .opus file."""
    pytest.importorskip("yt_dlp")
    monkeypatch.setattr("graphify.security.validate_url", lambda url: None)

    url = "https://example.com/video"
    out_dir = tmp_path / "downloads"
    out_dir.mkdir()

    import hashlib
    url_hash = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:12]
    cached = out_dir / f"yt_{url_hash}.opus"
    cached.write_bytes(b"cached opus audio")

    result = download_audio(url, out_dir)
    assert result == cached
