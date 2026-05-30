import json
from pathlib import Path
from typing import cast
import networkx as nx
import pytest
from networkx.readwrite import json_graph
from graphify.build import (
    _make_collision_key,
    build_from_json,
    build,
    build_merge,
    edge_data,
    edge_datas,
)
from graphify.edge_identity import make_stable_key

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
    G = cast(nx.Graph, build_from_json(load_extraction()))
    data = G.edges["n_attention", "n_concept_attn"]
    assert data["confidence"] == "INFERRED"


def test_ambiguous_edge_preserved():
    G = cast(nx.Graph, build_from_json(load_extraction()))
    data = G.edges["n_layernorm", "n_concept_attn"]
    assert data["confidence"] == "AMBIGUOUS"


def test_legacy_node_source_canonicalized():
    """Legacy 'source' key on nodes is renamed to 'source_file' before graph build."""
    ext = {
        "nodes": [{"id": "n1", "label": "A", "file_type": "code", "source": "a.py"}],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_from_json(ext)
    assert "source_file" in G.nodes["n1"]
    assert G.nodes["n1"]["source_file"] == "a.py"
    assert "source" not in G.nodes["n1"]


def test_legacy_edge_from_to_canonicalized():
    """Legacy 'from'/'to' keys on edges are accepted alongside 'source'/'target'."""
    ext = {
        "nodes": [
            {"id": "n1", "label": "A", "file_type": "code", "source_file": "a.py"},
            {"id": "n2", "label": "B", "file_type": "code", "source_file": "b.py"},
        ],
        "edges": [
            {
                "from": "n1",
                "to": "n2",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "weight": 1.0,
            }
        ],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_from_json(ext)
    assert G.number_of_edges() == 1


def test_source_file_backslash_normalized():
    """Windows backslash paths and POSIX paths for the same file must produce one node."""
    extraction = {
        "nodes": [
            {
                "id": "n1",
                "label": "A",
                "file_type": "code",
                "source_file": "src\\middleware\\auth.py",
            },
            {
                "id": "n2",
                "label": "B",
                "file_type": "code",
                "source_file": "src/middleware/auth.py",
            },
        ],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_from_json(extraction)
    sources = {G.nodes[n]["source_file"] for n in G.nodes()}
    assert sources == {"src/middleware/auth.py"}


def test_build_merges_multiple_extractions():
    ext1 = {
        "nodes": [{"id": "n1", "label": "A", "file_type": "code", "source_file": "a.py"}],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    ext2 = {
        "nodes": [{"id": "n2", "label": "B", "file_type": "document", "source_file": "b.md"}],
        "edges": [
            {
                "source": "n1",
                "target": "n2",
                "relation": "references",
                "confidence": "INFERRED",
                "source_file": "b.md",
                "weight": 1.0,
            }
        ],
        "input_tokens": 0,
        "output_tokens": 0,
    }
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
    saved_calls = [
        e for e in saved.get("links", saved.get("edges", [])) if e.get("relation") == "calls"
    ]
    assert len(saved_calls) == 1
    assert saved_calls[0]["source"] == truth_src
    assert saved_calls[0]["target"] == truth_tgt

    # Now simulate `--update` with no new chunks — load + re-save.
    G2 = build_merge([], graph_path, dedup=False)
    assert to_json(G2, communities, str(graph_path), force=True)

    # The calls edge must still go a -> b, not b -> a.
    reloaded = json.loads(graph_path.read_text())
    reloaded_calls = [
        e for e in reloaded.get("links", reloaded.get("edges", [])) if e.get("relation") == "calls"
    ]
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
            {
                "source": "a_handler",
                "target": "z_emitter",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "a.ts",
            },
            {
                "source": "z_emitter",
                "target": "a_handler",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "z.ts",
            },
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
    saved_calls = [
        e for e in saved.get("links", saved.get("edges", [])) if e.get("relation") == "calls"
    ]
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
            {
                "id": "overview_intro",
                "label": "Intro",
                "source_file": abs_path,
                "file_type": "document",
            },
        ],
        "edges": [
            {
                "source": "overview_intro",
                "target": "overview_intro",
                "relation": "self",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": abs_path,
            },
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
        "nodes": [
            {"id": "foo_bar", "label": "bar", "source_file": "src/foo.py", "file_type": "code"}
        ],
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
    chunk = {
        "nodes": [
            {"id": "n1", "label": "login", "file_type": "code", "source_file": "module_a/auth.py"},
            {
                "id": "n2",
                "label": "format_date",
                "file_type": "code",
                "source_file": "module_b/utils.py",
            },
        ],
        "edges": [
            {
                "source": "n1",
                "target": "n2",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "module_b/utils.py",
                "weight": 1.0,
            },
        ],
    }
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

    chunk = {
        "nodes": [
            {
                "id": "n1",
                "label": "parse_date",
                "file_type": "code",
                "source_file": "module_b/utils.py",
            },
        ],
        "edges": [],
    }
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


def _parallel_edge_extraction() -> dict:
    return {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "src/a.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "src/b.py"},
        ],
        "edges": [
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "src/a.py",
                "source_location": "L10",
            },
            {
                "source": "a",
                "target": "b",
                "relation": "imports",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "src/a.py",
                "source_location": "L2",
            },
        ],
    }


def test_default_build_stays_simple_when_parallel_edges_exist():
    G = build_from_json(_parallel_edge_extraction())

    assert type(G) is nx.Graph
    assert not G.is_multigraph()
    assert G.number_of_edges("a", "b") == 1


def test_multigraph_build_preserves_same_endpoint_different_relations():
    G = build_from_json(_parallel_edge_extraction(), multigraph=True)

    assert type(G) is nx.MultiDiGraph
    assert G.number_of_edges("a", "b") == 2
    edge_records = list(G["a"]["b"].items())
    assert {data["relation"] for _key, data in edge_records} == {"calls", "imports"}
    assert all(str(key).startswith("edge:v1:") for key, _data in edge_records)
    assert all("key" not in data for _key, data in edge_records)


def test_multigraph_build_preserves_same_identity_except_source_location():
    extraction = _parallel_edge_extraction()
    extraction["edges"][1].update(
        {
            "relation": "calls",
            "source_location": "L20",
        }
    )

    G = build_from_json(extraction, multigraph=True)

    assert G.number_of_edges("a", "b") == 2
    assert {data["source_location"] for data in G["a"]["b"].values()} == {"L10", "L20"}


def test_multigraph_build_collapses_exact_duplicates_with_diagnostic():
    extraction = _parallel_edge_extraction()
    extraction["edges"].append(dict(extraction["edges"][0]))

    G = build_from_json(extraction, multigraph=True)

    assert G.number_of_edges("a", "b") == 2
    assert G.graph["graphify_multigraph_diagnostics"]["exact_duplicate_edges"] == 1


def test_multigraph_build_preserves_non_exact_key_collisions_with_diagnostic():
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "src/a.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "src/b.py"},
        ],
        "edges": [
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "src/a.py",
                "source_location": "L10",
                "context": "static",
            },
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "src/a.py",
                "source_location": "L10",
                "context": "runtime",
            },
        ],
    }

    G = build_from_json(extraction, multigraph=True)

    assert G.number_of_edges("a", "b") == 2
    assert {data["context"] for data in G["a"]["b"].values()} == {
        "static",
        "runtime",
    }
    assert G.graph["graphify_multigraph_diagnostics"]["key_collision_edges"] == 1


