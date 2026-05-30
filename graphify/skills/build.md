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
# 0. If graphify-out/.aag_python already exists and still works, reuse it
if [ -f graphify-out/.aag_python ]; then
    _PREV=$(cat graphify-out/.aag_python)
    if "$_PREV" -c "import graphify" 2>/dev/null || "$_PREV" -c "import aag" 2>/dev/null; then
        PYTHON="$_PREV"
    fi
fi
# 1. Try python3 directly
if [ -z "$PYTHON" ]; then
    if python3 -c "import graphify" 2>/dev/null || python3 -c "import aag" 2>/dev/null; then
        PYTHON="python3"
    fi
fi
# 2. Try active virtualenv
if [ -z "$PYTHON" ] && [ -n "$VIRTUAL_ENV" ]; then
    if "$VIRTUAL_ENV/bin/python3" -c "import graphify" 2>/dev/null; then
        PYTHON="$VIRTUAL_ENV/bin/python3"
    fi
fi
# 3. Try venvs in known source repo locations
if [ -z "$PYTHON" ]; then
    for _candidate in /local-nvme/hfeng/aa/aa-graphify-devel /local-nvme/hfeng/aa/aa-graphify ~/.local/share/graphify-src; do
        # Check for venv first (editable installs live here)
        if [ -f "$_candidate/.venv/bin/python3" ]; then
            if "$_candidate/.venv/bin/python3" -c "import graphify" 2>/dev/null; then
                PYTHON="$_candidate/.venv/bin/python3"
                break
            fi
        fi
        # Fallback: set PYTHONPATH to source dir
        if [ -f "$_candidate/graphify/__init__.py" ]; then
            export PYTHONPATH="$_candidate${PYTHONPATH:+:$PYTHONPATH}"
            if python3 -c "import graphify" 2>/dev/null; then
                PYTHON="python3"
                break
            fi
        fi
    done
fi
# 4. Try uv tool installs
if [ -z "$PYTHON" ] && command -v uv >/dev/null 2>&1; then
    _UV_PY=$(uv tool run aagy python -c "import sys; print(sys.executable)" 2>/dev/null)
    if [ -n "$_UV_PY" ]; then PYTHON="$_UV_PY"; fi
fi
# 5. Last resort: pip install
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

**IMPORTANT:** The resolved `PYTHON` may be an absolute path to a venv interpreter (e.g., `/path/to/.venv/bin/python3`), not just `python3`. Always use `$(cat graphify-out/.aag_python)` in subsequent steps — never hardcode `python3`.

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

### Step 2.5a - Convert HTML files to Markdown (optimizes token usage)

HTML files are converted to clean Markdown before extraction to reduce token waste and expose section headings.

```bash
$(cat graphify-out/.aag_python) -c "
import json
from pathlib import Path
from aag.ingest import convert_html_files

detect = json.loads(Path('graphify-out/.aag_detect.json').read_text())
doc_files = [Path(f) for f in detect.get('files', {}).get('document', [])]
html_files = [f for f in doc_files if f.suffix.lower() in ('.html', '.htm', '.xhtml')]

if html_files:
    mapping = convert_html_files(html_files, Path('graphify-out'))
    Path('graphify-out/.aag_html_mapping.json').write_text(
        json.dumps({str(k): str(v) for k, v in mapping.items()})
    )
"
```

After conversion:
- Read `graphify-out/.aag_html_mapping.json`.
- For every HTML file in the `document` list, **REPLACE** its path with the corresponding `.aag_converted_*.md` path from the mapping before dispatching subagents in Step 3B.
- This ensures subagents read the clean, lightweight Markdown instead of raw HTML.

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

**Step B1 - Load domain prompt fragments (only if `--domain` was passed)**

If `--domain` was given, load domain-specific extraction prompts to inject into each subagent. Skip this step if no domains are active.

```bash
$(cat graphify-out/.aag_python) -c "
from pathlib import Path
from aag.domain import active_domains

DOMAIN_NAMES = ['DOMAIN1', 'DOMAIN2']  # Replace with actual domain names from --domain flag
config = {'domains': DOMAIN_NAMES}
fragments = []
for dom in active_domains(config):
    if dom.prompt_fragments:
        fragments.append(dom.prompt_fragments())
Path('graphify-out/.aag_domain_prompt.txt').write_text('\n\n'.join(fragments))
print(f'Loaded {len(fragments)} domain prompt fragment(s)')
"
```

Read `graphify-out/.aag_domain_prompt.txt` silently. You will append its contents to each subagent prompt as `DOMAIN_PROMPT` below.

**Step B2 - Dispatch ALL subagents in a single message**

Call the Agent tool multiple times IN THE SAME RESPONSE - one call per chunk. Use `subagent_type="general-purpose"` and `mode: "bypassPermissions"`.

**IMPORTANT: Subagent file writing.** Subagents MUST write their output to `graphify-out/.aag_chunk_NN.json`. To avoid permission denial issues:
- Use `mode: "bypassPermissions"` when spawning the Agent.
- Instruct each subagent to write the file using the Write tool.
- If a subagent reports that it cannot write (permission denied), you must extract the JSON from its response text and write it yourself.

