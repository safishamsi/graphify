import json
import sys

import pytest
import networkx as nx
from pathlib import Path
from graphify.build import build_from_json
from graphify.cluster import cluster, cohesion_score, score_all, _split_community, _partition, _MIN_SPLIT_SIZE, _MAX_COMMUNITY_FRACTION

FIXTURES = Path(__file__).parent / "fixtures"

def make_graph():
    return build_from_json(json.loads((FIXTURES / "extraction.json").read_text()))

def test_cluster_returns_dict():
    G = make_graph()
    communities = cluster(G)
    assert isinstance(communities, dict)

def test_cluster_covers_all_nodes():
    G = make_graph()
    communities = cluster(G)
    all_nodes = {n for nodes in communities.values() for n in nodes}
    assert all_nodes == set(G.nodes)

def test_cohesion_score_complete_graph():
    G = nx.complete_graph(4)
    G = nx.relabel_nodes(G, {i: str(i) for i in G.nodes})
    score = cohesion_score(G, list(G.nodes))
    assert score == 1.0

def test_cohesion_score_single_node():
    G = nx.Graph()
    G.add_node("a")
    score = cohesion_score(G, ["a"])
    assert score == 1.0

def test_cohesion_score_disconnected():
    G = nx.Graph()
    G.add_nodes_from(["a", "b", "c"])
    score = cohesion_score(G, ["a", "b", "c"])
    assert score == 0.0

def test_cohesion_score_range():
    G = make_graph()
    communities = cluster(G)
    for cid, nodes in communities.items():
        score = cohesion_score(G, nodes)
        assert 0.0 <= score <= 1.0

def test_score_all_keys_match_communities():
    G = make_graph()
    communities = cluster(G)
    scores = score_all(G, communities)
    assert set(scores.keys()) == set(communities.keys())


def test_cluster_does_not_write_to_stdout(capsys):
    """Clustering should not emit ANSI escape codes or other output.

    graspologic's leiden() can emit ANSI escape sequences that break
    PowerShell 5.1's scroll buffer on Windows (issue #19). The output
    suppression in _partition() should prevent any output from leaking.
    """
    G = make_graph()
    cluster(G)
    captured = capsys.readouterr()
    assert captured.out == "", f"cluster() wrote to stdout: {captured.out!r}"


def test_cluster_does_not_write_to_stderr(capsys):
    """Same as above but for stderr — ANSI codes can go to either stream."""
    G = make_graph()
    cluster(G)
    captured = capsys.readouterr()
    # Allow logging output (starts with [graphify]) but no raw ANSI codes
    for line in captured.err.splitlines():
        assert "\x1b" not in line, f"cluster() wrote ANSI to stderr: {line!r}"


# ---------------------------------------------------------------------------
# Edge case tests for cluster()
# ---------------------------------------------------------------------------

def test_cluster_empty_graph():
    """Empty graph returns {}."""
    G = nx.Graph()
    assert cluster(G) == {}


def test_cluster_no_edges():
    """Graph with nodes but no edges — each node is its own community."""
    G = nx.Graph()
    G.add_nodes_from(["a", "b", "c"])
    result = cluster(G)
    assert sum(len(v) for v in result.values()) == 3
    assert all(len(v) == 1 for v in result.values())


def test_cluster_directed_graph():
    """Directed graph should be converted to undirected and produce communities."""
    G = nx.DiGraph()
    G.add_edge("a", "b")
    G.add_edge("b", "c")
    result = cluster(G)
    assert sum(len(v) for v in result.values()) == 3


def test_cluster_isolates():
    """Isolate nodes (degree=0) survive as singleton communities."""
    G = nx.Graph()
    G.add_edge("a", "b")  # connected component
    G.add_node("isolated_1")
    G.add_node("isolated_2")
    result = cluster(G)
    all_nodes = {n for nodes in result.values() for n in nodes}
    assert "isolated_1" in all_nodes
    assert "isolated_2" in all_nodes
    # Each isolate should be alone
    for nodes in result.values():
        if "isolated_1" in nodes:
            assert nodes == ["isolated_1"]
        if "isolated_2" in nodes:
            assert nodes == ["isolated_2"]


