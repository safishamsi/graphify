"""Query routing for multi-layer knowledge graphs.

Routes natural-language questions to the most appropriate layer based on
keyword matching and abstraction-level heuristics, then optionally
auto-zooms into child layers when results are too sparse.

Typical usage::

    from graphify.query_router import QueryRouter
    from graphify.layer_config import load_layers, LayerRegistry

    layers = load_layers(Path("layers.yaml"))
    registry = LayerRegistry(layers)
    graphs = {"L0": G_L0, "L1": G_L1}

    router = QueryRouter(registry, graphs)
    layer_id = router.route("How does the system authenticate users?")
    result = router.query(layer_id, "How does the system authenticate users?")
"""
from __future__ import annotations

import sys
from pathlib import Path

import networkx as nx

from .layer_config import LayerConfig, LayerRegistry
from .serve import _score_nodes, _bfs, _subgraph_to_text


_ABSTRACT_TERMS_EN = frozenset({
    "architecture", "design", "system", "overview", "high-level", "structure",
    "pattern", "strategy", "framework", "concept", "abstraction", "module",
    "component", "layer", "topology", "landscape", "blueprint", "paradigm",
    "principle", "approach", "methodology", "model", "schema", "taxonomy",
    "hierarchy", "organization", "layout", "roadmap", "vision", "philosophy",
})

_ABSTRACT_TERMS_ZH = frozenset({
    "架构", "设计", "系统", "概览", "高层", "结构", "模式", "策略", "框架",
    "概念", "抽象", "模块", "组件", "层次", "拓扑", "蓝图", "范式", "原则",
    "方法", "模型", "体系", "组织", "规划", "愿景", "全局", "总体", "宏观",
})

_CONCRETE_TERMS_EN = frozenset({
    "function", "method", "class", "variable", "file", "line", "bug", "error",
    "implementation", "code", "source", "detail", "specific", "exact", "where",
    "how to", "parameter", "return", "type", "import", "call", "usage",
})

_CONCRETE_TERMS_ZH = frozenset({
    "函数", "方法", "类", "变量", "文件", "行", "bug", "错误", "实现",
    "代码", "源码", "细节", "具体", "精确", "哪里", "如何", "参数",
    "返回", "类型", "导入", "调用", "用法",
})


