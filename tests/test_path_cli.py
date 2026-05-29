"""Regression tests for `graphify path` arrow direction (#849)."""

from __future__ import annotations
import json
import graphify.__main__ as mainmod


def _write_graph(tmp_path):
    graph_data = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {
                "id": "create_patch",
                "label": "createPatchHandler()",
                "source_file": "server/create-patch-handler.ts",
                "community": 0,
            },
            {
                "id": "validate",
                "label": "validateSanitySession()",
                "source_file": "server/sanity-validate-session.ts",
                "community": 0,
            },
        ],
        "links": [
            {
                "source": "create_patch",
                "target": "validate",
                "relation": "calls",
                "confidence": "EXTRACTED",
            },
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def _run(monkeypatch, graph_path, src, tgt, capsys):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "path", src, tgt, "--graph", str(graph_path)]
    )
    mainmod.main()
    return capsys.readouterr().out


def test_forward_arrow(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "createPatchHandler", "validateSanitySession", capsys)
    assert "Shortest path (1 hops):" in out
    assert "createPatchHandler() --calls [EXTRACTED]--> validateSanitySession()" in out


def test_reverse_arrow(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "validateSanitySession", "createPatchHandler", capsys)
    assert "Shortest path (1 hops):" in out
    assert "validateSanitySession() <--calls [EXTRACTED]-- createPatchHandler()" in out
    assert "validateSanitySession() --calls [EXTRACTED]--> createPatchHandler()" not in out


def _write_multigraph(tmp_path):
    """A->B with 3 parallel relations, B->C with a single relation."""
    graph_data = {
        "directed": True,
        "multigraph": True,
        "graph": {},
        "nodes": [
            {"id": "a", "label": "alpha()", "source_file": "a.py", "community": 0},
            {"id": "b", "label": "beta()", "source_file": "b.py", "community": 0},
            {"id": "c", "label": "gamma()", "source_file": "c.py", "community": 0},
        ],
        "links": [
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "key": 0,
            },
            {
                "source": "a",
                "target": "b",
                "relation": "imports",
                "confidence": "EXTRACTED",
                "key": 1,
            },
            {
                "source": "a",
                "target": "b",
                "relation": "contains",
                "confidence": "EXTRACTED",
                "key": 2,
            },
            {
                "source": "b",
                "target": "c",
                "relation": "returns",
                "confidence": "INFERRED",
                "key": 0,
            },
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def test_path_multigraph_hop_shows_all_relations(monkeypatch, tmp_path, capsys):
    """PR5 gate: a MultiDiGraph hop bundles all parallel relations, never first-only."""
    p = _write_multigraph(tmp_path)
    out = _run(monkeypatch, p, "alpha", "gamma", capsys)
    assert "Shortest path (2 hops):" in out
    # The A->B hop carries 3 parallel relations: all must appear (sorted, unique).
    assert "--calls, contains, imports--> beta()" in out
    # First-edge-only regression guard: the lone "calls" hop form must NOT appear.
    assert "--calls [EXTRACTED]--> beta()" not in out
    # The single-relation B->C hop stays byte-stable.
    assert "--returns [INFERRED]--> gamma()" in out


def test_path_simple_graph_output_regression(monkeypatch, tmp_path, capsys):
    """Simple DiGraph path output is unchanged: single relation per hop."""
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "createPatchHandler", "validateSanitySession", capsys)
    # Byte-stable single-relation form, matching test_forward_arrow exactly.
    assert "createPatchHandler() --calls [EXTRACTED]--> validateSanitySession()" in out


def _write_bidirectional_multigraph(tmp_path):
    """A->B 'calls', B->A 'imports' (opposite relations), plus B->C so the
    shortest A->C path renders the A->B hop in its stored forward direction."""
    graph_data = {
        "directed": True,
        "multigraph": True,
        "graph": {},
        "nodes": [
            {"id": "a", "label": "alpha()", "source_file": "a.py", "community": 0},
            {"id": "b", "label": "beta()", "source_file": "b.py", "community": 0},
            {"id": "c", "label": "gamma()", "source_file": "c.py", "community": 0},
        ],
        "links": [
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "key": 0,
            },
            {
                "source": "b",
                "target": "a",
                "relation": "imports",
                "confidence": "EXTRACTED",
                "key": 0,
            },
            {
                "source": "b",
                "target": "c",
                "relation": "returns",
                "confidence": "INFERRED",
                "key": 0,
            },
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def test_path_directional_isolation(monkeypatch, tmp_path, capsys):
    """A->B hop renders only the forward 'calls' relation, never the reverse 'imports'.

    Regression for the directed_only fix: relationship_envelope merges both
    directions by default, which would wrongly bundle B->A 'imports' onto the
    A-->B arrow. directed_only=True must isolate the stored hop direction.
    """
    p = _write_bidirectional_multigraph(tmp_path)
    out = _run(monkeypatch, p, "alpha", "gamma", capsys)
    assert "Shortest path (2 hops):" in out
    # Forward hop shows ONLY 'calls' (byte-stable single-relation form).
    assert "alpha() --calls [EXTRACTED]--> beta()" in out
    # The reverse-direction 'imports' must NOT bleed into the forward arrow.
    assert "imports" not in out
