"""Tests for the Pascal/Delphi extractor."""
from __future__ import annotations
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _try_import():
    try:
        import tree_sitter_pascal  # noqa: F401
        return True
    except ImportError:
        return False


pascal_required = pytest.mark.skipif(
    not _try_import(),
    reason="tree_sitter_pascal not installed",
)


def _labels(r):
    return [n["label"] for n in r["nodes"]]


def _relations(r):
    return {e["relation"] for e in r["edges"]}


def _edges_with_relation(r, *relations):
    return [e for e in r["edges"] if e["relation"] in relations]


@pascal_required
def test_pascal_no_error():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    assert "error" not in r


@pascal_required
def test_pascal_finds_unit():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    assert any("SampleUnit" in l for l in _labels(r))


@pascal_required
def test_pascal_finds_classes():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    labels = _labels(r)
    assert any("TBaseProcessor" in l for l in labels)
    assert any("TDataProcessor" in l for l in labels)


@pascal_required
def test_pascal_finds_interface():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    assert any("IProcessor" in l for l in _labels(r))


@pascal_required
def test_pascal_finds_methods():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    labels = _labels(r)
    assert any("Process" in l for l in labels)
    assert any("Initialize" in l for l in labels)
    assert any("GetCount" in l for l in labels)
    assert any("Reset" in l for l in labels)


@pascal_required
def test_pascal_finds_imports():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    assert "imports" in _relations(r)


@pascal_required
def test_pascal_import_edges_have_import_context():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    import_edges = _edges_with_relation(r, "imports")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


@pascal_required
def test_pascal_finds_inherits():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    assert "inherits" in _relations(r)


@pascal_required
def test_pascal_inherits_from_base():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    inherits = [e for e in r["edges"] if e["relation"] == "inherits"]
    found = any(
        "TDataProcessor" in node_by_id.get(e["source"], "")
        for e in inherits
    )
    assert found, "TDataProcessor should have at least one inherits edge"


@pascal_required
def test_pascal_finds_calls():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    assert "calls" in _relations(r)


@pascal_required
def test_pascal_call_edges_have_call_context():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)


@pascal_required
def test_pascal_all_edges_extracted():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    structural = {"contains", "method", "inherits", "imports"}
    for e in r["edges"]:
        if e["relation"] in structural:
            assert e["confidence"] == "EXTRACTED", f"Expected EXTRACTED: {e}"


@pascal_required
def test_pascal_no_dangling_edges():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"


@pascal_required
def test_pascal_dispatch_registered():
    from graphify.extract import _DISPATCH
    assert ".pas" in _DISPATCH
    assert ".pp" in _DISPATCH
    assert ".dpr" in _DISPATCH
    assert ".dpk" in _DISPATCH
    assert ".inc" in _DISPATCH


@pascal_required
def test_pascal_detect_extensions_registered():
    from graphify.detect import CODE_EXTENSIONS
    assert ".pas" in CODE_EXTENSIONS
    assert ".pp" in CODE_EXTENSIONS
    assert ".dpr" in CODE_EXTENSIONS
