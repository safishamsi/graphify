"""Integration tests for graphify export subcommands and CLI commands.

Each test builds a minimal graph in a temp dir, runs the CLI command as a subprocess,
and asserts the expected output file exists and is non-empty / valid.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

import pytest

PYTHON = sys.executable
FIXTURES = Path(__file__).parent / "fixtures"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "graphify"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
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


# ── graphify export hugegraph ─────────────────────────────────────────────────

def test_export_hugegraph_creates_files(tmp_path):
    _make_graph(tmp_path)
    r = _run(["export", "hugegraph"], tmp_path)
    assert r.returncode == 0, r.stderr
    out = tmp_path / "graphify-out" / "hugegraph"
    assert (out / "hugegraph_vertices.json").exists()
    assert (out / "hugegraph_edges.json").exists()
    assert (out / "schema.groovy").exists()
    assert (out / "struct.json").exists()
    loader = out / "loader"
    assert loader.exists()
    # At least one per-label vertex file and one per-label edge file
    assert len(list(loader.glob("vertices_*.json"))) > 0
    assert len(list(loader.glob("edges_*.json"))) > 0


def test_export_hugegraph_vertices_schema(tmp_path):
    _make_graph(tmp_path)
    _run(["export", "hugegraph"], tmp_path)
    out = tmp_path / "graphify-out" / "hugegraph"
    vertices = json.loads((out / "hugegraph_vertices.json").read_text())
    assert isinstance(vertices, list)
    assert len(vertices) > 0
    v = vertices[0]
    assert "label" in v
    assert "properties" in v
    assert "id" in v["properties"]
    assert "label" in v["properties"]


def test_export_hugegraph_edges_schema(tmp_path):
    _make_graph(tmp_path)
    _run(["export", "hugegraph"], tmp_path)
    out = tmp_path / "graphify-out" / "hugegraph"
    edges = json.loads((out / "hugegraph_edges.json").read_text())
    assert isinstance(edges, list)
    if edges:
        e = edges[0]
        assert "label" in e
        assert "outV" in e
        assert "inV" in e
        assert "properties" in e
        assert "confidence" in e["properties"]
        assert "edge_label" in e["properties"]


def test_export_hugegraph_schema_groovy(tmp_path):
    _make_graph(tmp_path)
    _run(["export", "hugegraph"], tmp_path)
    groovy = (tmp_path / "graphify-out" / "hugegraph" / "schema.groovy").read_text()
    assert "schema.propertyKey" in groovy
    assert "schema.vertexLabel" in groovy
    assert "schema.edgeLabel" in groovy
    assert ".primaryKeys(" in groovy
    assert ".ifNotExist().create()" in groovy
    assert 'schema.propertyKey("edge_label")' in groovy
    assert '.properties("confidence","confidence_score","weight","edge_label")' in groovy


def test_export_hugegraph_struct_json(tmp_path):
    _make_graph(tmp_path)
    _run(["export", "hugegraph"], tmp_path)
    struct = json.loads((tmp_path / "graphify-out" / "hugegraph" / "struct.json").read_text())
    assert "vertices" in struct
    assert "edges" in struct
    assert len(struct["vertices"]) > 0
    sv = struct["vertices"][0]
    assert "label" in sv
    assert "input" in sv
    assert sv["input"]["format"] == "JSON"
    if struct["edges"]:
        se = struct["edges"][0]
        assert "source" in se
        assert "target" in se
        assert "field_mapping" in se


def test_export_hugegraph_loader_ndjson(tmp_path):
    _make_graph(tmp_path)
    _run(["export", "hugegraph"], tmp_path)
    loader = tmp_path / "graphify-out" / "hugegraph" / "loader"
    # Vertex NDJSON: each line must be valid JSON with "id" and "name"
    for vfile in loader.glob("vertices_*.json"):
        for line in vfile.read_text().splitlines():
            if line.strip():
                obj = json.loads(line)
                assert "id" in obj
                assert "name" in obj
    # Edge NDJSON: one file per label, each line must have out_id and in_id
    edge_files = list(loader.glob("edges_*.json"))
    assert len(edge_files) > 0
    for efile in edge_files:
        for line in efile.read_text().splitlines():
            if line.strip():
                obj = json.loads(line)
                assert "out_id" in obj
                assert "in_id" in obj
                assert "edge_label" in obj


def test_export_hugegraph_missing_graph_fails(tmp_path):
    r = _run(["export", "hugegraph"], tmp_path)
    assert r.returncode != 0


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


# ── graphify path ────────────────────────────────────────────────────────────

def test_path_runs_without_error(tmp_path):
    _make_graph(tmp_path)
    r = _run(["path", "Transformer", "LayerNorm"], tmp_path)
    # May find or not find a path — either is valid, should not crash
    assert r.returncode == 0, r.stderr


def test_path_missing_graph_fails(tmp_path):
    r = _run(["path", "a", "b"], tmp_path)
    assert r.returncode != 0


# ── graphify explain ─────────────────────────────────────────────────────────

def test_explain_runs_without_error(tmp_path):
    _make_graph(tmp_path)
    r = _run(["explain", "test"], tmp_path)
    assert r.returncode == 0, r.stderr


def test_explain_missing_graph_fails(tmp_path):
    r = _run(["explain", "anything"], tmp_path)
    assert r.returncode != 0


# ── graphify export unknown format ───────────────────────────────────────────

def test_export_unknown_format_fails(tmp_path):
    r = _run(["export", "pdf"], tmp_path)
    assert r.returncode != 0
