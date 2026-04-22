from pathlib import Path
from graphify.extract import extract_dart

FIXTURES = Path(__file__).parent / "fixtures"


def _edges_of(r, relation):
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == relation
    }


def _edge_dicts(r, relation):
    return [e for e in r["edges"] if e["relation"] == relation]


def _node_meta(r, label):
    return next((n for n in r["nodes"] if n["label"] == label), None)


# ── Navigator tests ─────────────────────────────────────────────────────────


def test_navigator_no_errors():
    r = extract_dart(FIXTURES / "sample_navigator.dart")
    assert "error" not in r


def test_navigator_push_named():
    """Navigator.pushNamed(context, '/settings') -> navigates_to edge."""
    r = extract_dart(FIXTURES / "sample_navigator.dart")
    navs = _edges_of(r, "navigates_to")
    assert ("HomeScreen", "/settings") in navs


def test_navigator_of_push_named():
    """Navigator.of(context).pushNamed('/profile') -> navigates_to edge."""
    r = extract_dart(FIXTURES / "sample_navigator.dart")
    navs = _edges_of(r, "navigates_to")
    assert ("HomeScreen", "/profile") in navs


def test_navigator_push_material_page_route():
    """Navigator.push with MaterialPageRoute(builder: => Screen()) -> navigates_to edge."""
    r = extract_dart(FIXTURES / "sample_navigator.dart")
    navs = _edges_of(r, "navigates_to")
    assert ("HomeScreen", "DetailScreen") in navs


def test_navigator_push_replacement_named():
    """Navigator.pushReplacementNamed(context, '/home') -> navigates_to edge."""
    r = extract_dart(FIXTURES / "sample_navigator.dart")
    navs = _edges_of(r, "navigates_to")
    assert ("DetailScreen", "/home") in navs


def test_navigator_pop_and_push_named():
    """Navigator.popAndPushNamed in non-build method -> navigates_to edge."""
    r = extract_dart(FIXTURES / "sample_navigator.dart")
    navs = _edges_of(r, "navigates_to")
    assert ("SettingsScreen", "/home") in navs


def test_navigator_route_node_kind():
    """Route path nodes should have dart_kind='route'."""
    r = extract_dart(FIXTURES / "sample_navigator.dart")
    route = _node_meta(r, "/settings")
    assert route is not None
    assert route.get("dart_kind") == "route"


def test_navigator_edges_are_inferred():
    """navigates_to edges should have confidence=INFERRED, weight=0.8."""
    r = extract_dart(FIXTURES / "sample_navigator.dart")
    for e in _edge_dicts(r, "navigates_to"):
        assert e["confidence"] == "INFERRED"
        assert e["weight"] == 0.8


# ── GoRouter tests ──────────────────────────────────────────────────────────


def test_gorouter_no_errors():
    r = extract_dart(FIXTURES / "sample_gorouter.dart")
    assert "error" not in r


def test_gorouter_route_definitions():
    """GoRoute(path: '/settings', builder: ... => SettingsScreen()) -> navigates_to edge."""
    r = extract_dart(FIXTURES / "sample_gorouter.dart")
    navs = _edges_of(r, "navigates_to")
    assert ("/settings", "SettingsScreen") in navs


def test_gorouter_route_definition_root():
    """GoRoute(path: '/', builder: ... => HomeScreen()) -> navigates_to edge."""
    r = extract_dart(FIXTURES / "sample_gorouter.dart")
    navs = _edges_of(r, "navigates_to")
    assert ("/", "HomeScreen") in navs


def test_gorouter_route_definition_with_block_body():
    """GoRoute with { return Screen(); } builder syntax."""
    r = extract_dart(FIXTURES / "sample_gorouter.dart")
    navs = _edges_of(r, "navigates_to")
    assert ("/profile/:id", "ProfileScreen") in navs


def test_gorouter_context_go():
    """context.go('/settings') -> navigates_to edge from calling class."""
    r = extract_dart(FIXTURES / "sample_gorouter.dart")
    navs = _edges_of(r, "navigates_to")
    assert ("HomeScreen", "/settings") in navs


def test_gorouter_context_push():
    """context.push('/profile/123') -> navigates_to edge from calling class."""
    r = extract_dart(FIXTURES / "sample_gorouter.dart")
    navs = _edges_of(r, "navigates_to")
    assert ("HomeScreen", "/profile/123") in navs


def test_gorouter_context_go_named():
    """context.goNamed('home') -> navigates_to edge from calling class."""
    r = extract_dart(FIXTURES / "sample_gorouter.dart")
    navs = _edges_of(r, "navigates_to")
    assert ("SettingsScreen", "home") in navs


def test_gorouter_framework_tag():
    """Classes should have go_router in frameworks metadata."""
    r = extract_dart(FIXTURES / "sample_gorouter.dart")
    home = _node_meta(r, "HomeScreen")
    assert home is not None
    assert "go_router" in home.get("frameworks", [])
