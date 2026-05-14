"""Tests for watch.py - file watcher helpers (no watchdog required)."""
import json
import time
from pathlib import Path
import pytest

from graphify.pipeline import merge_update_files, merge_update_payload
from graphify.watch import _notify_only, _WATCHED_EXTENSIONS


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
    assert ".json" not in _WATCHED_EXTENSIONS
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


def test_update_payload_preserves_rich_semantic_label_and_ast_location(tmp_path):
    existing = {
        "nodes": [
            {
                "id": "component_renderer_renderer",
                "label": "App::Presentation::ComponentRenderer",
                "file_type": "code",
                "source_file": "src/presentation/component_renderer.rb",
                "source_location": None,
                "author": None,
                "community": 42,
                "norm_label": "old export field",
            },
        ],
        "links": [],
        "hyperedges": [],
    }
    result = {
        "nodes": [
            {
                "id": "component_renderer_renderer",
                "label": "ComponentRenderer",
                "file_type": "code",
                "source_file": "src/presentation/component_renderer.rb",
                "source_location": "L8",
            },
        ],
        "edges": [],
    }

    merged = merge_update_payload(
        existing,
        result,
        evict_sources=set(),
        rebuilt_sources={"src/presentation/component_renderer.rb"},
        root=tmp_path,
    )

    node = merged["nodes"][0]
    assert node["label"] == "App::Presentation::ComponentRenderer"
    assert node["source_location"] == "L8"
    assert "author" in node
    assert "community" not in node
    assert "norm_label" not in node


def test_update_payload_keeps_existing_source_when_incoming_ids_collide(tmp_path):
    existing = {
        "nodes": [
            {
                "id": "report_report",
                "label": "Presentation::Report",
                "source_file": "src/presentation/report.rb",
                "source_location": None,
            },
        ],
        "links": [],
        "hyperedges": [],
    }
    result = {
        "nodes": [
            {
                "id": "report_report",
                "label": "Report",
                "source_file": "src/services/report.rb",
                "source_location": "L5",
            },
            {
                "id": "report_report",
                "label": "Report",
                "source_file": "src/presentation/report.rb",
                "source_location": "L6",
            },
        ],
        "edges": [],
    }

    merged = merge_update_payload(
        existing,
        result,
        rebuilt_sources={
            "src/services/report.rb",
            "src/presentation/report.rb",
        },
        root=tmp_path,
    )

    assert merged["nodes"] == [
        {
            "id": "report_report",
            "label": "Presentation::Report",
            "source_file": "src/presentation/report.rb",
            "source_location": "L6",
        },
    ]


def test_update_payload_does_not_pair_richer_label_with_different_ast_source(tmp_path):
    existing = {
        "nodes": [
            {
                "id": "report_expire",
                "label": "Domain::Report#expire",
                "source_file": "src/workers/report_expirer.rb",
                "source_location": None,
            },
        ],
        "links": [],
        "hyperedges": [],
    }
    result = {
        "nodes": [
            {
                "id": "report_expire",
                "label": "expire()",
                "source_file": "src/domain/report.rb",
                "source_location": "L29",
            },
        ],
        "edges": [],
    }

    merged = merge_update_payload(
        existing,
        result,
        rebuilt_sources={"src/domain/report.rb"},
        root=tmp_path,
    )

    assert merged["nodes"] == [
        {
            "id": "report_expire",
            "label": "Domain::Report#expire",
            "source_file": "src/workers/report_expirer.rb",
            "source_location": None,
        },
    ]


def test_update_payload_prunes_rebuilt_structural_edges_but_keeps_semantic_edges(tmp_path):
    existing = {
        "nodes": [
            {"id": "caller", "label": "Caller", "source_file": "app/service.rb"},
            {"id": "target", "label": "Target", "source_file": "app/service.rb"},
            {"id": "stale", "label": "Stale", "source_file": "app/old.rb"},
            {"id": "concept", "label": "Concept", "source_file": "README.md"},
        ],
        "links": [
            {
                "source": "caller",
                "target": "target",
                "relation": "calls",
                "context": "call",
                "source_file": "app/service.rb",
                "source_location": "L3",
            },
            {
                "source": "caller",
                "target": "stale",
                "relation": "calls",
                "context": "call",
                "source_file": "app/service.rb",
                "source_location": "L4",
            },
            {
                "source": "caller",
                "target": "concept",
                "relation": "implements",
                "confidence": "INFERRED",
                "source_file": "app/service.rb",
            },
            {
                "source": "caller",
                "target": "concept",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "app/service.rb",
            },
        ],
        "hyperedges": [{"id": "h1", "nodes": ["caller", "concept"]}],
    }
    result = {
        "nodes": [
            {"id": "caller", "label": "Caller", "source_file": "app/service.rb"},
            {"id": "target", "label": "Target", "source_file": "app/service.rb"},
        ],
        "edges": [
            {
                "source": "caller",
                "target": "target",
                "relation": "calls",
                "context": "call",
                "source_file": "app/service.rb",
                "source_location": "L3",
            },
        ],
        "hyperedges": [
            {"id": "h1", "nodes": ["caller", "concept"]},
            {"id": "h2", "nodes": ["caller", "target"]},
        ],
    }

    merged = merge_update_payload(
        existing,
        result,
        evict_sources=set(),
        rebuilt_sources={"app/service.rb"},
        root=tmp_path,
    )

    edge_keys = {(edge["source"], edge["target"], edge["relation"]) for edge in merged["edges"]}
    assert edge_keys == {
        ("caller", "target", "calls"),
        ("caller", "concept", "implements"),
        ("caller", "concept", "calls"),
    }
    assert merged["hyperedges"] == [
        {"id": "h1", "nodes": ["caller", "concept"]},
        {"id": "h2", "nodes": ["caller", "target"]},
    ]


def test_merge_update_files_rewrites_extraction_sidecar(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    graphify_out = tmp_path / "graphify-out"
    graphify_out.mkdir()
    (graphify_out / "graph.json").write_text(
        json.dumps({
            "nodes": [
                {
                    "id": "runner",
                    "label": "App::Runner",
                    "source_file": "runner.py",
                    "source_location": None,
                },
                {"id": "target", "label": "target()", "source_file": "runner.py"},
            ],
            "links": [
                {
                    "source": "runner",
                    "target": "target",
                    "relation": "calls",
                    "context": "call",
                    "source_file": "runner.py",
                    "source_location": "L3",
                },
            ],
        }),
        encoding="utf-8",
    )
    extraction_path = graphify_out / ".graphify_extract.json"
    extraction_path.write_text(
        json.dumps({
            "nodes": [
                {
                    "id": "runner",
                    "label": "Runner",
                    "source_file": "runner.py",
                    "source_location": "L1",
                },
                {"id": "target", "label": "target()", "source_file": "runner.py"},
            ],
            "edges": [],
        }),
        encoding="utf-8",
    )
    (graphify_out / ".graphify_incremental.json").write_text(
        json.dumps({"new_files": {"code": ["runner.py"]}, "deleted_files": []}),
        encoding="utf-8",
    )

    merged, stats = merge_update_files(root=tmp_path)

    assert stats["nodes"] == 2
    assert stats["edges"] == 0
    assert merged["nodes"][0]["label"] == "App::Runner"
    assert merged["nodes"][0]["source_location"] == "L1"
    assert json.loads(extraction_path.read_text(encoding="utf-8")) == merged


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
