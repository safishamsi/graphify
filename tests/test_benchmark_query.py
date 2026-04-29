import json
import tempfile
from pathlib import Path

import networkx as nx
import pytest
from graphify.benchmark import (
    _percentile,
    benchmark_memory,
    benchmark_pathfinding,
    benchmark_query_latency,
    benchmark_scale,
    diff_benchmarks,
    generate_bsbm_graph,
    run_full_benchmark,
)


def test_generate_bsbm_graph_creates_nodes():
    G = generate_bsbm_graph(num_nodes=1000)
    assert G.number_of_nodes() == 1000
    assert G.number_of_edges() > 0


def test_generate_bsbm_graph_has_communities():
    G = generate_bsbm_graph(num_nodes=1000)
    communities = set()
    for _, data in G.nodes(data=True):
        if data.get("community") is not None:
            communities.add(data["community"])
    assert len(communities) > 0


def test_generate_bsbm_graph_node_attributes():
    G = generate_bsbm_graph(num_nodes=200)
    node = G.nodes[0]
    assert "label" in node
    assert "source_file" in node
    assert "file_type" in node
    assert "community" in node
    assert "degree_centrality" in node


def test_generate_bsbm_graph_edge_attributes():
    G = generate_bsbm_graph(num_nodes=200)
    u, v = list(G.edges)[0]
    edge = G.edges[u, v]
    assert "relation" in edge
    assert "confidence" in edge
    assert "weight" in edge


def test_generate_bsbm_graph_reproducible():
    G1 = generate_bsbm_graph(num_nodes=200, seed=42)
    G2 = generate_bsbm_graph(num_nodes=200, seed=42)
    assert G1.number_of_nodes() == G2.number_of_nodes()
    assert G1.number_of_edges() == G2.number_of_edges()


def test_benchmark_query_latency_runs():
    G = generate_bsbm_graph(num_nodes=500)
    result = benchmark_query_latency(G, num_queries=10, depth=3)
    assert "avg" in result
    assert result["avg"] >= 0
    assert "p50" in result
    assert "p95" in result
    assert "p99" in result
    assert "qps" in result


def test_benchmark_query_latency_seed_reproducible():
    G = generate_bsbm_graph(num_nodes=500, seed=42)
    r1 = benchmark_query_latency(G, num_queries=10, seed=123)
    r2 = benchmark_query_latency(G, num_queries=10, seed=123)
    assert r1["avg"] == pytest.approx(r2["avg"], abs=0.1)


def test_benchmark_pathfinding_runs():
    G = generate_bsbm_graph(num_nodes=500)
    result = benchmark_pathfinding(G, num_pairs=5)
    assert "4hop_avg" in result
    assert "6hop_avg" in result
    assert "10hop_avg" in result


def test_benchmark_memory_runs():
    G = generate_bsbm_graph(num_nodes=500)
    result = benchmark_memory(G)
    assert result["graph"] > 0
    assert "bytes_per_node" in result
    assert "bytes_per_edge" in result


def test_generate_bsbm_graph_large():
    G = generate_bsbm_graph(num_nodes=5000)
    assert G.number_of_nodes() == 5000
    assert G.number_of_edges() > 0


def test_generate_bsbm_graph_small():
    G = generate_bsbm_graph(num_nodes=10)
    assert G.number_of_nodes() == 10
    assert G.number_of_edges() >= 0


def test_percentile_empty():
    assert _percentile([], 50) == 0.0


def test_percentile_single():
    assert _percentile([5.0], 50) == 5.0
    assert _percentile([5.0], 0) == 5.0
    assert _percentile([5.0], 100) == 5.0


def test_percentile_many():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _percentile(vals, 0) == 1.0
    assert _percentile(vals, 50) == 3.0
    assert _percentile(vals, 100) == 5.0


def test_percentile_interpolation():
    vals = [1.0, 2.0, 3.0, 4.0]
    p50 = _percentile(vals, 50)
    assert 2.0 <= p50 <= 3.0


def test_benchmark_query_latency_empty_graph():
    G = nx.Graph()
    result = benchmark_query_latency(G, num_queries=10)
    assert result["avg"] == 0
    assert result["qps"] == 0


def test_benchmark_pathfinding_too_few_nodes():
    G = nx.Graph()
    G.add_node(0)
    result = benchmark_pathfinding(G, num_pairs=5)
    assert result["4hop_avg"] == 0
    assert result["6hop_avg"] == 0
    assert result["10hop_avg"] == 0


def test_benchmark_pathfinding_disconnected():
    G = generate_bsbm_graph(num_nodes=100, seed=99)
    result = benchmark_pathfinding(G, num_pairs=50)
    assert result["4hop_avg"] >= 0
    assert result["6hop_avg"] >= 0
    assert result["10hop_avg"] >= 0


