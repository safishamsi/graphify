"""Tests for watch.py - file watcher helpers (no watchdog required)."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
import pytest

from graphify.watch import _notify_only, _WATCHED_EXTENSIONS, _rebuild_lock, _check_shrink


# --- _notify_only ---


def test_notify_only_creates_flag(tmp_path):
    _notify_only(tmp_path)
    flag = tmp_path / "graphify-out" / "needs_update"
    assert flag.exists()
    assert flag.read_text() == "1"


def test_notify_only_creates_flag_dir(tmp_path):
    # graphify-out dir does not exist yet
    assert not (tmp_path / "graphify-out").exists()
    _notify_only(tmp_path)
    assert (tmp_path / "graphify-out").is_dir()


def test_notify_only_idempotent(tmp_path):
    _notify_only(tmp_path)
    _notify_only(tmp_path)
    flag = tmp_path / "graphify-out" / "needs_update"
    assert flag.read_text() == "1"


# --- _WATCHED_EXTENSIONS ---


def test_watched_extensions_includes_code():
    assert ".py" in _WATCHED_EXTENSIONS
    assert ".ts" in _WATCHED_EXTENSIONS
    assert ".go" in _WATCHED_EXTENSIONS
    assert ".rs" in _WATCHED_EXTENSIONS


def test_watched_extensions_includes_docs():
    assert ".md" in _WATCHED_EXTENSIONS
    assert ".txt" in _WATCHED_EXTENSIONS
    assert ".pdf" in _WATCHED_EXTENSIONS


def test_watched_extensions_includes_images():
    assert ".png" in _WATCHED_EXTENSIONS
    assert ".jpg" in _WATCHED_EXTENSIONS


def test_watched_extensions_excludes_noise():
    # .json is now indexed (bash/JSON extractors added in #866)
    assert ".json" in _WATCHED_EXTENSIONS
    assert ".sh" in _WATCHED_EXTENSIONS
    assert ".pyc" not in _WATCHED_EXTENSIONS
    assert ".log" not in _WATCHED_EXTENSIONS


# --- watch() import error without watchdog ---


def test_check_update_no_flag_returns_true(tmp_path):
    """check_update returns True and is silent when needs_update flag is absent."""
    from graphify.watch import check_update

    assert check_update(tmp_path) is True


def test_check_update_with_flag_returns_true_and_prints(tmp_path, capsys):
    """check_update returns True and prints notification when flag exists."""
    from graphify.watch import check_update

    flag = tmp_path / "graphify-out" / "needs_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1")
    result = check_update(tmp_path)
    assert result is True
    out = capsys.readouterr().out
    assert "graphify --update" in out


def test_check_update_does_not_clear_flag(tmp_path):
    """check_update never removes the needs_update flag (clearing is LLM's job)."""
    from graphify.watch import check_update

    flag = tmp_path / "graphify-out" / "needs_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1")
    check_update(tmp_path)
    assert flag.exists()


