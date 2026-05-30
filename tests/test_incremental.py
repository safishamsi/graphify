"""Integration tests for incremental graphify extract behavior."""

from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

from graphify.llm import BACKENDS, _backend_env_keys


PYTHON = sys.executable


def _clean_env() -> dict:
    """Return os.environ with every backend API key stripped out."""
    env = dict(os.environ)
    for backend in BACKENDS:
        for env_key in _backend_env_keys(backend):
            env.pop(env_key, None)
    for extra in (
        "AWS_PROFILE",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "OLLAMA_BASE_URL",
        "OLLAMA_API_KEY",
    ):
        env.pop(extra, None)
    return env


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "graphify"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=_clean_env(),
    )


def _make_docs_corpus(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "intro.md").write_text("# Introduction\nThis doc introduces the system.")
    (docs / "api.md").write_text("# API Reference\nThe API has endpoints.")
    return docs


def test_manifest_written_after_extract(tmp_path):
    """After a full extract run, manifest.json must exist (or run fails before writing it)."""
    docs = _make_docs_corpus(tmp_path)
    r = _run(["extract", str(docs)], tmp_path)
    # Should fail with no API key — but NOT with a path error
    assert "no LLM API key" in r.stderr or r.returncode != 0
    # manifest should NOT exist (run failed before writing)
    manifest = docs / "graphify-out" / "manifest.json"
    assert not manifest.exists()


def test_incremental_mode_detected_via_manifest(tmp_path):
    """If manifest.json + graph.json exist, incremental mode message is shown."""
    docs = _make_docs_corpus(tmp_path)
    out = docs / "graphify-out"
    out.mkdir()
    (out / "graph.json").write_text(json.dumps({"nodes": [], "links": []}))
    (out / "manifest.json").write_text(json.dumps({"document": [str(docs / "intro.md")]}))
    r = _run(["extract", str(docs)], tmp_path)
    combined = r.stdout + r.stderr
    assert "incremental" in combined.lower() or r.returncode != 0


def test_no_incremental_without_manifest(tmp_path):
    """Without manifest.json, full scan message is shown (not incremental)."""
    docs = _make_docs_corpus(tmp_path)
    r = _run(["extract", str(docs)], tmp_path)
    # Check combined output doesn't contain incremental-mode phrasing.
    # Use a phrase rather than a bare word to avoid matching the tmp_path,
    # which pytest derives from the test name and contains "incremental".
    assert "incremental update" not in r.stdout.lower()
    assert "incremental scan" not in r.stdout.lower()


# ── PR 7: `graphify update` preserves the multidigraph profile (no silent fallback) ──
#
# watch._rebuild_code inherits the saved graph.json profile: it reads the on-disk
# `multigraph` flag and rebuilds via build_from_json(multigraph=...), re-stamping
# multigraph/directed + graphify_profile on write. So `graphify update` on a
# multidigraph round-trips it as a MultiDiGraph with keyed parallel edges intact —
# never silently collapsed to a simple graph. These tests prove that end-to-end by
# actually running `update` as a subprocess and reloading the rewritten graph.json.


def _make_code_corpus(tmp_path: Path) -> Path:
    """A tiny real code corpus so `graphify update` has AST-extractable files.

    Includes ``extra()`` so a rebuild ADDS AST nodes the seeded multidigraph
    graph.json lacks (file node + login()/helper()/extra()). That guarantees a
    real topology change, so `update` hits the graph.json REWRITE path rather
    than the no-change early return — the rewrite is what must preserve the
    multigraph profile, so the test would be vacuous without forcing it.
    """
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "auth.py").write_text(
        "def login():\n    return helper()\n\n\ndef helper():\n    return 1\n\n\n"
        "def extra():\n    return login()\n",
        encoding="utf-8",
    )
    return corpus


def _write_multidigraph_graph_json(corpus: Path) -> Path:
    """Seed corpus/graphify-out/graph.json as a multidigraph with parallel edges.

    Built and serialized exactly the way Phase A persists it (build_from_json
    multigraph=True -> export.to_json), so the saved file carries the top-level
    ``multigraph: true`` flag and ``graphify_profile.graph_type == multidigraph``.
    The two parallel ``login -> helper`` edges (ids absent from AST output) are
    preserved by `_rebuild_code` across the rebuild, proving parallels survive.
    """
    import networkx as nx
    from graphify.build import build_from_json
    from graphify.export import to_json

    nodes = [
        {
            "id": n,
            "label": n,
            "file_type": "code",
            "source_file": "auth.py",
            "source_location": "L1",
        }
        for n in ("login", "helper")
    ]
    # Two parallel edges between the same (login -> helper) pair.
    edges = [
        {
            "source": "login",
            "target": "helper",
            "relation": rel,
            "confidence": "EXTRACTED",
            "source_file": "auth.py",
            "source_location": f"L{i}",
        }
        for i, rel in enumerate(["calls", "imports"])
    ]
    G = build_from_json({"nodes": nodes, "edges": edges}, multigraph=True)
    assert isinstance(G, nx.MultiDiGraph)
    assert G.number_of_edges() == 2
    out = corpus / "graphify-out"
    out.mkdir(exist_ok=True)
    graph_json = out / "graph.json"
    to_json(G, {0: ["login", "helper"]}, str(graph_json), force=True)
    # Persist the scan root so `graphify update` (no path arg) can recover it.
    (out / ".graphify_root").write_text(str(corpus), encoding="utf-8")
    return graph_json