def test_multigraph_build_collapses_duplicates_after_collision_repair():
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "src/a.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "src/b.py"},
        ],
        "edges": [
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "src/a.py",
                "source_location": "L10",
                "context": "static",
            },
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "src/a.py",
                "source_location": "L10",
                "context": "runtime",
            },
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "src/a.py",
                "source_location": "L10",
                "context": "runtime",
            },
        ],
    }

    G = build_from_json(extraction, multigraph=True)

    assert G.number_of_edges("a", "b") == 2
    assert {data["context"] for data in G["a"]["b"].values()} == {
        "static",
        "runtime",
    }
    assert G.graph["graphify_multigraph_diagnostics"] == {
        "exact_duplicate_edges": 1,
        "key_collision_edges": 1,
    }


def test_multigraph_build_preserves_empty_string_schema_key():
    extraction = _parallel_edge_extraction()
    extraction["edges"] = [dict(extraction["edges"][0], key="")]

    G = build_from_json(extraction, multigraph=True)

    assert list(G["a"]["b"].keys()) == [""]


def test_multigraph_build_normalizes_path_identity_fields_for_stable_key(tmp_path):
    """Path objects survive coercion via the JSON 'default=str' path of json.dumps."""
    extraction = _parallel_edge_extraction()
    absolute_source = tmp_path / "src" / "a.py"
    extraction["edges"] = [
        {
            **extraction["edges"][0],
            "source_file": absolute_source,
            "source_location": {"line": 10},
        }
    ]

    G = build_from_json(extraction, root=tmp_path, multigraph=True)

    assert G.number_of_edges("a", "b") == 1
    assert next(iter(G["a"]["b"].keys())).startswith("edge:v1:")
    assert next(iter(G["a"]["b"].values()))["source_file"] == "src/a.py"