def test_watch_raises_without_watchdog(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "watchdog.observers" or name == "watchdog.events":
            raise ImportError("mocked missing watchdog")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    from graphify.watch import watch

    with pytest.raises(ImportError, match="watchdog not installed"):
        watch(tmp_path)


# --- _rebuild_lock (GH-858) ---


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_lock_writes_pid_with_newline(tmp_path):
    out = tmp_path / "graphify-out"
    lock_path = out / ".rebuild.lock"
    with _rebuild_lock(out) as got:
        assert got is True
        assert lock_path.exists()
        contents = lock_path.read_text(encoding="utf-8")
        assert contents == f"{os.getpid()}\n", contents


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_lock_removed_after_release(tmp_path):
    """GH-858: lock file must be unlinked once the rebuild completes so
    downstream waiters that poll for its absence unblock promptly."""
    out = tmp_path / "graphify-out"
    lock_path = out / ".rebuild.lock"
    with _rebuild_lock(out) as got:
        assert got is True
    assert not lock_path.exists(), "lock file should be unlinked after release"


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_lock_does_not_accumulate_pids_across_runs(tmp_path):
    """GH-858: each acquisition truncates and rewrites the PID line rather
    than appending, so the file never grows into a digit-concatenation."""
    out = tmp_path / "graphify-out"
    lock_path = out / ".rebuild.lock"
    expected = f"{os.getpid()}\n"
    for _ in range(5):
        with _rebuild_lock(out) as got:
            assert got is True
            assert lock_path.read_text(encoding="utf-8") == expected
        assert not lock_path.exists()


def test_rebuild_code_evicts_nodes_from_deleted_files(tmp_path):
    """#1007: graphify update (_rebuild_code with no changed_paths) must remove
    nodes and edges from files deleted since the last run."""
    import json
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()

    (corpus / "auth.py").write_text("def login(): pass\ndef logout(): pass\n", encoding="utf-8")
    (corpus / "utils.py").write_text("def format_date(): pass\n", encoding="utf-8")

    assert _rebuild_code(corpus, acquire_lock=False) is True
    graph_path = corpus / "graphify-out" / "graph.json"
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    node_labels_before = {n["label"] for n in data.get("nodes", [])}
    assert "format_date()" in node_labels_before

    (corpus / "utils.py").unlink()

    assert _rebuild_code(corpus, acquire_lock=False) is True
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    node_labels_after = {n["label"] for n in data.get("nodes", [])}
    assert "format_date()" not in node_labels_after, (
        "stale function node from deleted file must be evicted"
    )
    assert "login()" in node_labels_after, "nodes from surviving file must be kept"


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_lock_non_blocking_does_not_clobber_holder(tmp_path):
    """GH-858: a non-blocking caller that fails to acquire the lock must not
    truncate the holder's PID payload."""
    out = tmp_path / "graphify-out"
    lock_path = out / ".rebuild.lock"
    with _rebuild_lock(out) as outer:
        assert outer is True
        held_contents = lock_path.read_text(encoding="utf-8")
        with _rebuild_lock(out, blocking=False) as inner:
            assert inner is False
            # Holder's PID line must still be intact.
            assert lock_path.read_text(encoding="utf-8") == held_contents


def test_rebuild_code_is_idempotent_when_cluster_ids_flap(tmp_path, monkeypatch):
    from graphify import cluster as cluster_mod
    from graphify.watch import _rebuild_code

    src = tmp_path / "app.py"
    src.write_text(
        "def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n", encoding="utf-8"
    )

    calls = {"n": 0}

    def flaky_cluster(G):
        calls["n"] += 1
        nodes = sorted(G.nodes())
        if calls["n"] % 2 == 1:
            return {100: nodes}
        return {7: nodes}

    monkeypatch.setattr(cluster_mod, "cluster", flaky_cluster)
    monkeypatch.setattr(cluster_mod, "score_all", lambda _G, comm: {cid: 1.0 for cid in comm})

    assert _rebuild_code(tmp_path)
    graph_path = tmp_path / "graphify-out" / "graph.json"
    report_path = tmp_path / "graphify-out" / "GRAPH_REPORT.md"
    first_graph = graph_path.read_text(encoding="utf-8")
    first_report = report_path.read_text(encoding="utf-8")

    assert _rebuild_code(tmp_path)
    second_graph = graph_path.read_text(encoding="utf-8")
    second_report = report_path.read_text(encoding="utf-8")

    assert first_graph == second_graph
    assert first_report == second_report


def test_rebuild_code_skips_cluster_when_topology_unchanged(tmp_path, monkeypatch):
    from graphify import cluster as cluster_mod
    from graphify.watch import _rebuild_code

    src = tmp_path / "app.py"
    src.write_text(
        "def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n", encoding="utf-8"
    )

    calls = {"n": 0}

    def cluster_once(G):
        calls["n"] += 1
        if calls["n"] > 1:
            raise AssertionError("cluster() should be skipped when topology is unchanged")
        return {0: sorted(G.nodes())}

    monkeypatch.setattr(cluster_mod, "cluster", cluster_once)
    monkeypatch.setattr(cluster_mod, "score_all", lambda _G, comm: {cid: 1.0 for cid in comm})

    assert _rebuild_code(tmp_path)
    assert _rebuild_code(tmp_path)
    assert calls["n"] == 1


def test_rebuild_code_no_viz_removes_stale_html_and_skips_export(tmp_path, monkeypatch, capsys):
    from graphify import export as export_mod
    from graphify.watch import _rebuild_code

    (tmp_path / "app.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    stale_html = out / "graph.html"
    stale_html.write_text("<html/>", encoding="utf-8")

    def fail_to_html(*_args, **_kwargs):
        raise AssertionError("to_html should not be called when no_viz=True")

    monkeypatch.setattr(export_mod, "to_html", fail_to_html)

    assert _rebuild_code(tmp_path, no_viz=True)
    assert not stale_html.exists()
    assert "Skipped graph.html" not in capsys.readouterr().out


# --- .graphifyignore honored in watch handler (gh-928) ---


def _watchdog_available() -> bool:
    try:
        import watchdog  # noqa: F401

        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _watchdog_available(), reason="watchdog not installed")
def test_watch_handler_honors_graphifyignore(tmp_path, monkeypatch):
    """gh-928: the watch Handler must short-circuit paths matching
    .graphifyignore so busy volumes (node_modules churn, build artefacts,
    Time Machine writes, …) don't wake the rebuild pipeline.
    """
    import threading
    from graphify import watch as watch_mod

    (tmp_path / ".graphifyignore").write_text("node_modules/\nbuild/\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "build").mkdir()

    rebuild_calls: list[Path] = []
    notify_calls: list[Path] = []
    monkeypatch.setattr(watch_mod, "_rebuild_code", lambda p, **kw: rebuild_calls.append(p) or True)
    monkeypatch.setattr(watch_mod, "_notify_only", lambda p: notify_calls.append(p))

    # Run watch() in a thread with a short debounce so we can verify the
    # post-debounce dispatch path actually runs on real events.
    t = threading.Thread(
        target=watch_mod.watch, args=(tmp_path,), kwargs={"debounce": 0.2}, daemon=True
    )
    t.start()
    time.sleep(0.5)  # let observer.start() settle

    # Ignored writes — handler must drop these.
    (tmp_path / "node_modules" / "junk.js").write_text("// noise\n", encoding="utf-8")
    (tmp_path / "build" / "out.py").write_text("x = 1\n", encoding="utf-8")
    time.sleep(1.0)
    assert rebuild_calls == [], "ignored writes triggered a rebuild"
    assert notify_calls == [], "ignored writes triggered a notify"

    # Non-ignored write — handler must accept and (after debounce) dispatch.
    (tmp_path / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not rebuild_calls:
        time.sleep(0.1)
    assert rebuild_calls, "non-ignored .py write should have triggered _rebuild_code"


@pytest.mark.skipif(not _watchdog_available(), reason="watchdog not installed")
def test_watch_loads_graphifyignore_once(tmp_path, monkeypatch):
    """gh-928: .graphifyignore must be parsed exactly once at watch() startup,
    not per filesystem event. Otherwise busy volumes re-read the file
    thousands of times per second.
    """
    import threading
    from graphify import watch as watch_mod
    from graphify import detect as detect_mod

    (tmp_path / ".graphifyignore").write_text("ignored/\n", encoding="utf-8")
    (tmp_path / "ignored").mkdir()

    calls = {"n": 0}
    real_loader = detect_mod._load_graphifyignore

    def counting_loader(root):
        calls["n"] += 1
        return real_loader(root)

    # Patch the symbol the watch module imported at module-load time.
    monkeypatch.setattr(watch_mod, "_load_graphifyignore", counting_loader)
    monkeypatch.setattr(watch_mod, "_rebuild_code", lambda p, **kw: True)
    monkeypatch.setattr(watch_mod, "_notify_only", lambda p: None)

    t = threading.Thread(
        target=watch_mod.watch, args=(tmp_path,), kwargs={"debounce": 0.2}, daemon=True
    )
    t.start()
    time.sleep(0.5)

    # Generate many events; loader must not be called again.
    for i in range(50):
        (tmp_path / "ignored" / f"f{i}.py").write_text("x\n", encoding="utf-8")
    time.sleep(0.7)
    assert calls["n"] == 1, f"_load_graphifyignore called {calls['n']} times; expected 1"


# --- _check_shrink: silent-corruption guard with explicit-deletion bypass ---


def _shrink_payload(n: int) -> dict:
    """Build a minimal graph-data dict with *n* placeholder nodes."""
    return {"nodes": [{"id": f"n{i}"} for i in range(n)], "links": []}


def test_check_shrink_blocks_silent_shrink(capsys):
    """Default case: smaller new graph + no force + no declared deletions = refuse."""
    ok = _check_shrink(
        force=False,
        existing_data=_shrink_payload(100),
        new_data=_shrink_payload(80),
    )
    assert ok is False
    captured = capsys.readouterr()
    assert "Refusing to overwrite" in captured.err
    assert "80 nodes" in captured.err and "100" in captured.err


def test_check_shrink_allows_force_override():
    """force=True bypasses the guard regardless of node delta."""
    ok = _check_shrink(
        force=True,
        existing_data=_shrink_payload(100),
        new_data=_shrink_payload(1),
    )
    assert ok is True


def test_check_shrink_allows_explicit_deletions(capsys):
    """Caller declared deletions → shrink is expected → guard skipped silently."""
    ok = _check_shrink(
        force=False,
        existing_data=_shrink_payload(100),
        new_data=_shrink_payload(80),
        had_explicit_deletions=True,
    )
    assert ok is True
    # And critically, no scary warning is printed when the shrink is intentional.
    assert "Refusing to overwrite" not in capsys.readouterr().err


def test_check_shrink_allows_no_existing_data():
    """First-run case: no existing graph → guard inert."""
    ok = _check_shrink(
        force=False,
        existing_data={},
        new_data=_shrink_payload(50),
    )
    assert ok is True


def test_check_shrink_allows_growth():
    """new > existing is always fine."""
    ok = _check_shrink(
        force=False,
        existing_data=_shrink_payload(50),
        new_data=_shrink_payload(60),
    )
    assert ok is True


def test_check_shrink_unlinks_tmp_on_refuse(tmp_path):
    """When refusing, the temp graph file gets cleaned up so it can't leak across runs."""
    tmp = tmp_path / "graph.tmp.json"
    tmp.write_text("{}", encoding="utf-8")
    ok = _check_shrink(
        force=False,
        existing_data=_shrink_payload(100),
        new_data=_shrink_payload(80),
        tmp=tmp,
    )
    assert ok is False
    assert not tmp.exists()


def test_check_shrink_keeps_tmp_when_deletions_declared(tmp_path):
    """Mirror of the above: if the caller declared deletions, the tmp file is NOT unlinked
    because the caller is going to swap it into place. Regression guard against a future
    bug where the tmp cleanup leaks out of the refuse branch.
    """
    tmp = tmp_path / "graph.tmp.json"
    tmp.write_text("{}", encoding="utf-8")
    ok = _check_shrink(
        force=False,
        existing_data=_shrink_payload(100),
        new_data=_shrink_payload(80),
        tmp=tmp,
        had_explicit_deletions=True,
    )
    assert ok is True
    assert tmp.exists()


# --- _rebuild_code integration: post-commit delete scenario ---


@pytest.mark.skipif(sys.platform == "win32", reason="git CLI behaviour varies on Windows runners")
def test_rebuild_code_prunes_deleted_file_nodes(tmp_path):
    """End-to-end probe of the post-commit-delete bug fix.

    Build a tiny graph, delete one of its source files, then call _rebuild_code
    with the deleted path in changed_paths. Without the fix this raises the
    shrink guard and refuses to write; with the fix the deleted file's nodes
    are pruned and graph.json is rewritten.
    """
    from graphify.watch import _rebuild_code

    # Set up a minimal "project" with two Python files in a git repo so detect
    # treats it as a real corpus.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
        check=True,
    )

    keep = tmp_path / "keep.py"
    drop = tmp_path / "drop.py"
    keep.write_text("def keep_fn():\n    return 1\n", encoding="utf-8")
    drop.write_text("def drop_fn():\n    return 2\n", encoding="utf-8")

    # Initial build covers both files.
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        ok = _rebuild_code(tmp_path, no_cluster=True)
        assert ok is True
        graph_path = tmp_path / "graphify-out" / "graph.json"
        assert graph_path.exists()
        before = json.loads(graph_path.read_text(encoding="utf-8"))
        before_sources = {n.get("source_file") for n in before.get("nodes", [])}
        assert "drop.py" in before_sources

        # Now delete drop.py and re-run with it in the change list. This is what
        # the post-commit hook does when git diff --name-only HEAD~1 HEAD includes
        # a deletion: the path is passed to _rebuild_code even though it no
        # longer exists on disk.
        drop.unlink()
        ok = _rebuild_code(
            tmp_path,
            changed_paths=[Path("drop.py")],
            no_cluster=True,
        )
        assert ok is True, "rebuild should succeed even though the graph shrinks"

        after = json.loads(graph_path.read_text(encoding="utf-8"))
        after_sources = {n.get("source_file") for n in after.get("nodes", [])}
        assert "drop.py" not in after_sources, "deleted file's nodes should be pruned"
        assert "keep.py" in after_sources, "untouched file's nodes should survive"
    finally:
        os.chdir(cwd)


# --- #1059: pending-changes queue prevents commit drops under lock contention ---


def test_queue_and_drain_pending_round_trip(tmp_path):
    """_queue_pending writes one path per line; _drain_pending reads + unlinks
    and returns the same set of paths."""
    from graphify.watch import _queue_pending, _drain_pending, _PENDING_FILENAME

    out = tmp_path / "graphify-out"
    paths = [Path("a.py"), Path("sub/b.py"), Path("c.md")]
    _queue_pending(out, paths)

    pending_file = out / _PENDING_FILENAME
    assert pending_file.exists()
    # Each path written on its own line.
    assert pending_file.read_text(encoding="utf-8").splitlines() == [
        "a.py",
        "sub/b.py",
        "c.md",
    ]

    drained = _drain_pending(out)
    assert drained == paths
    # Drain unlinks so subsequent callers see an empty queue.
    assert not pending_file.exists()
    assert _drain_pending(out) == []


def test_drain_pending_dedupes_and_skips_blank_lines(tmp_path):
    """Repeated appends across concurrent contenders must dedupe; partial
    writes leaving blank lines must not poison the merge."""
    from graphify.watch import _queue_pending, _drain_pending

    out = tmp_path / "graphify-out"
    _queue_pending(out, [Path("a.py"), Path("b.py")])
    _queue_pending(out, [Path("b.py"), Path("c.py")])
    # Simulate a torn write leaving an empty line.
    with open(out / ".pending_changes", "a", encoding="utf-8") as fh:
        fh.write("\n   \n")

    drained = _drain_pending(out)
    assert drained == [Path("a.py"), Path("b.py"), Path("c.py")]


def test_queue_pending_noop_on_empty_list(tmp_path):
    """Empty change set must not create an empty .pending_changes file."""
    from graphify.watch import _queue_pending, _PENDING_FILENAME

    out = tmp_path / "graphify-out"
    _queue_pending(out, [])
    assert not (out / _PENDING_FILENAME).exists()


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_code_queues_on_lock_contention(tmp_path, monkeypatch, capsys):
    """#1059: when the rebuild lock is held, an incremental hook must queue
    its changed_paths to .pending_changes and print 'queued' instead of
    silently dropping the change set."""
    from graphify.watch import _rebuild_code, _rebuild_lock, _PENDING_FILENAME

    out = tmp_path / "graphify-out"
    out.mkdir()

    # Hold the lock so the next non-blocking attempt fails. Use a real
    # _rebuild_lock context manager in this same process — flock on the same
    # file descriptor would otherwise be re-entrant on Linux, so we open
    # the file ourselves via the lock helper.
    with _rebuild_lock(out, blocking=False) as outer_got:
        assert outer_got is True

        ok = _rebuild_code(
            tmp_path,
            changed_paths=[Path("a.py"), Path("b.py")],
        )
        assert ok is False

        # Output should say "queued", not "skipping".
        captured = capsys.readouterr().out
        assert "queued" in captured.lower()
        assert "skipping" not in captured.lower()

        # And the paths must have been written to the pending file so the
        # eventual lock-holder can drain them.
        pending = out / _PENDING_FILENAME
        assert pending.exists()
        assert pending.read_text(encoding="utf-8").splitlines() == ["a.py", "b.py"]


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_code_merges_pending_on_acquire(tmp_path, monkeypatch):
    """#1059: the process that acquires the lock must drain .pending_changes
    and pass the merged change set to the inner rebuild call."""
    from graphify import watch as watch_mod

    out = tmp_path / "graphify-out"
    out.mkdir()
    # Pre-populate the queue as if an earlier contender had dropped its paths.
    watch_mod._queue_pending(out, [Path("queued1.py"), Path("queued2.py")])

    # Snapshot the original BEFORE monkeypatching so we can drive the outer
    # dispatch path while the inner recursive call resolves to our spy.
    orig_rebuild = watch_mod._rebuild_code
    inner_calls: list[list[str]] = []

    def recording_inner(watch_path, **kwargs):
        if kwargs.get("acquire_lock") is False:
            paths = kwargs.get("changed_paths") or []
            inner_calls.append([p.as_posix() for p in paths])
        return True

    monkeypatch.setattr(watch_mod, "_rebuild_code", recording_inner)

    ok = orig_rebuild(
        tmp_path,
        changed_paths=[Path("own.py"), Path("queued1.py")],
    )
    assert ok is True

    # The first inner call must have received the merged + deduped set:
    # own.py first (caller's order preserved), then drained queued1/queued2,
    # with queued1.py deduped against own's prior occurrence.
    assert inner_calls, "inner _rebuild_code should have been called"
    assert inner_calls[0] == ["own.py", "queued1.py", "queued2.py"]

    # And .pending_changes was drained.
    assert not (out / watch_mod._PENDING_FILENAME).exists()


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_code_drains_late_arrivals(tmp_path, monkeypatch):
    """#1059: after the primary rebuild, the lock-holder must loop and drain
    any paths queued by hooks that arrived mid-rebuild."""
    from graphify import watch as watch_mod
    from graphify.watch import _rebuild_code as orig_rebuild

    out = tmp_path / "graphify-out"
    out.mkdir()

    inner_calls: list[list[str]] = []
    call_state = {"i": 0}

    def fake_inner(watch_path, **kwargs):
        if kwargs.get("acquire_lock") is False:
            paths = [p.as_posix() for p in (kwargs.get("changed_paths") or [])]
            inner_calls.append(paths)
            # Simulate a late-arriving hook that queues during the FIRST
            # inner rebuild only. The outer drain loop must see it.
            call_state["i"] += 1
            if call_state["i"] == 1:
                watch_mod._queue_pending(out, [Path("late.py")])
        return True

    monkeypatch.setattr(watch_mod, "_rebuild_code", fake_inner)

    ok = orig_rebuild(tmp_path, changed_paths=[Path("own.py")])
    assert ok is True

    # First inner call covers our own change set; second is the late-drain
    # pass that picks up "late.py".
    assert len(inner_calls) >= 2
    assert inner_calls[0] == ["own.py"]
    assert inner_calls[1] == ["late.py"]
    # And the queue is now empty (no further late drains).
    assert not (out / watch_mod._PENDING_FILENAME).exists()


def test_rebuild_code_full_corpus_skips_pending_queue(tmp_path, monkeypatch):
    """#1059: changed_paths=None means a full-corpus rebuild — the queue
    must not be touched on the failure path because there is nothing
    incremental to preserve."""
    from graphify import watch as watch_mod
    from graphify.watch import _rebuild_code as orig_rebuild

    out = tmp_path / "graphify-out"
    out.mkdir()

    # Pre-existing queued paths from an earlier incremental hook.
    watch_mod._queue_pending(out, [Path("earlier.py")])

    # Force the inner call to record what it saw.
    seen: list = []

    def fake_inner(watch_path, **kwargs):
        if kwargs.get("acquire_lock") is False:
            seen.append(kwargs.get("changed_paths"))
        return True

    monkeypatch.setattr(watch_mod, "_rebuild_code", fake_inner)

    ok = orig_rebuild(tmp_path, changed_paths=None)
    assert ok is True
    # Full-corpus rebuild passes None to the inner call (does not merge in
    # the queued paths — a full rebuild already covers them).
    assert seen == [None]
    # The queue still gets drained on entry so stale entries don't leak,
    # but no late-arrival loop runs for the full-corpus path.
    assert not (out / watch_mod._PENDING_FILENAME).exists()


def test_merge_changed_paths_dedupes_in_order():
    """_merge_changed_paths preserves first-seen order and drops dupes."""
    from graphify.watch import _merge_changed_paths

    merged = _merge_changed_paths(
        [Path("a.py"), Path("b.py")],
        None,
        [Path("b.py"), Path("c.py")],
        [Path("a.py")],
    )
    assert [p.as_posix() for p in merged] == ["a.py", "b.py", "c.py"]


# --- PR 7: MultiDiGraph keyed parallel-edge eviction + canonical comparison ----
#
# These exercise the incremental-update path of _rebuild_code against an on-disk
# MultiDiGraph graph.json. _rebuild_code's eviction logic (preserved_edges)
# operates on the raw on-disk "links" records BEFORE any graph build, and each
# parallel edge is one record carrying its own `key` + `source_file`, so the
# logic is naturally key-aware. The go/no-go gate: "Incremental update preserves
# and evicts keyed parallel edges intentionally, with no silent fallback to
# simple graph behavior."


def _git_init(path: Path) -> None:
    """Initialise a throwaway git repo so detect() treats `path` as a real corpus."""
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)


def _build_multigraph_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """Create a repo whose graph.json is a MultiDiGraph with two stable endpoints.

    Returns (repo_dir, a_id, b_id). Nodes ``afn``/``bfn`` live in dedicated,
    never-changed files (amod.py / bmod.py) so re-extraction of an edge-
    contributing file does not re-emit or evict them. The edge-contributing
    files (file1.py / file2.py / edgesrc.py) exist as tracked code so detect()
    keeps them in the corpus; parallel A->B edges are injected directly into the
    on-disk "links" so each carries its own `key` + `source_file`.
    """
    from graphify.watch import _rebuild_code

    _git_init(tmp_path)
    (tmp_path / "amod.py").write_text("def afn():\n    return 1\n", encoding="utf-8")
    (tmp_path / "bmod.py").write_text("def bfn():\n    return 2\n", encoding="utf-8")
    (tmp_path / "file1.py").write_text("x1 = 1\n", encoding="utf-8")
    (tmp_path / "file2.py").write_text("x2 = 2\n", encoding="utf-8")
    (tmp_path / "edgesrc.py").write_text("y = 1\n", encoding="utf-8")

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert _rebuild_code(tmp_path, no_cluster=True) is True
    finally:
        os.chdir(cwd)

    graph_path = tmp_path / "graphify-out" / "graph.json"
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    a_id = next(n["id"] for n in data["nodes"] if n.get("label", "").startswith("afn("))
    b_id = next(n["id"] for n in data["nodes"] if n.get("label", "").startswith("bfn("))
    return graph_path, a_id, b_id


def _set_links(graph_path: Path, base_data: dict, a_id: str, b_id: str, edges: list) -> None:
    """Append `edges` (A->B parallel records) and stamp multigraph flags on disk."""
    links = base_data.get("links", base_data.get("edges", []))
    links += edges
    base_data["links"] = links
    base_data["multigraph"] = True
    base_data["directed"] = True
    graph_path.write_text(json.dumps(base_data, indent=2), encoding="utf-8")


def _ab_links(graph_path: Path, a_id: str, b_id: str, source_file: str | None = None) -> list:
    """Return the surviving A->B link records on disk, optionally filtered by source_file."""
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    links = data.get("links", data.get("edges", []))
    out = [e for e in links if e.get("source") == a_id and e.get("target") == b_id]
    if source_file is not None:
        out = [e for e in out if e.get("source_file") == source_file]
    return out


@pytest.mark.skipif(sys.platform == "win32", reason="git CLI behaviour varies on Windows runners")
def test_watch_multigraph_unchanged_file_parallel_edges_persist(tmp_path):
    """A pair with 3 parallel edges from a file that is NOT changed must keep all
    3 across an incremental rebuild triggered by an unrelated file."""
    from graphify.watch import _rebuild_code

    graph_path, a_id, b_id = _build_multigraph_repo(tmp_path)
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    _set_links(
        graph_path,
        data,
        a_id,
        b_id,
        [
            {
                "source": a_id,
                "target": b_id,
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "edgesrc.py",
                "source_location": "L1",
                "key": "k1",
            },
            {
                "source": a_id,
                "target": b_id,
                "relation": "imports",
                "confidence": "EXTRACTED",
                "source_file": "edgesrc.py",
                "source_location": "L2",
                "key": "k2",
            },
            {
                "source": a_id,
                "target": b_id,
                "relation": "references",
                "confidence": "EXTRACTED",
                "source_file": "edgesrc.py",
                "source_location": "L3",
                "key": "k3",
            },
        ],
    )

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        # Change an UNRELATED file; edgesrc.py (the edge contributor) is untouched.
        (tmp_path / "other_change.py").write_text("def newfn():\n    return 0\n", encoding="utf-8")
        assert _rebuild_code(tmp_path, changed_paths=[Path("other_change.py")], no_cluster=True)
    finally:
        os.chdir(cwd)

    survivors = _ab_links(graph_path, a_id, b_id, source_file="edgesrc.py")
    assert len(survivors) == 3, "all 3 parallel edges from the unchanged file must persist"
    assert {e["relation"] for e in survivors} == {"calls", "imports", "references"}


@pytest.mark.skipif(sys.platform == "win32", reason="git CLI behaviour varies on Windows runners")
def test_watch_multigraph_changed_file_evicts_its_parallel_edges(tmp_path):
    """A pair A->B with parallel edges from file1 AND file2; changing file1 must
    evict file1's parallel edges between A->B while file2's survive (keyed,
    per-source_file eviction — no collapse to one-edge-per-pair behaviour)."""
    from graphify.watch import _rebuild_code

    graph_path, a_id, b_id = _build_multigraph_repo(tmp_path)
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    _set_links(
        graph_path,
        data,
        a_id,
        b_id,
        [
            {
                "source": a_id,
                "target": b_id,
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "file1.py",
                "source_location": "L1",
                "key": "k_f1_a",
            },
            {
                "source": a_id,
                "target": b_id,
                "relation": "imports",
                "confidence": "EXTRACTED",
                "source_file": "file1.py",
                "source_location": "L2",
                "key": "k_f1_b",
            },
            {
                "source": a_id,
                "target": b_id,
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "file2.py",
                "source_location": "L9",
                "key": "k_f2_a",
            },
        ],
    )

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        (tmp_path / "file1.py").write_text("x1 = 99\n", encoding="utf-8")
        assert _rebuild_code(tmp_path, changed_paths=[Path("file1.py")], no_cluster=True)
    finally:
        os.chdir(cwd)

    assert _ab_links(graph_path, a_id, b_id, source_file="file1.py") == [], (
        "file1's parallel A->B edges must be evicted when file1 changes"
    )
    file2_survivors = _ab_links(graph_path, a_id, b_id, source_file="file2.py")
    assert len(file2_survivors) == 1, "file2's parallel A->B edge must survive selectively"
    assert file2_survivors[0]["relation"] == "calls"


@pytest.mark.skipif(sys.platform == "win32", reason="git CLI behaviour varies on Windows runners")
def test_watch_multigraph_changed_file_evicts_stale_cross_file_edge(tmp_path):
    """The FIX 3 gap: an edge between two SURVIVING nodes that was CONTRIBUTED by
    the changed file must be evicted. The old endpoints-only check wrongly kept
    it because both A and B (defined in unchanged files) still exist."""
    from graphify.watch import _rebuild_code

    graph_path, a_id, b_id = _build_multigraph_repo(tmp_path)
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    # A single stale cross-file edge contributed by file1.py between A and B,
    # both of which live in amod.py / bmod.py and therefore survive the change.
    _set_links(
        graph_path,
        data,
        a_id,
        b_id,
        [
            {
                "source": a_id,
                "target": b_id,
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "file1.py",
                "source_location": "L1",
                "key": "stale",
            },
        ],
    )

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        (tmp_path / "file1.py").write_text("x1 = 99\n", encoding="utf-8")
        assert _rebuild_code(tmp_path, changed_paths=[Path("file1.py")], no_cluster=True)
    finally:
        os.chdir(cwd)

    assert _ab_links(graph_path, a_id, b_id, source_file="file1.py") == [], (
        "stale cross-file edge contributed by the changed file must be evicted "
        "even though both endpoints survive (FIX 3)"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="git CLI behaviour varies on Windows runners")
def test_watch_multigraph_deleted_file_removes_all_its_edge_records(tmp_path):
    """Deleting a file must remove ALL its edge records, including parallels,
    while leaving another file's parallel between the same pair intact."""
    from graphify.watch import _rebuild_code

    graph_path, a_id, b_id = _build_multigraph_repo(tmp_path)
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    _set_links(
        graph_path,
        data,
        a_id,
        b_id,
        [
            {
                "source": a_id,
                "target": b_id,
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "file1.py",
                "source_location": "L1",
                "key": "d1",
            },
            {
                "source": a_id,
                "target": b_id,
                "relation": "imports",
                "confidence": "EXTRACTED",
                "source_file": "file1.py",
                "source_location": "L2",
                "key": "d2",
            },
            {
                "source": a_id,
                "target": b_id,
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "file2.py",
                "source_location": "L3",
                "key": "keep",
            },
        ],
    )

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        # Delete file1.py and pass it in changed_paths (post-commit-hook style).
        (tmp_path / "file1.py").unlink()
        assert _rebuild_code(tmp_path, changed_paths=[Path("file1.py")], no_cluster=True)
    finally:
        os.chdir(cwd)

    assert _ab_links(graph_path, a_id, b_id, source_file="file1.py") == [], (
        "all of the deleted file's edge records (incl. parallels) must be removed"
    )
    assert len(_ab_links(graph_path, a_id, b_id, source_file="file2.py")) == 1, (
        "the surviving file's parallel edge between the same pair must be kept"
    )


def test_watch_canonical_comparison_distinguishes_parallel_edges():
    """Two multigraphs differing ONLY in a parallel edge's presence must canonical-
    compare as DIFFERENT (FIX 2). Identical multigraphs must compare EQUAL, and
    two parallels that differ ONLY in `key` must stay distinct (key is the
    load-bearing identity field that keeps parallels from collapsing)."""
    from graphify.watch import _canonical_topology_for_compare

    nodes = [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}]
    e1 = {
        "source": "A",
        "target": "B",
        "relation": "calls",
        "source_file": "f1.py",
        "source_location": "L1",
        "key": "k1",
    }
    e2 = {
        "source": "A",
        "target": "B",
        "relation": "calls",
        "source_file": "f1.py",
        "source_location": "L2",
        "key": "k2",
    }
    profile = {"graphify_profile": {"graph_type": "multidigraph"}}

    two = {"nodes": nodes, "links": [dict(e1), dict(e2)], "graph": dict(profile)}
    one = {"nodes": nodes, "links": [dict(e1)], "graph": dict(profile)}
    two_again = {"nodes": nodes, "links": [dict(e1), dict(e2)], "graph": dict(profile)}

    def canon(g: dict) -> str:
        return json.dumps(_canonical_topology_for_compare(g), sort_keys=True)

    assert canon(two) != canon(one), "adding a parallel edge must register as a change"
    assert canon(two) == canon(two_again), "identical multigraphs must compare equal"

    # Two parallels identical in every field EXCEPT key must remain distinct.
    twin_a = {
        "source": "A",
        "target": "B",
        "relation": "calls",
        "source_file": "f1.py",
        "source_location": "L1",
        "key": "ka",
    }
    twin_b = {
        "source": "A",
        "target": "B",
        "relation": "calls",
        "source_file": "f1.py",
        "source_location": "L1",
        "key": "kb",
    }
    twins = {"nodes": nodes, "links": [twin_a, twin_b]}
    canon_twins = _canonical_topology_for_compare(twins)
    assert len(canon_twins["links"]) == 2, "key-only-different parallels must not collapse"
    assert all("key" in e for e in canon_twins["links"]), "canonical edge must retain `key`"
    single_twin = {"nodes": nodes, "links": [dict(twin_a)]}
    assert canon(twins) != canon(single_twin), (
        "removing a key-only-different parallel must register as a change"
    )


