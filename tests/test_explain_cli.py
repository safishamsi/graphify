"""Regression tests for `graphify explain` arrow direction (#853)."""
from __future__ import annotations
import json
import graphify.__main__ as mainmod


def _write_graph(tmp_path):
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "validate", "label": "validateSanitySession()",
             "source_file": "server/sanity-validate-session.ts", "community": 0},
            {"id": "create_patch", "label": "createPatchHandler()",
             "source_file": "server/create-patch-handler.ts", "community": 0},
            {"id": "create_edit", "label": "createEditHandler()",
             "source_file": "server/create-edit-handler.ts", "community": 0},
            {"id": "stable_stringify", "label": "stableStringify()",
             "source_file": "shared/stringify.ts", "community": 0},
        ],
        "links": [
            {"source": "create_patch", "target": "validate",
             "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "create_edit", "target": "validate",
             "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "validate", "target": "stable_stringify",
             "relation": "calls", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def _run(monkeypatch, graph_path, label, capsys):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", label, "--graph", str(graph_path)])
    mainmod.main()
    return capsys.readouterr().out


def test_callee_shows_callers_as_inbound(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "validateSanitySession", capsys)
    assert "<-- createPatchHandler() [calls]" in out
    assert "<-- createEditHandler() [calls]" in out
    assert "--> stableStringify() [calls]" in out
    assert "--> createPatchHandler() [calls]" not in out
    assert "--> createEditHandler() [calls]" not in out


def test_caller_shows_callee_as_outbound(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "createPatchHandler", capsys)
    assert "--> validateSanitySession() [calls]" in out
    assert "<-- " not in out
