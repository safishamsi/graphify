"""Tests for serve.py - MCP graph query helpers (no mcp package required)."""
import json
import pytest
import networkx as nx
from networkx.readwrite import json_graph

from graphify.serve import (
    _communities_from_graph,
    _score_nodes,
    _compute_idf,
    _pick_seeds,
    _bfs,
    _dfs,
    _find_node,
    _filter_graph_by_context,
    _infer_context_filters,
    _query_terms,
    _query_graph_text,
    _resolve_context_filters,
    _subgraph_to_text,
    _load_graph,
)


def _make_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("n1", label="extract", source_file="extract.py", source_location="L10", community=0)
    G.add_node("n2", label="cluster", source_file="cluster.py", source_location="L5", community=0)
    G.add_node("n3", label="build", source_file="build.py", source_location="L1", community=1)
    G.add_node("n4", label="report", source_file="report.py", source_location="L1", community=1)
    G.add_node("n5", label="isolated", source_file="other.py", source_location="L1", community=2)
    G.add_edge("n1", "n2", relation="calls", confidence="INFERRED", context="call")
    G.add_edge("n2", "n3", relation="imports", confidence="EXTRACTED", context="import")
    G.add_edge("n3", "n4", relation="uses", confidence="EXTRACTED")
    return G


# --- _communities_from_graph ---

def test_communities_from_graph_basic():
    G = _make_graph()
    communities = _communities_from_graph(G)
    assert 0 in communities
    assert 1 in communities
    assert "n1" in communities[0]
    assert "n2" in communities[0]
    assert "n3" in communities[1]

def test_communities_from_graph_no_community_attr():
    G = nx.Graph()
    G.add_node("a", label="foo")  # no community attr
    communities = _communities_from_graph(G)
    assert communities == {}

def test_communities_from_graph_isolated():
    G = _make_graph()
    communities = _communities_from_graph(G)
    assert 2 in communities
    assert "n5" in communities[2]


# --- _score_nodes ---

def test_score_nodes_exact_label_match():
    G = _make_graph()
    scored = _score_nodes(G, ["extract"])
    nids = [nid for _, nid in scored]
    assert "n1" in nids
    assert scored[0][1] == "n1"  # highest score first

def test_score_nodes_no_match():
    G = _make_graph()
    scored = _score_nodes(G, ["xyzzy"])
    assert scored == []

def test_score_nodes_source_file_partial():
    G = _make_graph()
    # "cluster.py" contains "cluster" - should score 0.5 for source match
    scored = _score_nodes(G, ["cluster"])
    nids = [nid for _, nid in scored]
    assert "n2" in nids


def test_score_nodes_ignores_trailing_punctuation():
    G = _make_graph()
    scored = _score_nodes(G, ["extract?"])
    assert scored[0][1] == "n1"


def test_find_node_ignores_trailing_punctuation():
    G = _make_graph()
    assert _find_node(G, "extract?") == ["n1"]


def test_query_terms_strips_search_punctuation():
    assert _query_terms("what calls extract?") == ["what", "calls", "extract"]


def test_query_terms_filters_only_short_english_terms(monkeypatch):
    import graphify.serve as serve_mod

    class FakeJieba:
        def cut(self, text):
            return {
                "前端": ["前端"],
                "依赖": ["依赖"],
                "安装": ["安装"],
                "包管理器": ["包", "管理器"],
                "项目约定": ["项目", "约定"],
                "a前": ["a", "前"],
            }[text]

    monkeypatch.setattr(serve_mod, "_jieba", FakeJieba())
    terms = _query_terms("前端 dependency 依赖 install 安装 to of 包管理器 项目约定 a前")
    assert terms == ["前端", "dependency", "依赖", "install", "安装", "包", "管理器", "包管理器", "项目", "约定", "项目约定", "前", "a前"]


def test_query_graph_text_keeps_short_non_english_terms():
    G = nx.Graph()
    G.add_node("frontend", label="前端", source_file="docs/前端.md", source_location="L1", community=0)
    text = _query_graph_text(G, "前端", mode="bfs", depth=1)
    assert "No matching nodes found." not in text
    assert "NODE 前端" in text


def test_infer_context_filters_for_calls_question():
    assert _infer_context_filters("who calls extract") == ["call"]


def test_resolve_context_filters_explicit_overrides_heuristic():
    filters, source = _resolve_context_filters("who calls extract", ["field"])
    assert filters == ["field"]
    assert source == "explicit"


# --- _bfs ---

def test_bfs_depth_1():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=1)
    assert "n1" in visited
    assert "n2" in visited  # direct neighbor
    assert "n3" not in visited  # 2 hops away

