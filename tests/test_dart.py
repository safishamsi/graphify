from pathlib import Path
from graphify.extract_dart import extract_dart

FIXTURES = Path(__file__).parent / "fixtures"


def _labels(r):
    return [n["label"] for n in r["nodes"]]


def _relations(r):
    return {e["relation"] for e in r["edges"]}


def _edges_of(r, relation):
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == relation
    }


def _node_meta(r, label):
    return next((n for n in r["nodes"] if n["label"] == label), None)


def test_extract_dart_no_errors():
    r = extract_dart(FIXTURES / "sample.dart")
    assert "error" not in r


def test_extract_dart_finds_classes():
    r = extract_dart(FIXTURES / "sample.dart")
    labels = _labels(r)
    assert "Animal" in labels
    assert "Dog" in labels
    assert "Duck" in labels
    assert "HttpClient" in labels


def test_extract_dart_finds_mixins():
    r = extract_dart(FIXTURES / "sample.dart")
    labels = _labels(r)
    assert "Swimmer" in labels
    assert "Diver" in labels


def test_extract_dart_finds_enums():
    r = extract_dart(FIXTURES / "sample.dart")
    labels = _labels(r)
    assert "Status" in labels


def test_extract_dart_finds_typedefs():
    r = extract_dart(FIXTURES / "sample.dart")
    labels = _labels(r)
    assert "Callback" in labels


def test_extract_dart_finds_extensions():
    r = extract_dart(FIXTURES / "sample.dart")
    labels = _labels(r)
    assert "StringUtils" in labels


def test_extract_dart_finds_sealed():
    r = extract_dart(FIXTURES / "sample.dart")
    labels = _labels(r)
    assert "Shape" in labels
    assert "Circle" in labels
    assert "Square" in labels


def test_extract_dart_sealed_metadata():
    r = extract_dart(FIXTURES / "sample.dart")
    shape = _node_meta(r, "Shape")
    assert shape is not None
    assert shape.get("class_modifier") == "sealed"
    circle = _node_meta(r, "Circle")
    assert circle is not None
    assert circle.get("class_modifier") == "final"
    square = _node_meta(r, "Square")
    assert square is not None
    assert square.get("class_modifier") == "base"


def test_extract_dart_finds_functions():
    r = extract_dart(FIXTURES / "sample.dart")
    labels = _labels(r)
    assert "main()" in labels


def test_extract_dart_finds_methods():
    r = extract_dart(FIXTURES / "sample.dart")
    labels = _labels(r)
    assert ".speak()" in labels
    assert ".fetchData()" in labels


def test_extract_dart_finds_imports():
    r = extract_dart(FIXTURES / "sample.dart")
    relations = _relations(r)
    assert "imports" in relations


def test_extract_dart_no_dangling_edges():
    r = extract_dart(FIXTURES / "sample.dart")
    node_ids = {n["id"] for n in r["nodes"]}
    for edge in r["edges"]:
        if edge["relation"] in ("imports", "imports_from", "exports", "has_part"):
            assert edge["source"] in node_ids
        else:
            assert edge["source"] in node_ids, f"Dangling source: {edge}"
            assert edge["target"] in node_ids, f"Dangling target: {edge}"


def test_extract_dart_inherits():
    r = extract_dart(FIXTURES / "sample.dart")
    inherits = _edges_of(r, "inherits")
    assert ("Dog", "Animal") in inherits
    assert ("Duck", "Animal") in inherits
    assert ("Circle", "Shape") in inherits
    assert ("Square", "Shape") in inherits


def test_extract_dart_mixes_in():
    r = extract_dart(FIXTURES / "sample.dart")
    mixes = _edges_of(r, "mixes_in")
    assert ("Duck", "Swimmer") in mixes
    assert ("Duck", "Diver") in mixes


def test_extract_dart_constrained_to():
    r = extract_dart(FIXTURES / "sample.dart")
    constrained = _edges_of(r, "constrained_to")
    assert ("Diver", "Swimmer") in constrained


def test_extract_dart_extends_type():
    r = extract_dart(FIXTURES / "sample.dart")
    ext = _edges_of(r, "extends_type")
    assert ("StringUtils", "String") in ext


def test_extract_dart_exports():
    r = extract_dart(FIXTURES / "sample.dart")
    relations = _relations(r)
    assert "exports" in relations


def test_extract_dart_has_part():
    r = extract_dart(FIXTURES / "sample.dart")
    relations = _relations(r)
    assert "has_part" in relations


def test_extract_dart_calls():
    r = extract_dart(FIXTURES / "sample.dart")
    calls = _edges_of(r, "calls")
    assert len(calls) > 0
