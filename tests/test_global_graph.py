"""Tests for the global graph infrastructure (graphify/global_graph.py),
prefix/prune helpers in graphify/build.py, and the cross-repo guard in
graphify/dedup.py."""
from __future__ import annotations

import json
import pytest
import networkx as nx
from unittest.mock import patch


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_graph(nodes, edges=None):
    """Build a simple nx.Graph from node dicts."""
    G = nx.Graph()
    for n in nodes:
        nid = n["id"]
        G.add_node(nid, **{k: v for k, v in n.items() if k != "id"})
    for e in (edges or []):
        G.add_edge(
            e["source"],
            e["target"],
            **{k: v for k, v in e.items() if k not in ("source", "target")},
        )
    return G


def _graph_to_json(G, path):
    from networkx.readwrite import json_graph as jg
    try:
        data = jg.node_link_data(G, edges="links")
    except TypeError:
        data = jg.node_link_data(G)
    path.write_text(json.dumps(data), encoding="utf-8")


# ── build.py helpers ──────────────────────────────────────────────────────────

def test_prefix_graph_preserves_label():
    from graphify.build import prefix_graph_for_global
    G = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    H = prefix_graph_for_global(G, "repoA")
    assert "repoA::userservice" in H.nodes
    assert "userservice" not in H.nodes
    assert H.nodes["repoA::userservice"]["label"] == "UserService"


def test_prefix_graph_sets_repo_and_local_id():
    from graphify.build import prefix_graph_for_global
    G = _make_graph([{"id": "userservice", "label": "UserService"}])
    H = prefix_graph_for_global(G, "repoA")
    data = H.nodes["repoA::userservice"]
    assert data["repo"] == "repoA"
    assert data["local_id"] == "userservice"


def test_prefix_graph_rewrites_edges():
    from graphify.build import prefix_graph_for_global
    G = _make_graph(
        [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        [{"source": "a", "target": "b"}],
    )
    H = prefix_graph_for_global(G, "repo1")
    assert H.has_edge("repo1::a", "repo1::b")
    assert not H.has_edge("a", "b")


def test_prune_repo_removes_correct_nodes():
    from graphify.build import prune_repo_from_graph
    G = nx.Graph()
    G.add_node("repoA::userservice", repo="repoA", label="UserService")
    G.add_node("repoB::userservice", repo="repoB", label="UserService")
    G.add_node("repoA::auth", repo="repoA", label="Auth")
    removed = prune_repo_from_graph(G, "repoA")
    assert removed == 2
    assert "repoB::userservice" in G.nodes
    assert "repoA::userservice" not in G.nodes
    assert "repoA::auth" not in G.nodes


def test_prune_repo_returns_zero_if_not_present():
    from graphify.build import prune_repo_from_graph
    G = nx.Graph()
    G.add_node("repoA::x", repo="repoA")
    removed = prune_repo_from_graph(G, "repoB")
    assert removed == 0
    assert G.number_of_nodes() == 1


# ── global_graph.py ───────────────────────────────────────────────────────────

def test_global_add_creates_global_graph(tmp_path):
    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    _graph_to_json(G, src_graph)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add
        result = global_add(src_graph, "repoA")

    assert result["skipped"] is False
    assert result["nodes_added"] > 0
    manifest_path = global_dir / "global-manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert "repoA" in manifest["repos"]


def test_global_add_skip_on_unchanged_hash(tmp_path):
    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    _graph_to_json(G, src_graph)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add
        global_add(src_graph, "repoA")
        result2 = global_add(src_graph, "repoA")

    assert result2["skipped"] is True


def test_global_add_two_repos_no_collision(tmp_path):
    g1 = tmp_path / "graph1.json"
    g2 = tmp_path / "graph2.json"
    G1 = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    G2 = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    _graph_to_json(G1, g1)
    _graph_to_json(G2, g2)

    global_dir = tmp_path / ".graphify"
    global_graph_path = global_dir / "global-graph.json"
    global_manifest_path = global_dir / "global-manifest.json"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_graph_path), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_manifest_path):
        from graphify.global_graph import global_add, _load_global_graph
        global_add(g1, "repoA")
        global_add(g2, "repoB")
        G = _load_global_graph()

    assert "repoA::userservice" in G.nodes
    assert "repoB::userservice" in G.nodes
    assert G.number_of_nodes() == 2  # no silent merge


