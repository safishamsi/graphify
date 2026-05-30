"""Tests for the global graph infrastructure (graphify/global_graph.py),
prefix/prune helpers in graphify/build.py, and the cross-repo guard in
graphify/dedup.py."""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest
import networkx as nx
from unittest.mock import patch

import graphify.__main__ as mainmod


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_graph(nodes, edges=None):
    """Build a simple nx.Graph from node dicts."""
    G = nx.Graph()
    for n in nodes:
        nid = n["id"]
        G.add_node(nid, **{k: v for k, v in n.items() if k != "id"})
    for e in edges or []:
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


def _make_multidigraph(nodes, edges):
    """Build an nx.MultiDiGraph from node dicts and keyed edge dicts.

    Each edge dict must carry a ``key`` so parallel edges between the same
    (source, target) survive the build and the node_link round-trip.
    """
    G = nx.MultiDiGraph()
    for n in nodes:
        nid = n["id"]
        G.add_node(nid, **{k: v for k, v in n.items() if k != "id"})
    for e in edges:
        G.add_edge(
            e["source"],
            e["target"],
            key=e["key"],
            **{k: v for k, v in e.items() if k not in ("source", "target", "key")},
        )
    return G


@contextmanager
def _patch_global(global_dir):
    """Single context manager that points global_graph at a temp dir.

    Patches ``_GLOBAL_DIR`` / ``_GLOBAL_GRAPH`` / ``_GLOBAL_MANIFEST`` for the
    duration of the ``with`` block, mirroring the inline triple-patch the older
    tests use, so the PR 8 tests can ``with _patch_global(tmp / ".graphify"):``.
    """
    with (
        patch("graphify.global_graph._GLOBAL_DIR", global_dir),
        patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"),
        patch(
            "graphify.global_graph._GLOBAL_MANIFEST",
            global_dir / "global-manifest.json",
        ),
    ):
        yield


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
    with (
        patch("graphify.global_graph._GLOBAL_DIR", global_dir),
        patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"),
        patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"),
    ):
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
    with (
        patch("graphify.global_graph._GLOBAL_DIR", global_dir),
        patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"),
        patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"),
    ):
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
    with (
        patch("graphify.global_graph._GLOBAL_DIR", global_dir),
        patch("graphify.global_graph._GLOBAL_GRAPH", global_graph_path),
        patch("graphify.global_graph._GLOBAL_MANIFEST", global_manifest_path),
    ):
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
    with (
        patch("graphify.global_graph._GLOBAL_DIR", global_dir),
        patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"),
        patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"),
    ):
        from graphify.global_graph import global_add, global_remove

        global_add(src_graph, "repoA")
        removed = global_remove("repoA")

    assert removed > 0
    # manifest should no longer list repoA - need to re-patch for list call
    global_dir2 = global_dir  # same dir
    with (
        patch("graphify.global_graph._GLOBAL_DIR", global_dir2),
        patch("graphify.global_graph._GLOBAL_GRAPH", global_dir2 / "global-graph.json"),
        patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir2 / "global-manifest.json"),
    ):
        from graphify.global_graph import global_list

        repos = global_list()
    assert "repoA" not in repos


def test_global_remove_backs_up_before_overwrite(tmp_path):
    """Removing a repo mutates global-graph.json, so recovery policy requires a backup."""
    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    _graph_to_json(G, src_graph)

    global_dir = tmp_path / ".graphify"
    global_graph_path = global_dir / "global-graph.json"
    with (
        patch("graphify.global_graph._GLOBAL_DIR", global_dir),
        patch("graphify.global_graph._GLOBAL_GRAPH", global_graph_path),
        patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"),
    ):
        from graphify.global_graph import global_add, global_remove

        global_add(src_graph, "repoA")
        before_remove = global_graph_path.read_bytes()
        removed = global_remove("repoA")

    assert removed > 0
    backups = list(global_dir.glob("global-graph.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == before_remove


def test_global_remove_unknown_tag_raises(tmp_path):
    global_dir = tmp_path / ".graphify"
    with (
        patch("graphify.global_graph._GLOBAL_DIR", global_dir),
        patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"),
        patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"),
    ):
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
    with (
        patch("graphify.global_graph._GLOBAL_DIR", global_dir),
        patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"),
        patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"),
    ):
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
    result_nodes, result_edges = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2  # no false merge


def test_dedup_ok_with_no_repo_attr():
    from graphify.dedup import deduplicate_entities

    nodes = [
        {"id": "userservice", "label": "UserService"},
        {"id": "auth", "label": "Auth"},
    ]
    result_nodes, result_edges = deduplicate_entities(nodes, [], communities={})
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


def test_global_add_rejects_oversized_source_graph(monkeypatch, tmp_path):
    """#F4: global_add must refuse to read a source graph.json that
    exceeds the size cap, rather than json.loads-ing it into memory."""
    import pytest

    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "x", "label": "X", "source_file": "src/x.py"}])
    _graph_to_json(G, src_graph)

    global_dir = tmp_path / ".graphify"
    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 8)
    with (
        patch("graphify.global_graph._GLOBAL_DIR", global_dir),
        patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"),
        patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"),
    ):
        from graphify.global_graph import global_add

        with pytest.raises(ValueError, match="exceeds"):
            global_add(src_graph, "repoA")


