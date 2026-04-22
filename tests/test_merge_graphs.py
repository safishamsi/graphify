import networkx as nx
from graphify.build import merge_graphs


class TestMergeGraphs:
    def test_disjoint_merge(self):
        G_base = nx.Graph()
        G_base.add_node("A", label="Alpha")
        G_base.add_node("B", label="Beta")
        G_base.add_edge("A", "B", relation="connects")

        G_overlay = nx.Graph()
        G_overlay.add_node("X", label="Xray")
        G_overlay.add_node("Y", label="Yankee")
        G_overlay.add_edge("X", "Y", relation="depends")

        result = merge_graphs(G_base, G_overlay, "L0")
        assert set(result.nodes()) == {"A", "B", "summary:L0:X", "summary:L0:Y"}
        assert result.has_edge("A", "B")
        assert result.has_edge("summary:L0:X", "summary:L0:Y")

    def test_empty_overlay(self):
        G_base = nx.Graph()
        G_base.add_node("A", label="Alpha")
        G_overlay = nx.Graph()

        result = merge_graphs(G_base, G_overlay, "L0")
        assert set(result.nodes()) == {"A"}

    def test_empty_base(self):
        G_base = nx.Graph()
        G_overlay = nx.Graph()
        G_overlay.add_node("X", label="Xray")
        G_overlay.add_node("Y", label="Yankee")

        result = merge_graphs(G_base, G_overlay, "L0")
        assert set(result.nodes()) == {"summary:L0:X", "summary:L0:Y"}

    def test_attribute_preservation(self):
        G_base = nx.Graph()
        G_base.add_node("A", label="Alpha", source_file="a.py")

        G_overlay = nx.Graph()
        G_overlay.add_node("X", label="Xray", source_file="x.py")
        G_overlay.add_edge("X", "X", relation="self-ref", confidence="INFERRED")

        result = merge_graphs(G_base, G_overlay, "L0")
        assert result.nodes["A"]["label"] == "Alpha"
        assert result.nodes["A"]["source_file"] == "a.py"
        assert result.nodes["summary:L0:X"]["label"] == "Xray"
        assert result.nodes["summary:L0:X"]["source_file"] == "x.py"

    def test_provenance_tagging(self):
        G_base = nx.Graph()
        G_base.add_node("A", label="Alpha")

        G_overlay = nx.Graph()
        G_overlay.add_node("X", label="Xray")

        result = merge_graphs(G_base, G_overlay, "L0")
        assert result.nodes["summary:L0:X"]["_source_layer"] == "L0"
        assert "_source_layer" not in result.nodes["A"]

    def test_overlay_edge_remapping(self):
        G_overlay = nx.Graph()
        G_overlay.add_node("X", label="Xray")
        G_overlay.add_node("Y", label="Yankee")
        G_overlay.add_edge("X", "Y", relation="calls", weight=2.0)

        result = merge_graphs(nx.Graph(), G_overlay, "L0")
        edge_data = result.edges["summary:L0:X", "summary:L0:Y"]
        assert edge_data["relation"] == "calls"
        assert edge_data["weight"] == 2.0

    def test_preserves_graph_type(self):
        G_base = nx.DiGraph()
        G_overlay = nx.DiGraph()
        result = merge_graphs(G_base, G_overlay, "L0")
        assert isinstance(result, nx.DiGraph)

        G_base2 = nx.Graph()
        G_overlay2 = nx.Graph()
        result2 = merge_graphs(G_base2, G_overlay2, "L0")
        assert isinstance(result2, nx.Graph)