def test_multigraph_build_skips_edge_with_non_json_serializable_attrs(capsys):
    """Edges whose attrs cannot round-trip through JSON are skipped with a warning.

    Mutating attrs in place would silently change the user's stored value;
    skipping with a warning preserves data integrity for surviving edges and
    prevents later json.dump crashes during export.
    """
    extraction = _parallel_edge_extraction()
    extraction["edges"] = [
        {
            **extraction["edges"][0],
            "relation": {"calls", "uses"},
        }
    ]

    G = build_from_json(extraction, multigraph=True)

    assert G.number_of_edges("a", "b") == 0
    captured = capsys.readouterr()
    assert "non-JSON-serializable" in captured.err


@pytest.mark.parametrize("field", ["nodes", "edges"])
def test_build_from_json_treats_non_list_node_or_edge_field_as_empty(field, capsys):
    extraction = _parallel_edge_extraction()
    extraction[field] = 123

    G = build_from_json(extraction, multigraph=True)

    assert G.number_of_edges() == 0
    captured = capsys.readouterr()
    assert f"extraction field '{field}' must be a list" in captured.err


def test_multigraph_collision_repair_keys_do_not_depend_on_edge_order():
    base_edges = [
        {
            "source": "a",
            "target": "b",
            "relation": "calls",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": "src/a.py",
            "source_location": "L10",
            "context": "static",
        },
        {
            "source": "a",
            "target": "b",
            "relation": "calls",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": "src/a.py",
            "source_location": "L10",
            "context": "runtime",
        },
    ]

    def keys_by_context(edges: list[dict]) -> dict[str, str]:
        extraction = {
            "nodes": [
                {"id": "a", "label": "A", "file_type": "code", "source_file": "src/a.py"},
                {"id": "b", "label": "B", "file_type": "code", "source_file": "src/b.py"},
            ],
            "edges": edges,
        }
        G = build_from_json(extraction, multigraph=True)
        return {data["context"]: key for key, data in G["a"]["b"].items()}

    forward = keys_by_context(base_edges)
    reverse = keys_by_context(list(reversed(base_edges)))

    assert forward == reverse
    assert all(":alt:" in key for key in forward.values())


