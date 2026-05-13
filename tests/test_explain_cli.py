"""Tests for `graphify explain` arrow-direction rendering.

Regression for the structural twin of #849 — the same undirected-graph blind spot
that bit `graphify path` also bit `graphify explain`. Previously `explain` printed
every neighbor as `--> X [relation]`, so for a queried node that is the *callee*,
its callers were rendered as outbound calls, asserting a backwards graph.
"""
from __future__ import annotations

import json

import graphify.__main__ as mainmod


def _write_undirected_graph(tmp_path):
    """Write graph.json with `directed: false` but link.source/link.target
    encoding caller→callee in *write order*, matching what `graphify update`
    serializes. Writing the JSON directly (rather than via `nx.Graph` +
    `node_link_data`) is necessary because the latter emits links in
    node-insertion order, not edge-argument order, so a small fixture can
    silently encode the wrong direction.
    """
    graph_data = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {"id": "validate", "label": "validateSanitySession()",
             "source_file": "server/sanity-validate-session.ts",
             "source_location": "L9", "community": 0},
            {"id": "create_patch", "label": "createPatchHandler()",
             "source_file": "server/create-patch-handler.ts",
             "source_location": "L14", "community": 0},
            {"id": "create_edit", "label": "createEditHandler()",
             "source_file": "server/create-edit-handler.ts",
             "source_location": "L18", "community": 0},
            {"id": "stable_stringify", "label": "stableStringify()",
             "source_file": "shared/stringify.ts",
             "source_location": "L4", "community": 0},
        ],
        "links": [
            # Two callers of validate (edges point INTO validate).
            {"source": "create_patch", "target": "validate",
             "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "create_edit", "target": "validate",
             "relation": "calls", "confidence": "EXTRACTED"},
            # One callee of validate (edge points OUT of validate).
            {"source": "validate", "target": "stable_stringify",
             "relation": "calls", "confidence": "EXTRACTED"},
        ],
    }
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(graph_data))
    return graph_path


def _run_explain(monkeypatch, graph_path, label, capsys):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "explain", label, "--graph", str(graph_path)],
    )
    mainmod.main()
    return capsys.readouterr().out


def test_explain_renders_callers_as_inbound_and_callees_as_outbound(
    monkeypatch, tmp_path, capsys
):
    """A queried callee should show its callers as `<--` and its own callees as `-->`.
    Before the fix every neighbor printed as `-->`, regardless of stored direction."""
    graph_path = _write_undirected_graph(tmp_path)
    out = _run_explain(monkeypatch, graph_path, "validateSanitySession", capsys)

    # validateSanitySession is called BY createPatchHandler and createEditHandler.
    # Those must render as inbound (`<--`), not outbound.
    assert "<-- createPatchHandler() [calls]" in out
    assert "<-- createEditHandler() [calls]" in out
    # validateSanitySession itself calls stableStringify — that is outbound.
    assert "--> stableStringify() [calls]" in out
    # Critical guard: must NOT render callers as outbound (the pre-fix buggy output).
    assert "--> createPatchHandler() [calls]" not in out
    assert "--> createEditHandler() [calls]" not in out


def test_explain_renders_pure_caller_as_outbound(monkeypatch, tmp_path, capsys):
    """Sanity check the converse — querying a caller should show its callee outbound."""
    graph_path = _write_undirected_graph(tmp_path)
    out = _run_explain(monkeypatch, graph_path, "createPatchHandler", capsys)
    # createPatchHandler calls validateSanitySession.
    assert "--> validateSanitySession() [calls]" in out
    # And nothing calls createPatchHandler in this fixture, so no inbound rows.
    assert "<-- " not in out