def test_watch_simple_mode_unchanged_regression(tmp_path, monkeypatch):
    """Simple-graph watch rebuild behaves as before: a topology-unchanged second
    pass still skips cluster(). Guards the FIX 1 regression (graph-level
    graphify_profile metadata must not be read as a topology change)."""
    from graphify import cluster as cluster_mod
    from graphify.watch import _rebuild_code

    (tmp_path / "app.py").write_text(
        "def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n", encoding="utf-8"
    )

    calls = {"n": 0}

    def cluster_once(G):
        calls["n"] += 1
        if calls["n"] > 1:
            raise AssertionError("cluster() must be skipped when topology is unchanged")
        return {0: sorted(G.nodes())}

    monkeypatch.setattr(cluster_mod, "cluster", cluster_once)
    monkeypatch.setattr(cluster_mod, "score_all", lambda _G, comm: {cid: 1.0 for cid in comm})

    assert _rebuild_code(tmp_path)
    assert _rebuild_code(tmp_path)
    assert calls["n"] == 1, "topology-unchanged simple-graph rebuild must not re-cluster"


@pytest.mark.skipif(sys.platform == "win32", reason="git CLI behaviour varies on Windows runners")
def test_watch_multigraph_full_rebuild_preserves_profile_flag(tmp_path, monkeypatch):
    """Regression for the DEFERRED silent collapse to simple graph.

    A MultiDiGraph graph.json with keyed parallel edges, put through a
    TOPOLOGY-CHANGING rebuild (a new file is added so _rebuild_code does NOT
    early-return on the unchanged-topology check and actually rewrites
    graph.json via to_json), must rewrite a graph.json that still:
      - declares ``multigraph == true`` (the flag load_graph keys on),
      - carries ``graphify_profile.graph_type == "multidigraph"``,
      - keeps the parallel A->B edge records, and
      - reloads via the production loader as a MultiDiGraph with all parallels
        intact (NOT collapsed to one edge per pair).

    Before the inherit-multigraph fix, _rebuild_code built a simple DiGraph, so
    to_json wrote a graph.json with no multigraph flag and a "simple" profile —
    the next load_graph would collapse the preserved parallel links to a single
    edge (the PR 7 go/no-go violation: "no silent fallback to simple graph
    behavior"). This test fails on that regression and passes once _rebuild_code
    inherits the saved multigraph class.
    """
    from graphify.watch import _rebuild_code
    from graphify.graph_loader import load_graph, GRAPHIFY_PROFILE_KEY
    from graphify import cluster as cluster_mod
    import networkx as nx

    monkeypatch.setattr(
        cluster_mod,
        "cluster",
        lambda G: {0: sorted(G.nodes(), key=str)},
    )
    monkeypatch.setattr(cluster_mod, "score_all", lambda _G, comm: {cid: 1.0 for cid in comm})

    graph_path, a_id, b_id = _build_multigraph_repo(tmp_path)
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    # Three keyed parallel A->B edges contributed by amod.py (a file that is NOT
    # changed, so the edges are preserved across the rebuild). amod.py/bmod.py
    # define A/B, so both endpoints survive.
    _set_links(
        graph_path,
        data,
        a_id,
        b_id,
        [
            {
                "source": a_id,
                "target": b_id,
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "amod.py",
                "source_location": "L1",
                "key": "mk1",
            },
            {
                "source": a_id,
                "target": b_id,
                "relation": "imports",
                "confidence": "EXTRACTED",
                "source_file": "amod.py",
                "source_location": "L2",
                "key": "mk2",
            },
            {
                "source": a_id,
                "target": b_id,
                "relation": "references",
                "confidence": "EXTRACTED",
                "source_file": "amod.py",
                "source_location": "L3",
                "key": "mk3",
            },
        ],
    )

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        # Add a NEW file: this changes topology so the rebuild does NOT hit the
        # "no topology change" early return and genuinely rewrites graph.json via
        # the clustered to_json path. no_viz keeps the test fast.
        (tmp_path / "newmod.py").write_text("def newfn():\n    return 9\n", encoding="utf-8")
        assert _rebuild_code(tmp_path, no_viz=True) is True
    finally:
        os.chdir(cwd)

    rewritten = json.loads(graph_path.read_text(encoding="utf-8"))
    # 1. The multigraph flag survived the rewrite.
    assert rewritten.get("multigraph") is True, (
        "rewritten graph.json must keep multigraph=true (else next load collapses parallels)"
    )
    # 2. The multidigraph profile survived (Phase A persists it from the instance).
    profile = (rewritten.get("graph") or {}).get(GRAPHIFY_PROFILE_KEY) or {}
    assert profile.get("graph_type") == "multidigraph", (
        f"rewritten graphify_profile must be multidigraph, got {profile!r}"
    )
    # 3. The parallel edge records are still present (3 A->B records from amod.py).
    ab = _ab_links(graph_path, a_id, b_id, source_file="amod.py")
    assert len(ab) == 3, f"all 3 parallel A->B edge records must persist, got {len(ab)}"
    # 4. The new file's node landed (proves the rebuild actually re-ran, not a no-op).
    new_labels = {n.get("label", "") for n in rewritten.get("nodes", [])}
    assert any(lbl.startswith("newfn(") for lbl in new_labels), (
        "the topology-changing new file must have been extracted into the rewrite"
    )
    # 5. The production loader reloads it as a MultiDiGraph with parallels intact —
    #    the definitive proof there is no deferred collapse to simple.
    reloaded = load_graph(rewritten)
    assert isinstance(reloaded, nx.MultiDiGraph), (
        f"reloaded graph must be a MultiDiGraph, got {type(reloaded).__name__}"
    )
    assert reloaded.number_of_edges(a_id, b_id) == 3, (
        "reloaded MultiDiGraph must keep all 3 parallel A->B edges (NOT collapsed to 1)"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="git CLI behaviour varies on Windows runners")