# ── PR 8: keyed/class-normalized composition, recovery, backup ─────────────────


def _PARALLEL_NODES():
    return [
        {"id": "a", "label": "A", "source_file": "src/a.py"},
        {"id": "b", "label": "B", "source_file": "src/b.py"},
    ]


def _PARALLEL_EDGES():
    return [
        {"source": "a", "target": "b", "key": "calls:L1", "relation": "calls"},
        {"source": "a", "target": "b", "key": "imports:L2", "relation": "imports"},
    ]


def test_global_add_multidigraph_preserves_parallel_edges(tmp_path):
    """A MultiDiGraph source with parallel edges keeps every keyed edge in the
    global graph, which reloads as a MultiDiGraph (no keyless collapse)."""
    src_graph = tmp_path / "graph.json"
    M = _make_multidigraph(_PARALLEL_NODES(), _PARALLEL_EDGES())
    _graph_to_json(M, src_graph)

    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add, _load_global_graph

        result = global_add(src_graph, "repoA")
        G = _load_global_graph()

    assert result["skipped"] is False
    assert isinstance(G, nx.MultiDiGraph)
    assert G.number_of_edges("repoA::a", "repoA::b") == 2
    assert sorted(G["repoA::a"]["repoA::b"].keys()) == ["calls:L1", "imports:L2"]
    assert G.graph["graphify_profile"]["graph_type"] == "multidigraph"


def test_global_add_multidigraph_idempotent_under_repeat(tmp_path):
    """THE PR-7-lesson test: running global_add of the SAME multigraph repo 3
    times keeps the parallel-edge count, edge keys, and stored profile identical
    after every run — no duplication, no drift, no re-collapse.

    To prove the KEYED COMPOSE itself is idempotent (not merely the hash-skip
    short-circuit), the second repo's source is mutated to a fresh hash on every
    iteration while the FIRST repo (repoA) survives the prune and is re-composed
    through the keyed edge path each time. repoA's parallel edges must stay
    rock-stable across all three forced re-composes."""
    repo_a_src = tmp_path / "a.json"
    M_a = _make_multidigraph(_PARALLEL_NODES(), _PARALLEL_EDGES())
    _graph_to_json(M_a, repo_a_src)

    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add, _load_global_graph

        global_add(repo_a_src, "repoA")

        observed = []
        for i in range(3):
            # Distinct second repo each iteration → forces a real re-compose that
            # re-runs the keyed edge loop over the surviving repoA subgraph.
            churn_src = tmp_path / f"churn_{i}.json"
            M_b = _make_multidigraph(
                [
                    {"id": f"c{i}", "label": f"C{i}", "source_file": "src/c.py"},
                    {"id": f"d{i}", "label": f"D{i}", "source_file": "src/d.py"},
                ],
                [
                    {"source": f"c{i}", "target": f"d{i}", "key": "j1", "relation": "calls"},
                    {"source": f"c{i}", "target": f"d{i}", "key": "j2", "relation": "uses"},
                ],
            )
            _graph_to_json(M_b, churn_src)
            global_add(churn_src, "repoB")

            G = _load_global_graph()
            observed.append(
                (
                    G.number_of_edges("repoA::a", "repoA::b"),
                    tuple(sorted(G["repoA::a"]["repoA::b"].keys())),
                    G.graph["graphify_profile"]["graph_type"],
                )
            )

    # IDEMPOTENCE ASSERTION: parallel-edge count (2), keys, and profile identical
    # after each of the three repeated global_add re-composes — no drift.
    assert observed == [
        (2, ("calls:L1", "imports:L2"), "multidigraph"),
        (2, ("calls:L1", "imports:L2"), "multidigraph"),
        (2, ("calls:L1", "imports:L2"), "multidigraph"),
    ]


def test_global_add_mixed_simple_and_multi_no_crash(tmp_path):
    """One simple repo + one multi repo must not crash through a NetworkX class
    mismatch; the global target upgrades to multidigraph and both repos' edges
    are present (the multi repo keyed)."""
    simple_src = tmp_path / "simple.json"
    S = _make_graph(
        [
            {"id": "x", "label": "X", "source_file": "src/x.py"},
            {"id": "y", "label": "Y", "source_file": "src/y.py"},
        ],
        [{"source": "x", "target": "y", "relation": "calls"}],
    )
    _graph_to_json(S, simple_src)

    multi_src = tmp_path / "multi.json"
    M = _make_multidigraph(_PARALLEL_NODES(), _PARALLEL_EDGES())
    _graph_to_json(M, multi_src)

    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add, _load_global_graph

        global_add(simple_src, "repoSimple")
        # Composing a multi repo into the existing simple global graph must not
        # raise "All graphs must be directed or undirected."
        global_add(multi_src, "repoMulti")
        G = _load_global_graph()

    assert isinstance(G, nx.MultiDiGraph)
    assert G.graph["graphify_profile"]["graph_type"] == "multidigraph"
    # simple repo's single edge survives (folded into the multigraph)
    assert G.has_edge("repoSimple::x", "repoSimple::y")
    # multi repo's parallel edges survive distinctly, keyed
    assert G.number_of_edges("repoMulti::a", "repoMulti::b") == 2
    assert sorted(G["repoMulti::a"]["repoMulti::b"].keys()) == ["calls:L1", "imports:L2"]


