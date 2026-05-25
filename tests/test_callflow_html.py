import json
import subprocess
import sys
from pathlib import Path

from graphify.callflow_html import derive_sections_from_communities, write_callflow_html


def _make_graphify_out(tmp_path: Path) -> Path:
    out = tmp_path / "graphify-out"
    out.mkdir()
    graph = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {"id": "api", "label": "ApiClient", "source_file": "src/api.py", "file_type": "code", "community": 0},
            {"id": "run", "label": "run()", "source_file": "src/main.py", "file_type": "code", "community": 0},
            {"id": "export", "label": "write_html()", "source_file": "src/export.py", "file_type": "code", "community": 1},
            {"id": "evil", "label": "<script>alert(1)</script>", "source_file": "src/evil.py", "file_type": "code", "community": 1},
        ],
        "links": [
            {"source": "run", "target": "api", "relation": "calls", "confidence": "EXTRACTED", "confidence_score": 1.0},
            {"source": "api", "target": "export", "relation": "uses", "confidence": "EXTRACTED", "confidence_score": 1.0},
            {"source": "export", "target": "evil", "relation": "calls", "confidence": "EXTRACTED", "confidence_score": 1.0},
        ],
        "hyperedges": [],
        "built_at_commit": "abcdef123456",
    }
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (out / ".graphify_labels.json").write_text(
        json.dumps({"0": "Runtime", "1": "Export"}),
        encoding="utf-8",
    )
    (out / "GRAPH_REPORT.md").write_text(
        "\n".join(
            [
                "# Graph Report - sample",
                "",
                "## Summary",
                "- 3 nodes · 2 edges · 1 communities detected",
                "",
                "## God Nodes (most connected - your core abstractions)",
                "1. `Transformer` - 2 edges",
            ]
        ),
        encoding="utf-8",
    )
    return out


def test_write_callflow_html_creates_file_and_uses_report(tmp_path):
    out = _make_graphify_out(tmp_path)

    html_path = write_callflow_html(
        tmp_path,
        output="graphify-out/callflow.html",
        max_sections=4,
    )

    assert html_path == out / "callflow.html"
    content = html_path.read_text(encoding="utf-8")
    assert "mermaid" in content
    assert "Graph Report Highlights" in content
    assert "Transformer" in content
    assert "ApiClient" in content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content
    assert "<script>alert(1)</script>" not in content


def test_export_callflow_html_cli_creates_file(tmp_path):
    _make_graphify_out(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "graphify",
            "export",
            "callflow-html",
            "--output",
            "graphify-out/from-cli.html",
            "--max-sections",
            "4",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    html_path = tmp_path / "graphify-out" / "from-cli.html"
    assert html_path.exists()
    assert "callflow HTML written" in result.stdout


def test_export_callflow_html_cli_accepts_positional_graph_path(tmp_path):
    _make_graphify_out(tmp_path)
    external_out = tmp_path / "GitNexus" / "graphify-out"
    external_out.mkdir(parents=True)
    graph = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {"id": "external", "label": "ExternalOnly", "source_file": "src/external.py", "file_type": "code", "community": 0},
            {"id": "writer", "label": "write_external()", "source_file": "src/writer.py", "file_type": "code", "community": 1},
        ],
        "links": [
            {"source": "external", "target": "writer", "relation": "calls", "confidence": "EXTRACTED", "confidence_score": 1.0},
        ],
        "hyperedges": [],
    }
    (external_out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (external_out / ".graphify_labels.json").write_text(json.dumps({"0": "External Runtime", "1": "External Export"}), encoding="utf-8")
    (external_out / "GRAPH_REPORT.md").write_text(
        "\n".join(
            [
                "# Graph Report - external",
                "",
                "## Summary",
                "- 2 nodes · 1 edges · 2 communities detected",
                "",
                "## God Nodes (most connected - your core abstractions)",
                "1. `ExternalGod` - 1 edges",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "graphify",
            "export",
            "callflow-html",
            str(external_out / "graph.json"),
            "--output",
            "positional.html",
            "--max-sections",
            "4",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    html = (tmp_path / "positional.html").read_text(encoding="utf-8")
    assert "ExternalOnly" in html
    assert "ExternalGod" in html
    assert "ApiClient" not in html
    assert "Transformer" not in html


def test_derive_sections_groups_by_architecture_keywords():
    nodes = [
        {"id": "extract_py", "label": "extract_python", "source_file": "graphify/extract.py", "community": 0},
        {"id": "extract_js", "label": "extract_js", "source_file": "graphify/extract.py", "community": 0},
        {"id": "to_html", "label": "to_html", "source_file": "graphify/export.py", "community": 1},
        {"id": "test_html", "label": "test_export_html", "source_file": "tests/test_export.py", "community": 2},
    ]

    sections = derive_sections_from_communities(nodes, {}, "en", 6)
    ids = {section["id"] for section in sections}

    assert "extract-pipeline" in ids
    assert "outputs-docs" in ids
    assert "tests-fixtures" in ids


def test_load_graph_rejects_oversized_file(monkeypatch, tmp_path):
    """#F4: callflow_html.load_graph must refuse to read a graph.json that
    exceeds the size cap (SystemExit via translated ValueError)."""
    import pytest
    from graphify.callflow_html import load_graph

    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps({"nodes": [], "links": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 8)
    with pytest.raises(SystemExit) as excinfo:
        load_graph(graph_path)
    assert "exceeds" in str(excinfo.value)
