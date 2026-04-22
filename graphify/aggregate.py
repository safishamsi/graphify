"""Aggregation strategies for hierarchical knowledge graphs.

Each strategy takes a parent-layer graph and produces a summary sub-graph
that can be merged into a child layer via :func:`graphify.build.merge_graphs`.

Available strategies:

- ``none`` — returns an empty graph (no-op).
- ``topk_filter`` — select top-K nodes by degree with edge confidence filtering.
- ``community_collapse`` — collapse each community into abstract concept nodes.
- ``llm_summary`` — LLM-powered semantic summarization.
- ``composite`` — community_collapse → llm_summary pipeline.
"""
from __future__ import annotations

import json
import sys
from collections import Counter

import networkx as nx

from .analyze import _is_file_node, god_nodes, surprising_connections
from .build import build_from_json
from .cluster import cluster


def aggregate(
    G_parent: nx.Graph,
    strategy: str,
    params: dict | None = None,
) -> nx.Graph:
    """Produce a summary graph from *G_parent* using the given *strategy*.

    Parameters
    ----------
    G_parent:
        The graph of the parent layer to summarise.
    strategy:
        Name of the aggregation strategy.
    params:
        Optional parameters forwarded to the strategy implementation.

    Returns
    -------
    nx.Graph
        The summary (overlay) graph.

    Raises
    ------
    ValueError
        If *strategy* is not a recognised strategy name.
    """
    params = params or {}
    dispatchers = {
        "none": _strategy_none,
        "topk_filter": _strategy_topk_filter,
        "community_collapse": _strategy_community_collapse,
        "llm_summary": _strategy_llm_summary,
        "composite": _strategy_composite,
    }
    handler = dispatchers.get(strategy)
    if handler is None:
        raise ValueError(
            f"Unknown aggregation strategy: '{strategy}'. "
            f"Available strategies: {', '.join(sorted(dispatchers))}"
        )
    return handler(G_parent, params)


def _strategy_none(G_parent: nx.Graph, params: dict) -> nx.Graph:
    return G_parent.__class__()


def _topk_filter(G_parent: nx.Graph, params: dict) -> nx.Graph:
    """Select top-K nodes by degree, excluding file-level hub nodes."""
    k = params.get("top_k_nodes", 30)
    min_confidence = params.get("min_confidence")

    if G_parent.number_of_nodes() == 0:
        return G_parent.__class__()

    degree = dict(G_parent.degree())
    sorted_nodes = sorted(degree.items(), key=lambda x: x[1], reverse=True)

    selected_ids: list[str] = []
    for node_id, _ in sorted_nodes:
        if _is_file_node(G_parent, node_id):
            continue
        selected_ids.append(node_id)
        if len(selected_ids) >= k:
            break

    if not selected_ids:
        return G_parent.__class__()

    result = G_parent.__class__()
    for nid in selected_ids:
        result.add_node(nid, **G_parent.nodes[nid])

    confidence_rank = {"EXTRACTED": 3, "INFERRED": 2, "AMBIGUOUS": 1}
    min_rank = confidence_rank.get(min_confidence, 0) if min_confidence else 0

    for u, v, data in G_parent.edges(data=True):
        if u in selected_ids and v in selected_ids:
            if min_confidence:
                edge_conf = data.get("confidence", "EXTRACTED")
                edge_rank = confidence_rank.get(edge_conf, 0)
                if edge_rank < min_rank:
                    continue
            result.add_edge(u, v, **data)

    return result


def _strategy_topk_filter(G_parent: nx.Graph, params: dict) -> nx.Graph:
    return _topk_filter(G_parent, params)


def _community_collapse(G_parent: nx.Graph, params: dict) -> nx.Graph:
    """Collapse each community into abstract concept nodes."""
    nodes_per = params.get("nodes_per_community", 3)
    keep_bridges = params.get("keep_bridge_edges", True)

    if G_parent.number_of_nodes() == 0:
        return G_parent.__class__()

    communities = cluster(G_parent)
    if not communities:
        return G_parent.__class__()

    node_to_comm: dict[str, int] = {}
    for cid, nodes in communities.items():
        for n in nodes:
            node_to_comm[n] = cid

    comm_labels = {cid: f"Community {cid}" for cid in communities}

    result = G_parent.__class__()
    comm_representatives: dict[int, list[str]] = {}

    for cid, nodes in communities.items():
        if len(nodes) <= nodes_per:
            for nid in nodes:
                attrs = dict(G_parent.nodes[nid]) if nid in G_parent else {"label": nid}
                attrs["_community_id"] = cid
                result.add_node(nid, **attrs)
            comm_representatives[cid] = list(nodes)
        else:
            comm_degree = {n: G_parent.degree(n) for n in nodes if n in G_parent}
            top_nodes = sorted(comm_degree, key=comm_degree.get, reverse=True)[:nodes_per]
            label = comm_labels.get(cid, f"Community {cid}")
            reps: list[str] = []
            for idx, nid in enumerate(top_nodes, 1):
                collapsed_id = f"{label} [{idx}/{nodes_per}]"
                attrs = {
                    "label": collapsed_id,
                    "_collapsed": True,
                    "_community_id": cid,
                    "_original_node": nid,
                }
                result.add_node(collapsed_id, **attrs)
                reps.append(collapsed_id)
            comm_representatives[cid] = reps

    if keep_bridges:
        for u, v, data in G_parent.edges(data=True):
            u_comm = node_to_comm.get(u)
            v_comm = node_to_comm.get(v)
            if u_comm is None or v_comm is None or u_comm == v_comm:
                continue
            u_reps = comm_representatives.get(u_comm, [])
            v_reps = comm_representatives.get(v_comm, [])
            if u_reps and v_reps:
                result.add_edge(u_reps[0], v_reps[0], **data)

    return result


