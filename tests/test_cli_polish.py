import json
import subprocess
import sys
from pathlib import Path

import networkx as nx
import pytest

from graphify.build import graph_diff
from graphify.layer_pipeline import build_layers, _save_provenance, _group_by_level
from graphify.layer_config import LayerConfig
from graphify.serve import _auto_detect_layers


TWO_LAYER_YAML = """\
layers:
  - id: L0
    name: Services
    description: Service layer
    sources:
      - path: __L0_SRC__
    aggregation:
      strategy: none
  - id: L1
    name: System
    description: System layer
    parent: L0
    sources:
      - path: __L1_SRC__
    aggregation:
      strategy: none
"""


def _setup_fixture(tmp_path: Path) -> Path:
    l0_dir = tmp_path / "services"
    l1_dir = tmp_path / "system"
    l0_dir.mkdir()
    l1_dir.mkdir()
    (l0_dir / "auth.py").write_text(
        "class AuthService:\n    def login(self): pass\n",
        encoding="utf-8",
    )
    (l1_dir / "app.py").write_text(
        "class Application:\n    def run(self): pass\n",
        encoding="utf-8",
    )
    yaml_content = TWO_LAYER_YAML.replace("__L0_SRC__", str(l0_dir)).replace(
        "__L1_SRC__", str(l1_dir)
    )
    config_path = tmp_path / "layers.yaml"
    config_path.write_text(yaml_content, encoding="utf-8")
    return config_path


