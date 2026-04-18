from __future__ import annotations

from pathlib import Path

import networkx as nx

from depos.diagnostics import parse_sarif
from depos.fusion import attach_diagnostics
from depos.snapshot import build_graph_for_root


def test_sarif_attach(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text("def f():\n  return 1\n", encoding="utf-8")
    _, G = build_graph_for_root(tmp_path, directed=True)
    sarif = {
        "runs": [
            {
                "tool": {"driver": {"name": "test"}},
                "results": [
                    {
                        "ruleId": "r1",
                        "level": "error",
                        "message": {"text": "oops"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": str(src)},
                                    "region": {"startLine": 1},
                                }
                            }
                        ],
                    }
                ],
            }
        ]
    }
    attach_diagnostics(G, sarif, repo_root=tmp_path)
    assert any(G.nodes[n].get("erroneous") for n in G.nodes())


def test_parse_sarif_empty() -> None:
    assert parse_sarif({"runs": []}) == []
