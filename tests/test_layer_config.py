import pytest
from pathlib import Path
from graphify.layer_config import LayerConfig, load_layers, LayerRegistry


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "layers.yaml"
    p.write_text(content, encoding="utf-8")
    return p


SINGLE_LAYER = """\
layers:
  - id: L0
    name: Root
    description: Root layer
    sources:
      - path: src/
    aggregation:
      strategy: none
"""

THREE_LAYER_CHAIN = """\
layers:
  - id: L0
    name: Root
    description: Root layer
    sources:
      - path: src/
    aggregation:
      strategy: none
  - id: L1
    name: Middle
    description: Middle layer
    parent: L0
    sources:
      - path: services/
    aggregation:
      strategy: none
  - id: L2
    name: Top
    description: Top layer
    parent: L1
    sources:
      - path: system/
    aggregation:
      strategy: none
"""

FOREST = """\
layers:
  - id: L0
    name: Root A
    description: Root A
    sources:
      - path: a/
    aggregation:
      strategy: none
  - id: L1
    name: Child A1
    description: Child of A
    parent: L0
    sources:
      - path: a1/
    aggregation:
      strategy: none
  - id: X0
    name: Root B
    description: Root B
    sources:
      - path: b/
    aggregation:
      strategy: none
  - id: X1
    name: Child B1
    description: Child of B
    parent: X0
    sources:
      - path: b1/
    aggregation:
      strategy: none
"""


class TestValidConfigs:
    def test_single_layer(self, tmp_path):
        p = _write_yaml(tmp_path, SINGLE_LAYER)
        layers = load_layers(p)
        assert len(layers) == 1
        assert layers[0].id == "L0"
        assert layers[0].parent_id is None
        assert layers[0].level == 0
        assert layers[0].aggregation_strategy == "none"

    def test_three_layer_chain(self, tmp_path):
        p = _write_yaml(tmp_path, THREE_LAYER_CHAIN)
        layers = load_layers(p)
        assert len(layers) == 3
        ids = [l.id for l in layers]
        assert ids.index("L0") < ids.index("L1") < ids.index("L2")
        by_id = {l.id: l for l in layers}
        assert by_id["L0"].level == 0
        assert by_id["L1"].level == 1
        assert by_id["L2"].level == 2

    def test_forest_multiple_roots(self, tmp_path):
        p = _write_yaml(tmp_path, FOREST)
        layers = load_layers(p)
        assert len(layers) == 4
        ids = [l.id for l in layers]
        assert ids.index("L0") < ids.index("L1")
        assert ids.index("X0") < ids.index("X1")
        by_id = {l.id: l for l in layers}
        assert by_id["L0"].level == 0
        assert by_id["L1"].level == 1
        assert by_id["X0"].level == 0
        assert by_id["X1"].level == 1


class TestInvalidConfigs:
    def test_missing_id(self, tmp_path):
        yaml = """\
layers:
  - name: NoId
    description: Missing id
    sources:
      - path: src/
"""
        p = _write_yaml(tmp_path, yaml)
        with pytest.raises(ValueError, match="missing required field 'id'"):
            load_layers(p)

    def test_missing_name(self, tmp_path):
        yaml = """\
layers:
  - id: L0
    description: No name
    sources:
      - path: src/
"""
        p = _write_yaml(tmp_path, yaml)
        with pytest.raises(ValueError, match="missing required field 'name'"):
            load_layers(p)

    def test_duplicate_ids(self, tmp_path):
        yaml = """\
layers:
  - id: L0
    name: First
    description: First L0
    sources:
      - path: a/
  - id: L0
    name: Second
    description: Second L0
    sources:
      - path: b/
"""
        p = _write_yaml(tmp_path, yaml)
        with pytest.raises(ValueError, match="Duplicate layer id"):
            load_layers(p)

    def test_unknown_parent(self, tmp_path):
        yaml = """\
layers:
  - id: L1
    name: Orphan
    description: Bad parent
    parent: nonexistent
    sources:
      - path: src/
"""
        p = _write_yaml(tmp_path, yaml)
        with pytest.raises(ValueError, match="unknown parent"):
            load_layers(p)

    def test_malformed_yaml(self, tmp_path):
        p = tmp_path / "layers.yaml"
        p.write_text(":::not valid yaml:::", encoding="utf-8")
        with pytest.raises(Exception):
            load_layers(p)

    def test_missing_layers_key(self, tmp_path):
        p = _write_yaml(tmp_path, "something_else: true")
        with pytest.raises(ValueError, match="top-level 'layers' key"):
            load_layers(p)


