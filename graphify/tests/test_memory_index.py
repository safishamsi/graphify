"""Tests for memory_index exporter."""

import json
from pathlib import Path

import pytest

from graphify.memory_index import write_memory_index


@pytest.fixture
def sample_graph_json(tmp_path: Path) -> Path:
    """Create a minimal graph.json fixture for testing."""
    data = {
        "nodes": [
            {"id": "A", "label": "ModuleA", "community": 0, "source_file": "src/a.py"},
            {"id": "B", "label": "ModuleB", "community": 0, "source_file": "src/b.py"},
            {"id": "C", "label": "ModuleC", "community": 1, "source_file": "src/c.py"},
            {"id": "D", "label": "ModuleD", "community": 1, "source_file": "src/d.py"},
        ],
        "links": [
            {"source": "A", "target": "B", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "B", "target": "C", "relation": "imports", "confidence": "EXTRACTED"},
            {"source": "C", "target": "D", "relation": "uses", "confidence": "INFERRED"},
            {"source": "D", "target": "A", "relation": "references", "confidence": "AMBIGUOUS"},
        ],
        "hyperedges": [],
    }
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps(data))
    return graph_file


def test_memory_index_creates_files(sample_graph_json: Path, tmp_path: Path):
    """Test that write_memory_index creates all three output files."""
    output_html = tmp_path / "output" / "memory_index.html"
    write_memory_index(graph=sample_graph_json, output=output_html)

    output_dir = output_html.parent
    assert (output_dir / "memory_index.json").exists()
    assert (output_dir / "MEMORY_REPORT.md").exists()
    assert output_html.exists()


def test_memory_index_json_schema(sample_graph_json: Path, tmp_path: Path):
    """Test that memory_index.json has correct schema."""
    output_html = tmp_path / "output" / "memory_index.html"
    write_memory_index(graph=sample_graph_json, output=output_html)

    json_file = output_html.parent / "memory_index.json"
    data = json.loads(json_file.read_text())

    assert "project" in data
    assert "generated_at" in data
    assert "key_modules" in data
    assert "clusters" in data
    assert "critical_edges" in data
    assert "next_steps" in data
    assert "token_estimate" in data
    assert isinstance(data["key_modules"], list)
    assert isinstance(data["clusters"], list)
    assert isinstance(data["critical_edges"], list)


def test_memory_index_key_modules(sample_graph_json: Path, tmp_path: Path):
    """Test that key modules are extracted correctly."""
    output_html = tmp_path / "output" / "memory_index.html"
    write_memory_index(graph=sample_graph_json, output=output_html)

    json_file = output_html.parent / "memory_index.json"
    data = json.loads(json_file.read_text())
    modules = data["key_modules"]

    # Should extract some modules
    assert len(modules) > 0

    # Each module should have required fields
    for mod in modules:
        assert "id" in mod
        assert "label" in mod
        assert "file" in mod
        assert "degree" in mod
        assert "community" in mod


def test_memory_index_critical_edges(sample_graph_json: Path, tmp_path: Path):
    """Test that only EXTRACTED edges are included in critical_edges."""
    output_html = tmp_path / "output" / "memory_index.html"
    write_memory_index(graph=sample_graph_json, output=output_html)

    json_file = output_html.parent / "memory_index.json"
    data = json.loads(json_file.read_text())
    edges = data["critical_edges"]

    # All critical edges should have EXTRACTED confidence
    for edge in edges:
        assert edge["confidence"] == "EXTRACTED"
        assert "source" in edge
        assert "target" in edge
        assert "relation" in edge


def test_memory_index_with_next_steps(sample_graph_json: Path, tmp_path: Path):
    """Test that next_steps are included in JSON and report."""
    steps = ["Cargar Enero 2026", "Exportar a PDF", "Alertas por email"]
    output_html = tmp_path / "output" / "memory_index.html"
    write_memory_index(
        graph=sample_graph_json,
        output=output_html,
        next_steps=steps,
    )

    # Check JSON
    json_file = output_html.parent / "memory_index.json"
    data = json.loads(json_file.read_text())
    assert data["next_steps"] == steps

    # Check report
    report_file = output_html.parent / "MEMORY_REPORT.md"
    report = report_file.read_text()
    for step in steps:
        assert step in report


def test_memory_index_with_project_name(sample_graph_json: Path, tmp_path: Path):
    """Test that project_name is included in output."""
    output_html = tmp_path / "output" / "memory_index.html"
    project = "MyProject"
    write_memory_index(
        graph=sample_graph_json,
        output=output_html,
        project_name=project,
    )

    json_file = output_html.parent / "memory_index.json"
    data = json.loads(json_file.read_text())
    assert data["project"] == project

    report_file = output_html.parent / "MEMORY_REPORT.md"
    report = report_file.read_text()
    assert project in report


def test_memory_report_sections(sample_graph_json: Path, tmp_path: Path):
    """Test that MEMORY_REPORT.md contains required sections."""
    output_html = tmp_path / "output" / "memory_index.html"
    write_memory_index(graph=sample_graph_json, output=output_html)

    report_file = output_html.parent / "MEMORY_REPORT.md"
    report = report_file.read_text()

    # Check required sections
    assert "# Memory Index" in report
    assert "## Quick Start" in report
    assert "## Key Modules" in report or "## Architecture Clusters" in report
    assert "## Query the Full Graph" in report


def test_memory_index_html_has_search(sample_graph_json: Path, tmp_path: Path):
    """Test that HTML includes search functionality."""
    output_html = tmp_path / "output" / "memory_index.html"
    write_memory_index(graph=sample_graph_json, output=output_html)

    html = output_html.read_text()

    # Check for search input
    assert 'id="searchInput"' in html
    assert "Search modules" in html

    # Check for table structure
    assert '<table' in html
    assert '<thead>' in html
    assert '<tbody' in html

    # Check for JavaScript functionality
    assert "function filterModules()" in html
    assert "function sortTable()" in html


def test_memory_index_missing_graph():
    """Test that missing graph file raises error."""
    with pytest.raises(FileNotFoundError):
        write_memory_index(graph="/nonexistent/path/graph.json")


def test_memory_index_no_graph_arg():
    """Test that missing --graph argument raises error."""
    with pytest.raises(ValueError, match="--graph is required"):
        write_memory_index(graph=None)


def test_memory_index_token_estimate(sample_graph_json: Path, tmp_path: Path):
    """Test that token_estimate is reasonable."""
    output_html = tmp_path / "output" / "memory_index.html"
    write_memory_index(graph=sample_graph_json, output=output_html)

    json_file = output_html.parent / "memory_index.json"
    data = json.loads(json_file.read_text())

    # Token estimate should be positive and relatively small
    assert data["token_estimate"] > 0
    assert data["token_estimate"] < 100000  # Sanity check