def test_watch_no_cluster_full_rebuild_does_not_duplicate_links(tmp_path):
    """A full raw rebuild must be idempotent for links.

    The full no-cluster path re-extracts every code file and also preserves
    existing links. Without a dedupe pass, each full rebuild appends another copy
    of the same AST edge records.
    """
    from graphify.watch import _rebuild_code

    (tmp_path / "app.py").write_text(
        "def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n",
        encoding="utf-8",
    )

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
        graph_path = tmp_path / "graphify-out" / "graph.json"
        first = json.loads(graph_path.read_text(encoding="utf-8"))
        first_links = first.get("links", [])

        assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
        second = json.loads(graph_path.read_text(encoding="utf-8"))
    finally:
        os.chdir(cwd)

    second_links = second.get("links", [])
    assert len(second_links) == len(first_links)

    def fingerprint(edge: dict) -> str:
        comparable = dict(edge)
        comparable.pop("key", None)
        comparable.pop("confidence_score", None)
        return json.dumps(comparable, sort_keys=True, ensure_ascii=False)

    assert len({fingerprint(edge) for edge in second_links}) == len(second_links)


@pytest.mark.skipif(sys.platform == "win32", reason="git CLI behaviour varies on Windows runners")
def test_watch_no_cluster_full_rebuild_keeps_distinct_keyed_parallels(tmp_path):
    """Dedupe removes the fresh keyless duplicate, not the keyed parallels."""
    from graphify.watch import _rebuild_code

    (tmp_path / "app.py").write_text(
        "def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n",
        encoding="utf-8",
    )

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
        graph_path = tmp_path / "graphify-out" / "graph.json"
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        base_links = data["links"]
        selected = dict(base_links[0])
        selected_a = dict(selected, key="parallel-a")
        selected_b = dict(selected, key="parallel-b")
        data["links"] = [selected_a, selected_b]
        data["multigraph"] = True
        data["directed"] = True
        graph_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
        rebuilt = json.loads(graph_path.read_text(encoding="utf-8"))
    finally:
        os.chdir(cwd)

    def same_relationship(edge: dict) -> bool:
        comparable = dict(edge)
        comparable.pop("key", None)
        comparable.pop("confidence_score", None)
        expected = dict(selected)
        expected.pop("confidence_score", None)
        return comparable == expected

    matching = [edge for edge in rebuilt["links"] if same_relationship(edge)]
    assert {edge.get("key") for edge in matching} == {"parallel-a", "parallel-b"}
    assert len(matching) == 2