def test_global_add_simple_only_regression(tmp_path):
    """Pure simple inputs produce a simple global graph whose output is unchanged
    apart from the new graphify_profile metadata. Repeating twice is identical."""
    g1 = tmp_path / "g1.json"
    g2 = tmp_path / "g2.json"
    _graph_to_json(
        _make_graph(
            [
                {"id": "u", "label": "U", "source_file": "src/u.py"},
                {"id": "v", "label": "V", "source_file": "src/v.py"},
            ],
            [{"source": "u", "target": "v", "relation": "calls"}],
        ),
        g1,
    )
    _graph_to_json(
        _make_graph([{"id": "w", "label": "W", "source_file": "src/w.py"}]),
        g2,
    )

    global_dir = tmp_path / ".graphify"
    global_graph_path = global_dir / "global-graph.json"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add, _load_global_graph

        global_add(g1, "repoA")
        global_add(g2, "repoB")
        G = _load_global_graph()
        first_bytes = global_graph_path.read_text(encoding="utf-8")

        # Repeat the same two adds (hash-skip path) → byte-identical output.
        global_add(g1, "repoA")
        global_add(g2, "repoB")
        second_bytes = global_graph_path.read_text(encoding="utf-8")

    # Simple-only stays a simple Graph (not upgraded), profile is "simple".
    assert isinstance(G, nx.Graph)
    assert not G.is_multigraph()
    assert not G.is_directed()
    assert G.graph["graphify_profile"]["graph_type"] == "simple"
    assert G.has_edge("repoA::u", "repoA::v")
    assert "repoB::w" in G.nodes
    # Byte-stable across repeated adds (idempotent simple output).
    assert first_bytes == second_bytes


def test_normalize_graphs_for_global_infers_target(recwarn):
    """Mixed inputs infer multidigraph; an explicit simple target on a multi
    input warns and projects the multigraph down to simple."""
    from graphify.global_graph import normalize_graphs_for_global

    simple = _make_graph([{"id": "x"}, {"id": "y"}], [{"source": "x", "target": "y"}])
    multi = _make_multidigraph(
        [{"id": "a"}, {"id": "b"}],
        [
            {"source": "a", "target": "b", "key": "k1"},
            {"source": "a", "target": "b", "key": "k2"},
        ],
    )

    # Inference: any multi input → multidigraph target, no warning, no collapse.
    normalized, target = normalize_graphs_for_global([simple, multi])
    assert target == "multidigraph"
    assert all(isinstance(g, nx.MultiDiGraph) for g in normalized)
    assert normalized[1].number_of_edges("a", "b") == 2
    assert len(recwarn.list) == 0

    # Explicit simple target with a multi input → WARNING + projection to simple.
    with pytest.warns(UserWarning, match="collaps"):
        normalized2, target2 = normalize_graphs_for_global([simple, multi], target_type="simple")
    assert target2 == "simple"
    assert all(type(g) is nx.Graph for g in normalized2)
    # Parallel edges collapse to a single (a, b) pair on the simple projection.
    assert normalized2[1].number_of_edges() == 1

    # Unknown target token is rejected.
    with pytest.raises(ValueError, match="target_type"):
        normalize_graphs_for_global([simple], target_type="bogus")


def test_detect_pre_profile_global_graph():
    """A JSON without graphify_profile and without multigraph/directed flags is
    detected as pre-profile; any of those markers clears the flag."""
    from graphify.global_graph import detect_pre_profile

    assert detect_pre_profile({"nodes": [{"id": "a"}], "links": []}) is True
    # Top-level profile present → not pre-profile.
    assert detect_pre_profile({"nodes": [], "links": [], "graphify_profile": {}}) is False
    # Nested profile under "graph" → not pre-profile.
    assert (
        detect_pre_profile(
            {"nodes": [], "links": [], "graph": {"graphify_profile": {"graph_type": "simple"}}}
        )
        is False
    )
    # Explicit class flags → writer knew the class → not pre-profile.
    assert detect_pre_profile({"nodes": [], "links": [], "multigraph": False}) is False
    assert detect_pre_profile({"nodes": [], "links": [], "directed": True}) is False
    assert detect_pre_profile("not a dict") is False


def test_pre_profile_upgrade_refused_with_recovery_message(tmp_path):
    """Upgrading a pre-profile global graph to multidigraph refuses with a clear
    recovery message and does NOT mutate/destroy the existing global-graph.json."""
    from graphify.global_graph import (
        GlobalGraphRecoveryError,
        refuse_pre_profile_upgrade,
    )

    # Direct helper contract: pre-profile + multidigraph target → raises.
    pre_profile = {"nodes": [{"id": "a"}], "links": []}
    with pytest.raises(GlobalGraphRecoveryError, match="rebuild|remove|backup|pre-profile"):
        refuse_pre_profile_upgrade(pre_profile, "multidigraph")
    # Non-upgrade targets are allowed (no raise).
    refuse_pre_profile_upgrade(pre_profile, "simple")
    refuse_pre_profile_upgrade(pre_profile, "digraph")

    # End-to-end through global_add: seed a pre-profile global graph (no profile,
    # no flags), then add a multigraph repo → upgrade refused, file untouched.
    global_dir = tmp_path / ".graphify"
    global_dir.mkdir(parents=True)
    global_graph_path = global_dir / "global-graph.json"
    pre_profile_disk = {
        "nodes": [{"id": "legacy::old", "repo": "legacy", "label": "Old"}],
        "links": [],
    }
    original = json.dumps(pre_profile_disk, indent=2)
    global_graph_path.write_text(original, encoding="utf-8")

    multi_src = tmp_path / "multi.json"
    _graph_to_json(_make_multidigraph(_PARALLEL_NODES(), _PARALLEL_EDGES()), multi_src)

    with _patch_global(global_dir):
        from graphify.global_graph import global_add

        with pytest.raises(GlobalGraphRecoveryError):
            global_add(multi_src, "repoMulti")

    # The original pre-profile graph.json must be intact (not overwritten).
    assert global_graph_path.read_text(encoding="utf-8") == original
    # A recovery backup may have been taken alongside it; that is allowed.