def test_multigraph_collision_repair_does_not_overwrite_explicit_key():
    runtime_attrs = {
        "relation": "calls",
        "confidence": "EXTRACTED",
        "confidence_score": 1.0,
        "source_file": "src/a.py",
        "source_location": "L10",
        "context": "runtime",
        "_src": "a",
        "_tgt": "b",
    }
    base_key = make_stable_key("calls", "src/a.py", "L10")
    explicit_conflict_key = _make_collision_key(base_key, runtime_attrs)
    edges = [
        {
            "source": "a",
            "target": "b",
            "key": explicit_conflict_key,
            "relation": "imports",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": "src/a.py",
            "source_location": "L2",
            "context": "explicit",
        },
        {
            "source": "a",
            "target": "b",
            "relation": "calls",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": "src/a.py",
            "source_location": "L10",
            "context": "static",
        },
        {
            "source": "a",
            "target": "b",
            "relation": "calls",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": "src/a.py",
            "source_location": "L10",
            "context": "runtime",
        },
    ]

    def contexts_by_key(edge_order: list[dict]) -> dict[str, str]:
        extraction = {
            "nodes": [
                {"id": "a", "label": "A", "file_type": "code", "source_file": "src/a.py"},
                {"id": "b", "label": "B", "file_type": "code", "source_file": "src/b.py"},
            ],
            "edges": edge_order,
        }
        G = build_from_json(extraction, multigraph=True)
        assert G.number_of_edges("a", "b") == 3
        return {key: data["context"] for key, data in G["a"]["b"].items()}

    forward = contexts_by_key(edges)
    reverse = contexts_by_key(list(reversed(edges)))

    assert forward == reverse
    assert forward[explicit_conflict_key] == "explicit"
    runtime_keys = [key for key, context in forward.items() if context == "runtime"]
    assert len(runtime_keys) == 1
    assert runtime_keys[0] != explicit_conflict_key


def test_multigraph_build_roundtrips_through_json_loader(tmp_path):
    from graphify.export import to_json
    from graphify.graph_loader import load_graph_file

    G = build_from_json(_parallel_edge_extraction(), multigraph=True)
    graph_path = tmp_path / "graph.json"

    assert to_json(G, {}, str(graph_path), force=True)
    data = json.loads(graph_path.read_text())
    loaded = load_graph_file(graph_path)

    assert data["multigraph"] is True
    assert data["directed"] is True
    assert len(data["links"]) == 2
    assert all("key" in link for link in data["links"])
    assert type(loaded) is nx.MultiDiGraph
    assert loaded.number_of_edges("a", "b") == 2
    assert set(loaded["a"]["b"]) == {link["key"] for link in data["links"]}


def test_build_multigraph_merges_extractions_without_collapsing_parallel_edges():
    extraction = _parallel_edge_extraction()

    G = build(
        [
            {"nodes": extraction["nodes"], "edges": [extraction["edges"][0]]},
            {"nodes": [], "edges": [extraction["edges"][1]]},
        ],
        dedup=False,
        multigraph=True,
    )

    assert type(G) is nx.MultiDiGraph
    assert G.number_of_edges("a", "b") == 2


def test_build_preserves_hashable_non_string_edge_endpoints():
    extraction = {
        "nodes": [
            {"id": 1, "label": "A", "file_type": "code", "source_file": "src/a.py"},
            {"id": 2, "label": "B", "file_type": "code", "source_file": "src/b.py"},
        ],
        "edges": [
            {
                "source": 1,
                "target": 2,
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "src/a.py",
                "source_location": "L10",
            },
        ],
    }

    G = build_from_json(extraction)

    assert G.has_edge(1, 2)


def test_build_skips_unhashable_edge_endpoints_without_crashing(capsys):
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "src/a.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "src/b.py"},
        ],
        "edges": [
            {
                "source": "a",
                "target": {"bad": "target"},
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "src/a.py",
                "source_location": "L10",
            },
        ],
    }

    G = build_from_json(extraction)
    captured = capsys.readouterr()

    assert G.number_of_edges() == 0
    assert "unhashable" in captured.err


