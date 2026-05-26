"""Tests for .NET project file extraction (.sln, .csproj, .razor)."""
from pathlib import Path
import tempfile
import pytest
from graphify.extract import extract_sln, extract_csproj, extract_razor

FIXTURES = Path(__file__).parent / "fixtures"


def _labels(r):
    return [n["label"] for n in r["nodes"]]


def _relations(r):
    return {e["relation"] for e in r["edges"]}


# ── .sln ─────────────────────────────────────────────────────────────────────

def test_sln_extracts_projects():
    r = extract_sln(FIXTURES / "sample.sln")
    assert "error" not in r
    labels = set(_labels(r))
    assert "WebApi" in labels
    assert "Domain" in labels
    assert "Tests" in labels


def test_sln_contains_edges():
    r = extract_sln(FIXTURES / "sample.sln")
    contains = [e for e in r["edges"] if e["relation"] == "contains"]
    assert len(contains) == 3


def test_sln_project_dependency():
    r = extract_sln(FIXTURES / "sample.sln")
    assert "imports" in _relations(r)


# ── .csproj ──────────────────────────────────────────────────────────────────

def test_csproj_packages():
    r = extract_csproj(FIXTURES / "sample.csproj")
    assert "error" not in r
    labels = _labels(r)
    assert any("MediatR" in l for l in labels)
    assert any("FluentValidation" in l for l in labels)
    assert any("Swashbuckle" in l for l in labels)


def test_csproj_project_references():
    r = extract_csproj(FIXTURES / "sample.csproj")
    imports = [e for e in r["edges"] if e["relation"] == "imports"]
    assert len(imports) == 6  # 4 packages + 2 project refs


def test_csproj_target_framework():
    r = extract_csproj(FIXTURES / "sample.csproj")
    assert "net8.0" in _labels(r)


def test_csproj_sdk():
    r = extract_csproj(FIXTURES / "sample.csproj")
    assert "Microsoft.NET.Sdk.Web" in _labels(r)


def test_csproj_invalid_xml():
    with tempfile.NamedTemporaryFile(suffix=".csproj", mode="w", delete=False) as f:
        f.write("<Project><Invalid></Project>")
        f.flush()
        r = extract_csproj(Path(f.name))
    assert "error" in r


# ── .razor ───────────────────────────────────────────────────────────────────

def test_razor_using_and_inject():
    r = extract_razor(FIXTURES / "sample.razor")
    assert "error" not in r
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports"}
    assert any("microsoft" in t for t in targets)
    assert any("counterservice" in t.lower() for t in targets)


def test_razor_components():
    r = extract_razor(FIXTURES / "sample.razor")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "calls"}
    assert any("weatherdisplay" in t for t in targets)
    assert any("datagrid" in t for t in targets)


def test_razor_page_route():
    r = extract_razor(FIXTURES / "sample.razor")
    assert any("/counter" in l for l in _labels(r))


def test_razor_inherits():
    r = extract_razor(FIXTURES / "sample.razor")
    assert "inherits" in _relations(r)


def test_razor_code_methods():
    r = extract_razor(FIXTURES / "sample.razor")
    labels = _labels(r)
    assert "IncrementCount" in labels
    assert "LoadData" in labels


def test_razor_missing_file():
    r = extract_razor(Path("/nonexistent/file.razor"))
    assert "error" in r


# ── dispatch & detect integration ────────────────────────────────────────────

def test_dispatch_table():
    from graphify.extract import _get_extractor
    for ext in (".sln", ".csproj", ".fsproj", ".vbproj", ".razor", ".cshtml"):
        assert _get_extractor(Path(f"foo{ext}")) is not None, f"{ext} not in dispatch"


def test_code_extensions():
    from graphify.detect import CODE_EXTENSIONS
    for ext in (".sln", ".csproj", ".fsproj", ".vbproj", ".razor", ".cshtml"):
        assert ext in CODE_EXTENSIONS, f"{ext} missing"
