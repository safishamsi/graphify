import json
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph
from graphify.build import build_from_json, build, build_merge, edge_data, edge_datas

FIXTURES = Path(__file__).parent / "fixtures"

def load_extraction():
    return json.loads((FIXTURES / "extraction.json").read_text())

def test_build_from_json_node_count():
    G = build_from_json(load_extraction())
    assert G.number_of_nodes() == 4

def test_build_from_json_edge_count():
    G = build_from_json(load_extraction())
    assert G.number_of_edges() == 4

def test_nodes_have_label():
    G = build_from_json(load_extraction())
    assert G.nodes["n_transformer"]["label"] == "Transformer"

def test_edges_have_confidence():
    G = build_from_json(load_extraction())
    data = G.edges["n_attention", "n_concept_attn"]
    assert data["confidence"] == "INFERRED"

def test_ambiguous_edge_preserved():
    G = build_from_json(load_extraction())
    data = G.edges["n_layernorm", "n_concept_attn"]
    assert data["confidence"] == "AMBIGUOUS"

def test_legacy_node_source_canonicalized():
    """Legacy 'source' key on nodes is renamed to 'source_file' before graph build."""
    ext = {"nodes": [{"id": "n1", "label": "A", "file_type": "code", "source": "a.py"}],
           "edges": [], "input_tokens": 0, "output_tokens": 0}
    G = build_from_json(ext)
    assert "source_file" in G.nodes["n1"]
    assert G.nodes["n1"]["source_file"] == "a.py"
    assert "source" not in G.nodes["n1"]


def test_legacy_edge_from_to_canonicalized():
    """Legacy 'from'/'to' keys on edges are accepted alongside 'source'/'target'."""
    ext = {"nodes": [{"id": "n1", "label": "A", "file_type": "code", "source_file": "a.py"},
                     {"id": "n2", "label": "B", "file_type": "code", "source_file": "b.py"}],
           "edges": [{"from": "n1", "to": "n2", "relation": "calls",
                      "confidence": "EXTRACTED", "source_file": "a.py", "weight": 1.0}],
           "input_tokens": 0, "output_tokens": 0}
    G = build_from_json(ext)
    assert G.number_of_edges() == 1


def test_source_file_backslash_normalized():
    """Windows backslash paths and POSIX paths for the same file must produce one node."""
    extraction = {
        "nodes": [
            {"id": "n1", "label": "A", "file_type": "code", "source_file": "src\\middleware\\auth.py"},
            {"id": "n2", "label": "B", "file_type": "code", "source_file": "src/middleware/auth.py"},
        ],
        "edges": [],
        "input_tokens": 0, "output_tokens": 0,
    }
    G = build_from_json(extraction)
    sources = {G.nodes[n]["source_file"] for n in G.nodes()}
    assert sources == {"src/middleware/auth.py"}


def test_build_merges_multiple_extractions():
    ext1 = {"nodes": [{"id": "n1", "label": "A", "file_type": "code", "source_file": "a.py"}],
            "edges": [], "input_tokens": 0, "output_tokens": 0}
    ext2 = {"nodes": [{"id": "n2", "label": "B", "file_type": "document", "source_file": "b.md"}],
            "edges": [{"source": "n1", "target": "n2", "relation": "references",
                       "confidence": "INFERRED", "source_file": "b.md", "weight": 1.0}],
            "input_tokens": 0, "output_tokens": 0}
    G = build([ext1, ext2])
    assert G.number_of_nodes() == 2
    assert G.number_of_edges() == 1