def test_global_add_backs_up_before_overwrite(tmp_path):
    """A backup snapshot of the prior global-graph.json is created before an
    overwrite, and the original content is recoverable from the backup."""
    global_dir = tmp_path / ".graphify"

    g1 = tmp_path / "g1.json"
    _graph_to_json(_make_graph([{"id": "u", "label": "U", "source_file": "src/u.py"}]), g1)
    g2 = tmp_path / "g2.json"
    _graph_to_json(_make_graph([{"id": "w", "label": "W", "source_file": "src/w.py"}]), g2)

    with _patch_global(global_dir):
        from graphify.global_graph import global_add

        global_add(g1, "repoA")
        first = (global_dir / "global-graph.json").read_text(encoding="utf-8")
        # Second add (different repo, different hash) overwrites → backup taken.
        global_add(g2, "repoB")

    backups = list(global_dir.glob("global-graph.*.bak"))
    assert backups, "expected a dated .bak snapshot before overwrite"
    # The backup holds the pre-overwrite (first-add) state, recoverable verbatim.
    assert backups[0].read_text(encoding="utf-8") == first


def test_backup_global_graph_idempotent(tmp_path):
    """Repeated backup_global_graph() calls in the same run do not error and do
    not corrupt the snapshot (one dated backup, byte-stable)."""
    global_dir = tmp_path / ".graphify"
    global_dir.mkdir(parents=True)
    global_graph_path = global_dir / "global-graph.json"
    content = json.dumps({"nodes": [{"id": "a"}], "links": []}, indent=2)
    global_graph_path.write_text(content, encoding="utf-8")

    with _patch_global(global_dir):
        from graphify.global_graph import backup_global_graph

        p1 = backup_global_graph()
        p2 = backup_global_graph()
        p3 = backup_global_graph()

    assert p1 is not None
    assert p1 == p2 == p3  # same dated backup path
    assert p1.read_text(encoding="utf-8") == content
    # Exactly one backup file (no proliferation across repeated calls).
    assert len(list(global_dir.glob("global-graph.*.bak"))) == 1


def test_backup_global_graph_none_when_absent(tmp_path):
    """backup_global_graph() returns None when there is no global graph to back
    up (nothing to snapshot, never raises)."""
    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import backup_global_graph

        assert backup_global_graph() is None


# ── merge-driver / merge-graphs class normalization (PR 8) ─────────────────────
#
# Both commands run in-process through ``graphify.__main__.main`` with argv
# monkeypatched (env-isolated, mirroring test_extract_cli / test_query_cli). The
# go/no-go gate for PR 8: mixed graph inputs never crash through a NetworkX class
# mismatch AND never silently collapse multigraph input without an explicit
# simple target. Merge is STATEFUL, so every path is also asserted under REPEATED
# application (run 2-3×) to prove idempotence — no duplicated edges, no key drift,
# no profile drift, no re-collapse.


def _reload_graph(path):
    """Rehydrate a graph.json written by a merge command (handles edges/links)."""
    from networkx.readwrite import json_graph as jg

    data = json.loads(path.read_text(encoding="utf-8"))
    if "links" not in data and "edges" in data:
        data = dict(data, links=data["edges"])
    try:
        return jg.node_link_graph(data, edges="links"), data
    except TypeError:
        return jg.node_link_graph(data), data


def _edge_keys(G):
    """Stable, comparable edge identity: keyed triples for multigraphs, else pairs."""
    if G.is_multigraph():
        return sorted((u, v, k) for u, v, k in G.edges(keys=True))
    return sorted(G.edges())


def _run_merge_driver(monkeypatch, base_p, current_p, other_p):
    """Invoke `graphify merge-driver` in-process; return the exit code (0 on ok)."""
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "merge-driver", str(base_p), str(current_p), str(other_p)],
    )
    try:
        mainmod.main()
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1


def _run_merge_graphs(monkeypatch, paths, out_path, *flags):
    """Invoke `graphify merge-graphs` in-process; return the exit code (0 on ok)."""
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    argv = ["graphify", "merge-graphs", *[str(p) for p in paths], "--out", str(out_path), *flags]
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    try:
        mainmod.main()
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1


def _repo_graph(root, repo, G):
    """Write *G* to <root>/<repo>/graphify-out/graph.json (merge-graphs layout)."""
    out_dir = root / repo / "graphify-out"
    out_dir.mkdir(parents=True)
    gp = out_dir / "graph.json"
    _graph_to_json(G, gp)
    return gp