def test_global_remove(tmp_path):
    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    _graph_to_json(G, src_graph)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add, global_remove
        global_add(src_graph, "repoA")
        removed = global_remove("repoA")

    assert removed > 0
    # manifest should no longer list repoA - need to re-patch for list call
    global_dir2 = global_dir  # same dir
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir2), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir2 / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir2 / "global-manifest.json"):
        from graphify.global_graph import global_list
        repos = global_list()
    assert "repoA" not in repos


def test_global_remove_unknown_tag_raises(tmp_path):
    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_remove
        with pytest.raises(KeyError):
            global_remove("nonexistent")


def test_global_add_collision_warning(tmp_path, capsys):
    g1 = tmp_path / "graph1.json"
    g2 = tmp_path / "graph2.json"
    G = _make_graph([{"id": "x", "label": "X", "source_file": "x.py"}])
    _graph_to_json(G, g1)
    _graph_to_json(G, g2)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add
        global_add(g1, "myrepo")
        global_add(g2, "myrepo")  # different source path, same tag

    captured = capsys.readouterr()
    assert "warning" in captured.err.lower() or "warning" in captured.out.lower()


# ── dedup guard ───────────────────────────────────────────────────────────────

def test_dedup_raises_on_cross_repo_nodes():
    from graphify.dedup import deduplicate_entities
    nodes = [
        {"id": "repoA::userservice", "label": "UserService", "repo": "repoA"},
        {"id": "repoB::userservice", "label": "UserService", "repo": "repoB"},
    ]
    with pytest.raises(ValueError, match="multiple repos"):
        deduplicate_entities(nodes, [], communities={})


def test_dedup_ok_with_single_repo():
    from graphify.dedup import deduplicate_entities
    nodes = [
        {"id": "repoA::userservice", "label": "UserService", "repo": "repoA"},
        {"id": "repoA::auth", "label": "Auth", "repo": "repoA"},
    ]
    result_nodes, result_edges, _, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2  # no false merge


def test_dedup_ok_with_no_repo_attr():
    from graphify.dedup import deduplicate_entities
    nodes = [
        {"id": "userservice", "label": "UserService"},
        {"id": "auth", "label": "Auth"},
    ]
    result_nodes, result_edges, _, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2


# ── merge-graphs prefix ───────────────────────────────────────────────────────

def test_merge_graphs_prefixes_ids(tmp_path):
    """merge-graphs should prefix node IDs with repo name to avoid silent collision."""
    from graphify.build import prefix_graph_for_global
    from networkx.readwrite import json_graph as jg

    # Two graphs with same node ID
    G1 = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    G2 = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])

    repo1 = tmp_path / "repo1" / "graphify-out"
    repo2 = tmp_path / "repo2" / "graphify-out"
    repo1.mkdir(parents=True)
    repo2.mkdir(parents=True)

    g1_path = repo1 / "graph.json"
    g2_path = repo2 / "graph.json"
    _graph_to_json(G1, g1_path)
    _graph_to_json(G2, g2_path)

    # Simulate what merge-graphs now does (prefix before compose)
    graphs = []
    graph_paths = [g1_path, g2_path]
    for gp in graph_paths:
        data = json.loads(gp.read_text())
        if "links" not in data and "edges" in data:
            data = dict(data, links=data["edges"])
        try:
            G = jg.node_link_graph(data, edges="links")
        except TypeError:
            G = jg.node_link_graph(data)
        repo_tag = gp.parent.parent.name
        graphs.append(prefix_graph_for_global(G, repo_tag))

    merged = nx.Graph()
    for G in graphs:
        merged = nx.compose(merged, G)

    assert "repo1::userservice" in merged.nodes
    assert "repo2::userservice" in merged.nodes
    assert merged.number_of_nodes() == 2  # no silent collapse


# --- Coverage targets: lines 19-20, 33, 36-37, 45-46, 65, 85, 88-89, 107, 114-115, 155 ---

def test_load_manifest_corrupt_json(tmp_path):
    """_load_manifest handles corrupt JSON by returning default."""
    from graphify.global_graph import _load_manifest, _GLOBAL_MANIFEST
    global_dir = tmp_path / ".graphify"
    manifest_path = global_dir / "global-manifest.json"
    global_dir.mkdir(parents=True)
    manifest_path.write_text("not json {{{")
    with patch("graphify.global_graph._GLOBAL_MANIFEST", manifest_path):
        result = _load_manifest()
    assert result == {"version": 1, "repos": {}}


