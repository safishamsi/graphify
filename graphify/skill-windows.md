---
name: graphify-windows
description: "any input (code, docs, papers, images) → knowledge graph → clustered communities → HTML + JSON + audit report. Use when user asks any question about a codebase, project content, architecture, or file relationships — especially if graphify-out/ exists. Provides persistent graph with god nodes, community detection, and BFS/DFS query tools."
trigger: /graphify
---

# /graphify (Windows)

Turn any folder of files into a navigable knowledge graph with community detection, an honest audit trail, and three outputs: interactive HTML, GraphRAG-ready JSON, and a plain-language GRAPH_REPORT.md.

## Usage

```powershell
/graphify                                             # full pipeline on current directory → Obsidian vault
/graphify <path>                                      # full pipeline on specific path
/graphify <path> --mode deep                          # thorough extraction, richer INFERRED edges
/graphify <path> --update                             # incremental - re-extract only new/changed files
/graphify <path> --cluster-only                       # rerun clustering on existing graph
/graphify <path> --no-viz                             # skip visualization, just report + JSON
/graphify query "<question>"                          # BFS traversal - broad context
```

## Modular Instructions
To keep sessions efficient, this skill is modularized. Read the relevant file in this directory before performing a task:

1.  **Build/Extract/Analyze:** Read `build-win.md` for Step 0 through Step 5B.
2.  **Query/Navigate/Update:** Read `interact-win.md` for queries and updates.
3.  **Export/Obsidian/HTML:** Read `export.md` for Step 6 through Step 9.
4.  **Rules:** Read `rules.md` for global constraints and honesty rules.

## Quick Start: Build Pipeline
If you are building a new graph or updating an existing one, first ensure the environment is set up:

```powershell
# Detect Python and install graphify if needed
@'
import graphify
'@ | Out-File -FilePath .graphify_step_1_ensure_graphify_is_installed_1.py -Encoding utf8
python .graphify_step_1_ensure_graphify_is_installed_1.py 2>$null
Remove-Item -ErrorAction SilentlyContinue .graphify_step_1_ensure_graphify_is_installed_1.py
if ($LASTEXITCODE -ne 0) { pip install graphifyy -q 2>&1 | Select-Object -Last 3 }
# Write interpreter path for all subsequent steps
mkdir -p graphify-out
@'
import sys; open('graphify-out/.graphify_python', 'w').write(sys.executable)
'@ | Out-File -FilePath .graphify_step_1_ensure_graphify_is_installed_2.py -Encoding utf8
python .graphify_step_1_ensure_graphify_is_installed_2.py
Remove-Item -ErrorAction SilentlyContinue .graphify_step_1_ensure_graphify_is_installed_2.py
```

Then read **`build-win.md`** to continue with file detection and extraction.

## Global Rules
- Always read `rules.md` before finalizing any report or answering queries.
- Never invent edges; use AMBIGUOUS if unsure.
