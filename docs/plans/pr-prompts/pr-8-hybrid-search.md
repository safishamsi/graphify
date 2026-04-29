# PR 8: Hybrid Search (BM25 + Semantic + RRF)

**Phase:** 11
**Stream:** B (Code Intelligence)
**Estimate:** 2-3 weeks
**Depends on:** Phase 10 (process tracing for grouped results), Phase 5 (caching)

## What to Build

### 1. BM25 Index (`graphify/search/__init__.py` — package init, empty)
### 2. BM25 Index (`graphify/search/bm25.py` — NEW)

```python
import re
import math
from collections import defaultdict

class BM25Index:
    """BM25 keyword search on symbol names, file paths, docstrings.
    Built at graph load time. Incrementally updateable.
    Pure Python — no external deps."""
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: dict[str, str] = {}        # node_id → searchable text
        self.doc_lengths: dict[str, int] = {}
        self.avg_doc_length: float = 0.0
        self.inverted_index: dict[str, dict[str, int]] = defaultdict(dict)  # term → {doc_id: freq}
        self.doc_count_per_term: dict[str, int] = defaultdict(int)
        self.total_docs: int = 0
    
    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into lowercase alphanumeric tokens."""
        return re.findall(r'[a-z0-9]+', text.lower())
    
    def add_document(self, doc_id: str, text: str) -> None:
        """Add a document to the index."""
        
    def remove_document(self, doc_id: str) -> None:
        """Remove a document from the index (for incremental updates)."""
        
    def search(self, query: str, top_k: int = 20) -> list[tuple[str, float]]:
        """Search and return (doc_id, bm25_score) sorted descending."""
        
    def index_from_graph(self, G) -> None:
        """Index all nodes in a graph.
        For each node: tokenize label + signature + docstring + source_file."""
```

### 3. Semantic Embeddings (`graphify/search/embeddings.py` — NEW)

```python
"""Semantic vector embeddings for code symbols.
Uses deterministic random projections (no ML deps required).
For production, swap in sentence-transformers via optional dependency."""

import hashlib
from pathlib import Path

EMBEDDING_DIM = 384

def _import_numpy():
    import numpy as np
    return np

def generate_embedding(text: str, dimensions: int = EMBEDDING_DIM, seed: int = 42) -> list[float]:
    """Generate embedding via content-hash-seeded random projection.
    Deterministic: same text → same embedding across runs.
    L2 normalized. Pure numpy (optional — falls back to random if unavailable)."""

def node_embedding_text(node_data: dict) -> str:
    """Extract searchable text from a node for embedding.
    Concatenates: label + signature + docstring (space separated)."""

def generate_embeddings(G, dimensions: int = EMBEDDING_DIM) -> dict[str, list[float]]:
    """Generate embeddings for all code nodes (skip FILE, CONCEPT types).
    Only embed nodes that have meaningful text (label + optional signature/docstring).
    Returns {node_id: embedding_vector}."""

def compute_cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. Pure Python for portability."""

def search_by_embedding(query_text: str, embeddings: dict[str, list[float]],
                         top_k: int = 20) -> list[tuple[str, float]]:
    """Generate query embedding, compute cosine against all node embeddings.
    Returns (node_id, similarity) sorted descending."""

def save_embeddings(embeddings: dict[str, list[float]], output_dir: Path) -> None:
    """Save embeddings sharded by batches of 10000 nodes.
    Output: output_dir/embeddings_0000.json, embeddings_0001.json, ..."""

def load_embeddings(input_dir: Path) -> dict[str, list[float]]:
    """Load and merge all embedding shards."""

def compute_node_hash(G, node_id: str) -> str:
    """SHA256 of node content. Used for incremental updates:
    only re-embed nodes whose content hash changed."""
```

### 4. Reciprocal Rank Fusion (`graphify/search/fusion.py` — NEW)