def test_build_skips_unhashable_node_ids_without_crashing(capsys):
    extraction = {
        "nodes": [
            {"id": ["bad"], "label": "Bad", "file_type": "code", "source_file": "src/bad.py"},
            {"id": "ok", "label": "OK", "file_type": "code", "source_file": "src/ok.py"},
        ],
        "edges": [],
    }

    G = build_from_json(extraction)
    captured = capsys.readouterr()

    assert list(G.nodes()) == ["ok"]
    assert "Node 0 id is unhashable" in captured.err


def test_build_skips_malformed_nodes_without_crashing(capsys):
    extraction = {
        "nodes": [
            "bad-node",
            {"label": "Missing ID", "file_type": "code", "source_file": "src/missing.py"},
            {"id": "ok", "label": "OK", "file_type": "code", "source_file": "src/ok.py"},
        ],
        "edges": [],
    }

    G = build_from_json(extraction)
    captured = capsys.readouterr()

    assert list(G.nodes()) == ["ok"]
    assert "Node 0 must be an object" in captured.err


def test_build_warns_when_skipping_unhashable_endpoint_without_node_ids(capsys):
    extraction = {
        "nodes": [],
        "edges": [
            {
                "source": ["bad"],
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "src/a.py",
                "source_location": "L10",
            },
        ],
    }

    G = build_from_json(extraction)
    captured = capsys.readouterr()

    assert G.number_of_edges() == 0
    assert "skipped edge with unhashable source endpoint" in captured.err


def test_build_skips_malformed_edges_without_crashing(capsys):
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "src/a.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "src/b.py"},
        ],
        "edges": [
            7,
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "src/a.py",
                "source_location": "L10",
            },
        ],
    }

    G = build_from_json(extraction)
    captured = capsys.readouterr()

    assert G.number_of_edges() == 1
    assert "Edge 0 must be an object" in captured.err


def _write_multigraph_graph_json(graph_path: Path, extraction: dict) -> dict:
    """Build a MultiDiGraph from *extraction*, persist it via to_json, return the JSON.

    Produces a realistic on-disk multigraph graph.json (multigraph=true, keyed
    parallel edges) exactly as graphify writes it, so build_merge tests exercise
    the real load -> merge -> prune round-trip rather than a hand-rolled dict.
    """
    from graphify.export import to_json

    G = build_from_json(extraction, multigraph=True)
    assert type(G) is nx.MultiDiGraph
    assert to_json(G, {}, str(graph_path), force=True)
    data = json.loads(graph_path.read_text())
    assert data["multigraph"] is True
    return data


def _three_parallel_edges_one_pair() -> dict:
    """A→B carrying three parallel edges, each from a distinct source_file."""
    return {
        "nodes": [
            {"id": "A", "label": "A", "file_type": "code", "source_file": "file1.py"},
            {"id": "B", "label": "B", "file_type": "code", "source_file": "file2.py"},
        ],
        "edges": [
            {
                "source": "A",
                "target": "B",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "file1.py",
                "source_location": "L1",
            },
            {
                "source": "A",
                "target": "B",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "file2.py",
                "source_location": "L2",
            },
            {
                "source": "A",
                "target": "B",
                "relation": "imports",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "file3.py",
                "source_location": "L3",
            },
        ],
    }


def test_build_merge_multigraph_unchanged_file_preserves_parallel_edges(tmp_path):
    """PR 7 gate: merging a new chunk that does not touch A/B's files must
    preserve every keyed parallel edge on the existing A→B pair (no silent
    collapse to a single edge)."""
    graph_path = tmp_path / "graph.json"
    _write_multigraph_graph_json(graph_path, _three_parallel_edges_one_pair())

    # New chunk touches only unrelated files (other.py); A/B's files untouched.
    new_chunk = {
        "nodes": [
            {"id": "C", "label": "C", "file_type": "code", "source_file": "other.py"},
            {"id": "D", "label": "D", "file_type": "code", "source_file": "other.py"},
        ],
        "edges": [
            {
                "source": "C",
                "target": "D",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "other.py",
                "source_location": "L9",
            }
        ],
    }

    G = build_merge([new_chunk], graph_path=graph_path, dedup=False)

    assert type(G) is nx.MultiDiGraph
    assert G.number_of_edges("A", "B") == 3, "all 3 parallel edges must survive the merge"
    assert sorted(d.get("source_file") for d in G["A"]["B"].values()) == [
        "file1.py",
        "file2.py",
        "file3.py",
    ]
    assert G.number_of_edges("C", "D") == 1, "new chunk edge must be added"