Prompt for each subagent (substitute FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE, DOMAIN_PROMPT, and ABSOLUTE_OUTPUT_PATH):

```
You are a aag extraction subagent. Read the files listed and extract a knowledge graph fragment.

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

DOMAIN_PROMPT

Node ID format: `{stem}_{entity}` where stem is the filename without extension and entity is the symbol name, both normalized.

Write the result as valid JSON to: ABSOLUTE_OUTPUT_PATH
Use this exact schema:
{"nodes":[{"id":"session_validatetoken","label":"Name","description":"Summary","file_type":"code|document|paper|image|rationale","source_file":"path"}],"edges":[{"source":"id","target":"id","relation":"verb","confidence":"EXTRACTED|INFERRED|AMBIGUOUS","confidence_score":1.0}],"hyperedges":[],"input_tokens":0,"output_tokens":0}
```

**NOTE on DOMAIN_PROMPT:** If `graphify-out/.aag_domain_prompt.txt` exists and is non-empty, substitute its full contents in place of `DOMAIN_PROMPT` above. If no domains are active, remove the `DOMAIN_PROMPT` line entirely.

**Step B3 - Collect, cache, and merge**

Wait for all subagents. For each result:
- Check that `graphify-out/.aag_chunk_NN.json` exists on disk.
- **Fallback if file missing:** If a subagent completed but the file does not exist (permission issue), read the subagent's output file from the task notification and extract the JSON content from its Write tool call input. Then write the file yourself.
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

Path('graphify-out/.aag_extract.json').write_text(json.dumps(merged, indent=2))
print(f'Merged: {len(merged_nodes)} nodes, {len(merged_edges)} edges')
"
```

### Step 3D - Domain extraction (only if `--domain` was passed)

**Skip this step entirely if no `--domain` flag was given.**

For each domain name in the comma-separated `--domain` value (e.g., `finance,diligence`), run its extractors on all detected files, then merge results into the extraction.

```bash
$(cat graphify-out/.aag_python) -c "
import json
from pathlib import Path

DOMAIN_NAMES = ['DOMAIN1', 'DOMAIN2']  # Replace with actual domain names from --domain flag

detect = json.loads(Path('graphify-out/.aag_detect.json').read_text())
all_files = [Path(f) for files in detect['files'].values() for f in files]

domain_nodes, domain_edges = [], []

for domain_name in DOMAIN_NAMES:
    mod = __import__(f'aag.domains.{domain_name}', fromlist=['_SPEC'])
    spec = mod._SPEC

    # Run each extractor on matching files
    for extractor in spec.extractors:
        for fpath in all_files:
            if any(fpath.match(pat) for pat in extractor.file_patterns):
                content = fpath.read_text(errors='replace')
                result = extractor.extract(fpath, content)
                for n in result.get('nodes', []):
                    n['domain'] = domain_name
                domain_nodes.extend(result.get('nodes', []))
                domain_edges.extend(result.get('edges', []))

    # Run post_extract hook if defined
    if spec.post_extract:
        combined = spec.post_extract({'nodes': domain_nodes, 'edges': domain_edges})
        domain_nodes = combined['nodes']
        domain_edges = combined['edges']

# Merge into existing extraction
extract = json.loads(Path('graphify-out/.aag_extract.json').read_text())
seen_ids = {n['id'] for n in extract['nodes']}
for n in domain_nodes:
    if n['id'] not in seen_ids:
        extract['nodes'].append(n)
        seen_ids.add(n['id'])
extract['edges'].extend(domain_edges)

Path('graphify-out/.aag_extract.json').write_text(json.dumps(extract, indent=2))
print(f'Domain extraction: +{len(domain_nodes)} nodes, +{len(domain_edges)} edges')
print(f'Total: {len(extract[\"nodes\"])} nodes, {len(extract[\"edges\"])} edges')
"
```

Print a summary:
```
Domain extraction (finance, diligence):
  finance:    +N nodes, +M edges (tables: obligation schedules, maturities, covenants)
  diligence:  +N nodes, +M edges (governance tables, related-party flags, officer transactions)
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

### Step 4B - Domain post-build and analyzers (only if `--domain` was passed)

**Skip this step entirely if no `--domain` flag was given.**

This step runs domain-specific graph-level inference (e.g., conflict detection, type tagging, contradiction detection) and domain analyzers (red flags, key person risk, concentration risk).

**API notes:**
- `load(out_dir)` — takes only the directory path, auto-detects `graph.db` vs `graph.json`. Returns a NetworkX graph. No `backend` kwarg.
- `save(out_dir, G, communities, backend=...)` — `backend='db'` for SQLite, `None` for JSON.

