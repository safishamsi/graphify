import json
from unittest.mock import patch, MagicMock

import networkx as nx
import pytest

from graphify.aggregate import (
    aggregate,
    _topk_filter,
    _community_collapse,
    _llm_summarize,
    _composite_aggregate,
    _call_llm,
)


def _make_graph(n_nodes: int = 10, n_edges: int = 15) -> nx.Graph:
    G = nx.Graph()
    for i in range(n_nodes):
        G.add_node(f"n{i}", label=f"Node{i}", source_file=f"file{i}.py", file_type="code")
    for i in range(min(n_edges, n_nodes - 1)):
        G.add_edge(f"n{i}", f"n{i + 1}", relation="calls", confidence="EXTRACTED")
    return G


def _make_graph_with_hubs() -> nx.Graph:
    G = nx.Graph()
    G.add_node("hub", label="hub.py", source_file="hub.py", file_type="code")
    G.add_node("real1", label="AuthService", source_file="auth.py", file_type="code")
    G.add_node("real2", label="UserModel", source_file="user.py", file_type="code")
    G.add_node("real3", label="DataStore", source_file="store.py", file_type="code")
    for n in ["real1", "real2", "real3"]:
        G.add_edge("hub", n, relation="imports", confidence="EXTRACTED")
    G.add_edge("real1", "real2", relation="calls", confidence="INFERRED")
    return G


class TestTopkFilter:
    def test_basic_topk(self):
        G = _make_graph(20, 30)
        result = _topk_filter(G, {"top_k_nodes": 5})
        assert result.number_of_nodes() == 5

    def test_small_graph_returns_all(self):
        G = _make_graph(3, 2)
        result = _topk_filter(G, {"top_k_nodes": 30})
        assert result.number_of_nodes() == 3

    def test_hub_exclusion(self):
        G = _make_graph_with_hubs()
        result = _topk_filter(G, {"top_k_nodes": 3})
        node_ids = set(result.nodes())
        assert "hub" not in node_ids

    def test_confidence_filtering(self):
        G = _make_graph_with_hubs()
        result = _topk_filter(G, {"top_k_nodes": 10, "min_confidence": "EXTRACTED"})
        for u, v, data in result.edges(data=True):
            assert data.get("confidence") == "EXTRACTED"

    def test_attribute_preservation(self):
        G = nx.Graph()
        G.add_node("n1", label="Test", source_file="test.py", community=0)
        G.add_node("n2", label="Other", source_file="other.py", community=1)
        G.add_edge("n1", "n2", relation="calls", weight=2.0)
        result = _topk_filter(G, {"top_k_nodes": 10})
        assert result.nodes["n1"]["label"] == "Test"
        assert result.nodes["n1"]["community"] == 0

    def test_empty_graph(self):
        G = nx.Graph()
        result = _topk_filter(G, {"top_k_nodes": 10})
        assert result.number_of_nodes() == 0


class TestCommunityCollapse:
    def test_basic_collapse(self):
        G = _make_graph(20, 30)
        result = _community_collapse(G, {"nodes_per_community": 2})
        assert result.number_of_nodes() > 0
        assert result.number_of_nodes() < G.number_of_nodes()

    def test_small_community_pass_through(self):
        G = nx.Graph()
        G.add_node("a", label="A", source_file="a.py")
        G.add_node("b", label="B", source_file="b.py")
        G.add_edge("a", "b", relation="calls")
        result = _community_collapse(G, {"nodes_per_community": 5})
        assert "a" in result.nodes()
        assert "b" in result.nodes()

    def test_bridge_edge_preservation(self):
        G = nx.Graph()
        for i in range(8):
            G.add_node(f"n{i}", label=f"N{i}", source_file=f"f{i}.py")
        for i in range(3):
            G.add_edge(f"n{i}", f"n{i + 1}", relation="calls")
        for i in range(4, 7):
            G.add_edge(f"n{i}", f"n{i + 1}", relation="calls")
        G.add_edge("n3", "n4", relation="depends")
        result = _community_collapse(G, {"nodes_per_community": 2, "keep_bridge_edges": True})
        assert result.number_of_edges() > 0

    def test_bridge_edges_disabled(self):
        G = _make_graph(20, 30)
        result = _community_collapse(G, {"nodes_per_community": 2, "keep_bridge_edges": False})
        for u, v, data in G.edges(data=True):
            pass

    def test_metadata_attributes(self):
        G = _make_graph(20, 30)
        result = _community_collapse(G, {"nodes_per_community": 2})
        for nid, data in result.nodes(data=True):
            assert "_community_id" in data
            if data.get("_collapsed"):
                assert data["_collapsed"] is True

    def test_empty_graph(self):
        G = nx.Graph()
        result = _community_collapse(G, {"nodes_per_community": 3})
        assert result.number_of_nodes() == 0


