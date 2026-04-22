import json
from pathlib import Path
from unittest.mock import patch

import networkx as nx
import pytest

from graphify.layer_config import LayerConfig, LayerRegistry
from graphify.query_router import QueryRouter


def _make_layers() -> list[LayerConfig]:
    return [
        LayerConfig(
            id="L0", name="Code", description="Code layer",
            sources=[], parent_id=None, route_keywords=["code", "function", "class", "implementation"],
            level=0,
        ),
        LayerConfig(
            id="L1", name="Service", description="Service layer",
            sources=[], parent_id="L0", route_keywords=["service", "api", "endpoint"],
            level=1,
        ),
        LayerConfig(
            id="L2", name="System", description="System layer",
            sources=[], parent_id="L1", route_keywords=["architecture", "design", "system", "overview"],
            level=2,
        ),
    ]


def _make_graph(n_nodes: int = 10, label_prefix: str = "Node") -> nx.Graph:
    G = nx.Graph()
    for i in range(n_nodes):
        G.add_node(f"n{i}", label=f"{label_prefix}{i}", source_file=f"file{i}.py", file_type="code")
    for i in range(n_nodes - 1):
        G.add_edge(f"n{i}", f"n{i + 1}", relation="calls")
    return G


def _make_router() -> QueryRouter:
    layers = _make_layers()
    registry = LayerRegistry(layers)
    graphs = {
        "L0": _make_graph(15, "Code"),
        "L1": _make_graph(10, "Service"),
        "L2": _make_graph(5, "System"),
    }
    return QueryRouter(registry, graphs)


class TestRoute:
    def test_keyword_matching(self):
        router = _make_router()
        result = router.route("How does the code function work?")
        assert result == "L0"

    def test_service_keywords(self):
        router = _make_router()
        result = router.route("What API endpoints does the service expose?")
        assert result == "L1"

    def test_architecture_keywords(self):
        router = _make_router()
        result = router.route("Describe the system architecture and design overview")
        assert result == "L2"

    def test_abstract_terms_route_high(self):
        router = _make_router()
        result = router.route("What is the high-level architecture?")
        assert result == "L2"

    def test_concrete_terms_route_low(self):
        router = _make_router()
        result = router.route("Where is the class implementation for authentication?")
        assert result == "L0"

    def test_no_match_defaults_to_highest(self):
        router = _make_router()
        result = router.route("xyzzy plugh foo bar")
        assert result == "L2"

    def test_chinese_abstract_terms(self):
        router = _make_router()
        result = router.route("系统架构是怎样的？")
        assert result == "L2"

    def test_chinese_concrete_terms(self):
        router = _make_router()
        result = router.route("这个函数的实现细节是什么？")
        assert result == "L0"


class TestQuery:
    def test_basic_query(self):
        router = _make_router()
        layer_id, result = router.query("L0", "Node0 function")
        assert layer_id == "L0"
        assert len(result) > 0

    def test_nonexistent_layer(self):
        router = _make_router()
        layer_id, result = router.query("nonexistent", "test")
        assert "not found" in result.lower()

    def test_auto_zoom_disabled(self):
        router = _make_router()
        layer_id, result = router.query("L2", "nonexistent_xyz", auto_zoom=False)
        assert layer_id == "L2"


class TestAutoZoom:
    def test_auto_zoom_to_child(self):
        layers = _make_layers()
        registry = LayerRegistry(layers)
        G_L0 = _make_graph(15, "Code")
        G_L1 = _make_graph(10, "Service")
        G_L1.add_node("auth", label="AuthService", source_file="auth.py", file_type="code")
        G_L1.add_node("user", label="UserModel", source_file="user.py", file_type="code")
        G_L1.add_edge("auth", "user", relation="calls")

        router = QueryRouter(registry, {"L0": G_L0, "L1": G_L1}, auto_zoom_min_nodes=5)
        layer_id, result = router.query("L0", "auth service", auto_zoom=True)
        assert "L1" in result or layer_id == "L1"


class TestLayerInfo:
    def test_layer_info_output(self):
        router = _make_router()
        info = router.layer_info()
        assert "L0" in info
        assert "L1" in info
        assert "L2" in info
        assert "nodes" in info

    def test_layer_info_missing_graph(self):
        layers = _make_layers()
        registry = LayerRegistry(layers)
        router = QueryRouter(registry, {"L0": _make_graph(5)})
        info = router.layer_info()
        assert "not loaded" in info


class TestDrillDown:
    def test_drill_down_specific_layer(self):
        router = _make_router()
        result = router.drill_down("L0", "Node0")
        assert "L0" in result
        assert len(result) > 0

    def test_drill_down_nonexistent_layer(self):
        router = _make_router()
        result = router.drill_down("nonexistent", "test")
        assert "not found" in result.lower()