def test_build_merge_multigraph_changed_file_evicts_only_its_parallel_edges(tmp_path):
    """Critical source_file+key intersection: a single A→B pair carries parallel
    edges from file1.py AND file2.py; build_merge with file1.py in prune_set must
    remove ONLY file1.py's A→B edge and leave file2.py's A→B edge between the SAME
    pair intact. This is the core guarantee that key-aware pruning never collapses
    or over-deletes parallel edges that share an endpoint pair.

    Endpoint nodes deliberately live in a neutral file (defs.py) so that pruning
    file1.py prunes the EDGE record by its source_file without removing the
    endpoint nodes — isolating the source_file+key edge-prune behavior. (In the
    real incremental flow, deleted files populate prune_sources while changed
    files are re-extracted as fresh chunks; prune runs after the merge.)"""
    extraction = {
        "nodes": [
            {"id": "A", "label": "A", "file_type": "code", "source_file": "defs.py"},
            {"id": "B", "label": "B", "file_type": "code", "source_file": "defs.py"},
        ],
        "edges": [
            {
                "source": "A",
                "target": "B",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "file1.py",
                "source_location": "L1",
            },
            {
                "source": "A",
                "target": "B",
                "relation": "imports",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "file2.py",
                "source_location": "L2",
            },
        ],
    }
    graph_path = tmp_path / "graph.json"
    _write_multigraph_graph_json(graph_path, extraction)

    G = build_merge([], graph_path=graph_path, prune_sources=["file1.py"], dedup=False)

    assert type(G) is nx.MultiDiGraph
    # Both endpoint nodes survive (they live in defs.py, not pruned).
    assert G.has_node("A") and G.has_node("B")
    remaining = sorted(
        (d.get("source_file"), d.get("source_location")) for d in G["A"]["B"].values()
    )
    # file2.py's parallel edge between A→B survives; file1.py's is evicted.
    assert remaining == [("file2.py", "L2")], (
        f"only file1.py's A→B edge must be pruned, file2.py's must survive; got {remaining}"
    )
    assert G.number_of_edges("A", "B") == 1


def test_build_merge_multigraph_deleted_file_removes_all_its_edge_records(tmp_path):
    """Deleting a file must remove ALL edge records (including parallel ones)
    carrying that source_file across every pair, while edges from other files
    survive — even when they share an endpoint pair."""
    extraction = {
        "nodes": [
            {"id": "A", "label": "A", "file_type": "code", "source_file": "keep.py"},
            {"id": "B", "label": "B", "file_type": "code", "source_file": "keep.py"},
            {"id": "C", "label": "C", "file_type": "code", "source_file": "gone.py"},
        ],
        "edges": [
            # Two parallel A→B edges from the deleted file plus one from a kept file.
            {
                "source": "A",
                "target": "B",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "gone.py",
                "source_location": "L1",
            },
            {
                "source": "A",
                "target": "B",
                "relation": "imports",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "gone.py",
                "source_location": "L2",
            },
            {
                "source": "A",
                "target": "B",
                "relation": "references",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "keep.py",
                "source_location": "L3",
            },
            # An edge on a different pair, also from the deleted file.
            {
                "source": "A",
                "target": "C",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "gone.py",
                "source_location": "L4",
            },
        ],
    }
    graph_path = tmp_path / "graph.json"
    _write_multigraph_graph_json(graph_path, extraction)

    G = build_merge([], graph_path=graph_path, prune_sources=["gone.py"], dedup=False)

    assert type(G) is nx.MultiDiGraph
    # All gone.py edge records removed across all pairs.
    assert all(d.get("source_file") != "gone.py" for _u, _v, d in G.edges(data=True)), (
        "no edge record from the deleted file may survive"
    )
    # The keep.py A→B parallel edge survives even though gone.py shared that pair.
    assert G.number_of_edges("A", "B") == 1
    assert next(iter(G["A"]["B"].values())).get("source_file") == "keep.py"
    # Node C had source_file gone.py → pruned, so the A→C pair is gone entirely.
    assert not G.has_node("C")


