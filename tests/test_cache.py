"""Tests for graphify/cache.py."""
import json
import pytest
from pathlib import Path
from graphify.cache import file_hash, cache_dir, load_cached, save_cached, cached_files, clear_cache, _body_content, _relativize_source_value, _load_source_value


@pytest.fixture
def tmp_file(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("hello world")
    return f


@pytest.fixture
def cache_root(tmp_path):
    return tmp_path


def test_file_hash_consistent(tmp_file):
    """Same file gives same hash on repeated calls."""
    h1 = file_hash(tmp_file)
    h2 = file_hash(tmp_file)
    assert h1 == h2
    assert isinstance(h1, str)
    assert len(h1) == 64  # SHA256 hex digest length


def test_file_hash_changes(tmp_path):
    """Different file contents give different hashes."""
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("content one")
    f2.write_text("content two")
    assert file_hash(f1) != file_hash(f2)


def test_cache_roundtrip(tmp_file, cache_root):
    """Save then load returns the same result dict."""
    result = {"nodes": [{"id": "n1", "label": "Node1"}], "edges": []}
    save_cached(tmp_file, result, root=cache_root)
    loaded = load_cached(tmp_file, root=cache_root)
    assert loaded == result


def test_cache_miss_on_change(tmp_file, cache_root):
    """After file content changes, load_cached returns None."""
    result = {"nodes": [], "edges": [{"source": "a", "target": "b"}]}
    save_cached(tmp_file, result, root=cache_root)
    # Modify the file
    tmp_file.write_text("completely different content")
    assert load_cached(tmp_file, root=cache_root) is None


def test_cached_files(tmp_path, cache_root):
    """cached_files returns the set of cached hashes."""
    f1 = tmp_path / "file1.py"
    f2 = tmp_path / "file2.py"
    f1.write_text("alpha")
    f2.write_text("beta")

    save_cached(f1, {"nodes": [], "edges": []}, root=cache_root)
    save_cached(f2, {"nodes": [], "edges": []}, root=cache_root)

    hashes = cached_files(cache_root)
    assert file_hash(f1, cache_root) in hashes
    assert file_hash(f2, cache_root) in hashes


def test_clear_cache(tmp_file, cache_root):
    """clear_cache removes all .json files from graphify-out/cache/ (all subdirs)."""
    save_cached(tmp_file, {"nodes": [], "edges": []}, root=cache_root)
    # Since v0.5.3 entries go into cache/ast/, not the flat cache/ dir
    cache_base = cache_root / "graphify-out" / "cache"
    assert len(list(cache_base.rglob("*.json"))) > 0
    clear_cache(cache_root)
    assert len(list(cache_base.rglob("*.json"))) == 0


def test_md_frontmatter_only_change_same_hash(tmp_path):
    """Changing only frontmatter fields in a .md file does not change the hash."""
    f = tmp_path / "doc.md"
    f.write_text("---\nreviewed: 2026-01-01\n---\n\n# Title\n\nBody text.")
    h1 = file_hash(f)
    f.write_text("---\nreviewed: 2026-04-09\n---\n\n# Title\n\nBody text.")
    h2 = file_hash(f)
    assert h1 == h2


def test_md_body_change_different_hash(tmp_path):
    """Changing the body of a .md file produces a different hash."""
    f = tmp_path / "doc.md"
    f.write_text("---\nreviewed: 2026-01-01\n---\n\n# Title\n\nOriginal body.")
    h1 = file_hash(f)
    f.write_text("---\nreviewed: 2026-01-01\n---\n\n# Title\n\nChanged body.")
    h2 = file_hash(f)
    assert h1 != h2


def test_md_no_frontmatter_hashed_normally(tmp_path):
    """A .md file with no frontmatter is hashed by its full content."""
    f = tmp_path / "doc.md"
    f.write_text("# Just a heading\n\nNo frontmatter here.")
    h1 = file_hash(f)
    f.write_text("# Just a heading\n\nDifferent content.")
    h2 = file_hash(f)
    assert h1 != h2


def test_non_md_file_hashed_fully(tmp_path):
    """Non-.md files are still hashed by their full content."""
    f = tmp_path / "script.py"
    f.write_text("# comment\nx = 1")
    h1 = file_hash(f)
    f.write_text("# changed comment\nx = 1")
    h2 = file_hash(f)
    assert h1 != h2


def test_body_content_strips_frontmatter():
    """_body_content correctly strips YAML frontmatter."""
    content = b"---\ntitle: Test\n---\n\nActual body."
    assert _body_content(content) == b"\n\nActual body."


def test_body_content_no_frontmatter():
    """_body_content returns content unchanged when no frontmatter present."""
    content = b"No frontmatter here."
    assert _body_content(content) == content


# ---------------------------------------------------------------------------
# check_semantic_cache / save_semantic_cache
# ---------------------------------------------------------------------------

def test_check_semantic_cache_empty(tmp_path):
    from graphify.cache import check_semantic_cache
    files = [str(tmp_path / "nonexistent.md")]
    nodes, edges, hyperedges, uncached = check_semantic_cache(files, root=tmp_path)
    assert uncached == files
    assert nodes == []


def test_save_semantic_cache_and_load(tmp_path):
    from graphify.cache import save_semantic_cache, check_semantic_cache
    f = tmp_path / "test.py"
    f.write_text("print('hello')")
    source_file = str(f)
    nodes = [{"id": "n1", "label": "myFunc", "source_file": source_file}]
    edges = [{"source": "n1", "target": "n2", "relation": "calls", "source_file": source_file}]
    saved = save_semantic_cache(nodes, edges, root=tmp_path)
    assert saved == 1
    c_nodes, c_edges, c_hyper, uncached = check_semantic_cache([source_file], root=tmp_path)
    assert len(uncached) == 0
    assert len(c_nodes) == 1


def test_cached_files(tmp_path):
    from graphify.cache import cached_files
    f = tmp_path / "test.py"
    f.write_text("x = 1")
    save_cached(f, {"nodes": [], "edges": []}, root=tmp_path)
    hashes = cached_files(root=tmp_path)
    assert len(hashes) >= 1


def test_clear_cache(tmp_path):
    from graphify.cache import clear_cache, cached_files
    f = tmp_path / "test.py"
    f.write_text("x = 1")
    save_cached(f, {"nodes": [], "edges": []}, root=tmp_path)
    assert len(cached_files(root=tmp_path)) >= 1
    clear_cache(root=tmp_path)
    assert len(cached_files(root=tmp_path)) == 0


def test_file_hash_directory_raises(tmp_path):
    with pytest.raises(IsADirectoryError):
        file_hash(tmp_path)


def test_load_cached_missing_file(tmp_path):
    from graphify.cache import load_cached
    result = load_cached(tmp_path / "nope.py", root=tmp_path)
    assert result is None


def test_cache_dir_creates(tmp_path):
    d = cache_dir(root=tmp_path)
    assert d.exists()
    assert d.name == "ast"


def test_save_cached_skips_directory(tmp_path):
    """save_cached no-ops on directories (subagent edge case)."""
    d = tmp_path / "mydir"
    d.mkdir()
    save_cached(d, {"nodes": []}, root=tmp_path)  # should not raise


# ---------------------------------------------------------------------------
# load_cached edge cases
# ---------------------------------------------------------------------------

def test_load_cached_corrupted_json(tmp_path):
    """load_cached returns None for corrupted JSON in cache entry."""
    from graphify.cache import cache_dir
    f = tmp_path / "test.py"
    f.write_text("print('hello')")
    h = file_hash(f, tmp_path)
    # Write invalid JSON to the cache entry
    d = cache_dir(tmp_path, kind="ast")
    entry = d / f"{h}.json"
    entry.write_text("not json{{{")
    result = load_cached(f, root=tmp_path)
    assert result is None


def test_load_cached_legacy_ast_fallback(tmp_path):
    """load_cached checks legacy flat cache/ dir for AST entries."""
    f = tmp_path / "test.py"
    f.write_text("x = 1")
    h = file_hash(f, tmp_path)
    # Write to legacy flat cache/ (not cache/ast/)
    legacy_dir = tmp_path / "graphify-out" / "cache"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_entry = legacy_dir / f"{h}.json"
    result_data = {"nodes": [{"id": "n1"}], "edges": []}
    legacy_entry.write_text(json.dumps(result_data))
    loaded = load_cached(f, root=tmp_path, kind="ast")
    assert loaded == result_data


def test_load_cached_legacy_corrupted(tmp_path):
    """load_cached handles corrupted legacy cache JSON."""
    f = tmp_path / "test.py"
    f.write_text("x = 1")
    h = file_hash(f, tmp_path)
    legacy_dir = tmp_path / "graphify-out" / "cache"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_entry = legacy_dir / f"{h}.json"
    legacy_entry.write_text("not json")
    result = load_cached(f, root=tmp_path, kind="ast")
    assert result is None


# ---------------------------------------------------------------------------
# cached_files with legacy entries
# ---------------------------------------------------------------------------

def test_cached_files_legacy_entries(tmp_path):
    """cached_files also includes legacy flat cache/ entries."""
    legacy_dir = tmp_path / "graphify-out" / "cache"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "abcdef123456.json").write_text("{}")
    hashes = cached_files(root=tmp_path)
    assert "abcdef123456" in hashes