def test_merge_driver_mixed_classes_no_crash(monkeypatch, tmp_path):
    """merge-driver: simple `current` + MultiDiGraph `other` must NOT crash through
    a NetworkX class mismatch; the result is a keyed multidigraph that preserves
    both sides' edges. This is the core go/no-go gate."""
    current = _make_graph(
        [
            {"id": "a", "label": "A", "source_file": "a.py"},
            {"id": "b", "label": "B", "source_file": "b.py"},
        ],
        [{"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED"}],
    )
    other = _make_multidigraph(
        [
            {"id": "a", "label": "A", "source_file": "a.py"},
            {"id": "c", "label": "C", "source_file": "c.py"},
        ],
        [
            {"source": "a", "target": "c", "key": 0, "relation": "imports"},
            {"source": "a", "target": "c", "key": 1, "relation": "calls"},
        ],
    )
    base_p = tmp_path / "base.json"
    current_p = tmp_path / "current.json"
    other_p = tmp_path / "other.json"
    _graph_to_json(_make_graph([]), base_p)
    _graph_to_json(current, current_p)
    _graph_to_json(other, other_p)

    code = _run_merge_driver(monkeypatch, base_p, current_p, other_p)
    assert code == 0  # no class-mismatch crash → clean exit, not a surfaced conflict

    merged, data = _reload_graph(current_p)
    assert merged.is_multigraph()  # upgraded to the multi target, not collapsed
    assert data["graph"]["graphify_profile"]["graph_type"] == "multidigraph"
    # Both the simple edge and BOTH parallel multi edges survive.
    assert ("a", "b", 0) in _edge_keys(merged)
    assert ("a", "c", 0) in _edge_keys(merged)
    assert ("a", "c", 1) in _edge_keys(merged)
    assert merged.number_of_edges() == 3


def test_merge_driver_idempotent_under_repeat(monkeypatch, tmp_path):
    """STATEFUL idempotence: running merge-driver on the SAME inputs 3× must keep
    the edge count, edge KEYS and stored profile identical every time — no
    duplicated edges, no key drift, no re-collapse. The merge-driver writes back
    to `current`, so each rerun re-loads its own multidigraph output as `current`;
    the keyed compose must overwrite the same (u, v, key) slots, not accumulate."""
    current = _make_graph(
        [
            {"id": "a", "label": "A", "source_file": "a.py"},
            {"id": "b", "label": "B", "source_file": "b.py"},
        ],
        [{"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED"}],
    )
    other = _make_multidigraph(
        [
            {"id": "a", "label": "A", "source_file": "a.py"},
            {"id": "c", "label": "C", "source_file": "c.py"},
        ],
        [
            {"source": "a", "target": "c", "key": 0, "relation": "imports"},
            {"source": "a", "target": "c", "key": 1, "relation": "calls"},
        ],
    )
    base_p = tmp_path / "base.json"
    current_p = tmp_path / "current.json"
    other_p = tmp_path / "other.json"
    _graph_to_json(_make_graph([]), base_p)
    _graph_to_json(current, current_p)
    _graph_to_json(other, other_p)

    snapshots = []
    for _ in range(3):
        assert _run_merge_driver(monkeypatch, base_p, current_p, other_p) == 0
        merged, data = _reload_graph(current_p)
        snapshots.append(
            (
                merged.number_of_edges(),
                _edge_keys(merged),
                data["graph"]["graphify_profile"]["graph_type"],
            )
        )

    # The exact stability assertion: edges + keys + profile identical across all 3 runs.
    assert snapshots[0] == snapshots[1] == snapshots[2]
    assert snapshots[0][0] == 3  # 1 simple + 2 parallel, never duplicated
    assert snapshots[0][2] == "multidigraph"


def test_merge_graphs_multidigraph_preserves_parallel_edges(monkeypatch, tmp_path):
    """merge-graphs over a multigraph + a simple input keeps parallel edges with
    distinct keys (resolved target inferred as multidigraph, not collapsed)."""
    multi = _make_multidigraph(
        [
            {"id": "x", "label": "X", "source_file": "x.py"},
            {"id": "y", "label": "Y", "source_file": "y.py"},
        ],
        [
            {"source": "x", "target": "y", "key": 0, "relation": "calls"},
            {"source": "x", "target": "y", "key": 1, "relation": "imports"},
        ],
    )
    simple = _make_graph(
        [
            {"id": "z", "label": "Z", "source_file": "z.py"},
            {"id": "w", "label": "W", "source_file": "w.py"},
        ],
        [{"source": "z", "target": "w", "relation": "uses"}],
    )
    g1 = _repo_graph(tmp_path, "repo1", multi)
    g2 = _repo_graph(tmp_path, "repo2", simple)
    out_p = tmp_path / "merged.json"

    assert _run_merge_graphs(monkeypatch, [g1, g2], out_p) == 0
    merged, data = _reload_graph(out_p)
    assert merged.is_multigraph()
    assert data["graph"]["graphify_profile"]["graph_type"] == "multidigraph"
    # Both parallel edges survive (prefixed by repo tag), distinct keys retained.
    keys = _edge_keys(merged)
    assert ("repo1::x", "repo1::y", 0) in keys
    assert ("repo1::x", "repo1::y", 1) in keys
    assert merged.number_of_edges() == 3  # 2 parallel + 1 simple