def test_benchmark_scale_defaults():
    results = benchmark_scale(num_nodes_list=[500], seed=42)
    assert len(results) == 1
    assert results[0]["nodes"] == 500
    assert "qps" in results[0]
    assert "p95_ms" in results[0]
    assert "bytes_per_node" in results[0]
    assert "bytes_per_edge" in results[0]


def test_benchmark_scale_multi():
    results = benchmark_scale(num_nodes_list=[200, 500], seed=42)
    assert len(results) == 2
    assert results[0]["nodes"] == 200
    assert results[1]["nodes"] == 500


def test_diff_benchmarks_basic():
    prev = {
        "phase": "1-baseline",
        "query_latency_ms": {"avg": 10, "p50": 8, "p95": 40, "p99": 80, "qps": 100},
        "memory_mb": {"graph": 50, "total": 60, "bytes_per_node": 900, "bytes_per_edge": 300},
        "scale": [
            {"nodes": 50000, "qps": 100, "p95_ms": 40},
        ],
    }
    curr = {
        "phase": "2-indexing",
        "query_latency_ms": {"avg": 5, "p50": 4, "p95": 10, "p99": 20, "qps": 200},
        "memory_mb": {"graph": 60, "total": 70, "bytes_per_node": 1000, "bytes_per_edge": 350},
        "scale": [
            {"nodes": 50000, "qps": 200, "p95_ms": 10},
        ],
    }
    result = diff_benchmarks(prev, curr)
    assert result["phase"] == "2-indexing"
    assert "qps_50k" in result["deltas"]
    assert "p95_ms_50k" in result["deltas"]
    assert "memory_mb" in result["deltas"]


def test_diff_benchmarks_zero_old():
    prev = {
        "query_latency_ms": {"qps": 0},
        "memory_mb": {"graph": 0},
    }
    curr = {
        "query_latency_ms": {"qps": 100},
        "memory_mb": {"graph": 0},
    }
    result = diff_benchmarks(prev, curr)
    assert result["deltas"]["qps_50k"] == "+∞%"
    assert result["deltas"]["memory_mb"] == "0%"


def test_diff_benchmarks_no_query():
    prev = {"scale": []}
    curr = {"scale": []}
    result = diff_benchmarks(prev, curr)
    assert result["deltas"] == {}


def test_diff_benchmarks_scale_different_nodes():
    prev = {
        "scale": [
            {"nodes": 50000, "qps": 80, "p95_ms": 45},
        ],
    }
    curr = {
        "scale": [
            {"nodes": 100000, "qps": 35, "p95_ms": 98},
        ],
    }
    result = diff_benchmarks(prev, curr)
    assert result["deltas"] == {}


def test_run_full_benchmark_small_graph(monkeypatch):
    def _fast_scale(num_nodes_list=None, seed=42):
        return [
            {"nodes": 500, "qps": 10, "p95_ms": 5, "bytes_per_node": 100, "bytes_per_edge": 50},
        ]

    monkeypatch.setattr("graphify.benchmark.benchmark_scale", _fast_scale)
    G = generate_bsbm_graph(num_nodes=200, seed=42)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "benchmark.json"
        result = run_full_benchmark(G, output_path=str(out), seed=42)
        assert result["phase"] == "1-baseline"
        assert "graph_stats" in result
        assert "query_latency_ms" in result
        assert "pathfinding_ms" in result
        assert "memory_mb" in result
        assert "scale" in result
        assert out.exists()


def test_run_full_benchmark_with_compare(monkeypatch):
    def _fast_scale(num_nodes_list=None, seed=42):
        return [
            {"nodes": 500, "qps": 10, "p95_ms": 5, "bytes_per_node": 100, "bytes_per_edge": 50},
        ]

    monkeypatch.setattr("graphify.benchmark.benchmark_scale", _fast_scale)
    G = generate_bsbm_graph(num_nodes=200, seed=42)
    with tempfile.TemporaryDirectory() as tmp:
        out1 = Path(tmp) / "benchmark1.json"
        out2 = Path(tmp) / "benchmark2.json"
        run_full_benchmark(G, output_path=str(out1), seed=42)
        run_full_benchmark(G, output_path=str(out2), seed=43, prev_benchmark_path=str(out1))
        prog = Path(tmp) / "progressive.json"
        assert prog.exists()
        data = json.loads(prog.read_text())
        assert len(data) >= 1
        assert "deltas" in data[0]


def test_run_full_benchmark_with_huge_scale(monkeypatch):
    def _fast_scale(num_nodes_list=None, seed=42):
        return [
            {"nodes": n, "qps": 10, "p95_ms": 5, "bytes_per_node": 100, "bytes_per_edge": 50}
            for n in (num_nodes_list or [50000, 5000000])
        ]

    monkeypatch.setattr("graphify.benchmark.benchmark_scale", _fast_scale)
    G = generate_bsbm_graph(num_nodes=100, seed=42)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "benchmark.json"
        result = run_full_benchmark(G, output_path=str(out), seed=42, scale="huge")
        tiers = [s["nodes"] for s in result["scale"]]
        assert 5000000 in tiers


