from pathlib import Path
from graphify.extract_melos import extract_melos

FIXTURES = Path(__file__).parent / "fixtures"

def _node_meta(r, label):
    return next((n for n in r["nodes"] if n["label"] == label), None)

def test_melos_no_errors():
    r = extract_melos(FIXTURES / "sample_melos" / "melos.yaml")
    assert "error" not in r

def test_melos_workspace_node():
    r = extract_melos(FIXTURES / "sample_melos" / "melos.yaml")
    ws = _node_meta(r, "my_workspace")
    assert ws is not None
    assert ws.get("dart_kind") == "workspace"