```python
def reciprocal_rank_fusion(
    result_sets: list[list[tuple[str, float]]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Merge multiple ranked result lists via RRF.
    
    RRF_score(doc) = sum over result_sets: 1 / (k + rank_in_list)
    
    Merges by rank, not score — avoids calibration issues between
    BM25 and vector scorers which use different scales.
    
    Each result_set is [(doc_id, score), ...] sorted by relevance.
    Returns merged [(doc_id, rrf_score), ...] sorted descending."""
    
def normalize_ranks(results: list[tuple[str, float]]) -> dict[str, int]:
    """Convert scored results to rank mapping: doc_id → rank (1-indexed)."""
```

### 5. Process-Grouped Results (`graphify/search/grouping.py` — NEW)

```python
@dataclass
class GroupedSearchResult:
    process_id: str
    process_name: str
    summary: str
    priority: float                 # Based on symbol match density
    symbol_count: int
    process_type: str               # route_handler, cli_main, etc.
    step_count: int
    definitions: list[dict]         # Top matching definitions
    references: list[dict]          # Related references

def group_results_by_process(
    ranked_results: list[tuple[str, float]],
    G,
    processes: list[Process],
) -> list[GroupedSearchResult]:
    """Group search results by the process they belong to.
    
    For each process, compute priority = avg(match_score) * symbol_density.
    Cross-community results flagged.
    Top 3 definitions and references per process included."""
    
def format_grouped_results(grouped: list[GroupedSearchResult]) -> str:
    """Format grouped results for MCP tool response text.
    Returns human-readable markdown-style text."""
```

### 6. Hybrid Search Orchestrator (`graphify/search/hybrid.py` — NEW)

```python
def hybrid_search(G, query: str, 
                  bm25_index: BM25Index,
                  embeddings: dict[str, list[float]],
                  processes: list[Process] | None = None,
                  top_k: int = 20) -> list[GroupedSearchResult]:
    """Full hybrid search pipeline.
    
    1. BM25 keyword search → ranked results
    2. Semantic embedding search → ranked results
    3. RRF merge (k=60) → combined ranking
    4. Process grouping (if processes available) → GroupedSearchResults
    
    Returns formatted results for MCP response."""
```

### 7. Serve Integration (`graphify/serve.py` — EXTEND)

Replace `_tool_query_graph` default implementation:

```python
def _tool_query_graph(arguments: dict) -> str:
    question = arguments["question"]
    mode = arguments.get("mode", "hybrid")  # NEW DEFAULT: hybrid instead of bfs
    depth = min(int(arguments.get("depth", 3)), 6)
    budget = int(arguments.get("token_budget", 2000))
    
    if mode == "hybrid":
        return _hybrid_query(G, question, bm25, embeddings, processes, top_k=20, token_budget=budget)
    elif mode in ("bfs", "dfs"):
        # Existing BFS/DFS logic (preserved)
        ...
    elif mode == "bidirectional":
        ...
    elif mode == "astar":
        ...
```

New MCP tool `query` (replaces `query_graph` default):
```
query({query: "authentication middleware"}) →
  processes: [{summary, priority, symbol_count, process_type, step_count}]
  definitions: [{name, type, file, confidence}]
  references: [{name, type, file, process_context}]
  total_results: N
```

But keep old `query_graph` tool for backward compatibility — just change its default mode from "bfs" to "hybrid".

### 8. Build Integration (`graphify/build.py` — EXTEND)

Add `generate_embeddings` parameter:
```python
def build_from_json(extraction: dict, *, directed: bool = False,
                    build_indexes: bool = True,
                    materialize: list[str] | None = None,
                    trace_processes: bool = False,
                    generate_embeddings: bool = False) -> nx.Graph:
    """If generate_embeddings=True, compute embeddings after graph built."""
    # ... existing build ...
    if generate_embeddings:
        from .search.embeddings import generate_embeddings, save_embeddings
        emb = generate_embeddings(G)
        save_embeddings(emb, Path("graphify-out/embeddings"))
    return G
```

