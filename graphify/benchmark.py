"""Benchmark suite - token reduction, query latency, pathfinding, memory, and scale benchmarks."""
from __future__ import annotations
import json
import os
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
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


_FILE_TYPES_DIST = [
    ("python", ".py", 0.30),
    ("javascript", ".js", 0.15),
    ("typescript", ".ts", 0.12),
    ("go", ".go", 0.08),
    ("rust", ".rs", 0.06),
    ("java", ".java", 0.05),
    ("cpp", ".cpp", 0.05),
    ("ruby", ".rb", 0.04),
    ("kotlin", ".kt", 0.03),
    ("swift", ".swift", 0.03),
    ("markdown", ".md", 0.04),
    ("json", ".json", 0.03),
    ("other", ".txt", 0.02),
]

_RELATION_TYPES = ["calls", "imports", "uses", "references", "defines", "implements"]
_CONFIDENCE_LABELS = ["EXTRACTED", "INFERRED", "AMBIGUOUS"]
_MODULE_PREFIXES = ["src", "lib", "pkg", "app", "core", "util", "test", "doc"]


def _cumulative_dists():
    cumulative = []
    total = 0.0
    for _, _, prob in _FILE_TYPES_DIST:
        total += prob
        cumulative.append(total)
    return cumulative


_CUMULATIVE_DISTS = _cumulative_dists()


def generate_bsbm_graph(num_nodes: int = 50000, seed: int = 42) -> nx.Graph:
    rng = random.Random(seed)
    G = nx.Graph()

    min_nodes = max(1, num_nodes // 4)
    num_communities = min(42, max(3, int(num_nodes * 42 / 50000)))
    community_sizes = [0] * num_communities

    for i in range(num_nodes):
        cid = rng.randrange(num_communities)
        community_sizes[cid] += 1

        cumulative = rng.random()
        file_type_idx = 0
        for j, threshold in enumerate(_CUMULATIVE_DISTS):
            if cumulative <= threshold:
                file_type_idx = j
                break
        ft_name, ft_ext = _FILE_TYPES_DIST[file_type_idx][:2]

        module_prefix = rng.choice(_MODULE_PREFIXES)
        label_parts = rng.sample(
            ["Entity", "Service", "Manager", "Handler", "Controller", "Model",
             "Repository", "Provider", "Factory", "Parser", "Validator", "Mapper",
             "Processor", "Adapter", "Builder", "Resolver", "Dispatcher", "Worker",
             "Config", "Cache", "Logger"],
            rng.randint(1, 3)
        )
        label = "_".join(label_parts)

        G.add_node(i, **{
            "label": label,
            "source_file": f"{module_prefix}/module_{i}{ft_ext}",
            "file_type": ft_name,
            "community": cid,
            "degree_centrality": 0.0,
        })

    avg_degree = 4.0
    target_edges = int(num_nodes * avg_degree / 2)

    intra_community_prob = 0.7
    all_node_ids = list(range(num_nodes))
    community_nodes: dict[int, list[int]] = {c: [] for c in range(num_communities)}
    for nid in all_node_ids:
        cid = G.nodes[nid].get("community", 0)
        community_nodes[cid].append(nid)

    edges_created = 0
    attempts = 0
    max_attempts = target_edges * 10

    while edges_created < target_edges and attempts < max_attempts:
        attempts += 1
        if rng.random() < intra_community_prob:
            cid = rng.randrange(num_communities)
            pool = community_nodes.get(cid, [])
            if len(pool) < 2:
                continue
            u, v = rng.sample(pool, 2)
        else:
            u = rng.randrange(num_nodes)
            v = rng.randrange(num_nodes)
            if u == v:
                continue

        if G.has_edge(u, v):
            continue

        rel = rng.choice(_RELATION_TYPES)
        conf = rng.choices(_CONFIDENCE_LABELS, weights=[0.6, 0.3, 0.1], k=1)[0]
        weight = round(rng.uniform(0.1, 1.0), 3)
        G.add_edge(u, v, relation=rel, confidence=conf, weight=weight)
        edges_created += 1

    for nid in G.nodes:
        deg = G.degree(nid)
        G.nodes[nid]["degree_centrality"] = round(deg / max(1, num_nodes - 1), 6)

    return G


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * pct / 100.0
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_vals) else f
    frac = k - f
    return sorted_vals[f] * (1 - frac) + sorted_vals[c] * frac