class TestLLMSummary:
    def test_fallback_on_no_llm(self):
        G = _make_graph(10, 15)
        with patch("graphify.aggregate._call_llm", return_value=None):
            result = _llm_summarize(G, {})
        assert result.number_of_nodes() > 0

    def test_successful_mock_llm(self):
        G = _make_graph(10, 15)
        mock_response = json.dumps({
            "nodes": [
                {"id": "summary_1", "label": "Core Service"},
                {"id": "summary_2", "label": "Data Layer"},
            ],
            "edges": [
                {"source": "summary_1", "target": "summary_2", "relation": "depends"},
            ],
        })
        with patch("graphify.aggregate._call_llm", return_value=mock_response):
            result = _llm_summarize(G, {"max_summary_nodes": 10, "max_summary_edges": 20})
        assert result.number_of_nodes() == 2
        assert result.number_of_edges() == 1

    def test_output_limits(self):
        G = _make_graph(10, 15)
        nodes = [{"id": f"s{i}", "label": f"Summary {i}"} for i in range(50)]
        edges = [{"source": "s0", "target": f"s{i}", "relation": "rel"} for i in range(1, 50)]
        mock_response = json.dumps({"nodes": nodes, "edges": edges})
        with patch("graphify.aggregate._call_llm", return_value=mock_response):
            result = _llm_summarize(G, {"max_summary_nodes": 5, "max_summary_edges": 10})
        assert result.number_of_nodes() <= 5
        assert result.number_of_edges() <= 10

    def test_fallback_on_bad_json(self):
        G = _make_graph(10, 15)
        with patch("graphify.aggregate._call_llm", return_value="not valid json"):
            result = _llm_summarize(G, {})
        assert result.number_of_nodes() > 0

    def test_model_override(self):
        G = _make_graph(10, 15)
        mock_response = json.dumps({
            "nodes": [{"id": "s1", "label": "Test"}],
            "edges": [],
        })
        with patch("graphify.aggregate._call_llm", return_value=mock_response) as mock_llm:
            _llm_summarize(G, {"model": "gpt-4o"})
            mock_llm.assert_called_once()
            assert mock_llm.call_args[0][1] == "gpt-4o"

    def test_empty_graph(self):
        G = nx.Graph()
        result = _llm_summarize(G, {})
        assert result.number_of_nodes() == 0


class TestCompositeAggregate:
    def test_two_phase_pipeline(self):
        G = _make_graph(20, 30)
        mock_response = json.dumps({
            "nodes": [{"id": "cs1", "label": "Composite Summary"}],
            "edges": [],
        })
        with patch("graphify.aggregate._call_llm", return_value=mock_response):
            result = _composite_aggregate(G, {
                "nodes_per_community": 2,
                "max_summary_nodes": 10,
            })
        assert result.number_of_nodes() > 0

    def test_param_splitting(self):
        G = _make_graph(20, 30)
        mock_response = json.dumps({
            "nodes": [{"id": "cs1", "label": "Summary"}],
            "edges": [],
        })
        with patch("graphify.aggregate._call_llm", return_value=mock_response):
            result = _composite_aggregate(G, {
                "nodes_per_community": 5,
                "keep_bridge_edges": False,
                "max_summary_nodes": 15,
                "max_summary_edges": 30,
                "model": "gpt-4o",
            })
        assert result.number_of_nodes() > 0

    def test_llm_failure_fallback(self):
        G = _make_graph(20, 30)
        with patch("graphify.aggregate._call_llm", return_value=None):
            result = _composite_aggregate(G, {"nodes_per_community": 2})
        assert result.number_of_nodes() > 0


class TestAggregateDispatcher:
    def test_none_strategy(self):
        G = _make_graph(10, 15)
        result = aggregate(G, "none")
        assert result.number_of_nodes() == 0

    def test_topk_filter_strategy(self):
        G = _make_graph(10, 15)
        result = aggregate(G, "topk_filter", {"top_k_nodes": 5})
        assert result.number_of_nodes() == 5

    def test_community_collapse_strategy(self):
        G = _make_graph(20, 30)
        result = aggregate(G, "community_collapse", {"nodes_per_community": 2})
        assert result.number_of_nodes() > 0

    def test_unknown_strategy_raises(self):
        G = _make_graph(10, 15)
        with pytest.raises(ValueError, match="Unknown aggregation strategy"):
            aggregate(G, "nonexistent")

    def test_available_strategies_in_error(self):
        G = _make_graph(10, 15)
        with pytest.raises(ValueError, match="topk_filter"):
            aggregate(G, "bad_strategy")