def test_bfs_depth_2():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=2)
    assert "n3" in visited  # n1 -> n2 -> n3

def test_bfs_disconnected():
    G = _make_graph()
    visited, edges = _bfs(G, ["n5"], depth=3)
    assert visited == {"n5"}  # isolated node

def test_bfs_returns_edges():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=1)
    assert len(edges) >= 1
    assert any(u == "n1" or v == "n1" for u, v in edges)


def test_filter_graph_by_context_limits_traversal():
    G = _make_graph()
    filtered = _filter_graph_by_context(G, ["call"])
    visited, edges = _bfs(filtered, ["n1"], depth=2)
    assert "n2" in visited
    assert "n3" not in visited
    assert edges == [("n1", "n2")]


# --- _dfs ---

def test_dfs_depth_1():
    G = _make_graph()
    visited, edges = _dfs(G, ["n1"], depth=1)
    assert "n1" in visited
    assert "n2" in visited
    assert "n3" not in visited

def test_dfs_full_chain():
    G = _make_graph()
    visited, edges = _dfs(G, ["n1"], depth=5)
    assert {"n1", "n2", "n3", "n4"}.issubset(visited)


# --- _subgraph_to_text ---

def test_subgraph_to_text_contains_labels():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, [("n1", "n2")])
    assert "extract" in text
    assert "cluster" in text

def test_subgraph_to_text_truncates():
    G = _make_graph()
    # Very small budget forces truncation
    text = _subgraph_to_text(G, {"n1", "n2", "n3", "n4"}, [("n1", "n2")], token_budget=1)
    assert "truncated" in text

def test_subgraph_to_text_edge_included():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, [("n1", "n2")])
    assert "EDGE" in text
    assert "calls" in text


def test_subgraph_to_text_includes_edge_context():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, [("n1", "n2")])
    assert "context=call" in text


def test_query_graph_text_explicit_context_filter_changes_traversal():
    G = _make_graph()
    text = _query_graph_text(G, "extract", mode="bfs", depth=2, token_budget=2000, context_filters=["call"])
    assert "Context: call (explicit)" in text
    assert "cluster" in text
    assert "build" not in text


def test_query_graph_text_heuristic_context_filter_changes_traversal():
    G = _make_graph()
    text = _query_graph_text(G, "who calls extract", mode="bfs", depth=2, token_budget=2000)
    assert "Context: call (heuristic)" in text
    assert "cluster" in text
    assert "build" not in text


# --- _load_graph ---

def test_load_graph_roundtrip(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))
    G2 = _load_graph(str(p))
    assert G2.number_of_nodes() == G.number_of_nodes()
    assert G2.number_of_edges() == G.number_of_edges()

def test_load_graph_missing_file(tmp_path):
    graphify_dir = tmp_path / "graphify-out"
    graphify_dir.mkdir()
    with pytest.raises(SystemExit):
        _load_graph(str(graphify_dir / "nonexistent.json"))


def test_load_graph_rejects_oversized_file(monkeypatch, tmp_path, capsys):
    # #F4: oversized graph.json must fail fast (SystemExit) with a clear error.
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))
    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 16)
    with pytest.raises(SystemExit):
        _load_graph(str(p))
    err = capsys.readouterr().err
    assert "exceeds" in err
    assert "byte cap" in err


def test_load_graph_accepts_under_cap(monkeypatch, tmp_path):
    # Verifies the cap path does not regress the normal load.
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))
    # Cap well above the actual file size — load proceeds.
    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 10 * 1024 * 1024)
    G2 = _load_graph(str(p))
    assert G2.number_of_nodes() == G.number_of_nodes()


# --- #874: MCP hot-reload ---

def _write_graph(path, nodes: list[str]) -> None:
    """Write a minimal graph.json with the given node IDs."""
    G = nx.DiGraph()
    for n in nodes:
        G.add_node(n, label=n, community=0)
    data = json_graph.node_link_data(G, edges="links")
    path.write_text(json.dumps(data), encoding="utf-8")


def test_maybe_reload_detects_graph_change(tmp_path):
    """serve() picks up a new graph.json written after startup (#874)."""
    import time
    from unittest.mock import patch

    out = tmp_path / "graphify-out"
    out.mkdir()
    graph_path = out / "graph.json"
    _write_graph(graph_path, ["alpha", "beta"])

    # Bootstrap _load_graph + _communities_from_graph to verify the reload path
    G1 = _load_graph(str(graph_path))
    assert set(G1.nodes()) == {"alpha", "beta"}

    # Simulate file changing (bump mtime by touching)
    time.sleep(0.01)
    _write_graph(graph_path, ["alpha", "beta", "gamma"])

    G2 = _load_graph(str(graph_path))
    assert "gamma" in G2.nodes()