# ---------------------------------------------------------------------------
# save_semantic_cache edge cases
# ---------------------------------------------------------------------------

def test_save_semantic_cache_with_hyperedges(tmp_path):
    """save_semantic_cache saves hyperedges grouped by source_file."""
    from graphify.cache import save_semantic_cache
    f = tmp_path / "test.py"
    f.write_text("x = 1")
    source_file = str(f)
    nodes = [{"id": "n1", "source_file": source_file}]
    edges = []
    hyperedges = [{"nodes": ["n1", "n2"], "source_file": source_file}]
    saved = save_semantic_cache(nodes, edges, hyperedges, root=tmp_path)
    assert saved == 1


def test_save_semantic_cache_relative_path(tmp_path):
    """save_semantic_cache resolves relative source_file paths."""
    from graphify.cache import save_semantic_cache
    f = tmp_path / "test.py"
    f.write_text("x = 1")
    nodes = [{"id": "n1", "source_file": "test.py"}]
    edges = []
    saved = save_semantic_cache(nodes, edges, root=tmp_path)
    assert saved == 1


def test_save_semantic_cache_missing_file(tmp_path):
    """save_semantic_cache skips files that don't exist."""
    from graphify.cache import save_semantic_cache
    nodes = [{"id": "n1", "source_file": "/nonexistent/file.py"}]
    edges = []
    saved = save_semantic_cache(nodes, edges, root=tmp_path)
    assert saved == 0


