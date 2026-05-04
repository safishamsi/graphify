"""Tests for graphify/benchmark.py."""
from __future__ import annotations
import json
import pytest
import networkx as nx
from networkx.readwrite import json_graph

from graphify.benchmark import run_benchmark, print_benchmark, _query_subgraph_tokens, _SAMPLE_QUESTIONS


def _make_graph() -> nx.Graph:
    G = nx.DiGraph()
    G.add_node("n1", label="authentication", source_file="auth.py", source_location="L1", community=0)
    G.add_node("n2", label="api_handler", source_file="api.py", source_location="L5", community=0)
    G.add_node("n3", label="main_entry", source_file="main.py", source_location="L1", community=1)
    G.add_node("n4", label="error_handler", source_file="errors.py", source_location="L1", community=1)
    G.add_node("n5", label="database_layer", source_file="db.py", source_location="L1", community=2)
    G.add_edge("n1", "n2", relation="calls", confidence="INFERRED")
    G.add_edge("n2", "n3", relation="imports", confidence="EXTRACTED")
    G.add_edge("n3", "n4", relation="uses", confidence="EXTRACTED")
    G.add_edge("n5", "n2", relation="provides", confidence="EXTRACTED")
    return G


def _write_graph(G: nx.Graph, path) -> None:
    data = json_graph.node_link_data(G, edges="links")
    path.write_text(json.dumps(data))


# --- _query_subgraph_tokens ---

def test_query_returns_positive_for_matching_question():
    G = _make_graph()
    tokens = _query_subgraph_tokens(G, "how does authentication work")
    assert tokens > 0

def test_query_returns_zero_for_no_match():
    G = _make_graph()
    tokens = _query_subgraph_tokens(G, "xyzzy plugh zorkmid")
    assert tokens == 0

def test_query_bfs_expands_neighbors():
    G = _make_graph()
    # "authentication" matches n1, BFS depth=3 should reach n2, n3, n4
    tokens_deep = _query_subgraph_tokens(G, "authentication", depth=3)
    tokens_shallow = _query_subgraph_tokens(G, "authentication", depth=1)
    assert tokens_deep >= tokens_shallow


# --- run_benchmark ---

def test_run_benchmark_returns_reduction(tmp_path):
    G = _make_graph()
    graph_file = tmp_path / "graph.json"
    _write_graph(G, graph_file)
    result = run_benchmark(str(graph_file), corpus_words=10_000)
    assert "reduction_ratio" in result
    assert result["reduction_ratio"] > 1.0

def test_run_benchmark_corpus_tokens_proportional(tmp_path):
    G = _make_graph()
    graph_file = tmp_path / "graph.json"
    _write_graph(G, graph_file)
    r1 = run_benchmark(str(graph_file), corpus_words=1_000)
    r2 = run_benchmark(str(graph_file), corpus_words=10_000)
    # corpus_tokens scales linearly with corpus_words (within integer-division rounding)
    assert abs(r2["corpus_tokens"] - r1["corpus_tokens"] * 10) <= r1["corpus_tokens"]

def test_run_benchmark_per_question_list(tmp_path):
    G = _make_graph()
    graph_file = tmp_path / "graph.json"
    _write_graph(G, graph_file)
    result = run_benchmark(str(graph_file), corpus_words=5_000,
                           questions=["how does authentication work", "what is the main entry"])
    assert len(result["per_question"]) >= 1
    for p in result["per_question"]:
        assert "question" in p
        assert "query_tokens" in p
        assert "reduction" in p

def test_run_benchmark_estimates_corpus_if_no_words(tmp_path):
    G = _make_graph()
    graph_file = tmp_path / "graph.json"
    _write_graph(G, graph_file)
    result = run_benchmark(str(graph_file), corpus_words=None)
    assert result["corpus_words"] > 0

def test_run_benchmark_error_on_empty_graph(tmp_path):
    G = nx.DiGraph()
    graph_file = tmp_path / "empty.json"
    _write_graph(G, graph_file)
    result = run_benchmark(str(graph_file), corpus_words=1_000)
    assert "error" in result

def test_run_benchmark_includes_node_edge_counts(tmp_path):
    G = _make_graph()
    graph_file = tmp_path / "graph.json"
    _write_graph(G, graph_file)
    result = run_benchmark(str(graph_file), corpus_words=5_000)
    assert result["nodes"] == G.number_of_nodes()
    assert result["edges"] == G.number_of_edges()


# --- print_benchmark ---

def test_print_benchmark_no_crash(tmp_path, capsys):
    G = _make_graph()
    graph_file = tmp_path / "graph.json"
    _write_graph(G, graph_file)
    result = run_benchmark(str(graph_file), corpus_words=5_000)
    print_benchmark(result)
    out = capsys.readouterr().out
    assert "reduction" in out.lower()
    assert "x" in out

def test_print_benchmark_error_message(capsys):
    print_benchmark({"error": "test error message"})
    out = capsys.readouterr().out
    assert "test error message" in out
