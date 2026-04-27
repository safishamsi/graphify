---
name: graphify
description: any input (code, docs, papers, images) → knowledge graph → clustered communities → HTML + JSON + audit report
trigger: /graphify
---

# /graphify

Turn any folder of files into a navigable knowledge graph with community detection, an honest audit trail, and three outputs: interactive HTML, GraphRAG-ready JSON, and a plain-language GRAPH_REPORT.md.

## Usage

```
/graphify                     # full pipeline on current directory
/graphify <path>              # full pipeline on specific path
/graphify <path> --update     # incremental - re-extract only new/changed files
/graphify <path> --no-viz     # skip visualization, just report + JSON
/graphify <path> --wiki       # build agent-crawlable wiki
/graphify query "<question>"  # BFS traversal - broad context
```

## What You Must Do When Invoked

If no path was given, use `.` (current directory). Do not ask the user for a path.

Follow these steps in order. Do not skip steps.

**All commands use `python -c "..."` syntax — no bash heredocs, no shell redirects, no `&&`/`||`. This runs correctly on Windows PowerShell and macOS/Linux alike.**

### Step 1 - Ensure graphify is installed

```python
python -c "import graphify; import sys; from pathlib import Path; Path('graphify-out').mkdir(exist_ok=True); Path('graphify-out/.graphify_python').write_text(sys.executable)"
```

If the import fails, install first:

```python
python -m pip install graphifyy -q
```

Then re-run the Step 1 command.

### Step 2 - Detect files

```python
python -c "
import json, sys
from graphify.detect import detect
from pathlib import Path

result = detect(Path('INPUT_PATH'))
Path('graphify-out/.graphify_detect.json').write_text(json.dumps(result, indent=2))
total = result.get('total_files', 0)
words = result.get('total_words', 0)
print(f'Corpus: {total} files, ~{words} words')
for ftype, files in result.get('files', {}).items():
    if files:
        print(f'  {ftype}: {len(files)} files')
"
```

Replace `INPUT_PATH` with the actual path. Present a clean summary — do not dump the raw JSON.

- If `total_files` is 0: stop with "No supported files found in [path]."
- If `total_words` > 2,000,000 OR `total_files` > 200: warn the user and ask which subfolder to run on.
- Otherwise: proceed to Step 3.

### Step 3 - Extract entities and relationships

#### Part A - Structural extraction (AST, free, no API cost)

```python
python -c "
import json
from graphify.extract import collect_files, extract
from pathlib import Path

detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text())
code_files = []
for f in detect.get('files', {}).get('code', []):
    p = Path(f)
    code_files.extend(collect_files(p) if p.is_dir() else [p])

if code_files:
    result = extract(code_files)
    Path('graphify-out/.graphify_ast.json').write_text(json.dumps(result, indent=2))
    print(f'AST: {len(result[\"nodes\"])} nodes, {len(result[\"edges\"])} edges')
else:
    Path('graphify-out/.graphify_ast.json').write_text(json.dumps({'nodes':[],'edges':[],'input_tokens':0,'output_tokens':0}))
    print('No code files - skipping AST extraction')
"
```

#### Part B - Semantic extraction (AI, costs tokens)

Skip if corpus is code-only (no docs, papers, or images).

Check cache first:

```python
python -c "
import json
from graphify.cache import check_semantic_cache
from pathlib import Path

detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text())
all_files = [f for files in detect['files'].values() for f in files]
cached_nodes, cached_edges, cached_hyperedges, uncached = check_semantic_cache(all_files)

if cached_nodes or cached_edges:
    Path('graphify-out/.graphify_cached.json').write_text(json.dumps({'nodes': cached_nodes, 'edges': cached_edges, 'hyperedges': cached_hyperedges}))
Path('graphify-out/.graphify_uncached.txt').write_text('\n'.join(uncached))
print(f'Cache: {len(all_files)-len(uncached)} hit, {len(uncached)} need extraction')
"
```

For each chunk of uncached files (20-25 files per chunk), dispatch a subagent with this prompt:

