#!/usr/bin/env python3
"""Run Kimi K2.6 extraction across the same corpora/files used in the K2.5 benchmark."""
from __future__ import annotations
import json, sys, time, random
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm import extract_files_direct, estimate_cost

KIMI_KEY = "sk-5rsh69xqeq2JRREJzelnTcnkxpn2hMcZdRpBb0iVgabnJ7br"
MODEL    = "kimi-k2.6"
CHUNK    = 2  # files per call, same as previous benchmark

CORPORA = {
    "httpx":   Path("/home/safi/graphify_eval/codebase/httpx"),
    "click":   Path("/home/safi/graphify_eval/codebase/click"),
    "rich":    Path("/home/safi/graphify_eval/codebase/rich"),
    "nanoGPT": Path("/home/safi/graphify_eval/mixed/nanoGPT"),
}

_SKIP = {".git","graphify-out","venv",".venv","build","dist","__pycache__",".pytest_cache","node_modules","egg-info"}
_EXT  = {".py",".ts",".js",".go",".rs",".java",".c",".cpp",".rb",".cs",
         ".md",".txt",".rst",".php",".swift",".kt",".scala",".lua",".zig"}

def pick(path: Path, n: int = 60, seed: int = 42) -> list[Path]:
    candidates = [p for p in sorted(path.rglob("*"))
                  if p.is_file()
                  and p.suffix.lower() in _EXT
                  and not any(x in _SKIP or x.endswith(".egg-info") for x in p.parts)]
    random.seed(seed)
    random.shuffle(candidates)
    return candidates[:n]

def chunk(lst, size):
    return [lst[i:i+size] for i in range(0, len(lst), size)]

def analyze(result):
    nodes = result.get("nodes", [])
    edges = result.get("edges", [])
    return {
        "node_count":     len(nodes),
        "edge_count":     len(edges),
        "relation_types": dict(Counter(e.get("relation","") for e in edges)),
        "node_labels":    [n.get("label", n.get("id","")) for n in nodes],
        "input_tokens":   result.get("input_tokens", 0),
        "output_tokens":  result.get("output_tokens", 0),
        "elapsed_seconds":result.get("elapsed_seconds", 0),
    }

results = {}

for corpus, path in CORPORA.items():
    print(f"\n{'='*60}")
    print(f"  {corpus}  ({MODEL})")
    print(f"{'='*60}")

    files = pick(path)
    chunks = chunk(files, CHUNK)[:3]  # 3 chunks per corpus = 6 files
    print(f"  {len(files)} files sampled → {len(chunks)} chunks of {CHUNK}")

    all_nodes, all_edges, rel_types = [], [], Counter()
    total_in, total_out, total_cost, total_time = 0, 0, 0.0, 0.0
    failed = 0

    for i, ch in enumerate(chunks):
        print(f"  chunk {i+1}/{len(chunks)}: {[f.name for f in ch]} ...", end=" ", flush=True)
        try:
            r = extract_files_direct(ch, backend="kimi", api_key=KIMI_KEY, model=MODEL, root=path)
            m = analyze(r)
            all_nodes.extend(m["node_labels"])
            all_edges.append(m["edge_count"])
            rel_types.update(m["relation_types"])
            total_in   += m["input_tokens"]
            total_out  += m["output_tokens"]
            cost = estimate_cost("kimi", m["input_tokens"], m["output_tokens"])
            total_cost += cost
            total_time += m["elapsed_seconds"]
            print(f"nodes={m['node_count']} edges={m['edge_count']} rel_types={len(m['relation_types'])} cost=${cost:.4f} t={m['elapsed_seconds']:.1f}s")
        except Exception as exc:
            print(f"FAILED: {exc}")
            failed += 1

    results[corpus] = {
        "model":           MODEL,
        "chunk_size":      CHUNK,
        "total_nodes":     len(all_nodes),
        "total_edges":     sum(all_edges),
        "unique_rel_types":len(rel_types),
        "relation_types":  dict(rel_types.most_common()),
        "input_tokens":    total_in,
        "output_tokens":   total_out,
        "cost_usd":        round(total_cost, 4),
        "elapsed_seconds": round(total_time, 1),
        "chunks_run":      len(chunks) - failed,
        "chunks_failed":   failed,
    }

    print(f"\n  TOTAL: nodes={results[corpus]['total_nodes']} edges={results[corpus]['total_edges']} "
          f"rel_types={results[corpus]['unique_rel_types']} cost=${results[corpus]['cost_usd']:.4f}")

out = Path("scripts/benchmark_kimi_k2.6.json")
out.write_text(json.dumps(results, indent=2))
print(f"\n\nResults saved to {out}")

# Print comparison table vs K2.5 results
k25_ref = {
    "httpx":   {"total_nodes": 877+502+370, "total_edges": 907+543+358, "unique_rel_types": 48, "cost_usd": 0.72+0.47+0.40},
    "click":   {"total_nodes": 653+540+310, "total_edges": 637+470+231, "unique_rel_types": 44, "cost_usd": 0.67+0.50+0.36},
    "rich":    {"total_nodes": 447+397+311, "total_edges": 446+397+294, "unique_rel_types": 35, "cost_usd": 0.62+0.53+0.44},
    "nanoGPT": {"total_nodes": 183+126+100+103, "total_edges": 222+148+107+101, "unique_rel_types": 36, "cost_usd": 0.25+0.16+0.11+0.09},
}

print(f"\n{'='*70}")
print(f"  Kimi K2.5 vs K2.6 — same corpora, chunk={CHUNK}")
print(f"{'─'*70}")
print(f"  {'Corpus':<10} {'K2.5 nodes':>12} {'K2.6 nodes':>12} {'K2.5 rel':>10} {'K2.6 rel':>10} {'K2.5 $':>8} {'K2.6 $':>8}")
print(f"{'─'*70}")
for corpus in CORPORA:
    r = results[corpus]
    ref = k25_ref[corpus]
    print(f"  {corpus:<10} {ref['total_nodes']:>12} {r['total_nodes']:>12} "
          f"{ref['unique_rel_types']:>10} {r['unique_rel_types']:>10} "
          f"${ref['cost_usd']:>7.2f} ${r['cost_usd']:>7.4f}")
print(f"{'='*70}")