class QueryRouter:
    """Routes questions to the most appropriate knowledge graph layer."""

    def __init__(
        self,
        registry: LayerRegistry,
        graphs: dict[str, nx.Graph],
        *,
        auto_zoom_min_nodes: int = 5,
        auto_zoom_max_depth: int = 2,
    ) -> None:
        self._registry = registry
        self._graphs = graphs
        self._auto_zoom_min_nodes = auto_zoom_min_nodes
        self._auto_zoom_max_depth = auto_zoom_max_depth

    @property
    def registry(self) -> LayerRegistry:
        return self._registry

    @property
    def graphs(self) -> dict[str, nx.Graph]:
        return self._graphs

    def route(self, question: str) -> str:
        """Select the best layer for *question*.

        Uses keyword scoring with level-weighted abstraction heuristics.
        Falls back to the highest-level layer when no keywords match.
        """
        all_layers = list(self._registry._by_id.values())

        if not all_layers:
            raise ValueError("No layers configured")

        scores: dict[str, float] = {}
        question_lower = question.lower()

        for layer in all_layers:
            score = 0.0

            for kw in layer.route_keywords:
                if kw.lower() in question_lower:
                    score += 10.0

            abstract_hits = self._count_term_hits(question_lower, _ABSTRACT_TERMS_EN | _ABSTRACT_TERMS_ZH)
            concrete_hits = self._count_term_hits(question_lower, _CONCRETE_TERMS_EN | _CONCRETE_TERMS_ZH)

            level_weight = 1.0 + layer.level * 0.5
            score += abstract_hits * level_weight * 2.0
            score += concrete_hits * (1.0 / level_weight) * 2.0

            scores[layer.id] = score

        max_score = max(scores.values())
        if max_score == 0:
            highest = max(all_layers, key=lambda l: l.level)
            return highest.id

        best = max(scores, key=scores.get)
        return best

    @staticmethod
    def _count_term_hits(text: str, terms: frozenset[str]) -> int:
        """Count how many terms appear in text (substring match for CJK support)."""
        hits = 0
        for term in terms:
            if term in text:
                hits += 1
        return hits

    def query(
        self,
        layer_id: str,
        question: str,
        *,
        mode: str = "bfs",
        depth: int = 3,
        token_budget: int = 2000,
        auto_zoom: bool = True,
    ) -> tuple[str, str]:
        """Query a specific layer and optionally auto-zoom.

        Returns ``(layer_id, result_text)``.  If auto-zoom triggers, the
        returned *layer_id* is the zoomed-in layer and the text includes
        a zoom annotation prefix.
        """
        G = self._graphs.get(layer_id)
        if G is None:
            return layer_id, f"Layer '{layer_id}' not found."

        terms = [t.lower() for t in question.split() if len(t) > 2]
        scored = _score_nodes(G, terms)
        start_nodes = [nid for _, nid in scored[:3]]

        if not start_nodes:
            result_text = "No matching nodes found."
        else:
            nodes, edges = _bfs(G, start_nodes, depth)
            result_text = _subgraph_to_text(G, nodes, edges, token_budget)

        if auto_zoom and len(start_nodes) < self._auto_zoom_min_nodes:
            zoomed_id, zoomed_text = self._auto_zoom(
                layer_id, question, mode, depth, token_budget, zoom_depth=0
            )
            if zoomed_id != layer_id:
                return zoomed_id, zoomed_text

        return layer_id, f"[Layer: {layer_id}]\n{result_text}" if len(self._graphs) > 1 else result_text

    def _auto_zoom(
        self,
        current_layer_id: str,
        question: str,
        mode: str,
        depth: int,
        token_budget: int,
        zoom_depth: int,
    ) -> tuple[str, str]:
        """Drill down to child layers when results are sparse."""
        if zoom_depth >= self._auto_zoom_max_depth:
            return current_layer_id, ""

        children = self._registry.get_children(current_layer_id)
        if not children:
            return current_layer_id, ""

        child = children[0]
        G_child = self._graphs.get(child.id)
        if G_child is None:
            return current_layer_id, ""

        terms = [t.lower() for t in question.split() if len(t) > 2]
        scored = _score_nodes(G_child, terms)
        start_nodes = [nid for _, nid in scored[:3]]

        if not start_nodes:
            return current_layer_id, ""

        nodes, edges = _bfs(G_child, start_nodes, depth)
        child_text = _subgraph_to_text(G_child, nodes, edges, token_budget)

        annotation = f"[Auto-zoom: {current_layer_id} → {child.id}]\n"
        result = f"[Layer: {child.id}]\n{annotation}{child_text}"

        if len(start_nodes) < self._auto_zoom_min_nodes and zoom_depth + 1 < self._auto_zoom_max_depth:
            deeper_id, deeper_text = self._auto_zoom(
                child.id, question, mode, depth, token_budget, zoom_depth + 1
            )
            if deeper_id != child.id:
                return deeper_id, deeper_text

        return child.id, result

    def layer_info(self) -> str:
        """Return a summary of all layers with stats."""
        lines = ["Layer Information:"]
        for layer in self._registry._by_id.values():
            G = self._graphs.get(layer.id)
            if G is not None:
                stats = f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges"
            else:
                stats = "graph not loaded"
            parent = layer.parent_id or "(root)"
            lines.append(
                f"  {layer.id}: {layer.name} (level={layer.level}, parent={parent}) — {stats}"
            )
        return "\n".join(lines)

    def drill_down(
        self,
        layer_id: str,
        question: str,
        *,
        mode: str = "bfs",
        depth: int = 3,
        token_budget: int = 2000,
    ) -> str:
        """Query a specific layer by ID directly."""
        G = self._graphs.get(layer_id)
        if G is None:
            return f"Layer '{layer_id}' not found. Available: {', '.join(sorted(self._graphs))}"

        terms = [t.lower() for t in question.split() if len(t) > 2]
        scored = _score_nodes(G, terms)
        start_nodes = [nid for _, nid in scored[:3]]

        if not start_nodes:
            return f"[Layer: {layer_id}]\nNo matching nodes found."

        nodes, edges = _bfs(G, start_nodes, depth)
        result = _subgraph_to_text(G, nodes, edges, token_budget)
        return f"[Layer: {layer_id}]\n{result}"
