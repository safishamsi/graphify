"""Tests for `graphify extract` CLI dispatch path in graphify.__main__."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import networkx as nx
import pytest

import graphify.__main__ as mainmod
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.graph_loader import load_graph
from graphify.llm import BACKENDS, _backend_env_keys


PYTHON = sys.executable


def _clean_env() -> dict:
    """Return os.environ with every backend API key stripped out.

    Mirrors tests/test_incremental._clean_env so subprocess runs do not pick up
    a real key from the developer's shell and accidentally hit a live LLM.
    """
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


def _run(args: list[str], cwd: Path, *, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run `python -m graphify <args>` as a sanitized subprocess."""
    return subprocess.run(
        [PYTHON, "-m", "graphify"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env if env is not None else _clean_env(),
    )


def _make_code_corpus(tmp_path: Path) -> Path:
    """A tiny AST-only code corpus — no docs, so semantic/LLM extraction never runs.

    The functions reference each other so AST extraction produces real edges.
    """
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "app.py").write_text(
        "def helper():\n    return 1\n\n\n"
        "def main():\n    return helper()\n\n\n"
        "def extra():\n    return main()\n",
        encoding="utf-8",
    )
    return corpus


def _write_multidigraph_graph_json(corpus: Path) -> Path:
    """Seed corpus/graphify-out/graph.json as a multidigraph with parallel edges.

    Built exactly the way the pipeline persists it (build_from_json multigraph=True
    -> export.to_json), so the file carries the top-level ``multigraph: true`` flag
    and ``graphify_profile.graph_type == multidigraph``. Two parallel main->helper
    edges (different relations) prove parallels survive a sticky re-extract.
    """
    nodes = [
        {
            "id": n,
            "label": f"{n}()",
            "file_type": "code",
            "source_file": "app.py",
            "source_location": "L1",
        }
        for n in ("main", "helper")
    ]
    edges = [
        {
            "source": "main",
            "target": "helper",
            "relation": rel,
            "confidence": "EXTRACTED",
            "source_file": "app.py",
            "source_location": f"L{i}",
        }
        for i, rel in enumerate(["calls", "imports"])
    ]
    G = build_from_json({"nodes": nodes, "edges": edges}, multigraph=True)
    assert isinstance(G, nx.MultiDiGraph)
    assert G.number_of_edges("main", "helper") == 2
    out = corpus / "graphify-out"
    out.mkdir(exist_ok=True)
    graph_json = out / "graph.json"
    to_json(G, {0: ["main", "helper"]}, str(graph_json), force=True)
    # Persist the scan root so a later `update` (no path arg) can recover it.
    (out / ".graphify_root").write_text(str(corpus), encoding="utf-8")
    return graph_json


def _graph_type(graph_data: dict) -> str | None:
    return graph_data.get("graph", {}).get("graphify_profile", {}).get("graph_type")


def _parallel_edges(graph_data: dict, src: str, tgt: str) -> list[dict]:
    links = graph_data.get("links", graph_data.get("edges", []))
    return [e for e in links if e.get("source") == src and e.get("target") == tgt]


# ───────────────────────────── PR 9: public --multigraph / --simple ─────────────
#
# extract exposes the MultiDiGraph build publicly. Default is STICKY: a default
# re-extract inherits the existing graph.json profile (a multigraph stays a
# multigraph). --multigraph forces a keyed MultiDiGraph; --simple is the explicit,
# warned, lossy downgrade. Capability failures surface as a clean CLI error.


def test_extract_simple_default(tmp_path):
    """No flag on a fresh corpus → a simple graph (historical behavior).

    A fresh corpus has no existing graph.json to inherit, so the sticky default
    collapses to the historical simple build: multigraph:false / graph_type simple.
    """
    corpus = _make_code_corpus(tmp_path)
    env = _clean_env()
    env["ANTHROPIC_API_KEY"] = "sk-test-fake-key"  # code-only corpus never calls the LLM
    r = _run(["extract", str(corpus), "--backend", "claude"], tmp_path, env=env)
    assert r.returncode == 0, f"fresh simple extract should succeed: {r.stderr}"

    graph_json = corpus / "graphify-out" / "graph.json"
    assert graph_json.exists(), f"graph.json must be written: {r.stderr}"
    data = json.loads(graph_json.read_text(encoding="utf-8"))
    assert data.get("multigraph") is False, "default fresh build must be a simple graph"
    assert _graph_type(data) == "simple"


