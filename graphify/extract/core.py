import json
import os
import sys
from pathlib import Path
from typing import Any
from graphify.extractors import *
from graphify.extractors.core import _raise_recursion_limit, _JS_CACHE_BYPASS_SUFFIXES, _make_id, _WORKSPACE_PACKAGE_CACHE
from graphify.cache import load_cached

# ── Main extract and collect_files ────────────────────────────────────────────


def _check_tree_sitter_version() -> None:
    """Raise a clear error if tree-sitter is too old for the new Language API."""
    try:
        from tree_sitter import LANGUAGE_VERSION
    except ImportError:
        raise ImportError(
            "tree-sitter is not installed. Run: pip install 'tree-sitter>=0.23.0'"
        )
    # Language API v2 starts at LANGUAGE_VERSION 14
    if LANGUAGE_VERSION < 14:
        import tree_sitter as _ts
        raise RuntimeError(
            f"tree-sitter {getattr(_ts, '__version__', 'unknown')} is too old. "
            f"graphify requires tree-sitter >= 0.23.0 (Language API v2). "
            f"Run: pip install --upgrade tree-sitter"
        )



_DISPATCH: dict[str, Any] = {
    ".py": extract_python,
    ".js": extract_js,
    ".jsx": extract_js,
    ".mjs": extract_js,
    ".ts": extract_js,
    ".tsx": extract_js,
    ".go": extract_go,
    ".rs": extract_rust,
    ".java": extract_java,
    ".groovy": extract_groovy,
    ".gradle": extract_groovy,
    ".c": extract_c,
    ".h": extract_c,
    ".cpp": extract_cpp,
    ".cc": extract_cpp,
    ".cxx": extract_cpp,
    ".hpp": extract_cpp,
    ".rb": extract_ruby,
    ".cs": extract_csharp,
    ".kt": extract_kotlin,
    ".kts": extract_kotlin,
    ".scala": extract_scala,
    ".php": extract_php,
    ".swift": extract_swift,
    ".lua": extract_lua,
    ".luau": extract_lua,
    ".toc": extract_lua,
    ".zig": extract_zig,
    ".ps1": extract_powershell,
    ".ex": extract_elixir,
    ".exs": extract_elixir,
    ".m": extract_objc,
    ".mm": extract_objc,
    ".jl": extract_julia,
    ".f": extract_fortran,
    ".F": extract_fortran,
    ".f90": extract_fortran,
    ".F90": extract_fortran,
    ".f95": extract_fortran,
    ".F95": extract_fortran,
    ".f03": extract_fortran,
    ".F03": extract_fortran,
    ".f08": extract_fortran,
    ".F08": extract_fortran,
    ".vue": extract_js,
    ".svelte": extract_svelte,
    ".astro": extract_astro,
    ".dart": extract_dart,
    ".v": extract_verilog,
    ".sv": extract_verilog,
    ".sql": extract_sql,
    ".md": extract_markdown,
    ".mdx": extract_markdown,
    ".qmd": extract_markdown,
    ".pas": extract_pascal,
    ".pp": extract_pascal,
    ".dpr": extract_pascal,
    ".dpk": extract_pascal,
    ".lpr": extract_pascal,
    ".inc": extract_pascal,
    ".dfm": extract_delphi_form,
    ".lfm": extract_lazarus_form,
    ".lpk": extract_lazarus_package,
    ".sh": extract_bash,
    ".bash": extract_bash,
    ".json": extract_json,
}


def _get_extractor(path: Path) -> Any | None:
    """Return the correct extractor function for a file, or None if unsupported."""
    if path.name.endswith(".blade.php"):
        return extract_blade
    return _DISPATCH.get(path.suffix)




from .workers import _extract_parallel, _extract_sequential, _PARALLEL_THRESHOLD