def test_merge_graphs_idempotent_under_repeat(monkeypatch, tmp_path):
    """STATEFUL idempotence: the SAME merge-graphs run repeated 3× yields a stable
    output — edge count, keys and profile unchanged (no duplicated parallel edges,
    no key drift, no re-collapse). Inputs are read fresh each run; only the output
    is overwritten, so stability proves the keyed compose is deterministic."""
    multi = _make_multidigraph(
        [
            {"id": "x", "label": "X", "source_file": "x.py"},
            {"id": "y", "label": "Y", "source_file": "y.py"},
        ],
        [
            {"source": "x", "target": "y", "key": 0, "relation": "calls"},
            {"source": "x", "target": "y", "key": 1, "relation": "imports"},
        ],
    )
    simple = _make_graph(
        [{"id": "z", "label": "Z", "source_file": "z.py"}],
        [],
    )
    g1 = _repo_graph(tmp_path, "repo1", multi)
    g2 = _repo_graph(tmp_path, "repo2", simple)
    out_p = tmp_path / "merged.json"

    snapshots = []
    for _ in range(3):
        assert _run_merge_graphs(monkeypatch, [g1, g2], out_p) == 0
        merged, data = _reload_graph(out_p)
        snapshots.append(
            (
                merged.number_of_edges(),
                _edge_keys(merged),
                data["graph"]["graphify_profile"]["graph_type"],
            )
        )
    assert snapshots[0] == snapshots[1] == snapshots[2]
    assert snapshots[0][0] == 2  # 2 parallel edges, never duplicated to 4
    assert snapshots[0][2] == "multidigraph"


def test_merge_graphs_explicit_simple_target_warns_on_multi(monkeypatch, tmp_path, capsys):
    """An EXPLICIT --simple target over a multigraph input projects DOWN to simple
    WITH a warning (intentional, audible collapse) — never a silent collapse."""
    multi = _make_multidigraph(
        [
            {"id": "x", "label": "X", "source_file": "x.py"},
            {"id": "y", "label": "Y", "source_file": "y.py"},
        ],
        [
            {"source": "x", "target": "y", "key": 0, "relation": "calls"},
            {"source": "x", "target": "y", "key": 1, "relation": "imports"},
        ],
    )
    simple = _make_graph(
        [{"id": "z", "label": "Z", "source_file": "z.py"}],
        [],
    )
    g1 = _repo_graph(tmp_path, "repo1", multi)
    g2 = _repo_graph(tmp_path, "repo2", simple)
    out_p = tmp_path / "merged.json"

    with pytest.warns(UserWarning, match="multigraph"):
        assert _run_merge_graphs(monkeypatch, [g1, g2], out_p, "--simple") == 0

    # Loud collapse: a WARNING is also emitted on stderr, and the result is simple.
    err = capsys.readouterr().err
    assert "WARNING" in err and "multigraph" in err
    merged, data = _reload_graph(out_p)
    assert not merged.is_multigraph() and not merged.is_directed()
    assert data["graph"]["graphify_profile"]["graph_type"] == "simple"
    # Parallel edges folded onto a single (x, y) pair (the explicit, warned choice).
    assert merged.number_of_edges() == 1


def test_merge_simple_only_regression(monkeypatch, tmp_path):
    """Pure simple inputs → simple output, byte-stable across repeated runs (the
    default no-flag path must not upgrade or perturb a simple-only merge)."""
    s1 = _make_graph(
        [
            {"id": "a", "label": "A", "source_file": "a.py"},
            {"id": "b", "label": "B", "source_file": "b.py"},
        ],
        [{"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED"}],
    )
    s2 = _make_graph(
        [
            {"id": "c", "label": "C", "source_file": "c.py"},
            {"id": "d", "label": "D", "source_file": "d.py"},
        ],
        [{"source": "c", "target": "d", "relation": "uses", "confidence": "EXTRACTED"}],
    )
    g1 = _repo_graph(tmp_path, "repo1", s1)
    g2 = _repo_graph(tmp_path, "repo2", s2)
    out_p = tmp_path / "merged.json"

    assert _run_merge_graphs(monkeypatch, [g1, g2], out_p) == 0
    first = out_p.read_text(encoding="utf-8")
    assert _run_merge_graphs(monkeypatch, [g1, g2], out_p) == 0
    second = out_p.read_text(encoding="utf-8")

    assert first == second  # byte-stable under repeat
    merged, data = _reload_graph(out_p)
    assert not merged.is_multigraph() and not merged.is_directed()  # stays simple
    assert data["graph"]["graphify_profile"]["graph_type"] == "simple"
    assert merged.number_of_edges() == 2  # no silent multi upgrade


