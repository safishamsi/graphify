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
    # imports edges are cross-file by design; only check within-file edge targets
    within_file_relations = {"contains", "method", "inherits", "calls"}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"
        if e["relation"] in within_file_relations:
            assert e["target"] in node_ids, f"Dangling target: {e}"


@pascal_required
def test_pascal_dispatch_registered():
    from graphify.extract import _DISPATCH
    assert ".pas" in _DISPATCH
    assert ".pp" in _DISPATCH
    assert ".dpr" in _DISPATCH
    assert ".dpk" in _DISPATCH
    assert ".lpr" in _DISPATCH
    assert ".inc" in _DISPATCH
    assert ".lfm" in _DISPATCH
    assert ".lpk" in _DISPATCH


@pascal_required
def test_pascal_detect_extensions_registered():
    from graphify.detect import CODE_EXTENSIONS
    assert ".pas" in CODE_EXTENSIONS
    assert ".pp" in CODE_EXTENSIONS
    assert ".dpr" in CODE_EXTENSIONS
    assert ".lpr" in CODE_EXTENSIONS
    assert ".lfm" in CODE_EXTENSIONS
    assert ".lpk" in CODE_EXTENSIONS


# ── Lazarus Form (.lfm) ───────────────────────────────────────────────────────

def test_lfm_no_error():
    from graphify.extract import extract_lazarus_form
    r = extract_lazarus_form(FIXTURES / "sample.lfm")
    assert "error" not in r


def test_lfm_finds_root_form_class():
    from graphify.extract import extract_lazarus_form
    r = extract_lazarus_form(FIXTURES / "sample.lfm")
    assert any("TSampleForm" in l for l in _labels(r))


def test_lfm_finds_component_classes():
    from graphify.extract import extract_lazarus_form
    r = extract_lazarus_form(FIXTURES / "sample.lfm")
    labels = _labels(r)
    assert any("TPanel" in l for l in labels)
    assert any("TButton" in l for l in labels)
    assert any("TLabel" in l for l in labels)
    assert any("TTimer" in l for l in labels)


def test_lfm_finds_event_handlers():
    from graphify.extract import extract_lazarus_form
    r = extract_lazarus_form(FIXTURES / "sample.lfm")
    labels = _labels(r)
    assert any("ButtonOKClick" in l for l in labels)
    assert any("TimerRefreshTimer" in l for l in labels)


def test_lfm_event_edges_have_event_context():
    from graphify.extract import extract_lazarus_form
    r = extract_lazarus_form(FIXTURES / "sample.lfm")
    ref_edges = [e for e in r["edges"] if e["relation"] == "references"]
    assert ref_edges
    assert all(e.get("context") == "event" for e in ref_edges)


def test_lfm_contains_edges_form_hierarchy():
    from graphify.extract import extract_lazarus_form
    r = extract_lazarus_form(FIXTURES / "sample.lfm")
    assert "contains" in _relations(r)


def test_lfm_no_dangling_edges():
    from graphify.extract import extract_lazarus_form
    r = extract_lazarus_form(FIXTURES / "sample.lfm")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"


# ── Lazarus Package (.lpk) ───────────────────────────────────────────────────

def test_lpk_no_error():
    from graphify.extract import extract_lazarus_package
    r = extract_lazarus_package(FIXTURES / "sample.lpk")
    assert "error" not in r


def test_lpk_finds_package_name():
    from graphify.extract import extract_lazarus_package
    r = extract_lazarus_package(FIXTURES / "sample.lpk")
    assert any("SamplePackage" in l for l in _labels(r))


def test_lpk_finds_required_packages():
    from graphify.extract import extract_lazarus_package
    r = extract_lazarus_package(FIXTURES / "sample.lpk")
    labels = _labels(r)
    assert any("FCL" in l for l in labels)
    assert any("LCL" in l for l in labels)


def test_lpk_imports_edges_have_import_context():
    from graphify.extract import extract_lazarus_package
    r = extract_lazarus_package(FIXTURES / "sample.lpk")
    import_edges = _edges_with_relation(r, "imports")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_lpk_contains_listed_units():
    from graphify.extract import extract_lazarus_package
    r = extract_lazarus_package(FIXTURES / "sample.lpk")
    labels = _labels(r)
    assert any("sample" in l.lower() for l in labels)
    assert any("sampleutils" in l.lower() for l in labels)


def test_lpk_no_dangling_edges():
    from graphify.extract import extract_lazarus_package
    r = extract_lazarus_package(FIXTURES / "sample.lpk")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"


# ── Delphi Form (.dfm) ───────────────────────────────────────────────────────

def test_dfm_no_error():
    from graphify.extract import extract_delphi_form
    r = extract_delphi_form(FIXTURES / "sample.dfm")
    assert "error" not in r


def test_dfm_finds_root_form_class():
    from graphify.extract import extract_delphi_form
    r = extract_delphi_form(FIXTURES / "sample.dfm")
    assert any("TMainForm" in l for l in _labels(r))


def test_dfm_finds_component_classes():
    from graphify.extract import extract_delphi_form
    r = extract_delphi_form(FIXTURES / "sample.dfm")
    labels = _labels(r)
    assert any("TPanel" in l for l in labels)
    assert any("TButton" in l for l in labels)
    assert any("TMemo" in l for l in labels)
    assert any("TStatusBar" in l for l in labels)


def test_dfm_finds_event_handlers():
    from graphify.extract import extract_delphi_form
    r = extract_delphi_form(FIXTURES / "sample.dfm")
    labels = _labels(r)
    assert any("FormCreate" in l for l in labels)
    assert any("ButtonOKClick" in l for l in labels)


def test_dfm_event_edges_have_event_context():
    from graphify.extract import extract_delphi_form
    r = extract_delphi_form(FIXTURES / "sample.dfm")
    ref_edges = [e for e in r["edges"] if e["relation"] == "references"]
    assert ref_edges
    assert all(e.get("context") == "event" for e in ref_edges)


def test_dfm_contains_edges_form_hierarchy():
    from graphify.extract import extract_delphi_form
    r = extract_delphi_form(FIXTURES / "sample.dfm")
    assert "contains" in _relations(r)


def test_dfm_no_dangling_edges():
    from graphify.extract import extract_delphi_form
    r = extract_delphi_form(FIXTURES / "sample.dfm")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"


def test_dfm_binary_returns_empty_not_crash():
    from graphify.extract import extract_delphi_form
    import tempfile, pathlib
    # Write a fake binary DFM (FF 0A magic header)
    with tempfile.NamedTemporaryFile(suffix=".dfm", delete=False) as f:
        f.write(b"\xff\x0a\x00\x00some binary data")
        tmp = pathlib.Path(f.name)
    try:
        r = extract_delphi_form(tmp)
        assert r["nodes"] == []
        assert r["edges"] == []
        assert "error" in r
    finally:
        tmp.unlink()


def test_dfm_dispatch_registered():
    from graphify.extract import _DISPATCH
    assert ".dfm" in _DISPATCH


def test_dfm_detect_extension_registered():
    from graphify.detect import CODE_EXTENSIONS
    assert ".dfm" in CODE_EXTENSIONS