# ---------------------------------------------------------------------------
# _normalize_path Windows path handling (lines 35-38)
# ---------------------------------------------------------------------------

def test_normalize_path_non_windows_returns_unchanged():
    """_normalize_path returns path unchanged on non-Windows platforms."""
    from graphify.cache import _normalize_path
    p = Path("/tmp/test/file.py")
    result = _normalize_path(p)
    assert result == p


def test_normalize_path_win32_no_prefix(monkeypatch):
    """_normalize_path on win32 without extended prefix."""
    monkeypatch.setattr("sys.platform", "win32")
    import os as os_mod
    from graphify.cache import _normalize_path
    p = Path("C:\\Users\\test\\file.py")
    result = _normalize_path(p)
    assert result == Path(os_mod.path.normcase("C:\\Users\\test\\file.py"))


def test_normalize_path_win32_extended_prefix(monkeypatch):
    """_normalize_path on win32 strips \\\\?\\ extended-length prefix."""
    monkeypatch.setattr("sys.platform", "win32")
    import os as os_mod
    from graphify.cache import _normalize_path
    p = Path("\\\\?\\C:\\Users\\test\\file.py")
    result = _normalize_path(p)
    assert result == Path(os_mod.path.normcase("C:\\Users\\test\\file.py"))


# ---------------------------------------------------------------------------
# save_cached exception handling (lines 134-149)
# ---------------------------------------------------------------------------