def test_none_file_type_defaults_to_concept(capsys):
    """Legacy nodes with file_type=None (e.g. preserved from older graph.json
    by `_rebuild_code`) must not trigger 'invalid file_type None' warnings (#660)."""
    ext = {
        "nodes": [
            {"id": "n1", "label": "Stub", "file_type": None, "source_file": "a.py"},
            {"id": "n2", "label": "Real", "file_type": "code", "source_file": "b.py"},
        ],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_from_json(ext)
    err = capsys.readouterr().err
    assert "invalid file_type" not in err
    # The legacy node still exists in the graph and has been canonicalized
    assert G.nodes["n1"]["file_type"] == "concept"
    assert G.nodes["n2"]["file_type"] == "code"


def test_missing_file_type_defaults_to_concept(capsys):
    """Nodes missing file_type entirely should also be canonicalized to 'concept'."""
    ext = {
        "nodes": [
            {"id": "n1", "label": "Bare", "source_file": "a.py"},
        ],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_from_json(ext)
    err = capsys.readouterr().err
    assert "invalid file_type" not in err
    assert "missing required field 'file_type'" not in err
    assert G.nodes["n1"]["file_type"] == "concept"


def test_real_invalid_file_type_coerced_to_concept():
    """Unknown file_type values are coerced through the synonym mapper, falling
    back to 'concept' for anything that isn't a known LLM synonym (#840)."""
    ext = {
        "nodes": [
            {"id": "n1", "label": "Bad", "file_type": "weird_type", "source_file": "a.py"},
        ],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_from_json(ext)
    assert G.nodes["n1"]["file_type"] == "concept"


def test_file_type_synonym_mapping():
    """Known invalid file_type values map to their canonical equivalents."""
    ext = {
        "nodes": [
            {"id": "n1", "label": "MD", "file_type": "markdown", "source_file": "a.md"},
            {"id": "n2", "label": "Tool", "file_type": "tool", "source_file": "b.py"},
            {"id": "n3", "label": "Pat", "file_type": "pattern", "source_file": "c.md"},
        ],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_from_json(ext)
    assert G.nodes["n1"]["file_type"] == "document"
    assert G.nodes["n2"]["file_type"] == "code"
    assert G.nodes["n3"]["file_type"] == "concept"


def test_build_merge_preserves_call_edge_direction(tmp_path):
    """Regression for #760.

    When the callee is defined before the caller in source, NetworkX's
    undirected Graph stores edges in node-insertion order. Going through
    node_link_graph() + edges() during build_merge previously flipped the
    `calls` edge so that on the next save source/target were swapped.

    build_merge must read the saved JSON's source/target verbatim instead
    of round-tripping through NetworkX.
    """
    from graphify.extract import extract_js
    from graphify.export import to_json

    # Callee `b` is defined before caller `a` so node insertion order
    # is b, a. An undirected Graph then yields the edge as (b, a) on
    # iteration, which is the wrong direction for `calls` (a calls b).
    src = "function b() {}\nfunction a() { b(); }\n"
    src_file = tmp_path / "x.js"
    src_file.write_text(src)

    extraction = extract_js(src_file)
    assert "error" not in extraction

    # Locate the `calls` edge in the raw extraction so we know the truth.
    call_edges = [e for e in extraction["edges"] if e["relation"] == "calls"]
    assert len(call_edges) == 1, "expected exactly one calls edge from the snippet"
    truth_src = call_edges[0]["source"]
    truth_tgt = call_edges[0]["target"]

    nodes_by_id = {n["id"]: n for n in extraction["nodes"]}
    assert nodes_by_id[truth_src]["label"].startswith("a")
    assert nodes_by_id[truth_tgt]["label"].startswith("b")

    # First build + save.
    G1 = build([extraction], dedup=False)
    graph_path = tmp_path / "graph.json"
    communities: dict = {}
    assert to_json(G1, communities, str(graph_path), force=True)

    # Verify direction is correct in the freshly written JSON.
    saved = json.loads(graph_path.read_text())
    saved_calls = [e for e in saved.get("links", saved.get("edges", []))
                   if e.get("relation") == "calls"]
    assert len(saved_calls) == 1
    assert saved_calls[0]["source"] == truth_src
    assert saved_calls[0]["target"] == truth_tgt

    # Now simulate `--update` with no new chunks — load + re-save.
    G2 = build_merge([], graph_path, dedup=False)
    assert to_json(G2, communities, str(graph_path), force=True)

    # The calls edge must still go a -> b, not b -> a.
    reloaded = json.loads(graph_path.read_text())
    reloaded_calls = [e for e in reloaded.get("links", reloaded.get("edges", []))
                      if e.get("relation") == "calls"]
    assert len(reloaded_calls) == 1
    assert reloaded_calls[0]["source"] == truth_src, (
        f"calls edge source flipped after build_merge round-trip: "
        f"expected {truth_src} (a), got {reloaded_calls[0]['source']}"
    )
    assert reloaded_calls[0]["target"] == truth_tgt, (
        f"calls edge target flipped after build_merge round-trip: "
        f"expected {truth_tgt} (b), got {reloaded_calls[0]['target']}"
    )


def test_build_from_json_preserves_first_direction_on_bidirectional_pair(tmp_path):
    """Regression for #1061.

    When an extraction emits two `calls` edges between the same pair in
    opposite directions (mutual recursion, callbacks, event handlers, etc.),
    nx.Graph collapses them into a single undirected edge. The deterministic
    edge sort introduced in #1010 ordered edges by (source, target, relation),
    so the lexicographically-later direction always wrote second and clobbered
    the first edge's _src/_tgt — the surviving edge then exported with caller
    and callee systematically swapped on every collision.

    build_from_json must keep the first-seen direction for the surviving edge
    instead of letting the second add_edge overwrite _src/_tgt.
    """
    from graphify.export import to_json

    # Lexicographic order of (src, tgt, rel) puts `a` < `z` first, so the sort
    # processes `a -> z` BEFORE `z -> a`. Without the fix, the second write
    # overwrites _src/_tgt and the exported edge becomes z -> a. With the fix,
    # the first-seen `a -> z` direction is preserved.
    extraction = {
        "nodes": [
            {"id": "a_handler", "label": "a", "file_type": "code", "source_file": "a.ts"},
            {"id": "z_emitter", "label": "z", "file_type": "code", "source_file": "z.ts"},
        ],
        "edges": [
            {"source": "a_handler", "target": "z_emitter", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "a.ts"},
            {"source": "z_emitter", "target": "a_handler", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "z.ts"},
        ],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_from_json(extraction)
    # Only one undirected edge between the pair survives, but its stored
    # direction must be the first-seen one (a_handler -> z_emitter), not the
    # lexicographically-later one (z_emitter -> a_handler).
    assert G.number_of_edges() == 1
    data = edge_data(G, "a_handler", "z_emitter")
    assert data["_src"] == "a_handler"
    assert data["_tgt"] == "z_emitter"

    graph_path = tmp_path / "graph.json"
    assert to_json(G, {}, str(graph_path), force=True)
    saved = json.loads(graph_path.read_text())
    saved_calls = [e for e in saved.get("links", saved.get("edges", []))
                   if e.get("relation") == "calls"]
    assert len(saved_calls) == 1
    assert saved_calls[0]["source"] == "a_handler", (
        f"calls edge source flipped on bidirectional collision: "
        f"expected a_handler, got {saved_calls[0]['source']}"
    )
    assert saved_calls[0]["target"] == "z_emitter", (
        f"calls edge target flipped on bidirectional collision: "
        f"expected z_emitter, got {saved_calls[0]['target']}"
    )


# Regression tests for #796 — edge_data / edge_datas helpers must tolerate
# MultiGraph and MultiDiGraph, which networkx's node_link_graph() produces
# whenever the loaded JSON has multigraph: true. Plain G.edges[u, v] crashes
# on those with `ValueError: not enough values to unpack (expected 3, got 2)`.

def test_edge_data_simple_graph():
    G = nx.Graph()
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    d = edge_data(G, "a", "b")
    assert isinstance(d, dict)
    assert d["relation"] == "calls"
    assert d["confidence"] == "EXTRACTED"


def test_edge_datas_simple_graph_returns_singleton_list():
    G = nx.Graph()
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    ds = edge_datas(G, "a", "b")
    assert isinstance(ds, list)
    assert len(ds) == 1
    assert ds[0]["relation"] == "calls"


def test_edge_data_multigraph_with_parallel_edges():
    G = nx.MultiGraph()
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    G.add_edge("a", "b", relation="references", confidence="INFERRED")
    d = edge_data(G, "a", "b")
    assert isinstance(d, dict)
    # First parallel edge wins; should be one of the two attribute dicts above.
    assert d.get("relation") in ("calls", "references")


def test_edge_datas_multigraph_returns_all_parallel_edges():
    G = nx.MultiGraph()
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    G.add_edge("a", "b", relation="references", confidence="INFERRED")
    ds = edge_datas(G, "a", "b")
    assert isinstance(ds, list)
    assert len(ds) == 2
    relations = {e.get("relation") for e in ds}
    assert relations == {"calls", "references"}


def test_edge_data_multidigraph():
    G = nx.MultiDiGraph()
    G.add_edge("a", "b", relation="calls")
    G.add_edge("a", "b", relation="imports")
    d = edge_data(G, "a", "b")
    assert isinstance(d, dict)
    assert d.get("relation") in ("calls", "imports")
    ds = edge_datas(G, "a", "b")
    assert len(ds) == 2


def test_edge_data_node_link_multigraph_roundtrip():
    """A node_link JSON with multigraph: true must load as MultiGraph and the
    helpers must operate on it without raising the 3-tuple unpack ValueError."""
    data = {
        "directed": False,
        "multigraph": True,
        "graph": {},
        "nodes": [
            {"id": "a", "label": "A"},
            {"id": "b", "label": "B"},
        ],
        "links": [
            {"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "a", "target": "b", "relation": "references", "confidence": "INFERRED"},
        ],
    }
    try:
        G = json_graph.node_link_graph(data, edges="links")
    except TypeError:
        G = json_graph.node_link_graph(data)
    assert isinstance(G, nx.MultiGraph)
    # Plain G.edges[u, v] would raise here; the helper must not.
    d = edge_data(G, "a", "b")
    assert isinstance(d, dict)
    assert d.get("relation") in ("calls", "references")
    ds = edge_datas(G, "a", "b")
    assert len(ds) == 2


def test_build_from_json_relativizes_absolute_source_file(tmp_path):
    """Semantic subagents emit absolute source_file paths; build_from_json must
    relativize them to root so MCP traversal works correctly (#932)."""
    root = tmp_path / "myproject"
    root.mkdir()
    abs_path = str(root / "docs" / "overview.md")
    extraction = {
        "nodes": [
            {"id": "overview_intro", "label": "Intro", "source_file": abs_path, "file_type": "document"},
        ],
        "edges": [
            {"source": "overview_intro", "target": "overview_intro",
             "relation": "self", "confidence": "EXTRACTED", "confidence_score": 1.0,
             "source_file": abs_path},
        ],
    }
    G = build_from_json(extraction, root=root)
    sf = G.nodes["overview_intro"]["source_file"]
    assert not sf.startswith("/"), f"source_file still absolute: {sf}"
    assert sf == "docs/overview.md"


def test_build_relativizes_absolute_source_file(tmp_path):
    """build() passes root through to build_from_json (#932)."""
    root = tmp_path / "proj"
    root.mkdir()
    abs_path = str(root / "src" / "main.py")
    extraction = {
        "nodes": [{"id": "main_fn", "label": "main", "source_file": abs_path, "file_type": "code"}],
        "edges": [],
    }
    G = build([extraction], root=root)
    sf = G.nodes["main_fn"]["source_file"]
    assert sf == "src/main.py"


def test_build_from_json_relative_source_file_unchanged(tmp_path):
    """Already-relative source_file paths must not be modified."""
    extraction = {
        "nodes": [{"id": "foo_bar", "label": "bar", "source_file": "src/foo.py", "file_type": "code"}],
        "edges": [],
    }
    G = build_from_json(extraction, root=tmp_path)
    assert G.nodes["foo_bar"]["source_file"] == "src/foo.py"


def test_build_merge_prune_absolute_paths_match_relative_nodes(tmp_path):
    """#1007: manifest stores absolute paths, graph nodes store relative paths.
    prune_sources with absolute paths must still remove the right nodes and edges."""
    import networkx as nx

    root = tmp_path / "corpus"
    root.mkdir()
    graph_path = tmp_path / "graph.json"

    # Simulate a graph with relative source_file paths (as built normally)
    chunk = {"nodes": [
        {"id": "n1", "label": "login", "file_type": "code", "source_file": "module_a/auth.py"},
        {"id": "n2", "label": "format_date", "file_type": "code", "source_file": "module_b/utils.py"},
    ], "edges": [
        {"source": "n1", "target": "n2", "relation": "calls", "confidence": "EXTRACTED",
         "source_file": "module_b/utils.py", "weight": 1.0},
    ]}
    G0 = build([chunk], dedup=False)
    graph_path.write_text(json.dumps(nx.node_link_data(G0, edges="edges")), encoding="utf-8")

    # prune_sources from manifest — absolute paths (what detect_incremental emits)
    deleted_abs = [str(root / "module_b" / "utils.py")]
    G1 = build_merge([], graph_path, prune_sources=deleted_abs, dedup=False, root=root)

    node_labels = {d["label"] for _, d in G1.nodes(data=True)}
    assert "format_date" not in node_labels, "stale node from deleted file should be pruned"
    assert "login" in node_labels, "unrelated node must survive"
    # Edge from deleted file must also be gone
    assert G1.number_of_edges() == 0, "edge from deleted source_file should be pruned"


def test_build_merge_prune_windows_backslash_paths(tmp_path):
    """#1007: prune_sources with Windows-style backslash absolute paths must still match."""
    import networkx as nx

    root = tmp_path / "corpus"
    root.mkdir()
    graph_path = tmp_path / "graph.json"

    chunk = {"nodes": [
        {"id": "n1", "label": "parse_date", "file_type": "code", "source_file": "module_b/utils.py"},
    ], "edges": []}
    G0 = build([chunk], dedup=False)
    graph_path.write_text(json.dumps(nx.node_link_data(G0, edges="edges")), encoding="utf-8")

    # Simulate Windows manifest path with backslashes
    win_path = str(root / "module_b" / "utils.py").replace("/", "\\")
    G1 = build_merge([], graph_path, prune_sources=[win_path], dedup=False, root=root)

    node_labels = {d["label"] for _, d in G1.nodes(data=True)}
    assert "parse_date" not in node_labels, "node should be pruned even with backslash path"


def test_build_merge_rejects_oversized_existing_graph(monkeypatch, tmp_path):
    """#F4: build_merge must refuse to read an existing graph.json that
    exceeds the size cap, rather than json.loads-ing it into memory."""
    import pytest

    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")
    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 8)
    with pytest.raises(ValueError, match="exceeds"):
        build_merge([], graph_path, dedup=False)
