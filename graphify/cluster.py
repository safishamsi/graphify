"""Community detection on NetworkX graphs. Uses Leiden (graspologic) if available, falls back to Louvain (networkx). Splits oversized communities. Returns cohesion scores."""
from __future__ import annotations
import contextlib
import inspect
import io
import sys
import networkx as nx


def _suppress_output():
    """Context manager to suppress stdout/stderr during library calls.

    graspologic's leiden() emits ANSI escape sequences (progress bars,
    colored warnings) that corrupt PowerShell 5.1's scroll buffer on
    Windows (see issue #19). Redirecting stdout/stderr to devnull during
    the call prevents this without losing any graphify output.
    """
    return contextlib.redirect_stdout(io.StringIO())


def _partition(G: nx.Graph) -> dict[str, int]:
    """Run community detection. Returns {node_id: community_id}.

    Tries Leiden (graspologic) first — best quality.
    Falls back to Louvain (built into networkx) if graspologic is not installed.

    Output from graspologic is suppressed to prevent ANSI escape codes
    from corrupting terminal scroll buffers on Windows PowerShell 5.1.
    """
    try:
        from graspologic.partition import leiden
        # Suppress graspologic output to prevent ANSI escape codes from
        # corrupting PowerShell 5.1 scroll buffer (issue #19)
        old_stderr = sys.stderr
        try:
            sys.stderr = io.StringIO()
            with _suppress_output():
                result = leiden(G)
        finally:
            sys.stderr = old_stderr
        return result
    except ImportError:
        pass

    # Fallback: networkx louvain (available since networkx 2.7).
    # Inspect kwargs to stay compatible across NetworkX versions — max_level
    # was added in a later release and prevents hangs on large sparse graphs.
    kwargs: dict = {"seed": 42, "threshold": 1e-4}
    if "max_level" in inspect.signature(nx.community.louvain_communities).parameters:
        kwargs["max_level"] = 10
    communities = nx.community.louvain_communities(G, **kwargs)
    return {node: cid for cid, nodes in enumerate(communities) for node in nodes}


from .constants import MAX_COMMUNITY_FRACTION as _MAX_COMMUNITY_FRACTION
from .constants import MIN_SPLIT_SIZE as _MIN_SPLIT_SIZE


def cluster(G: nx.Graph | nx.DiGraph) -> dict[int, list[str]]:
    """Run Leiden community detection. Returns {community_id: [node_ids]}.

    Community IDs are stable across runs: 0 = largest community after splitting.
    Oversized communities (> 25% of graph nodes, min 10) are split by running
    a second Leiden pass on the subgraph.

    Accepts directed or undirected graphs. DiGraphs are converted to undirected
    internally since Louvain/Leiden require undirected input.
    """
    if G.number_of_nodes() == 0:
        return {}
    if G.is_directed():
        G = G.to_undirected()
    if G.number_of_edges() == 0:
        return {i: [n] for i, n in enumerate(sorted(G.nodes))}

    # G is already undirected at this point (converted above if needed)
    U = G

    # Pre-filter: split into connected components and run Leiden on each
    # independently. This avoids running Leiden on the full graph when it
    # consists of multiple disconnected subgraphs (common for multi-repo corpora).
    isolates = [n for n in U.nodes() if U.degree(n) == 0]

    raw: dict[int, list[str]] = {}
    next_cid = 0
    for component in nx.connected_components(U):
        if len(component) == 1:
            isolates.extend(component)
            continue
        subgraph = U.subgraph(component)
        partition = _partition(subgraph)
        # Remap community IDs to avoid collisions between components
        local_communities: dict[int, list[str]] = {}
        for node, cid in partition.items():
            local_communities.setdefault(cid, []).append(node)
        for nodes in local_communities.values():
            raw[next_cid] = nodes
            next_cid += 1

    # Each isolate becomes its own single-node community
    next_cid = max(raw.keys(), default=-1) + 1
    for node in isolates:
        raw[next_cid] = [node]
        next_cid += 1

    # Split oversized communities
    max_size = max(_MIN_SPLIT_SIZE, int(U.number_of_nodes() * _MAX_COMMUNITY_FRACTION))
    final_communities: list[list[str]] = []
    for nodes in raw.values():
        if len(nodes) > max_size:
            final_communities.extend(_split_community(U, nodes))
        else:
            final_communities.append(nodes)

    # Re-index by size descending for deterministic ordering
    final_communities.sort(key=len, reverse=True)
    return {i: sorted(nodes) for i, nodes in enumerate(final_communities)}


def _split_community(G: nx.Graph, nodes: list[str]) -> list[list[str]]:
    """Run a second Leiden pass on a community subgraph to split it further."""
    subgraph = G.subgraph(nodes)
    if subgraph.number_of_edges() == 0:
        # No edges - split into individual nodes
        return [[n] for n in sorted(nodes)]
    try:
        sub_partition = _partition(subgraph)
        sub_communities: dict[int, list[str]] = {}
        for node, cid in sub_partition.items():
            sub_communities.setdefault(cid, []).append(node)
        if len(sub_communities) <= 1:
            return [sorted(nodes)]
        return [sorted(v) for v in sub_communities.values()]
    except Exception:
        return [sorted(nodes)]


def cohesion_score(G: nx.Graph | nx.DiGraph, community_nodes: list[str]) -> float:
    """Ratio of actual intra-community edges to maximum possible."""
    n = len(community_nodes)
    if n <= 1:
        return 1.0
    U = G.to_undirected() if G.is_directed() else G
    subgraph = U.subgraph(community_nodes)
    actual = subgraph.number_of_edges()
    possible = n * (n - 1) / 2
    return round(actual / possible, 2) if possible > 0 else 0.0


def score_all(G: nx.Graph | nx.DiGraph, communities: dict[int, list[str]]) -> dict[int, float]:
    return {cid: cohesion_score(G, nodes) for cid, nodes in communities.items()}