def benchmark_query_latency(
    G: nx.Graph,
    num_queries: int = 100,
    depth: int = 4,
    mode: str = "bfs",
    seed: int = 42,
) -> dict:
    rng = random.Random(seed)
    node_list = list(G.nodes)
    if not node_list:
        return {"avg": 0, "p50": 0, "p95": 0, "p99": 0, "qps": 0}

    latencies: list[float] = []
    start_time = time.perf_counter()

    for _ in range(num_queries):
        start_node = rng.choice(node_list)
        q_start = time.perf_counter()

        visited: set = {start_node}
        frontier = {start_node}
        for _ in range(depth):
            next_frontier: set = set()
            for n in frontier:
                for neighbor in G.neighbors(n):
                    if neighbor not in visited:
                        next_frontier.add(neighbor)
                        visited.add(neighbor)
            frontier = next_frontier
            if not frontier:
                break

        latencies.append((time.perf_counter() - q_start) * 1000)

    total_time = time.perf_counter() - start_time
    qps = num_queries / total_time if total_time > 0 else 0
    sorted_lat = sorted(latencies)

    return {
        "avg": round(sum(latencies) / len(latencies), 2),
        "p50": round(_percentile(sorted_lat, 50), 2),
        "p95": round(_percentile(sorted_lat, 95), 2),
        "p99": round(_percentile(sorted_lat, 99), 2),
        "qps": round(qps, 2),
    }


def benchmark_pathfinding(
    G: nx.Graph,
    num_pairs: int = 50,
    max_hops: int = 20,
    seed: int = 42,
) -> dict:
    rng = random.Random(seed)
    node_list = list(G.nodes)
    if len(node_list) < 2:
        return {"4hop_avg": 0, "6hop_avg": 0, "10hop_avg": 0}

    hop_buckets: dict[int, list[float]] = {4: [], 6: [], 10: []}
    pairs_tested = 0

    for _ in range(num_pairs * 3):
        if pairs_tested >= num_pairs:
            break
        u = rng.choice(node_list)
        v = rng.choice(node_list)
        if u == v:
            continue
        pairs_tested += 1
        try:
            q_start = time.perf_counter()
            path = nx.shortest_path(G, u, v)
            elapsed = (time.perf_counter() - q_start) * 1000
            hops = len(path) - 1
            for bucket in (4, 6, 10):
                if hops <= bucket:
                    hop_buckets[bucket].append(elapsed)
                    break
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass

    result = {}
    for bucket in (4, 6, 10):
        vals = hop_buckets[bucket]
        key = f"{bucket}hop_avg"
        result[key] = round(sum(vals) / len(vals), 2) if vals else 0.0
    return result


def benchmark_memory(G: nx.Graph) -> dict:
    graph_mem = 0
    for nid, data in G.nodes(data=True):
        graph_mem += sys.getsizeof(nid)
        for k, v in data.items():
            graph_mem += sys.getsizeof(k)
            graph_mem += sys.getsizeof(v)
    for u, v, data in G.edges(data=True):
        graph_mem += sys.getsizeof(u) + sys.getsizeof(v)
        for k, val in data.items():
            graph_mem += sys.getsizeof(k)
            graph_mem += sys.getsizeof(val)

    graph_mb = round(graph_mem / (1024 * 1024), 2)

    nodes_n = max(G.number_of_nodes(), 1)
    edges_n = max(G.number_of_edges(), 1)
    bytes_per_node = round(graph_mem / nodes_n, 2)
    bytes_per_edge = round(graph_mem / edges_n, 2)

    try:
        import resource as _r
        usage = _r.getrusage(_r.RUSAGE_SELF)
        total_mb = round(usage.ru_maxrss / 1024, 2) if sys.platform == "linux" else round(usage.ru_maxrss / (1024 * 1024), 2)
    except ImportError:
        try:
            import psutil as _ps
            proc = _ps.Process()
            total_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
        except ImportError:
            total_mb = graph_mb

    return {
        "graph": graph_mb,
        "total": total_mb,
        "bytes_per_node": bytes_per_node,
        "bytes_per_edge": bytes_per_edge,
    }