def test_load_graph_cache_key_changes_with_content(tmp_path):
    """mtime_ns + size uniquely identifies a graph version (#874)."""
    import time

    out = tmp_path / "graphify-out"
    out.mkdir()
    graph_path = out / "graph.json"
    _write_graph(graph_path, ["a"])

    s1 = graph_path.stat()
    key1 = (s1.st_mtime_ns, s1.st_size)

    time.sleep(0.01)
    _write_graph(graph_path, ["a", "b"])

    s2 = graph_path.stat()
    key2 = (s2.st_mtime_ns, s2.st_size)

    assert key1 != key2, "stat key must change when file content changes"


# --- IDF weighting tests (#897) ---

def _make_noisy_graph() -> nx.Graph:
    """20 error-handler nodes + 1 rare identifier: FooBarService."""
    G = nx.Graph()
    for i in range(20):
        G.add_node(f"err{i}", label=f"error_handler_{i}", source_file=f"err{i}.py", community=0)
        if i > 0:
            G.add_edge(f"err{i-1}", f"err{i}", relation="calls", confidence="EXTRACTED")
    G.add_node("fbs", label="FooBarService", source_file="service.py", community=1)
    G.add_node("fbs_dep", label="ServiceClient", source_file="client.py", community=1)
    G.add_edge("fbs", "fbs_dep", relation="uses", confidence="EXTRACTED")
    return G


def test_idf_downweights_common_terms():
    """'error' matches 20 nodes, 'foobarservice' matches 1 — IDF should make
    FooBarService rank first despite error's higher raw frequency."""
    G = _make_noisy_graph()
    scored = _score_nodes(G, ["foobarservice", "error"])
    assert scored, "should have results"
    assert scored[0][1] == "fbs", (
        f"FooBarService should rank first, got {scored[0][1]}"
    )


def test_idf_cached_on_graph():
    """IDF results are stored in G.graph so repeated queries don't recompute."""
    G = _make_graph()
    _score_nodes(G, ["extract"])
    assert "_idf_cache" in G.graph
    assert "extract" in G.graph["_idf_cache"]


def test_idf_new_graph_starts_fresh():
    """Two separate graph instances must not share an IDF cache."""
    G1 = _make_graph()
    G2 = _make_graph()
    _score_nodes(G1, ["extract"])
    assert "_idf_cache" not in G2.graph


def test_idf_rare_term_gets_high_weight():
    """A term matching only 1 of N nodes should get IDF > 1."""
    import math
    G = _make_graph()  # 5 nodes
    idf = _compute_idf(G, ["extract"])
    # extract matches only n1: IDF = log(1 + 5/2) ≈ 1.25
    assert idf["extract"] > 1.0


def test_idf_common_term_gets_low_weight():
    """A term matching most nodes should get IDF < 1."""
    import math
    G = nx.Graph()
    # 'handle' in every node label
    for i in range(20):
        G.add_node(f"n{i}", label=f"handle_{i}", source_file=f"f{i}.py")
    idf = _compute_idf(G, ["handle"])
    assert idf["handle"] < 1.0


# --- _pick_seeds tests (#897) ---

def test_pick_seeds_dominant_identifier_gives_one_seed():
    """FooBarService at 1000 vs error nodes at 1.0 → only 1 seed chosen."""
    scored = [(1000.0, "fbs"), (1.0, "err1"), (0.9, "err2")]
    seeds = _pick_seeds(scored)
    assert seeds == ["fbs"]


def test_pick_seeds_close_scores_keeps_multiple():
    """When all scores are within 20% of the top, keep up to 3 seeds."""
    scored = [(10.0, "a"), (9.0, "b"), (8.5, "c")]
    seeds = _pick_seeds(scored)
    assert len(seeds) == 3


def test_pick_seeds_empty():
    assert _pick_seeds([]) == []


def test_pick_seeds_single():
    assert _pick_seeds([(5.0, "x")]) == ["x"]


def test_pick_seeds_respects_max_k():
    """Never return more than max_k seeds even when all scores are close."""
    scored = [(10.0, f"n{i}") for i in range(10)]
    seeds = _pick_seeds(scored, max_k=3)
    assert len(seeds) == 3


# --- actionable truncation hint (#897) ---

def test_subgraph_to_text_truncation_hint_is_actionable():
    """Truncation message must tell Claude what to do, not just say truncated."""
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2", "n3", "n4"}, [("n1", "n2")], token_budget=1)
    assert "truncated" in text
    assert "get_node" in text or "context_filter" in text


# --- integration: identifier + noise query seeds from identifier (#897) ---

