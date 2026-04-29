# MCP stdio server - exposes graph query tools to Claude and other agents
from __future__ import annotations
import json
import sys
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph
from graphify.security import sanitize_label
from graphify.query_planner import select_start_nodes_by_degree, order_frontier_by_confidence
from graphify.query_cache import cache_key, get_cached_query, set_cached_query
from graphify.matviews import check_materialized_path
from graphify.approx import sample_subgraph, _should_skip_query, build_path_bloom_filter


def _load_graph(graph_path: str) -> nx.Graph:
    try:
        resolved = Path(graph_path).resolve()
        if resolved.suffix != ".json":
            raise ValueError(f"Graph path must be a .json file, got: {graph_path!r}")
        if not resolved.exists():
            raise FileNotFoundError(f"Graph file not found: {resolved}")
        safe = resolved
        data = json.loads(safe.read_text(encoding="utf-8"))
        try:
            return json_graph.node_link_graph(data, edges="links")
        except TypeError:
            return json_graph.node_link_graph(data)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"error: graph.json is corrupted ({exc}). Re-run /graphify to rebuild.", file=sys.stderr)
        sys.exit(1)


def _communities_from_graph(G: nx.Graph) -> dict[int, list[str]]:
    """Reconstruct community dict from community property stored on nodes."""
    communities: dict[int, list[str]] = {}
    for node_id, data in G.nodes(data=True):
        cid = data.get("community")
        if cid is not None:
            communities.setdefault(int(cid), []).append(node_id)
    return communities


def _strip_diacritics(text: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _score_nodes(G: nx.Graph, terms: list[str]) -> list[tuple[float, str]]:
    indexes = G.graph.get("indexes", {}) if hasattr(G, "graph") else {}
    label_index = indexes.get("label_index", {})
    scored = []
    norm_terms = [_strip_diacritics(t).lower() for t in terms]
    if label_index:
        seen: set[str] = set()
        for term in norm_terms:
            for length in range(min(3, len(term)), 0, -1):
                prefix = term[:length]
                for nid in label_index.get(prefix, []):
                    if nid in seen:
                        continue
                    seen.add(nid)
                    data = G.nodes[nid]
                    norm_label = data.get("norm_label") or _strip_diacritics(data.get("label") or "").lower()
                    source = (data.get("source_file") or "").lower()
                    s = sum(1 for t in norm_terms if t in norm_label) + sum(0.5 for t in norm_terms if t in source)
                    if s > 0:
                        scored.append((s, nid))
        return sorted(scored, reverse=True)
    for nid, data in G.nodes(data=True):
        norm_label = data.get("norm_label") or _strip_diacritics(data.get("label") or "").lower()
        source = (data.get("source_file") or "").lower()
        score = sum(1 for t in norm_terms if t in norm_label) + sum(0.5 for t in norm_terms if t in source)
        if score > 0:
            scored.append((score, nid))
    return sorted(scored, reverse=True)


def _bfs(G: nx.Graph, start_nodes: list[str], depth: int) -> tuple[set[str], list[tuple]]:
    visited: set[str] = set(start_nodes)
    frontier = set(start_nodes)
    edges_seen: list[tuple] = []
    for _ in range(depth):
        next_frontier: set[str] = set()
        for n in frontier:
            for neighbor in G.neighbors(n):
                if neighbor not in visited:
                    next_frontier.add(neighbor)
                    edges_seen.append((n, neighbor))
        visited.update(next_frontier)
        frontier = next_frontier
    return visited, edges_seen


def _bfs_planned(
    G: nx.Graph, start_node: str, depth: int, preference: str = "extracted"
) -> tuple[set[str], list[tuple]]:
    """BFS with planner: reorder frontier at each hop by confidence and degree."""
    visited: set[str] = {start_node}
    frontier = [start_node]
    edges_seen: list[tuple] = []
    for _ in range(depth):
        next_frontier: list[str] = []
        for n in frontier:
            for neighbor in G.neighbors(n):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.append(neighbor)
                    edges_seen.append((n, neighbor))
        frontier = order_frontier_by_confidence(G, next_frontier, preference)
    return visited, edges_seen


def _dfs(G: nx.Graph, start_nodes: list[str], depth: int) -> tuple[set[str], list[tuple]]:
    visited: set[str] = set()
    edges_seen: list[tuple] = []
    stack = [(n, 0) for n in reversed(start_nodes)]
    while stack:
        node, d = stack.pop()
        if node in visited or d > depth:
            continue
        visited.add(node)
        for neighbor in G.neighbors(node):
            if neighbor not in visited:
                stack.append((neighbor, d + 1))
                edges_seen.append((node, neighbor))
    return visited, edges_seen


def _bidirectional_shortest_path(
    G: nx.Graph, src: str, tgt: str, max_hops: int = 20
) -> tuple[list[str], float]:
    """BFS from both src and tgt simultaneously. Returns (path_nodes, path_length).

    Uses edge relation index if available for faster neighbor access.
    """
    if src == tgt:
        return [src], 0.0
    if src not in G or tgt not in G:
        return [], float("inf")
    f_parent: dict[str, str | None] = {src: None}
    b_parent: dict[str, str | None] = {tgt: None}
    f_frontier = {src}
    b_frontier = {tgt}
    f_dist: dict[str, float] = {src: 0}
    b_dist: dict[str, float] = {tgt: 0}
    mid = None
    for _ in range(max_hops):
        nf: set[str] = set()
        for n in f_frontier:
            dist = f_dist[n] + 1
            for nb in G.neighbors(n):
                if nb in f_parent:
                    continue
                f_parent[nb] = n
                f_dist[nb] = dist
                nf.add(nb)
                if nb in b_parent:
                    mid = nb
                    break
            if mid:
                break
        if mid:
            break
        f_frontier = nf
        nb_set: set[str] = set()
        for n in b_frontier:
            dist = b_dist[n] + 1
            for nb in G.neighbors(n):
                if nb in b_parent:
                    continue
                b_parent[nb] = n
                b_dist[nb] = dist
                nb_set.add(nb)
                if nb in f_parent:
                    mid = nb
                    break
            if mid:
                break
        if mid:
            break
        b_frontier = nb_set
        if not f_frontier or not b_frontier:
            break
    if mid is None:
        return [], float("inf")
    path: list[str] = []
    cur = mid
    while cur is not None:
        path.append(cur)
        cur = f_parent[cur]
    path.reverse()
    cur = b_parent[mid]
    while cur is not None:
        path.append(cur)
        cur = b_parent[cur]
    length = float(len(path) - 1)
    return path, length


def _dijkstra_shortest_path(
    G: nx.Graph, src: str, tgt: str
) -> tuple[list[str], float]:
    """Uses edge['weight'] field. Returns (path, total_weight)."""
    import heapq
    if src == tgt:
        return [src], 0.0
    if src not in G or tgt not in G:
        return [], float("inf")
    dist: dict[str, float] = {src: 0}
    parent: dict[str, str | None] = {src: None}
    pq = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, float("inf")):
            continue
        if u == tgt:
            break
        for v in G.neighbors(u):
            w = G.edges[u, v].get("weight", 1.0)
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                parent[v] = u
                heapq.heappush(pq, (nd, v))
    if tgt not in parent:
        return [], float("inf")
    path: list[str] = []
    cur: str | None = tgt
    while cur is not None:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path, dist[tgt]


