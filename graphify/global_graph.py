from __future__ import annotations
import json
import hashlib
import shutil
import sys
import warnings
from contextlib import suppress
from datetime import date, datetime, timezone
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph as _jg

from graphify.graph_loader import GRAPHIFY_PROFILE_KEY
from graphify.projections import normalize_to_multidigraph

_GLOBAL_DIR = Path.home() / ".graphify"
_GLOBAL_GRAPH = _GLOBAL_DIR / "global-graph.json"
_GLOBAL_MANIFEST = _GLOBAL_DIR / "global-manifest.json"

# Graphify graph_type vocabulary (kept byte-identical to graph_loader /
# export so the global graph profile round-trips through node_link_data).
_GRAPH_TYPE_SIMPLE = "simple"
_GRAPH_TYPE_DIGRAPH = "digraph"
_GRAPH_TYPE_MULTIDIGRAPH = "multidigraph"
_GRAPH_TYPES = frozenset({_GRAPH_TYPE_SIMPLE, _GRAPH_TYPE_DIGRAPH, _GRAPH_TYPE_MULTIDIGRAPH})


def _graph_type_for_instance(G: nx.Graph) -> str:
    """Return the graphify ``graph_type`` token for a live NetworkX instance.

    The instance is authoritative: classify from ``is_multigraph()`` /
    ``is_directed()`` rather than from any stored profile. Mirrors
    :func:`graphify.export._graph_type_for_instance` and the loader's
    :func:`~graphify.graph_loader._set_graph_profile` vocabulary so a
    save/load round-trip is stable.
    """
    if G.is_multigraph():
        return _GRAPH_TYPE_MULTIDIGRAPH
    if G.is_directed():
        return _GRAPH_TYPE_DIGRAPH
    return _GRAPH_TYPE_SIMPLE


def _graph_class_for_type(graph_type: str) -> type[nx.Graph]:
    """Map a graphify ``graph_type`` token to the NetworkX class that realizes it."""
    if graph_type == _GRAPH_TYPE_MULTIDIGRAPH:
        return nx.MultiDiGraph
    if graph_type == _GRAPH_TYPE_DIGRAPH:
        return nx.DiGraph
    return nx.Graph


def _project_to_class(G: nx.Graph, graph_type: str) -> nx.Graph:
    """Return a copy of *G* realized as the NetworkX class for *graph_type*.

    Multigraph targets reuse :func:`normalize_to_multidigraph` so parallel
    keys survive. Simple/digraph targets rebuild the skeleton and replay
    edges with keyless ``add_edge``; when *G* is itself a multigraph this is
    an intentional, caller-warned collapse (parallel edges fold onto one
    ``(u, v)`` pair). Already-correct classes are still copied so callers can
    mutate the result without aliasing the input.
    """
    if graph_type == _GRAPH_TYPE_MULTIDIGRAPH:
        return normalize_to_multidigraph(G)
    target_cls = _graph_class_for_type(graph_type)
    H = target_cls()
    H.graph.update(G.graph)
    H.add_nodes_from((node, attrs.copy()) for node, attrs in G.nodes(data=True))
    if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)):
        for u, v, _key, data in G.edges(keys=True, data=True):
            H.add_edge(u, v, **data)
    else:
        for u, v, data in G.edges(data=True):
            H.add_edge(u, v, **data)
    return H


def _infer_target_type(graphs: list[nx.Graph]) -> str:
    """Infer the composition target type from a list of graphs.

    Multidigraph if ANY input is a multigraph; else digraph if ANY input is
    directed; else simple. This is the no-explicit-target precedence the
    global compose and the merge driver both rely on.
    """
    if any(G.is_multigraph() for G in graphs):
        return _GRAPH_TYPE_MULTIDIGRAPH
    if any(G.is_directed() for G in graphs):
        return _GRAPH_TYPE_DIGRAPH
    return _GRAPH_TYPE_SIMPLE


