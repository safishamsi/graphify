import json
from pathlib import Path

import networkx as nx

from graphify.layer_pipeline import build_layers


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


class TestBuildLayers:
    def test_two_layer_build_creates_output_dirs(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        result = build_layers(config_path)

        out_root = config_path.parent / "graphify-out"
        assert (out_root / "layers" / "L0").exists()
        assert (out_root / "layers" / "L1").exists()

    def test_two_layer_build_creates_graph_json(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        result = build_layers(config_path)

        out_root = config_path.parent / "graphify-out"
        assert (out_root / "layers" / "L0" / "graph.json").exists()
        assert (out_root / "layers" / "L1" / "graph.json").exists()

    def test_two_layer_build_creates_report(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        result = build_layers(config_path)

        out_root = config_path.parent / "graphify-out"
        assert (out_root / "layers" / "L0" / "GRAPH_REPORT.md").exists()
        assert (out_root / "layers" / "L1" / "GRAPH_REPORT.md").exists()

    def test_two_layer_build_returns_graphs(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        result = build_layers(config_path)

        assert "L0" in result
        assert "L1" in result
        assert isinstance(result["L0"], nx.Graph)
        assert isinstance(result["L1"], nx.Graph)

    def test_l0_has_extracted_nodes(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        result = build_layers(config_path)

        G_L0 = result["L0"]
        assert G_L0.number_of_nodes() > 0

    def test_l1_graph_json_valid(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        build_layers(config_path)

        out_root = config_path.parent / "graphify-out"
        data = json.loads(
            (out_root / "layers" / "L1" / "graph.json").read_text(encoding="utf-8")
        )
        assert "nodes" in data
        assert "links" in data


class TestBuildLayersIncremental:
    def test_target_layer_only(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        build_layers(config_path)

        out_root = config_path.parent / "graphify-out"
        l1_graph = out_root / "layers" / "L1" / "graph.json"
        first_mtime = l1_graph.stat().st_mtime

        import time
        time.sleep(0.1)

        build_layers(config_path, target_layer="L1")
        second_mtime = l1_graph.stat().st_mtime
        assert second_mtime >= first_mtime

    def test_auto_build_missing_parent(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        out_root = config_path.parent / "graphify-out"

        build_layers(config_path)

        import shutil
        shutil.rmtree(out_root / "layers" / "L0")

        build_layers(config_path, target_layer="L1")
        assert (out_root / "layers" / "L0" / "graph.json").exists()
        assert (out_root / "layers" / "L1" / "graph.json").exists()