### 9. Tests

**`tests/test_search_bm25.py` (NEW, 5+ tests):**
```python
def test_bm25_add_and_search():
def test_bm25_empty_index():
def test_bm25_remove_document():
def test_bm25_multiple_docs_ranking():
def test_bm25_index_from_graph():
```

**`tests/test_search_embeddings.py` (NEW, 4+ tests):**
```python
import pytest

def test_generate_embedding_deterministic():
    """Same text → same embedding."""

def test_generate_embedding_shape():
    emb = generate_embedding("def foo()")
    assert len(emb) == EMBEDDING_DIM

def test_cosine_similarity_identical():
    """Identical vectors → 1.0."""

def test_cosine_similarity_orthogonal_approx():
    """Roughly orthogonal → close to 0."""

def test_node_embedding_text():
    """Extracts label + signature + docstring."""
```

**`tests/test_search_fusion.py` (NEW, 4+ tests):**
```python
def test_rrf_merges_rankings():
def test_rrf_empty_input():
def test_rrf_single_list():
def test_normalize_ranks():
```

**`tests/test_search_grouping.py` (NEW, 3+ tests):**
```python
def test_group_results_by_process():
def test_format_grouped_results():
def test_empty_results():
```

## Files Changed/Created

| File | Action | Purpose |
|------|--------|---------|
| `graphify/search/__init__.py` | **New** | Package init |
| `graphify/search/bm25.py` | **New** | BM25 keyword search index |
| `graphify/search/embeddings.py` | **New** | Semantic vector embeddings |
| `graphify/search/fusion.py` | **New** | Reciprocal rank fusion |
| `graphify/search/grouping.py` | **New** | Process-grouped results |
| `graphify/search/hybrid.py` | **New** | Hybrid search orchestrator |
| `graphify/serve.py` | **Extend** | Default mode → hybrid, new query tool, index/embed load |
| `graphify/build.py` | **Extend** | generate_embeddings parameter |
| `tests/test_search_bm25.py` | **New** | |
| `tests/test_search_embeddings.py` | **New** | |
| `tests/test_search_fusion.py` | **New** | |
| `tests/test_search_grouping.py` | **New** | |

## Compatibility
- `query_graph` default mode changes from "bfs" to "hybrid"
- `mode="bfs"` and `mode="dfs"` still work as before
- New `query` MCP tool is additive
- No changes to graph.json format
- embeddings stored in `graphify-out/embeddings/`
- numpy is optional — deterministic fallback uses pure Python + hashlib

## Verification
```bash
pytest tests/test_search_bm25.py tests/test_search_embeddings.py tests/test_search_fusion.py tests/test_search_grouping.py -q
pytest tests/test_serve.py -q
pytest tests/ -q  # full suite
```

### Search Quality Benchmarks

Add to `graphify/benchmark.py`:

```python
def benchmark_search_latency(G, bm25_index, embeddings, num_queries: int = 50, seed: int = 42) -> dict:
    """Measure search latency by method.
    Returns {bm25_ms: {avg, p95}, semantic_ms: {avg, p95}, hybrid_ms: {avg, p95},
            rrf_overhead_ms: {avg}}."""

def benchmark_search_overlap(bm25_results: dict, semantic_results: dict, k: int = 20) -> dict:
    """Measure result overlap between BM25 and semantic search.
    Returns {overlap_at_5: float, overlap_at_10: float, overlap_at_20: float,
            rrf_boost_pct: float} — % of results IMPROVED by RRF fusion over either method alone."""

def benchmark_search_relevance(G, bm25_index, embeddings,
                               judgments: dict[str, set[str]],
                               ks: list[int] = [5, 10, 20]) -> dict:
    """Measure search relevance with ground truth judgments.
    judgments: {query_text: {relevant_node_id, ...}} — manually curated.
    Returns {
      bm25:     {k: {precision, recall, ndcg} for k in ks},
      semantic: {k: {precision, recall, ndcg} for k in ks},
      hybrid:   {k: {precision, recall, ndcg} for k in ks},
    }
    NDCG uses binary relevance (relevant=1, not=0).
    Precision@k = |retrieved ∩ relevant| / k
    Recall@k    = |retrieved ∩ relevant| / |relevant|"""

def load_relevance_judgments(path: str) -> dict[str, set[str]]:
    """Load relevance judgments from JSON.
    Format: {"query text": ["relevant_node_id", ...], ...}"""
```

