---
name: aag
description: "any input (code, docs, papers, images, videos) to knowledge graph. Use when user asks any question about a codebase, documents, or project content - especially if graphify-out/ exists, treat the question as a /aag query."
trigger: /aag
---

# /aag

Turn any folder of files into a navigable knowledge graph with community detection, an honest audit trail, and interactive dashboard.

## Usage

```
/aag                                             # full pipeline on current directory
/aag <path>                                      # full pipeline on specific path
/aag query "<question>"                          # BFS traversal - broad context
/aag path "AuthModule" "Database"                # shortest path between two concepts
/aag explain "SwinTransformer"                   # plain-language explanation of a node
/aag --update                             # incremental - re-extract only new/changed files
/aag --cluster-only                       # rerun clustering on existing graph
/aag --watch                              # watch folder, auto-rebuild on code changes
```

## Modular Instructions
To keep sessions efficient, this skill is modularized. Read the relevant file in this directory before performing a task:

1.  **Build/Extract/Analyze:** Read `build.md` for Step 0 through Step 5B.
2.  **Query/Navigate/Update:** Read `interact.md` for `/aag query`, `/aag path`, `/aag explain`, `/aag add`, and `--update`.
3.  **Export/Obsidian/HTML:** Read `export.md` for Step 6 through Step 9.
4.  **Rules:** Read `rules.md` for global constraints and honesty rules.

## Quick Start: Build Pipeline
If you are building a new graph or updating an existing one, first ensure the environment is set up:

```bash
# Ensure aag is installed and get python path
PYTHON=$(aag python-path) || PYTHON="python3"
mkdir -p graphify-out
echo "$PYTHON" > graphify-out/.aag_python
```

Then read **`build.md`** to continue with file detection and extraction.

## Global Rules
- Always read `rules.md` before finalizing any report or answering queries.
- Never invent edges; use AMBIGUOUS if unsure.
