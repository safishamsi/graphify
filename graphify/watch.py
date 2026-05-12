# monitor a folder and auto-trigger --update when files change
from __future__ import annotations
import contextlib
import json
import os
import sys
import time
from pathlib import Path

_GRAPHIFY_OUT = os.environ.get("GRAPHIFY_OUT", "graphify-out")


@contextlib.contextmanager
def _rebuild_lock(out_dir: Path, *, blocking: bool = False):
    """Per-repo advisory lock around a rebuild.

    Yields True if acquired, False if another rebuild is already running and
    ``blocking`` is False. Uses fcntl.flock so the lock is released
    automatically if the process is killed (no stale-lock cleanup needed).

    Falls back to a no-op yield(True) on platforms without fcntl (Windows).
    """
    try:
        import fcntl
    except ImportError:
        yield True
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    lock_path = out_dir / ".rebuild.lock"
    fh = open(lock_path, "a", encoding="utf-8")
    try:
        flags = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            fcntl.flock(fh.fileno(), flags)
        except BlockingIOError:
            yield False
            return
        try:
            fh.write(str(os.getpid()))
            fh.flush()
        except OSError:
            pass
        yield True
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        fh.close()


def _apply_resource_limits() -> None:
    """Best-effort nice + memory cap. Called from inline hook scripts.

    GRAPHIFY_REBUILD_MEMORY_LIMIT_MB caps RSS-ish memory. Uses RLIMIT_DATA on
    macOS (RLIMIT_AS is unreliable under Apple's libmalloc) and RLIMIT_AS on
    Linux. Silently skips if the platform doesn't support it.
    """
    try:
        os.nice(10)
    except (OSError, AttributeError):
        pass
    mb = os.environ.get("GRAPHIFY_REBUILD_MEMORY_LIMIT_MB", "").strip()
    if not mb:
        return
    try:
        limit = int(mb) * 1024 * 1024
    except ValueError:
        return
    try:
        import resource
        which = resource.RLIMIT_DATA if sys.platform == "darwin" else resource.RLIMIT_AS
        soft, hard = resource.getrlimit(which)
        new_hard = hard if hard != resource.RLIM_INFINITY and hard < limit else limit
        resource.setrlimit(which, (limit, new_hard))
    except (ImportError, ValueError, OSError):
        pass


def _git_head() -> str | None:
    """Return current git HEAD commit hash, or None outside a repo."""
    import subprocess as _sp
    try:
        r = _sp.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


from graphify.detect import CODE_EXTENSIONS, DOC_EXTENSIONS, PAPER_EXTENSIONS, IMAGE_EXTENSIONS

_WATCHED_EXTENSIONS = CODE_EXTENSIONS | DOC_EXTENSIONS | PAPER_EXTENSIONS | IMAGE_EXTENSIONS
_CODE_EXTENSIONS = CODE_EXTENSIONS


def _report_root_label(watch_path: Path) -> str:
    if watch_path.is_absolute():
        return watch_path.name or str(watch_path)
    return Path.cwd().name if watch_path == Path(".") else str(watch_path)


def _relativize_source_files(payload: dict, root: Path) -> None:
    for bucket in ("nodes", "edges", "hyperedges"):
        for item in payload.get(bucket, []):
            source = item.get("source_file")
            if not source:
                continue
            source_path = Path(source)
            if not source_path.is_absolute():
                continue
            try:
                item["source_file"] = str(source_path.resolve().relative_to(root))
            except ValueError:
                continue


