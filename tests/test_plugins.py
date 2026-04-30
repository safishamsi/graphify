"""Tests for graphify.plugins — plugin discovery and registration."""
from __future__ import annotations

from pathlib import Path

from graphify.plugins import (
    load_plugins,
    get_extractor,
    list_plugins,
    reset_registry,
    register_extractor,
)


def test_register_and_get_extractor():
    reset_registry()

    def fake_extract(path: Path) -> dict:
        return {"nodes": [{"id": "fake", "label": "Fake", "file_type": "code", "source_file": str(path)}], "edges": []}

    register_extractor(".fake", fake_extract)
    fn = get_extractor(".fake")
    assert fn is not None
    result = fn(Path("test.fake"))
    assert result["nodes"][0]["id"] == "fake"


def test_get_extractor_unknown():
    reset_registry()
    assert get_extractor(".nonexistent") is None


def test_load_plugins_from_directory(tmp_path, monkeypatch):
    reset_registry()
    monkeypatch.setenv("GRAPHIFY_ENABLE_PLUGINS", "1")
    plugin_dir = tmp_path / ".graphify" / "plugins"
    plugin_dir.mkdir(parents=True)

    plugin_file = plugin_dir / "test_plugin.py"
    plugin_file.write_text(
        '''
def register():
    return {".test": extract_test}

def extract_test(path):
    return {"nodes": [{"id": "test", "label": "Test", "file_type": "code", "source_file": str(path)}], "edges": []}
''',
        encoding="utf-8",
    )

    # Override default plugin dirs temporarily
    import graphify.plugins as plugins_mod
    original_dirs = plugins_mod._DEFAULT_PLUGIN_DIRS
    plugins_mod._DEFAULT_PLUGIN_DIRS = [plugin_dir]
    try:
        registry = load_plugins()
        assert ".test" in registry
        result = registry[".test"](Path("x.test"))
        assert result["nodes"][0]["id"] == "test"
    finally:
        plugins_mod._DEFAULT_PLUGIN_DIRS = original_dirs
        reset_registry()


def test_load_plugins_disabled_by_default(tmp_path, monkeypatch):
    # Without GRAPHIFY_ENABLE_PLUGINS set, a plugin file on disk must not
    # be auto-imported — auto-discovery would be a code-execution sink.
    reset_registry()
    monkeypatch.delenv("GRAPHIFY_ENABLE_PLUGINS", raising=False)
    plugin_dir = tmp_path / ".graphify" / "plugins"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "evil.py").write_text(
        "raise RuntimeError('plugin should not have been imported')",
        encoding="utf-8",
    )

    import graphify.plugins as plugins_mod
    original_dirs = plugins_mod._DEFAULT_PLUGIN_DIRS
    plugins_mod._DEFAULT_PLUGIN_DIRS = [plugin_dir]
    try:
        registry = load_plugins()
        assert registry == {}
    finally:
        plugins_mod._DEFAULT_PLUGIN_DIRS = original_dirs
        reset_registry()


def test_list_plugins(tmp_path):
    reset_registry()
    plugin_dir = tmp_path / "graphify-plugins"
    plugin_dir.mkdir()
    (plugin_dir / "foo.py").write_text("# plugin", encoding="utf-8")
    (plugin_dir / "_private.py").write_text("# private", encoding="utf-8")

    import graphify.plugins as plugins_mod
    original_dirs = plugins_mod._DEFAULT_PLUGIN_DIRS
    plugins_mod._DEFAULT_PLUGIN_DIRS = [plugin_dir]
    try:
        found = list_plugins()
        assert any("foo.py" in p for p in found)
        assert not any("_private.py" in p for p in found)
    finally:
        plugins_mod._DEFAULT_PLUGIN_DIRS = original_dirs
        reset_registry()


def test_plugin_bad_register_is_graceful(tmp_path, monkeypatch):
    reset_registry()
    monkeypatch.setenv("GRAPHIFY_ENABLE_PLUGINS", "1")
    plugin_dir = tmp_path / ".graphify" / "plugins"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "bad.py").write_text("# no register function", encoding="utf-8")

    import graphify.plugins as plugins_mod
    original_dirs = plugins_mod._DEFAULT_PLUGIN_DIRS
    plugins_mod._DEFAULT_PLUGIN_DIRS = [plugin_dir]
    try:
        registry = load_plugins()
        assert ".bad" not in registry  # gracefully skipped
    finally:
        plugins_mod._DEFAULT_PLUGIN_DIRS = original_dirs
        reset_registry()