def _strategy_community_collapse(G_parent: nx.Graph, params: dict) -> nx.Graph:
    return _community_collapse(G_parent, params)


def _llm_summarize(G_parent: nx.Graph, params: dict) -> nx.Graph:
    """LLM-powered semantic summarization with fallback to topk_filter."""
    max_nodes = params.get("max_summary_nodes", 30)
    max_edges = params.get("max_summary_edges", 60)
    model = params.get("model", "auto")

    if G_parent.number_of_nodes() == 0:
        return G_parent.__class__()

    gods = god_nodes(G_parent)
    communities = cluster(G_parent)
    surprises = surprising_connections(G_parent, communities)

    comm_summary_lines = []
    for cid, nodes in communities.items():
        labels = [G_parent.nodes[n].get("label", n) for n in nodes if n in G_parent]
        comm_summary_lines.append(f"  Community {cid}: {', '.join(labels[:10])}")

    god_lines = [f"  {g['label']} (degree {g.get('degree', g.get('edges', '?'))})" for g in gods[:15]]
    surprise_lines = [
        f"  {s.get('source', '?')} --{s.get('relation', '?')}--> {s.get('target', '?')}"
        for s in surprises[:10]
    ]

    prompt = f"""Summarize this knowledge graph into a compressed representation.

God nodes (most connected):
{chr(10).join(god_lines) if god_lines else '  (none)'}

Communities:
{chr(10).join(comm_summary_lines) if comm_summary_lines else '  (none)'}

Surprising connections:
{chr(10).join(surprise_lines) if surprise_lines else '  (none)'}

Return ONLY valid JSON in this exact format (no markdown, no explanation):
{{"nodes": [{{"id": "node_id", "label": "Node Label"}}], "edges": [{{"source": "node_id", "target": "node_id", "relation": "relationship"}}]}}

Constraints:
- At most {max_nodes} nodes
- At most {max_edges} edges
- Use descriptive, concise labels
- Focus on architectural abstractions, not implementation details"""

    llm_result = _call_llm(prompt, model)

    if llm_result is not None:
        try:
            parsed = json.loads(llm_result)
            nodes = parsed.get("nodes", [])[:max_nodes]
            edges = parsed.get("edges", [])[:max_edges]
            extraction = {"nodes": nodes, "edges": edges}
            return build_from_json(extraction)
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    print(
        "[graphify] LLM summarization failed, falling back to topk_filter",
        file=sys.stderr,
    )
    return _topk_filter(G_parent, {"top_k_nodes": 30})


def _call_llm(prompt: str, model: str = "auto") -> str | None:
    """Call an LLM with the given prompt. Returns response text or None on failure."""
    try:
        import openai

        client = openai.OpenAI()
        effective_model = model if model != "auto" else "gpt-4o-mini"
        response = client.chat.completions.create(
            model=effective_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=4096,
        )
        return response.choices[0].message.content
    except ImportError:
        pass
    except Exception as exc:
        print(f"[graphify] LLM call failed: {exc}", file=sys.stderr)

    try:
        import anthropic

        client = anthropic.Anthropic()
        effective_model = model if model != "auto" else "claude-3-5-haiku-latest"
        response = client.messages.create(
            model=effective_model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except ImportError:
        pass
    except Exception as exc:
        print(f"[graphify] Anthropic call failed: {exc}", file=sys.stderr)

    return None


def _strategy_llm_summary(G_parent: nx.Graph, params: dict) -> nx.Graph:
    return _llm_summarize(G_parent, params)


def _composite_aggregate(G_parent: nx.Graph, params: dict) -> nx.Graph:
    """Pipeline: community_collapse → llm_summary with fallback."""
    cc_params = {
        "nodes_per_community": params.get("nodes_per_community", 3),
        "keep_bridge_edges": params.get("keep_bridge_edges", True),
    }
    llm_params = {
        "max_summary_nodes": params.get("max_summary_nodes", 30),
        "max_summary_edges": params.get("max_summary_edges", 60),
        "model": params.get("model", "auto"),
    }

    collapsed = _community_collapse(G_parent, cc_params)

    if collapsed.number_of_nodes() == 0:
        return collapsed

    llm_result = _llm_summarize(collapsed, llm_params)

    if llm_result.number_of_nodes() > 0:
        return llm_result

    print(
        "[graphify] Composite LLM step failed, returning community_collapse result",
        file=sys.stderr,
    )
    return collapsed


def _strategy_composite(G_parent: nx.Graph, params: dict) -> nx.Graph:
    return _composite_aggregate(G_parent, params)