def test_extract_multigraph_flag(tmp_path):
    """`extract --multigraph` → graph.json is a keyed MultiDiGraph.

    Real end-to-end CLI subprocess: multigraph:true + graphify_profile.graph_type
    == "multidigraph", and it reloads as an actual nx.MultiDiGraph.
    """
    corpus = _make_code_corpus(tmp_path)
    env = _clean_env()
    env["ANTHROPIC_API_KEY"] = "sk-test-fake-key"
    r = _run(["extract", str(corpus), "--backend", "claude", "--multigraph"], tmp_path, env=env)
    assert r.returncode == 0, f"extract --multigraph should succeed: {r.stderr}"

    graph_json = corpus / "graphify-out" / "graph.json"
    data = json.loads(graph_json.read_text(encoding="utf-8"))
    assert data.get("multigraph") is True, "--multigraph must produce a multigraph graph.json"
    assert data.get("directed") is True, "a MultiDiGraph is always directed"
    assert _graph_type(data) == "multidigraph"
    # Reloads as a real MultiDiGraph.
    G = load_graph(data)
    assert G.is_multigraph(), "graph.json must reload as a MultiDiGraph"


def test_extract_multigraph_then_update_sticky(tmp_path):
    """`extract --multigraph`, then default re-extract/update STAYS multigraph.

    The second build is run WITHOUT any flag 3 times in a row; the profile must
    stay multidigraph each time (idempotence-under-repeat), with the keyed
    parallel-edge capability intact — never a silent collapse to simple.
    """
    corpus = _make_code_corpus(tmp_path)
    env = _clean_env()
    env["ANTHROPIC_API_KEY"] = "sk-test-fake-key"

    r0 = _run(["extract", str(corpus), "--backend", "claude", "--multigraph"], tmp_path, env=env)
    assert r0.returncode == 0, f"initial --multigraph extract failed: {r0.stderr}"
    graph_json = corpus / "graphify-out" / "graph.json"

    # Seed two parallel main->helper edges so we can prove parallels persist.
    _write_multidigraph_graph_json(corpus)
    seeded = json.loads(graph_json.read_text(encoding="utf-8"))
    assert seeded.get("multigraph") is True
    assert len(_parallel_edges(seeded, "main", "helper")) == 2

    # Default re-extract (NO flag) 3×; sticky must keep it multigraph every time.
    for attempt in range(1, 4):
        r = _run(["extract", str(corpus), "--backend", "claude"], tmp_path, env=env)
        assert r.returncode == 0, f"sticky re-extract #{attempt} failed: {r.stderr}"
        data = json.loads(graph_json.read_text(encoding="utf-8"))
        assert data.get("multigraph") is True, (
            f"re-extract #{attempt} must STAY multigraph (sticky), "
            f"got multigraph={data.get('multigraph')!r}"
        )
        assert _graph_type(data) == "multidigraph", f"re-extract #{attempt} profile drifted"
        # Parallel edges are not collapsed away by the sticky rebuild.
        par = _parallel_edges(data, "main", "helper")
        assert len(par) == 2, f"re-extract #{attempt} must preserve keyed parallel edges"
        assert sorted(e["relation"] for e in par) == ["calls", "imports"]
        # Reloads as a MultiDiGraph with the parallels intact.
        G = load_graph(data)
        assert G.is_multigraph()
        assert G.number_of_edges("main", "helper") == 2

    # A default `update` (the watch entrypoint) also stays multigraph.
    ru = _run(["update", str(corpus)], tmp_path, env=env)
    assert ru.returncode == 0, f"sticky update failed: {ru.stderr}"
    after_update = json.loads(graph_json.read_text(encoding="utf-8"))
    assert after_update.get("multigraph") is True, "update must inherit the multigraph profile"
    assert _graph_type(after_update) == "multidigraph"