def test_run_full_benchmark_without_huge(monkeypatch):
    def _fast_scale(num_nodes_list=None, seed=42):
        return [
            {"nodes": n, "qps": 10, "p95_ms": 5, "bytes_per_node": 100, "bytes_per_edge": 50}
            for n in (num_nodes_list or [50000])
        ]

    monkeypatch.setattr("graphify.benchmark.benchmark_scale", _fast_scale)
    G = generate_bsbm_graph(num_nodes=100, seed=42)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "benchmark.json"
        result = run_full_benchmark(G, output_path=str(out), seed=42)
        tiers = [s["nodes"] for s in result["scale"]]
        assert 5000000 not in tiers


def test_run_full_benchmark_missing_prev(monkeypatch):
    def _fast_scale(num_nodes_list=None, seed=42):
        return [
            {"nodes": 500, "qps": 10, "p95_ms": 5, "bytes_per_node": 100, "bytes_per_edge": 50},
        ]

    monkeypatch.setattr("graphify.benchmark.benchmark_scale", _fast_scale)
    G = generate_bsbm_graph(num_nodes=100, seed=42)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "benchmark.json"
        result = run_full_benchmark(G, output_path=str(out), seed=42, prev_benchmark_path="/nonexistent/path.json")
        assert result["phase"] == "1-baseline"


def test_benchmark_scale_default_uses_tiny(monkeypatch):
    def _tiny_bsbm(num_nodes=50000, seed=42):
        return generate_bsbm_graph(num_nodes=min(num_nodes, 200), seed=seed)

    monkeypatch.setattr("graphify.benchmark.generate_bsbm_graph", _tiny_bsbm)
    results = benchmark_scale()
    assert len(results) == 4
    assert results[0]["nodes"] == 50000


def test_run_full_benchmark_corrupt_progressive(monkeypatch):
    def _fast_scale(num_nodes_list=None, seed=42):
        return [
            {"nodes": 500, "qps": 10, "p95_ms": 5, "bytes_per_node": 100, "bytes_per_edge": 50},
        ]

    monkeypatch.setattr("graphify.benchmark.benchmark_scale", _fast_scale)
    G = generate_bsbm_graph(num_nodes=100, seed=42)
    with tempfile.TemporaryDirectory() as tmp:
        out1 = Path(tmp) / "benchmark1.json"
        out2 = Path(tmp) / "benchmark2.json"
        run_full_benchmark(G, output_path=str(out1), seed=42)
        prog = Path(tmp) / "progressive.json"
        prog.write_text("not json")
        run_full_benchmark(G, output_path=str(out2), seed=43, prev_benchmark_path=str(out1))
        data = json.loads(prog.read_text())
        assert len(data) >= 1


def test_run_full_benchmark_dict_progressive(monkeypatch):
    def _fast_scale(num_nodes_list=None, seed=42):
        return [
            {"nodes": 500, "qps": 10, "p95_ms": 5, "bytes_per_node": 100, "bytes_per_edge": 50},
        ]

    monkeypatch.setattr("graphify.benchmark.benchmark_scale", _fast_scale)
    G = generate_bsbm_graph(num_nodes=100, seed=42)
    with tempfile.TemporaryDirectory() as tmp:
        out1 = Path(tmp) / "benchmark1.json"
        out2 = Path(tmp) / "benchmark2.json"
        run_full_benchmark(G, output_path=str(out1), seed=42)
        prog = Path(tmp) / "progressive.json"
        prog.write_text('{"not": "a list"}')
        run_full_benchmark(G, output_path=str(out2), seed=43, prev_benchmark_path=str(out1))
        data = json.loads(prog.read_text())
        assert isinstance(data, list)
        assert len(data) >= 1
    G = nx.Graph()
    result = benchmark_memory(G)
    assert result["graph"] >= 0
    assert result["bytes_per_node"] >= 0


def test_diff_benchmarks_no_memory():
    prev = {
        "query_latency_ms": {"qps": 50, "p95": 100},
    }
    curr = {
        "query_latency_ms": {"qps": 75, "p95": 80},
    }
    result = diff_benchmarks(prev, curr)
    assert result["phase"] == "unknown"
    assert "qps_50k" in result["deltas"]
    assert "p95_ms_50k" in result["deltas"]
    assert "memory_mb" not in result["deltas"]


def test_benchmark_pathfinding_no_crash_on_no_path():
    G = nx.Graph()
    G.add_node(0)
    G.add_node(1)
    result = benchmark_pathfinding(G, num_pairs=20)
    assert result["4hop_avg"] == 0
    assert result["6hop_avg"] == 0
    assert result["10hop_avg"] == 0