def test_load_global_graph_links_fallback(tmp_path):
    """_load_global_graph handles 'edges' key (converts to 'links')."""
    from networkx.readwrite import json_graph as jg
    from graphify.global_graph import _load_global_graph, _GLOBAL_GRAPH
    G = nx.Graph()
    G.add_node("a", label="A")
    data = jg.node_link_data(G, edges="links")
    # Simulate old format with 'edges' instead of 'links'
    data["edges"] = data.pop("links")
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(data))
    with patch("graphify.global_graph._GLOBAL_GRAPH", graph_path):
        loaded = _load_global_graph()
    assert loaded.number_of_nodes() == 1


def test_save_global_graph_edges_fallback(tmp_path, monkeypatch):
    """_save_global_graph handles TypeError fallback for node_link_data."""
    import networkx.readwrite.json_graph as jg
    from graphify.global_graph import _save_global_graph, _GLOBAL_GRAPH
    G = nx.Graph()
    G.add_node("a", label="A")
    graph_path = tmp_path / "graph.json"
    # Make node_link_data raise TypeError with edges="links" kwarg
    original = jg.node_link_data
    def mock_node_link_data(G, **kwargs):
        if "edges" in kwargs:
            raise TypeError("unexpected keyword")
        return original(G, edges="links")
    monkeypatch.setattr(jg, "node_link_data", mock_node_link_data)
    with patch("graphify.global_graph._GLOBAL_GRAPH", graph_path):
        _save_global_graph(G)
    assert graph_path.exists()


def test_global_add_file_not_found(tmp_path):
    """global_add raises FileNotFoundError for missing source graph."""
    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add
        with pytest.raises(FileNotFoundError, match="graph not found"):
            global_add(tmp_path / "nonexistent.json", "repoA")


def test_global_add_external_dedup(tmp_path):
    """External nodes (no source_file) with same label are deduplicated."""
    src_graph = tmp_path / "graph.json"
    G = _make_graph([
        {"id": "flask", "label": "Flask", "source_file": ""},  # external
        {"id": "userservice", "label": "UserService", "source_file": "src/user.py"},
    ])
    _graph_to_json(G, src_graph)

    global_dir = tmp_path / ".graphify"
    global_graph_path = global_dir / "global-graph.json"
    global_manifest_path = global_dir / "global-manifest.json"
    # Pre-populate global graph with same external node
    G_existing = nx.Graph()
    G_existing.add_node("repoB::flask", label="Flask", source_file="", repo="repoB")
    global_dir.mkdir(parents=True)
    from networkx.readwrite import json_graph as jg
    try:
        data_existing = jg.node_link_data(G_existing, edges="links")
    except TypeError:
        data_existing = jg.node_link_data(G_existing)
    global_graph_path.write_text(json.dumps(data_existing))
    global_manifest_path.write_text(json.dumps({"version": 1, "repos": {"repoB": {"source_hash": "abc"}}}))

    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_graph_path), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_manifest_path):
        from graphify.global_graph import global_add
        result = global_add(src_graph, "repoA")

    assert result["skipped"] is False


def test_global_path():
    """global_path() returns _GLOBAL_GRAPH Path."""
    from graphify.global_graph import global_path, _GLOBAL_GRAPH
    assert global_path() == _GLOBAL_GRAPH


# ---------------------------------------------------------------------------
# _load_global_graph — TypeError fallback (lines 36-37)
# ---------------------------------------------------------------------------

def test_load_global_graph_typeerror_fallback(tmp_path, monkeypatch):
    """When node_link_graph rejects edges='links', falls back without it."""
    import networkx.readwrite.json_graph as jg
    from graphify.global_graph import _load_global_graph, _GLOBAL_GRAPH

    # Write valid JSON data
    G = nx.Graph()
    G.add_node("a", label="A")
    graph_path = tmp_path / "global-graph.json"
    graph_path.write_text(json.dumps(jg.node_link_data(G)))

    # Make node_link_graph raise TypeError with edges="links"
    def mock_node_link_graph(data, **kwargs):
        if "edges" in kwargs:
            raise TypeError("unexpected keyword 'edges'")
        return nx.node_link_graph(data)

    monkeypatch.setattr(jg, "node_link_graph", mock_node_link_graph)

    with patch("graphify.global_graph._GLOBAL_GRAPH", graph_path):
        result = _load_global_graph()
    assert isinstance(result, nx.Graph)
    assert "a" in result.nodes


# ---------------------------------------------------------------------------
# global_add — edges format in source data (line 85)
# ---------------------------------------------------------------------------