def test_merge_backs_up_before_overwrite(monkeypatch, tmp_path):
    """An overwriting merge writes a dated .bak sibling of the pre-merge target
    first, so the previous state is recoverable."""
    s1 = _make_graph([{"id": "a", "label": "A", "source_file": "a.py"}], [])
    s2 = _make_graph([{"id": "b", "label": "B", "source_file": "b.py"}], [])
    g1 = _repo_graph(tmp_path, "repo1", s1)
    g2 = _repo_graph(tmp_path, "repo2", s2)
    out_p = tmp_path / "merged.json"

    # Pre-seed an existing output so the merge OVERWRITES it (triggers backup).
    sentinel = _make_graph([{"id": "old", "label": "OLD", "source_file": "old.py"}], [])
    _graph_to_json(sentinel, out_p)
    sentinel_bytes = out_p.read_bytes()

    monkeypatch.delenv("GRAPHIFY_NO_BACKUP", raising=False)
    assert _run_merge_graphs(monkeypatch, [g1, g2], out_p) == 0

    backups = list(tmp_path.glob("merged.*.bak"))
    assert len(backups) == 1  # exactly one dated backup sibling, no proliferation
    assert backups[0].read_bytes() == sentinel_bytes  # holds the PRE-overwrite state


def test_merge_pre_profile_refused(monkeypatch, tmp_path):
    """Merging that would UPGRADE a pre-profile graph (no graphify_profile /
    multigraph / directed markers) to a multidigraph target is refused with a
    recovery message, leaving the target file unmutated — its lost parallel edges
    cannot be reconstructed by an in-place upgrade."""
    from networkx.readwrite import json_graph as jg

    # A pre-profile `current`: strip the multigraph/directed flags AND any profile
    # so detect_pre_profile() classifies it as predating class tracking.
    current = _make_graph(
        [
            {"id": "a", "label": "A", "source_file": "a.py"},
            {"id": "b", "label": "B", "source_file": "b.py"},
        ],
        [{"source": "a", "target": "b", "relation": "calls"}],
    )
    current_p = tmp_path / "current.json"
    raw = jg.node_link_data(current, edges="links")
    raw.pop("multigraph", None)
    raw.pop("directed", None)
    raw.pop("graph", None)  # no graphify_profile anywhere → pre-profile
    current_p.write_text(json.dumps(raw), encoding="utf-8")
    pre_bytes = current_p.read_bytes()

    # `other` is a multigraph → the merge would upgrade `current` to multidigraph.
    other = _make_multidigraph(
        [
            {"id": "a", "label": "A", "source_file": "a.py"},
            {"id": "c", "label": "C", "source_file": "c.py"},
        ],
        [
            {"source": "a", "target": "c", "key": 0, "relation": "imports"},
            {"source": "a", "target": "c", "key": 1, "relation": "calls"},
        ],
    )
    base_p = tmp_path / "base.json"
    other_p = tmp_path / "other.json"
    _graph_to_json(_make_graph([]), base_p)
    _graph_to_json(other, other_p)

    code = _run_merge_driver(monkeypatch, base_p, current_p, other_p)
    assert code == 1  # refused → surfaced as a conflict, not silently upgraded
    assert current_p.read_bytes() == pre_bytes  # target left unmutated


def _write_pre_profile_graph(path, nodes, edges):
    """Write a LEGACY pre-profile graph.json: bare nodes + links, NO graphify_profile
    and NO multigraph/directed flags, so detect_pre_profile() treats it as predating
    class tracking (it may already be a silently-collapsed simple graph)."""
    from networkx.readwrite import json_graph as jg

    G = _make_graph(nodes, edges)
    raw = jg.node_link_data(G, edges="links")
    raw.pop("multigraph", None)
    raw.pop("directed", None)
    raw.pop("graph", None)
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_merge_driver_pre_profile_other_does_not_block(monkeypatch, tmp_path):
    """REGRESSION for the narrowed pre-profile refusal: when `current` is a real
    MultiDiGraph and `other` is a LEGACY pre-profile simple graph, the merge must
    SUCCEED — `other` is read-only (merged in, never rewritten), so its pre-profile
    status implies no unreconstructable in-place loss. Before the fix the refusal
    loop also inspected `other`, false-positive-blocking this valid merge with a
    misleading 'global-graph.json / rebuild from source' recovery message."""
    # `current`: a genuine MultiDiGraph (carries multigraph:true + parallel edges).
    current = _make_multidigraph(
        [
            {"id": "a", "label": "A", "source_file": "a.py"},
            {"id": "b", "label": "B", "source_file": "b.py"},
        ],
        [
            {"source": "a", "target": "b", "key": 0, "relation": "calls"},
            {"source": "a", "target": "b", "key": 1, "relation": "imports"},
        ],
    )
    current_p = tmp_path / "current.json"
    _graph_to_json(current, current_p)

    # `other`: a legacy pre-profile simple graph (no profile / multigraph flags).
    other_p = tmp_path / "other.json"
    _write_pre_profile_graph(
        other_p,
        [
            {"id": "a", "label": "A", "source_file": "a.py"},
            {"id": "c", "label": "C", "source_file": "c.py"},
        ],
        [{"source": "a", "target": "c", "relation": "uses"}],
    )

    base_p = tmp_path / "base.json"
    _graph_to_json(_make_graph([]), base_p)

    code = _run_merge_driver(monkeypatch, base_p, current_p, other_p)
    assert code == 0  # NOT refused — a pre-profile `other` must not block the merge

    merged, data = _reload_graph(current_p)
    assert merged.is_multigraph()  # current stays multidigraph, not collapsed
    assert data["graph"]["graphify_profile"]["graph_type"] == "multidigraph"
    keys = _edge_keys(merged)
    # current's parallel edges preserved...
    assert ("a", "b", 0) in keys
    assert ("a", "b", 1) in keys
    # ...and other's edge is merged in (keyed onto the multi target).
    assert ("a", "c", 0) in keys
    assert merged.number_of_edges() == 3


