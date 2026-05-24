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


def _write_hub_graph(tmp_path, n_neighbors: int = 35):
    """Build a hub-and-spoke graph with one center and N neighbors so the
    default 20-connection cap actually kicks in.
    """
    nodes = [{"id": "hub", "label": "Hub()", "source_file": "hub.py", "community": 0}]
    links = []
    for i in range(n_neighbors):
        nid = f"spoke_{i}"
        nodes.append({"id": nid, "label": f"spoke_{i}()",
                      "source_file": f"spokes/s{i}.py", "community": 0})
        links.append({"source": nid, "target": "hub",
                      "relation": "calls", "confidence": "EXTRACTED"})
    graph_data = {"directed": False, "multigraph": False, "graph": {},
                  "nodes": nodes, "links": links}
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def _run_with_args(monkeypatch, argv, capsys):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    mainmod.main()
    return capsys.readouterr().out


def test_explain_default_truncates_at_20_and_hints_at_flag(monkeypatch, tmp_path, capsys):
    """Default behavior unchanged: cap at 20, then "and N more". Hint must
    name the new flag so users can recover the truncated tail without
    inspecting graph.json directly.
    """
    p = _write_hub_graph(tmp_path, n_neighbors=35)
    out = _run_with_args(monkeypatch,
                         ["graphify", "explain", "Hub", "--graph", str(p)], capsys)
    assert "Connections (35):" in out
    assert "... and 15 more" in out
    assert "--limit" in out and "--full" in out  # flag hint surfaced


def test_explain_limit_flag_raises_cap(monkeypatch, tmp_path, capsys):
    p = _write_hub_graph(tmp_path, n_neighbors=35)
    out = _run_with_args(monkeypatch,
                         ["graphify", "explain", "Hub", "--limit", "30", "--graph", str(p)], capsys)
    # First 30 spokes should appear, last 5 truncated
    assert "spoke_29()" in out or out.count("spoke_") >= 30
    assert "... and 5 more" in out


def test_explain_full_flag_prints_all_connections(monkeypatch, tmp_path, capsys):
    p = _write_hub_graph(tmp_path, n_neighbors=35)
    out = _run_with_args(monkeypatch,
                         ["graphify", "explain", "Hub", "--full", "--graph", str(p)], capsys)
    # All 35 spokes must appear; no truncation footer
    assert out.count("spoke_") >= 35
    assert "... and" not in out


def test_explain_limit_zero_equivalent_to_full(monkeypatch, tmp_path, capsys):
    p = _write_hub_graph(tmp_path, n_neighbors=35)
    out = _run_with_args(monkeypatch,
                         ["graphify", "explain", "Hub", "--limit", "0", "--graph", str(p)], capsys)
    assert out.count("spoke_") >= 35
    assert "... and" not in out


def test_explain_limit_eq_form(monkeypatch, tmp_path, capsys):
    """--limit=N (equals form) parses the same as --limit N."""
    p = _write_hub_graph(tmp_path, n_neighbors=35)
    out = _run_with_args(monkeypatch,
                         ["graphify", "explain", "Hub", "--limit=25", "--graph", str(p)], capsys)
    assert "... and 10 more" in out
