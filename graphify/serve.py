# MCP stdio server - exposes graph query tools to Claude and other agents
from __future__ import annotations
import json
import sys
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph
from graphify.security import sanitize_label
from graphify.build import edge_data


def _load_graph(graph_path: str) -> nx.Graph:
    try:
        resolved = Path(graph_path).resolve()
        if resolved.suffix != ".json":
            raise ValueError(f"Graph path must be a .json file, got: {graph_path!r}")
        if not resolved.exists():
            raise FileNotFoundError(f"Graph file not found: {resolved}")
        safe = resolved
        data = json.loads(safe.read_text(encoding="utf-8"))
        if "links" not in data and "edges" in data:
            data = dict(data, links=data["edges"])
        data = {**data, "directed": True}
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


_EXACT_MATCH_BONUS = 1000.0
_PREFIX_MATCH_BONUS = 100.0
_SUBSTRING_MATCH_BONUS = 1.0
_SOURCE_MATCH_BONUS = 0.5


def _score_nodes(G: nx.Graph, terms: list[str]) -> list[tuple[float, str]]:
    scored = []
    norm_terms = [_strip_diacritics(t).lower() for t in terms]
    for nid, data in G.nodes(data=True):
        norm_label = data.get("norm_label") or _strip_diacritics(data.get("label") or "").lower()
        bare_label = norm_label.rstrip("()")
        source = (data.get("source_file") or "").lower()
        score = 0.0
        for t in norm_terms:
            # Three-tier precedence: exact > prefix > substring (take the
            # strongest tier per term so a single term cannot double-count).
            if t == norm_label or t == bare_label:
                score += _EXACT_MATCH_BONUS
            elif norm_label.startswith(t) or bare_label.startswith(t):
                score += _PREFIX_MATCH_BONUS
            elif t in norm_label:
                score += _SUBSTRING_MATCH_BONUS
            if t in source:
                score += _SOURCE_MATCH_BONUS
        if score > 0:
            scored.append((score, nid))
    return sorted(scored, reverse=True)


_CONTEXT_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("call", ("call", "calls", "called", "invoke", "invokes", "invoked")),
    ("import", ("import", "imports", "imported", "module", "modules")),
    ("field", ("field", "fields", "member", "members", "property", "properties")),
    ("parameter_type", ("parameter", "parameters", "param", "params", "argument", "arguments")),
    ("return_type", ("return", "returns", "returned")),
    ("generic_arg", ("generic", "generics", "template", "templates")),
)


def _normalize_context_filters(filters: list[str] | None) -> list[str]:
    if not filters:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in filters:
        key = _strip_diacritics(str(value)).strip().lower()
        if key and key not in seen:
            seen.add(key)
            normalized.append(key)
    return normalized


def _infer_context_filters(question: str) -> list[str]:
    lowered = {
        _strip_diacritics(token).lower()
        for token in question.replace("?", " ").replace(",", " ").split()
    }
    inferred: list[str] = []
    for context, hints in _CONTEXT_HINTS:
        if any(hint in lowered for hint in hints):
            inferred.append(context)
    return inferred


def _resolve_context_filters(question: str, explicit_filters: list[str] | None = None) -> tuple[list[str], str | None]:
    normalized = _normalize_context_filters(explicit_filters)
    if normalized:
        return normalized, "explicit"
    inferred = _infer_context_filters(question)
    if inferred:
        return inferred, "heuristic"
    return [], None


def _filter_graph_by_context(G: nx.Graph, context_filters: list[str] | None) -> nx.Graph:
    filters = set(_normalize_context_filters(context_filters))
    if not filters:
        return G
    H = G.__class__()
    H.add_nodes_from(G.nodes(data=True))
    if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)):
        for u, v, key, data in G.edges(keys=True, data=True):
            if data.get("context") in filters:
                H.add_edge(u, v, key=key, **data)
    else:
        for u, v, data in G.edges(data=True):
            if data.get("context") in filters:
                H.add_edge(u, v, **data)
    return H