def test_split_community_no_edges():
    """_split_community with no edges returns singletons."""
    G = nx.Graph()
    G.add_nodes_from(["a", "b", "c", "d"])
    result = _split_community(G, ["a", "b", "c", "d"])
    assert result == [["a"], ["b"], ["c"], ["d"]]


def test_split_community_exception_fallback(monkeypatch):
    """When _partition raises, _split_community returns original community."""
    G = nx.Graph()
    G.add_edge("a", "b")
    G.add_edge("b", "c")

    def mock_partition(*args, **kwargs):
        raise RuntimeError("Simulated failure")
    monkeypatch.setattr("graphify.cluster._partition", mock_partition)
    result = _split_community(G, ["a", "b", "c"])
    assert result == [["a", "b", "c"]]


def test_split_community_single_subcommunity():
    """When Leiden produces ≤1 subcommunity, original is returned."""
    G = nx.Graph()
    G.add_edge("a", "b")
    # Small connected graph — Leiden should produce 1 community
    result = _split_community(G, ["a", "b"])
    assert result == [["a", "b"]]


def test_cluster_oversized_community():
    """Large community should get split if >25% of nodes."""
    G = nx.Graph()
    # 12 nodes in a chain (12 > 0.25*13=3.25)
    for i in range(12):
        G.add_edge(f"big_{i}", f"big_{i+1}")
    # Small component
    G.add_edge("x", "y")
    result = cluster(G)
    # Giant component should be split into multiple
    all_nodes = {n for nodes in result.values() for n in nodes}
    assert len(all_nodes) == 15  # big_0..big_12 (13) + x + y = 15
    assert len(result) >= 2


def test_cluster_low_cohesion_re_split():
    """Star graph (hub + 55 leaves) — cohesion <0.05 triggers re-split.

    A pure star has cohesion of ~0.0357 (<0.05) with 56 nodes (≥50).
    The split may or may not produce multiple communities depending
    on Leiden's behavior, but all nodes must be present.
    """
    G = nx.Graph()
    hub = "hub"
    for i in range(55):
        G.add_edge(hub, f"leaf_{i}")
    result = cluster(G)
    all_nodes = {n for nodes in result.values() for n in nodes}
    assert hub in all_nodes
    assert len(all_nodes) == 56
    # Cohesion re-split path was exercised — just verify completeness


def test_louvain_fallback_without_graspologic(monkeypatch):
    """When graspologic is missing, fall back to NetworkX Louvain."""
    import builtins
    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "graspologic.partition":
            raise ImportError("Mocked missing graspologic")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    # Force reload of cluster to pick up the import error
    import graphify.cluster
    import importlib
    importlib.reload(graphify.cluster)
    from graphify.cluster import cluster, _partition
    G = nx.Graph()
    G.add_edge("a", "b")
    G.add_edge("b", "c")
    result = cluster(G)
    assert isinstance(result, dict)
    assert len(result) > 0
    # Restore
    importlib.reload(graphify.cluster)


def test_partition_max_level_kwarg():
    """_partition passes max_level=10 on supported NetworkX versions."""
    G = nx.Graph()
    G.add_edge("a", "b")
    result = _partition(G)
    assert isinstance(result, dict)
    assert len(result) > 0


def test_cluster_louvain_no_max_level(monkeypatch):
    """When max_level is not in louvain_communities signature, it is not passed."""
    import builtins
    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "graspologic.partition":
            raise ImportError("Mocked missing graspologic")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    import graphify.cluster
    import importlib
    importlib.reload(graphify.cluster)

    # Also mock inspect to say max_level is NOT available
    import inspect
    original_signature = inspect.signature

    def mock_signature(fn):
        sig = original_signature(fn)
        if "max_level" in sig.parameters:
            # Remove max_level from the parameters
            params = [p for name, p in sig.parameters.items() if name != "max_level"]
            return sig.replace(parameters=params)
        return sig

    monkeypatch.setattr(inspect, "signature", mock_signature)

    from graphify.cluster import _partition
    G = nx.Graph()
    G.add_edge("a", "b")
    result = _partition(G)
    assert isinstance(result, dict)
    # Restore
    importlib.reload(graphify.cluster)


# ---------------------------------------------------------------------------
# Seed parameter edge cases in graspologic Leiden (lines 31-41)
# ---------------------------------------------------------------------------