def _rebuild_code(
    watch_path: Path,
    *,
    changed_paths: list[Path] | None = None,
    follow_symlinks: bool = False,
    force: bool = False,
    acquire_lock: bool = True,
    block_on_lock: bool = False,
) -> bool:
    """Re-run AST extraction + build + cluster + report for code files. No LLM needed.

    When ``force`` is True the node-count safety check in ``to_json`` is bypassed
    so the rebuilt graph overwrites graph.json even if it has fewer nodes.
    Use this after refactors that legitimately delete code.

    When ``changed_paths`` is provided, only those files are re-extracted; nodes
    for unchanged files are preserved from the existing graph. Deleted paths
    in ``changed_paths`` (paths that no longer exist on disk) are dropped from
    the preserved set. When ``changed_paths`` is None the full code corpus is
    re-extracted (used by the watcher and post-checkout hook).

    ``acquire_lock`` (default True) takes a non-blocking per-repo flock around
    the rebuild so concurrent post-commit hooks across multiple repos do not
    pile up. Returns False with a log line if the lock is held. Pass
    ``block_on_lock=True`` to wait instead of skip (used by the interactive
    ``graphify update`` CLI).

    Returns True on success, False on error or skipped-due-to-lock.
    """
    out = watch_path / _GRAPHIFY_OUT
    if acquire_lock:
        with _rebuild_lock(out, blocking=block_on_lock) as got:
            if not got:
                print("[graphify watch] Rebuild already in progress for "
                      f"{watch_path.resolve()} - skipping.")
                return False
            return _rebuild_code(
                watch_path,
                changed_paths=changed_paths,
                follow_symlinks=follow_symlinks,
                force=force,
                acquire_lock=False,
            )

    watch_root = watch_path.resolve()
    project_root = Path.cwd().resolve() if not watch_path.is_absolute() else watch_root
    report_root = _report_root_label(watch_path)
    try:
        from graphify.extract import extract, _get_extractor
        from graphify.detect import detect
        from graphify.build import build_from_json
        from graphify.cluster import cluster, score_all
        from graphify.analyze import god_nodes, surprising_connections, suggest_questions
        from graphify.report import generate
        from graphify.export import to_json, to_html

        detected = detect(watch_path, follow_symlinks=follow_symlinks)
        code_files = [Path(f) for f in detected['files']['code']]

        # Include document files that have AST extractors (e.g. .md, .mdx, .qmd)
        for doc_file in detected['files'].get('document', []):
            p = Path(doc_file)
            if _get_extractor(p) is not None:
                code_files.append(p)

        if not code_files:
            print("[graphify watch] No code files found - nothing to rebuild.")
            return False

        # Incremental path: when the caller passed an explicit change list,
        # extract only changed-and-still-existing files. Deleted paths are
        # tracked separately so their stale nodes can be evicted below.
        deleted_paths: set[str] = set()
        if changed_paths is not None:
            code_set = {p.resolve() for p in code_files}
            wanted: list[Path] = []
            for raw in changed_paths:
                cand = (watch_root / raw).resolve() if not raw.is_absolute() else raw.resolve()
                if cand.exists() and cand in code_set:
                    wanted.append(cand)
                else:
                    # File was deleted, renamed away, or filtered out by detect
                    # (e.g. .gitignore, vendored). Either way, evict any
                    # preserved nodes that still claim this source path.
                    try:
                        deleted_paths.add(str(cand.relative_to(project_root)))
                    except ValueError:
                        deleted_paths.add(str(cand))
            if not wanted and not deleted_paths:
                print("[graphify watch] No tracked code files in change set - skipping rebuild.")
                return True
            extract_targets = wanted
        else:
            extract_targets = code_files

        commit = _git_head()
        result = extract(extract_targets, cache_root=watch_root) if extract_targets else {
            "nodes": [], "edges": [], "hyperedges": [],
            "input_tokens": 0, "output_tokens": 0,
        }

        # Preserve semantic nodes/edges from a previous full run.
        # AST-only rebuild replaces nodes for changed files; everything else is kept.
        # Filter by node ID membership in the new AST output, not by file_type —
        # INFERRED/AMBIGUOUS nodes extracted from code files also carry file_type="code"
        # and would be wrongly dropped by a file_type-based filter.
        # When the caller supplied changed_paths, also evict preserved nodes whose
        # source_file matches a path that was changed (re-extracted) or deleted —
        # otherwise the old nodes for those files would survive forever.
        existing_graph = out / "graph.json"
        if existing_graph.exists():
            try:
                existing = json.loads(existing_graph.read_text(encoding="utf-8"))
                new_ast_ids = {n["id"] for n in result["nodes"]}
                evict_sources: set[str] = set(deleted_paths)
                if changed_paths is not None:
                    for p in extract_targets:
                        try:
                            evict_sources.add(str(p.relative_to(project_root)))
                        except ValueError:
                            evict_sources.add(str(p))
                preserved_nodes = [
                    n for n in existing.get("nodes", [])
                    if n["id"] not in new_ast_ids
                    and (not evict_sources or n.get("source_file") not in evict_sources)
                ]
                all_ids = new_ast_ids | {n["id"] for n in preserved_nodes}
                preserved_edges = [
                    e for e in existing.get("links", existing.get("edges", []))
                    if e.get("source") in all_ids and e.get("target") in all_ids
                ]
                result = {
                    "nodes": result["nodes"] + preserved_nodes,
                    "edges": result["edges"] + preserved_edges,
                    "hyperedges": existing.get("hyperedges", []),
                    "input_tokens": 0,
                    "output_tokens": 0,
                }
            except Exception:
                pass  # corrupt graph.json - proceed with AST-only

        _relativize_source_files(result, project_root)

        detection = {
            "files": {"code": [str(f) for f in code_files], "document": [], "paper": [], "image": []},
            "total_files": len(code_files),
            "total_words": detected.get("total_words", 0),
        }

        G = build_from_json(result)
        communities = cluster(G)
        cohesion = score_all(G, communities)
        gods = god_nodes(G)
        surprises = surprising_connections(G, communities)
        labels_file = out / ".graphify_labels.json"
        try:
            raw = json.loads(labels_file.read_text(encoding="utf-8")) if labels_file.exists() else {}
            labels = {int(k): v for k, v in raw.items() if int(k) in communities}
        except Exception:
            raw = {}
            labels = {}
        for cid in communities:
            if cid not in labels:
                labels[cid] = "Community " + str(cid)
        questions = suggest_questions(G, communities, labels)

        out.mkdir(exist_ok=True)
        (out / ".graphify_root").write_text(str(watch_root), encoding="utf-8")

        json_written = to_json(G, communities, str(out / "graph.json"), force=force, built_at_commit=commit)
        if not json_written:
            return False

        try:
            from graphify.detect import save_manifest
            save_manifest(detected["files"])
        except Exception:
            pass

        report = generate(G, communities, cohesion, labels, gods, surprises, detection,
                          {"input": 0, "output": 0}, report_root, suggested_questions=questions,
                          built_at_commit=commit)
        (out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")

        # to_html raises ValueError for graphs > MAX_NODES_FOR_VIZ (5000).
        # Wrap so core outputs (graph.json + GRAPH_REPORT.md) always land.
        html_written = False
        try:
            to_html(G, communities, str(out / "graph.html"), community_labels=labels or None)
            html_written = True
        except ValueError as viz_err:
            print(f"[graphify watch] Skipped graph.html: {viz_err}")
            stale = out / "graph.html"
            if stale.exists():
                stale.unlink()

        # Regenerate callflow HTML if the user previously generated one —
        # opt-in by existence so users who never ran callflow-html aren't affected.
        callflow_files = list(out.glob("*-callflow.html"))
        if callflow_files:
            try:
                from graphify.callflow_html import write_callflow_html
                for cf in callflow_files:
                    write_callflow_html(
                        graph=out / "graph.json",
                        report=out / "GRAPH_REPORT.md",
                        labels=out / ".graphify_labels.json",
                        output=cf,
                        verbose=False,
                    )
            except Exception as cf_err:
                print(f"[graphify watch] callflow HTML update skipped: {cf_err}")

        # clear stale needs_update flag if present
        flag = out / "needs_update"
        if flag.exists():
            flag.unlink()

        print(f"[graphify watch] Rebuilt: {G.number_of_nodes()} nodes, "
              f"{G.number_of_edges()} edges, {len(communities)} communities")
        products = "graph.json" + (", graph.html" if html_written else "") + " and GRAPH_REPORT.md"
        if callflow_files:
            products += f", {len(callflow_files)} callflow HTML"
        print(f"[graphify watch] {products} updated in {out}")
        return True

    except Exception as exc:
        print(f"[graphify watch] Rebuild failed: {exc}")
        return False


def expand_graph(
    watch_path: Path,
    expand_paths: list[Path],
    *,
    dry_run: bool = False,
    force: bool = False,
) -> bool:
    """Add new directories/files to an existing graph incrementally.

    Unlike _rebuild_code which re-extracts all files or specific changed files,
    this function:
    1. Detects code files in the expand_paths
    2. Loads existing graph and finds files NOT already tracked
    3. Extracts only the NEW files
    4. Merges new nodes into existing graph (preserving all existing nodes)

    Args:
        watch_path: the project root (where graphify-out lives)
        expand_paths: list of directories or files to add to the graph
        dry_run: if True, only show what would be added without modifying the graph
        force: if True, bypass node-count safety check

    Returns True on success, False on error or nothing to add.
    """
    from graphify.detect import detect
    from graphify.extract import extract, _get_extractor
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections, suggest_questions
    from graphify.report import generate
    from graphify.export import to_json

    out = watch_path / _GRAPHIFY_OUT
    if not out.exists():
        out.mkdir(parents=True, exist_ok=True)

    # Load existing graph to find what's already tracked
    existing_graph = out / "graph.json"
    existing_files: set[str] = set()
    existing_nodes: list[dict] = []
    existing_edges: list[dict] = []
    existing_hyperedges: list[dict] = []

    if existing_graph.exists():
        try:
            existing = json.loads(existing_graph.read_text(encoding="utf-8"))
            existing_nodes = existing.get("nodes", [])
            existing_edges = existing.get("links", existing.get("edges", []))
            existing_hyperedges = existing.get("hyperedges", [])
            # Build set of files already in the graph
            for node in existing_nodes:
                if sf := node.get("source_file"):
                    existing_files.add(sf)
        except Exception as e:
            print(f"[graphify expand] Warning: could not load existing graph: {e}")

    # Detect files in the expand paths
    all_candidate_files: list[Path] = []
    for ep in expand_paths:
        ep = ep.resolve()
        if not ep.exists():
            print(f"[graphify expand] Warning: path does not exist: {ep}")
            continue

        if ep.is_file():
            if ep.suffix in _WATCHED_EXTENSIONS:
                all_candidate_files.append(ep)
        else:
            # It's a directory - detect files in it
            detected = detect(ep, follow_symlinks=False)
            for f in detected['files']['code']:
                all_candidate_files.append(Path(f))
            # Also check document files with AST extractors
            for f in detected['files'].get('document', []):
                p = Path(f)
                if _get_extractor(p) is not None:
                    all_candidate_files.append(p)

    # Filter to only truly NEW files (not already in graph)
    new_files: list[Path] = []
    for f in all_candidate_files:
        try:
            rel_path = str(f.relative_to(watch_path.resolve()))
        except ValueError:
            rel_path = str(f)
        if rel_path not in existing_files:
            new_files.append(f)

    if not new_files:
        print("[graphify expand] No new files to add - all files in specified paths are already in the graph.")
        return True

    print(f"[graphify expand] Found {len(new_files)} new file(s) to add (from {len(existing_files)} already tracked)")

    if dry_run:
        print("[graphify expand] Dry run - would add:")
        for f in new_files[:20]:
            print(f"  - {f}")
        if len(new_files) > 20:
            print(f"  ... and {len(new_files) - 20} more")
        return True

    # Extract new files
    print(f"[graphify expand] Extracting {len(new_files)} new file(s)...")
    result = extract(new_files, cache_root=watch_path.resolve())

    # Merge with existing graph - preserve ALL existing nodes/edges
    # (unlike _rebuild_code which evicts nodes for changed files)
    new_ast_ids = {n["id"] for n in result["nodes"]}

    # Keep all existing nodes that aren't being replaced (none should be, since these are new files)
    preserved_nodes = [
        n for n in existing_nodes
        if n["id"] not in new_ast_ids
    ]
    all_ids = new_ast_ids | {n["id"] for n in preserved_nodes}

    preserved_edges = [
        e for e in existing_edges
        if e.get("source") in all_ids and e.get("target") in all_ids
    ]

    # Merge results
    merged_result = {
        "nodes": result["nodes"] + preserved_nodes,
        "edges": result["edges"] + preserved_edges,
        "hyperedges": existing_hyperedges,
        "input_tokens": result.get("input_tokens", 0),
        "output_tokens": result.get("output_tokens", 0),
    }

    # Relativize source files
    project_root = watch_path.resolve()
    _relativize_source_files(merged_result, project_root)

    # Build graph and run analysis
    detection = {
        "files": {
            "code": [str(f) for f in all_candidate_files],  # All files in expand paths
            "document": [],
            "paper": [],
            "image": []
        },
        "total_files": len(all_candidate_files),
        "total_words": 0,  # Not computed for expand
    }

    G = build_from_json(merged_result)
    communities = cluster(G)
    cohesion = score_all(G, communities)
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)

    # Load existing labels or create defaults
    labels_file = out / ".graphify_labels.json"
    try:
        raw = json.loads(labels_file.read_text(encoding="utf-8")) if labels_file.exists() else {}
        labels = {int(k): v for k, v in raw.items() if int(k) in communities}
    except Exception:
        raw = {}
        labels = {}
    for cid in communities:
        if cid not in labels:
            labels[cid] = "Community " + str(cid)

    questions = suggest_questions(G, communities, labels)

    # Save updated graph
    commit = _git_head()
    (out / ".graphify_root").write_text(str(watch_path.resolve()), encoding="utf-8")

    json_written = to_json(G, communities, str(out / "graph.json"), force=force, built_at_commit=commit)
    if not json_written:
        return False

    # Generate report
    report = generate(G, communities, cohesion, labels, gods, surprises, detection,
                      {"input": 0, "output": 0}, str(watch_path), suggested_questions=questions,
                      built_at_commit=commit)
    (out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")

    print(f"[graphify expand] Done - added {len(new_files)} new file(s). Graph now has {G.number_of_nodes()} nodes.")
    return True


def check_update(watch_path: Path) -> bool:
    """Check for pending semantic update flag and notify the user if set.

    Cron-safe: always returns True so cron jobs do not alarm.
    Non-code file changes (docs, papers, images) require LLM-backed
    re-extraction via `/graphify --update` — this function only signals
    that the update is needed.
    """
    flag = Path(watch_path) / _GRAPHIFY_OUT / "needs_update"
    if flag.exists():
        print(f"[graphify check-update] Pending non-code changes in {watch_path}.")
        print("[graphify check-update] Run `/graphify --update` to apply semantic re-extraction.")
    return True


def _notify_only(watch_path: Path) -> None:
    """Write a flag file and print a notification (fallback for non-code-only corpora)."""
    flag = watch_path / _GRAPHIFY_OUT / "needs_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1", encoding="utf-8")
    print(f"\n[graphify watch] New or changed files detected in {watch_path}")
    print("[graphify watch] Non-code files changed - semantic re-extraction requires LLM.")
    print("[graphify watch] Run `/graphify --update` in Claude Code to update the graph.")
    print(f"[graphify watch] Flag written to {flag}")


