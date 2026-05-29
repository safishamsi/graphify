"""Regression tests for `graphify explain` arrow direction (#853)."""

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
                "id": "validate",
                "label": "validateSanitySession()",
                "source_file": "server/sanity-validate-session.ts",
                "community": 0,
            },
            {
                "id": "create_patch",
                "label": "createPatchHandler()",
                "source_file": "server/create-patch-handler.ts",
                "community": 0,
            },
            {
                "id": "create_edit",
                "label": "createEditHandler()",
                "source_file": "server/create-edit-handler.ts",
                "community": 0,
            },
            {
                "id": "stable_stringify",
                "label": "stableStringify()",
                "source_file": "shared/stringify.ts",
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
            {
                "source": "create_edit",
                "target": "validate",
                "relation": "calls",
                "confidence": "EXTRACTED",
            },
            {
                "source": "validate",
                "target": "stable_stringify",
                "relation": "calls",
                "confidence": "EXTRACTED",
            },
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def _run(monkeypatch, graph_path, label, capsys):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "explain", label, "--graph", str(graph_path)]
    )
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


def _write_multigraph(tmp_path, relations):
    """Node 'a' with `relations` parallel edges to neighbor 'b' (MultiDiGraph)."""
    links = [
        {"source": "a", "target": "b", "relation": rel, "key": idx}
        for idx, rel in enumerate(relations)
    ]
    graph_data = {
        "directed": True,
        "multigraph": True,
        "graph": {},
        "nodes": [
            {"id": "a", "label": "alpha()", "source_file": "a.py", "community": 0},
            {"id": "b", "label": "beta()", "source_file": "b.py", "community": 0},
        ],
        "links": links,
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def test_explain_multigraph_neighbor_bundles_relations(monkeypatch, tmp_path, capsys):
    """PR5 gate: a neighbor reached by 4 parallel edges shows the bundle, not one."""
    p = _write_multigraph(tmp_path, ["calls", "imports", "contains", "reads"])
    out = _run(monkeypatch, p, "alpha()", capsys)
    # 4 unique relations exceeds the default cap (3), so a capped bundle renders
    # the bundle for that neighbor rather than a single first-edge relation.
    assert "--> beta() [calls, contains, imports (+1 more, 4 total)]" in out
    # First-edge-only regression guard: a lone "[calls] [...]" block must NOT appear.
    assert "--> beta() [calls] [" not in out


def test_explain_multigraph_capped_summary(monkeypatch, tmp_path, capsys):
    """A neighbor pair with >3 unique relations renders the capped (+K more, N total) form."""
    p = _write_multigraph(tmp_path, ["gamma", "alpha", "epsilon", "beta", "delta"])
    out = _run(monkeypatch, p, "alpha()", capsys)
    # sorted unique: alpha, beta, delta, epsilon, gamma -> first 3 + capped suffix.
    assert "--> beta() [alpha, beta, delta (+2 more, 5 total)]" in out


def test_explain_simple_graph_output_regression(monkeypatch, tmp_path, capsys):
    """Simple DiGraph explain output is unchanged: '[rel] [conf]' per neighbor."""
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "validateSanitySession", capsys)
    # Byte-stable bracketed form, matching test_callee_shows_callers_as_inbound.
    assert "<-- createPatchHandler() [calls]" in out
    assert "<-- createEditHandler() [calls]" in out
    assert "--> stableStringify() [calls]" in out


def _write_bidirectional_multigraph(tmp_path):
    """A<->B with different relations each way: A->B 'calls', B->A 'imports'."""
    graph_data = {
        "directed": True,
        "multigraph": True,
        "graph": {},
        "nodes": [
            {"id": "a", "label": "alpha()", "source_file": "a.py", "community": 0},
            {"id": "b", "label": "beta()", "source_file": "b.py", "community": 0},
        ],
        "links": [
            {"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED", "key": 0},
            {"source": "b", "target": "a", "relation": "imports", "confidence": "EXTRACTED", "key": 0},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def test_explain_directional_isolation(monkeypatch, tmp_path, capsys):
    """Out and in connections to the same neighbor stay isolated by direction.

    Regression for the directed_only fix: relationship_envelope merges both
    directions by default, which would wrongly show 'calls, imports' on both
    the out (-->) and in (<--) arrows. directed_only=True isolates each
    connection's own stored direction.
    """
    p = _write_bidirectional_multigraph(tmp_path)
    out = _run(monkeypatch, p, "alpha()", capsys)
    # Outgoing A->B shows ONLY 'calls'; incoming B->A shows ONLY 'imports'.
    assert "--> beta() [calls] [EXTRACTED]" in out
    assert "<-- beta() [imports] [EXTRACTED]" in out
    # Neither arrow may merge the opposite direction's relation.
    assert "--> beta() [calls, imports" not in out
    assert "<-- beta() [calls, imports" not in out
    assert "--> beta() [imports" not in out
    assert "<-- beta() [calls]" not in out
