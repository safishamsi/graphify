"""Quantitative NetworkX vs rustworkx comparison helpers.

This benchmark is intentionally additive. It does not replace graphify's
NetworkX runtime; it measures whether a rustworkx adapter is promising for the
subset of operations graphify uses most often in build/query paths.
"""

from __future__ import annotations

import argparse
from importlib.metadata import version as package_version
import json
from pathlib import Path
from statistics import median
import sys
import time

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import networkx as nx

from graphify.build import build_from_json
from experiments.rustworkx_experiment import (
    build_rustworkx_from_extraction,
    rustworkx_bfs,
    rustworkx_graph_stats,
    rustworkx_shortest_path,
)


def make_synthetic_extraction(node_count: int = 1_000, *, directed: bool = False) -> dict:
    """Create a deterministic extraction payload for backend comparisons."""
    if node_count < 2:
        raise ValueError("node_count must be at least 2")

    nodes = [
        {
            "id": f"n{i}",
            "label": f"Node {i}",
            "file_type": "code",
            "source_file": "synthetic.py",
            "source_location": f"L{i + 1}",
        }
        for i in range(node_count)
    ]
    edges = []
    for i in range(node_count - 1):
        edges.append(
            {
                "source": f"n{i}",
                "target": f"n{i + 1}",
                "relation": "connects",
                "confidence": "EXTRACTED",
                "source_file": "synthetic.py",
                "weight": 1.0,
            }
        )
    stride = max(3, node_count // 20)
    for i in range(node_count - stride):
        edges.append(
            {
                "source": f"n{i}",
                "target": f"n{i + stride}",
                "relation": "skip",
                "confidence": "INFERRED",
                "source_file": "synthetic.py",
                "weight": 1.0,
            }
        )
        if directed:
            continue
        edges.append(
            {
                "source": f"n{i + stride}",
                "target": f"n{i}",
                "relation": "skip",
                "confidence": "INFERRED",
                "source_file": "synthetic.py",
                "weight": 1.0,
            }
        )
    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}


def _networkx_bfs(G: nx.Graph, start_id: str, depth: int) -> tuple[set[str], list[tuple[str, str]]]:
    visited: set[str] = {start_id}
    frontier: set[str] = {start_id}
    edges_seen: list[tuple[str, str]] = []
    for _ in range(depth):
        next_frontier: set[str] = set()
        for node_id in frontier:
            for neighbor_id in G.neighbors(node_id):
                edges_seen.append((node_id, neighbor_id))
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                next_frontier.add(neighbor_id)
        frontier = next_frontier
        if not frontier:
            break
    return visited, edges_seen


def _time_call(callback, repeats: int) -> tuple[float, object]:
    durations: list[float] = []
    last_result = None
    for _ in range(repeats):
        started = time.perf_counter()
        last_result = callback()
        durations.append((time.perf_counter() - started) * 1000)
    return round(median(durations), 3), last_result


def compare_networkx_rustworkx(
    *,
    node_count: int = 1_000,
    repeats: int = 5,
    directed: bool = False,
    depth: int = 3,
) -> dict:
    """Benchmark build, BFS, and shortest path for NetworkX vs rustworkx."""
    extraction = make_synthetic_extraction(node_count=node_count, directed=directed)
    start_id = "n0"
    target_id = f"n{node_count - 1}"

    networkx_build_ms, G = _time_call(lambda: build_from_json(extraction, directed=directed), repeats)
    rustworkx_build_ms, adapter = _time_call(
        lambda: build_rustworkx_from_extraction(extraction, directed=directed), repeats
    )

    networkx_bfs_ms, nx_bfs_result = _time_call(lambda: _networkx_bfs(G, start_id, depth), repeats)
    rustworkx_bfs_ms, rx_bfs_result = _time_call(lambda: rustworkx_bfs(adapter, [start_id], depth), repeats)

    networkx_path_ms, nx_path = _time_call(lambda: nx.shortest_path(G, start_id, target_id), repeats)
    rustworkx_path_ms, rx_path = _time_call(
        lambda: rustworkx_shortest_path(adapter, start_id, target_id),
        repeats,
    )

    nx_stats = {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "directed": G.is_directed(),
        "isolates": sum(1 for node_id in G.nodes if G.degree(node_id) == 0),
    }
    rx_stats = rustworkx_graph_stats(adapter)

    return {
        "node_count": node_count,
        "repeats": repeats,
        "depth": depth,
        "networkx": {
            "build_ms": networkx_build_ms,
            "bfs_ms": networkx_bfs_ms,
            "shortest_path_ms": networkx_path_ms,
            "stats": nx_stats,
            "bfs_visited": len(nx_bfs_result[0]),
            "shortest_path_length": len(nx_path),
        },
        "rustworkx": {
            "build_ms": rustworkx_build_ms,
            "bfs_ms": rustworkx_bfs_ms,
            "shortest_path_ms": rustworkx_path_ms,
            "stats": rx_stats,
            "bfs_visited": len(rx_bfs_result[0]),
            "shortest_path_length": len(rx_path),
        },
        "ratios": {
            "build": round(networkx_build_ms / rustworkx_build_ms, 3) if rustworkx_build_ms else 0.0,
            "bfs": round(networkx_bfs_ms / rustworkx_bfs_ms, 3) if rustworkx_bfs_ms else 0.0,
            "shortest_path": round(networkx_path_ms / rustworkx_path_ms, 3) if rustworkx_path_ms else 0.0,
        },
    }


def run_default_benchmarks(
    *,
    node_counts: list[int] | None = None,
    repeats: int = 5,
    depth: int = 3,
    directed: bool = False,
) -> dict:
    """Run a standard set of benchmarks and include library versions."""
    counts = node_counts or [1_000, 5_000]
    return {
        "environment": {
            "networkx": package_version("networkx"),
            "rustworkx": package_version("rustworkx"),
        },
        "runs": [
            compare_networkx_rustworkx(
                node_count=node_count,
                repeats=repeats,
                depth=depth,
                directed=directed,
            )
            for node_count in counts
        ],
    }


def save_benchmark_results(
    result: dict,
    *,
    output_path: str | Path | None = None,
) -> Path:
    """Write benchmark results to experiments/output by default."""
    path = Path(output_path) if output_path else Path(__file__).resolve().parent / "output" / "networkx_vs_rustworkx.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark graphify's NetworkX path against the additive rustworkx experiment.")
    parser.add_argument("--node-count", type=int, action="append", dest="node_counts", help="Node count to benchmark. Repeat for multiple sizes.")
    parser.add_argument("--repeats", type=int, default=5, help="How many repetitions per measurement.")
    parser.add_argument("--depth", type=int, default=3, help="Traversal depth for the BFS comparison.")
    parser.add_argument("--directed", action="store_true", help="Benchmark directed graphs instead of undirected ones.")
    parser.add_argument("--output", type=str, help="Optional output file path. Defaults to experiments/output/networkx_vs_rustworkx.json.")
    args = parser.parse_args(argv)

    result = run_default_benchmarks(
        node_counts=args.node_counts,
        repeats=args.repeats,
        depth=args.depth,
        directed=args.directed,
    )
    output_file = save_benchmark_results(result, output_path=args.output)
    print(json.dumps(result, indent=2))
    print(f"\nSaved benchmark results to {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
