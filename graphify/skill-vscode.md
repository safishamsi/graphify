---
name: graphify
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

```python
import sys
from pathlib import Path
mkdir -p graphify-out
Path('graphify-out/.graphify_python').write_text(sys.executable)
```

Then read **`build.md`** to continue with file detection and extraction.

## Global Rules
- Always read `rules.md` before finalizing any report or answering queries.
- Never invent edges; use AMBIGUOUS if unsure.
