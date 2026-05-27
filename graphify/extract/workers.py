import os
import sys
from pathlib import Path

from graphify.extractors.core import _raise_recursion_limit, _safe_extract, _JS_CACHE_BYPASS_SUFFIXES
from graphify.cache import load_cached, save_cached

# ── Main extract and collect_files ────────────────────────────────────────────

from .core import _get_extractor

def _extract_single_file(args: tuple) -> tuple[int, dict]:
    """Worker function for parallel extraction. Runs in a subprocess.

    Must be at module level (not a closure) so it can be pickled by
    ProcessPoolExecutor.

    Args:
        args: (index, path_str, cache_root_str) tuple

    Returns:
        (index, result_dict) so results can be placed back in order.
    """
    idx, path_str, cache_root_str = args
    path = Path(path_str)
    cache_root = Path(cache_root_str)
    _raise_recursion_limit()
    bypass_cache = path.suffix in _JS_CACHE_BYPASS_SUFFIXES

    # Check cache first (avoid re-extraction)
    if not bypass_cache:
        cached = load_cached(path, cache_root)
        if cached is not None:
            return idx, cached

    extractor = _get_extractor(path)
    if extractor is None:
        return idx, {"nodes": [], "edges": []}

    result = _safe_extract(extractor, path)
    if not bypass_cache and "error" not in result:
        save_cached(path, result, cache_root)
    return idx, result


def _extract_parallel(
    uncached_work: list[tuple[int, Path]],
    per_file: list[dict | None],
    effective_root: Path,
    max_workers: int | None,
    total_files: int,
) -> bool:
    """Extract uncached files in parallel using ProcessPoolExecutor.

    Returns True if the pool ran to completion. Returns False if the pool
    failed in a recoverable way (typically Windows-spawn without an
    ``if __name__ == "__main__"`` guard in the calling script, which causes
    BrokenProcessPool); the caller should fall back to sequential extraction.
    """
    import concurrent.futures

    if max_workers is None:
        # Honour GRAPHIFY_MAX_WORKERS env override; otherwise scale to the
        # full CPU. The historical `, 8)` cap was a safety bound for laptops
        # in 2023 — on a 32-thread workstation it costs a 4x slowdown
        # (issue #792). Capping at len(uncached_work) keeps small jobs
        # from spawning useless idle workers.
        env_raw = os.environ.get("GRAPHIFY_MAX_WORKERS", "").strip()
        env_cap = None
        if env_raw:
            try:
                v = int(env_raw)
                if v > 0:
                    env_cap = v
            except ValueError:
                pass
        cpu_cap = env_cap if env_cap is not None else (os.cpu_count() or 4)
        max_workers = min(cpu_cap, len(uncached_work))

    root_str = str(effective_root)
    work_items = [(idx, str(path), root_str) for idx, path in uncached_work]

    done_count = 0
    _PROGRESS_INTERVAL = 100
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_extract_single_file, item): item[0] for item in work_items
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    idx, result = future.result()
                    per_file[idx] = result
                except Exception as exc:
                    idx = futures[future]
                    print(
                        f"  warning: worker failed for {work_items[idx][1]}: {exc}",
                        file=sys.stderr, flush=True,
                    )
                done_count += 1
                if (
                    total_files >= _PROGRESS_INTERVAL
                    and done_count % _PROGRESS_INTERVAL == 0
                ):
                    print(
                        f"  AST extraction: {done_count}/{len(uncached_work)} uncached files "
                        f"({done_count * 100 // len(uncached_work)}%) [{max_workers} workers]",
                        flush=True,
                    )
    except concurrent.futures.process.BrokenProcessPool:
        # On Windows (spawn start method) the worker subprocesses re-import the
        # caller's __main__. Inline invocations like `python -c "..."` have no
        # __main__ guard, so worker bootstrap raises and the pool dies before
        # any work completes. Fall back to in-process sequential extraction —
        # slower but correct.
        print(
            "  warning: parallel extraction failed (BrokenProcessPool); "
            "falling back to sequential. On Windows this usually means the "
            'caller is missing an `if __name__ == "__main__":` guard. Pass '
            "parallel=False to extract() to skip the pool entirely.",
            flush=True,
        )
        return False
    if total_files >= _PROGRESS_INTERVAL:
        print(
            f"  AST extraction: {total_files}/{total_files} files (100%) [{max_workers} workers]",
            flush=True,
        )
    return True


def _extract_sequential(
    uncached_work: list[tuple[int, Path]],
    per_file: list[dict | None],
    effective_root: Path,
    total_files: int,
) -> None:
    """Extract uncached files sequentially (fallback for small batches)."""
    _PROGRESS_INTERVAL = 100
    for work_idx, (idx, path) in enumerate(uncached_work):
        if (
            total_files >= _PROGRESS_INTERVAL
            and work_idx % _PROGRESS_INTERVAL == 0
            and work_idx > 0
        ):
            print(
                f"  AST extraction: {work_idx}/{len(uncached_work)} uncached files ({work_idx * 100 // len(uncached_work)}%)",
                flush=True,
            )
        extractor = _get_extractor(path)
        if extractor is None:
            per_file[idx] = {"nodes": [], "edges": []}
            continue
        bypass_cache = path.suffix in _JS_CACHE_BYPASS_SUFFIXES
        result = _safe_extract(extractor, path)
        if not bypass_cache and "error" not in result:
            save_cached(path, result, effective_root)
        per_file[idx] = result
    if total_files >= _PROGRESS_INTERVAL:
        print(f"  AST extraction: {total_files}/{total_files} files (100%)", flush=True)


_PARALLEL_THRESHOLD = 20


