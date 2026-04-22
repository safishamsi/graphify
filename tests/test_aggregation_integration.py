import json
from pathlib import Path
from unittest.mock import patch

import networkx as nx

from graphify.layer_pipeline import build_layers


TOPK_YAML = """\
layers:
  - id: L0
    name: Services
    description: Service layer
    sources:
      - path: __L0_SRC__
    aggregation:
      strategy: topk_filter
      params:
        top_k_nodes: 5
  - id: L1
    name: System
    description: System layer
    parent: L0
    sources:
      - path: __L1_SRC__
    aggregation:
      strategy: topk_filter
      params:
        top_k_nodes: 3
"""

CC_YAML = """\
layers:
  - id: L0
    name: Services
    description: Service layer
    sources:
      - path: __L0_SRC__
    aggregation:
      strategy: community_collapse
      params:
        nodes_per_community: 2
  - id: L1
    name: System
    description: System layer
    parent: L0
    sources:
      - path: __L1_SRC__
    aggregation:
      strategy: community_collapse
      params:
        nodes_per_community: 2
"""


def _setup_sources(tmp_path: Path) -> tuple[Path, Path]:
    l0_dir = tmp_path / "services"
    l1_dir = tmp_path / "system"
    l0_dir.mkdir()
    l1_dir.mkdir()
    (l0_dir / "auth.py").write_text(
        "class AuthService:\n    def login(self): pass\n    def logout(self): pass\n",
        encoding="utf-8",
    )
    (l0_dir / "store.py").write_text(
        "class DataStore:\n    def save(self): pass\n    def load(self): pass\n",
        encoding="utf-8",
    )
    (l1_dir / "app.py").write_text(
        "class Application:\n    def run(self): pass\n",
        encoding="utf-8",
    )
    return l0_dir, l1_dir


def _write_config(tmp_path: Path, template: str, l0_dir: Path, l1_dir: Path) -> Path:
    content = template.replace("__L0_SRC__", str(l0_dir)).replace("__L1_SRC__", str(l1_dir))
    config_path = tmp_path / "layers.yaml"
    config_path.write_text(content, encoding="utf-8")
    return config_path


class TestTopkFilterIntegration:
    def test_topk_filter_end_to_end(self, tmp_path):
        l0_dir, l1_dir = _setup_sources(tmp_path)
        config_path = _write_config(tmp_path, TOPK_YAML, l0_dir, l1_dir)
        result = build_layers(config_path)

        assert "L0" in result
        assert "L1" in result

        out_root = config_path.parent / "graphify-out"
        l0_graph_path = out_root / "layers" / "L0" / "graph.json"
        assert l0_graph_path.exists()

        l1_graph_path = out_root / "layers" / "L1" / "graph.json"
        assert l1_graph_path.exists()

    def test_topk_summary_nodes_appear_in_upper_layer(self, tmp_path):
        l0_dir, l1_dir = _setup_sources(tmp_path)
        config_path = _write_config(tmp_path, TOPK_YAML, l0_dir, l1_dir)
        result = build_layers(config_path)

        G_L1 = result["L1"]
        summary_nodes = [n for n in G_L1.nodes() if n.startswith("summary:L0:")]
        assert len(summary_nodes) > 0


class TestCommunityCollapseIntegration:
    def test_community_collapse_end_to_end(self, tmp_path):
        l0_dir, l1_dir = _setup_sources(tmp_path)
        config_path = _write_config(tmp_path, CC_YAML, l0_dir, l1_dir)
        result = build_layers(config_path)

        assert "L0" in result
        assert "L1" in result

    def test_cc_summary_nodes_with_prefix(self, tmp_path):
        l0_dir, l1_dir = _setup_sources(tmp_path)
        config_path = _write_config(tmp_path, CC_YAML, l0_dir, l1_dir)
        result = build_layers(config_path)

        G_L1 = result["L1"]
        summary_nodes = [n for n in G_L1.nodes() if n.startswith("summary:L0:")]
        assert len(summary_nodes) > 0

        for nid in summary_nodes:
            assert G_L1.nodes[nid].get("_source_layer") == "L0"
