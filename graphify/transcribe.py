# Video transcription using faster-whisper
# Converts video/audio files to text transcripts for graph extraction
from __future__ import annotations

import os
from pathlib import Path


VIDEO_EXTENSIONS = {'.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v', '.mp3', '.wav', '.m4a', '.ogg'}
URL_PREFIXES = ('http://', 'https://', 'www.')

_DEFAULT_MODEL = "base"
_TRANSCRIPTS_DIR = "graphify-out/transcripts"
_FALLBACK_PROMPT = "Use proper punctuation and paragraph breaks."


def _model_name() -> str:
    return os.environ.get("GRAPHIFY_WHISPER_MODEL", _DEFAULT_MODEL)


def _get_whisper():
    try:
        from faster_whisper import WhisperModel
        return WhisperModel
    except ImportError as exc:
        raise ImportError(
            "Video transcription requires faster-whisper. "
            "Run: pip install 'graphifyy[video]'"
        ) from exc


def _get_yt_dlp():
    try:
        import yt_dlp
        return yt_dlp
    except ImportError as exc:
        raise ImportError(
            "YouTube/URL download requires yt-dlp. "
            "Run: pip install 'graphifyy[video]'"
        ) from exc


def is_url(path: str) -> bool:
    """Return True if the string looks like a URL rather than a file path."""
    return any(path.startswith(p) for p in URL_PREFIXES)


def download_audio(url: str, output_dir: Path) -> Path:
    """Download audio-only stream from a URL using yt-dlp.

    Returns the path to the downloaded audio file (.m4a or .opus).
    Uses cached file if already downloaded.
    """
    from graphify.security import validate_url
    validate_url(url)  # blocks private IPs, bad schemes before yt-dlp runs
    yt_dlp = _get_yt_dlp()
    output_dir.mkdir(parents=True, exist_ok=True)

    # yt-dlp uses %(title)s which can be long/weird — use a stable name based on URL hash
    import hashlib
    url_hash = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:12]
    out_template = str(output_dir / f"yt_{url_hash}.%(ext)s")

    # Check for already-downloaded file
    for ext in ('.m4a', '.opus', '.mp3', '.ogg', '.wav', '.webm'):
        candidate = output_dir / f"yt_{url_hash}{ext}"
        if candidate.exists():
            print(f"  cached audio: {candidate.name}")
            return candidate

    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': out_template,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'postprocessors': [],  # no ffmpeg needed — use native audio
    }

    print(f"  downloading audio: {url[:80]} ...", flush=True)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        ext = info.get('ext', 'm4a')
        downloaded = output_dir / f"yt_{url_hash}.{ext}"
        if not downloaded.exists():
            # yt-dlp may have picked a different extension
            for p in output_dir.glob(f"yt_{url_hash}.*"):
                downloaded = p
                break
        return downloaded


def build_whisper_prompt(god_nodes: list[dict]) -> str:
    """Build a domain hint for Whisper from god nodes extracted from the corpus.

    Formats the top god node labels into a topic string for Whisper.
    The coding agent (Claude Code, Codex, etc.) generates the actual one-sentence
    domain hint from these labels and passes it via GRAPHIFY_WHISPER_PROMPT or
    as initial_prompt — no separate API call needed here.
    """
    if not god_nodes:
        return _FALLBACK_PROMPT

    override = os.environ.get("GRAPHIFY_WHISPER_PROMPT")
    if override:
        return override

    labels = [n.get("label", "") for n in god_nodes[:10] if n.get("label")]
    if not labels:
        return _FALLBACK_PROMPT

    topics = ", ".join(labels[:5])
    return f"Technical discussion about {topics}. Use proper punctuation and paragraph breaks."


def transcribe(
    video_path: Path | str,
    output_dir: Path | None = None,
    initial_prompt: str | None = None,
    force: bool = False,
) -> Path:
    """Transcribe a video/audio file or URL to a .txt transcript.

    If video_path is a URL, audio is downloaded first via yt-dlp.
    Returns the path to the saved transcript file.
    Uses cached transcript if it exists unless force=True.

    initial_prompt: domain hint for Whisper (built from corpus god nodes).
    force: re-transcribe even if transcript already exists.
    """
    out_dir = Path(output_dir) if output_dir else Path(_TRANSCRIPTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    if is_url(str(video_path)):
        audio_path = download_audio(str(video_path), out_dir / "downloads")
    else:
        audio_path = Path(video_path)

    transcript_path = out_dir / (audio_path.stem + ".txt")
    if transcript_path.exists() and not force:
        return transcript_path

    WhisperModel = _get_whisper()
    model_name = _model_name()
    prompt = initial_prompt or _FALLBACK_PROMPT

    print(f"  transcribing {audio_path.name} (model={model_name}) ...", flush=True)
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        initial_prompt=prompt,
    )

    lines = [segment.text.strip() for segment in segments if segment.text.strip()]
    transcript = "\n".join(lines)

    transcript_path.write_text(transcript, encoding="utf-8")
    lang = info.language if hasattr(info, "language") else "unknown"
    print(f"  transcript saved -> {transcript_path} (lang={lang}, {len(lines)} segments)")
    return transcript_path


def transcribe_all(
    video_files: list[str],
    output_dir: Path | None = None,
    initial_prompt: str | None = None,
) -> list[str]:
    """Transcribe a list of video/audio files or URLs, return paths to transcript .txt files.

    Already-transcribed files are returned from cache instantly.
    initial_prompt is shared across all files — built once from corpus god nodes.
    """
    if not video_files:
        return []

    transcript_paths = []
    for vf in video_files:
        try:
            t = transcribe(vf, output_dir, initial_prompt=initial_prompt)
            transcript_paths.append(str(t))
        except Exception as exc:
            print(f"  warning: could not transcribe {vf}: {exc}")
    return transcript_paths