```
You are a graphify extraction subagent. Read the files listed and extract a knowledge graph fragment.
Output ONLY valid JSON: {"nodes": [...], "edges": [...], "hyperedges": [...]}

Each node: {"id": "unique_id", "label": "Human Name", "file_type": "code|document|paper|image"}
Each edge: {"source": "id", "target": "id", "relation": "verb_phrase", "confidence": "EXTRACTED|INFERRED|AMBIGUOUS"}
hyperedges: [] unless you find a genuine group relationship

Files:
FILE_LIST
```

Collect all subagent responses and merge them:

```python
python -c "
import json
from pathlib import Path

# Merge: combine AST + cached + all semantic chunk results
all_nodes, all_edges, all_hyperedges = [], [], []

ast = json.loads(Path('graphify-out/.graphify_ast.json').read_text())
all_nodes.extend(ast.get('nodes', []))
all_edges.extend(ast.get('edges', []))

cached_path = Path('graphify-out/.graphify_cached.json')
if cached_path.exists():
    cached = json.loads(cached_path.read_text())
    all_nodes.extend(cached.get('nodes', []))
    all_edges.extend(cached.get('edges', []))
    all_hyperedges.extend(cached.get('hyperedges', []))

# PASTE each subagent response here as chunk_1, chunk_2, etc.
for chunk_json in []:  # replace [] with your chunk results
    chunk = json.loads(chunk_json) if isinstance(chunk_json, str) else chunk_json
    all_nodes.extend(chunk.get('nodes', []))
    all_edges.extend(chunk.get('edges', []))
    all_hyperedges.extend(chunk.get('hyperedges', []))

merged = {'nodes': all_nodes, 'edges': all_edges, 'hyperedges': all_hyperedges, 'input_tokens': 0, 'output_tokens': 0}
Path('graphify-out/.graphify_extract.json').write_text(json.dumps(merged, indent=2))
print(f'Merged: {len(all_nodes)} nodes, {len(all_edges)} edges')
"
```

### Step 4 - Build graph and cluster

```python
python -c "
import json
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.analyze import god_nodes, surprising_connections
from pathlib import Path

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
G = build_from_json(extraction)
communities = cluster(G)
gods = god_nodes(G)
surprises = surprising_connections(G, communities)

import networkx as nx
from networkx.readwrite import json_graph
graph_data = json_graph.node_link_data(G)
Path('graphify-out/graph.json').write_text(json.dumps(graph_data, indent=2))
Path('graphify-out/.graphify_analysis.json').write_text(json.dumps({
    'communities': {str(k): v for k, v in communities.items()},
    'cohesion': {},
    'god_nodes': gods,
    'surprises': surprises,
}, indent=2))
print(f'Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities')
print(f'God nodes: {[g[\"label\"] for g in gods[:5]]}')
"
```

### Step 5 - Generate report and visualization

```python
python -c "
import json
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.analyze import god_nodes, surprising_connections
from graphify.report import generate
from pathlib import Path

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
analysis = json.loads(Path('graphify-out/.graphify_analysis.json').read_text())

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}
gods = god_nodes(G)
surprises = surprising_connections(G, communities)

report = generate(G, communities, {}, {}, gods, surprises, extraction)
Path('graphify-out/GRAPH_REPORT.md').write_text(report)
print('GRAPH_REPORT.md written')
"
```

```python
python -c "
import json
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import to_html
from pathlib import Path

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
G = build_from_json(extraction)
communities = cluster(G)

try:
    to_html(G, communities, 'graphify-out/graph.html')
    print('graph.html written')
except ValueError as e:
    print(f'Visualization skipped: {e}')
"
```

### After completing all steps

Print this summary:

```
graphify complete
  graph.json      — GraphRAG-ready, queryable by MCP or CLI
  graph.html      — interactive visualization (open in browser)
  GRAPH_REPORT.md — plain-language architecture summary
```

Read `graphify-out/GRAPH_REPORT.md` and share the **God Nodes** and **Surprising Connections** sections directly in the chat — do not ask the user to open the file themselves.