def normalize_graphs_for_global(
    graphs: list[nx.Graph], *, target_type: str | None = None
) -> tuple[list[nx.Graph], str]:
    """Normalize a list of graphs to one common class for global composition.

    Reusable by both :func:`global_add` and the ``__main__`` merge driver /
    merge-graphs path so class normalization lives in exactly one place.

    - When *target_type* is ``None`` it is inferred via :func:`_infer_target_type`
      (multidigraph if any input is multi; else digraph if any directed; else
      simple). An inferred multidigraph target never loses data.
    - When *target_type* is an EXPLICIT ``"simple"`` / ``"digraph"`` and any
      input is a multigraph, that input is projected down to the simple class
      with an explicit :func:`warnings.warn` + stderr WARNING — graphify never
      silently collapses multigraph input without an explicit simple target.
    - Returns ``(normalized_graphs, resolved_target_type)`` where every graph
      is the same class and ``resolved_target_type`` is in the graph_type
      vocabulary.

    Raises:
        ValueError - *target_type* is not a recognized graph_type token.
    """
    if target_type is not None and target_type not in _GRAPH_TYPES:
        raise ValueError(
            f"target_type must be one of {sorted(_GRAPH_TYPES)}, got {target_type!r}"
        )

    explicit = target_type is not None
    resolved = target_type if explicit else _infer_target_type(graphs)

    if explicit and resolved != _GRAPH_TYPE_MULTIDIGRAPH:
        # Down-projecting an explicit simple/digraph target: warn loudly for
        # every multigraph input whose parallel edges are about to collapse.
        for G in graphs:
            if G.is_multigraph():
                msg = (
                    f"global compose: projecting multigraph input "
                    f"({G.number_of_edges()} edges) to '{resolved}' target — "
                    f"parallel edges will be collapsed onto single (u, v) pairs. "
                    f"Omit the explicit simple/digraph target to preserve them."
                )
                warnings.warn(msg, stacklevel=2)
                print(f"[graphify global] WARNING: {msg}", file=sys.stderr)

    normalized = [_project_to_class(G, resolved) for G in graphs]
    return normalized, resolved


def detect_pre_profile(data: object) -> bool:
    """Return True when a global-graph JSON dict predates profile/class metadata.

    A "pre-profile" graph JSON LACKS ``graphify_profile`` (at the top level and
    nested under ``"graph"``) AND lacks BOTH explicit ``multigraph`` / ``directed``
    flags. Such a file was written before class normalization existed, so it may
    already be a silently-collapsed simple graph whose lost parallel edges cannot
    be reconstructed. The presence of ANY of those four markers means the writer
    knew the graph class, so it is NOT pre-profile.
    """
    if not isinstance(data, dict):
        return False
    if GRAPHIFY_PROFILE_KEY in data:
        return False
    nested = data.get("graph")
    if isinstance(nested, dict) and GRAPHIFY_PROFILE_KEY in nested:
        return False
    if "multigraph" in data or "directed" in data:
        return False
    return True


class GlobalGraphRecoveryError(RuntimeError):
    """Raised when a global operation would irreversibly upgrade a pre-profile graph."""