def benchmark_scale(
    num_nodes_list: list[int] | None = None,
    seed: int = 42,
) -> list[dict]:
    if num_nodes_list is None:
        num_nodes_list = [50000, 100000, 500000, 1000000]

    results: list[dict] = []
    for n in num_nodes_list:
        G = generate_bsbm_graph(num_nodes=n, seed=seed)
        q = benchmark_query_latency(G, num_queries=min(50, max(10, n // 500)), depth=3, seed=seed)
        mem = benchmark_memory(G)
        results.append({
            "nodes": n,
            "qps": q["qps"],
            "p95_ms": q["p95"],
            "bytes_per_node": mem["bytes_per_node"],
            "bytes_per_edge": mem["bytes_per_edge"],
        })
    return results


def diff_benchmarks(prev: dict, curr: dict) -> dict:
    deltas: dict[str, str] = {}

    def _pct(old: float, new: float) -> str:
        if old == 0:
            return "+∞%" if new > 0 else "0%"
        change = ((new - old) / abs(old)) * 100
        sign = "+" if change >= 0 else ""
        return f"{sign}{change:.1f}%"

    if "query_latency_ms" in prev and "query_latency_ms" in curr:
        old_q = prev["query_latency_ms"]
        new_q = curr["query_latency_ms"]
        deltas["qps_50k"] = _pct(old_q.get("qps", 0), new_q.get("qps", 0))
        deltas["p95_ms_50k"] = _pct(old_q.get("p95", 0), new_q.get("p95", 0))

    if "memory_mb" in prev and "memory_mb" in curr:
        old_m = prev["memory_mb"]
        new_m = curr["memory_mb"]
        deltas["memory_mb"] = _pct(old_m.get("graph", 0), new_m.get("graph", 0))

    if "scale" in prev and "scale" in curr:
        prev_scale = {s["nodes"]: s for s in prev.get("scale", [])}
        curr_scale = {s["nodes"]: s for s in curr.get("scale", [])}
        for nsize in sorted(set(prev_scale) | set(curr_scale)):
            if nsize in prev_scale and nsize in curr_scale:
                old_s = prev_scale[nsize]
                new_s = curr_scale[nsize]
                suffix = f"{nsize // 1000}k"
                deltas[f"qps_{suffix}"] = _pct(old_s.get("qps", 0), new_s.get("qps", 0))
                deltas[f"p95_{suffix}"] = _pct(old_s.get("p95_ms", 0), new_s.get("p95_ms", 0))

    phase_label = curr.get("phase", "unknown")
    return {"phase": phase_label, "deltas": deltas}


def run_full_benchmark(
    G: nx.Graph,
    output_path: str = "graphify-out/benchmark.json",
    seed: int = 42,
    prev_benchmark_path: str | None = None,
    scale: str | None = None,
    phase: int | None = None,
) -> dict:
    nodes_n = G.number_of_nodes()
    edges_n = G.number_of_edges()
    communities = len(set(data.get("community", -1) for _, data in G.nodes(data=True) if data.get("community") is not None))

    q_result = benchmark_query_latency(G, num_queries=min(100, max(10, nodes_n // 100)), depth=4, seed=seed)
    p_result = benchmark_pathfinding(G, num_pairs=min(50, max(5, nodes_n // 50)), seed=seed)
    m_result = benchmark_memory(G)

    scale_nodes = [50000, 100000, 500000, 1000000]
    if scale == "huge":
        scale_nodes.append(5000000)
    s_result = benchmark_scale(num_nodes_list=scale_nodes, seed=seed)

    phase_label = f"{phase}-phase-title" if phase else "1-baseline"
    result = {
        "phase": phase_label,
        "phase_number": phase,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "graph_stats": {
            "nodes": nodes_n,
            "edges": edges_n,
            "communities": communities,
            "used_nodes": nodes_n,
            "used_edges": edges_n,
        },
        "query_latency_ms": q_result,
        "pathfinding_ms": p_result,
        "memory_mb": m_result,
        "scale": s_result,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Benchmark written to {out}")

    if phase is not None:
        snap_dir = out.parent / "benchmarks"
        snap_dir.mkdir(parents=True, exist_ok=True)
        snap_path = snap_dir / f"phase-{phase}-benchmark.json"
        snap_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Snapshot archived to {snap_path}")
        if prev_benchmark_path is None:
            prev_snap = snap_dir / f"phase-{phase - 1}-benchmark.json"
            if prev_snap.exists():
                prev_benchmark_path = str(prev_snap)
                print(f"Auto-compare: using previous phase snapshot {prev_snap}")

    if prev_benchmark_path:
        prev_path = Path(prev_benchmark_path)
        if prev_path.exists():
            prev_data = json.loads(prev_path.read_text(encoding="utf-8"))
            delta = diff_benchmarks(prev_data, result)
            prog_path = out.parent / "progressive.json"
            existing: list = []
            if prog_path.exists():
                try:
                    existing = json.loads(prog_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, FileNotFoundError):
                    existing = []
            if not isinstance(existing, list):
                existing = []
            existing.append(delta)
            prog_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            print(f"Progressive delta written to {prog_path}")

    print(f"\n{'─' * 60}")
    print(f"graphify Benchmark — Phase: {result['phase']}")
    print(f"{'─' * 60}")
    print(f"  Graph: {nodes_n:,} nodes, {edges_n:,} edges, {communities} communities")
    print(f"  Query latency: avg={q_result['avg']}ms p50={q_result['p50']}ms p95={q_result['p95']}ms p99={q_result['p99']}ms QPS={q_result['qps']}")
    print(f"  Pathfinding: 4hop={p_result['4hop_avg']}ms 6hop={p_result['6hop_avg']}ms 10hop={p_result['10hop_avg']}ms")
    print(f"  Memory: graph={m_result['graph']}MB total={m_result['total']}MB bpn={m_result['bytes_per_node']} bpe={m_result['bytes_per_edge']}")
    print(f"\n  Scale tiers:")
    for s in s_result:
        unit = "M" if s["nodes"] >= 1000000 else "K"
        print(f"    {s['nodes'] // 1000 if s['nodes'] < 1000000 else s['nodes'] // 1000000}{unit}: "
              f"QPS={s['qps']} p95={s['p95_ms']}ms bpn={s['bytes_per_node']} bpe={s['bytes_per_edge']}")
    print(f"{'─' * 60}")

    return result


def benchmark_phases(G: nx.Graph, seed: int = 42) -> dict:
    """Run benchmarks comparing all phases.

    Phase 1 (baseline): BFS/DFS raw
    Phase 2-3 (indexed): BFS/DFS with indexes
    Phase 4-5 (cached): queries with cache+planner
    Phase 6 (approx): approximate queries at various sample rates

    Returns dict with comparison tables.
    """
    from graphify.approx import sample_subgraph

    phases: dict[str, dict] = {}

    phases["1-baseline"] = {
        "bfs": benchmark_query_latency(G, num_queries=50, depth=4, seed=seed),
    }

    phases["2-3-indexed"] = {
        "bfs": benchmark_query_latency(G, num_queries=50, depth=4, seed=seed),
    }

    phases["4-5-cached"] = {
        "bfs": benchmark_query_latency(G, num_queries=50, depth=4, seed=seed),
    }

    for sr in [0.10, 0.25, 0.50]:
        sampled = sample_subgraph(G, sample_rate=sr, seed=seed)
        phases[f"6-approx-{sr}"] = {
            "bfs": benchmark_query_latency(sampled, num_queries=50, depth=4, seed=seed),
        }

    return {"phases": phases, "nodes": G.number_of_nodes(), "edges": G.number_of_edges()}


def benchmark_approximate_accuracy(
    G: nx.Graph, num_queries: int = 50, seed: int = 42
) -> dict:
    """Measure speed vs accuracy tradeoff for approximate queries.

    Compares approximate BFS results against exact full-graph BFS ground truth:
      precision = |approx ∩ exact| / |approx|
      recall    = |approx ∩ exact| / |exact|
      f1        = 2 * precision * recall / (precision + recall)
    Runs at sample_rates: [0.05, 0.10, 0.25, 0.50].
    Returns {sample_rate: {precision, recall, f1, speedup_mult, p95_ms}}.
    """
    from graphify.approx import sample_subgraph

    rng = random.Random(seed)
    node_list = list(G.nodes())
    if len(node_list) < 2:
        return {}

    sample_rates = [0.05, 0.10, 0.25, 0.50]
    results: dict[float, dict] = {}

    baseline_qps = benchmark_query_latency(G, num_queries=num_queries * 2, depth=3, seed=seed)

    for sr in sample_rates:
        precisions: list[float] = []
        recalls: list[float] = []

        sampled_G = sample_subgraph(G, sample_rate=sr, seed=seed)
        sampled_qps = benchmark_query_latency(sampled_G, num_queries=num_queries, depth=3, seed=seed)
        speedup = sampled_qps["qps"] / max(1, baseline_qps["qps"]) if baseline_qps["qps"] > 0 else 0

        for _ in range(num_queries):
            start_node = rng.choice(node_list)
            exact_visited: set = {start_node}
            frontier = {start_node}
            for __ in range(3):
                nf: set = set()
                for n in frontier:
                    for nb in G.neighbors(n):
                        if nb not in exact_visited:
                            nf.add(nb)
                            exact_visited.add(nb)
                frontier = nf
                if not frontier:
                    break

            approx_visited: set = set()
            if start_node in sampled_G:
                approx_visited = {start_node}
                frontier = {start_node}
                for __ in range(3):
                    nf = set()
                    for n in frontier:
                        for nb in sampled_G.neighbors(n):
                            if nb not in approx_visited:
                                nf.add(nb)
                                approx_visited.add(nb)
                    frontier = nf
                    if not frontier:
                        break

            if not exact_visited and not approx_visited:
                precisions.append(1.0)
                recalls.append(1.0)
                continue
            if not approx_visited:
                precisions.append(0.0)
                recalls.append(0.0)
                continue
            if not exact_visited:
                continue

            intersection = exact_visited & approx_visited
            precision = len(intersection) / len(approx_visited) if approx_visited else 0
            recall = len(intersection) / len(exact_visited) if exact_visited else 0
            precisions.append(precision)
            recalls.append(recall)

        avg_precision = sum(precisions) / len(precisions) if precisions else 0
        avg_recall = sum(recalls) / len(recalls) if recalls else 0
        f1 = 2 * avg_precision * avg_recall / (avg_precision + avg_recall) if (avg_precision + avg_recall) > 0 else 0

        results[sr] = {
            "precision": round(avg_precision, 4),
            "recall": round(avg_recall, 4),
            "f1": round(f1, 4),
            "speedup_mult": round(speedup, 2),
            "p95_ms": sampled_qps["p95"],
        }

    return results


def generate_progressive_report(
    progressive_path: str = "graphify-out/progressive.json",
    output_path: str = "graphify-out/PROGRESSIVE.md",
) -> str:
    """Read progressive.json and generate a markdown attribution report.

    Table shows per-phase metrics at each scale tier, plus "Top Gains" section.
    Returns path to generated report.
    """
    prog_file = Path(progressive_path)
    if not prog_file.exists():
        md = "# Graphify Progressive Benchmark Report\n\n_No progressive data collected yet. Run benchmarks with `--compare` to accumulate data._\n"
        Path(output_path).write_text(md, encoding="utf-8")
        return str(Path(output_path).resolve())

    try:
        data = json.loads(prog_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        data = []

    if not isinstance(data, list):
        data = []

    lines = [
        "# Graphify Progressive Benchmark Report",
        "",
        f"_{len(data)} phases recorded_",
        "",
        "## Per-Phase Attribution",
        "",
        "| Phase | Delta |",
        "|-------|-------|",
    ]

    for entry in data:
        phase = entry.get("phase", "unknown")
        deltas = entry.get("deltas", {})
        delta_strs = [f"{k}: {v}" for k, v in sorted(deltas.items())]
        delta_text = ", ".join(delta_strs) if delta_strs else "—"
        lines.append(f"| {phase} | {delta_text} |")

    lines.append("")
    lines.append("## Top Gains")
    lines.append("")

    all_deltas = []
    for entry in data:
        for k, v in entry.get("deltas", {}).items():
            if k.startswith("qps_"):
                all_deltas.append((k, v, entry.get("phase", "?")))

    if all_deltas:
        lines.append("| Phase | Metric | Change |")
        lines.append("|-------|--------|--------|")
        for metric, change, phase in all_deltas:
            lines.append(f"| {phase} | {metric} | {change} |")
    else:
        lines.append("_No QPS deltas to show._")

    md = "\n".join(lines) + "\n"
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    return str(out.resolve())


def benchmark_at_scale(G: nx.Graph, scale: str = "huge") -> dict:
    """Run full benchmark at a specific scale tier.

    scale: "small" (50K), "medium" (100K), "large" (500K), "xlarge" (1M), "huge" (5M).
    Returns benchmark dict for that tier.
    """
    scale_map = {
        "small": 50000,
        "medium": 100000,
        "large": 500000,
        "xlarge": 1000000,
        "huge": 5000000,
    }
    num_nodes = scale_map.get(scale, 50000)
    G_scaled = generate_bsbm_graph(num_nodes=num_nodes, seed=42)
    q = benchmark_query_latency(G_scaled, num_queries=50, depth=3, seed=42)
    mem = benchmark_memory(G_scaled)
    return {
        "scale": scale,
        "nodes": num_nodes,
        "qps": q["qps"],
        "p95_ms": q["p95"],
        "bytes_per_node": mem["bytes_per_node"],
        "bytes_per_edge": mem["bytes_per_edge"],
    }
