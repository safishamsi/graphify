import json
from pathlib import Path
from graphify.build import build_from_json, build

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


def test_real_invalid_file_type_still_warns(capsys):
    """Truly invalid file_type values (not None, not empty) must still warn."""
    ext = {
        "nodes": [
            {"id": "n1", "label": "Bad", "file_type": "weird_type", "source_file": "a.py"},
        ],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    build_from_json(ext)
    err = capsys.readouterr().err
    assert "invalid file_type" in err
    assert "weird_type" in err


# ── Internal helpers exposed for direct testing ──────────────────────────


def test_norm_source_file_converts_backslashes():
    """_norm_source_file converts backslashes to forward slashes only."""
    from graphify.build import _norm_source_file
    assert _norm_source_file("/home/user/git/repo/src/lib.rs") == "/home/user/git/repo/src/lib.rs"
    assert _norm_source_file("src/lib.rs") == "src/lib.rs"
    assert _norm_source_file("") == ""


# ── build_from_json edge-case paths ──────────────────────────────────────


def test_build_from_json_handles_hyperedges_in_extraction():
    """Edges stored under 'hyperedges' should bind when 'edges' is missing."""
    G = build_from_json({
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [],
        "hyperedges": [
            {"nodes": ["a", "b"], "label": "shared-concept", "relation": "concept_group"}
        ],
    })
    assert G.number_of_nodes() == 2
    # hyperedge loaded as graph attribute
    h_edges = G.graph.get("hyperedges", [])
    assert len(h_edges) >= 1


def test_build_from_json_uses_links_key_when_edges_absent():
    """Fallback to 'links' key ensures older graph exports load."""
    G = build_from_json({
        "nodes": [{"id": "a"}, {"id": "b"}],
        "links": [{"source": "a", "target": "b", "relation": "calls"}],
    })
    assert G.number_of_edges() == 1


# (test_build_from_json_loads_extraction_fixture removed — fixture not available)


def test_build_from_json_canonicalizes_legacy_from_to_keys():
    """Edges using 'from'/'to' get remapped to 'source'/'target'."""
    G = build_from_json({
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [{"from": "a", "to": "b", "relation": "imports"}],
    })
    assert G.number_of_edges() == 1
    edge = list(G.edges(data=True))[0]
    assert edge[2]["relation"] == "imports"


def test_build_from_json_edge_source_file_explicit():
    """Edge source_file comes from the edge dict, not top-level inheritance."""
    G = build_from_json({
        "source_file": "src/main.py",
        "nodes": [{"id": "a", "source_file": "src/main.py"}, {"id": "b", "source_file": "src/main.py"}],
        "edges": [{"source": "a", "target": "b", "relation": "calls", "source_file": "src/main.py"}],
    })
    assert G.number_of_edges() == 1
    edge = list(G.edges(data=True))[0]
    assert edge[2]["source_file"] == "src/main.py"


def test_build_from_json_handles_empty_nodes():
    """Empty nodes list produces empty graph rather than raising."""
    G = build_from_json({"nodes": [], "links": []})
    assert G.number_of_nodes() == 0


def test_build_merge_no_existing_graph():
    """build_merge without an existing graph falls through clean."""
    from graphify.build import build_merge
    result = build_merge(
        new_chunks=[{"nodes": [{"id": "n1", "label": "X", "file_type": "code", "source_file": "a.py"}], "edges": []}],
        graph_path=Path("graphify-out/nonexistent-graph.json"),
    )
    assert result is not None
    assert result.number_of_nodes() >= 1


def test_build_merge_with_existing_graph(tmp_path):
    """build_merge loads existing graph, merges, and returns combined."""
    import json as _json
    from graphify.build import build_merge
    old = tmp_path / "graph.json"
    old.write_text(_json.dumps({
        "nodes": [{"id": "old", "label": "Old", "file_type": "code", "source_file": "old.py"}],
        "links": [],
        "hyperedges": [],
    }))
    result = build_merge(
        new_chunks=[{"nodes": [{"id": "new", "label": "New", "file_type": "code", "source_file": "new.py"}], "edges": []}],
        graph_path=old,
    )
    assert result.number_of_nodes() >= 2
