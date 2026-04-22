from pathlib import Path
from graphify.extract_pubspec import extract_pubspec

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

def test_pubspec_no_errors():
    r = extract_pubspec(FIXTURES / "sample_pubspec" / "pubspec.yaml")
    assert "error" not in r

def test_pubspec_package_node():
    r = extract_pubspec(FIXTURES / "sample_pubspec" / "pubspec.yaml")
    pkg = _node_meta(r, "my_flutter_app")
    assert pkg is not None
    assert pkg.get("dart_kind") == "package"
    assert pkg.get("project_type") == "flutter"

def test_pubspec_depends_on():
    r = extract_pubspec(FIXTURES / "sample_pubspec" / "pubspec.yaml")
    deps = _edges_of(r, "depends_on")
    assert ("my_flutter_app", "http") in deps
    assert ("my_flutter_app", "riverpod") in deps
    assert ("my_flutter_app", "shared_models") in deps

def test_pubspec_dev_depends_on():
    r = extract_pubspec(FIXTURES / "sample_pubspec" / "pubspec.yaml")
    deps = _edges_of(r, "dev_depends_on")
    assert ("my_flutter_app", "build_runner") in deps
    assert ("my_flutter_app", "freezed") in deps
