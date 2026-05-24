---
name: graphify
description: any input (code, docs, papers, images) -> knowledge graph -> clustered communities -> HTML + JSON + audit report
trigger: /graphify
---

# /graphify

Turn any folder of files into a navigable knowledge graph with community detection, an honest audit trail, and three outputs: interactive HTML, GraphRAG-ready JSON, and a plain-language `GRAPH_REPORT.md`.

## Usage

```text
/graphify
/graphify <path>
/graphify <path> --mode deep
/graphify <path> --update
/graphify <path> --cluster-only
/graphify <path> --no-viz
/graphify add <url>
/graphify query "<question>"
/graphify path "AuthModule" "Database"
/graphify explain "SwinTransformer"
```

## What You Must Do When Invoked

If no path was given, use `.`. Do not ask the user for a path.

Follow these steps in order. Do not skip steps.

### Step 1 - Ensure graphify is installed

```bash
# Detect the correct Python interpreter (handles pipx, venv, system installs)
GRAPHIFY_BIN=$(which graphify 2>/dev/null)
if [ -n "$GRAPHIFY_BIN" ]; then
    PYTHON=$(head -1 "$GRAPHIFY_BIN" | tr -d '#!')
    case "$PYTHON" in
        *[!a-zA-Z0-9/_.-]*) PYTHON="python3" ;;
    esac
else
    PYTHON="python3"
fi
"$PYTHON" -c "import graphify" 2>/dev/null || "$PYTHON" -m pip install graphifyy -q 2>/dev/null || "$PYTHON" -m pip install graphifyy -q --break-system-packages 2>&1 | tail -3
mkdir -p graphify-out
"$PYTHON" -c "import sys; open('graphify-out/.graphify_python', 'w').write(sys.executable)"
```

If the import succeeds, print nothing and move straight to Step 2.

**In every later bash block, replace `python3` with `$(cat graphify-out/.graphify_python)` to reuse the correct interpreter.**

### Step 2 - Detect files

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from graphify.detect import detect
from pathlib import Path

result = detect(Path('INPUT_PATH'))
print(json.dumps(result))
" > graphify-out/.graphify_detect.json
```

Replace `INPUT_PATH` with the actual path the user provided. Do not dump the JSON to the user. Read it silently and present a clean summary instead:

```text
Corpus: X files · ~Y words
  code:     N files
  docs:     N files
  papers:   N files
  images:   N files
  video:    N files
```

Omit any category with 0 files.

Then act on it:

- If `total_files` is 0: stop with `No supported files found in [path].`
- If `skipped_sensitive` is non-empty: mention the count skipped, not the filenames.
- If `total_words > 2_000_000` or `total_files > 200`: show the warning and ask which subfolder to run on.
- Otherwise continue directly to Step 2.5 if video files were detected, or Step 3 if not.

### Step 2.5 - Transcribe video or audio files (only if video files were detected)

Skip this step entirely if detection found zero `video` files.

Transcribe the files first, then treat the transcripts as docs during semantic extraction.

Write a one-sentence Whisper prompt yourself from the top graph labels. If the corpus only contains video, use `Use proper punctuation and paragraph breaks.`

```bash
$(cat graphify-out/.graphify_python) -c "
import json, os
from pathlib import Path
from graphify.transcribe import transcribe_all

detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text())
video_files = detect.get('files', {}).get('video', [])
prompt = os.environ.get('GRAPHIFY_WHISPER_PROMPT', 'Use proper punctuation and paragraph breaks.')

transcript_paths = transcribe_all(video_files, initial_prompt=prompt)
print(json.dumps(transcript_paths))
" > graphify-out/.graphify_transcripts.json
```

After transcription:

- Read the transcript paths from `graphify-out/.graphify_transcripts.json`
- Add them to the docs list before semantic extraction
- Print `Transcribed N video file(s) -> treating as docs`
- If a file fails, warn and continue with the rest

### Step 3 - Extract entities and relationships

Track whether `--mode deep` was given. Pass that through to every semantic extraction task.

This step has two parts: deterministic AST extraction for code and semantic extraction for docs, papers, and images.

#### Part A - Structural extraction for code files

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from graphify.extract import collect_files, extract
from pathlib import Path

code_files = []
detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text())
for f in detect.get('files', {}).get('code', []):
    code_files.extend(collect_files(Path(f)) if Path(f).is_dir() else [Path(f)])

if code_files:
    result = extract(code_files, cache_root=Path('.'))
    Path('graphify-out/.graphify_ast.json').write_text(json.dumps(result, indent=2))
    print('AST: {} nodes, {} edges'.format(len(result['nodes']), len(result['edges'])))
else:
    Path('graphify-out/.graphify_ast.json').write_text(json.dumps({'nodes': [], 'edges': [], 'input_tokens': 0, 'output_tokens': 0}))
    print('No code files - skipping AST extraction')
"
```

#### Part B - Semantic extraction for docs, papers, and images

If detection found zero docs, papers, and images, skip this part and go straight to Part C.