def extract(
    paths: list[Path],
    cache_root: Path | None = None,
    *,
    parallel: bool = True,
    max_workers: int | None = None,
) -> dict:
    """Extract AST nodes and edges from a list of code files.

    Two-pass process:
    1. Per-file structural extraction (classes, functions, imports)
    2. Cross-file import resolution: turns file-level imports into
       class-level INFERRED edges (DigestAuth --uses--> Response)

    Args:
        paths: files to extract from
        cache_root: explicit root for graphify-out/cache/ (overrides the
            inferred common path prefix). Pass Path('.') when running on a
            subdirectory so the cache stays at ./graphify-out/cache/.
        parallel: if True and there are >= _PARALLEL_THRESHOLD uncached files,
            use ProcessPoolExecutor for multi-core extraction.
        max_workers: max subprocess count. Defaults to cpu_count (or the
            value of GRAPHIFY_MAX_WORKERS if set), bounded by len(uncached_work).
    """
    paths = [Path(p) for p in paths]
    _check_tree_sitter_version()
    _raise_recursion_limit()
    # Workspace package manifests/globs can change during watch or repeated extraction.
    _WORKSPACE_PACKAGE_CACHE.clear()

    # Infer a common root for cache keys (use first diverging segment, not sum of all matches)
    try:
        if not paths:
            root = Path(".")
        elif len(paths) == 1:
            root = paths[0].parent
        else:
            min_parts = min(len(p.parts) for p in paths)
            common_len = 0
            for i in range(min_parts):
                if len({p.parts[i] for p in paths}) == 1:
                    common_len += 1
                else:
                    break
            root = Path(*paths[0].parts[:common_len]) if common_len else Path(".")
    except Exception:
        root = Path(".")
    if cache_root is not None:
        root = cache_root
    root = root.resolve()

    effective_root = cache_root or root
    total = len(paths)

    # Phase 1: separate cached hits from uncached work
    per_file: list[dict | None] = [None] * total
    uncached_work: list[tuple[int, Path]] = []

    for i, path in enumerate(paths):
        if _get_extractor(path) is None:
            per_file[i] = {"nodes": [], "edges": []}
            continue
        bypass_cache = path.suffix in _JS_CACHE_BYPASS_SUFFIXES
        if not bypass_cache:
            cached = load_cached(path, effective_root)
            if cached is not None:
                per_file[i] = cached
                continue
        uncached_work.append((i, path))

    # Phase 2: extract uncached files (parallel or sequential)
    if uncached_work:
        ran_parallel = False
        if parallel and len(uncached_work) >= _PARALLEL_THRESHOLD:
            ran_parallel = _extract_parallel(
                uncached_work, per_file, effective_root, max_workers, total
            )
        if not ran_parallel:
            _extract_sequential(uncached_work, per_file, effective_root, total)

    # Fill any remaining None slots (shouldn't happen, but defensive)
    for i in range(total):
        if per_file[i] is None:
            per_file[i] = {"nodes": [], "edges": []}

    all_nodes: list[dict] = []
    all_edges: list[dict] = []
    all_raw_calls: list[dict] = []
    for result in per_file:
        all_nodes.extend(result.get("nodes", []))
        all_edges.extend(result.get("edges", []))
        all_raw_calls.extend(result.get("raw_calls", []))

    _augment_symbol_resolution_edges(paths, all_nodes, all_edges, root)

    # Remap file node IDs from absolute-path-derived to project-relative so
    # graph.json edge endpoints are stable across machines (#502)
    id_remap: dict[str, str] = {}
    for path in paths:
        old_id = _make_id(str(path))
        try:
            new_id = _make_id(str(path.relative_to(root)))
        except ValueError:
            continue
        if old_id != new_id:
            id_remap[old_id] = new_id
    if id_remap:
        for n in all_nodes:
            if n.get("id") in id_remap:
                n["id"] = id_remap[n["id"]]
        for e in all_edges:
            if e.get("source") in id_remap:
                e["source"] = id_remap[e["source"]]
            if e.get("target") in id_remap:
                e["target"] = id_remap[e["target"]]

    _merge_swift_extensions(per_file, all_nodes, all_edges)
    _disambiguate_colliding_node_ids(all_nodes, all_edges, all_raw_calls, root)
    _rewire_unique_stub_nodes(all_nodes, all_edges)

    # Add cross-file class-level edges (Python only - uses Python parser internally)
    py_paths = [p for p in paths if p.suffix == ".py"]
    if py_paths:
        py_results = [r for r, p in zip(per_file, paths) if p.suffix == ".py"]
        try:
            cross_file_edges = _resolve_cross_file_imports(py_results, py_paths)
            all_edges.extend(cross_file_edges)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Cross-file import resolution failed, skipping: %s", exc)

    # Cross-file Java import resolution
    java_paths = [p for p in paths if p.suffix == ".java"]
    if java_paths:
        java_results = [r for r, p in zip(per_file, paths) if p.suffix == ".java"]
        try:
            all_edges.extend(_resolve_cross_file_java_imports(java_results, java_paths))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Java cross-file import resolution failed, skipping: %s", exc)

    # Cross-file call resolution for all languages
    # Each extractor saved unresolved calls in raw_calls. Now that we have all
    # nodes from all files, resolve any callee that exists in another file.
    # Build name → ALL matching node IDs so we can skip ambiguous common names
    # (e.g. "log", "execute", "find") that appear in multiple files — resolving
    # those inflates god_nodes ranking with spurious cross-file edges.
    # Build label -> node_id index for cross-file call resolution.
    # Skip rationale nodes (their labels are docstring text, not callable
    # identifiers, and they were polluting matches for short names — #563).
    global_label_to_nids: dict[str, list[str]] = {}
    for n in all_nodes:
        if n.get("file_type") == "rationale":
            continue
        raw = n.get("label", "")
        normalised = raw.strip("()").lstrip(".")
        if normalised:
            key = normalised.lower()
            global_label_to_nids.setdefault(key, []).append(n["id"])

    # Build evidence index from import edges so cross-file calls backed by an
    # explicit import statement can be promoted from INFERRED to EXTRACTED.
    # Direct symbol imports (`import { foo }` / `const { foo } = require()`) are
    # the strongest evidence — caller's file_id has an `imports` edge directly to
    # the callee's symbol id. Module imports (`imports_from`) are weaker but still
    # confirm the caller pulled in the callee's source file.
    file_to_symbol_imports: dict[str, set[str]] = {}
    file_to_module_imports: dict[str, set[str]] = {}
    for e in all_edges:
        if e.get("relation") == "imports":
            file_to_symbol_imports.setdefault(e["source"], set()).add(e["target"])
        elif e.get("relation") == "imports_from":
            file_to_module_imports.setdefault(e["source"], set()).add(e["target"])

    # Map each node back to its containing file_id so we can ask
    # "did the caller's file import the callee's file?"
    # Use relativized paths to match how file node IDs were remapped above (#502).
    nid_to_file_nid: dict[str, str] = {}
    for n in all_nodes:
        sf = n.get("source_file")
        if not sf:
            continue
        sf_path = Path(sf)
        try:
            sf_rel = sf_path.relative_to(root) if sf_path.is_absolute() else sf_path
        except ValueError:
            sf_rel = sf_path
        nid_to_file_nid[n["id"]] = _make_id(str(sf_rel))

    existing_pairs = {(e["source"], e["target"]) for e in all_edges}
    for rc in all_raw_calls:
        callee = rc.get("callee", "")
        if not callee:
            continue
        # Skip member-call callees: obj.log() → "log" has no import evidence
        # and collides with any top-level function named "log" in the corpus.
        if rc.get("is_member_call"):
            continue
        candidates = global_label_to_nids.get(callee.lower(), [])
        # Skip ambiguous names that resolve to multiple nodes — these are
        # common short names (log, execute, find) with no import evidence
        # to pick the right target; emitting all edges inflates god_nodes.
        if len(candidates) != 1:
            continue
        tgt = candidates[0]
        caller = rc["caller_nid"]
        if tgt != caller and (caller, tgt) not in existing_pairs:
            existing_pairs.add((caller, tgt))
            # Promote to EXTRACTED when there's a direct import edge from the
            # caller's file pointing at either the callee symbol itself or the
            # file the callee lives in.
            caller_file_nid = nid_to_file_nid.get(caller)
            callee_file_nid = nid_to_file_nid.get(tgt)
            imported_symbols = file_to_symbol_imports.get(caller_file_nid, set())
            imported_modules = file_to_module_imports.get(caller_file_nid, set())
            has_import_evidence = (
                tgt in imported_symbols
                or (callee_file_nid is not None and callee_file_nid in imported_modules)
            )
            if has_import_evidence:
                confidence = "EXTRACTED"
                confidence_score = 1.0
            else:
                confidence = "INFERRED"
                confidence_score = 0.8
            all_edges.append({
                "source": caller,
                "target": tgt,
                "relation": "calls",
                "context": "call",
                "confidence": confidence,
                "confidence_score": confidence_score,
                "source_file": rc.get("source_file", ""),
                "source_location": rc.get("source_location"),
                "weight": 1.0,
            })

    # Relativize source_file fields so paths are portable across machines (#555)
    for item in all_nodes + all_edges:
        sf = item.get("source_file")
        if not sf:
            continue
        sf_path = Path(sf)
        if not sf_path.is_absolute():
            continue
        try:
            item["source_file"] = str(sf_path.relative_to(root))
        except ValueError:
            pass

    return {
        "nodes": all_nodes,
        "edges": all_edges,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def collect_files(target: Path, *, follow_symlinks: bool = False, root: Path | None = None) -> list[Path]:
    if target.is_file():
        return [target]
    _EXTENSIONS = set(_DISPATCH.keys())
    from graphify.detect.core import _load_graphifyignore, _is_ignored, _is_noise_dir
    ignore_root = root if root is not None else target
    patterns = _load_graphifyignore(ignore_root)

    def _ignored(p: Path) -> bool:
        return bool(patterns and _is_ignored(p, ignore_root, patterns))

    if not follow_symlinks:
        results: list[Path] = []
        for ext in sorted(_EXTENSIONS):
            results.extend(
                p for p in target.rglob(f"*{ext}")
                if not any(_is_noise_dir(part) for part in p.parts)
                and not _ignored(p)
            )
        return sorted(results)
    # Walk with symlink following + cycle detection
    results = []
    for dirpath, dirnames, filenames in os.walk(target, followlinks=True):
        if os.path.islink(dirpath):
            real = os.path.realpath(dirpath)
            parent_real = os.path.realpath(os.path.dirname(dirpath))
            if parent_real == real or parent_real.startswith(real + os.sep):
                dirnames.clear()
                continue
        dp = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not _is_noise_dir(d)]
        for fname in filenames:
            p = dp / fname
            if p.suffix in _EXTENSIONS and not _ignored(p):
                results.append(p)
    return sorted(results)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m graphify.extract <file_or_dir> ...", file=sys.stderr)
        sys.exit(1)

    paths: list[Path] = []
    for arg in sys.argv[1:]:
        paths.extend(collect_files(Path(arg)))

    result = extract(paths)
    print(json.dumps(result, indent=2))

