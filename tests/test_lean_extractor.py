from pathlib import Path

import pytest

from graphify.extract import extract_lean


FIXTURE = Path(__file__).parent / "fixtures" / "sample.lean"


def test_extract_lean_returns_schema():
    result = extract_lean(str(FIXTURE))
    assert "nodes" in result
    assert "edges" in result
    assert isinstance(result["nodes"], list)
    assert isinstance(result["edges"], list)


def test_extract_lean_detects_theorem():
    result = extract_lean(str(FIXTURE))
    labels = [n["label"] for n in result["nodes"]]
    assert "safety_implies_budget" in labels


def test_extract_lean_detects_def():
    result = extract_lean(str(FIXTURE))
    labels = [n["label"] for n in result["nodes"]]
    assert "isSafe" in labels


def test_extract_lean_detects_structure():
    result = extract_lean(str(FIXTURE))
    structures = [n for n in result["nodes"] if n.get("node_type") == "Class"]
    labels = [n["label"] for n in structures]
    assert "PolicyState" in labels


def test_extract_lean_detects_namespace():
    result = extract_lean(str(FIXTURE))
    modules = [n for n in result["nodes"] if n.get("node_type") == "Module"]
    labels = [n["label"] for n in modules]
    assert "Fulcrum.Proofs" in labels or "Proofs" in labels


def test_extract_lean_detects_imports():
    result = extract_lean(str(FIXTURE))
    import_edges = [e for e in result["edges"] if e["relation"] == "imports"]
    assert len(import_edges) >= 2
    targets = [e["target"] for e in import_edges]
    assert any("Mathlib.Analysis.Basic" in t for t in targets)