**You must use the native `Task` tool here.** Reading files sequentially yourself is too slow and defeats the purpose of the Kilo integration.

Before dispatching tasks, check the semantic cache first:

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from graphify.cache import check_semantic_cache
from pathlib import Path

detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text())
all_files = [f for files in detect['files'].values() for f in files]

cached_nodes, cached_edges, cached_hyperedges, uncached = check_semantic_cache(all_files)

if cached_nodes or cached_edges or cached_hyperedges:
    Path('graphify-out/.graphify_cached.json').write_text(json.dumps({'nodes': cached_nodes, 'edges': cached_edges, 'hyperedges': cached_hyperedges}))
Path('graphify-out/.graphify_uncached.txt').write_text('\n'.join(uncached))
print(f'Cache: {len(all_files) - len(uncached)} files hit, {len(uncached)} files need extraction')
"
```

If every file is cached, skip directly to Part C.

Split `graphify-out/.graphify_uncached.txt` into chunks of 20-25 files, grouping related directories together. Each image should get its own chunk.

Dispatch **all** chunk tasks in the same response so they run in parallel. Always use `subagent_type="general"`.

Each task should receive a prompt like this, with the placeholders replaced:

```text
You are a graphify extraction subagent. Read the files listed and extract a knowledge graph fragment.
Output ONLY valid JSON matching the schema below.

Files (chunk CHUNK_NUM of TOTAL_CHUNKS):
FILE_LIST

Rules:
- EXTRACTED: relationship explicit in source
- INFERRED: reasonable inference
- AMBIGUOUS: uncertain, flag it instead of omitting it
- Code files: focus on semantic edges AST cannot find
- Doc and paper files: extract concepts, citations, and rationale nodes
- Image files: use vision to understand the artifact, not just OCR
- If DEEP_MODE is true, be more aggressive with INFERRED edges
- Include `confidence_score` on every edge

Write the result to `graphify-out/.graphify_chunk_CHUNK_NUM.json` and also return the same JSON.

Schema:
{"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
```

After all tasks finish, merge them into `graphify-out/.graphify_semantic_new.json`. Track the chunk filenames yourself and substitute them below.

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from pathlib import Path

chunk_files = CHUNK_FILES
combined = {'nodes': [], 'edges': [], 'hyperedges': [], 'input_tokens': 0, 'output_tokens': 0}
failures = 0

for chunk_file in chunk_files:
    path = Path(chunk_file)
    if not path.exists():
        failures += 1
        continue
    try:
        data = json.loads(path.read_text())
    except Exception:
        failures += 1
        continue
    combined['nodes'].extend(data.get('nodes', []))
    combined['edges'].extend(data.get('edges', []))
    combined['hyperedges'].extend(data.get('hyperedges', []))
    combined['input_tokens'] += data.get('input_tokens', 0)
    combined['output_tokens'] += data.get('output_tokens', 0)

Path('graphify-out/.graphify_semantic_new.json').write_text(json.dumps(combined, indent=2))
print('Semantic extraction: {} nodes, {} edges, {} failed chunk(s)'.format(len(combined['nodes']), len(combined['edges']), failures))
"
```

If more than half the chunk tasks fail, stop and report the failure instead of silently continuing.

Cache the new semantic results and merge them with cached data:

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from graphify.cache import save_semantic_cache
from pathlib import Path

new = json.loads(Path('graphify-out/.graphify_semantic_new.json').read_text()) if Path('graphify-out/.graphify_semantic_new.json').exists() else {'nodes': [], 'edges': [], 'hyperedges': []}
save_semantic_cache(new.get('nodes', []), new.get('edges', []), new.get('hyperedges', []))

cached = json.loads(Path('graphify-out/.graphify_cached.json').read_text()) if Path('graphify-out/.graphify_cached.json').exists() else {'nodes': [], 'edges': [], 'hyperedges': []}

all_nodes = cached.get('nodes', []) + new.get('nodes', [])
all_edges = cached.get('edges', []) + new.get('edges', [])
all_hyperedges = cached.get('hyperedges', []) + new.get('hyperedges', [])

seen = set()
deduped_nodes = []
for node in all_nodes:
    node_id = node.get('id')
    if node_id and node_id not in seen:
        seen.add(node_id)
        deduped_nodes.append(node)

merged = {
    'nodes': deduped_nodes,
    'edges': all_edges,
    'hyperedges': all_hyperedges,
    'input_tokens': new.get('input_tokens', 0),
    'output_tokens': new.get('output_tokens', 0),
}
Path('graphify-out/.graphify_semantic.json').write_text(json.dumps(merged, indent=2))
print(f'Semantic merge complete - {len(deduped_nodes)} nodes, {len(all_edges)} edges')
"
```

#### Part C - Merge AST and semantic extraction

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from pathlib import Path

ast = json.loads(Path('graphify-out/.graphify_ast.json').read_text())
sem = json.loads(Path('graphify-out/.graphify_semantic.json').read_text()) if Path('graphify-out/.graphify_semantic.json').exists() else {'nodes': [], 'edges': [], 'hyperedges': [], 'input_tokens': 0, 'output_tokens': 0}

seen = {n['id'] for n in ast['nodes']}
merged_nodes = list(ast['nodes'])
for node in sem.get('nodes', []):
    if node['id'] not in seen:
        merged_nodes.append(node)
        seen.add(node['id'])

merged = {
    'nodes': merged_nodes,
    'edges': ast['edges'] + sem.get('edges', []),
    'hyperedges': sem.get('hyperedges', []),
    'input_tokens': sem.get('input_tokens', 0),
    'output_tokens': sem.get('output_tokens', 0),
}
Path('graphify-out/.graphify_extract.json').write_text(json.dumps(merged, indent=2))
print('Merged extraction: {} nodes, {} edges'.format(len(merged_nodes), len(merged['edges'])))
"
```

### Step 4 - Build the graph and generate outputs

Use generic labels like `Community 0`, `Community 1`, and so on. Do not stop to ask for manual labels.

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from pathlib import Path
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json, to_html

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
detection = json.loads(Path('graphify-out/.graphify_detect.json').read_text())

G = build_from_json(extraction)
communities = cluster(G)
cohesion = score_all(G, communities)
labels = {cid: f'Community {cid}' for cid in communities}
gods = god_nodes(G)
surprises = surprising_connections(G, communities)
questions = suggest_questions(G, communities, labels)
tokens = {'input': extraction.get('input_tokens', 0), 'output': extraction.get('output_tokens', 0)}

report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, 'INPUT_PATH', suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report, encoding='utf-8')
to_json(G, communities, 'graphify-out/graph.json')
Path('graphify-out/.graphify_analysis.json').write_text(json.dumps({'questions': questions, 'gods': gods, 'surprises': surprises, 'labels': labels}, indent=2), encoding='utf-8')

