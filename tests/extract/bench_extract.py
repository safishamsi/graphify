#!/usr/bin/env python3
"""Benchmark: sequential vs parallel AST extraction.

Usage:
    python tests/bench_extract.py [path-to-repo]

Defaults to the current directory if no path is given.
Clears the AST cache between runs so every file is re-extracted.

Example output:
    === Graphify AST Extraction Benchmark ===
    Files:        1,247
    Languages:    Python (412), TypeScript (389), Go (201), ...

    Sequential:   4.32s (8,934 nodes, 12,456 edges)
    Parallel (8): 1.28s (8,934 nodes, 12,456 edges)

    Speedup:      3.38x
    Results:      ✓ identical
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

# Ensure the project root is importable
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from graphify.extract import extract, collect_files
from graphify.cache import clear_cache


def _count_by_ext(paths: list[Path]) -> dict[str, int]:
    """Count files by extension."""
    counter: Counter[str] = Counter()
    for p in paths:
        ext = p.suffix.lower()
        counter[ext] += 1
    return dict(counter.most_common())


_EXT_NAMES: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JSX",
    ".mjs": "MJS",
    ".ts": "TypeScript",
    ".tsx": "TSX",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".c": "C",
    ".h": "C Header",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++ Header",
    ".rb": "Ruby",
    ".cs": "C#",
    ".kt": "Kotlin",
    ".kts": "Kotlin Script",
    ".scala": "Scala",
    ".php": "PHP",
    ".swift": "Swift",
    ".lua": "Lua",
    ".toc": "Lua TOC",
    ".zig": "Zig",
    ".ps1": "PowerShell",
    ".ex": "Elixir",
    ".exs": "Elixir Script",
    ".m": "Obj-C",
    ".mm": "Obj-C++",
    ".jl": "Julia",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".dart": "Dart",
    ".v": "Verilog",
    ".sv": "SystemVerilog",
    ".sql": "SQL",
}


def _format_languages(ext_counts: dict[str, int]) -> str:
    parts = []
    for ext, count in ext_counts.items():
        name = _EXT_NAMES.get(ext, ext)
        parts.append(f"{name} ({count})")
    return ", ".join(parts)


def _run_extraction(
    paths: list[Path],
    cache_root: Path,
    parallel: bool,
    max_workers: int | None = None,
) -> tuple[float, int, int]:
    """Run extraction, return (elapsed_seconds, node_count, edge_count)."""
    clear_cache(cache_root)
    t0 = time.perf_counter()
    result = extract(
        paths, cache_root=cache_root, parallel=parallel, max_workers=max_workers
    )
    elapsed = time.perf_counter() - t0
    nodes = len(result.get("nodes", []))
    edges = len(result.get("edges", []))
    return elapsed, nodes, edges


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    target = target.resolve()

    if not target.exists():
        print(f"Error: {target} does not exist", file=sys.stderr)
        sys.exit(1)

    print("=== Graphify AST Extraction Benchmark ===\n")
    print(f"Scanning {target} ...", flush=True)

    paths = collect_files(target)
    if not paths:
        print("No extractable files found.", file=sys.stderr)
        sys.exit(1)

    ext_counts = _count_by_ext(paths)
    print(f"Files:        {len(paths):,}")
    print(f"Languages:    {_format_languages(ext_counts)}")
    print()

    cache_root = target if target.is_dir() else target.parent

    # Workers count (same logic as _extract_parallel)
    import os

    workers = min(os.cpu_count() or 4, len(paths), 8)

    # Run sequential
    print("Running sequential extraction...", flush=True)
    seq_time, seq_nodes, seq_edges = _run_extraction(paths, cache_root, parallel=False)
    print(f"Sequential:   {seq_time:.2f}s ({seq_nodes:,} nodes, {seq_edges:,} edges)")

    # Run parallel
    print(f"\nRunning parallel extraction ({workers} workers)...", flush=True)
    par_time, par_nodes, par_edges = _run_extraction(
        paths, cache_root, parallel=True, max_workers=workers
    )
    print(
        f"Parallel ({workers}): {par_time:.2f}s ({par_nodes:,} nodes, {par_edges:,} edges)"
    )

    # Results
    print()
    if seq_time > 0:
        speedup = seq_time / par_time if par_time > 0 else float("inf")
        print(f"Speedup:      {speedup:.2f}x")
    print(f"Workers:      {workers} (auto-detected)")

    # Validate correctness
    if seq_nodes == par_nodes and seq_edges == par_edges:
        print("Results:      ✓ identical (node count, edge count match)")
    else:
        print("Results:      ✗ MISMATCH!")
        print(f"  Sequential: {seq_nodes} nodes, {seq_edges} edges")
        print(f"  Parallel:   {par_nodes} nodes, {par_edges} edges")
        sys.exit(1)

    # Clean up cache after benchmark
    clear_cache(cache_root)
    print("\nCache cleared after benchmark.")


if __name__ == "__main__":
    main()