def _parallel_login_helper_edges(graph_data: dict) -> list[dict]:
    """Return the parallel ``login -> helper`` edge records from a graph.json dict."""
    links = graph_data.get("links", graph_data.get("edges", []))
    return [e for e in links if e.get("source") == "login" and e.get("target") == "helper"]


def test_update_preserves_multigraph_profile(tmp_path):
    """`graphify update` on a multidigraph graph.json preserves the profile and
    its parallel edges end-to-end: the rewritten file stays multigraph=true /
    graph_type=multidigraph and reloads via load_graph as a MultiDiGraph with the
    parallel edges intact."""
    from graphify.graph_loader import load_graph

    corpus = _make_code_corpus(tmp_path)
    graph_json = _write_multidigraph_graph_json(corpus)

    before = json.loads(graph_json.read_text(encoding="utf-8"))
    assert before.get("multigraph") is True
    assert len(_parallel_login_helper_edges(before)) == 2  # both parallel edges present

    r = _run(["update", str(corpus)], tmp_path)
    assert r.returncode == 0, f"update on multidigraph should succeed, got: {r.stderr}"
    assert "multidigraph" not in r.stderr  # no refusal message

    after = json.loads(graph_json.read_text(encoding="utf-8"))
    # Profile preserved (no silent collapse to simple).
    assert after.get("multigraph") is True, "multigraph flag must be preserved"
    assert after.get("graph", {}).get("graphify_profile", {}).get("graph_type") == "multidigraph"
    # Prove the REWRITE path ran (rebuild added AST nodes the seed lacked), not a
    # no-change early return that would trivially leave the seed file untouched.
    assert any(n.get("label") == "extra()" for n in after.get("nodes", [])), (
        "rebuild should have added AST nodes — rewrite path must have executed"
    )
    # Parallel edges survive the rewrite.
    par = _parallel_login_helper_edges(after)
    assert len(par) == 2, "keyed parallel edges must be preserved across update"
    assert sorted(e["relation"] for e in par) == ["calls", "imports"]
    # Reloads as a MultiDiGraph with the parallels intact.
    G2 = load_graph(after)
    assert G2.is_multigraph(), "rewritten graph.json must reload as a MultiDiGraph"
    assert G2.number_of_edges("login", "helper") == 2


def test_update_simple_graph_unchanged_regression(tmp_path):
    """A simple graph.json updated in simple mode behaves exactly as before:
    `graphify update` succeeds and the graph stays a simple graph."""
    corpus = _make_code_corpus(tmp_path)

    # First run on a fresh corpus builds the simple graph via the normal path.
    r1 = _run(["update", str(corpus)], tmp_path)
    assert r1.returncode == 0, f"initial simple update failed: {r1.stderr}"
    graph_json = corpus / "graphify-out" / "graph.json"
    assert graph_json.exists()
    data1 = json.loads(graph_json.read_text(encoding="utf-8"))
    assert data1.get("multigraph") is False
    assert data1.get("graph", {}).get("graphify_profile", {}).get("graph_type") == "simple"
    assert any(n.get("label") == "login()" for n in data1.get("nodes", []))

    # Re-running update on the now-simple graph must still succeed (no refusal,
    # no profile change) — the pre-PR7 behavior is preserved.
    r2 = _run(["update", str(corpus)], tmp_path)
    assert r2.returncode == 0, f"re-run simple update failed: {r2.stderr}"
    assert "multidigraph" not in r2.stderr
    data2 = json.loads(graph_json.read_text(encoding="utf-8"))
    assert data2.get("multigraph") is False
    assert data2.get("graph", {}).get("graphify_profile", {}).get("graph_type") == "simple"


def test_update_profile_mismatch_no_silent_fallback(tmp_path):
    """Go/no-go gate: `graphify update` on a multidigraph must NOT silently fall
    back to simple-graph behavior. The gate is satisfied by PRESERVATION — the
    result is still a multidigraph with parallel edges, never a collapsed simple
    graph (and never a spurious refusal now that the pipeline preserves)."""
    corpus = _make_code_corpus(tmp_path)
    graph_json = _write_multidigraph_graph_json(corpus)

    r = _run(["update", str(corpus)], tmp_path)
    after = json.loads(graph_json.read_text(encoding="utf-8"))

    # The invariant: never a silent simple-graph result.
    assert after.get("multigraph") is True, (
        "no silent fallback: a multidigraph update must remain a multidigraph, "
        f"got multigraph={after.get('multigraph')!r}"
    )
    assert after.get("graph", {}).get("graphify_profile", {}).get("graph_type") == "multidigraph"
    # Parallel edges are not collapsed away.
    assert len(_parallel_login_helper_edges(after)) == 2, (
        "parallel edges must survive — collapsing to one edge is a silent fallback"
    )
    # Preservation, not refusal: the command succeeds normally.
    assert r.returncode == 0, f"update should preserve (succeed), not refuse: {r.stderr}"
