"""Integration tests for graphify export subcommands and CLI commands.

Each test builds a minimal graph in a temp dir, runs the CLI command as a subprocess,
and asserts the expected output file exists and is non-empty / valid.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PYTHON = sys.executable
FIXTURES = Path(__file__).parent / "fixtures"


def _run(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "graphify"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def _make_graph(tmp_path: Path) -> Path:
    """Build a minimal graph.json + analysis/labels files in tmp_path/graphify-out/."""
    out = tmp_path / "graphify-out"
    out.mkdir()

    extraction = json.loads((FIXTURES / "extraction.json").read_text())
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections
    from graphify.export import to_json

    G = build_from_json(extraction)
    communities = cluster(G)
    cohesion = score_all(G, communities)
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    labels = {cid: f"Community {cid}" for cid in communities}

    to_json(G, communities, str(out / "graph.json"))

    analysis = {
        "communities": {str(k): v for k, v in communities.items()},
        "cohesion": {str(k): v for k, v in cohesion.items()},
        "gods": gods,
        "surprises": surprises,
    }
    (out / ".graphify_analysis.json").write_text(json.dumps(analysis))
    (out / ".graphify_labels.json").write_text(
        json.dumps({str(k): v for k, v in labels.items()})
    )
    return out


# ── graphify export html ─────────────────────────────────────────────────────

def test_export_html_creates_file(tmp_path):
    _make_graph(tmp_path)
    r = _run(["export", "html"], tmp_path)
    assert r.returncode == 0, r.stderr
    html = tmp_path / "graphify-out" / "graph.html"
    assert html.exists()
    assert html.stat().st_size > 0


def test_export_html_no_viz_removes_file(tmp_path):
    out = _make_graph(tmp_path)
    (out / "graph.html").write_text("<html/>")
    r = _run(["export", "html", "--no-viz"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert not (out / "graph.html").exists()


def test_export_html_error_without_graph(tmp_path):
    r = _run(["export", "html"], tmp_path)
    assert r.returncode != 0


# ── graphify export obsidian ─────────────────────────────────────────────────

def test_export_obsidian_creates_vault(tmp_path):
    _make_graph(tmp_path)
    r = _run(["export", "obsidian"], tmp_path)
    assert r.returncode == 0, r.stderr
    vault = tmp_path / "graphify-out" / "obsidian"
    assert vault.exists()
    md_files = list(vault.glob("*.md"))
    assert len(md_files) > 0


def test_export_obsidian_custom_dir(tmp_path):
    _make_graph(tmp_path)
    custom = tmp_path / "my-vault"
    r = _run(["export", "obsidian", "--dir", str(custom)], tmp_path)
    assert r.returncode == 0, r.stderr
    assert custom.exists()
    assert len(list(custom.glob("*.md"))) > 0


# ── graphify export wiki ─────────────────────────────────────────────────────

def test_export_wiki_creates_articles(tmp_path):
    _make_graph(tmp_path)
    r = _run(["export", "wiki"], tmp_path)
    assert r.returncode == 0, r.stderr
    wiki = tmp_path / "graphify-out" / "wiki"
    assert wiki.exists()
    assert (wiki / "index.md").exists()


# ── graphify export graphml ──────────────────────────────────────────────────

def test_export_graphml_creates_file(tmp_path):
    _make_graph(tmp_path)
    r = _run(["export", "graphml"], tmp_path)
    assert r.returncode == 0, r.stderr
    gml = tmp_path / "graphify-out" / "graph.graphml"
    assert gml.exists()
    assert gml.stat().st_size > 0
    content = gml.read_text()
    assert "<graphml" in content


# ── graphify export neo4j (cypher) ───────────────────────────────────────────

def test_export_neo4j_creates_cypher(tmp_path):
    _make_graph(tmp_path)
    r = _run(["export", "neo4j"], tmp_path)
    assert r.returncode == 0, r.stderr
    cypher = tmp_path / "graphify-out" / "cypher.txt"
    assert cypher.exists()
    assert cypher.stat().st_size > 0
    content = cypher.read_text()
    assert "MERGE" in content or "CREATE" in content


# ── graphify query ───────────────────────────────────────────────────────────

def test_query_returns_output(tmp_path):
    _make_graph(tmp_path)
    r = _run(["query", "test"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert len(r.stdout) > 0


def test_query_dfs_flag(tmp_path):
    _make_graph(tmp_path)
    r = _run(["query", "test", "--dfs"], tmp_path)
    assert r.returncode == 0, r.stderr


def test_query_budget_flag(tmp_path):
    _make_graph(tmp_path)
    r = _run(["query", "test", "--budget", "500"], tmp_path)
    assert r.returncode == 0, r.stderr


def test_query_missing_graph_fails(tmp_path):
    r = _run(["query", "anything"], tmp_path)
    assert r.returncode != 0


def test_query_uses_graphify_out_env(tmp_path):
    out = _make_graph(tmp_path)
    custom_out = tmp_path / "custom-graph"
    out.rename(custom_out)
    env = os.environ.copy()
    env["GRAPHIFY_OUT"] = custom_out.name

    r = _run(["query", "test"], tmp_path, env=env)

    assert r.returncode == 0, r.stderr
    assert len(r.stdout) > 0


# ── graphify path ────────────────────────────────────────────────────────────

def test_path_runs_without_error(tmp_path):
    _make_graph(tmp_path)
    r = _run(["path", "Transformer", "LayerNorm"], tmp_path)
    # May find or not find a path — either is valid, should not crash
    assert r.returncode == 0, r.stderr


def test_path_missing_graph_fails(tmp_path):
    r = _run(["path", "a", "b"], tmp_path)
    assert r.returncode != 0


def test_path_uses_graphify_out_env(tmp_path):
    out = _make_graph(tmp_path)
    custom_out = tmp_path / "custom-graph"
    out.rename(custom_out)
    env = os.environ.copy()
    env["GRAPHIFY_OUT"] = custom_out.name

    r = _run(["path", "Transformer", "LayerNorm"], tmp_path, env=env)

    assert r.returncode == 0, r.stderr


# ── graphify explain ─────────────────────────────────────────────────────────

def test_explain_runs_without_error(tmp_path):
    _make_graph(tmp_path)
    r = _run(["explain", "test"], tmp_path)
    assert r.returncode == 0, r.stderr


def test_explain_missing_graph_fails(tmp_path):
    r = _run(["explain", "anything"], tmp_path)
    assert r.returncode != 0


def test_explain_uses_graphify_out_env(tmp_path):
    out = _make_graph(tmp_path)
    custom_out = tmp_path / "custom-graph"
    out.rename(custom_out)
    env = os.environ.copy()
    env["GRAPHIFY_OUT"] = custom_out.name

    r = _run(["explain", "test"], tmp_path, env=env)

    assert r.returncode == 0, r.stderr


# ── graphify export unknown format ───────────────────────────────────────────

def test_export_unknown_format_fails(tmp_path):
    r = _run(["export", "pdf"], tmp_path)
    assert r.returncode != 0