```bash
$(cat graphify-out/.aag_python) -c "
import json
from pathlib import Path
from aag.store import load as _gx_load, save as _gx_save

DOMAIN_NAMES = ['DOMAIN1', 'DOMAIN2']  # Replace with actual domain names

G = _gx_load('graphify-out')

# Run post_build hooks (graph-level inference)
for domain_name in DOMAIN_NAMES:
    mod = __import__(f'aag.domains.{domain_name}', fromlist=['_SPEC'])
    spec = mod._SPEC
    if spec.post_build:
        spec.post_build(G)
        print(f'  {domain_name}: post_build complete')

# Run domain analyzers
domain_analysis = {}
for domain_name in DOMAIN_NAMES:
    mod = __import__(f'aag.domains.{domain_name}', fromlist=['_SPEC'])
    spec = mod._SPEC
    for analyzer in spec.analyzers:
        result = analyzer(G)
        key = f'{domain_name}.{analyzer.__name__}'
        domain_analysis[key] = result
        print(f'  {domain_name}/{key}: {len(result)} findings')

# Save domain analysis into .aag_analysis.json
analysis = json.loads(Path('graphify-out/.aag_analysis.json').read_text())
analysis['domain_analysis'] = domain_analysis
analysis['synthesized_narratives'] = []
Path('graphify-out/.aag_analysis.json').write_text(json.dumps(analysis, indent=2))

# Save updated graph (post_build may have added edges/attributes)
from aag.cluster import cluster
communities = cluster(G)
_gx_save('graphify-out', G, communities, backend=('db' if USE_DB else None))
print(f'Graph after domain hooks: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges')
"
```

Print a summary:
```
Domain analysis:
  red_flag_analyzer:         N findings (X high, Y medium, Z low)
  key_person_risk_analyzer:  N findings
  concentration_risk_analyzer: N findings
```

### Step 5 - Label communities

1. Read `graphify-out/.aag_analysis.json`.
2. For each community, write a 2-5 word name.
3. Update the report and save labels to `graphify-out/.aag_labels.json`.

### Step 5B - Narrative Synthesis (Agent-Led, only if `--domain` was passed)

**Skip this step entirely if no `--domain` flag was given or if `domain_analysis` is absent from `.aag_analysis.json`.**

This step generates investigative risk narratives from the domain analysis findings. The synthesis is agent-led: you generate the prompts programmatically, then write the narratives yourself based on the subgraph context and red flags.

**Step 5B.1 - Generate synthesis prompts:**

```bash
$(cat graphify-out/.aag_python) -c "
import json
from pathlib import Path
from aag.store import load as _gx_load
from aag.synthesize import synthesize_risks_offline

G = _gx_load('graphify-out')
analysis = json.loads(Path('graphify-out/.aag_analysis.json').read_text())

red_flags = analysis.get('domain_analysis', {}).get('red_flag_analyzer', [])
key_persons = analysis.get('domain_analysis', {}).get('key_person_risk_analyzer', [])

prompts = synthesize_risks_offline(G, red_flags, key_persons)
Path('graphify-out/.aag_synthesis_prompts.json').write_text(json.dumps(prompts, indent=2))
print(f'Generated {len(prompts)} synthesis prompts:')
for p in prompts:
    print(f'  - {p[\"label\"]} ({p[\"finding_count\"]} findings)')
"
```

**Step 5B.2 - Write narratives:**

Read the prompts from `graphify-out/.aag_synthesis_prompts.json`. For each prompt:
1. Read the SUBGRAPH and RED FLAGS sections from the prompt text.
2. Write a narrative following the structure in the prompt (What's happening / Who benefits / Why worse than it looks / What to investigate next).
3. Use actual entity names and dollar amounts from the subgraph. Be direct and blunt.

**Step 5B.3 - Inject narratives:**

Save the narratives back into `graphify-out/.aag_analysis.json` under the `synthesized_narratives` key. Each entry should have:
```json
{
  "theme": "theme_id",
  "label": "Theme Label",
  "center_entity": "entity name",
  "finding_count": N,
  "findings_summary": ["type1", "type2"],
  "narrative": "## What's happening\n..."
}
```

**Step 5B.4 - Regenerate report with narratives:**

```bash
$(cat graphify-out/.aag_python) -c "
import json
from pathlib import Path
from aag.store import load as _gx_load
from aag.report import generate

G = _gx_load('graphify-out')
analysis = json.loads(Path('graphify-out/.aag_analysis.json').read_text())
detection = json.loads(Path('graphify-out/.aag_detect.json').read_text())

communities = {int(k): v for k, v in analysis['communities'].items()}
cohesion = {int(k): v for k, v in analysis['cohesion'].items()}
labels = json.loads(Path('graphify-out/.aag_labels.json').read_text()) if Path('graphify-out/.aag_labels.json').exists() else {str(k): f'Community {k}' for k in communities}

report = generate(G, communities, labels, analysis['gods'], analysis['surprises'], detection, {'input':0,'output':0}, 'INPUT_PATH', cohesion_scores=cohesion, suggested_questions=analysis.get('questions',[]), synthesized_narratives=analysis.get('synthesized_narratives',[]))
Path('graphify-out/GRAPH_REPORT.md').write_text(report)
print(f'Report regenerated with {len(analysis.get(\"synthesized_narratives\",[]))} narratives')
"
```