# --- RISK 3: no-cluster compare must not flap on a legacy edges-keyed graph.json ---


def _downgrade_to_legacy_edges(graph_path: Path) -> None:
    """Rewrite ``graph_path`` in the pre-modern on-disk shape that triggered the
    no-cluster flap: the edge list keyed as ``edges`` (not ``links``), a
    ``confidence_score`` stamped on every edge (a recomputed/volatile field), and
    the top-level ``hyperedges`` key dropped entirely (null-vs-[] history).

    All three deviations are required to reproduce the full bug: a fixture that
    only renames ``links``->``edges`` (without injecting ``confidence_score`` and
    without dropping ``hyperedges``) would falsely pass once the key fold lands,
    masking the volatile-field and missing-hyperedges legs of the same flap.
    """
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    links = data.pop("links", data.pop("edges", []))
    data["edges"] = [{**edge, "confidence_score": 0.9} for edge in links]
    data.pop("hyperedges", None)
    graph_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@pytest.mark.skipif(sys.platform == "win32", reason="git CLI behaviour varies on Windows runners")
def test_rebuild_code_no_cluster_does_not_flap_on_legacy_edges_key(tmp_path):
    """RISK 3: a no-op ``--no-cluster`` rebuild over a graph.json written in the
    legacy ``edges``-keyed shape must detect "no change" and leave graph.json
    byte-for-byte untouched (no flap).

    The legacy downgrade renames ``links``->``edges``, stamps a volatile
    ``confidence_score`` on each edge, and drops the top-level ``hyperedges``
    key. ``_canonical_graph_for_compare`` must fold all three back so the
    on-disk legacy graph compares EQUAL to the freshly-extracted candidate;
    otherwise every watcher tick rewrites graph.json forever.
    """
    from graphify.watch import _rebuild_code

    repo = tmp_path / "corpus"
    repo.mkdir()
    _git_init(repo)
    (repo / "app.py").write_text(
        "def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n",
        encoding="utf-8",
    )

    cwd = os.getcwd()
    try:
        os.chdir(repo)
        # Real build to get an authentic no-cluster graph.json for this corpus.
        assert _rebuild_code(repo, no_cluster=True, acquire_lock=False) is True
        graph_path = repo / "graphify-out" / "graph.json"
        assert graph_path.exists()

        # The idempotence requirement is >=3 consecutive no-op rebuilds.  We
        # re-apply the legacy downgrade IMMEDIATELY before each measured run
        # because a buggy _rebuild_code rewrites edges->links on the first
        # flap; without re-downgrading, subsequent runs would compare links vs
        # links and falsely pass (masking the regression).
        #
        # Each run captures its own before-state (mtime + bytes) AFTER the
        # downgrade but BEFORE the sleep+rebuild, then asserts the rebuild
        # leaves the file untouched.  Comparing within each run (not across
        # runs) is correct because _downgrade_to_legacy_edges itself writes the
        # file and therefore changes its mtime — only the rebuild must be a
        # no-op.
        for run_idx in range(3):
            _downgrade_to_legacy_edges(graph_path)
            pre_bytes = graph_path.read_bytes()
            pre_mtime = graph_path.stat().st_mtime_ns

            # No source change — a correct compare must short-circuit to "no change".
            time.sleep(0.01)  # ensure any rewrite would move mtime measurably
            assert _rebuild_code(repo, no_cluster=True, acquire_lock=False) is True

            post_bytes = graph_path.read_bytes()
            post_mtime = graph_path.stat().st_mtime_ns

            assert post_bytes == pre_bytes, (
                f"run {run_idx + 1}: legacy edges-keyed graph.json was rewritten "
                "on a no-op no-cluster rebuild — the canonical compare flapped "
                "(edges->links / confidence_score / missing-hyperedges not folded)"
            )
            assert post_mtime == pre_mtime, (
                f"run {run_idx + 1}: graph.json mtime changed on a no-op rebuild (flap)"
            )
    finally:
        os.chdir(cwd)


