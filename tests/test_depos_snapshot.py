"""depOS snapshot uses graphify build_from_json only."""
from __future__ import annotations

from pathlib import Path

import networkx as nx

from depos.snapshot import build_graph_for_root, persist_graph_json, load_graph_json
from graphify.build import build_from_json


def test_build_graph_for_root_uses_graphify_pipeline(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text("def foo():\n    pass\n", encoding="utf-8")
    extraction, G = build_graph_for_root(tmp_path, directed=True)
    assert isinstance(G, nx.DiGraph)
    assert G.number_of_nodes() >= 1
    ext2, _ = build_graph_for_root(tmp_path, directed=True)
    assert ext2.get("nodes") == extraction.get("nodes") or len(ext2.get("nodes", [])) == len(
        extraction.get("nodes", [])
    )
    g2 = build_from_json(extraction, directed=True)
    assert g2.number_of_nodes() == G.number_of_nodes()


def test_roundtrip_json(tmp_path: Path) -> None:
    src = tmp_path / "a.py"
    src.write_text("x = 1\n", encoding="utf-8")
    _, G = build_graph_for_root(tmp_path, directed=True)
    p = tmp_path / "g.json"
    persist_graph_json(G, p)
    G2 = load_graph_json(p)
    assert G2.number_of_nodes() == G.number_of_nodes()
