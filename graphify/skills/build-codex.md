### Step 0 - Clone GitHub repo(s) (only if a GitHub URL was given)

**Single repo:**
```bash
LOCAL_PATH=$(aag clone <github-url> [--branch <branch>])
# Use LOCAL_PATH as the target for all subsequent steps
```

**Multiple repos (cross-repo graph):**
```bash
# Clone each repo, run the full pipeline on each, then merge
aag clone <url1>   # → ~/.aag/repos/<owner1>/<repo1>
aag clone <url2>   # → ~/.aag/repos/<owner2>/<repo2>
# Run /aag on each local path to produce their per-repo graph artifacts
# (graphify-out/graph.json or graph.db, depending on backend)
# Then merge — merge-graphs accepts either backend per source path:
aag merge-graphs \
  ~/.aag/repos/<owner1>/<repo1>/graphify-out/graph.json \
  ~/.aag/repos/<owner2>/<repo2>/graphify-out/graph.json \
  --out graphify-out/cross-repo-graph.json
```

Graphify clones into `~/.aag/repos/<owner>/<repo>` and reuses existing clones on repeat runs. Each node in the merged graph carries a `repo` attribute so you can filter by origin.

### Step 1 - Ensure aag is installed

```bash
# Find a Python that can import graphify (or aag)
PYTHON=""
# 1. Try python3 directly
if python3 -c "import graphify" 2>/dev/null || python3 -c "import aag" 2>/dev/null; then
    PYTHON="python3"
fi
# 2. Try uv tool installs
if [ -z "$PYTHON" ] && command -v uv >/dev/null 2>&1; then
    _UV_PY=$(uv tool run aagy python -c "import sys; print(sys.executable)" 2>/dev/null)
    if [ -n "$_UV_PY" ]; then PYTHON="$_UV_PY"; fi
fi
# 3. Try the graphify source repo (dev mode — set PYTHONPATH)
if [ -z "$PYTHON" ]; then
    for _candidate in /local-nvme/hfeng/aa/aa-graphify ~/.local/share/graphify-src; do
        if [ -f "$_candidate/graphify/__init__.py" ]; then
            export PYTHONPATH="$_candidate${PYTHONPATH:+:$PYTHONPATH}"
            if python3 -c "import graphify" 2>/dev/null; then
                PYTHON="python3"
                break
            fi
        fi
    done
fi
# 4. Last resort: pip install
if [ -z "$PYTHON" ]; then
    PYTHON="python3"
    "$PYTHON" -m pip install aagy -q 2>/dev/null || "$PYTHON" -m pip install aagy -q --break-system-packages 2>&1 | tail -3
fi
# Write interpreter path for all subsequent steps
mkdir -p graphify-out
echo "$PYTHON" > graphify-out/.aag_python
# Save PYTHONPATH if we set one
[ -n "$PYTHONPATH" ] && echo "$PYTHONPATH" > graphify-out/.aag_pythonpath
# Save scan root so `aag update` (no args) knows where to look next time
echo "$(cd INPUT_PATH && pwd)" > graphify-out/.aag_root
```

If the import succeeds, print nothing and move straight to Step 2.

**In every subsequent bash block:** use `$(cat graphify-out/.aag_python)` as the interpreter; if `graphify-out/.aag_pythonpath` exists, prepend `PYTHONPATH=$(cat graphify-out/.aag_pythonpath)` to the command.

### Step 2 - Detect files

```bash
$(cat graphify-out/.aag_python) -c "
import json
from aag.detect import detect
from pathlib import Path
result = detect(Path('INPUT_PATH'))
print(json.dumps(result))
" > graphify-out/.aag_detect.json
```

Replace INPUT_PATH with the actual path the user provided. Do NOT cat or print the JSON - read it silently and present a clean summary instead:

```
Corpus: X files · ~Y words
  code:     N files (.py .ts .go ...)
  docs:     N files (.md .txt ...)
  papers:   N files (.pdf ...)
  images:   N files
  video:    N files (.mp4 .mp3 ...)
```

Omit any category with 0 files from the summary.

### Step 2.5 - Transcribe video / audio files (only if video files detected)

Skip this step entirely if `detect` returned zero `video` files.

Video and audio files cannot be read directly. Transcribe them to text first, then treat the transcripts as doc files in Step 3.

**Strategy:** Read the god nodes from `graphify-out/.aag_detect.json` (or the analysis file if it exists from a previous run). You are already a language model — write a one-sentence domain hint yourself from those labels. Then pass it to Whisper as the initial prompt. No separate API call needed.

**Step 1 - Write the Whisper prompt yourself.**