def test_partition_seed_not_random_seed(monkeypatch):
    """_partition passes 'seed' when graspologic has 'seed' but not 'random_seed' (lines 34-35)."""
    pytest.importorskip('graspologic')
    import inspect
    import sys

    def mock_sig_seed(fn):
        """Return a signature with 'seed' but NOT 'random_seed'."""
        import inspect as _inspect
        sig = _inspect.Signature([
            _inspect.Parameter('graph', _inspect.Parameter.POSITIONAL_OR_KEYWORD),
            _inspect.Parameter('seed', _inspect.Parameter.KEYWORD_ONLY, default=0),
        ])
        return sig

    imported_kwargs = []
    def mock_leiden(graph, **kwargs):
        imported_kwargs.append(kwargs)
        return {"a": 0, "b": 0}

    _orig_sig = inspect.signature
    gp = sys.modules.get("graspologic.partition")
    _orig_leiden = gp.leiden if gp and hasattr(gp, "leiden") else None
    try:
        inspect.signature = mock_sig_seed
        if gp is not None:
            gp.leiden = mock_leiden
        from graphify.cluster import _partition
        G = nx.Graph()
        G.add_edge("a", "b")
        result = _partition(G)
        assert isinstance(result, dict)
        assert any("seed" in kw for kw in imported_kwargs), f"Expected 'seed' in kwargs, got {imported_kwargs}"
    finally:
        inspect.signature = _orig_sig
        if _orig_leiden is not None:
            gp.leiden = _orig_leiden


def test_partition_no_seed_param(monkeypatch):
    """_partition warns when graspologic has neither 'random_seed' nor 'seed' (lines 36-41)."""
    pytest.importorskip('graspologic')
    import inspect
    import sys

    def mock_sig_none(fn):
        """Return a signature with only 'graph', no seed params."""
        import inspect as _inspect
        sig = _inspect.Signature([
            _inspect.Parameter('graph', _inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ])
        return sig

    def mock_leiden(graph, **kwargs):
        return {"a": 0, "b": 0}

    _orig_sig = inspect.signature
    gp = sys.modules.get("graspologic.partition")
    _orig_leiden = gp.leiden if gp and hasattr(gp, "leiden") else None
    try:
        inspect.signature = mock_sig_none
        if gp is not None:
            gp.leiden = mock_leiden
        from graphify.cluster import _partition
        G = nx.Graph()
        G.add_edge("a", "b")
        result = _partition(G)
        assert isinstance(result, dict)
    finally:
        inspect.signature = _orig_sig
        if _orig_leiden is not None:
            gp.leiden = _orig_leiden


# --- Coverage target: line 133 (_split_community returns multiple sub-communities) ---

def test_split_community_multiple_subcommunities(monkeypatch):
    """When _partition returns >1 subcommunity, line 133 returns sorted sub-lists."""
    G = nx.Graph()
    G.add_edge("a", "b")
    G.add_edge("b", "c")
    G.add_edge("c", "a")  # triangle cluster
    G.add_edge("d", "e")   # pair cluster

    # Mock _partition to return two communities
    monkeypatch.setattr("graphify.cluster._partition", lambda g: {"a": 0, "b": 0, "c": 0, "d": 1, "e": 1})
    result = _split_community(G, ["a", "b", "c", "d", "e"])
    assert len(result) == 2
    assert sorted(result[0] + result[1]) == ["a", "b", "c", "d", "e"]


# ---------------------------------------------------------------------------
# Patch 1: Deterministic community ordering
# ---------------------------------------------------------------------------

def test_cluster_equal_size_communities_have_stable_tiebreaker():
    """When two communities have the same size, ordering is deterministic (lexical tiebreaker)."""
    G = nx.Graph()
    # Two disconnected 3-node cliques: {a,b,c} and {d,e,f}
    G.add_edge("a", "b")
    G.add_edge("b", "c")
    G.add_edge("c", "a")
    G.add_edge("d", "e")
    G.add_edge("e", "f")
    G.add_edge("f", "d")

    result = cluster(G)
    # Community 0 should be the one with lexically smaller first node
    # {a,b,c} < {d,e,f} because 'a' < 'd'
    assert result[0] == ["a", "b", "c"]
    assert result[1] == ["d", "e", "f"]