def test_build_merge_multigraph_output_stays_multigraph(tmp_path):
    """After merge, the written graph.json must still be multigraph=true and
    reload as a MultiDiGraph — no silent fallback to a simple graph."""
    from graphify.export import to_json
    from graphify.graph_loader import load_graph_file

    graph_path = tmp_path / "graph.json"
    _write_multigraph_graph_json(graph_path, _three_parallel_edges_one_pair())

    G = build_merge([], graph_path=graph_path, dedup=False)
    assert type(G) is nx.MultiDiGraph
    assert G.is_multigraph() and G.is_directed()

    # Write back and confirm the multigraph flag round-trips on reload.
    out_path = tmp_path / "graph_out.json"
    assert to_json(G, {}, str(out_path), force=True)
    data = json.loads(out_path.read_text())
    assert data["multigraph"] is True
    assert data["directed"] is True
    reloaded = load_graph_file(out_path)
    assert type(reloaded) is nx.MultiDiGraph
    assert reloaded.number_of_edges("A", "B") == 3


def test_build_merge_simple_graph_unchanged_regression(tmp_path):
    """Removing the multigraph rejection must not change simple-graph behavior:
    a simple/digraph build_merge output is identical to pre-PR7 behavior."""
    import networkx as nx_local

    # Build and persist a plain directed simple graph (multigraph absent/false).
    chunk = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "a.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "b.py"},
        ],
        "edges": [
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "weight": 1.0,
            }
        ],
    }
    G0 = build([chunk], dedup=False)
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(nx_local.node_link_data(G0, edges="edges")), encoding="utf-8")

    # No new chunks, default args → must inherit simple (non-multigraph) type and
    # remain a plain undirected Graph here (saved directed flag is false).
    G = build_merge([], graph_path=graph_path, dedup=False)
    assert not G.is_multigraph(), "simple-graph build_merge must not upgrade to multigraph"
    assert type(G) is nx.Graph
    assert G.number_of_nodes() == 2
    assert G.number_of_edges() == 1
    assert G.has_edge("a", "b")

    # Pruning a deleted file on a simple graph still removes the matching edge.
    G2 = build_merge([], graph_path=graph_path, prune_sources=["a.py"], dedup=False)
    assert not G2.is_multigraph()
    assert G2.number_of_edges() == 0, "simple-graph prune path unchanged"


def test_build_merge_inherits_directed_from_saved_graph_json(tmp_path):
    """build_merge with default args must preserve direction of a directed saved graph."""
    import json as _json

    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        _json.dumps(
            {
                "directed": True,
                "multigraph": False,
                "nodes": [
                    {"id": "caller", "file_type": "code", "source_file": "a.py"},
                    {"id": "callee", "file_type": "code", "source_file": "b.py"},
                ],
                "links": [
                    {
                        "source": "caller",
                        "target": "callee",
                        "relation": "calls",
                        "source_file": "a.py",
                        "_src": "caller",
                        "_tgt": "callee",
                    }
                ],
            }
        )
    )

    # No `directed=` arg passed — must inherit True from the saved file.
    G = build_merge([], graph_path=graph_path)
    assert G.is_directed(), "build_merge default-args must inherit directed=True from saved graph"
    assert G.has_edge("caller", "callee")
    assert not G.has_edge("callee", "caller")