Read the top god node labels from detect output or analysis, then compose a short domain hint sentence, for example:

- Labels: `transformer, attention, encoder, decoder` → `"Machine learning research on transformer architectures and attention mechanisms. Use proper punctuation and paragraph breaks."`
- Labels: `kubernetes, deployment, pod, helm` → `"DevOps discussion about Kubernetes deployments and Helm charts. Use proper punctuation and paragraph breaks."`

Set it as `WHISPER_PROMPT` to use in the next command.

**Step 2 - Transcribe:**

```bash
GRAPHIFY_WHISPER_MODEL=base  # or whatever --whisper-model the user passed
$(cat graphify-out/.aag_python) -c "
import json, os
from pathlib import Path
from aag.transcribe import transcribe_all

detect = json.loads(Path('graphify-out/.aag_detect.json').read_text())
video_files = detect.get('files', {}).get('video', [])
prompt = os.environ.get('GRAPHIFY_WHISPER_PROMPT', 'Use proper punctuation and paragraph breaks.')

transcript_paths = transcribe_all(video_files, initial_prompt=prompt)
print(json.dumps(transcript_paths))
" > graphify-out/.aag_transcripts.json
```

After transcription:
- Read the transcript paths from `graphify-out/.aag_transcripts.json`
- Add them to the docs list before dispatching semantic subagents in Step 3B
- Print how many transcripts were created: `Transcribed N video file(s) -> treating as docs`

### Step 3 - Extract entities and relationships

**Before starting:** note whether `--mode deep` was given. You must pass `DEEP_MODE=true` to every subagent in Step B2 if it was. Track this from the original invocation - do not lose it.

This step has two parts: **structural extraction** (deterministic, free) and **semantic extraction** (LLM, costs tokens).

**Run Part A (AST) and Part B (semantic) in parallel. Dispatch all semantic subagents AND start AST extraction in the same message. Both can run simultaneously since they operate on different file types. Merge results in Part C as before.**

#### Part A - Structural extraction for code files

For any code files detected, run AST extraction in parallel with Part B subagents:

```bash
$(cat graphify-out/.aag_python) -c "
import sys, json
from aag.extract import collect_files, extract
from pathlib import Path
import json

code_files = []
detect = json.loads(Path('graphify-out/.aag_detect.json').read_text())
for f in detect.get('files', {}).get('code', []):
    code_files.extend(collect_files(Path(f)) if Path(f).is_dir() else [Path(f)])

if code_files:
    result = extract(code_files, cache_root=Path('.'))
    Path('graphify-out/.aag_ast.json').write_text(json.dumps(result, indent=2))
    print(f'AST: {len(result[\"nodes\"])} nodes, {len(result[\"edges\"])} edges')
else:
    Path('graphify-out/.aag_ast.json').write_text(json.dumps({'nodes':[],'edges':[],'input_tokens':0,'output_tokens':0}))
    print('No code files - skipping AST extraction')
"
```

#### Part B - Semantic extraction (parallel subagents)

**MANDATORY: You MUST use the Agent tool here. Reading files yourself one-by-one is forbidden - it is 5-10x slower.**

**Step B0 - Check extraction cache first**

```bash
$(cat graphify-out/.aag_python) -c "
import json
from aag.cache import check_semantic_cache
from pathlib import Path

detect = json.loads(Path('graphify-out/.aag_detect.json').read_text())
all_files = [f for files in detect['files'].values() for f in files]

cached_nodes, cached_edges, cached_hyperedges, uncached = check_semantic_cache(all_files)

if cached_nodes or cached_edges or cached_hyperedges:
    Path('graphify-out/.aag_cached.json').write_text(json.dumps({'nodes': cached_nodes, 'edges': cached_edges, 'hyperedges': cached_hyperedges}))
Path('graphify-out/.aag_uncached.txt').write_text('\n'.join(uncached))
print(f'Cache: {len(all_files)-len(uncached)} files hit, {len(uncached)} files need extraction')
"
```

**Step B2 - Dispatch ALL subagents in a single message (Codex)**

> **Codex platform:** Uses `spawn_agent` + `wait_agent` + `close_agent` instead of the Agent tool.

Call `spawn_agent` once per chunk — ALL in the same response:

```
spawn_agent(agent_type="worker", message="Your task is to perform the following...\n[extraction prompt below]")
```

Prompt for each subagent (substitute FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, and DEEP_MODE):

