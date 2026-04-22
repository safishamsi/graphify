import pytest

pytest.importorskip("rustworkx")

from experiments.rustworkx_benchmark import (
    compare_networkx_rustworkx,
    make_synthetic_extraction,
    run_default_benchmarks,
    save_benchmark_results,
)


def test_make_synthetic_extraction_has_expected_shape():
    extraction = make_synthetic_extraction(node_count=10)
    assert len(extraction["nodes"]) == 10
    assert len(extraction["edges"]) >= 9


def test_make_synthetic_extraction_rejects_too_small_graph():
    with pytest.raises(ValueError, match="at least 2"):
        make_synthetic_extraction(node_count=1)


def test_compare_networkx_rustworkx_returns_quantitative_metrics():
    result = compare_networkx_rustworkx(node_count=50, repeats=2, depth=2)
    assert result["networkx"]["build_ms"] >= 0
    assert result["rustworkx"]["build_ms"] >= 0
    assert result["networkx"]["bfs_ms"] >= 0
    assert result["rustworkx"]["bfs_ms"] >= 0
    assert result["networkx"]["shortest_path_ms"] >= 0
    assert result["rustworkx"]["shortest_path_ms"] >= 0
    assert result["networkx"]["stats"]["nodes"] == result["rustworkx"]["stats"]["nodes"]
    assert result["networkx"]["stats"]["edges"] == result["rustworkx"]["stats"]["edges"]
    assert result["networkx"]["bfs_visited"] == result["rustworkx"]["bfs_visited"]
    assert result["networkx"]["shortest_path_length"] == result["rustworkx"]["shortest_path_length"]


def test_compare_networkx_rustworkx_includes_ratios():
    result = compare_networkx_rustworkx(node_count=30, repeats=2, depth=1)
    assert set(result["ratios"]) == {"build", "bfs", "shortest_path"}


def test_run_default_benchmarks_reports_environment():
    result = run_default_benchmarks(node_counts=[30], repeats=2, depth=1)
    assert "networkx" in result["environment"]
    assert "rustworkx" in result["environment"]
    assert len(result["runs"]) == 1


def test_save_benchmark_results_writes_output(tmp_path):
    result = run_default_benchmarks(node_counts=[30], repeats=2, depth=1)
    output_path = tmp_path / "networkx_vs_rustworkx.json"
    saved = save_benchmark_results(result, output_path=output_path)
    assert saved == output_path
    assert output_path.exists()