def test_save_cached_permission_error_fallback(tmp_path, monkeypatch):
    """save_cached handles PermissionError by falling back to copy-then-delete."""
    import os as os_mod
    import shutil as shutil_mod
    from graphify.cache import save_cached

    f = tmp_path / "test.py"
    f.write_text("x = 1")

    calls = {"copy2": 0, "unlink": 0}
    _real_copy2 = shutil_mod.copy2  # save original before mocking

    def mock_replace(src, dst):
        raise PermissionError("Access denied")

    def mock_copy2(src, dst):
        calls["copy2"] += 1
        _real_copy2(src, dst)

    def mock_unlink(path):
        calls["unlink"] += 1
        os_mod.remove(path)

    monkeypatch.setattr(os_mod, "replace", mock_replace)
    monkeypatch.setattr(shutil_mod, "copy2", mock_copy2)
    monkeypatch.setattr(os_mod, "unlink", mock_unlink)

    save_cached(f, {"nodes": [], "edges": []}, root=tmp_path)

    # Verify fallback was used
    assert calls["copy2"] == 1
    assert calls["unlink"] == 1


def test_save_cached_general_exception_cleanup(tmp_path, monkeypatch):
    """save_cached cleans up tmp file on general Exception, then re-raises."""
    import os as os_mod
    from graphify.cache import save_cached

    f = tmp_path / "test.py"
    f.write_text("x = 1")

    # Mock json.dumps to raise a generic Exception during write
    import json as json_mod
    orig_dumps = json_mod.dumps

    def mock_dumps(obj, **kwargs):
        raise RuntimeError("Serialization failed")

    monkeypatch.setattr(json_mod, "dumps", mock_dumps)

    with pytest.raises(RuntimeError, match="Serialization failed"):
        save_cached(f, {"nodes": [], "edges": []}, root=tmp_path)


def test_save_cached_oserror_on_close_cleanup(tmp_path, monkeypatch):
    """save_cached handles OSError during tmp file close cleanly."""
    import os as os_mod
    from graphify.cache import save_cached

    f = tmp_path / "test.py"
    f.write_text("x = 1")

    # Raise RuntimeError during write, then OSError on close
    import json as json_mod

    def mock_dumps(obj, **kwargs):
        raise RuntimeError("Serialization failed")

    def mock_close(fd):
        raise OSError("Bad file descriptor")

    monkeypatch.setattr(json_mod, "dumps", mock_dumps)
    monkeypatch.setattr(os_mod, "close", mock_close)

    # Should still raise the original RuntimeError, not OSError
    with pytest.raises(RuntimeError, match="Serialization failed"):
        save_cached(f, {"nodes": [], "edges": []}, root=tmp_path)


def test_save_cached_oserror_on_unlink_during_cleanup(tmp_path, monkeypatch):
    """save_cached handles OSError during tmp file unlink in exception handler."""
    import os as os_mod
    from graphify.cache import save_cached

    f = tmp_path / "test.py"
    f.write_text("x = 1")

    # Raise RuntimeError during write, then OSError on both close AND unlink
    import json as json_mod

    def mock_dumps(obj, **kwargs):
        raise RuntimeError("Serialization failed")

    def mock_unlink(path):
        raise OSError("Permission denied")

    monkeypatch.setattr(json_mod, "dumps", mock_dumps)
    monkeypatch.setattr(os_mod, "unlink", mock_unlink)

    # Should still raise the original RuntimeError, not OSError
    with pytest.raises(RuntimeError, match="Serialization failed"):
        save_cached(f, {"nodes": [], "edges": []}, root=tmp_path)


# ---------------------------------------------------------------------------
# clear_cache legacy flat entries (line 173)
# ---------------------------------------------------------------------------

