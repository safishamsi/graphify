"""Verify cache and manifest I/O survive non-ASCII content cross-platform.

On Windows the default text codec is cp1252, which raises UnicodeEncodeError
when writing CJK / emoji / accented Latin content unless an explicit
encoding="utf-8" is passed. This test pins the behavior so any future
regression is caught immediately.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.cache import load_cached, save_cached
from graphify.detect import load_manifest, save_manifest


# Sample content that crashes default-codec write_text on Windows
NON_ASCII_PAYLOADS = [
    "ascii_only",
    "中文测试",                      # CJK
    "日本語コメント",                 # Japanese
    "한글 테스트",                    # Korean
    "café résumé naïve",              # Accented Latin
    "emoji 🚀 mixed 中 with 한",     # Mixed scripts + emoji
]


def _make_source_file(tmp_path: Path, name: str = "module.py") -> Path:
    """Create a temporary source file we can hash and cache."""
    source = tmp_path / name
    source.write_text("x = 1\n", encoding="utf-8")
    return source


@pytest.mark.parametrize("payload", NON_ASCII_PAYLOADS)
def test_cache_roundtrip_preserves_non_ascii_labels(tmp_path, payload):
    """save_cached / load_cached must roundtrip non-ASCII node labels."""
    source = _make_source_file(tmp_path)
    result = {
        "nodes": [{"id": "n1", "label": payload, "source_file": str(source)}],
        "edges": [],
    }
    save_cached(source, result, root=tmp_path)
    loaded = load_cached(source, root=tmp_path)

    assert loaded is not None
    assert loaded["nodes"][0]["label"] == payload


def test_cache_roundtrip_preserves_non_ascii_in_source_file_path(tmp_path):
    """Cache must handle source_file paths containing non-ASCII characters."""
    # Create a directory and file with CJK characters in the name
    cjk_dir = tmp_path / "中文目录"
    cjk_dir.mkdir()
    source = cjk_dir / "模块.py"
    source.write_text("x = 1\n", encoding="utf-8")

    result = {
        "nodes": [{"id": "n1", "label": "MyClass", "source_file": str(source)}],
        "edges": [],
    }
    save_cached(source, result, root=tmp_path)
    loaded = load_cached(source, root=tmp_path)

    assert loaded is not None
    assert loaded["nodes"][0]["source_file"] == str(source)


def test_cache_file_is_valid_utf8_on_disk(tmp_path):
    """The cache file written to disk must be readable as UTF-8 by other tools."""
    source = _make_source_file(tmp_path)
    payload = "中文 emoji 🚀"
    result = {"nodes": [{"id": "n1", "label": payload}], "edges": []}
    save_cached(source, result, root=tmp_path)

    # Find the cache entry on disk and verify it's valid UTF-8 JSON
    cache_files = list((tmp_path / "graphify-out" / "cache").glob("*.json"))
    assert len(cache_files) == 1
    raw = cache_files[0].read_bytes()
    # Round-trip via UTF-8 decode + JSON parse must succeed
    parsed = json.loads(raw.decode("utf-8"))
    assert parsed["nodes"][0]["label"] == payload


@pytest.mark.parametrize("path_name", [
    "ascii_module.py",
    "中文模块.py",
    "日本語.py",
    "café.py",
])
def test_manifest_roundtrip_preserves_non_ascii_paths(tmp_path, path_name):
    """save_manifest / load_manifest must roundtrip non-ASCII file paths."""
    source = tmp_path / path_name
    source.write_text("x = 1\n", encoding="utf-8")

    manifest_path = str(tmp_path / "manifest.json")
    save_manifest({"code": [str(source)]}, manifest_path=manifest_path)

    loaded = load_manifest(manifest_path=manifest_path)
    assert str(source) in loaded
    assert loaded[str(source)] == source.stat().st_mtime


def test_manifest_file_is_valid_utf8_on_disk(tmp_path):
    """The manifest file on disk must be readable as UTF-8."""
    source = tmp_path / "中文.py"
    source.write_text("x = 1\n", encoding="utf-8")

    manifest_path = str(tmp_path / "manifest.json")
    save_manifest({"code": [str(source)]}, manifest_path=manifest_path)

    raw = Path(manifest_path).read_bytes()
    parsed = json.loads(raw.decode("utf-8"))
    assert str(source) in parsed
