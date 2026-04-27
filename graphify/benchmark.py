"""Token-reduction benchmark - measures how much context graphify saves vs naive full-corpus approach."""
from __future__ import annotations
import json
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph


_CHARS_PER_TOKEN = 4  # standard approximation


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _query_subgraph_tokens(G: nx.Graph, question: str, depth: int = 3) -> int:
    """Run BFS from best-matching nodes and return estimated tokens in the subgraph context."""
    terms = [t.lower() for t in question.split() if len(t) > 2]
    scored = []
    for nid, data in G.nodes(data=True):
        label = data.get("label", "").lower()
        score = sum(1 for t in terms if t in label)
        if score > 0:
            scored.append((score, nid))
    scored.sort(reverse=True)
    start_nodes = [nid for _, nid in scored[:3]]
    if not start_nodes:
        return 0

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

    lines = []
    for nid in visited:
        d = G.nodes[nid]
        lines.append(f"NODE {d.get('label', nid)} src={d.get('source_file', '')} loc={d.get('source_location', '')}")
    for u, v in edges_seen:
        if u in visited and v in visited:
            d = G.edges[u, v]
            lines.append(f"EDGE {G.nodes[u].get('label', u)} --{d.get('relation', '')}--> {G.nodes[v].get('label', v)}")

    return _estimate_tokens("\n".join(lines))


_SAMPLE_QUESTIONS = [
    "how does authentication work",
    "what is the main entry point",
    "how are errors handled",
    "what connects the data layer to the api",
    "what are the core abstractions",
]


def run_benchmark(
    graph_path: str = "graphify-out/graph.json",
    corpus_words: int | None = None,
    questions: list[str] | None = None,
) -> dict:
    """Measure token reduction: corpus tokens vs graphify query tokens.

    Args:
        graph_path: path to the built graph
        corpus_words: total word count from detect() output; if None, estimated from graph
        questions: list of questions to benchmark; defaults to _SAMPLE_QUESTIONS

    Returns dict with: corpus_tokens, avg_query_tokens, reduction_ratio, per_question
    """
    data = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    try:
        G = json_graph.node_link_graph(data, edges="links")
    except TypeError:
        G = json_graph.node_link_graph(data)

    if corpus_words is None:
        # Rough estimate: each node label is ~3 words, plus source context
        corpus_words = G.number_of_nodes() * 50

    corpus_tokens = corpus_words * 100 // 75  # words → tokens (100 words ≈ 133 tokens)

    qs = questions or _SAMPLE_QUESTIONS
    per_question = []
    for q in qs:
        qt = _query_subgraph_tokens(G, q)
        if qt > 0:
            per_question.append({"question": q, "query_tokens": qt, "reduction": round(corpus_tokens / qt, 1)})

    if not per_question:
        return {"error": "No matching nodes found for sample questions. Build the graph first."}

    avg_query_tokens = sum(p["query_tokens"] for p in per_question) // len(per_question)
    reduction_ratio = round(corpus_tokens / avg_query_tokens, 1) if avg_query_tokens > 0 else 0

    return {
        "corpus_tokens": corpus_tokens,
        "corpus_words": corpus_words,
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "avg_query_tokens": avg_query_tokens,
        "reduction_ratio": reduction_ratio,
        "per_question": per_question,
    }


def print_benchmark(result: dict) -> None:
    """Print a human-readable benchmark report."""
    if "error" in result:
        print(f"Benchmark error: {result['error']}")
        return

    print(f"\ngraphify token reduction benchmark")
    print(f"{'─' * 50}")
    print(f"  Corpus:          {result['corpus_words']:,} words → ~{result['corpus_tokens']:,} tokens (naive)")
    print(f"  Graph:           {result['nodes']:,} nodes, {result['edges']:,} edges")
    print(f"  Avg query cost:  ~{result['avg_query_tokens']:,} tokens")
    print(f"  Reduction:       {result['reduction_ratio']}x fewer tokens per query")
    print(f"\n  Per question:")
    for p in result["per_question"]:
        print(f"    [{p['reduction']}x] {p['question'][:55]}")
    print()