def _bfs(G: nx.Graph, start_nodes: list[str], depth: int) -> tuple[set[str], list[tuple]]:
    # Compute hub threshold: nodes above this degree are not expanded as transit.
    # p99 of degree distribution, floored at 50 to avoid over-blocking small graphs.
    degrees = [G.degree(n) for n in G.nodes()]
    if degrees:
        degrees_sorted = sorted(degrees)
        p99_idx = int(len(degrees_sorted) * 0.99)
        hub_threshold = max(50, degrees_sorted[p99_idx])
    else:
        hub_threshold = 50
    seed_set = set(start_nodes)
    visited: set[str] = set(start_nodes)
    frontier = set(start_nodes)
    edges_seen: list[tuple] = []
    for _ in range(depth):
        next_frontier: set[str] = set()
        for n in frontier:
            # Don't expand through high-degree hubs (except seeds - a hub that
            # is the starting node should still be explored).
            if n not in seed_set and G.degree(n) >= hub_threshold:
                continue
            for neighbor in G.neighbors(n):
                if neighbor not in visited:
                    next_frontier.add(neighbor)
                    edges_seen.append((n, neighbor))
        visited.update(next_frontier)
        frontier = next_frontier
    return visited, edges_seen


def _dfs(G: nx.Graph, start_nodes: list[str], depth: int) -> tuple[set[str], list[tuple]]:
    degrees = [G.degree(n) for n in G.nodes()]
    if degrees:
        degrees_sorted = sorted(degrees)
        p99_idx = int(len(degrees_sorted) * 0.99)
        hub_threshold = max(50, degrees_sorted[p99_idx])
    else:
        hub_threshold = 50
    seed_set = set(start_nodes)
    visited: set[str] = set()
    edges_seen: list[tuple] = []
    stack = [(n, 0) for n in reversed(start_nodes)]
    while stack:
        node, d = stack.pop()
        if node in visited or d > depth:
            continue
        visited.add(node)
        if node not in seed_set and G.degree(node) >= hub_threshold:
            continue
        for neighbor in G.neighbors(node):
            if neighbor not in visited:
                stack.append((neighbor, d + 1))
                edges_seen.append((node, neighbor))
    return visited, edges_seen


def _subgraph_to_text(G: nx.Graph, nodes: set[str], edges: list[tuple], token_budget: int = 2000, *, seeds: list[str] | None = None) -> str:
    """Render subgraph as text, cutting at token_budget (approx 3 chars/token).

    seeds: exact-match nodes rendered first before the degree-sorted expansion,
    so the queried symbol always appears at the top of the output.
    """
    char_budget = token_budget * 3
    lines = []
    seed_set = set(seeds or [])
    ordered = [n for n in (seeds or []) if n in nodes] + \
              sorted(nodes - seed_set, key=lambda n: G.degree(n), reverse=True)
    for nid in ordered:
        d = G.nodes[nid]
        # Every LLM-derived field passes through sanitize_label before being
        # concatenated into MCP tool output (F-010): an attacker who controls a
        # corpus document can otherwise inject ANSI escapes, fake graphify-out
        # log lines, or prompt-injection markup into the model's context via
        # source_file / source_location / community.
        line = (
            f"NODE {sanitize_label(d.get('label', nid))} "
            f"[src={sanitize_label(str(d.get('source_file', '')))} "
            f"loc={sanitize_label(str(d.get('source_location', '')))} "
            f"community={sanitize_label(str(d.get('community', '')))}]"
        )
        lines.append(line)
    for u, v in edges:
        if u in nodes and v in nodes:
            raw = G[u][v]
            d = next(iter(raw.values()), {}) if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)) else raw
            context = d.get("context")
            context_suffix = f" context={sanitize_label(str(context))}" if context else ""
            line = (
                f"EDGE {sanitize_label(G.nodes[u].get('label', u))} "
                f"--{sanitize_label(str(d.get('relation', '')))} "
                f"[{sanitize_label(str(d.get('confidence', '')))}{context_suffix}]--> "
                f"{sanitize_label(G.nodes[v].get('label', v))}"
            )
            lines.append(line)
    output = "\n".join(lines)
    if len(output) > char_budget:
        output = output[:char_budget] + f"\n... (truncated to ~{token_budget} token budget)"
    return output