def test_merge_driver_pre_profile_current_still_refused(monkeypatch, tmp_path):
    """Confirm the guard STILL fires for the legitimate case after the fix narrowed
    its scope: `current` is a pre-profile simple graph and `other` is a MultiDiGraph,
    so the inferred target is multidigraph and the merge would upgrade the
    OVERWRITTEN current in place (its lost parallels unreconstructable). merge-driver
    must REFUSE (exit 1, recovery message) and leave current unmutated — proving the
    fix did not disable the real protection."""
    current_p = tmp_path / "current.json"
    _write_pre_profile_graph(
        current_p,
        [
            {"id": "a", "label": "A", "source_file": "a.py"},
            {"id": "b", "label": "B", "source_file": "b.py"},
        ],
        [{"source": "a", "target": "b", "relation": "calls"}],
    )
    pre_bytes = current_p.read_bytes()

    other = _make_multidigraph(
        [
            {"id": "a", "label": "A", "source_file": "a.py"},
            {"id": "c", "label": "C", "source_file": "c.py"},
        ],
        [
            {"source": "a", "target": "c", "key": 0, "relation": "imports"},
            {"source": "a", "target": "c", "key": 1, "relation": "calls"},
        ],
    )
    base_p = tmp_path / "base.json"
    other_p = tmp_path / "other.json"
    _graph_to_json(_make_graph([]), base_p)
    _graph_to_json(other, other_p)

    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "merge-driver", str(base_p), str(current_p), str(other_p)],
    )
    import pytest as _pytest

    with _pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    assert exc_info.value.code == 1  # the real protection still fires
    assert current_p.read_bytes() == pre_bytes  # current left unmutated


def test_merge_driver_pre_profile_current_refusal_message(monkeypatch, tmp_path, capsys):
    """Companion to the refusal test: the refusal prints the recovery message
    (rebuild-from-source guidance), not a silent failure."""
    current_p = tmp_path / "current.json"
    _write_pre_profile_graph(
        current_p,
        [{"id": "a", "label": "A", "source_file": "a.py"}],
        [],
    )
    other = _make_multidigraph(
        [
            {"id": "a", "label": "A", "source_file": "a.py"},
            {"id": "c", "label": "C", "source_file": "c.py"},
        ],
        [
            {"source": "a", "target": "c", "key": 0, "relation": "imports"},
            {"source": "a", "target": "c", "key": 1, "relation": "calls"},
        ],
    )
    base_p = tmp_path / "base.json"
    other_p = tmp_path / "other.json"
    _graph_to_json(_make_graph([]), base_p)
    _graph_to_json(other, other_p)

    code = _run_merge_driver(monkeypatch, base_p, current_p, other_p)
    assert code == 1
    err = capsys.readouterr().err
    assert "pre-profile" in err
    assert "multidigraph" in err
    assert str(current_p) in err
    assert "regenerate" in err or "recreate" in err
    assert "global-graph.json" not in err
    assert "graphify global remove" not in err


def test_merge_backup_suppressed_by_env(monkeypatch, tmp_path):
    """`_backup_merge_target` honors the GRAPHIFY_NO_BACKUP env var: with it set, an
    overwriting merge writes NO .bak; without it, the dated .bak sibling is created.
    Confirms the env-suppression path Copilot flagged as only indirectly exercised."""
    s1 = _make_graph([{"id": "a", "label": "A", "source_file": "a.py"}], [])
    s2 = _make_graph([{"id": "b", "label": "B", "source_file": "b.py"}], [])
    g1 = _repo_graph(tmp_path, "repo1", s1)
    g2 = _repo_graph(tmp_path, "repo2", s2)

    # --- with GRAPHIFY_NO_BACKUP=1: overwrite an existing target, expect NO .bak ---
    out_suppressed = tmp_path / "merged_suppressed.json"
    _graph_to_json(
        _make_graph([{"id": "old", "label": "OLD", "source_file": "old.py"}], []), out_suppressed
    )
    monkeypatch.setenv("GRAPHIFY_NO_BACKUP", "1")
    assert _run_merge_graphs(monkeypatch, [g1, g2], out_suppressed) == 0
    assert list(tmp_path.glob("merged_suppressed.*.bak")) == []  # suppressed → no backup

    # --- without it: overwrite an existing target, expect the .bak to appear ---
    out_enabled = tmp_path / "merged_enabled.json"
    sentinel = _make_graph([{"id": "old", "label": "OLD", "source_file": "old.py"}], [])
    _graph_to_json(sentinel, out_enabled)
    sentinel_bytes = out_enabled.read_bytes()
    monkeypatch.delenv("GRAPHIFY_NO_BACKUP", raising=False)
    assert _run_merge_graphs(monkeypatch, [g1, g2], out_enabled) == 0
    backups = list(tmp_path.glob("merged_enabled.*.bak"))
    assert len(backups) == 1  # backup created when env is unset
    assert backups[0].read_bytes() == sentinel_bytes  # holds the PRE-overwrite state