# --- RISK 4 Guard 2: a failed/aborted extraction must not wipe a populated graph ---


@pytest.mark.skipif(sys.platform == "win32", reason="git CLI behaviour varies on Windows runners")
def test_watch_no_cluster_delete_all_preserves_graph(tmp_path, monkeypatch):
    """RISK 4: when a declared-deletion rebuild ends with 0 nodes because the
    remaining files' extraction aborted (a failed/half-written extraction, not a
    real empty result), the no-cluster raw-write site must REFUSE to overwrite a
    populated graph.json and preserve the previous graph.

    Reproduction: a two-file corpus is built, ``a.py`` is deleted (declared via
    ``changed_paths`` so ``had_explicit_deletions`` is True and the existing
    shrink guard is bypassed), ``b.py`` stays on disk (so the "no code files"
    early return does NOT fire), and ``extract`` is stubbed to return nothing
    (the aborted extraction). Without the 0-floor the graph is wiped to 0 nodes.
    """
    import graphify.extract as extract_mod
    from graphify.watch import _rebuild_code

    repo = tmp_path / "corpus"
    repo.mkdir()
    _git_init(repo)
    (repo / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (repo / "b.py").write_text("def g():\n    return 2\n", encoding="utf-8")

    cwd = os.getcwd()
    try:
        os.chdir(repo)
        assert _rebuild_code(repo, no_cluster=True, acquire_lock=False) is True
        graph_path = repo / "graphify-out" / "graph.json"
        before = json.loads(graph_path.read_text(encoding="utf-8"))
        nodes_before = len(before.get("nodes", []))
        assert nodes_before > 0
        before_bytes = graph_path.read_bytes()

        # Delete a.py (declared deletion -> had_explicit_deletions=True). Keep
        # b.py on disk so detect() still returns code files, but make extraction
        # abort to empty so the merged candidate has 0 nodes.
        (repo / "a.py").unlink()

        def aborted_extract(_targets, cache_root=None):
            return {
                "nodes": [],
                "edges": [],
                "hyperedges": [],
                "input_tokens": 0,
                "output_tokens": 0,
            }

        monkeypatch.setattr(extract_mod, "extract", aborted_extract)
        result = _rebuild_code(
            repo,
            changed_paths=[Path("a.py"), Path("b.py")],
            no_cluster=True,
            acquire_lock=False,
        )

        after = json.loads(graph_path.read_text(encoding="utf-8"))
        after_bytes = graph_path.read_bytes()
    finally:
        os.chdir(cwd)

    assert result is False, "rebuild must refuse the empty overwrite"
    assert len(after.get("nodes", [])) == nodes_before, (
        "populated graph.json must be preserved when a failed extraction yields 0 nodes"
    )
    assert after_bytes == before_bytes, "graph.json must be byte-for-byte untouched"


@pytest.mark.skipif(sys.platform == "win32", reason="git CLI behaviour varies on Windows runners")
def test_watch_clustered_delete_all_preserves_graph(tmp_path, monkeypatch):
    """RISK 4: the clustered ``tmp.replace`` write site must likewise refuse to
    overwrite a populated graph.json with an empty (0-node) graph produced by a
    failed/aborted extraction during a declared-deletion rebuild.

    Same reproduction as the no-cluster sibling, exercising the clustered path
    (the ``graph_tmp.replace(existing_graph)`` write guarded by ``_check_shrink``).
    """
    import graphify.extract as extract_mod
    from graphify.watch import _rebuild_code

    repo = tmp_path / "corpus"
    repo.mkdir()
    _git_init(repo)
    (repo / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (repo / "b.py").write_text("def g():\n    return 2\n", encoding="utf-8")

    cwd = os.getcwd()
    try:
        os.chdir(repo)
        # no_viz keeps the clustered path fast (skips graph.html generation).
        assert _rebuild_code(repo, no_viz=True, acquire_lock=False) is True
        graph_path = repo / "graphify-out" / "graph.json"
        before = json.loads(graph_path.read_text(encoding="utf-8"))
        nodes_before = len(before.get("nodes", []))
        assert nodes_before > 0
        before_bytes = graph_path.read_bytes()

        (repo / "a.py").unlink()

        def aborted_extract(_targets, cache_root=None):
            return {
                "nodes": [],
                "edges": [],
                "hyperedges": [],
                "input_tokens": 0,
                "output_tokens": 0,
            }

        monkeypatch.setattr(extract_mod, "extract", aborted_extract)
        result = _rebuild_code(
            repo,
            changed_paths=[Path("a.py"), Path("b.py")],
            no_viz=True,
            acquire_lock=False,
        )

        after = json.loads(graph_path.read_text(encoding="utf-8"))
        after_bytes = graph_path.read_bytes()
    finally:
        os.chdir(cwd)

    assert result is False, "clustered rebuild must refuse the empty overwrite"
    assert len(after.get("nodes", [])) == nodes_before, (
        "populated graph.json must be preserved when a failed extraction yields 0 nodes "
        "(clustered path)"
    )
    assert after_bytes == before_bytes, (
        "graph.json must be byte-for-byte untouched (clustered path)"
    )
