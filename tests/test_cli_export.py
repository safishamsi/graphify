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


def test_export_wiki_accepts_edges_only_graph_json(tmp_path):
    out = _make_graph(tmp_path)
    graph_path = out / "graph.json"
    data = json.loads(graph_path.read_text())
    data["edges"] = data.pop("links")
    graph_path.write_text(json.dumps(data))

    r = _run(["export", "wiki"], tmp_path)

    assert r.returncode == 0, r.stderr
    assert (out / "wiki" / "index.md").exists()


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


def test_update_no_cluster_writes_raw_graph(tmp_path):
    src = tmp_path / "sample.py"
    src.write_text("def f():\n    return 1\n", encoding="utf-8")

    r = _run(["update", ".", "--no-cluster"], tmp_path)
    assert r.returncode == 0, r.stderr

    graph_path = tmp_path / "graphify-out" / "graph.json"
    assert graph_path.exists()
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    assert "nodes" in data and "links" in data
    assert all("community" not in node for node in data["nodes"])


# Regression test for #934 - cluster-only crashes when graphify-out/ doesn't exist

def test_cluster_only_creates_output_dir_when_missing(tmp_path):
    """cluster-only must not crash with FileNotFoundError when graphify-out/ is absent (#934)."""
    # Build graph.json somewhere other than the default graphify-out/ location
    # so we can point --graph at it while graphify-out/ doesn't exist yet.
    graph_src = tmp_path / "backup" / "graph.json"
    graph_src.parent.mkdir()

    out_dir = _make_graph(tmp_path)
    graph_json = out_dir / "graph.json"
    # Simulate user archiving the output dir before re-clustering
    import shutil
    shutil.copy(graph_json, graph_src)
    shutil.rmtree(out_dir)

    assert not (tmp_path / "graphify-out").exists()

    r = _run(["cluster-only", ".", "--graph", str(graph_src), "--no-viz"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "graphify-out" / "GRAPH_REPORT.md").exists()


# Regression test for #1027 - cluster-only must remap labels via node overlap

def test_cluster_only_remaps_labels_to_previous_cids(tmp_path):
    """cluster-only must invoke remap_communities_to_previous so the existing
    .graphify_labels.json keeps tracking the same conceptual communities after
    re-clustering. Without the remap call, Leiden's size-descending cid order
    re-applies labels by raw index and they silently misalign with cluster
    contents (#1027). Mirror of the watch/update fix from #822.
    """
    out = _make_graph(tmp_path)
    graph_json = out / "graph.json"
    labels_json = out / ".graphify_labels.json"

    # Tag every node with an out-of-band community id and write a labels file
    # keyed on those ids. After cluster-only, at least one of those sentinel
    # ids must survive in the labels file (= remap succeeded by node overlap).
    # If the cluster-only branch skips remap, Leiden returns small ints
    # (0, 1, ...) and the sentinel keys disappear entirely.
    g = json.loads(graph_json.read_text(encoding="utf-8"))
    nodes = g.get("nodes", [])
    assert len(nodes) >= 4, "fixture must have enough nodes to form 2+ communities"
    sentinel_a, sentinel_b = 4242, 9999
    half = len(nodes) // 2
    for i, n in enumerate(nodes):
        n["community"] = sentinel_a if i < half else sentinel_b
    graph_json.write_text(json.dumps(g), encoding="utf-8")
    labels_json.write_text(
        json.dumps({str(sentinel_a): "First Group", str(sentinel_b): "Second Group"}),
        encoding="utf-8",
    )

    r = _run(["cluster-only", ".", "--no-viz"], tmp_path)
    assert r.returncode == 0, r.stderr

    # Real signal: labels.json keys must align with the community ids actually
    # written to graph.json's per-node community attribute. Without remap,
    # Leiden returns small cids (0, 1, ...) but labels.json still carries the
    # old sentinel keys, so the intersection is empty and labels are orphaned.
    final_graph = json.loads(graph_json.read_text(encoding="utf-8"))
    final_labels = json.loads(labels_json.read_text(encoding="utf-8"))
    actual_cids = {n.get("community") for n in final_graph.get("nodes", [])}
    label_cids = {int(k) for k in final_labels.keys()}
    overlap = actual_cids & label_cids
    assert overlap, (
        f"After cluster-only with prior labels keyed on cids {label_cids}, at "
        f"least one of those cids must still appear in graph.json's community "
        f"attribute ({actual_cids}). Without remap_communities_to_previous "
        f"(#1027) Leiden renumbers communities to 0,1,... and the prior labels "
        f"become orphaned. Final labels: {final_labels}"
    )


# ── communities-fallback when .graphify_analysis.json is absent ──────────────
# The watch / post-commit rebuild path only writes graph.json + GRAPH_REPORT.md;
# it does NOT regenerate .graphify_analysis.json. The full `graphify extract`
# pipeline also removes its temp files at the end of the run on some skill
# workflows. In both cases the per-node `community` attribute is intact on
# every node in graph.json — that's the source of truth `to_json` writes.
# Without these tests, `graphify export html|obsidian|wiki|svg|graphml|neo4j`
# silently bails or generates a degraded artifact whenever the sidecar is
# missing, even though the data is right there.

def test_export_html_falls_back_to_node_community_attribute(tmp_path):
    """When .graphify_analysis.json is absent, export html should reconstruct
    communities from the per-node attribute in graph.json rather than bailing
    out with 'Single community - aggregated view not useful.'.
    """
    out = _make_graph(tmp_path)
    # Simulate the watch-rebuild / cleanup case: graph.json + labels survive,
    # analysis sidecar is gone.
    (out / ".graphify_analysis.json").unlink()

    r = _run(["export", "html"], tmp_path)
    assert r.returncode == 0, r.stderr
    html = out / "graph.html"
    assert html.exists(), "graph.html should be generated from the fallback"
    assert html.stat().st_size > 0
    # The success message comes from to_html — confirm we're not hitting the
    # "Single community" bail-out path.
    assert "Single community" not in r.stdout
    assert "Single community" not in r.stderr


def test_export_html_fallback_recovers_multiple_communities(tmp_path):
    """Stronger assertion: the reconstructed `communities` dict should have the
    SAME community count as the analysis sidecar would, so downstream code
    (aggregation thresholds, member counts) sees identical input.
    """
    out = _make_graph(tmp_path)

    # Read the canonical community count from the analysis sidecar
    analysis = json.loads((out / ".graphify_analysis.json").read_text(encoding="utf-8"))
    expected_count = len(analysis["communities"])

    # And the count we'd reconstruct from graph.json's node attributes
    graph = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    reconstructed_cids = {
        n["community"] for n in graph.get("nodes", [])
        if n.get("community") is not None
    }
    assert len(reconstructed_cids) == expected_count, (
        f"reconstruction would lose communities: sidecar={expected_count} vs "
        f"graph.json={len(reconstructed_cids)}"
    )

    # Now remove the sidecar and confirm the CLI still succeeds end-to-end.
    (out / ".graphify_analysis.json").unlink()
    r = _run(["export", "html"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert (out / "graph.html").exists()


def test_export_html_no_community_data_at_all_still_succeeds(tmp_path):
    """If a graph.json was somehow written without any per-node `community`
    attribute (older versions of to_json, hand-built graphs), the fallback
    should produce an empty communities dict and the renderer should still
    not crash. Whether the aggregated view is useful is a separate question.
    """
    out = _make_graph(tmp_path)
    (out / ".graphify_analysis.json").unlink()

    # Strip the community attribute from every node
    graph_path = out / "graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    for n in graph.get("nodes", []):
        n.pop("community", None)
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    r = _run(["export", "html"], tmp_path)
    # Should NOT crash. It may print a warning and skip rendering, but exit
    # code stays clean — same behaviour as the pre-fallback empty-communities
    # path, just no longer silently failing on the common case.
    assert r.returncode == 0, r.stderr
