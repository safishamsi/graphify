# How graphify works

## The three passes

graphify processes your files in three passes:

**Pass 1 — Code structure (free, no API calls)**
Tree-sitter parses your code files and extracts classes, functions, imports, call graphs, and inline comments. This runs locally with no LLM involved. 25 languages supported. SQL files get special treatment: tables, views, foreign keys, and JOIN relationships are extracted deterministically.

**Pass 2 — Video and audio (local, no API calls)**
Video and audio files are transcribed with faster-whisper. To focus the transcript on your domain, the transcription prompt is seeded with your top god nodes (the most-connected concepts in your code graph so far). Transcripts are cached — re-runs skip already-processed files.

**Pass 3 — Docs, papers, images (Claude subagents, costs tokens)**
Claude runs in parallel over markdown, PDFs, images, and transcripts. Each subagent reads a batch of files and outputs a JSON fragment: nodes, edges, and any group relationships. The fragments are merged into a single graph.

Before Pass 3, optional converters turn supported pointer/binary formats into
Markdown sidecars under `graphify-out/converted/`. Office files (`.docx`,
`.xlsx`) use the `[office]` extra. Google Workspace shortcuts (`.gdoc`,
`.gsheet`, `.gslides`) are opt-in with `--google-workspace` or
`GRAPHIFY_GOOGLE_WORKSPACE=1` and require an authenticated `gws` CLI.

---

## How community detection works

Communities are found using the [Leiden algorithm](https://www.nature.com/articles/s41598-019-41695-z) — a graph-clustering method that groups nodes by edge density. Nodes with many connections between them end up in the same community.

**No embeddings needed.** The semantic similarity edges that Claude extracts (`semantically_similar_to`) are already in the graph, so they influence community shape directly. The graph structure is the similarity signal — there's no separate embedding step or vector database.

---

## Confidence tagging

Every relationship is tagged with one of three labels:

| Tag | Meaning |
|-----|---------|
| `EXTRACTED` | Found directly in the source (e.g. a function call, an import) |
| `INFERRED` | A reasonable inference Claude made, with a `confidence_score` (0.0–1.0) |
| `AMBIGUOUS` | Uncertain — flagged in the report for manual review |

EXTRACTED edges always have confidence 1.0. INFERRED edges use a discrete rubric:
- **0.95** — near-certain (explicit cross-file reference, one plausible target)
- **0.85** — strong evidence (naming + context align)
- **0.75** — reasonable (contextual but not explicit)
- **0.65** — weak (naming similarity only)
- **0.55** — speculative

---

## Token benchmark

The first run extracts and builds the graph — this costs tokens. Every subsequent query reads the compact graph instead of raw files. That's where the savings compound.

On a mixed corpus (Karpathy repos + 5 papers + 4 images, 52 files): **71.5x fewer tokens per query** vs reading the raw files directly.

| Corpus | Files | Reduction |
|--------|-------|-----------|
| Karpathy repos + papers + images | 52 | **71.5x** |
| graphify source + Transformer paper | 4 | **5.4x** |
| httpx (synthetic Python library) | 6 | ~1x |

Token reduction scales with corpus size. Six files already fits in a context window — the graph value there is structural clarity, not compression. At 52 files the savings compound quickly.

Each `worked/` folder in the repo has the raw input files and actual output (`GRAPH_REPORT.md`, `graph.json`) so you can run it yourself and verify.

---

## Parallel extraction

Code files are extracted in parallel using `ProcessPoolExecutor` — bypasses Python's GIL for genuine multiprocessing. Doc/paper/image batches are dispatched as parallel Claude subagents. On a corpus of 84 code files, parallel AST extraction runs in about 1.66x less time than sequential.

---

## SHA256 cache

Every extracted file is fingerprinted by content hash. Re-runs skip unchanged files entirely — only new or modified files go through extraction again. The cache lives in `graphify-out/cache/`.

---

## The graph format

The output `graph.json` uses NetworkX's node-link format. Each node has:
- `id` — stable identifier
- `label` — human-readable name
- `file_type` — `code`, `document`, `paper`, `image`, `rationale`
- `source_file` — where it came from

Each edge has:
- `source`, `target` — node IDs
- `relation` — verb phrase (e.g. `calls`, `imports`, `implements`, `semantically_similar_to`)
- `confidence` — `EXTRACTED`, `INFERRED`, or `AMBIGUOUS`
- `confidence_score` — float (INFERRED only)
- `source_file` — where the relationship was found

Hyperedges (group relationships connecting 3+ nodes) live in `G.graph["hyperedges"]`.
