---
name: aag-copilot
description: "any input (code, docs, papers, images) → knowledge graph → clustered communities → HTML + JSON + audit report. Use when user asks any question about a codebase, project content, architecture, or file relationships — especially if graphify-out/ exists. Provides persistent graph with god nodes, community detection, and BFS/DFS query tools."
trigger: /graphify
---

# /graphify

Turn any folder of files into a navigable knowledge graph with community detection, an honest audit trail, and three outputs: interactive HTML, GraphRAG-ready JSON, and a plain-language GRAPH_REPORT.md.

## Modular Instructions
To keep sessions efficient, this skill is modularized. Read the relevant file in this directory before performing a task:

1.  **Build/Extract/Analyze:** Read `build.md` for Step 0 through Step 5B.
2.  **Query/Navigate/Update:** Read `interact.md` for queries and updates.
3.  **Export/Obsidian/HTML:** Read `export.md` for Step 6 through Step 9.
4.  **Rules:** Read `rules.md` for global constraints and honesty rules.

## Quick Start: Build Pipeline

```bash
# Find a Python that can import graphify
PYTHON=""
if python3 -c "import graphify" 2>/dev/null; then
    PYTHON="python3"
fi
if [ -z "$PYTHON" ] && command -v uv >/dev/null 2>&1; then
    _UV_PY=$(uv tool run graphifyy python -c "import sys; print(sys.executable)" 2>/dev/null)
    if [ -n "$_UV_PY" ]; then PYTHON="$_UV_PY"; fi
fi
if [ -z "$PYTHON" ]; then
    PYTHON="python3"
    "$PYTHON" -m pip install graphifyy -q 2>/dev/null
fi
mkdir -p graphify-out
echo "$PYTHON" > graphify-out/.graphify_python
```

Then read **`build.md`** to continue with file detection and extraction.

## Global Rules
- Always read `rules.md` before finalizing any report or answering queries.
- Never invent edges; use AMBIGUOUS if unsure.