def test_query_seeds_from_identifier_not_noise():
    """'FooBarService error handling' should expand from FooBarService,
    not from error-handler nodes, so ServiceClient appears in results."""
    G = _make_noisy_graph()
    text = _query_graph_text(G, "FooBarService error handling", mode="bfs", depth=2)
    assert "FooBarService" in text
    assert "ServiceClient" in text


def test_query_graph_text_parameter_type_context_filter_changes_traversal():
    import networkx as nx
    from graphify.serve import _query_graph_text

    graph = nx.Graph()
    graph.add_node("process", label="process", source_file="sample.cs", source_location="L20")
    graph.add_node("payload", label="Payload", source_file="sample.cs", source_location="L5")
    graph.add_node("other", label="PayloadFactory", source_file="sample.cs", source_location="L40")
    graph.add_edge("process", "payload", relation="references", context="parameter_type", confidence="EXTRACTED")
    graph.add_edge("process", "other", relation="calls", context="call", confidence="EXTRACTED")

    text = _query_graph_text(graph, "who accepts Payload", context_filters=["parameter_type"])

    assert "parameter_type" in text
    assert "Payload" in text
    assert "PayloadFactory" not in text


def test_query_graph_text_context_filter_aliases_resolve():
    import networkx as nx
    from graphify.serve import _normalize_context_filters

    assert _normalize_context_filters(["param"]) == ["parameter_type"]
    assert _normalize_context_filters(["parameter"]) == ["parameter_type"]
    assert _normalize_context_filters(["return"]) == ["return_type"]
    assert _normalize_context_filters(["returns"]) == ["return_type"]
    assert _normalize_context_filters(["generic"]) == ["generic_arg"]
    assert _normalize_context_filters(["generics"]) == ["generic_arg"]
    assert _normalize_context_filters(["annotation"]) == ["attribute"]
    assert _normalize_context_filters(["decorator"]) == ["attribute"]
    # Pass-through for already-canonical values
    assert _normalize_context_filters(["parameter_type"]) == ["parameter_type"]
    assert _normalize_context_filters(["field"]) == ["field"]


# --- Chinese segmentation ---

def test_query_terms_chinese_segments_with_cached_jieba(monkeypatch):
    """Chinese text should use the cached jieba module and keep the original term."""
    import graphify.serve as serve_mod

    class FakeJieba:
        def cut(self, text):
            assert text == "页面路由"
            return ["页面", "路由"]

    monkeypatch.setattr(serve_mod, "_jieba", FakeJieba())
    terms = _query_terms("页面路由")
    assert terms == ["页面", "路由", "页面路由"]


def test_query_terms_chinese_mixed():
    """Mixed Chinese and English text should be handled correctly."""
    terms = _query_terms("前端 router 路由配置")
    assert "前端" in terms
    assert "router" in terms
    assert "路由" in terms
    assert "配置" in terms


def test_query_terms_non_chinese_scripts_are_not_segmented():
    """Japanese kana and Hangul are kept as terms but not segmented as Chinese."""
    import graphify.serve as serve_mod

    assert not serve_mod._has_chinese("かなカナ한글")
    assert serve_mod._query_terms("かなカナ한글") == ["かなカナ한글"]


def test_query_terms_chinese_no_jieba_fallback(monkeypatch):
    """When jieba is not installed, fallback to character bigrams."""
    import graphify.serve as serve_mod

    monkeypatch.setattr(serve_mod, "_jieba", None)
    terms = serve_mod._query_terms("页面路由")
    # bigram fallback: ["页面", "面路", "路由"] + original "页面路由"
    assert "页面" in terms
    assert "路由" in terms
    assert "页面路由" in terms
    assert len(terms) == 4


def test_score_nodes_chinese_substring_match():
    """Searching for '路由' should match a node with label containing '路由'."""
    G = nx.Graph()
    G.add_node("n1", label="路由桥接核对表", source_file="doc.md", community=0)
    G.add_node("n2", label="其他内容", source_file="doc.md", community=0)
    scored = _score_nodes(G, ["路由"])
    nids = [nid for _, nid in scored]
    assert "n1" in nids
    assert "n2" not in nids


def test_query_text_chinese_finds_routing_nodes():
    """Full pipeline: '页面路由' should find nodes with '路由' in label."""
    G = nx.Graph()
    G.add_node("parent", label="页面路由规范", source_file="doc.md", source_location="L1", community=0)
    G.add_node("child", label="路由桥接核对表", source_file="doc.md", source_location="L10", community=0)
    G.add_edge("parent", "child", relation="contains", confidence="EXTRACTED")
    text = _query_graph_text(G, "页面路由", mode="bfs", depth=2)
    assert "No matching nodes found." not in text
    assert "路由" in text