Run after implementation:
```bash
python -c "
from graphify.search import BM25Index; from graphify.search.embeddings import generate_embeddings, search_by_embedding
from graphify.benchmark import benchmark_search_latency
import json
G = json.load(open('graphify-out/graph.json'))
bm25 = BM25Index(); bm25.index_from_graph(G)
emb = generate_embeddings(G)
print(benchmark_search_latency(G, bm25, emb))
"
```

### Commit

```bash
git add -A && git commit -m "feat(phase-11): hybrid search (BM25 + semantic + RRF)"
```

---

## Code Review Checklist

Before merging this PR, verify:
- [ ] All tests pass: `pytest tests/ -q`
- [ ] `benchmark_search_relevance()` runs against `tests/fixtures/search_judgments.json`
- [ ] Hybrid search (RRF) precision@10 ≥ best single method
- [ ] BM25 index builds from graph and searches return ranked results
- [ ] Semantic search L2-normalizes and returns correct cosine rankings
- [ ] RRF fusion result set is not subset of BM25 or semantic alone
- [ ] Process-grouped results are non-empty when processes exist
- [ ] Default mode changed to "hybrid" — `mode="bfs"` still works
- [ ] `query` MCP tool is a working alias for `query_graph` with hybrid default
- [ ] At least 1 other developer reviewed

---

## CI Verification
```bash
# Run automated verification for this PR:
bash docs/plans/verify-pr.sh 8

# Expected checks:
# - Full test suite passes
# - tests/test_search_*.py all pass
# - Search relevance: P@10 >= 0.85
# - benchmark snapshot archived to graphify-out/benchmarks/phase-8-benchmark.json

# After passing, update PROGRESS.md:
# - Set PR 8 status to ✅ Done
# - Fill commit hash: git log -1 --format="%H"
# - Fill accuracy benchmark results in Accuracy Benchmarks table
```

---

## Prompt (paste into AI coding agent)