def test_build_merge_directed_override_warns(tmp_path, capsys):
    """Explicit directed=False against a directed saved graph emits a warning."""
    import json as _json

    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        _json.dumps(
            {
                "directed": True,
                "multigraph": False,
                "nodes": [{"id": "a"}, {"id": "b"}],
                "links": [{"source": "a", "target": "b", "relation": "calls"}],
            }
        )
    )

    G = build_merge([], graph_path=graph_path, directed=False)
    captured = capsys.readouterr()
    assert "overrides saved" in captured.err.lower()
    assert not G.is_directed()


def test_build_merge_rejects_non_bool_multigraph_in_saved_graph(tmp_path):
    """A saved graph.json with a non-bool 'multigraph' value must be rejected."""
    import json as _json

    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        _json.dumps(
            {
                "directed": True,
                "multigraph": "false",
                "nodes": [{"id": "a"}, {"id": "b"}],
                "links": [{"source": "a", "target": "b", "relation": "calls"}],
            }
        )
    )
    with pytest.raises(TypeError, match="'multigraph' in .* must be a boolean"):
        build_merge([], graph_path=graph_path)


def test_build_merge_rejects_non_bool_directed_in_saved_graph(tmp_path):
    import json as _json

    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        _json.dumps(
            {
                "directed": "true",
                "multigraph": False,
                "nodes": [{"id": "a"}, {"id": "b"}],
                "links": [{"source": "a", "target": "b", "relation": "calls"}],
            }
        )
    )
    with pytest.raises(TypeError, match="'directed' in .* must be a boolean"):
        build_merge([], graph_path=graph_path)


def test_simple_build_skips_edge_with_non_json_serializable_attrs(capsys):
    """Same skip-and-warn policy applies to simple-graph builds."""
    extraction = _parallel_edge_extraction()
    extraction["edges"] = [
        {
            **extraction["edges"][0],
            "relation": {"calls", "uses"},
        }
    ]
    G = build_from_json(extraction, multigraph=False)
    assert G.number_of_edges("a", "b") == 0
    captured = capsys.readouterr()
    assert "non-JSON-serializable" in captured.err


def test_build_skips_node_with_non_json_serializable_attrs(capsys):
    """Nodes with non-JSON-serializable attrs are skipped with a warning."""
    extraction = {
        "nodes": [
            {"id": "ok", "label": "OK", "file_type": "code", "source_file": "a.py"},
            {
                "id": "bad",
                "label": "Bad",
                "file_type": "code",
                "source_file": "b.py",
                "tags": {"unhashable", "set"},
            },
        ],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_from_json(extraction)
    assert "ok" in G.nodes
    assert "bad" not in G.nodes
    captured = capsys.readouterr()
    assert "non-JSON-serializable" in captured.err


def test_build_strips_legacy_from_to_from_edge_attrs():
    """Legacy from/to keys must not survive into stored edge attrs after remap."""
    ext = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "a.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "b.py"},
        ],
        "edges": [
            {
                "from": "a",
                "to": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "weight": 1.0,
            }
        ],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = cast(nx.Graph, build_from_json(ext))
    data = G.edges["a", "b"]
    assert "from" not in data
    assert "to" not in data


def test_multigraph_preserves_first_explicit_key_in_collision_group():
    """When multiple edges share an explicit user key, the first one preserves it."""
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "a.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "b.py"},
        ],
        "edges": [
            {
                "source": "a",
                "target": "b",
                "key": "user-key",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "context": "first",
            },
            {
                "source": "a",
                "target": "b",
                "key": "user-key",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "context": "second",
            },
        ],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_from_json(extraction, multigraph=True)
    keys = set(G["a"]["b"].keys())
    assert "user-key" in keys, "First edge must retain the explicit user-supplied key"
    assert len(keys) == 2, "Both edges must survive; second gets a repair key"
