#!/usr/bin/env python3
"""
Kimi K2.6 large-context benchmark — 2 corpora, chunk=4 and chunk=8.

K2.5 reference (from previous benchmark):
  httpx   chunk=4: nodes=502, edges=543, rel_types=34
  httpx   chunk=8: nodes=370, edges=358, rel_types=37
  nanoGPT chunk=4: nodes=100, edges=107, rel_types=24
  nanoGPT chunk=8: nodes=103, edges=101, rel_types=26

Claude Sonnet reference (chunk=4 and chunk=8):
  httpx   chunk=4: nodes=417, rel_types=8
  httpx   chunk=8: nodes=290, rel_types=7
  nanoGPT chunk=4: nodes=108, rel_types=8
  nanoGPT chunk=8: nodes=83,  rel_types=8
"""
from __future__ import annotations
import json, sys, time, random
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm import extract_files_direct, estimate_cost

KIMI_KEY = "sk-5rsh69xqeq2JRREJzelnTcnkxpn2hMcZdRpBb0iVgabnJ7br"
MODEL    = "kimi-k2.6"

CORPORA = {
    "nanoGPT": Path("/home/safi/graphify_eval/mixed/nanoGPT"),
    "httpx":   Path("/home/safi/graphify_eval/codebase/httpx"),
}

CHUNK_SIZES = [4, 8]

_SKIP = {".git","graphify-out","venv",".venv","build","dist","__pycache__",
         ".pytest_cache","node_modules","egg-info"}
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

def analyze(result):
    nodes = result.get("nodes", [])
    edges = result.get("edges", [])
    return {
        "node_count":      len(nodes),
        "edge_count":      len(edges),
        "unique_rel_types":len(set(e.get("relation","") for e in edges)),
        "relation_types":  dict(Counter(e.get("relation","") for e in edges)),
        "input_tokens":    result.get("input_tokens", 0),
        "output_tokens":   result.get("output_tokens", 0),
        "elapsed_seconds": result.get("elapsed_seconds", 0),
    }

all_results = {}

for chunk_size in CHUNK_SIZES:
    print(f"\n{'#'*65}")
    print(f"  CHUNK = {chunk_size} files")
    print(f"{'#'*65}")
    chunk_results = {}

    for corpus, path in CORPORA.items():
        files = pick(path)
        batch = files[:chunk_size]
        print(f"\n  [{corpus}] sending {len(batch)} files...", end=" ", flush=True)
        try:
            r = extract_files_direct(batch, backend="kimi", api_key=KIMI_KEY,
                                     model=MODEL, root=path)
            m = analyze(r)
            cost = estimate_cost("kimi", m["input_tokens"], m["output_tokens"])
            print(f"nodes={m['node_count']} edges={m['edge_count']} "
                  f"rel_types={m['unique_rel_types']} "
                  f"tokens={m['input_tokens']:,}in/{m['output_tokens']:,}out "
                  f"cost=${cost:.4f} t={m['elapsed_seconds']:.1f}s")
            chunk_results[corpus] = {**m, "cost_usd": round(cost, 4)}
        except Exception as exc:
            print(f"FAILED: {exc}")
            chunk_results[corpus] = {"error": str(exc)}

    all_results[f"chunk_{chunk_size}"] = chunk_results

out = Path("scripts/benchmark_kimi_k2.6_largechunk.json")
out.write_text(json.dumps(all_results, indent=2))
print(f"\nResults saved to {out}")

# Reference data
REF = {
    "K2.5": {
        4: {"httpx": (502, 34), "nanoGPT": (100, 24)},
        8: {"httpx": (370, 37), "nanoGPT": (103, 26)},
    },
    "Sonnet": {
        4: {"httpx": (417, 8),  "nanoGPT": (108, 8)},
        8: {"httpx": (290, 7),  "nanoGPT": (83,  8)},
    },
}

print(f"\n{'='*75}")
print(f"  Relation-type diversity — K2.6 vs K2.5 vs Claude Sonnet 4.6")
print(f"{'─'*75}")
print(f"  {'Corpus+Chunk':<18} {'Sonnet nodes':>13} {'Sonnet rel':>11} {'K2.5 nodes':>11} {'K2.5 rel':>9} {'K2.6 nodes':>11} {'K2.6 rel':>9}")
print(f"{'─'*75}")
for chunk_size in CHUNK_SIZES:
    for corpus in CORPORA:
        k26 = all_results.get(f"chunk_{chunk_size}", {}).get(corpus, {})
        k25n, k25r = REF["K2.5"][chunk_size][corpus]
        snn, snr   = REF["Sonnet"][chunk_size][corpus]
        k26n = k26.get("node_count", "ERR")
        k26r = k26.get("unique_rel_types", "ERR")
        label = f"{corpus} @{chunk_size}"
        print(f"  {label:<18} {snn:>13} {snr:>11} {k25n:>11} {k25r:>9} {k26n!s:>11} {k26r!s:>9}")
print(f"{'='*75}")
