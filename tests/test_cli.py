"""Focused CLI tests for graph export commands."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

from graphify.__main__ import main
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import to_json


FIXTURES = Path(__file__).parent / "fixtures"


def _write_graph_json(tmp_path: Path) -> Path:
    extraction = json.loads((FIXTURES / "extraction.json").read_text())
    G = build_from_json(extraction)
    communities = cluster(G)
    graph_path = tmp_path / "graph.json"
    to_json(G, communities, str(graph_path))
    return graph_path


def test_mermaid_command_writes_output(tmp_path, capsys):
    graph_path = _write_graph_json(tmp_path)
    out_path = tmp_path / "graph.mmd"

    with patch.object(sys, "argv", [
        "graphify",
        "mermaid",
        "--graph",
        str(graph_path),
        "--out",
        str(out_path),
    ]):
        main()

    assert out_path.exists()
    content = out_path.read_text()
    assert "flowchart LR" in content
    assert "-->|" in content
    stdout = capsys.readouterr().out
    assert "Mermaid graph written to" in stdout
