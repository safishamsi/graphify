from pathlib import Path
from graphify.extract import extract_dart

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


def test_flutter_no_errors():
    r = extract_dart(FIXTURES / "sample_flutter.dart")
    assert "error" not in r


def test_flutter_widget_kind_stateless():
    r = extract_dart(FIXTURES / "sample_flutter.dart")
    my_app = _node_meta(r, "MyApp")
    assert my_app is not None
    assert my_app.get("widget_kind") == "stateless"


def test_flutter_widget_kind_stateful():
    r = extract_dart(FIXTURES / "sample_flutter.dart")
    home = _node_meta(r, "MyHomePage")
    assert home is not None
    assert home.get("widget_kind") == "stateful"


def test_flutter_widget_kind_state():
    r = extract_dart(FIXTURES / "sample_flutter.dart")
    state = _node_meta(r, "_MyHomePageState")
    assert state is not None
    assert state.get("widget_kind") == "state"


def test_flutter_creates_state():
    r = extract_dart(FIXTURES / "sample_flutter.dart")
    creates = _edges_of(r, "creates_state")
    assert ("MyHomePage", "_MyHomePageState") in creates


def test_flutter_composition_nested():
    r = extract_dart(FIXTURES / "sample_flutter.dart")
    composes = _edges_of(r, "composes")
    # _MyHomePageState's build returns Scaffold
    assert ("Scaffold", "AppBar") in composes
    assert ("Scaffold", "Center") in composes
    assert ("Center", "Column") in composes


def test_flutter_composition_conditional_flat():
    r = extract_dart(FIXTURES / "sample_flutter.dart")
    composes = _edges_of(r, "composes")
    # Conditional branches attach flat to ConditionalWidget
    assert ("ConditionalWidget", "HomeScreen") in composes
    assert ("ConditionalWidget", "LoginScreen") in composes


def test_flutter_depends_on_inherited():
    r = extract_dart(FIXTURES / "sample_flutter.dart")
    deps = _edges_of(r, "depends_on_inherited")
    # Theme.of(context) in _MyHomePageState
    assert ("_MyHomePageState", "Theme") in deps
