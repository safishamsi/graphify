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
