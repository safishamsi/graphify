# Case Study: rsl-siege-manager (Python + TypeScript monorepo)

A graphify dry-run against [`glitchwerks/rsl-siege-manager`](https://github.com/glitchwerks/rsl-siege-manager) — a real-world web app with a Python (FastAPI) backend, a TypeScript (React + Vite) frontend, and a Python Discord bot, all in one repo. Captured here as a worked example of running graphify on a mixed-language full-stack codebase that includes a substantial test suite.

**Corpus:** `glitchwerks/rsl-siege-manager` @ commit `6085fd66`
**Date:** 2026-05-15
**Findings:** [`review.md`](./review.md)
**Raw artifacts:** [`GRAPH_REPORT.md`](./GRAPH_REPORT.md), [`graph.html`](./graph.html), [`graph.json`](./graph.json), [`manifest.json`](./manifest.json)

## How to reproduce

### 1. Clone the corpus

```bash
git clone https://github.com/glitchwerks/rsl-siege-manager
cd rsl-siege-manager
git checkout 6085fd66
```

### 2. Install the CLI

```powershell
uv tool install graphifyy
```

> The PyPI package is `graphifyy` (double-y). The CLI command is `graphify`.

Verify it's on PATH:

```powershell
graphify --version
```

If "not recognized" on Windows, open a new shell — `uv tool` updates PATH but the current session won't see it.

### 3. Run extraction

This case study ran extraction with no `.graphifyignore` (the run included tests). To reproduce a tests-included run:

```powershell
graphify extract .
```

Watch terminal output. graphify uses tree-sitter for code (free, fast) and LLM API calls only for non-code files (markdown, PDFs, images). On a code-heavy repo like rsl-siege-manager, the cost is dominated by docs.

Check the cost summary when it finishes:

```powershell
Get-Content .\graphify-out\cost.json
```

### 4. Inspect

```powershell
# The headline summary an assistant would read
code .\graphify-out\GRAPH_REPORT.md

# The interactive graph
Start-Process .\graphify-out\graph.html
```

## What's in this directory

| File | What it is |
|---|---|
| `README.md` | This file — corpus description + reproduction steps |
| `review.md` | Findings against the headline outputs in `GRAPH_REPORT.md` |
| `GRAPH_REPORT.md` | Raw graphify report (god nodes, communities, surprising connections, suggested questions) |
| `graph.html` | Interactive force-directed visualization |
| `graph.json` | Underlying graph data used by `graphify query` |
| `manifest.json` | Per-file extraction record |

The AST cache (`graphify-out/cache/`) is regenerable and not committed.

## Why this corpus

rsl-siege-manager is structurally interesting for graphify evaluation because:

- **Three services in one repo** — Python backend, TypeScript frontend, Python bot — exercises cross-language inference.
- **Substantial test suite** — both Python (`backend/tests/`) and TypeScript (`frontend/src/**/__tests__/`) — surfaces how degree-centrality behaves on covered codebases.
- **17 Alembic migrations** with revision docstrings — exercises how docstring-shaped content is or is not treated as graph entities.
- **Clean three-tier architecture** — a developer can describe the structure in one sentence, giving a clear ground truth to evaluate community detection against.

## Reference

- graphify repo: https://github.com/safishamsi/graphify
- graphify PyPI: https://pypi.org/project/graphifyy/
- rsl-siege-manager: https://github.com/glitchwerks/rsl-siege-manager