def test_clear_cache_legacy_flat_entries(tmp_path):
    """clear_cache removes legacy flat .json entries in cache/ dir."""
    from graphify.cache import clear_cache
    import os
    # Set GRAPHIFY_OUT so clear_cache uses the tmp_path
    os.environ["GRAPHIFY_OUT"] = "graphify-out"
    try:
        legacy_dir = tmp_path / "graphify-out" / "cache"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy_entry = legacy_dir / "abc.json"
        legacy_entry.write_text("{}")

        assert legacy_entry.exists()
        clear_cache(root=tmp_path)
        assert not legacy_entry.exists()
    finally:
        os.environ.pop("GRAPHIFY_OUT", None)


# ---------------------------------------------------------------------------
# Patch 1: Portable source_file cache
# ---------------------------------------------------------------------------

def test_save_cached_relativizes_source_file(tmp_path):
    """save_cached stores source_file values relative to root."""
    (tmp_path / "src").mkdir()
    f = tmp_path / "src" / "test.py"
    f.write_text("x = 1")

    result = {
        "nodes": [{"id": "n1", "label": "N1", "source_file": str(f.resolve())}],
        "edges": [],
    }
    save_cached(f, result, root=tmp_path)

    h = file_hash(f, tmp_path)
    entry = cache_dir(tmp_path) / f"{h}.json"
    assert entry.exists()
    data = json.loads(entry.read_text())
    source = data["nodes"][0]["source_file"]
    # Should be relative: "src/test.py" not absolute
    assert not source.startswith("/"), f"Expected relative, got: {source}"
    assert source.endswith("test.py")


# ---------------------------------------------------------------------------
# _relativize_source_value edge cases
# ---------------------------------------------------------------------------

def test_relativize_source_value_empty():
    """Empty string is returned as-is (line 88-89)."""
    assert _relativize_source_value("", Path("/root")) == ""


def test_relativize_source_value_already_relative():
    """Relative path is returned as-is (line 92-93)."""
    assert _relativize_source_value("src/test.py", Path("/root")) == "src/test.py"


def test_relativize_source_value_outside_root(tmp_path):
    """Absolute path outside root returns original value (ValueError, lines 96-97)."""
    other = tmp_path / "other" / "file.py"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("x")
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    result = _relativize_source_value(str(other.resolve()), root)
    # ValueError from relative_to: returns original absolute path
    assert result == str(other.resolve())


# ---------------------------------------------------------------------------
# _load_source_value edge cases
# ---------------------------------------------------------------------------

def test_load_source_value_empty():
    """Empty string is returned as-is (line 109-110)."""
    assert _load_source_value("", Path("/root")) == ""


def test_load_source_value_already_relative():
    """Relative path is returned as-is (line 113-114)."""
    assert _load_source_value("src/test.py", Path("/root")) == "src/test.py"


def test_load_source_value_outside_root_no_current(tmp_path):
    """Absolute path outside root without current_path returns original (line 123)."""
    other = tmp_path / "other" / "file.py"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("x")
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    result = _load_source_value(str(other.resolve()), root, current_path=None)
    assert result == str(other.resolve())


def test_load_source_value_outside_root_with_current(tmp_path):
    """Absolute path outside root with current_path uses current as fallback (lines 118-122)."""
    other = tmp_path / "other" / "file.py"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("x")
    current = tmp_path / "root" / "sub" / "current.py"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text("y")
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    result = _load_source_value(str(other.resolve()), root, current_path=current)
    assert result == "sub/current.py"


def test_load_source_value_both_outside_root(tmp_path):
    """When both value and current_path are outside root, returns current_path absolute (lines 121-122)."""
    outside1 = tmp_path / "alt1" / "old.py"
    outside1.parent.mkdir(parents=True, exist_ok=True)
    outside1.write_text("old")
    outside2 = tmp_path / "alt2" / "new.py"
    outside2.parent.mkdir(parents=True, exist_ok=True)
    outside2.write_text("new")
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)

    result = _load_source_value(
        str(outside1.resolve()),
        root,
        current_path=outside2,
    )
    # Both outside root — should fall through to absolute current_path
    assert result == str(outside2.resolve())