```
You are implementing Phase 11 of the Graphify fork enhancement plan — Hybrid Search (BM25 + Semantic + RRF).

Repository: ~/graphify
Branch: feat/phase-11-hybrid-search

TASK: Build BM25 keyword search, semantic embeddings, reciprocal rank fusion, and process-grouped results. Replace default query mode from BFS to hybrid.

## PART A: BM25 Index (graphify/search/bm25.py)

Create graphify/search/bm25.py with class BM25Index:

1. BM25Index(k1=1.5, b=0.75): Standard BM25 parameters.
2. _tokenize(text) → list[str]: Lowercase alphanumeric tokens.
3. add_document(doc_id, text): Tokenize text, update inverted index, doc lengths, avg length, total_docs.
4. remove_document(doc_id): Remove from index (for incremental updates).
5. search(query, top_k=20) → list[tuple[str, float]]: Compute BM25 score for each matching doc. Return ranked results.
6. index_from_graph(G): Iterate all graph nodes. For each node, create searchable text from: label + signature + docstring + source_file. Add to index.

## PART B: Semantic Embeddings (graphify/search/embeddings.py)

7. EMBEDDING_DIM = 384 constant.

8. generate_embedding(text, dimensions=384, seed=42) → list[float]:
   - Deterministic via hashlib.sha256 of text → seed for random projection.
   - L2 normalize. Use numpy if available, otherwise pure Python fallback with random module.
   - Same text always produces same embedding.

9. node_embedding_text(node_data) → str: Concat label + signature + docstring.

10. generate_embeddings(G) → dict[str, list[float]]: For all code-type nodes, generate embedding. Skip FILE/CONCEPT/UNKNOWN types.

11. compute_cosine(a, b) → float: Pure Python cosine similarity.

12. search_by_embedding(query_text, embeddings, top_k=20) → list[tuple[str, float]]: Embed query, compute cosine against all, return top-k.

13. save_embeddings(embeddings, output_dir): Shard into batches of 10000. JSON files.

14. load_embeddings(input_dir) → dict: Load and merge shards.

## PART C: Reciprocal Rank Fusion (graphify/search/fusion.py)

15. reciprocal_rank_fusion(result_sets, k=60) → list[tuple[str, float]]:
    - result_sets: list of [(doc_id, score), ...] from different search methods.
    - For each doc, RRF_score = sum(1 / (k + rank_in_list)).
    - Returns merged and sorted by RRF_score descending.

16. normalize_ranks(results) → dict[str, int]: Convert to rank mapping (1-indexed).

## PART D: Process-Grouped Results (graphify/search/grouping.py)

17. GroupedSearchResult dataclass with: process_id, process_name, summary, priority, symbol_count, process_type, step_count, definitions, references.

18. group_results_by_process(ranked_results, G, processes) → list[GroupedSearchResult]:
    - For each process, find which ranked results belong to it (by node membership).
    - Compute priority = avg_match_score * (matching_symbols / total_process_steps).
    - Sort processes by priority.

19. format_grouped_results(grouped) → str: Human-readable text for MCP response.

## PART E: Hybrid Search Orchestrator (graphify/search/hybrid.py)

20. hybrid_search(G, query, bm25_index, embeddings, processes, top_k) → list[GroupedSearchResult]:
    Pipeline: BM25 search → embedding search → RRF merge → process grouping → format.

## PART F: Integration

21. In serve.py, update _tool_query_graph:
    - Change default mode to "hybrid".
    - In hybrid mode, use hybrid_search from the search module.
    - Keep bfs/dfs/bidirectional/astar modes as before.
    - Load BM25 index and embeddings lazily on first query.

22. In serve.py, add new `query` MCP tool (alias for query_graph with hybrid default). Input schema same as query_graph but mode defaults to "hybrid". Use hybrid_search pipeline.

23. In build.py, add generate_embeddings parameter. If True, call search.embeddings.generate_embeddings() + save_embeddings().

## PART G: Tests

24. tests/test_search_bm25.py: 5 tests
25. tests/test_search_embeddings.py: 5 tests
26. tests/test_search_fusion.py: 4 tests
27. tests/test_search_grouping.py: 3 tests
28. tests/fixtures/search_judgments.json: Sample relevance judgments (5+ queries with known relevant nodes) for benchmark_search_relevance tests

MATCH EXISTING CODE STYLE. Package graphify/search/ needs __init__.py (can be empty or re-export key functions).

Numpy is OPTIONAL. All embedding logic works with pure Python fallback.

RUN `pytest tests/ -q` after implementation. All existing tests must pass.

ADD benchmark_search_latency(G, bm25, embeddings) and benchmark_search_overlap(bm25, semantic) to graphify/benchmark.py. Measure BM25 vs semantic vs hybrid latency and RRF fusion effectiveness.

ADD benchmark_search_relevance(G, bm25, embeddings, judgments, ks=[5,10,20]) and load_relevance_judgments(path) to graphify/benchmark.py. Measure precision@k, recall@k, NDCG@k against ground truth judgments for all three search methods. Create a sample judgments file at test/fixtures/search_judgments.json for testing.

RUN `git add -A && git commit -m "feat(phase-11): hybrid search (BM25 + semantic + RRF)"`
```