def test_global_add_source_with_edges_not_links(tmp_path):
    """Source JSON with 'edges' key but no 'links' key should work."""
    src_graph = tmp_path / "graph.json"
    # Write JSON with "edges" format (old style), not "links"
    src_data = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}],
        "edges": [],  # "edges" not "links"
    }
    src_graph.write_text(json.dumps(src_data))

    global_dir = tmp_path / ".graphify"
    global_graph_path = global_dir / "global-graph.json"
    global_manifest_path = global_dir / "global-manifest.json"
    global_dir.mkdir(parents=True)
    global_graph_path.write_text(json.dumps({"nodes": [], "links": []}))
    global_manifest_path.write_text(json.dumps({"version": 1, "repos": {}}))

    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_graph_path), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_manifest_path):
        from graphify.global_graph import global_add
        result = global_add(src_graph, "repoA")
    assert result["skipped"] is False


# ---------------------------------------------------------------------------
# global_add — TypeError fallback for node_link_graph (lines 88-89)
# ---------------------------------------------------------------------------

def test_global_add_node_link_graph_typeerror_fallback(tmp_path, monkeypatch):
    """When node_link_graph rejects edges='links' in global_add, uses fallback."""
    import networkx.readwrite.json_graph as jg

    src_graph = tmp_path / "graph.json"
    G = _make_graph([
        {"id": "userservice", "label": "UserService", "source_file": "src/user.py"},
    ])
    _graph_to_json(G, src_graph)

    # Mock node_link_graph: first call (with edges kwarg) raises TypeError,
    # second call (fallback without edges) returns the correct graph
    call_count = [0]
    original_ng = jg.node_link_graph
    def mock_node_link_graph(data, **kwargs):
        call_count[0] += 1
        if "edges" in kwargs:
            raise TypeError("unexpected keyword 'edges'")
        # Fallback: call the real function with edges="links" explicitly
        # since our data was written with that key
        return original_ng(data, edges="links")
    monkeypatch.setattr(jg, "node_link_graph", mock_node_link_graph)
    # Fix node_link_data to also handle the edges kwarg silently
    original_nd = jg.node_link_data
    monkeypatch.setattr(jg, "node_link_data", lambda G, **kwargs: original_nd(G, edges="links"))

    global_dir = tmp_path / ".graphify"
    global_graph_path = global_dir / "global-graph.json"
    global_manifest_path = global_dir / "global-manifest.json"
    global_dir.mkdir(parents=True)
    global_graph_path.write_text(json.dumps({"nodes": [], "links": []}))
    global_manifest_path.write_text(json.dumps({"version": 1, "repos": {}}))

    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_graph_path), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_manifest_path):
        from graphify.global_graph import global_add
        result = global_add(src_graph, "repoA")
    assert result["skipped"] is False
    # Both the try and the except block should have been exercised
    assert call_count[0] >= 2


# ---------------------------------------------------------------------------
# global_add — edges skipped when nodes are deduplicated (lines 114-115)
# ---------------------------------------------------------------------------

def test_global_add_external_dedup_skips_edges(tmp_path):
    """Edges involving deduplicated external nodes are skipped."""
    src_graph = tmp_path / "graph.json"
    G = _make_graph([
        {"id": "flask", "label": "Flask", "source_file": ""},  # external
        {"id": "userservice", "label": "UserService", "source_file": "src/user.py"},
    ], [
        {"source": "flask", "target": "userservice", "relation": "uses",
         "confidence": "EXTRACTED", "source_file": ""},
    ])
    _graph_to_json(G, src_graph)

    global_dir = tmp_path / ".graphify"
    global_graph_path = global_dir / "global-graph.json"
    global_manifest_path = global_dir / "global-manifest.json"
    global_dir.mkdir(parents=True)

    # Pre-populate global graph with same external node
    G_existing = nx.Graph()
    G_existing.add_node("repoB::flask", label="Flask", source_file="", repo="repoB")
    from networkx.readwrite import json_graph as jg
    try:
        data_existing = jg.node_link_data(G_existing, edges="links")
    except TypeError:
        data_existing = jg.node_link_data(G_existing)
    global_graph_path.write_text(json.dumps(data_existing))
    global_manifest_path.write_text(json.dumps({"version": 1, "repos": {"repoB": {"source_hash": "abc"}}}))

    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_graph_path), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_manifest_path):
        from graphify.global_graph import global_add
        result = global_add(src_graph, "repoA")

    assert result["skipped"] is False
    # Flask should be deduplicated, edge flask→userservice should be skipped
    # Result should have 1 node added (userservice) instead of 2
    assert result["nodes_added"] == 1
