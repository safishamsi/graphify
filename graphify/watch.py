# monitor a folder and auto-trigger --update when files change
from __future__ import annotations
import json
import sys
import time
from pathlib import Path


from graphify.detect import CODE_EXTENSIONS, DOC_EXTENSIONS, PAPER_EXTENSIONS, IMAGE_EXTENSIONS

_WATCHED_EXTENSIONS = CODE_EXTENSIONS | DOC_EXTENSIONS | PAPER_EXTENSIONS | IMAGE_EXTENSIONS
_CODE_EXTENSIONS = CODE_EXTENSIONS


def _rebuild_code(watch_path: Path, *, follow_symlinks: bool = False) -> bool:
    """Re-run AST extraction + build + cluster + report for code files. No LLM needed.

    Returns True on success, False on error.
    """
    watch_path = watch_path.resolve()
    try:
        from graphify.extract import extract
        from graphify.detect import detect
        from graphify.build import build_from_json
        from graphify.cluster import cluster, score_all
        from graphify.analyze import god_nodes, surprising_connections, suggest_questions
        from graphify.report import generate
        from graphify.export import to_json, to_html

        detected = detect(watch_path, follow_symlinks=follow_symlinks)
        code_files = [Path(f) for f in detected['files']['code']]

        if not code_files:
            print("[graphify watch] No code files found - nothing to rebuild.")
            return False

        result = extract(code_files, cache_root=watch_path)

        # Preserve semantic nodes/edges from a previous full run.
        # AST-only rebuild replaces code nodes; doc/paper/image nodes are kept.
        out = watch_path / "graphify-out"
        existing_graph = out / "graph.json"
        if existing_graph.exists():
            try:
                existing = json.loads(existing_graph.read_text(encoding="utf-8"))
                code_ids = {n["id"] for n in existing.get("nodes", []) if n.get("file_type") == "code"}
                sem_nodes = [n for n in existing.get("nodes", []) if n.get("file_type") != "code"]
                sem_edges = [e for e in existing.get("links", existing.get("edges", []))
                             if e.get("confidence") in ("INFERRED", "AMBIGUOUS")
                             or (e.get("source") not in code_ids and e.get("target") not in code_ids)]
                result = {
                    "nodes": result["nodes"] + sem_nodes,
                    "edges": result["edges"] + sem_edges,
                    "hyperedges": existing.get("hyperedges", []),
                    "input_tokens": 0,
                    "output_tokens": 0,
                }
            except Exception:
                pass  # corrupt graph.json - proceed with AST-only

        # Inject persistent cross-file edges
        cross_edges_path = out / "cross_edges.json"
        if cross_edges_path.exists():
            try:
                cross_data = json.loads(cross_edges_path.read_text(encoding="utf-8"))
                cross_edges = cross_data.get("edges", [])
                merged_node_ids = {n["id"] for n in result["nodes"]}
                existing_edge_keys = {
                    (e.get("source"), e.get("target"), e.get("relation"))
                    for e in result["edges"]
                }
                injected = 0
                for edge in cross_edges:
                    src, tgt = edge.get("source"), edge.get("target")
                    rel = edge.get("relation", "")
                    if src in merged_node_ids and tgt in merged_node_ids:
                        if (src, tgt, rel) not in existing_edge_keys:
                            result["edges"].append(edge)
                            existing_edge_keys.add((src, tgt, rel))
                            injected += 1
                if injected:
                    print(f"[graphify watch] Injected {injected} cross-file edge(s) from cross_edges.json")
            except Exception:
                pass  # malformed cross_edges.json -- skip silently

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
        labels = {cid: "Community " + str(cid) for cid in communities}
        questions = suggest_questions(G, communities, labels)

        out.mkdir(exist_ok=True)

        report = generate(G, communities, cohesion, labels, gods, surprises, detection,
                          {"input": 0, "output": 0}, str(watch_path), suggested_questions=questions)
        (out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
        to_json(G, communities, str(out / "graph.json"))

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

        # clear stale needs_update flag if present
        flag = out / "needs_update"
        if flag.exists():
            flag.unlink()

        print(f"[graphify watch] Rebuilt: {G.number_of_nodes()} nodes, "
              f"{G.number_of_edges()} edges, {len(communities)} communities")
        products = "graph.json" + (", graph.html" if html_written else "") + " and GRAPH_REPORT.md"
        print(f"[graphify watch] {products} updated in {out}")
        return True

    except Exception as exc:
        print(f"[graphify watch] Rebuild failed: {exc}")
        return False


def _notify_only(watch_path: Path) -> None:
    """Write a flag file and print a notification (fallback for non-code-only corpora)."""
    flag = watch_path / "graphify-out" / "needs_update"
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
            if "graphify-out" in path.parts:
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
                if _has_non_code(batch):
                    _notify_only(watch_path)
                else:
                    _rebuild_code(watch_path)
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
