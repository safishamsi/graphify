import pytest
from graphify.validate import validate_extraction, assert_valid

VALID = {
    "nodes": [
        {"id": "n1", "label": "Foo", "file_type": "code", "source_file": "foo.py"},
        {"id": "n2", "label": "Bar", "file_type": "document", "source_file": "bar.md"},
    ],
    "edges": [
        {"source": "n1", "target": "n2", "relation": "references",
         "confidence": "EXTRACTED", "source_file": "foo.py", "weight": 1.0},
    ],
}

def test_valid_passes():
    assert validate_extraction(VALID) == []

def test_missing_nodes_key():
    errors = validate_extraction({"edges": []})
    assert any("nodes" in e for e in errors)

def test_missing_edges_key():
    errors = validate_extraction({"nodes": []})
    assert any("edges" in e for e in errors)

def test_not_a_dict():
    errors = validate_extraction([])
    assert len(errors) == 1

def test_invalid_file_type():
    data = {
        "nodes": [{"id": "n1", "label": "X", "file_type": "video", "source_file": "x.mp4"}],
        "edges": [],
    }
    errors = validate_extraction(data)
    assert any("file_type" in e for e in errors)

def test_invalid_confidence():
    data = {
        "nodes": [
            {"id": "n1", "label": "A", "file_type": "code", "source_file": "a.py"},
            {"id": "n2", "label": "B", "file_type": "code", "source_file": "b.py"},
        ],
        "edges": [
            {"source": "n1", "target": "n2", "relation": "calls",
             "confidence": "CERTAIN", "source_file": "a.py"},
        ],
    }
    errors = validate_extraction(data)
    assert any("confidence" in e for e in errors)

def test_dangling_edge_source():
    data = {
        "nodes": [{"id": "n1", "label": "A", "file_type": "code", "source_file": "a.py"}],
        "edges": [
            {"source": "missing_id", "target": "n1", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "a.py"},
        ],
    }
    errors = validate_extraction(data)
    assert any("source" in e and "missing_id" in e for e in errors)

def test_dangling_edge_target():
    data = {
        "nodes": [{"id": "n1", "label": "A", "file_type": "code", "source_file": "a.py"}],
        "edges": [
            {"source": "n1", "target": "ghost", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "a.py"},
        ],
    }
    errors = validate_extraction(data)
    assert any("target" in e and "ghost" in e for e in errors)

def test_missing_node_field():
    data = {
        "nodes": [{"id": "n1", "label": "A", "source_file": "a.py"}],  # missing file_type
        "edges": [],
    }
    errors = validate_extraction(data)
    assert any("file_type" in e for e in errors)

def test_assert_valid_raises_on_errors():
    with pytest.raises(ValueError, match="error"):
        assert_valid({"nodes": [], "edges": [], "oops": True, **{"nodes": "bad"}})

def test_assert_valid_passes_silently():
    assert_valid(VALID)  # should not raise
