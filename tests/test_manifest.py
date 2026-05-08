"""Tests for graphify.manifest — backwards-compatible re-export module."""
import pytest


def test_manifest_reexports_save_manifest():
    """save_manifest is importable from graphify.manifest."""
    from graphify.manifest import save_manifest
    from graphify.detect import save_manifest as _orig

    assert save_manifest is _orig


def test_manifest_reexports_load_manifest():
    """load_manifest is importable from graphify.manifest."""
    from graphify.manifest import load_manifest
    from graphify.detect import load_manifest as _orig

    assert load_manifest is _orig


def test_manifest_reexports_detect_incremental():
    """detect_incremental is importable from graphify.manifest."""
    from graphify.manifest import detect_incremental
    from graphify.detect import detect_incremental as _orig

    assert detect_incremental is _orig


def test_manifest_all_exports_complete():
    """__all__ matches the actual re-exported names."""
    import graphify.manifest as m

    for name in m.__all__:
        assert hasattr(m, name), f"__all__ includes {name!r} but it's not importable"


def test_manifest_import_fails_for_unknown_name():
    """Trying to import a non-existent name from manifest raises ImportError."""
    with pytest.raises(ImportError):
        from graphify.manifest import nonexistent_name  # noqa: F811


def test_manifest_reexports_are_callable():
    """The re-exported functions are actually callable (sanity check signatures)."""
    from graphify.manifest import save_manifest, load_manifest, detect_incremental

    assert callable(save_manifest)
    assert callable(load_manifest)
    assert callable(detect_incremental)
