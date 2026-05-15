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