def test_extract_multigraph_no_cluster_sticky_idempotent(tmp_path):
    """`--no-cluster` still preserves a sticky multigraph across no-op re-runs.

    A no-cluster incremental scan with no changed files produces an empty fresh
    extraction. The command must merge that empty delta with the saved graph,
    not overwrite graph.json with zero nodes/edges.
    """
    corpus = _make_code_corpus(tmp_path)
    env = _clean_env()
    env["ANTHROPIC_API_KEY"] = "sk-test-fake-key"

    r0 = _run(
        ["extract", str(corpus), "--backend", "claude", "--multigraph", "--no-cluster"],
        tmp_path,
        env=env,
    )
    assert r0.returncode == 0, f"initial no-cluster --multigraph failed: {r0.stderr}"

    graph_json = corpus / "graphify-out" / "graph.json"
    first = json.loads(graph_json.read_text(encoding="utf-8"))
    first_nodes = len(first.get("nodes", []))
    first_edges = len(first.get("links", first.get("edges", [])))
    assert first.get("multigraph") is True
    assert _graph_type(first) == "multidigraph"
    assert first_nodes > 0
    assert first_edges > 0

    for attempt in range(1, 4):
        r = _run(
            ["extract", str(corpus), "--backend", "claude", "--no-cluster"],
            tmp_path,
            env=env,
        )
        assert r.returncode == 0, f"sticky no-cluster re-extract #{attempt} failed: {r.stderr}"
        data = json.loads(graph_json.read_text(encoding="utf-8"))
        assert data.get("multigraph") is True
        assert _graph_type(data) == "multidigraph"
        assert len(data.get("nodes", [])) == first_nodes
        assert len(data.get("links", data.get("edges", []))) == first_edges


def test_extract_explicit_simple_downgrade_warns(tmp_path):
    """Existing multigraph graph.json + `extract --simple` → builds simple AND warns.

    The downgrade collapses parallel edges, so it requires explicit intent and a
    loud lossy-collapse WARNING — never a silent collapse. A manifest is seeded so
    the run takes the incremental (preserve+merge) path, where the existing
    multigraph's parallel edges are loaded and then collapsed under the simple
    target — the real lossy projection we want to prove.
    """
    from graphify.detect import save_manifest

    corpus = _make_code_corpus(tmp_path)
    graph_json = _write_multidigraph_graph_json(corpus)
    out = corpus / "graphify-out"
    save_manifest(
        {"code": [str(corpus / "app.py")]},
        manifest_path=str(out / "manifest.json"),
        kind="both",
    )
    before = json.loads(graph_json.read_text(encoding="utf-8"))
    assert before.get("multigraph") is True
    assert len(_parallel_edges(before, "main", "helper")) == 2

    env = _clean_env()
    env["ANTHROPIC_API_KEY"] = "sk-test-fake-key"
    r = _run(["extract", str(corpus), "--backend", "claude", "--simple"], tmp_path, env=env)
    assert r.returncode == 0, f"--simple downgrade should succeed: {r.stderr}"
    # Lossy-collapse WARNING must be printed (explicit, audible downgrade).
    assert "WARNING" in r.stderr and "--simple" in r.stderr, (
        f"explicit --simple downgrade must warn about lossy collapse, got: {r.stderr}"
    )
    assert "collaps" in r.stderr.lower()

    after = json.loads(graph_json.read_text(encoding="utf-8"))
    assert after.get("multigraph") is False, "--simple must produce a non-multigraph graph"
    assert _graph_type(after) != "multidigraph"
    # The two parallel edges from the seeded multigraph collapse onto a single
    # main->helper edge (the lossy projection — one survivor, not two parallels).
    assert len(_parallel_edges(after, "main", "helper")) == 1, (
        "explicit --simple must collapse the existing parallel edges onto one"
    )


