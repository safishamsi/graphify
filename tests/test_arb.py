from pathlib import Path
from graphify.extract_arb import extract_arb

FIXTURES = Path(__file__).parent / "fixtures"

def _labels(r):
    return [n["label"] for n in r["nodes"]]

def _edges_of(r, relation):
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == relation
    }

def _node_meta(r, label):
    return next((n for n in r["nodes"] if n["label"] == label), None)

def test_arb_no_errors():
    r = extract_arb(FIXTURES / "app_en.arb")
    assert "error" not in r

def test_arb_locale_node():
    r = extract_arb(FIXTURES / "app_en.arb")
    loc = _node_meta(r, "app_en")
    assert loc is not None
    assert loc.get("dart_kind") == "localization"
    assert loc.get("locale") == "en"

def test_arb_defines_message():
    r = extract_arb(FIXTURES / "app_en.arb")
    messages = _edges_of(r, "defines_message")
    assert len(messages) == 3  # appTitle, helloWorld, itemCount