def test_generate_bsbm_graph_tiny():
    G = generate_bsbm_graph(num_nodes=1)
    assert G.number_of_nodes() == 1
    assert G.number_of_edges() >= 0


def test_benchmark_phases_runs():
    from graphify.benchmark import benchmark_phases
    G = generate_bsbm_graph(num_nodes=200, seed=42)
    result = benchmark_phases(G, seed=42)
    assert "phases" in result
    assert "nodes" in result
    assert "edges" in result
    assert len(result["phases"]) >= 1


def test_benchmark_phases_empty():
    from graphify.benchmark import benchmark_phases
    G = nx.Graph()
    result = benchmark_phases(G, seed=42)
    assert "nodes" in result
    assert result["nodes"] == 0


def test_benchmark_approximate_accuracy_runs():
    from graphify.benchmark import benchmark_approximate_accuracy
    G = generate_bsbm_graph(num_nodes=200, seed=42)
    result = benchmark_approximate_accuracy(G, num_queries=10, seed=42)
    assert 0.05 in result
    assert 0.10 in result
    assert 0.25 in result
    assert 0.50 in result
    for sr in result:
        assert "precision" in result[sr]
        assert "recall" in result[sr]
        assert "f1" in result[sr]
        assert "speedup_mult" in result[sr]
        assert "p95_ms" in result[sr]


def test_benchmark_approximate_accuracy_small():
    from graphify.benchmark import benchmark_approximate_accuracy
    G = nx.Graph()
    G.add_node(0)
    result = benchmark_approximate_accuracy(G, num_queries=5, seed=42)
    assert result == {}


def test_generate_progressive_report_empty(tmp_path):
    from graphify.benchmark import generate_progressive_report
    prog_path = tmp_path / "nonexistent.json"
    out_path = tmp_path / "report.md"
    result = generate_progressive_report(str(prog_path), str(out_path))
    assert out_path.exists()
    content = out_path.read_text()
    assert "No progressive data" in content


def test_generate_progressive_report_with_data(tmp_path):
    from graphify.benchmark import generate_progressive_report
    import json
    prog_path = tmp_path / "progressive.json"
    out_path = tmp_path / "report.md"
    data = [
        {"phase": "1-baseline", "deltas": {"qps_50k": "+100%", "memory_mb": "+5%"}},
        {"phase": "2-indexing", "deltas": {"qps_50k": "+89%", "p95_ms_50k": "-50%"}},
    ]
    prog_path.write_text(json.dumps(data))
    result = generate_progressive_report(str(prog_path), str(out_path))
    content = out_path.read_text()
    assert "1-baseline" in content
    assert "2-indexing" in content
    assert "Top Gains" in content


def test_generate_progressive_report_corrupt(tmp_path):
    from graphify.benchmark import generate_progressive_report
    prog_path = tmp_path / "progressive.json"
    out_path = tmp_path / "report.md"
    prog_path.write_text("not valid json {{{")
    result = generate_progressive_report(str(prog_path), str(out_path))
    content = out_path.read_text()
    assert "No progressive" in content or "0 phases" in content


def test_generate_progressive_report_dict(tmp_path):
    from graphify.benchmark import generate_progressive_report
    import json
    prog_path = tmp_path / "progressive.json"
    out_path = tmp_path / "report.md"
    prog_path.write_text(json.dumps({"not": "a list"}))
    result = generate_progressive_report(str(prog_path), str(out_path))
    content = out_path.read_text()
    assert "0 phases" in content


def test_generate_progressive_report_no_qps_deltas(tmp_path):
    from graphify.benchmark import generate_progressive_report
    import json
    prog_path = tmp_path / "progressive.json"
    out_path = tmp_path / "report.md"
    data = [{"phase": "test", "deltas": {"memory_mb": "+5%"}}]
    prog_path.write_text(json.dumps(data))
    result = generate_progressive_report(str(prog_path), str(out_path))
    content = out_path.read_text()
    assert "No QPS deltas" in content


def test_benchmark_at_scale_runs():
    from graphify.benchmark import benchmark_at_scale
    G = generate_bsbm_graph(num_nodes=200, seed=42)
    result = benchmark_at_scale(G, scale="small")
    assert result["scale"] == "small"
    assert "qps" in result
    assert "p95_ms" in result
    assert "bytes_per_node" in result
    assert "bytes_per_edge" in result


def test_benchmark_at_scale_unknown():
    from graphify.benchmark import benchmark_at_scale
    G = generate_bsbm_graph(num_nodes=200, seed=42)
    result = benchmark_at_scale(G, scale="unknown")
    assert result["scale"] == "unknown"
    assert result["nodes"] == 50000
