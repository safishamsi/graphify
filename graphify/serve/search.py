from __future__ import annotations
import json
import sys
import math
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

from graphify.security import sanitize_label, check_graph_file_size_cap
from graphify.serve.core import _EXACT_MATCH_BONUS, _CONTEXT_HINTS, _PREFIX_MATCH_BONUS, _SUBSTRING_MATCH_BONUS, _SOURCE_MATCH_BONUS, _CONTEXT_FILTER_ALIASES

def _load_graph(graph_path: str) -> nx.Graph:
    try:
        resolved = Path(graph_path).resolve()
        if resolved.suffix != ".json":
            raise ValueError(f"Graph path must be a .json file, got: {graph_path!r}")
        if not resolved.exists():
            raise FileNotFoundError(f"Graph file not found: {resolved}")
        check_graph_file_size_cap(resolved)
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

def _query_terms(question: str) -> list[str]:
    """Split a query into searchable terms, filtering only short English terms."""
    terms: list[str] = []
    for raw in question.split():
        term = raw.lower().strip()
        if not term:
            continue
        is_english_only = all("a" <= ch <= "z" for ch in term)
        if not is_english_only or len(term) > 2:
            terms.append(term)
    return terms

def _compute_idf(G: nx.Graph, terms: list[str]) -> dict[str, float]:
    """IDF weights for query terms, cached in G.graph['_idf_cache'].

    Common terms like 'error' or 'exception' that match hundreds of nodes get
    low weights; rare identifiers like 'FooBarService' get high weights.
    Cache is stored on the graph object itself so it auto-invalidates when
    _maybe_reload() replaces G with a new object.
    """
    cache: dict[str, float] = G.graph.setdefault("_idf_cache", {})
    N = G.number_of_nodes() or 1
    uncached = [t for t in terms if t not in cache]
    if uncached:
        df: dict[str, int] = {t: 0 for t in uncached}
        for _, data in G.nodes(data=True):
            norm_label = (
                data.get("norm_label") or _strip_diacritics(data.get("label") or "")
            ).lower()
            for t in uncached:
                if t in norm_label:
                    df[t] += 1
        for t in uncached:
            cache[t] = math.log(1 + N / (1 + df[t]))
    return {t: cache.get(t, math.log(1 + N)) for t in terms}

def _score_nodes(G: nx.Graph, terms: list[str]) -> list[tuple[float, str]]:
    scored = []
    norm_terms = [_strip_diacritics(t).lower() for t in terms]
    idf = _compute_idf(G, norm_terms)
    for nid, data in G.nodes(data=True):
        norm_label = data.get("norm_label") or _strip_diacritics(data.get("label") or "").lower()
        bare_label = norm_label.rstrip("()")
        source = (data.get("source_file") or "").lower()
        score = 0.0
        for t in norm_terms:
            w = idf.get(t, 1.0)
            # Three-tier precedence: exact > prefix > substring (take the
            # strongest tier per term so a single term cannot double-count).
            if t == norm_label or t == bare_label:
                score += _EXACT_MATCH_BONUS * w
            elif norm_label.startswith(t) or bare_label.startswith(t):
                score += _PREFIX_MATCH_BONUS * w
            elif t in norm_label:
                score += _SUBSTRING_MATCH_BONUS * w
            if t in source:
                score += _SOURCE_MATCH_BONUS * w
        if score > 0:
            scored.append((score, nid))
    return sorted(scored, reverse=True)

def _pick_seeds(scored: list[tuple[float, str]], max_k: int = 3, gap_ratio: float = 0.2) -> list[str]:
    """Select BFS seed nodes, stopping when score drops too far below the top.

    Prevents high-frequency noise terms (error, exception) from stealing seed
    slots from a dominant identifier match. When FooBarService scores 1000 and
    error nodes score 1.0, only FooBarService is seeded — the score gap is 99.9%
    which is well above the 20% threshold that would allow additional seeds.
    """
    if not scored:
        return []
    top_score = scored[0][0]
    seeds = []
    for score, nid in scored[:max_k]:
        if seeds and score < top_score * gap_ratio:
            break
        seeds.append(nid)
    return seeds

def _normalize_context_filters(filters: list[str] | None) -> list[str]:
    if not filters:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in filters:
        key = _strip_diacritics(str(value)).strip().lower()
        if not key:
            continue
        key = _CONTEXT_FILTER_ALIASES.get(key, key)
        if key not in seen:
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
        cut_at = output[:char_budget].rfind("\n")
        cut_at = cut_at if cut_at > 0 else char_budget
        total_nodes = sum(1 for l in lines if l.startswith("NODE "))
        shown_nodes = output[:cut_at].count("\nNODE ") + (1 if output.startswith("NODE ") else 0)
        cut_count = total_nodes - shown_nodes
        output = (
            output[:cut_at]
            + f"\n... (truncated — {cut_count} more nodes cut by ~{token_budget}-token budget."
            f" Narrow with context_filter=['call'] or use get_node for a specific symbol)"
        )
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
    terms = _query_terms(question)
    scored = _score_nodes(G, terms)
    start_nodes = _pick_seeds(scored)
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