def _run_graphify(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "graphify", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


class TestLayerInfoCLI:
    def test_layer_info_after_build(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        _run_graphify("build", "--layers", str(config_path), cwd=str(tmp_path))
        result = _run_graphify("layer-info", "--layers", str(config_path), cwd=str(tmp_path))
        assert result.returncode == 0
        assert "L0" in result.stdout
        assert "L1" in result.stdout
        assert "built" in result.stdout

    def test_layer_info_not_built(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        result = _run_graphify("layer-info", "--layers", str(config_path), cwd=str(tmp_path))
        assert result.returncode == 0
        assert "not built" in result.stdout

    def test_layer_info_missing_config(self, tmp_path):
        result = _run_graphify("layer-info", "--layers", str(tmp_path / "nonexistent.yaml"))
        assert result.returncode != 0


class TestLayerTreeCLI:
    def test_layer_tree_after_build(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        _run_graphify("build", "--layers", str(config_path), cwd=str(tmp_path))
        result = _run_graphify("layer-tree", "--layers", str(config_path), cwd=str(tmp_path))
        assert result.returncode == 0
        assert "L0" in result.stdout
        assert "L1" in result.stdout

    def test_layer_tree_format(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        _run_graphify("build", "--layers", str(config_path), cwd=str(tmp_path))
        result = _run_graphify("layer-tree", "--layers", str(config_path), cwd=str(tmp_path))
        assert "└" in result.stdout or "├" in result.stdout


class TestLayerDiffCLI:
    def test_layer_diff_after_build(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        _run_graphify("build", "--layers", str(config_path), cwd=str(tmp_path))
        result = _run_graphify("layer-diff", "L0", "L1", "--layers", str(config_path), cwd=str(tmp_path))
        assert result.returncode == 0
        assert "Diff" in result.stdout

    def test_layer_diff_nonexistent_id(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        _run_graphify("build", "--layers", str(config_path), cwd=str(tmp_path))
        result = _run_graphify("layer-diff", "L0", "nonexistent", "--layers", str(config_path), cwd=str(tmp_path))
        assert result.returncode != 0
        assert "not found" in result.stderr

    def test_layer_diff_not_built(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        result = _run_graphify("layer-diff", "L0", "L1", "--layers", str(config_path), cwd=str(tmp_path))
        assert result.returncode != 0
        assert "not been built" in result.stderr


class TestGraphDiff:
    def test_identical_graphs(self):
        G = nx.Graph()
        G.add_node("A", label="Alpha")
        G.add_node("B", label="Beta")
        G.add_edge("A", "B", relation="calls")
        diff = graph_diff(G, G)
        assert len(diff["common_nodes"]) == 2
        assert len(diff["common_edges"]) == 1
        assert len(diff["nodes_only_in_a"]) == 0

    def test_different_graphs(self):
        G1 = nx.Graph()
        G1.add_node("A", label="Alpha")
        G1.add_node("B", label="Beta")
        G1.add_edge("A", "B", relation="calls")

        G2 = nx.Graph()
        G2.add_node("B", label="Beta")
        G2.add_node("C", label="Gamma")
        G2.add_edge("B", "C", relation="depends")

        diff = graph_diff(G1, G2)
        assert "A" in diff["nodes_only_in_a"]
        assert "C" in diff["nodes_only_in_b"]
        assert "B" in diff["common_nodes"]

    def test_empty_graphs(self):
        G1 = nx.Graph()
        G2 = nx.Graph()
        diff = graph_diff(G1, G2)
        assert len(diff["common_nodes"]) == 0


class TestProvenance:
    def test_provenance_file_created(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        result = build_layers(config_path, parallel=False)

        out_root = config_path.parent / "graphify-out"
        provenance_path = out_root / "layers" / "L1" / "aggregation" / "from_L0.json"
        assert provenance_path.exists()

    def test_provenance_is_valid_json(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        result = build_layers(config_path, parallel=False)

        out_root = config_path.parent / "graphify-out"
        provenance_path = out_root / "layers" / "L1" / "aggregation" / "from_L0.json"
        data = json.loads(provenance_path.read_text(encoding="utf-8"))
        assert "nodes" in data
        assert "links" in data

    def test_root_layer_no_provenance(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        result = build_layers(config_path, parallel=False)

        out_root = config_path.parent / "graphify-out"
        agg_dir = out_root / "layers" / "L0" / "aggregation"
        assert not agg_dir.exists()

    def test_provenance_loadable(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        result = build_layers(config_path, parallel=False)

        out_root = config_path.parent / "graphify-out"
        provenance_path = out_root / "layers" / "L1" / "aggregation" / "from_L0.json"
        from graphify.build import build_from_json
        data = json.loads(provenance_path.read_text(encoding="utf-8"))
        G = build_from_json(data)
        assert isinstance(G, nx.Graph)


class TestParallelGroups:
    def test_group_by_level(self):
        layers = [
            LayerConfig(id="L0", name="A", description="", sources=[], level=0),
            LayerConfig(id="X0", name="B", description="", sources=[], level=0),
            LayerConfig(id="L1", name="C", description="", sources=[], parent_id="L0", level=1),
        ]
        groups = _group_by_level(layers)
        assert len(groups[0]) == 2
        assert len(groups[1]) == 1

    def test_sequential_build_works(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        result = build_layers(config_path, parallel=False)
        assert "L0" in result
        assert "L1" in result


class TestAutoDetectLayers:
    def test_detects_layers_yaml(self, tmp_path):
        out_dir = tmp_path / "graphify-out"
        out_dir.mkdir()
        (out_dir / "layers").mkdir()
        (out_dir / "layers" / "L0").mkdir()
        (out_dir / "layers.yaml").write_text(
            "layers:\n  - id: L0\n    name: Test\n    description: Test\n    sources: []\n",
            encoding="utf-8",
        )
        graph_path = str(out_dir / "graph.json")
        result = _auto_detect_layers(graph_path)
        assert result is not None

    def test_no_layers_dir_returns_none(self, tmp_path):
        out_dir = tmp_path / "graphify-out"
        out_dir.mkdir()
        graph_path = str(out_dir / "graph.json")
        result = _auto_detect_layers(graph_path)
        assert result is None

    def test_invalid_layers_yaml_returns_none(self, tmp_path):
        out_dir = tmp_path / "graphify-out"
        out_dir.mkdir()
        (out_dir / "layers").mkdir()
        (out_dir / "layers.yaml").write_text("invalid: yaml", encoding="utf-8")
        graph_path = str(out_dir / "graph.json")
        result = _auto_detect_layers(graph_path)
        assert result is None