def _has_non_code(changed_paths: list[Path]) -> bool:
    return any(p.suffix.lower() not in _CODE_EXTENSIONS for p in changed_paths)


def watch(watch_path: Path, debounce: float = 3.0) -> None:
    """
    Watch watch_path for new or modified files and auto-update the graph.

    For code-only changes: re-runs AST extraction + rebuild immediately (no LLM).
    For doc/paper/image changes: writes a needs_update flag and notifies the user
    to run /graphify --update (LLM extraction required).

    debounce: seconds to wait after the last change before triggering (avoids
    running on every keystroke when many files are saved at once).
    """
    try:
        from watchdog.observers import Observer
        from watchdog.observers.polling import PollingObserver
        from watchdog.events import FileSystemEventHandler
    except ImportError as e:
        raise ImportError("watchdog not installed. Run: pip install watchdog") from e

    last_trigger: float = 0.0
    pending: bool = False
    changed: set[Path] = set()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            nonlocal last_trigger, pending
            if event.is_directory:
                return
            path = Path(event.src_path)
            if path.suffix.lower() not in _WATCHED_EXTENSIONS:
                return
            if any(part.startswith(".") for part in path.parts):
                return
            if _GRAPHIFY_OUT in path.parts:
                return
            last_trigger = time.monotonic()
            pending = True
            changed.add(path)

    handler = Handler()
    # Use polling observer on macOS — FSEvents can miss rapid saves in some editors
    observer = PollingObserver() if sys.platform == "darwin" else Observer()
    observer.schedule(handler, str(watch_path), recursive=True)
    observer.start()

    print(f"[graphify watch] Watching {watch_path.resolve()} - press Ctrl+C to stop")
    print(f"[graphify watch] Code changes rebuild graph automatically. "
          f"Doc/image changes require /graphify --update.")
    print(f"[graphify watch] Debounce: {debounce}s")

    try:
        while True:
            time.sleep(0.5)
            if pending and (time.monotonic() - last_trigger) >= debounce:
                pending = False
                batch = list(changed)
                changed.clear()
                print(f"\n[graphify watch] {len(batch)} file(s) changed")
                has_non_code = _has_non_code(batch)
                has_code = any(p.suffix.lower() in _CODE_EXTENSIONS for p in batch)
                if has_code:
                    _rebuild_code(watch_path)
                if has_non_code:
                    _notify_only(watch_path)
    except KeyboardInterrupt:
        print("\n[graphify watch] Stopped.")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Watch a folder and auto-update the graphify graph")
    parser.add_argument("path", nargs="?", default=".", help="Folder to watch (default: .)")
    parser.add_argument("--debounce", type=float, default=3.0,
                        help="Seconds to wait after last change before updating (default: 3)")
    args = parser.parse_args()
    watch(Path(args.path), debounce=args.debounce)