def test_extract_multigraph_capability_failure_message(monkeypatch, tmp_path, capsys):
    """A MultiDiGraph capability failure surfaces as a clean CLI error, exit 1.

    The probe RuntimeError must be caught and printed (no traceback), and no
    graph.json may be written. Run in-process so we can monkeypatch the probe.
    """
    corpus = _make_code_corpus(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    def _boom():
        raise RuntimeError(
            "error: --multigraph requires NetworkX keyed MultiDiGraph node-link "
            "round-trip support. Simulated capability failure."
        )

    # Patch where the extract handler imports it from.
    monkeypatch.setattr("graphify.multigraph_compat.require_multigraph_capabilities", _boom)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude", "--multigraph"],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    assert exc_info.value.code == 1, f"capability failure must exit 1, got {exc_info.value.code}"

    err = capsys.readouterr().err
    assert "--multigraph requires" in err, f"clean capability message expected, got: {err}"
    assert "Traceback" not in err, "capability failure must not leak a traceback"
    assert not (corpus / "graphify-out" / "graph.json").exists(), (
        "no graph.json may be written when the capability gate fails"
    )


def test_extract_multigraph_query_roundtrip(tmp_path, capsys, monkeypatch):
    """End-to-end public workflow: a multigraph corpus with same-endpoint different
    relations exposes the parallel relationships through the public query/path path.

    Builds the multigraph graph.json the way `extract --multigraph` persists it,
    then runs `graphify path` (a public query surface) and asserts BOTH parallel
    relations show — the parallel relationships are visible, not collapsed.
    """
    corpus = _make_code_corpus(tmp_path)
    graph_json = _write_multidigraph_graph_json(corpus)

    # Sanity: the persisted file is a multidigraph with both parallel relations.
    data = json.loads(graph_json.read_text(encoding="utf-8"))
    assert data.get("multigraph") is True
    G = load_graph(data)
    assert G.is_multigraph() and G.number_of_edges("main", "helper") == 2

    # Public query surface: `graphify path main helper` bundles all relations.
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "path", "main", "helper", "--graph", str(graph_json)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "calls" in out, f"parallel 'calls' relation must appear in path output: {out}"
    assert "imports" in out, f"parallel 'imports' relation must appear in path output: {out}"


def _make_corpus(tmp_path):
    """Minimal corpus: one Go code file + one Markdown doc.

    Both file types are needed so semantic extraction is requested
    (docs path triggers the LLM step we want to assert against).
    """
    (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")
    (tmp_path / "README.md").write_text("# Notes\nThe main function entry point.\n")
    return tmp_path


def test_extract_exits_nonzero_when_all_semantic_chunks_fail(monkeypatch, tmp_path, capsys):
    """When every semantic chunk errors (e.g. backend SDK not installed),
    the CLI must exit non-zero instead of silently writing an AST-only graph.

    The bug this guards: `pip install graphifyy` doesn't pull in `anthropic`,
    so `graphify extract --backend claude` would print per-chunk errors and
    still exit 0 with a graph.json. Callers checking exit status saw success.
    """
    corpus = _make_corpus(tmp_path)
    out_dir = tmp_path / "out"

    # Stub the API-key check so the backend gate doesn't reject before we
    # reach the semantic-extraction step.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    # Patch extract_corpus_parallel to simulate "all chunks failed":
    # return an empty merged accumulator without ever invoking on_chunk_done.
    # This matches the real behavior of extract_corpus_parallel when every
    # chunk raises (the per-chunk failures print to stderr and the loop
    # continues without calling the success callback).
    def _all_chunks_failed(paths, **kwargs):
        return {
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 0,
            "output_tokens": 0,
        }

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _all_chunks_failed)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude", "--out", str(out_dir)],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 1, (
        f"expected exit code 1 when all semantic chunks fail, got {exc_info.value.code}"
    )

    stderr = capsys.readouterr().err
    assert "all semantic chunks failed" in stderr
    assert "claude" in stderr

    # No graph.json should have been written - the failure must abort before
    # the merge/cluster/write phase, not after.
    assert not (out_dir / "graphify-out" / "graph.json").exists(), (
        "graph.json must not be written when semantic extraction fails"
    )


def test_extract_succeeds_when_at_least_one_chunk_completes(monkeypatch, tmp_path):
    """Sanity counter-test: a successful chunk run keeps exit 0. Confirms the
    new guard only fires on the all-failed path, not on every extract."""
    corpus = _make_corpus(tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    def _one_chunk_succeeded(paths, **kwargs):
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            on_chunk(0, 1, {"nodes": [], "edges": [], "hyperedges": []})
        return {
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 100,
            "output_tokens": 50,
        }

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _one_chunk_succeeded)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude", "--out", str(out_dir)],
    )

    # extract may still raise SystemExit at the end (clean exit code 0)
    # depending on platform; accept either no exception or SystemExit(0).
    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"

    # graph.json should exist on the happy path
    assert (out_dir / "graphify-out" / "graph.json").exists(), (
        "graph.json must be written on the happy path"
    )