```
You are a aag extraction subagent. Read the files listed and extract a knowledge graph fragment.
Output ONLY valid JSON matching the schema below - no explanation, no markdown fences, no preamble.

Files (chunk CHUNK_NUM of TOTAL_CHUNKS):
FILE_LIST

Rules:
- EXTRACTED: relationship explicit in source (import, call, citation, "see §3.2").
- INFERRED: reasonable inference (shared data structure, implied dependency)
- AMBIGUOUS: uncertain - flag for review, do not omit

GROUNDING: Every node you create MUST correspond to a named entity, concept, metric, or clause that actually appears in the source file(s) you were given.

Code files: focus on semantic edges AST cannot find (call relationships, shared data, arch patterns).
Doc/paper files: extract named concepts, entities, citations.
Image files: use vision to understand what the image IS.

Node ID format: `{stem}_{entity}` where stem is the filename without extension and entity is the symbol name, both normalized.

Output exactly this JSON:
{"nodes":[{"id":"session_validatetoken","label":"Name","description":"Summary","file_type":"code|document|paper|image|rationale","source_file":"path"}],"edges":[{"source":"id","target":"id","relation":"verb","confidence":"EXTRACTED|INFERRED|AMBIGUOUS","confidence_score":1.0}],"hyperedges":[],"input_tokens":0,"output_tokens":0}
```

**Step B3 - Collect, cache, and merge**

Wait for all subagents. For each result:
- Check that `graphify-out/.aag_chunk_NN.json` exists on disk.
- Merge all chunk files into `.aag_semantic_new.json`.

**Part C - Merge AST + semantic into final extraction**

```bash
$(cat graphify-out/.aag_python) -c "
import sys, json
from pathlib import Path

ast = json.loads(Path('graphify-out/.aag_ast.json').read_text())
sem = json.loads(Path('graphify-out/.aag_semantic.json').read_text())

seen = {n['id'] for n in ast['nodes']}
merged_nodes = list(ast['nodes'])
for n in sem['nodes']:
    if n['id'] not in seen:
        merged_nodes.append(n)
        seen.add(n['id'])

merged_edges = ast['edges'] + sem['edges']
merged_hyperedges = sem.get('hyperedges', [])
merged = {'nodes': merged_nodes, 'edges': merged_edges, 'hyperedges': merged_hyperedges, 'input_tokens': sem.get('input_tokens', 0), 'output_tokens': sem.get('output_tokens', 0)}

# Domain plugin hooks (only if --domain was passed)
DOMAIN_NAMES = DOMAIN_NAMES_PLACEHOLDER
if DOMAIN_NAMES:
    # ... (see skill.md for full domain logic)
    pass

Path('graphify-out/.aag_extract.json').write_text(json.dumps(merged, indent=2))
print(f'Merged: {len(merged_nodes)} nodes, {len(merged_edges)} edges')
"
```

### Step 4 - Build graph, cluster, analyze, generate outputs

```bash
mkdir -p graphify-out
$(cat graphify-out/.aag_python) -c "
import sys, json
from aag.build import build_from_json
from aag.cluster import cluster, score_all
from aag.analyze import god_nodes, surprising_connections, suggest_questions
from aag.report import generate
from aag.store import save as _gx_save
from pathlib import Path

extraction = json.loads(Path('graphify-out/.aag_extract.json').read_text())
detection  = json.loads(Path('graphify-out/.aag_detect.json').read_text())

G = build_from_json(extraction)
communities = cluster(G)
cohesion = score_all(G, communities)

gods = god_nodes(G)
surprises = surprising_connections(G, communities)
labels = {cid: 'Community ' + str(cid) for cid in communities}
questions = suggest_questions(G, communities, labels)

report = generate(G, communities, labels, gods, surprises, detection, {'input':0,'output':0}, 'INPUT_PATH', cohesion_scores=cohesion, suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report)
_gx_save('graphify-out', G, communities, backend=('db' if USE_DB else None))

analysis = {
    'communities': {str(k): v for k, v in communities.items()},
    'cohesion': {str(k): v for k, v in cohesion.items()},
    'gods': gods,
    'surprises': surprises,
    'questions': questions,
}
Path('graphify-out/.aag_analysis.json').write_text(json.dumps(analysis, indent=2))
"
```

### Step 5 - Label communities

1. Read `graphify-out/.aag_analysis.json`.
2. For each community, write a 2-5 word name.
3. Update the report and save labels to `graphify-out/.aag_labels.json`.

### Step 5B - Narrative Synthesis (Agent-Led)

If domain analysis is present but `synthesized_narratives` is empty, perform synthesis using your own reasoning.

1. **Generate Prompts:** Run `synthesize_risks_offline`.
2. **Perform Synthesis:** Write narratives based on the prompts.
3. **Inject Narratives:** Save back to `graphify-out/.aag_analysis.json`.