if G.number_of_nodes() == 0:
    print('ERROR: Graph is empty - extraction produced no nodes.')
    raise SystemExit(1)

if 'NO_VIZ' != 'true' and G.number_of_nodes() <= 5000:
    to_html(G, communities, 'graphify-out/graph.html', community_labels=labels)

print(f'Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities')
"
```

Replace `INPUT_PATH` with the actual path. Replace `NO_VIZ` with `true` if `--no-viz` was given, otherwise `false`.

If the graph is empty, stop and report the failure.

### Step 5 - Save manifest, clean up, and report

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from pathlib import Path
from datetime import datetime, timezone
from graphify.detect import save_manifest

detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text())
save_manifest(detect['files'])

extract = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
input_tok = extract.get('input_tokens', 0)
output_tok = extract.get('output_tokens', 0)

cost_path = Path('graphify-out/cost.json')
cost = json.loads(cost_path.read_text()) if cost_path.exists() else {'runs': [], 'total_input_tokens': 0, 'total_output_tokens': 0}
cost['runs'].append({'date': datetime.now(timezone.utc).isoformat(), 'input_tokens': input_tok, 'output_tokens': output_tok, 'files': detect.get('total_files', 0)})
cost['total_input_tokens'] += input_tok
cost['total_output_tokens'] += output_tok
cost_path.write_text(json.dumps(cost, indent=2), encoding='utf-8')

print(f'This run: {input_tok:,} input tokens, {output_tok:,} output tokens')
"
rm -f graphify-out/.graphify_cached.json graphify-out/.graphify_uncached.txt graphify-out/.graphify_semantic_new.json graphify-out/.graphify_ast.json graphify-out/.graphify_semantic.json graphify-out/.graphify_extract.json
```

Tell the user where the outputs were written:

```text
Graph complete. Outputs in PATH_TO_DIR/graphify-out/

  graph.html            - interactive graph, open in browser
  GRAPH_REPORT.md       - audit report
  graph.json            - raw graph data
```

Then summarize the god nodes, surprising connections, and suggested questions from `GRAPH_REPORT.md` without pasting the entire report.

### Query mode

Before any query-style subcommand, ensure `graphify-out/.graphify_python` exists. If not, recreate it using the Step 1 interpreter detection.

When the user invokes one of these forms, use the CLI directly instead of rebuilding the graph:

- `/graphify query "..."`
- `/graphify path "A" "B"`
- `/graphify explain "X"`

Use:

```bash
$(cat graphify-out/.graphify_python) -m graphify query "QUESTION" --graph graphify-out/graph.json
$(cat graphify-out/.graphify_python) -m graphify path "SOURCE" "TARGET" --graph graphify-out/graph.json
$(cat graphify-out/.graphify_python) -m graphify explain "NODE" --graph graphify-out/graph.json
```

Prefer graph-backed answers over guesses, and cite source files when the graph provides them.

### Kilo-specific rules

- Use the native `Task` tool for semantic extraction fan-out.
- Launch all chunk tasks in the same response so they run in parallel.
- Always use `subagent_type="general"` for extraction chunks.
- After modifying code files during the session, run `graphify update .`.