def _astar_search(
    G: nx.Graph, src: str, tgt: str, communities: dict[int, list[str]], max_hops: int = 20
) -> list[str]:
    """A* with heuristic h(n) = 1 if different community else 0.5."""
    import heapq
    if src == tgt:
        return [src]
    if src not in G or tgt not in G:
        return []
    node_comm: dict[str, int] = {}
    for cid, node_list in communities.items():
        for nid in node_list:
            node_comm[nid] = cid
    tgt_c = node_comm.get(tgt)

    def h(n: str) -> float:
        c = node_comm.get(n)
        if tgt_c is not None and c is not None:
            return 0.5 if c == tgt_c else 1.0
        return 0.5

    parent: dict[str, str | None] = {src: None}
    g: dict[str, float] = {src: 0}
    open_set = [(h(src), 0, src)]
    while open_set:
        _, cost, u = heapq.heappop(open_set)
        if cost > g.get(u, float("inf")):
            continue
        if u == tgt:
            break
        if cost >= max_hops:
            continue
        for v in G.neighbors(u):
            ng = cost + 1
            if ng < g.get(v, float("inf")):
                g[v] = ng
                parent[v] = u
                heapq.heappush(open_set, (ng + h(v), ng, v))
    if tgt not in parent:
        return []
    path: list[str] = []
    cur: str | None = tgt
    while cur is not None:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path


