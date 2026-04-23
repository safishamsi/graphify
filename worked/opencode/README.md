# opencode — TypeScript AI Coding Assistant

Real production TypeScript + TSX codebase (not a synthetic example).

## Corpus

**Source:** https://github.com/opencode-ai/opencode — `packages/opencode/src/`  
**Commit:** `dev` branch, April 2026  
**Files:** 406 TypeScript / TSX / JavaScript files  
**Words:** ~88,600 (source code only, no docs)  
**Extraction:** AST only (tree-sitter, no LLM) — `graphify update packages/opencode/src`

## How to run

```bash
git clone https://github.com/opencode-ai/opencode
pip install graphifyy
graphify update opencode/packages/opencode/src
```

## What to expect

- ~1,772 nodes, ~2,958 edges (66% EXTRACTED, 34% INFERRED)
- 213 communities detected — 38 real, 175 single-file isolates
- God nodes: all generic method names (`push`, `get`, `set`, `info`, `trim`) — not useful
- Token reduction: **12.6x** on this corpus vs naive full-context

Actual output is in this folder: `GRAPH_REPORT.md` and `graph.json`.  
Full honest evaluation with scores and specific bugs found: `review.md`.
