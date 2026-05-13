"""Tests for `graphify path` arrow-direction rendering (regression for #849)."""
from __future__ import annotations

import json

import networkx as nx
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod


def _write_undirected_graph(tmp_path):
    """Write a graph.json with `directed: false` (the build's default) but link
    source/target encoding caller→callee. This mirrors the on-disk shape that
    ships from `graphify update`."""
    G = nx.Graph()
    G.add_node(
        "create_patch_handler",
        label="createPatchHandler()",
        source_file="server/create-patch-handler.ts",
        source_location="L14",
        community=0,
    )
    G.add_node(
        "validate_sanity_session",
        label="validateSanitySession()",
        source_file="server/sanity-validate-session.ts",
        source_location="L9",
        community=0,
    )
    # The link is serialized as source=createPatchHandler, target=validateSanitySession
    # because nx.Graph.add_edge(u, v, ...) places u in `source` and v in `target`
    # when round-tripped through node_link_data.
    G.add_edge(
        "create_patch_handler",
        "validate_sanity_session",
        relation="calls",
        confidence="EXTRACTED",
        context="call",
    )
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")))
    # Sanity-check the on-disk shape matches the production build (#849 reproducer).
    on_disk = json.loads(graph_path.read_text())
    assert on_disk["directed"] is False
    assert on_disk["links"][0]["source"] == "create_patch_handler"
    assert on_disk["links"][0]["target"] == "validate_sanity_session"
    return graph_path


def _run_path(monkeypatch, graph_path, source_label, target_label, capsys):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "path", source_label, target_label, "--graph", str(graph_path)],
    )
    mainmod.main()
    return capsys.readouterr().out


def test_path_renders_forward_arrow_when_traversal_matches_edge_direction(
    monkeypatch, tmp_path, capsys
):
    """createPatchHandler --calls--> validateSanitySession is the stored direction;
    querying in that order should print the arrow pointing right."""
    graph_path = _write_undirected_graph(tmp_path)
    out = _run_path(
        monkeypatch, graph_path, "createPatchHandler", "validateSanitySession", capsys
    )
    assert "Shortest path (1 hops):" in out
    assert "createPatchHandler() --calls [EXTRACTED]--> validateSanitySession()" in out


def test_path_renders_reverse_arrow_when_traversal_opposes_edge_direction(
    monkeypatch, tmp_path, capsys
):
    """When the user queries `path B A` but the stored edge is A→B, the arrow must
    point back at A — not forward at A as if B called A. This is the #849 regression."""
    graph_path = _write_undirected_graph(tmp_path)
    out = _run_path(
        monkeypatch, graph_path, "validateSanitySession", "createPatchHandler", capsys
    )
    assert "Shortest path (1 hops):" in out
    # Reverse arrow: traversal goes validate→create but edge points create→validate.
    assert (
        "validateSanitySession() <--calls [EXTRACTED]-- createPatchHandler()" in out
    )
    # Critical guard: must NOT render forward in this direction (the #849 bug output).
    assert (
        "validateSanitySession() --calls [EXTRACTED]--> createPatchHandler()" not in out
    )
