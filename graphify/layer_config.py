"""Layer configuration parsing, DAG validation, and topological ordering for hierarchical knowledge aggregation.

Reads a ``layers.yaml`` file and produces validated :class:`LayerConfig` objects
in topological build order.  The module also provides :class:`LayerRegistry` for
fast metadata look-ups (by id, by children).

Typical usage::

    from graphify.layer_config import load_layers, LayerRegistry

    layers = load_layers(Path("layers.yaml"))
    registry = LayerRegistry(layers)
    root = registry.get_layer_by_id("L0")
    children = registry.get_children("L0")
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LayerConfig:
    """Represents a single layer in the hierarchical configuration."""

    id: str
    name: str
    description: str
    sources: list[dict[str, Any]]
    parent_id: str | None = None
    route_keywords: list[str] = field(default_factory=list)
    aggregation_strategy: str = "none"
    aggregation_params: dict[str, Any] = field(default_factory=dict)
    level: int = 0


def load_layers(config_path: Path) -> list[LayerConfig]:
    """Parse *layers.yaml*, validate, and return layers in topological build order.

    Raises :class:`ValueError` on:
    - missing required fields
    - duplicate layer IDs
    - unknown parent references
    - cycles (including self-references)
    """
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "pyyaml is a required dependency but could not be imported. "
            "Your installation may be corrupted; please reinstall graphify."
        )

    if not config_path.exists():
        raise FileNotFoundError(f"Layer config file not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "layers" not in raw:
        raise ValueError("layers.yaml must contain a top-level 'layers' key")

    raw_layers = raw["layers"]
    if not isinstance(raw_layers, list):
        raise ValueError("'layers' must be a list")

    layers: list[LayerConfig] = []
    seen_ids: set[str] = set()

    for idx, entry in enumerate(raw_layers):
        if not isinstance(entry, dict):
            raise ValueError(f"Layer entry at index {idx} must be a mapping")

        layer_id = entry.get("id")
        if not layer_id:
            raise ValueError(f"Layer at index {idx} missing required field 'id'")

        if layer_id in seen_ids:
            raise ValueError(f"Duplicate layer id: '{layer_id}'")
        seen_ids.add(layer_id)

        name = entry.get("name")
        if not name:
            raise ValueError(f"Layer '{layer_id}' missing required field 'name'")

        description = entry.get("description", "")
        sources = entry.get("sources", [])
        if not isinstance(sources, list):
            raise ValueError(f"Layer '{layer_id}': 'sources' must be a list")

        parent_id = entry.get("parent")
        route_keywords = entry.get("route_keywords", [])

        agg = entry.get("aggregation", {})
        if not isinstance(agg, dict):
            agg = {}
        strategy = agg.get("strategy", "none")
        params = agg.get("params", {})

        layers.append(
            LayerConfig(
                id=layer_id,
                name=name,
                description=description,
                sources=sources,
                parent_id=parent_id,
                route_keywords=route_keywords if isinstance(route_keywords, list) else [],
                aggregation_strategy=strategy,
                aggregation_params=params if isinstance(params, dict) else {},
            )
        )

    _validate_parents(layers)
    _validate_no_cycles(layers)
    _compute_levels(layers)

    return _topological_sort(layers)


def _validate_parents(layers: list[LayerConfig]) -> None:
    """Ensure every parent_id references an existing layer id."""
    all_ids = {l.id for l in layers}
    for layer in layers:
        if layer.parent_id is not None and layer.parent_id not in all_ids:
            raise ValueError(
                f"Layer '{layer.id}' references unknown parent '{layer.parent_id}'. "
                f"Valid layer IDs: {sorted(all_ids)}"
            )


def _validate_no_cycles(layers: list[LayerConfig]) -> None:
    """Detect cycles using DFS, including self-references."""
    by_id = {l.id: l for l in layers}

    for layer in layers:
        if layer.parent_id == layer.id:
            raise ValueError(f"Layer '{layer.id}' references itself as parent (self-reference cycle)")

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {l.id: WHITE for l in layers}
    path: list[str] = []

    def visit(node_id: str) -> None:
        color[node_id] = GRAY
        path.append(node_id)
        layer = by_id[node_id]
        if layer.parent_id is not None and layer.parent_id in by_id:
            if color[layer.parent_id] == GRAY:
                cycle_start = path.index(layer.parent_id)
                cycle_path = path[cycle_start:] + [layer.parent_id]
                raise ValueError(f"Cycle detected: {' -> '.join(cycle_path)}")
            if color[layer.parent_id] == WHITE:
                visit(layer.parent_id)
        path.pop()
        color[node_id] = BLACK

    for layer in layers:
        if color[layer.id] == WHITE:
            visit(layer.id)


def _compute_levels(layers: list[LayerConfig]) -> None:
    """Compute depth level for each layer (roots = 0)."""
    by_id = {l.id: l for l in layers}
    for layer in layers:
        if layer.parent_id is None:
            layer.level = 0
        else:
            parent = by_id.get(layer.parent_id)
            if parent is not None:
                layer.level = parent.level + 1


def _topological_sort(layers: list[LayerConfig]) -> list[LayerConfig]:
    """Return layers in topological build order (parents before children).

    Uses Kahn's algorithm for deterministic, stable ordering.
    """
    by_id = {l.id: l for l in layers}
    children_map: dict[str | None, list[str]] = {}
    for l in layers:
        children_map.setdefault(l.parent_id, []).append(l.id)

    in_degree: dict[str, int] = {l.id: 0 for l in layers}
    for l in layers:
        if l.parent_id is not None and l.parent_id in by_id:
            in_degree[l.id] = 1

    queue: deque[str] = deque(sorted(lid for lid, deg in in_degree.items() if deg == 0))
    result: list[LayerConfig] = []

    while queue:
        node_id = queue.popleft()
        result.append(by_id[node_id])
        for child_id in sorted(children_map.get(node_id, [])):
            in_degree[child_id] -= 1
            if in_degree[child_id] == 0:
                queue.append(child_id)

    return result


class LayerRegistry:
    """Fast lookup interface for layer metadata."""

    def __init__(self, layers: list[LayerConfig]) -> None:
        self._by_id: dict[str, LayerConfig] = {l.id: l for l in layers}
        self._children: dict[str, list[LayerConfig]] = {}
        for l in layers:
            if l.parent_id is not None:
                self._children.setdefault(l.parent_id, []).append(l)

    def get_layer_by_id(self, layer_id: str) -> LayerConfig:
        """Return the layer with the given id, or raise KeyError."""
        if layer_id not in self._by_id:
            raise KeyError(f"No layer with id '{layer_id}'")
        return self._by_id[layer_id]

    def get_children(self, parent_id: str) -> list[LayerConfig]:
        """Return child layers of the given parent (empty list if none)."""
        return self._children.get(parent_id, [])
    