class TestCycleDetection:
    def test_direct_cycle(self, tmp_path):
        yaml = """\
layers:
  - id: L0
    name: A
    description: A
    parent: L1
    sources:
      - path: a/
  - id: L1
    name: B
    description: B
    parent: L0
    sources:
      - path: b/
"""
        p = _write_yaml(tmp_path, yaml)
        with pytest.raises(ValueError, match="[Cc]ycle"):
            load_layers(p)

    def test_self_reference(self, tmp_path):
        yaml = """\
layers:
  - id: L0
    name: Self
    description: Self-ref
    parent: L0
    sources:
      - path: src/
"""
        p = _write_yaml(tmp_path, yaml)
        with pytest.raises(ValueError, match="self-reference"):
            load_layers(p)

    def test_three_node_cycle(self, tmp_path):
        yaml = """\
layers:
  - id: L0
    name: A
    description: A
    parent: L2
    sources:
      - path: a/
  - id: L1
    name: B
    description: B
    parent: L0
    sources:
      - path: b/
  - id: L2
    name: C
    description: C
    parent: L1
    sources:
      - path: c/
"""
        p = _write_yaml(tmp_path, yaml)
        with pytest.raises(ValueError, match="[Cc]ycle"):
            load_layers(p)


class TestTopologicalOrder:
    def test_parents_before_children(self, tmp_path):
        p = _write_yaml(tmp_path, THREE_LAYER_CHAIN)
        layers = load_layers(p)
        ids = [l.id for l in layers]
        assert ids == ["L0", "L1", "L2"]

    def test_forest_ordering_stable(self, tmp_path):
        p = _write_yaml(tmp_path, FOREST)
        layers = load_layers(p)
        ids = [l.id for l in layers]
        assert ids.index("L0") < ids.index("L1")
        assert ids.index("X0") < ids.index("X1")


class TestLevelComputation:
    def test_chain_levels(self, tmp_path):
        p = _write_yaml(tmp_path, THREE_LAYER_CHAIN)
        layers = load_layers(p)
        by_id = {l.id: l for l in layers}
        assert by_id["L0"].level == 0
        assert by_id["L1"].level == 1
        assert by_id["L2"].level == 2

    def test_root_level_zero(self, tmp_path):
        p = _write_yaml(tmp_path, SINGLE_LAYER)
        layers = load_layers(p)
        assert layers[0].level == 0


class TestLayerRegistry:
    def _make_registry(self, tmp_path):
        p = _write_yaml(tmp_path, THREE_LAYER_CHAIN)
        layers = load_layers(p)
        return LayerRegistry(layers)

    def test_get_existing_layer(self, tmp_path):
        reg = self._make_registry(tmp_path)
        layer = reg.get_layer_by_id("L1")
        assert layer.id == "L1"
        assert layer.name == "Middle"

    def test_get_nonexistent_layer_raises(self, tmp_path):
        reg = self._make_registry(tmp_path)
        with pytest.raises(KeyError, match="nonexistent"):
            reg.get_layer_by_id("nonexistent")

    def test_get_children(self, tmp_path):
        reg = self._make_registry(tmp_path)
        children = reg.get_children("L0")
        assert len(children) == 1
        assert children[0].id == "L1"

    def test_get_children_leaf(self, tmp_path):
        reg = self._make_registry(tmp_path)
        children = reg.get_children("L2")
        assert children == []

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_layers(tmp_path / "nonexistent.yaml")
