"""Tests for watch.py - file watcher helpers (no watchdog required)."""
import json
import os
import sys
import time
from pathlib import Path
import pytest

from graphify.watch import _notify_only, _WATCHED_EXTENSIONS, _rebuild_lock


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
    assert ".tab" in _WATCHED_EXTENSIONS

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
    src.write_text("def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n", encoding="utf-8")

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
    src.write_text("def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n", encoding="utf-8")

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


def test_rebuild_code_changed_tab_keeps_reference_connected_to_preserved_file(tmp_path):
    from graphify.watch import _rebuild_code

    (tmp_path / ".git").mkdir()
    scripts = tmp_path / "scripts" / "ai"
    scripts.mkdir(parents=True)
    target = scripts / "StandardAI.lua"
    target.write_text("function tick() end\n", encoding="utf-8")
    config_dir = tmp_path / "data" / "config"
    config_dir.mkdir(parents=True)
    tab = config_dir / "ai.tab"
    tab.write_text("ID\tScript\n1\tscripts/ai/StandardAI.lua\n", encoding="utf-8")

    assert _rebuild_code(tmp_path, no_cluster=True, force=True)

    tab.write_text(
        "ID\tScript\n"
        "1\tscripts/ai/StandardAI.lua\n"
        "2\tscripts/ai/StandardAI.lua\n",
        encoding="utf-8",
    )
    assert _rebuild_code(tmp_path, changed_paths=[tab], no_cluster=True, force=True)

    graph = json.loads((tmp_path / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    target_ids = {
        n["id"]
        for n in graph["nodes"]
        if n["label"] == "StandardAI.lua" and n["source_file"] == "scripts/ai/StandardAI.lua"
    }
    assert target_ids
    reference_edges = [e for e in graph["links"] if e["relation"] == "references"]
    assert reference_edges
    assert all(e["target"] in target_ids for e in reference_edges)
    assert not any(e.get("target_ref") for e in graph["links"])
    assert not any(
        n["label"] == "StandardAI.lua" and n["source_file"].endswith("ai.tab")
        for n in graph["nodes"]
    )


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
    t = threading.Thread(target=watch_mod.watch, args=(tmp_path,), kwargs={"debounce": 0.2}, daemon=True)
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

    t = threading.Thread(target=watch_mod.watch, args=(tmp_path,), kwargs={"debounce": 0.2}, daemon=True)
    t.start()
    time.sleep(0.5)

    # Generate many events; loader must not be called again.
    for i in range(50):
        (tmp_path / "ignored" / f"f{i}.py").write_text("x\n", encoding="utf-8")
    time.sleep(0.7)
    assert calls["n"] == 1, f"_load_graphifyignore called {calls['n']} times; expected 1"