def refuse_pre_profile_upgrade(
    data: dict,
    target_type: str,
    *,
    backup_hint: Path | None = None,
) -> None:
    """Refuse to upgrade a pre-profile global graph to multigraph.

    Reusable guard (callable by the merge driver) that enforces the recovery
    policy: a pre-profile global graph (see :func:`detect_pre_profile`) may
    already be collapsed, so "upgrading" it to a multidigraph target would
    fabricate a keyed graph from data that can no longer carry the lost
    parallel edges. In that case raise :class:`GlobalGraphRecoveryError` with a
    clear recovery message pointing at the backup and the rebuild-from-source
    path (``global remove`` + ``global add``).

    Simple-in -> simple-out (or digraph) operation on a pre-profile graph is
    NOT refused — only an upgrade to ``multidigraph`` is irreversible.
    """
    if target_type != _GRAPH_TYPE_MULTIDIGRAPH:
        return
    if not detect_pre_profile(data):
        return
    backup_line = (
        f" A pre-overwrite backup was saved at {backup_hint}."
        if backup_hint is not None
        else " Check ~/.graphify for a dated .bak snapshot of the previous graph."
    )
    raise GlobalGraphRecoveryError(
        "refusing to upgrade a pre-profile global graph to a multidigraph: the "
        "existing global-graph.json has no graphify_profile or multigraph/directed "
        "flags, so it predates class tracking and may already have collapsed "
        "parallel edges that cannot be reconstructed by upgrading in place."
        + backup_line
        + " To rebuild safely, remove the affected repos and re-add them from source "
        "(`graphify global remove <tag>` then `graphify global add`), which "
        "regenerates keyed parallel edges from the per-repo graph.json."
    )


def backup_global_graph() -> Path | None:
    """Snapshot the existing global-graph.json to a dated ``.bak`` before overwrite.

    Mirrors :func:`graphify.export.backup_if_protected`'s dated-snapshot pattern,
    adapted for the single global-graph.json file: the backup is written next to
    it as ``global-graph.<YYYY-MM-DD>.bak``. Idempotent within a day — if today's
    backup already holds byte-identical content the copy is skipped; if the live
    graph changed since the last backup today the snapshot is refreshed in place
    (one backup per day, always the latest pre-overwrite state).

    Returns the backup path, or None when there is nothing to back up (no
    existing global graph) or backup is disabled via ``GRAPHIFY_NO_BACKUP``.
    Never raises — a backup failure prints a warning and returns None so it can
    never block the write it protects.
    """
    import os

    if os.environ.get("GRAPHIFY_NO_BACKUP"):
        return None
    if not _GLOBAL_GRAPH.exists():
        return None

    today = date.today().isoformat()
    backup_path = _GLOBAL_GRAPH.with_name(f"{_GLOBAL_GRAPH.stem}.{today}.bak")
    try:
        if backup_path.exists():
            src_hash = hashlib.sha256(_GLOBAL_GRAPH.read_bytes()).hexdigest()
            bak_hash = hashlib.sha256(backup_path.read_bytes()).hexdigest()
            if src_hash == bak_hash:
                return backup_path  # identical content, nothing to do
        _GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_GLOBAL_GRAPH, backup_path)
        return backup_path
    except Exception as exc:
        print(
            f"[graphify global] warning: backup failed ({exc}) — continuing with overwrite",
            file=sys.stderr,
        )
        return None


def _load_manifest() -> dict:
    if _GLOBAL_MANIFEST.exists():
        with suppress(Exception):
            return json.loads(_GLOBAL_MANIFEST.read_text(encoding="utf-8"))
    return {"version": 1, "repos": {}}


def _save_manifest(manifest: dict) -> None:
    _GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    _GLOBAL_MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _read_global_graph_data() -> dict | None:
    """Return the raw global-graph.json dict (size-capped), or None if absent.

    Reads the on-disk JSON WITHOUT rebuilding the NetworkX graph so callers can
    inspect pre-profile markers (:func:`detect_pre_profile`) before deciding
    whether an operation is safe. The ``edges``->``links`` alias is normalized
    so downstream node_link_graph rehydration is consistent with
    :func:`_load_global_graph`.
    """
    if not _GLOBAL_GRAPH.exists():
        return None
    from graphify.security import check_graph_file_size_cap

    check_graph_file_size_cap(_GLOBAL_GRAPH)
    data = json.loads(_GLOBAL_GRAPH.read_text(encoding="utf-8"))
    if "links" not in data and "edges" in data:
        data = dict(data, links=data["edges"])
    return data


