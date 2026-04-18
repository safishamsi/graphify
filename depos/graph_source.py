"""Graph source abstraction.

Every intelligence-layer module that needs a graph receives
``nx.DiGraph`` via a :class:`GraphSource`. Only this module is allowed to
call ``depos.snapshot``; ``depos.enrichment``, ``depos.analysis``, and
``depos.cli`` MUST import :class:`GraphSource` rather than touching
snapshot directly.

Adding a future :class:`CPGSource` is a new class + constructor wiring in
one place — no refactor needed across Modules 1–7.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

import networkx as nx


@runtime_checkable
class GraphSource(Protocol):
    """Read-only view of a structural graph."""

    def get_graph(self) -> nx.DiGraph: ...

    def get_source_metadata(self) -> dict[str, Any]: ...


class GraphifySource:
    """Phase 1 source: graphify extract → build_from_json, wrapped here."""

    def __init__(
        self,
        *,
        root: Optional[Path] = None,
        graph_json_path: Optional[Path] = None,
        version: str = "graphify-phase1",
    ) -> None:
        if root is None and graph_json_path is None:
            raise ValueError("Provide either root= or graph_json_path=")
        self._root = Path(root).resolve() if root is not None else None
        self._graph_json = Path(graph_json_path) if graph_json_path is not None else None
        self._graph: Optional[nx.DiGraph] = None
        self._version = version

    def get_graph(self) -> nx.DiGraph:
        if self._graph is not None:
            return self._graph
        if self._graph_json is not None:
            from depos.snapshot import load_graph_json  # local import: isolation rule

            g = load_graph_json(self._graph_json)
        else:
            from depos.snapshot import build_graph_for_root

            _, g = build_graph_for_root(self._root, directed=True)  # type: ignore[arg-type]
        if not isinstance(g, nx.DiGraph):
            g = nx.DiGraph(g)
        self._graph = g
        return g

    def get_source_metadata(self) -> dict[str, Any]:
        return {
            "source_type": "graphify",
            "version": self._version,
            "repo_path": str(self._root) if self._root else None,
            "graph_json": str(self._graph_json) if self._graph_json else None,
        }


class CPGSource:
    """Phase 2 source: loads a CPG JSON artifact into a DiGraph.

    Not used in Phase 1. The constructor is accepted so downstream code
    can already reference ``CPGSource`` behind a feature flag, but
    :meth:`get_graph` raises :class:`NotImplementedError` until a concrete
    CPG artifact format is pinned.
    """

    def __init__(self, *, cpg_path: Path, version: str = "cpg-future") -> None:
        self._cpg_path = Path(cpg_path)
        self._version = version

    def get_graph(self) -> nx.DiGraph:  # pragma: no cover - Phase 2
        raise NotImplementedError(
            "CPGSource is reserved for Phase 2; no CPG artifact format is pinned yet. "
            "Use GraphifySource for Phase 1."
        )

    def get_source_metadata(self) -> dict[str, Any]:
        return {
            "source_type": "cpg",
            "version": self._version,
            "cpg_path": str(self._cpg_path),
        }


class InMemoryGraphSource:
    """Test helper: wraps an already-constructed DiGraph. Not for production
    code paths."""

    def __init__(self, graph: nx.DiGraph, *, metadata: Optional[dict[str, Any]] = None) -> None:
        if not isinstance(graph, nx.DiGraph):
            graph = nx.DiGraph(graph)
        self._graph = graph
        self._metadata = metadata or {"source_type": "in_memory", "version": "test", "repo_path": None}

    def get_graph(self) -> nx.DiGraph:
        return self._graph

    def get_source_metadata(self) -> dict[str, Any]:
        return dict(self._metadata)

    @classmethod
    def from_node_link_json(cls, path: Path) -> "InMemoryGraphSource":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        g = nx.DiGraph()
        for node in data.get("nodes", []):
            nid = node.get("id")
            attrs = {k: v for k, v in node.items() if k != "id"}
            g.add_node(nid, **attrs)
        for edge in data.get("links", data.get("edges", [])):
            src = edge.get("source")
            tgt = edge.get("target")
            attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
            g.add_edge(src, tgt, **attrs)
        return cls(g, metadata={"source_type": "fixture", "version": "test", "repo_path": str(path)})