def _subgraph_to_text(G: nx.Graph, nodes: set[str], edges: list[tuple], token_budget: int = 2000) -> str:
    """Render subgraph as text, cutting at token_budget (approx 3 chars/token)."""
    char_budget = token_budget * 3
    lines = []
    for nid in sorted(nodes, key=lambda n: G.degree(n), reverse=True):
        d = G.nodes[nid]
        line = f"NODE {sanitize_label(d.get('label', nid))} [src={d.get('source_file', '')} loc={d.get('source_location', '')} community={d.get('community', '')}]"
        lines.append(line)
    for u, v in edges:
        if u in nodes and v in nodes:
            raw = G[u][v]
            d = next(iter(raw.values()), {}) if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)) else raw
            line = f"EDGE {sanitize_label(G.nodes[u].get('label', u))} --{d.get('relation', '')} [{d.get('confidence', '')}]--> {sanitize_label(G.nodes[v].get('label', v))}"
            lines.append(line)
    output = "\n".join(lines)
    if len(output) > char_budget:
        output = output[:char_budget] + f"\n... (truncated to ~{token_budget} token budget)"
    return output


def _find_node(G: nx.Graph, label: str) -> list[str]:
    """Return node IDs whose label or ID matches the search term (diacritic-insensitive)."""
    term = _strip_diacritics(label).lower()
    return [nid for nid, d in G.nodes(data=True)
            if term in (d.get("norm_label") or _strip_diacritics(d.get("label") or "").lower())
            or term == nid.lower()]


def _filter_blank_stdin() -> None:
    """Filter blank lines from stdin before MCP reads it.

    Some MCP clients (Claude Desktop, etc.) send blank lines between JSON
    messages. The MCP stdio transport tries to parse every line as a
    JSONRPCMessage, so a bare newline triggers a Pydantic ValidationError.
    This installs an OS-level pipe that relays stdin while dropping blanks.
    """
    import os
    import threading

    r_fd, w_fd = os.pipe()
    saved_fd = os.dup(sys.stdin.fileno())

    def _relay() -> None:
        try:
            with open(saved_fd, "rb") as src, open(w_fd, "wb") as dst:
                for line in src:
                    if line.strip():
                        dst.write(line)
                        dst.flush()
        except Exception:
            pass

    threading.Thread(target=_relay, daemon=True).start()
    os.dup2(r_fd, sys.stdin.fileno())
    os.close(r_fd)
    sys.stdin = open(0, "r", closefd=False)