def _query_graph_text(
    G: nx.Graph,
    question: str,
    *,
    mode: str = "bfs",
    depth: int = 3,
    token_budget: int = 2000,
    context_filters: list[str] | None = None,
) -> str:
    terms = [t.lower() for t in question.split() if len(t) > 2]
    scored = _score_nodes(G, terms)
    start_nodes = [nid for _, nid in scored[:3]]
    if not start_nodes:
        return "No matching nodes found."
    resolved_filters, filter_source = _resolve_context_filters(question, context_filters)
    traversal_graph = _filter_graph_by_context(G, resolved_filters)
    nodes, edges = _dfs(traversal_graph, start_nodes, depth) if mode == "dfs" else _bfs(traversal_graph, start_nodes, depth)
    header_parts = [
        f"Traversal: {mode.upper()} depth={depth}",
        f"Start: {[G.nodes[n].get('label', n) for n in start_nodes]}",
    ]
    if resolved_filters:
        header_parts.append(f"Context: {', '.join(resolved_filters)} ({filter_source})")
    header_parts.append(f"{len(nodes)} nodes found")
    header = " | ".join(header_parts) + "\n\n"
    return header + _subgraph_to_text(traversal_graph, nodes, edges, token_budget)


def _find_node(G: nx.Graph, label: str) -> list[str]:
    """Return node IDs whose label or ID matches the search term (diacritic-insensitive).

    Results are ordered by three-tier precedence: exact match, then prefix match,
    then substring match. Node-ID exact matches are grouped with label exact matches.
    """
    term = _strip_diacritics(label).lower()
    exact: list[str] = []
    prefix: list[str] = []
    substring: list[str] = []
    for nid, d in G.nodes(data=True):
        norm_label = d.get("norm_label") or _strip_diacritics(d.get("label") or "").lower()
        bare_label = norm_label.rstrip("()")
        nid_lower = nid.lower()
        if term == norm_label or term == bare_label or term == nid_lower:
            exact.append(nid)
        elif norm_label.startswith(term) or bare_label.startswith(term) or nid_lower.startswith(term):
            prefix.append(nid)
        elif term in norm_label:
            substring.append(nid)
    return exact + prefix + substring


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
    import threading

    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp import types
        from mcp.types import AnyUrl
    except ImportError as e:
        raise ImportError("mcp not installed. Run: pip install mcp") from e

    G = _load_graph(graph_path)
    communities = _communities_from_graph(G)

    # Hot-reload state: mtime+size key lets us detect graph.json changes without
    # polling. Initialised from the file stat at startup so the first tool call
    # never triggers a redundant reload.
    _reload_lock = threading.Lock()
    try:
        _s = Path(graph_path).stat()
        _reload_state: dict = {"mtime_ns": _s.st_mtime_ns, "size": _s.st_size}
    except FileNotFoundError:
        _reload_state = {"mtime_ns": 0, "size": -1}

    def _maybe_reload() -> None:
        nonlocal G, communities
        try:
            s = Path(graph_path).stat()
            key = (s.st_mtime_ns, s.st_size)
        except FileNotFoundError:
            return
        if key == (_reload_state["mtime_ns"], _reload_state["size"]):
            return
        with _reload_lock:
            try:
                s = Path(graph_path).stat()
                key = (s.st_mtime_ns, s.st_size)
            except FileNotFoundError:
                return
            if key == (_reload_state["mtime_ns"], _reload_state["size"]):
                return  # another thread already reloaded
            try:
                new_G = _load_graph(graph_path)
            except SystemExit:
                return  # keep serving stale graph on transient read error
            G = new_G
            communities = _communities_from_graph(new_G)
            _reload_state["mtime_ns"], _reload_state["size"] = key

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
                        "mode": {"type": "string", "enum": ["bfs", "dfs"], "default": "bfs",
                                 "description": "bfs=broad context, dfs=trace a specific path"},
                        "depth": {"type": "integer", "default": 3, "description": "Traversal depth (1-6)"},
                        "token_budget": {"type": "integer", "default": 2000, "description": "Max output tokens"},
                        "context_filter": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional explicit edge-context filter, e.g. ['call', 'field']",
                        },
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
        context_filter = arguments.get("context_filter")
        return _query_graph_text(
            G,
            question,
            mode=mode,
            depth=depth,
            token_budget=budget,
            context_filters=context_filter,
        )

    def _tool_get_node(arguments: dict) -> str:
        label = arguments["label"].lower()
        matches = [(nid, d) for nid, d in G.nodes(data=True)
                   if label in (d.get("label") or "").lower() or label == nid.lower()]
        if not matches:
            return f"No node matching '{label}' found."
        nid, d = matches[0]
        # Sanitise every LLM-derived field before concatenation (F-010).
        return "\n".join([
            f"Node: {sanitize_label(d.get('label', nid))}",
            f"  ID: {sanitize_label(nid)}",
            f"  Source: {sanitize_label(str(d.get('source_file', '')))} {sanitize_label(str(d.get('source_location', '')))}",
            f"  Type: {sanitize_label(str(d.get('file_type', '')))}",
            f"  Community: {sanitize_label(str(d.get('community', '')))}",
            f"  Degree: {G.degree(nid)}",
        ])

    def _tool_get_neighbors(arguments: dict) -> str:
        label = arguments["label"].lower()
        rel_filter = arguments.get("relation_filter", "").lower()
        matches = _find_node(G, label)
        if not matches:
            return f"No node matching '{label}' found."
        nid = matches[0]
        lines = [f"Neighbors of {sanitize_label(G.nodes[nid].get('label', nid))}:"]
        for nb in G.successors(nid):
            d = edge_data(G, nid, nb)
            rel = d.get("relation", "")
            if rel_filter and rel_filter not in rel.lower():
                continue
            lines.append(
                f"  --> {sanitize_label(G.nodes[nb].get('label', nb))} "
                f"[{sanitize_label(str(rel))}] [{sanitize_label(str(d.get('confidence', '')))}]"
            )
        for nb in G.predecessors(nid):
            d = edge_data(G, nb, nid)
            rel = d.get("relation", "")
            if rel_filter and rel_filter not in rel.lower():
                continue
            lines.append(
                f"  <-- {sanitize_label(G.nodes[nb].get('label', nb))} "
                f"[{sanitize_label(str(rel))}] [{sanitize_label(str(d.get('confidence', '')))}]"
            )
        return "\n".join(lines)

    def _tool_get_community(arguments: dict) -> str:
        cid = int(arguments["community_id"])
        nodes = communities.get(cid, [])
        if not nodes:
            return f"Community {cid} not found."
        lines = [f"Community {cid} ({len(nodes)} nodes):"]
        for n in nodes:
            d = G.nodes[n]
            # Sanitise label and source_file (F-010).
            lines.append(
                f"  {sanitize_label(d.get('label', n))} "
                f"[{sanitize_label(str(d.get('source_file', '')))}]"
            )
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
        # Ambiguity guard: when both queries resolve to the same node, the
        # shortest path is trivially zero hops, which is almost never what the
        # caller wanted (see bug #828).
        if src_nid == tgt_nid:
            return (
                f"'{arguments['source']}' and '{arguments['target']}' both resolved to "
                f"the same node '{src_nid}'. Use a more specific label or the exact node ID."
            )
        warnings: list[str] = []
        for name, scored in (("source", src_scored), ("target", tgt_scored)):
            if len(scored) >= 2:
                top, runner = scored[0][0], scored[1][0]
                if top > 0 and (top - runner) / top < 0.10:
                    warnings.append(
                        f"warning: {name} match was ambiguous "
                        f"(top score {top:g}, runner-up {runner:g})"
                    )
        max_hops = int(arguments.get("max_hops", 8))
        try:
            # Use undirected view for path-finding (works regardless of query src/tgt order)
            path_nodes = nx.shortest_path(G.to_undirected(as_view=True), src_nid, tgt_nid)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return f"No path found between '{G.nodes[src_nid].get('label', src_nid)}' and '{G.nodes[tgt_nid].get('label', tgt_nid)}'."
        hops = len(path_nodes) - 1
        if hops > max_hops:
            return f"Path exceeds max_hops={max_hops} ({hops} hops found)."
        segments = []
        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            if G.has_edge(u, v):
                edata = edge_data(G, u, v)
                forward = True
            else:
                edata = edge_data(G, v, u)
                forward = False
            rel = edata.get("relation", "")
            conf = edata.get("confidence", "")
            conf_str = f" [{conf}]" if conf else ""
            if i == 0:
                segments.append(G.nodes[u].get("label", u))
            if forward:
                segments.append(f"--{rel}{conf_str}--> {G.nodes[v].get('label', v)}")
            else:
                segments.append(f"<--{rel}{conf_str}-- {G.nodes[v].get('label', v)}")
        prefix = ("\n".join(warnings) + "\n") if warnings else ""
        return prefix + f"Shortest path ({hops} hops):\n  " + " ".join(segments)

    _handlers = {
        "query_graph": _tool_query_graph,
        "get_node": _tool_get_node,
        "get_neighbors": _tool_get_neighbors,
        "get_community": _tool_get_community,
        "god_nodes": _tool_god_nodes,
        "graph_stats": _tool_graph_stats,
        "shortest_path": _tool_shortest_path,
    }

    def _load_community_labels() -> dict[int, str]:
        labels_path = Path(graph_path).parent / ".graphify_labels.json"
        if labels_path.exists():
            try:
                return {int(k): v for k, v in json.loads(labels_path.read_text(encoding="utf-8")).items()}
            except Exception:
                pass
        return {cid: f"Community {cid}" for cid in communities}

    @server.list_resources()
    async def list_resources() -> list[types.Resource]:
        return [
            types.Resource(uri=AnyUrl("graphify://report"), name="Graph Report", description="Full GRAPH_REPORT.md", mimeType="text/markdown"),
            types.Resource(uri=AnyUrl("graphify://stats"), name="Graph Stats", description="Node/edge/community counts and confidence breakdown", mimeType="text/plain"),
            types.Resource(uri=AnyUrl("graphify://god-nodes"), name="God Nodes", description="Top 10 most-connected nodes", mimeType="text/plain"),
            types.Resource(uri=AnyUrl("graphify://surprises"), name="Surprising Connections", description="Cross-community surprising connections", mimeType="text/plain"),
            types.Resource(uri=AnyUrl("graphify://audit"), name="Confidence Audit", description="EXTRACTED/INFERRED/AMBIGUOUS edge breakdown", mimeType="text/plain"),
            types.Resource(uri=AnyUrl("graphify://questions"), name="Suggested Questions", description="Suggested questions for this codebase", mimeType="text/plain"),
        ]

    @server.read_resource()
    async def read_resource(uri: AnyUrl) -> str:
        _maybe_reload()
        uri_str = str(uri)
        if uri_str == "graphify://report":
            report_path = Path(graph_path).parent / "GRAPH_REPORT.md"
            if report_path.exists():
                return report_path.read_text(encoding="utf-8")
            return "GRAPH_REPORT.md not found. Run graphify extract first."
        if uri_str == "graphify://stats":
            return _tool_graph_stats({})
        if uri_str == "graphify://god-nodes":
            return _tool_god_nodes({"top_n": 10})
        if uri_str == "graphify://surprises":
            try:
                from graphify.analyze import surprising_connections
                surprises = surprising_connections(G, communities, top_n=10)
                if not surprises:
                    return "No surprising connections found."
                lines = ["Surprising cross-community connections:"]
                for s in surprises:
                    lines.append(f"  {s.get('source', '')} <-> {s.get('target', '')} [{s.get('relation', '')}]")
                return "\n".join(lines)
            except Exception as exc:
                return f"Could not compute surprising connections: {exc}"
        if uri_str == "graphify://audit":
            confs = [d.get("confidence", "EXTRACTED") for _, _, d in G.edges(data=True)]
            total = len(confs) or 1
            return (
                f"Total edges: {total}\n"
                f"EXTRACTED: {confs.count('EXTRACTED')} ({round(confs.count('EXTRACTED')/total*100)}%)\n"
                f"INFERRED: {confs.count('INFERRED')} ({round(confs.count('INFERRED')/total*100)}%)\n"
                f"AMBIGUOUS: {confs.count('AMBIGUOUS')} ({round(confs.count('AMBIGUOUS')/total*100)}%)\n"
            )
        if uri_str == "graphify://questions":
            try:
                from graphify.analyze import suggest_questions
                community_labels = _load_community_labels()
                questions = suggest_questions(G, communities, community_labels, top_n=10)
                if not questions:
                    return "No suggested questions available."
                lines = ["Suggested questions:"]
                for q in questions:
                    if isinstance(q, dict):
                        lines.append(f"  - {q.get('question', '')}")
                    else:
                        lines.append(f"  - {q}")
                return "\n".join(lines)
            except Exception as exc:
                return f"Could not generate questions: {exc}"
        raise ValueError(f"Unknown resource: {uri_str}")

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        _maybe_reload()
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
