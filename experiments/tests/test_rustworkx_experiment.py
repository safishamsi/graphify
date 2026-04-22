import json
from pathlib import Path

import networkx as nx
import pytest
from networkx.readwrite import json_graph

pytest.importorskip("rustworkx")

from experiments.rustworkx_experiment import (
    build_rustworkx_from_extraction,
    build_rustworkx_from_graph_json,
    build_rustworkx_from_networkx,
    rustworkx_bfs,
    rustworkx_graph_stats,
    rustworkx_neighbors,
    rustworkx_shortest_path,
)

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def load_extraction():
    return json.loads((FIXTURES / "extraction.json").read_text())


def test_build_rustworkx_from_extraction_matches_counts():
    adapter = build_rustworkx_from_extraction(load_extraction())
    assert adapter.graph.num_nodes() == 4
    assert adapter.graph.num_edges() == 4


def test_build_rustworkx_preserves_original_node_payload():
    adapter = build_rustworkx_from_extraction(load_extraction())
    node = adapter.node_data("n_transformer")
    assert node["id"] == "n_transformer"
    assert node["label"] == "Transformer"


def test_build_rustworkx_from_networkx_preserves_ids():
    G = nx.Graph()
    G.add_node("a", label="A")
    G.add_node("b", label="B")
    G.add_edge("a", "b", relation="connects", confidence="EXTRACTED")

    adapter = build_rustworkx_from_networkx(G)

    assert adapter.id_to_index["a"] == 0
    assert adapter.node_data("b")["label"] == "B"


def test_build_rustworkx_from_graph_json_reads_links(tmp_path):
    G = nx.Graph()
    G.add_node("a", label="A", community=0)
    G.add_node("b", label="B", community=0)
    G.add_edge("a", "b", relation="connects", confidence="EXTRACTED")
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps(json_graph.node_link_data(G, edges="links")))

    adapter = build_rustworkx_from_graph_json(str(graph_file))

    assert adapter.graph.num_nodes() == 2
    assert adapter.graph.num_edges() == 1


def test_neighbors_return_original_string_ids():
    adapter = build_rustworkx_from_extraction(load_extraction())
    neighbors = rustworkx_neighbors(adapter, "n_transformer")
    assert set(neighbors) == {"n_attention", "n_layernorm"}


def test_bfs_returns_original_ids():
    adapter = build_rustworkx_from_extraction(load_extraction())
    visited, edges_seen = rustworkx_bfs(adapter, ["n_transformer"], depth=2)
    assert "n_concept_attn" in visited
    assert ("n_transformer", "n_attention") in edges_seen


def test_shortest_path_returns_original_ids():
    adapter = build_rustworkx_from_extraction(load_extraction())
    path = rustworkx_shortest_path(adapter, "n_transformer", "n_concept_attn")
    assert path[0] == "n_transformer"
    assert path[-1] == "n_concept_attn"


def test_graph_stats_include_metadata():
    adapter = build_rustworkx_from_extraction(load_extraction())
    stats = rustworkx_graph_stats(adapter)
    assert stats["nodes"] == 4
    assert stats["edges"] == 4
    assert stats["metadata"]["source"] == "extraction"