def test_extract_no_cluster_refuses_to_zero_populated_graph(monkeypatch, tmp_path, capsys):
    """RISK 4 — Guard 3: the non-incremental no-cluster simple path must NOT wipe a
    populated graph.json with a 0-node extraction.

    The bug: with an existing populated (simple) graph.json but NO manifest.json
    (so the run is non-incremental) the ``--no-cluster`` branch falls to the raw
    ``graph_json_path.write_text(json.dumps(merged, ...))`` ``else`` case. That raw
    write bypasses both existing empty-merge guards (``export.to_json`` /
    ``watch._check_shrink``). When AST extraction aborts (returns 0 nodes) the raw
    write overwrites the saved graph with an EMPTY one — a failed extraction
    silently destroys real data. The clustered sibling already guards this with
    ``if G.number_of_nodes() == 0: ... sys.exit(1)``; the no-cluster simple path
    must do the same. The command must instead exit non-zero, print the byte-
    identical guard message, and leave the populated graph.json untouched.
    """
    corpus = _make_code_corpus(tmp_path)
    out = corpus / "graphify-out"
    out.mkdir(exist_ok=True)
    graph_json = out / "graph.json"

    # Seed a POPULATED *simple* graph.json the way the pipeline persists it
    # (build_from_json default-simple -> to_json). Simple (not multigraph) so the
    # sticky profile resolves to non-multigraph and the run takes the raw-write
    # ``else`` branch — exactly the unguarded site. NO manifest.json is written,
    # so the run is non-incremental (the path the incremental build_merge floor
    # never protects).
    seed_nodes = [
        {
            "id": n,
            "label": f"{n}()",
            "file_type": "code",
            "source_file": "app.py",
            "source_location": "L1",
        }
        for n in ("main", "helper", "extra")
    ]
    seed_edges = [
        {
            "source": "main",
            "target": "helper",
            "relation": "calls",
            "confidence": "EXTRACTED",
            "source_file": "app.py",
            "source_location": "L5",
        }
    ]
    G_seed = build_from_json({"nodes": seed_nodes, "edges": seed_edges})
    assert not G_seed.is_multigraph(), "seed must be a simple graph (non-multigraph)"
    to_json(G_seed, {0: ["main", "helper", "extra"]}, str(graph_json), force=True)
    before = json.loads(graph_json.read_text(encoding="utf-8"))
    seeded_n = len(before.get("nodes", []))
    assert seeded_n == 3, "seed graph.json must start populated with 3 nodes"
    assert before.get("multigraph") is False, "seed graph.json must be simple"
    assert not (out / "manifest.json").exists(), "no manifest → non-incremental run"

    # Force the AST extraction to abort so the merged extraction yields 0 nodes.
    # This mirrors the real trigger (a parser/extractor blowing up): the extract
    # handler's ``except`` resets ast_result to an empty dict, and a code-only
    # corpus has no semantic pass, so ``merged`` collapses to 0 nodes. The extract
    # handler imports ``extract`` from graphify.extract at call time, so patching
    # the source symbol is picked up.
    def _ast_boom(paths, **kwargs):
        raise RuntimeError("simulated AST extractor failure (parser crash)")

    import graphify.extract as _extract_mod

    monkeypatch.setattr(_extract_mod, "extract", _ast_boom)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")  # code-only: LLM never called
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude", "--no-cluster"],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    assert exc_info.value.code == 1, (
        f"a 0-node no-cluster extraction over a populated graph must exit 1, "
        f"got {exc_info.value.code}"
    )

    err = capsys.readouterr().err
    # Byte-identical to the Guard 1 / Guard 2 message.
    assert (
        f"[graphify] ERROR: refusing to overwrite a populated graph.json "
        f"({seeded_n} nodes) with an EMPTY (0-node) graph - this is a "
        f"failed/aborted extraction, not a real result. The previous graph "
        f"is preserved." in err
    ), f"guard message must match Guards 1/2 byte-for-byte, got: {err!r}"

    # The populated graph.json must be PRESERVED — not wiped to an empty graph.
    after = json.loads(graph_json.read_text(encoding="utf-8"))
    assert len(after.get("nodes", [])) == seeded_n, (
        "the populated graph.json must NOT be overwritten with a 0-node graph"
    )


