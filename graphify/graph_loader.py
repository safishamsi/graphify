"""Schema-aware graph loader for saved graphify node-link JSON.

This module loads *serialized graph files* (graph.json / node-link format).
It is distinct from :func:`graphify.build.build_from_json`, which assembles
graphs from raw extraction dicts produced by AST and semantic passes.

The two are complementary:
  - extraction dict  →  ``build_from_json``
  - saved graph.json →  ``load_graph`` / ``load_graph_file``
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import networkx as nx

from .edge_identity import strip_schema_key
from .multigraph_compat import require_multigraph_capabilities

GRAPHIFY_PROFILE_KEY = "graphify_profile"


def load_graph(
    data: dict,
    *,
    require_capabilities: bool = True,
) -> nx.Graph | nx.DiGraph | nx.MultiDiGraph:
    """Load a serialized node-link graph dict into the appropriate NetworkX type.

    Detects graph type from ``multigraph`` and ``directed`` flags in *data*:

    - ``multigraph: true``               → :class:`nx.MultiDiGraph`
    - ``multigraph: false, directed: true``  → :class:`nx.DiGraph`
    - ``multigraph: false, directed: false`` → :class:`nx.Graph`

    All paths set ``G.graph[GRAPHIFY_PROFILE_KEY]`` with at minimum
    ``{"graph_type": "simple" | "digraph" | "multidigraph"}``.

    ``require_capabilities`` (default ``True``) gates multigraph loading behind
    :func:`~graphify.multigraph_compat.require_multigraph_capabilities`.  Pass
    ``False`` to skip the probe entirely — used in unit tests and when the
    caller has already verified capabilities externally.
    """
    if data.get("multigraph", False):
        if data.get("directed", None) is False:
            print(
                "[graphify] WARNING: multigraph=true but directed=false; "
                "normalizing to MultiDiGraph (graphify uses directed graphs).",
                file=sys.stderr,
            )
        if require_capabilities:
            require_multigraph_capabilities()
        return _load_multigraph(data)
    if data.get("directed", False):
        return _load_directed_simple(data)
    return _load_simple(data)


def load_graph_file(
    path: str | Path,
    *,
    require_capabilities: bool = True,
) -> nx.Graph | nx.DiGraph | nx.MultiDiGraph:
    """Load a graph.json file produced by graphify.

    Applies the 512 MiB size cap before parsing.
    """
    from .security import check_graph_file_size_cap

    path = Path(path)
    check_graph_file_size_cap(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return load_graph(data, require_capabilities=require_capabilities)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_edges(data: dict) -> list[dict]:
    """Return the edge list, accepting both ``"edges"`` and legacy ``"links"``."""
    for key in ("edges", "links"):
        if key in data:
            val = data[key]
            if not isinstance(val, list):
                raise TypeError(f"'{key}' must be a list, got {type(val).__name__}")
            return list(val)
    return []


def _set_graph_profile(G: nx.Graph, data: dict, *, graph_type: str) -> None:
    """Store Graphify profile metadata in ``G.graph[GRAPHIFY_PROFILE_KEY]``."""
    raw = data.get(GRAPHIFY_PROFILE_KEY)
    profile = dict(raw) if isinstance(raw, dict) else {}
    profile.setdefault("graph_type", graph_type)
    G.graph[GRAPHIFY_PROFILE_KEY] = profile


def _add_nodes(G: nx.Graph, data: dict) -> set[str]:
    """Add valid nodes from *data* to *G*; return the resulting node ID set."""
    for node in data.get("nodes", []):
        if not isinstance(node, dict) or "id" not in node:
            continue
        G.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    return set(G.nodes())


def _load_simple(data: dict) -> nx.Graph:
    """Build an undirected :class:`nx.Graph` from node-link data."""
    G = nx.Graph()
    _set_graph_profile(G, data, graph_type="simple")
    node_set = _add_nodes(G, data)
    for edge in _get_edges(data):
        if not isinstance(edge, dict):
            continue
        src = edge["source"] if "source" in edge else edge.get("from")
        tgt = edge["target"] if "target" in edge else edge.get("to")
        if not src or not tgt or src not in node_set or tgt not in node_set:
            continue
        attrs = {k: v for k, v in edge.items() if k not in ("source", "target", "from", "to")}
        _, attrs = strip_schema_key(attrs)
        G.add_edge(src, tgt, **attrs)
    return G


def _load_directed_simple(data: dict) -> nx.DiGraph:
    """Build a directed :class:`nx.DiGraph` from node-link data."""
    G = nx.DiGraph()
    _set_graph_profile(G, data, graph_type="digraph")
    node_set = _add_nodes(G, data)
    for edge in _get_edges(data):
        if not isinstance(edge, dict):
            continue
        src = edge["source"] if "source" in edge else edge.get("from")
        tgt = edge["target"] if "target" in edge else edge.get("to")
        if not src or not tgt or src not in node_set or tgt not in node_set:
            continue
        attrs = {k: v for k, v in edge.items() if k not in ("source", "target", "from", "to")}
        _, attrs = strip_schema_key(attrs)
        G.add_edge(src, tgt, **attrs)
    return G


def _load_multigraph(data: dict) -> nx.MultiDiGraph:
    """Build a :class:`nx.MultiDiGraph` with preserved edge keys.

    Missing-key repair: when a serialized edge has no ``"key"`` field, a
    deterministic repair key is generated from the full edge attribute payload
    (not just the 3 identity fields) so parallel edges with different metadata
    are never silently overwritten.
    """
    G = nx.MultiDiGraph()
    _set_graph_profile(G, data, graph_type="multidigraph")
    node_set = _add_nodes(G, data)
    missing_key_count = 0
    for edge in _get_edges(data):
        if not isinstance(edge, dict):
            continue
        src = edge["source"] if "source" in edge else edge.get("from")
        tgt = edge["target"] if "target" in edge else edge.get("to")
        if not src or not tgt or src not in node_set or tgt not in node_set:
            continue
        attrs = {k: v for k, v in edge.items() if k not in ("source", "target", "from", "to")}
        key, attrs = strip_schema_key(attrs)
        if key is not None and not isinstance(key, str):
            raise TypeError(f"multigraph edge 'key' must be a string, got {type(key).__name__!r}")
        if key is None:
            missing_key_count += 1
            # Hash the full payload so edges with different metadata get different
            # keys and both survive (identity-field-only hashing collapses distinct
            # parallel edges that share relation/source_file/source_location).
            repair_payload = json.dumps(attrs, sort_keys=True, default=str)
            repair_digest = hashlib.sha256(repair_payload.encode()).hexdigest()
            key = f"edge:v1:{repair_digest}"
        G.add_edge(src, tgt, key=key, **attrs)
    if missing_key_count:
        print(
            f"[graphify] WARNING: {missing_key_count} multigraph edge(s) were missing "
            f"'key' — generated repair keys from full edge payload.",
            file=sys.stderr,
        )
    return G
