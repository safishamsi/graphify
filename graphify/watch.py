# monitor a folder and auto-trigger --update when files change
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

_GRAPHIFY_OUT = os.environ.get("GRAPHIFY_OUT", "graphify-out")


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


def _is_code_path(path: Path) -> bool:
    """Return True if this path is a code file (detection-based, not suffix-only).

    Handles extensionless files with Bash-family shebangs that suffix-only
    checks would miss.
    """
    if path.suffix.lower() in _CODE_EXTENSIONS:
        return True
    if path.suffix:
        return False
    try:
        from graphify.detect import classify_file, FileType
        return classify_file(path) == FileType.CODE
    except Exception:
        return False


def _report_root_label(watch_path: Path) -> str:
    if watch_path.is_absolute():
        return watch_path.name or str(watch_path)
    return Path.cwd().name if watch_path == Path(".") else str(watch_path)


def _portable_root_label(watch_path: Path, project_root: Path) -> str:
    """Return the value to persist in graphify-out/.graphify_root.

    Current code stores watch_path.resolve(), which breaks after clone (#777).
    Preserve explicit relative paths such as "." and "src"; for absolute paths
    inside the current project, store a project-relative path.
    """
    if not watch_path.is_absolute():
        return str(watch_path)
    try:
        return str(watch_path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return str(watch_path.resolve())


def _changed_extractor_inputs(incremental: dict) -> list[str]:
    """Return changed files that affect AST-only graph output."""
    from graphify.extract import _get_extractor

    changed: list[str] = []
    for file_list in incremental.get("new_files", {}).values():
        for f in file_list:
            if _get_extractor(Path(f)) is not None:
                changed.append(f)
    return changed


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


def _rebuild_code(watch_path: Path, *, follow_symlinks: bool = False, force: bool = False) -> bool:
    """Re-run AST extraction + build + cluster + report for code files. No LLM needed."""
    watch_root = watch_path.resolve()
    project_root = Path.cwd().resolve() if not watch_path.is_absolute() else watch_root
    report_root = _report_root_label(watch_path)
    out = watch_path / _GRAPHIFY_OUT
    manifest_path = out / "manifest.json"
    try:
        from graphify.extract import extract
        from graphify.detect import detect, detect_incremental
        from graphify.build import build_from_json
        from graphify.cluster import cluster, score_all
        from graphify.analyze import god_nodes, surprising_connections, suggest_questions
        from graphify.report import generate
        from graphify.export import to_json, to_html

        detected = detect(watch_path, follow_symlinks=follow_symlinks)
        code_files = [Path(f) for f in detected["files"]["code"]]

        from graphify.extract import _get_extractor
        for doc_file in detected["files"].get("document", []):
            p = Path(doc_file)
            if _get_extractor(p) is not None:
                code_files.append(p)

        if not code_files:
            print("[graphify watch] No code files found - nothing to rebuild.")
            return False

        existing_graph = out / "graph.json"
        deleted_inputs: list[str] = []
        if not force and existing_graph.exists() and manifest_path.exists():
            incremental = detect_incremental(
                watch_root,
                manifest_path=str(manifest_path),
                follow_symlinks=follow_symlinks,
                full=detected,
            )
            changed_inputs = _changed_extractor_inputs(incremental)
            deleted_inputs = incremental.get("deleted_files", [])
            if not changed_inputs and not deleted_inputs:
                print("[graphify watch] Already up to date; graph outputs left unchanged.")
                return True

        commit = _git_head()
        result = extract(code_files, cache_root=watch_root)

        if existing_graph.exists():
            try:
                existing = json.loads(existing_graph.read_text(encoding="utf-8"))
                new_ast_ids = {n["id"] for n in result["nodes"]}
                # F2: Build deleted-source set for filtering preserved nodes.
                # deleted_inputs are absolute paths from detect_incremental;
                # graph node source_file may be relative (#777). Match both forms.
                _deleted_sources: set[str] = set()
                for dp in deleted_inputs:
                    _deleted_sources.add(dp)
                    try:
                        _deleted_sources.add(str(Path(dp).resolve().relative_to(project_root)))
                    except ValueError:
                        pass
                preserved_nodes = [
                    n for n in existing.get("nodes", [])
                    if n["id"] not in new_ast_ids
                    and n.get("source_file") not in _deleted_sources
                ]
                all_ids = new_ast_ids | {n["id"] for n in preserved_nodes}
                preserved_edges = [
                    e for e in existing.get("links", existing.get("edges", []))
                    if e.get("source") in all_ids and e.get("target") in all_ids
                ]
                # F2: filter hyperedges to drop members from deleted files
                _preserved_hyperedges: list[dict] = []
                for he in existing.get("hyperedges", []):
                    members = [
                        m for m in he.get("nodes", [])
                        if m in all_ids
                    ]
                    if len(members) >= 2:
                        _preserved_hyperedges.append({**he, "nodes": members})
                result = {
                    "nodes": result["nodes"] + preserved_nodes,
                    "edges": result["edges"] + preserved_edges,
                    "hyperedges": _preserved_hyperedges,
                    "input_tokens": 0,
                    "output_tokens": 0,
                }
            except Exception:
                print(
                    f"[graphify watch] Could not read {existing_graph}; rebuilding from AST only.",
                    file=sys.stderr,
                )
                pass

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
            labels = {}
        for cid in communities:
            if cid not in labels:
                labels[cid] = "Community " + str(cid)
        questions = suggest_questions(G, communities, labels)

        out.mkdir(exist_ok=True)
        (out / ".graphify_root").write_text(_portable_root_label(watch_path, project_root), encoding="utf-8")

        json_written = to_json(G, communities, str(out / "graph.json"), force=force, built_at_commit=commit)
        if not json_written:
            return False

        try:
            from graphify.detect import save_manifest
            save_manifest(detected["files"], manifest_path=str(manifest_path), root=watch_root)
        except Exception:
            pass

        report = generate(
            G,
            communities,
            cohesion,
            labels,
            gods,
            surprises,
            detection,
            {"input": 0, "output": 0},
            report_root,
            suggested_questions=questions,
            built_at_commit=commit,
        )
        (out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")

        html_written = False
        try:
            to_html(G, communities, str(out / "graph.html"), community_labels=labels or None)
            html_written = True
        except ValueError as viz_err:
            print(f"[graphify watch] Skipped graph.html: {viz_err}")
            stale = out / "graph.html"
            if stale.exists():
                stale.unlink()

        flag = out / "needs_update"
        if flag.exists():
            flag.unlink()

        print(f"[graphify watch] Rebuilt: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities")
        if not html_written:
            print(f"[graphify watch] Wrote graph.json + GRAPH_REPORT.md to {out}")
        return True
    except Exception as e:
        print(f"[graphify watch] Rebuild failed: {e}", file=sys.stderr)
        return False


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
    return any(not _is_code_path(p) for p in changed_paths)


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
            if path.suffix.lower() not in _WATCHED_EXTENSIONS and not _is_code_path(path):
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
                has_code = any(_is_code_path(p) for p in batch)
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