def test_extract_no_cluster_incremental_zero_merge_exits_nonzero_and_preserves_graph(
    monkeypatch, tmp_path, capsys
):
    """RISK 4 — Guard 1 signaling gap: the INCREMENTAL no-cluster path must SIGNAL
    failure (exit non-zero, no false-success line) when the merge yields 0 nodes.

    The incremental no-cluster branch writes through
    ``to_json(_nc_graph, {}, ..., force=True)`` (Guard 1). When ``build_merge``
    collapses to a 0-node graph over a populated graph.json, Guard 1's empty-merge
    floor correctly *returns False and PRESERVES the data* — but the caller ignored
    that return value: it fell through, printed the success line
    ``[graphify extract] wrote ... graph.json — 0 nodes, 0 edges (no clustering)``
    and exited 0. The data was safe, but a failed/aborted extraction reported a
    misleading false success (wrong exit code + message).

    The fix captures Guard 1's ``False`` return at the no-cluster incremental write
    site and, on refusal only, emits an aborted-extraction stderr note and exits 1
    — never the bogus "wrote ... 0 nodes" success line. A populated graph.json plus
    a manifest.json makes the run incremental; ``build_merge`` is forced to yield an
    empty graph to model the aborted/pruned-to-empty merge. The legitimate sticky
    no-cluster case (``test_extract_multigraph_no_cluster_sticky_idempotent``) keeps
    exit 0 because ``build_merge`` preserves the existing nodes there (True return).
    """
    from graphify.detect import save_manifest

    corpus = _make_code_corpus(tmp_path)
    out = corpus / "graphify-out"
    out.mkdir(exist_ok=True)
    graph_json = out / "graph.json"

    # Seed a POPULATED *simple* graph.json the way the pipeline persists it.
    seed_nodes = [
        {
            "id": n,
            "label": f"{n}()",
            "file_type": "code",
            "source_file": "app.py",
            "source_location": "L1",
        }
        for n in ("main", "helper", "extra")
    ]
    seed_edges = [
        {
            "source": "main",
            "target": "helper",
            "relation": "calls",
            "confidence": "EXTRACTED",
            "source_file": "app.py",
            "source_location": "L5",
        }
    ]
    G_seed = build_from_json({"nodes": seed_nodes, "edges": seed_edges})
    assert not G_seed.is_multigraph(), "seed must be a simple graph (non-multigraph)"
    to_json(G_seed, {0: ["main", "helper", "extra"]}, str(graph_json), force=True)

    # A manifest.json alongside the populated graph.json makes the run INCREMENTAL
    # (incremental_mode = manifest.exists() and graph.json.exists()), so the write
    # routes through the incremental ``to_json(..., force=True)`` site, not the
    # raw-write else-branch the Guard 3 sibling covers.
    save_manifest(
        {"code": [str(corpus / "app.py")]},
        manifest_path=str(out / "manifest.json"),
        kind="both",
    )

    before = json.loads(graph_json.read_text(encoding="utf-8"))
    seeded_n = len(before.get("nodes", []))
    assert seeded_n == 3, "seed graph.json must start populated with 3 nodes"
    assert before.get("multigraph") is False, "seed graph.json must be simple"
    assert (out / "manifest.json").exists(), "manifest → incremental run"

    # Force the incremental merge to yield a 0-node graph (aborted / pruned-to-empty
    # extraction). The no-cluster incremental branch imports build_merge from
    # graphify.build at call time, so patching the source symbol is picked up.
    def _empty_merge(*args, **kwargs):
        return build_from_json({"nodes": [], "edges": []})

    import graphify.build as _build_mod

    monkeypatch.setattr(_build_mod, "build_merge", _empty_merge)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")  # code-only: LLM never called
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude", "--no-cluster"],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    assert exc_info.value.code == 1, (
        f"a 0-node incremental no-cluster merge over a populated graph must exit 1, "
        f"got {exc_info.value.code}"
    )

    captured = capsys.readouterr()
    # The misleading false-success line must NOT be printed.
    assert "0 nodes, 0 edges" not in captured.out, (
        f"a 0-node aborted merge must NOT print the 'wrote ... 0 nodes' success "
        f"line, got stdout: {captured.out!r}"
    )

    # The populated graph.json must be PRESERVED — not wiped to an empty graph.
    after = json.loads(graph_json.read_text(encoding="utf-8"))
    assert len(after.get("nodes", [])) == seeded_n, (
        "the populated graph.json must NOT be overwritten with a 0-node graph"
    )
    assert after == before, "graph.json must be byte-for-byte unchanged after the refused write"
