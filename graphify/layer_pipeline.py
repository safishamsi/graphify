"""Layered build pipeline orchestration.

Orchestrates per-layer build in topological order, producing per-layer output
directories under ``graphify-out/layers/<id>/``.  Each layer's graph may
include summary nodes from its parent layer (merged via
:func:`graphify.build.merge_graphs`).

Typical usage::

    from graphify.layer_pipeline import build_layers
    build_layers(Path("layers.yaml"))
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

from .aggregate import aggregate
from .build import build_from_json, merge_graphs
from .cluster import cluster, score_all
from .extract import extract
from .layer_config import LayerConfig, LayerRegistry, load_layers
from .report import generate as generate_report


def _extract_layer_sources(layer: LayerConfig) -> list[Path]:
    """Resolve source paths from a layer config into actual file paths."""
    paths: list[Path] = []
    for src in layer.sources:
        p = src.get("path")
        if p is None:
            continue
        resolved = Path(p)
        if resolved.is_dir():
            for f in resolved.rglob("*"):
                if f.is_file():
                    paths.append(f)
        elif resolved.is_file():
            paths.append(resolved)
    return paths


def _save_provenance(
    summary_graph: nx.Graph,
    layer: LayerConfig,
    out_root: Path,
) -> None:
    """Save aggregation provenance metadata for debugging and auditability."""
    if layer.parent_id is None:
        return

    agg_dir = out_root / "layers" / layer.id / "aggregation"
    agg_dir.mkdir(parents=True, exist_ok=True)

    provenance_path = agg_dir / f"from_{layer.parent_id}.json"
    from networkx.readwrite import json_graph as _jg
    data = _jg.node_link_data(summary_graph, edges="links")
    provenance_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _save_layer_output(
    G: nx.Graph,
    communities: dict[int, list[str]],
    layer: LayerConfig,
    out_root: Path,
) -> Path:
    """Save graph.json and GRAPH_REPORT.md for a single layer.

    Returns the layer output directory path.
    """
    layer_dir = out_root / "layers" / layer.id
    layer_dir.mkdir(parents=True, exist_ok=True)

    from graphify.export import to_json
    to_json(G, communities, str(layer_dir / "graph.json"))

    cohesion = score_all(G, communities)
    from graphify.analyze import god_nodes, surprising_connections, suggest_questions
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    labels = {cid: f"Community {cid}" for cid in communities}
    questions = suggest_questions(G, communities, labels)

    detection = {
        "files": {"code": [], "document": [], "paper": [], "image": []},
        "total_files": G.number_of_nodes(),
        "total_words": 0,
    }

    report = generate_report(
        G, communities, cohesion, labels, gods, surprises,
        detection, {"input": 0, "output": 0},
        layer.name, suggested_questions=questions,
    )
    (layer_dir / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")

    return layer_dir


def _build_single_layer(
    layer: LayerConfig,
    parent_graph: nx.Graph | None,
    out_root: Path,
) -> nx.Graph:
    """Build a single layer: extract → build → aggregate parent → merge → cluster → save."""
    source_files = _extract_layer_sources(layer)

    if source_files:
        extraction = extract(source_files)
        G = build_from_json(extraction)
    else:
        G = nx.Graph()

    if parent_graph is not None and layer.parent_id is not None:
        summary = aggregate(
            parent_graph,
            layer.aggregation_strategy,
            layer.aggregation_params,
        )
        _save_provenance(summary, layer, out_root)
        G = merge_graphs(G, summary, layer.parent_id)

    communities = cluster(G)
    _save_layer_output(G, communities, layer, out_root)

    return G


def build_layers(
    config_path: Path,
    target_layer: str | None = None,
    parallel: bool = True,
) -> dict[str, nx.Graph]:
    """Build all layers (or a single target) from a layers.yaml config.

    Parameters
    ----------
    config_path:
        Path to ``layers.yaml``.
    target_layer:
        If provided, only build this layer (and auto-build dependencies if
        their output does not exist yet).
    parallel:
        If True, build same-depth layers concurrently.

    Returns
    -------
    dict mapping layer id → built graph.
    """
    layers = load_layers(config_path)
    registry = LayerRegistry(layers)
    out_root = config_path.parent / "graphify-out"

    built_graphs: dict[str, nx.Graph] = {}

    if target_layer is not None:
        target = registry.get_layer_by_id(target_layer)
        layers_to_build = _collect_deps(target, registry, out_root)
    else:
        layers_to_build = layers

    level_groups = _group_by_level(layers_to_build)

    for level, level_layers in sorted(level_groups.items()):
        parent_graphs = {l.parent_id: built_graphs.get(l.parent_id) for l in level_layers if l.parent_id}

        if parallel and len(level_layers) > 1:
            try:
                level_results = _build_level_parallel(level_layers, parent_graphs, out_root)
                built_graphs.update(level_results)
            except Exception as exc:
                print(
                    f"[graphify] Warning: parallel build failed ({exc}), "
                    f"retrying sequentially",
                    file=sys.stderr,
                )
                for layer in level_layers:
                    pg = parent_graphs.get(layer.parent_id)
                    if pg is None and layer.parent_id is not None:
                        pg = _try_load_parent(layer.parent_id, out_root)
                    print(f"[graphify] Building layer: {layer.id} ({layer.name})")
                    G = _build_single_layer(layer, pg, out_root)
                    built_graphs[layer.id] = G
        else:
            for layer in level_layers:
                pg = parent_graphs.get(layer.parent_id)
                if pg is None and layer.parent_id is not None:
                    pg = _try_load_parent(layer.parent_id, out_root)
                print(f"[graphify] Building layer: {layer.id} ({layer.name})")
                G = _build_single_layer(layer, pg, out_root)
                built_graphs[layer.id] = G

    return built_graphs


def _try_load_parent(parent_id: str, out_root: Path) -> nx.Graph | None:
    """Try to load a parent graph from disk."""
    graph_path = out_root / "layers" / parent_id / "graph.json"
    if graph_path.exists():
        try:
            return _load_graph(graph_path)
        except Exception:
            pass
    print(
        f"[graphify] Warning: parent layer '{parent_id}' "
        f"output not found, building without parent summary",
        file=sys.stderr,
    )
    return None


def _group_by_level(layers: list[LayerConfig]) -> dict[int, list[LayerConfig]]:
    """Group layers by their depth level."""
    groups: dict[int, list[LayerConfig]] = {}
    for layer in layers:
        groups.setdefault(layer.level, []).append(layer)
    return groups


def _build_level_parallel(
    level_layers: list[LayerConfig],
    parent_graphs: dict[str | None, nx.Graph | None],
    out_root: Path,
) -> dict[str, nx.Graph]:
    """Build layers at the same depth level in parallel."""
    from concurrent.futures import ProcessPoolExecutor, as_completed

    results: dict[str, nx.Graph] = {}

    def _build_task(layer: LayerConfig) -> tuple[str, nx.Graph]:
        pg = parent_graphs.get(layer.parent_id)
        print(f"[graphify] Building layer: {layer.id} ({layer.name})")
        G = _build_single_layer(layer, pg, out_root)
        return layer.id, G

    with ProcessPoolExecutor() as executor:
        futures = {executor.submit(_build_task, layer): layer for layer in level_layers}
        for future in as_completed(futures):
            layer_id, G = future.result()
            results[layer_id] = G

    return results


def _collect_deps(
    target: LayerConfig,
    registry: LayerRegistry,
    out_root: Path,
) -> list[LayerConfig]:
    """Collect target layer and its missing dependencies in topological order."""
    needed: list[LayerConfig] = []
    current: LayerConfig | None = target

    while current is not None:
        layer_dir = out_root / "layers" / current.id
        graph_path = layer_dir / "graph.json"

        if not graph_path.exists():
            needed.append(current)

        if current.parent_id is not None:
            current = registry.get_layer_by_id(current.parent_id)
        else:
            current = None

    needed.reverse()
    return needed


def _load_graph(path: Path) -> nx.Graph:
    """Load a graph from a graph.json file."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        return json_graph.node_link_graph(raw, edges="links")
    except TypeError:
        return json_graph.node_link_graph(raw)