def serve(graph_path: str = "graphify-out/graph.json") -> None:
    """Start the MCP server. Requires pip install mcp."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp import types
    except ImportError as e:
        raise ImportError("mcp not installed. Run: pip install mcp") from e

    G = _load_graph(graph_path)
    communities = _communities_from_graph(G)

    server = Server("graphify")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="query_graph",
                description="Search the knowledge graph using BFS or DFS. Returns relevant nodes and edges as text context.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "Natural language question or keyword search"},
                         "mode": {"type": "string", "enum": ["bfs", "dfs", "bidirectional", "astar"], "default": "bfs",
                                  "description": "bfs=broad context, dfs=trace a specific path, bidirectional=path finding, astar=community-aware path"},
                        "depth": {"type": "integer", "default": 3, "description": "Traversal depth (1-6)"},
                        "token_budget": {"type": "integer", "default": 2000, "description": "Max output tokens"},
                        "use_cache": {"type": "boolean", "default": True, "description": "Use query result cache"},
                        "prefer": {"type": "string", "enum": ["extracted", "inferred", "all"], "default": "extracted",
                                   "description": "Edge confidence preference for traversal order"},
                        "materialize": {"type": "boolean", "default": False, "description": "Use planned BFS with confidence ordering"},
                        "approximate": {"type": "boolean", "default": False, "description": "Query a sampled subgraph (~10x faster, ~90% accuracy)"},
                        "sample_rate": {"type": "number", "default": 0.1, "description": "Fraction of graph to sample when approximate=True (0.01-1.0)"},
                    },
                    "required": ["question"],
                },
            ),
            types.Tool(
                name="get_node",
                description="Get full details for a specific node by label or ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"label": {"type": "string", "description": "Node label or ID to look up"}},
                    "required": ["label"],
                },
            ),
            types.Tool(
                name="get_neighbors",
                description="Get all direct neighbors of a node with edge details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "relation_filter": {"type": "string", "description": "Optional: filter by relation type"},
                    },
                    "required": ["label"],
                },
            ),
            types.Tool(
                name="get_community",
                description="Get all nodes in a community by community ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"community_id": {"type": "integer", "description": "Community ID (0-indexed by size)"}},
                    "required": ["community_id"],
                },
            ),
            types.Tool(
                name="god_nodes",
                description="Return the most connected nodes - the core abstractions of the knowledge graph.",
                inputSchema={"type": "object", "properties": {"top_n": {"type": "integer", "default": 10}}},
            ),
            types.Tool(
                name="graph_stats",
                description="Return summary statistics: node count, edge count, communities, confidence breakdown.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="shortest_path",
                description="Find the shortest path between two concepts in the knowledge graph.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Source concept label or keyword"},
                        "target": {"type": "string", "description": "Target concept label or keyword"},
                        "max_hops": {"type": "integer", "default": 8, "description": "Maximum hops to consider"},
                        "weighted": {"type": "boolean", "default": False, "description": "Use Dijkstra with edge weights"},
                        "mode": {"type": "string", "enum": ["default", "bidirectional"], "default": "default",
                                 "description": "default=nx shortest_path, bidirectional=simultaneous BFS from both ends"},
                    },
                    "required": ["source", "target"],
                },
            ),
        ]

    def _tool_query_graph(arguments: dict) -> str:
        question = arguments["question"]
        mode = arguments.get("mode", "bfs")
        depth = min(int(arguments.get("depth", 3)), 6)
        budget = int(arguments.get("token_budget", 2000))
        use_cache = arguments.get("use_cache", True)
        prefer = arguments.get("prefer", "extracted")
        materialize = arguments.get("materialize", False)
        approximate = arguments.get("approximate", False)
        sample_rate = float(arguments.get("sample_rate", 0.1))

        if approximate:
            cache_dir = Path("graphify-out/query_cache")
            key = cache_key(question, mode, depth, budget)
            if use_cache:
                cached = get_cached_query(cache_dir, key)
                if cached is not None:
                    return cached
            sampled_G = sample_subgraph(G, sample_rate=sample_rate, seed=42)
            terms = [t.lower() for t in question.split() if len(t) > 2]
            scored = _score_nodes(sampled_G, terms)
            if not scored:
                result = "[APPROXIMATE] No matching nodes found in sampled subgraph."
                if use_cache:
                    set_cached_query(cache_dir, key, result)
                return result
            start_nodes = [nid for _, nid in scored[:3]]
            nodes, edges = _bfs(sampled_G, start_nodes, depth)
            header = f"[APPROXIMATE] BFS depth={depth} sample={sample_rate} | {len(nodes)} nodes found\n\n"
            result = header + _subgraph_to_text(sampled_G, nodes, edges, budget)
            if use_cache:
                set_cached_query(cache_dir, key, result)
            return result

        if use_cache:
            cache_dir = Path("graphify-out/query_cache")
            key = cache_key(question, mode, depth, budget)
            cached = get_cached_query(cache_dir, key)
            if cached is not None:
                return cached

        terms = [t.lower() for t in question.split() if len(t) > 2]
        scored = _score_nodes(G, terms)
        if not scored:
            result = "No matching nodes found."
            if use_cache:
                set_cached_query(Path("graphify-out/query_cache"),
                                 cache_key(question, mode, depth, budget), result)
            return result

        candidate_ids = [nid for _, nid in scored[:5]]
        start_node = select_start_nodes_by_degree(G, candidate_ids)
        start_nodes = [start_node]

        if mode == "bidirectional" and len(candidate_ids) >= 2:
            path, length = _bidirectional_shortest_path(G, candidate_ids[0], candidate_ids[1])
            if not path:
                result = f"No bidirectional path found between '{G.nodes[candidate_ids[0]].get('label', candidate_ids[0])}' and '{G.nodes[candidate_ids[1]].get('label', candidate_ids[1])}'."
                if use_cache:
                    set_cached_query(Path("graphify-out/query_cache"),
                                     cache_key(question, mode, depth, budget), result)
                return result
            nodes = set(path)
            edges = [(path[i], path[i + 1]) for i in range(len(path) - 1)]
            header = f"Bidirectional path ({int(length)} hops):\n"
            result = header + _subgraph_to_text(G, nodes, edges, budget)
            if use_cache:
                set_cached_query(Path("graphify-out/query_cache"),
                                 cache_key(question, mode, depth, budget), result)
            return result

        if mode == "astar" and len(candidate_ids) >= 2:
            path = _astar_search(G, candidate_ids[0], candidate_ids[1], communities)
            if not path:
                result = f"No A* path found between '{G.nodes[candidate_ids[0]].get('label', candidate_ids[0])}' and '{G.nodes[candidate_ids[1]].get('label', candidate_ids[1])}'."
                if use_cache:
                    set_cached_query(Path("graphify-out/query_cache"),
                                     cache_key(question, mode, depth, budget), result)
                return result
            nodes = set(path)
            edges = [(path[i], path[i + 1]) for i in range(len(path) - 1)]
            header = f"A* path ({len(path) - 1} hops):\n"
            result = header + _subgraph_to_text(G, nodes, edges, budget)
            if use_cache:
                set_cached_query(Path("graphify-out/query_cache"),
                                 cache_key(question, mode, depth, budget), result)
            return result

        if mode == "dfs":
            nodes, edges = _dfs(G, start_nodes, depth)
        elif materialize and mode == "bfs":
            nodes, edges = _bfs_planned(G, start_node, depth, prefer)
        elif prefer != "extracted" and mode == "bfs":
            nodes, edges = _bfs_planned(G, start_node, depth, prefer)
        else:
            nodes, edges = _bfs(G, start_nodes, depth)

        header = f"Traversal: {mode.upper()} depth={depth} | Start: {[G.nodes[n].get('label', n) for n in [start_node]]} | {len(nodes)} nodes found\n\n"
        result = header + _subgraph_to_text(G, nodes, edges, budget)
        if use_cache:
            set_cached_query(Path("graphify-out/query_cache"),
                             cache_key(question, mode, depth, budget), result)
        return result

    def _tool_get_node(arguments: dict) -> str:
        label = arguments["label"].lower()
        matches = [(nid, d) for nid, d in G.nodes(data=True)
                   if label in (d.get("label") or "").lower() or label == nid.lower()]
        if not matches:
            return f"No node matching '{label}' found."
        nid, d = matches[0]
        return "\n".join([
            f"Node: {d.get('label', nid)}",
            f"  ID: {nid}",
            f"  Source: {d.get('source_file', '')} {d.get('source_location', '')}",
            f"  Type: {d.get('file_type', '')}",
            f"  Community: {d.get('community', '')}",
            f"  Degree: {G.degree(nid)}",
        ])

    def _tool_get_neighbors(arguments: dict) -> str:
        label = arguments["label"].lower()
        rel_filter = arguments.get("relation_filter", "").lower()
        matches = _find_node(G, label)
        if not matches:
            return f"No node matching '{label}' found."
        nid = matches[0]
        lines = [f"Neighbors of {G.nodes[nid].get('label', nid)}:"]
        for neighbor in G.neighbors(nid):
            d = G.edges[nid, neighbor]
            rel = d.get("relation", "")
            if rel_filter and rel_filter not in rel.lower():
                continue
            lines.append(f"  --> {G.nodes[neighbor].get('label', neighbor)} [{rel}] [{d.get('confidence', '')}]")
        return "\n".join(lines)

    def _tool_get_community(arguments: dict) -> str:
        cid = int(arguments["community_id"])
        nodes = communities.get(cid, [])
        if not nodes:
            return f"Community {cid} not found."
        lines = [f"Community {cid} ({len(nodes)} nodes):"]
        for n in nodes:
            d = G.nodes[n]
            lines.append(f"  {d.get('label', n)} [{d.get('source_file', '')}]")
        return "\n".join(lines)

    def _tool_god_nodes(arguments: dict) -> str:
        from .analyze import god_nodes as _god_nodes
        nodes = _god_nodes(G, top_n=int(arguments.get("top_n", 10)))
        lines = ["God nodes (most connected):"]
        lines += [f"  {i}. {n['label']} - {n['degree']} edges" for i, n in enumerate(nodes, 1)]
        return "\n".join(lines)

    def _tool_graph_stats(_: dict) -> str:
        confs = [d.get("confidence", "EXTRACTED") for _, _, d in G.edges(data=True)]
        total = len(confs) or 1
        return (
            f"Nodes: {G.number_of_nodes()}\n"
            f"Edges: {G.number_of_edges()}\n"
            f"Communities: {len(communities)}\n"
            f"EXTRACTED: {round(confs.count('EXTRACTED')/total*100)}%\n"
            f"INFERRED: {round(confs.count('INFERRED')/total*100)}%\n"
            f"AMBIGUOUS: {round(confs.count('AMBIGUOUS')/total*100)}%\n"
        )

    def _tool_shortest_path(arguments: dict) -> str:
        src_scored = _score_nodes(G, [t.lower() for t in arguments["source"].split()])
        tgt_scored = _score_nodes(G, [t.lower() for t in arguments["target"].split()])
        if not src_scored:
            return f"No node matching source '{arguments['source']}' found."
        if not tgt_scored:
            return f"No node matching target '{arguments['target']}' found."
        src_nid, tgt_nid = src_scored[0][1], tgt_scored[0][1]
        max_hops = int(arguments.get("max_hops", 8))
        path_mode = arguments.get("mode", "default")
        weighted = arguments.get("weighted", False)

        matviews_dir = Path("graphify-out/matviews")
        if matviews_dir.exists():
            for rel_type in ("calls", "imports"):
                hop_dist = check_materialized_path(G, src_nid, tgt_nid, rel_type, matviews_dir)
                if hop_dist is not None and hop_dist <= max_hops:
                    return f"Materialized path ({rel_type}, {hop_dist} hops): {G.nodes[src_nid].get('label', src_nid)} --{rel_type}--> {G.nodes[tgt_nid].get('label', tgt_nid)}"

        if weighted:
            path_nodes, total_weight = _dijkstra_shortest_path(G, src_nid, tgt_nid)
            if not path_nodes:
                return f"No weighted path found between '{G.nodes[src_nid].get('label', src_nid)}' and '{G.nodes[tgt_nid].get('label', tgt_nid)}'."
            hops = len(path_nodes) - 1
            if hops > max_hops:
                return f"Path exceeds max_hops={max_hops} ({hops} hops found)."
            segments = []
            for i in range(len(path_nodes) - 1):
                u, v = path_nodes[i], path_nodes[i + 1]
                edata = G.edges[u, v]
                rel = edata.get("relation", "")
                w = edata.get("weight", 1.0)
                if i == 0:
                    segments.append(G.nodes[u].get("label", u))
                segments.append(f"--{rel}[w={w}]--> {G.nodes[v].get('label', v)}")
            return f"Weighted shortest path ({hops} hops, total_weight={round(total_weight, 3)}):\n  " + " ".join(segments)

        if path_mode == "bidirectional":
            path_nodes, length = _bidirectional_shortest_path(G, src_nid, tgt_nid, max_hops)
            if not path_nodes:
                return f"No bidirectional path found between '{G.nodes[src_nid].get('label', src_nid)}' and '{G.nodes[tgt_nid].get('label', tgt_nid)}'."
            hops = len(path_nodes) - 1
            segments = []
            for i in range(len(path_nodes) - 1):
                u, v = path_nodes[i], path_nodes[i + 1]
                edata = G.edges[u, v]
                rel = edata.get("relation", "")
                conf = edata.get("confidence", "")
                conf_str = f" [{conf}]" if conf else ""
                if i == 0:
                    segments.append(G.nodes[u].get("label", u))
                segments.append(f"--{rel}{conf_str}--> {G.nodes[v].get('label', v)}")
            return f"Bidirectional shortest path ({hops} hops):\n  " + " ".join(segments)

        try:
            path_nodes = nx.shortest_path(G, src_nid, tgt_nid)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return f"No path found between '{G.nodes[src_nid].get('label', src_nid)}' and '{G.nodes[tgt_nid].get('label', tgt_nid)}'."
        hops = len(path_nodes) - 1
        if hops > max_hops:
            return f"Path exceeds max_hops={max_hops} ({hops} hops found)."
        segments = []
        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            edata = G.edges[u, v]
            rel = edata.get("relation", "")
            conf = edata.get("confidence", "")
            conf_str = f" [{conf}]" if conf else ""
            if i == 0:
                segments.append(G.nodes[u].get("label", u))
            segments.append(f"--{rel}{conf_str}--> {G.nodes[v].get('label', v)}")
        return f"Shortest path ({hops} hops):\n  " + " ".join(segments)

    _handlers = {
        "query_graph": _tool_query_graph,
        "get_node": _tool_get_node,
        "get_neighbors": _tool_get_neighbors,
        "get_community": _tool_get_community,
        "god_nodes": _tool_god_nodes,
        "graph_stats": _tool_graph_stats,
        "shortest_path": _tool_shortest_path,
    }

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        handler = _handlers.get(name)
        if not handler:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
        try:
            return [types.TextContent(type="text", text=handler(arguments))]
        except Exception as exc:
            return [types.TextContent(type="text", text=f"Error executing {name}: {exc}")]

    import asyncio

    async def main() -> None:
        async with stdio_server() as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    _filter_blank_stdin()
    asyncio.run(main())


if __name__ == "__main__":
    graph_path = sys.argv[1] if len(sys.argv) > 1 else "graphify-out/graph.json"
    serve(graph_path)
