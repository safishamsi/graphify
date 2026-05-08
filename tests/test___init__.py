"""Tests for graphify.__init__ — lazy import mechanism via __getattr__."""
import sys

import pytest


@pytest.fixture(autouse=True)
def _reload_graphify():
    """Ensure a clean graphify module for each test (lazy attrs need fresh state)."""
    # Save all graphify modules before removing them
    saved = {k: v for k, v in sys.modules.items()
             if k == "graphify" or k.startswith("graphify.")}
    for k in list(saved.keys()):
        sys.modules.pop(k, None)
    yield
    # Restore after test so subsequent tests in the session aren't corrupted
    sys.modules.update(saved)


def test_getattr_extract():
    """__getattr__ lazily imports and returns graphify.extract.extract."""
    import graphify

    fn = graphify.extract
    assert fn is not None
    assert callable(fn)
    assert fn.__module__ == "graphify.extract" or "extract" in repr(fn)


def test_getattr_collect_files():
    """__getattr__ lazily imports collect_files."""
    import graphify

    fn = graphify.collect_files
    assert callable(fn)


def test_getattr_build_from_json():
    """__getattr__ lazily imports build_from_json."""
    import graphify

    fn = graphify.build_from_json
    assert callable(fn)


def test_getattr_cluster():
    """__getattr__ lazily imports cluster."""
    import graphify

    fn = graphify.cluster
    assert callable(fn)


def test_getattr_score_all():
    """__getattr__ lazily imports score_all."""
    import graphify

    fn = graphify.score_all
    assert callable(fn)


def test_getattr_cohesion_score():
    """__getattr__ lazily imports cohesion_score."""
    import graphify

    fn = graphify.cohesion_score
    assert callable(fn)


def test_getattr_god_nodes():
    """__getattr__ lazily imports god_nodes."""
    import graphify

    fn = graphify.god_nodes
    assert callable(fn)


def test_getattr_surprising_connections():
    """__getattr__ lazily imports surprising_connections."""
    import graphify

    fn = graphify.surprising_connections
    assert callable(fn)


def test_getattr_suggest_questions():
    """__getattr__ lazily imports suggest_questions."""
    import graphify

    fn = graphify.suggest_questions
    assert callable(fn)


def test_getattr_generate():
    """__getattr__ lazily imports generate."""
    import graphify

    fn = graphify.generate
    assert callable(fn)


def test_getattr_to_json():
    """__getattr__ lazily imports to_json."""
    import graphify

    fn = graphify.to_json
    assert callable(fn)


def test_getattr_to_html():
    """__getattr__ lazily imports to_html."""
    import graphify

    fn = graphify.to_html
    assert callable(fn)


def test_getattr_to_svg():
    """__getattr__ lazily imports to_svg."""
    import graphify

    fn = graphify.to_svg
    assert callable(fn)


def test_getattr_to_canvas():
    """__getattr__ lazily imports to_canvas."""
    import graphify

    fn = graphify.to_canvas
    assert callable(fn)


def test_getattr_to_wiki():
    """__getattr__ lazily imports to_wiki."""
    import graphify

    fn = graphify.to_wiki
    assert callable(fn)


def test_getattr_unknown_raises_attribute_error():
    """__getattr__ raises AttributeError for unrecognized names."""
    import graphify

    with pytest.raises(AttributeError, match="graphify"):
        _ = graphify.nonexistent_attr


def test_getattr_extract_returns_function():
    """__getattr__('extract') returns the extract function from graphify.extract."""
    import graphify

    fn = graphify.extract
    # On first access, __getattr__ returns the function itself.
    # (Python may later shortcut via sys.modules on re-access, which is fine.)
    assert callable(fn)
    assert not isinstance(fn, type(sys))  # not a module


def test_getattr_multiple_different_attrs():
    """Accessing multiple different attrs works without cross-contamination."""
    import graphify

    extract = graphify.extract
    html = graphify.to_html
    cluster = graphify.cluster

    assert extract is not None
    assert html is not None
    assert cluster is not None
    assert extract is not html
    assert html is not cluster


def test_getattr_known_name_not_in_map_but_exists():
    """Verify that map completeness — every entry actually exists."""
    import graphify

    # All 15 attributes should resolve
    expected = [
        "extract", "collect_files", "build_from_json", "cluster",
        "score_all", "cohesion_score", "god_nodes", "surprising_connections",
        "suggest_questions", "generate", "to_json", "to_html",
        "to_svg", "to_canvas", "to_wiki",
    ]
    for name in expected:
        val = getattr(graphify, name)
        assert val is not None, f"__getattr__ for {name!r} returned None"
