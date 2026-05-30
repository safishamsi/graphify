"""Tests for graphify/cache.py."""

import json

import pytest
from graphify.cache import (
    CACHE_SCHEMA_VERSION,
    _SCHEMA_VERSION_KEY,
    file_hash,
    load_cached,
    save_cached,
    cached_files,
    clear_cache,
    _body_content,
)


def _ast_entry_path(cache_root, src_file):
    """Path to the on-disk AST cache entry JSON for a source file."""
    h = file_hash(src_file, cache_root)
    return cache_root / "graphify-out" / "cache" / "ast" / f"{h}.json"


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


# --- Cache schema versioning (PR 7: profile/version invalidation) ---


def test_cache_schema_version_recorded(tmp_file, cache_root):
    """A cache write stamps the current CACHE_SCHEMA_VERSION into the stored JSON."""
    result = {"nodes": [{"id": "n1"}], "edges": []}
    save_cached(tmp_file, result, root=cache_root)

    entry = _ast_entry_path(cache_root, tmp_file)
    assert entry.exists()
    raw = json.loads(entry.read_text(encoding="utf-8"))
    assert raw[_SCHEMA_VERSION_KEY] == CACHE_SCHEMA_VERSION
    # The reserved version key must not leak into the payload callers consume.
    loaded = load_cached(tmp_file, root=cache_root)
    assert loaded is not None
    assert loaded == result
    assert _SCHEMA_VERSION_KEY not in loaded


def test_cache_invalidates_on_schema_version_change(tmp_file, cache_root):
    """An entry written under a mismatched/old version is a miss (rebuilt), not reused.

    Covers both the explicit-but-stale version and the legacy pre-versioning
    entry that has no version field at all — both must invalidate (return None)
    so the producer rebuilds rather than silently trusting stale cached output.
    """
    result = {"nodes": [{"id": "stale"}], "edges": []}
    save_cached(tmp_file, result, root=cache_root)
    entry = _ast_entry_path(cache_root, tmp_file)

    # 1. Stale explicit version (simulate a future producer bump).
    raw = json.loads(entry.read_text(encoding="utf-8"))
    raw[_SCHEMA_VERSION_KEY] = CACHE_SCHEMA_VERSION + 1
    entry.write_text(json.dumps(raw), encoding="utf-8")
    assert load_cached(tmp_file, root=cache_root) is None

    # 2. Legacy entry with no version field (backward compatibility).
    legacy = {"nodes": [{"id": "stale"}], "edges": []}
    entry.write_text(json.dumps(legacy), encoding="utf-8")
    assert load_cached(tmp_file, root=cache_root) is None


def test_cache_hit_when_version_matches(tmp_file, cache_root):
    """A matching schema version produces a cache hit (no needless invalidation)."""
    result = {"nodes": [{"id": "n1"}], "edges": [{"source": "a", "target": "b"}]}
    save_cached(tmp_file, result, root=cache_root)
    loaded = load_cached(tmp_file, root=cache_root)
    assert loaded == result  # protects hit rate when nothing changed


def test_cache_reused_across_graph_profiles(tmp_path, cache_root):
    """Raw extraction cache is profile-independent and reused across build profiles.

    Extraction produces nodes + edge records keyed only by file hash; the
    simple-graph vs MultiDiGraph distinction is a build-time assembly choice
    (build_from_json(multigraph=...)), not an extraction-time one. The same
    cached extraction must serve both a simple build and a multigraph build —
    proving we did NOT needlessly profile-key the raw cache.
    """
    src = tmp_path / "module.py"
    src.write_text("def f():\n    pass\n")

    extraction = {
        "nodes": [{"id": "module.f", "type": "function"}],
        "edges": [
            {"source": "module.f", "target": "module.g", "type": "calls"},
            {"source": "module.f", "target": "module.g", "type": "imports"},
        ],
    }
    save_cached(src, extraction, root=cache_root)

    # Simulate two separate build runs (simple, then multigraph). Neither passes
    # any profile to the cache layer; both must read back the identical entry.
    loaded_for_simple = load_cached(src, root=cache_root)
    loaded_for_multigraph = load_cached(src, root=cache_root)
    assert loaded_for_simple == extraction
    assert loaded_for_multigraph == extraction
    assert loaded_for_simple == loaded_for_multigraph

    # Only one cache entry exists — the cache was not split per profile.
    ast_dir = cache_root / "graphify-out" / "cache" / "ast"
    assert len(list(ast_dir.glob("*.json"))) == 1


def test_cache_existing_behavior_regression(tmp_file, cache_root):
    """Existing round-trip and hashing behavior is unchanged by versioning."""
    # Round-trip equality (the original test_cache_roundtrip contract).
    result = {"nodes": [{"id": "n1", "label": "Node1"}], "edges": []}
    save_cached(tmp_file, result, root=cache_root)
    assert load_cached(tmp_file, root=cache_root) == result

    # Content change still invalidates.
    tmp_file.write_text("completely different content")
    assert load_cached(tmp_file, root=cache_root) is None

    # Hashes remain stable across calls and unaffected by the version stamp.
    h1 = file_hash(tmp_file, cache_root)
    h2 = file_hash(tmp_file, cache_root)
    assert h1 == h2 and len(h1) == 64