def _load_global_graph() -> nx.Graph:
    data = _read_global_graph_data()
    if data is not None:
        try:
            G = _jg.node_link_graph(data, edges="links")
        except TypeError:
            G = _jg.node_link_graph(data)
        # Surface the persisted profile (if any) on G.graph and reconcile its
        # graph_type with the live instance so a later save round-trips stably.
        _stamp_global_profile(G)
        return G
    return nx.Graph()


def _stamp_global_profile(G: nx.Graph) -> None:
    """Stamp ``G.graph[GRAPHIFY_PROFILE_KEY]`` with the instance graph_type.

    Existing profile fields are preserved; ``graph_type`` is always overwritten
    to match the live instance (the instance is authoritative), mirroring
    :func:`graphify.export._ensure_graph_profile`. This guarantees the global
    graph JSON always carries an accurate, round-trippable profile.
    """
    existing = G.graph.get(GRAPHIFY_PROFILE_KEY)
    profile = dict(existing) if isinstance(existing, dict) else {}
    profile["graph_type"] = _graph_type_for_instance(G)
    G.graph[GRAPHIFY_PROFILE_KEY] = profile


def _save_global_graph(G: nx.Graph) -> None:
    _GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    _stamp_global_profile(G)
    try:
        data = _jg.node_link_data(G, edges="links")
    except TypeError:
        data = _jg.node_link_data(G)
    # Defensively guarantee the profile is present under data["graph"] even if a
    # backend did not surface G.graph (node_link_data normally does).
    graph_meta = data.get("graph")
    if not isinstance(graph_meta, dict):
        graph_meta = {}
        data["graph"] = graph_meta
    if GRAPHIFY_PROFILE_KEY not in graph_meta:
        graph_meta[GRAPHIFY_PROFILE_KEY] = dict(G.graph[GRAPHIFY_PROFILE_KEY])
    _GLOBAL_GRAPH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def global_add(source_path: Path, repo_tag: str) -> dict:
    """Add or update a project graph in the global graph.

    Returns a summary dict with keys: repo_tag, nodes_added, nodes_removed, skipped.
    Skipped=True means the source graph hasn't changed since last add.
    """
    from graphify.build import prefix_graph_for_global, prune_repo_from_graph

    if not source_path.exists():
        raise FileNotFoundError(f"graph not found: {source_path}")

    manifest = _load_manifest()
    src_hash = _file_hash(source_path)

    existing = manifest["repos"].get(repo_tag, {})
    existing_path = existing.get("source_path", "")
    if existing_path and existing_path != str(source_path.resolve()):
        print(
            f"[graphify global] warning: repo tag '{repo_tag}' previously pointed to "
            f"{existing_path!r}, now updating to {str(source_path.resolve())!r}. "
            f"Use --as <tag> to give it a different name.",
            file=sys.stderr,
        )
    if existing.get("source_hash") == src_hash:
        return {"repo_tag": repo_tag, "nodes_added": 0, "nodes_removed": 0, "skipped": True}

    # Load source graph
    from graphify.security import check_graph_file_size_cap

    check_graph_file_size_cap(source_path)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    if "links" not in data and "edges" in data:
        data = dict(data, links=data["edges"])
    try:
        src_G = _jg.node_link_graph(data, edges="links")
    except TypeError:
        src_G = _jg.node_link_graph(data)

    # Prefix IDs for cross-project isolation (relabel_nodes preserves multigraph
    # keys, so a MultiDiGraph source keeps its parallel edges through this step).
    prefixed = prefix_graph_for_global(src_G, repo_tag)

    # Inspect the on-disk global graph BEFORE rehydrating, so the recovery
    # policy can see whether it is a pre-profile file that may already have
    # collapsed parallel edges.
    existing_data = _read_global_graph_data()

    # Load global graph and prune stale nodes for this repo. Pruning happens on
    # the loaded class; the surviving (other-repo) subgraph is what we compose
    # the incoming repo into.
    G = _load_global_graph()
    removed = prune_repo_from_graph(G, repo_tag)

    # Resolve the composition target class: multidigraph if EITHER the existing
    # global graph OR the incoming source is multi; else digraph if either is
    # directed; else simple. Inferred (target_type=None) never silently
    # collapses — a simple+multi mix upgrades to multidigraph, which is exactly
    # the go/no-go gate (no class-mismatch crash, no silent collapse).
    target_type = _infer_target_type([G, prefixed])

    # Recovery refusal: if composing would UPGRADE a pre-profile global graph to
    # multidigraph (lost parallel edges unreconstructable), back up first so the
    # refusal can point at the snapshot, then refuse without mutating the file.
    if existing_data is not None and target_type == _GRAPH_TYPE_MULTIDIGRAPH:
        if detect_pre_profile(existing_data):
            backup_hint = backup_global_graph()
            refuse_pre_profile_upgrade(existing_data, target_type, backup_hint=backup_hint)

    # Normalize the surviving global graph and the prefixed source to the common
    # target class. normalize_graphs_for_global returns them in the same order.
    (G, prefixed), target_type = normalize_graphs_for_global(
        [G, prefixed], target_type=target_type
    )

    # Merge external-library nodes (no source_file) by label to avoid duplication
    external_labels = {
        d.get("label", ""): n
        for n, d in G.nodes(data=True)
        if not d.get("source_file") and d.get("label")
    }
    nodes_to_skip = set()
    for node, ndata in prefixed.nodes(data=True):
        if not ndata.get("source_file") and ndata.get("label") in external_labels:
            nodes_to_skip.add(node)

    # Compose: add prefixed nodes (except deduplicated externals) into global graph
    for node, ndata in prefixed.nodes(data=True):
        if node not in nodes_to_skip:
            G.add_node(node, **ndata)
    # KEY-AWARE edge compose. For a multigraph target, iterate keys=True and
    # replay G.add_edge(u, v, key=key, ...) so parallel edges are preserved
    # distinctly AND re-adding the same (pruned-then-readded) repo overwrites the
    # same (u, v, key) slots instead of accumulating fresh auto-int keys — that
    # keyless drift is the bug this fixes. Simple/digraph targets keep the
    # historical keyless behavior (one edge per pair), unchanged byte-for-byte.
    if isinstance(prefixed, (nx.MultiGraph, nx.MultiDiGraph)):
        for u, v, key, edata in prefixed.edges(keys=True, data=True):
            if u not in nodes_to_skip and v not in nodes_to_skip:
                G.add_edge(u, v, key=key, **edata)
    else:
        for u, v, edata in prefixed.edges(data=True):
            if u not in nodes_to_skip and v not in nodes_to_skip:
                G.add_edge(u, v, **edata)

    added = prefixed.number_of_nodes() - len(nodes_to_skip)

    # Back up the existing global graph before the irreversible overwrite. Cheap
    # and idempotent within a day; no-op when there is nothing to back up.
    backup_global_graph()
    _save_global_graph(G)

    manifest["repos"][repo_tag] = {
        "added_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path.resolve()),
        "node_count": added,
        "edge_count": prefixed.number_of_edges(),
        "source_hash": src_hash,
        "graph_type": target_type,
    }
    _save_manifest(manifest)

    return {"repo_tag": repo_tag, "nodes_added": added, "nodes_removed": removed, "skipped": False}


def global_remove(repo_tag: str) -> int:
    """Remove all nodes for repo_tag from the global graph. Returns count removed."""
    from graphify.build import prune_repo_from_graph

    manifest = _load_manifest()
    if repo_tag not in manifest["repos"]:
        raise KeyError(f"repo '{repo_tag}' not in global graph")

    G = _load_global_graph()
    removed = prune_repo_from_graph(G, repo_tag)
    _save_global_graph(G)

    del manifest["repos"][repo_tag]
    _save_manifest(manifest)
    return removed


def global_list() -> dict:
    """Return the manifest repos dict."""
    return _load_manifest().get("repos", {})


def global_path() -> Path:
    return _GLOBAL_GRAPH
