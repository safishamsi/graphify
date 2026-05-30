# WeWork S-1 Filing E2E Test

This is a full-scale test for both finance and diligence domain pipelines on a real SEC filing (4.7MB HTML). Tests HTML→markdown conversion, semantic extraction with domain prompts, domain table extractors, red flag analyzer, key-person risk, narrative synthesis, and dashboard.

## Prerequisites

```bash
PYTHON=/home/xfz/aa/aa-graphify-dev/.venv/bin/python3
WORKDIR=/home/xfz/aa/aa-graphify-dev/examples/wework-s1
```

## Step 1: Setup

```bash
cd $WORKDIR
rm -rf graphify-out
mkdir -p graphify-out
echo "$PYTHON" > graphify-out/.aag_python
echo "$(cd raw && pwd)" > graphify-out/.aag_root
```

## Step 2: Detect

```bash
$PYTHON -c "
import json
from graphify.detect import detect
from pathlib import Path
result = detect(Path('raw'))
print(json.dumps(result))
" > graphify-out/.aag_detect.json
```

**Verify:** 1 document file, total_words > 400,000

## Step 2.5a: HTML→Markdown Conversion

```bash
$PYTHON -c "
import json
from pathlib import Path
from graphify.ingest import convert_html_files

detect = json.loads(Path('graphify-out/.aag_detect.json').read_text())
doc_files = [Path(f) for f in detect.get('files', {}).get('document', [])]
html_files = [f for f in doc_files if f.suffix.lower() in ('.html', '.htm', '.xhtml')]

if html_files:
    mapping = convert_html_files(html_files, Path('graphify-out'))
    Path('graphify-out/.aag_html_mapping.json').write_text(
        json.dumps({str(k): str(v) for k, v in mapping.items()})
    )
    for orig, conv in mapping.items():
        print(f'{orig.stat().st_size:,} -> {conv.stat().st_size:,} bytes')
"
```

**Verify:**
- `graphify-out/.aag_converted_d781982ds1.md` exists
- Size reduction >= 60% (baseline: 4,704,976 → 1,540,161 bytes, 68% reduction)

## Step 3A: AST (empty - no code)

```bash
$PYTHON -c "
import json
from pathlib import Path
Path('graphify-out/.aag_ast.json').write_text(json.dumps({'nodes':[],'edges':[],'input_tokens':0,'output_tokens':0}))
"
```

## Step 3B1: Load domain prompts

```bash
$PYTHON -c "
from pathlib import Path
from graphify.domain import active_domains
config = {'domains': ['finance', 'diligence']}
fragments = []
for dom in active_domains(config):
    if dom.prompt_fragments:
        fragments.append(dom.prompt_fragments())
Path('graphify-out/.aag_domain_prompt.txt').write_text('\n\n'.join(fragments))
print(f'Loaded {len(fragments)} domain prompt fragment(s)')
"
```

**Verify:** 2 fragments loaded; file contains "Due Diligence" and "Finance Domain"

## Step 3B2: Semantic extraction (4 LLM subagents)

Split the **converted markdown** file into 4 chunks (~375K chars each) and dispatch 4 parallel subagents.

Each subagent reads its chunk of `graphify-out/.aag_converted_d781982ds1.md` and extracts entities/relationships using the domain prompt.

Subagent outputs: `graphify-out/.aag_chunk_01.json` through `.aag_chunk_04.json`

**Verify after extraction (baseline: 129 semantic nodes, 246 edges across 4 chunks):**
- At least 100 nodes extracted total
- Nodes include companies (The We Company, SoftBank), persons (Adam Neumann, Rebekah Neumann), financial instruments
- Edges include: `officer_of`, `controls`, `owns`, `obligated_to`, `counterparty_to`, `self_dealing`, `loan_to_officer`, `family_tie`, `leases_from`

## Step 3C: Merge chunks into extraction

```bash
$PYTHON -c "
import json
from pathlib import Path

all_nodes, all_edges, all_hyperedges = [], [], []
seen_ids = set()
for i in range(1, 5):
    chunk = json.loads(Path(f'graphify-out/.aag_chunk_{i:02d}.json').read_text())
    for n in chunk.get('nodes', []):
        if n['id'] not in seen_ids:
            all_nodes.append(n)
            seen_ids.add(n['id'])
    all_edges.extend(chunk.get('edges', []))
    all_hyperedges.extend(chunk.get('hyperedges', []))

sem = {'nodes': all_nodes, 'edges': all_edges, 'hyperedges': all_hyperedges, 'input_tokens': 0, 'output_tokens': 0}
Path('graphify-out/.aag_semantic.json').write_text(json.dumps(sem, indent=2))

ast = json.loads(Path('graphify-out/.aag_ast.json').read_text())
seen = {n['id'] for n in ast['nodes']}
merged_nodes = list(ast['nodes'])
for n in sem['nodes']:
    if n['id'] not in seen:
        merged_nodes.append(n)
        seen.add(n['id'])
merged = {'nodes': merged_nodes, 'edges': ast['edges'] + sem['edges'], 'hyperedges': all_hyperedges, 'input_tokens': 0, 'output_tokens': 0}
Path('graphify-out/.aag_extract.json').write_text(json.dumps(merged, indent=2))
print(f'Merged: {len(merged_nodes)} nodes, {len(merged[\"edges\"])} edges')
"
```

## Step 3D: Domain extraction (structured table parsers)

```bash
$PYTHON -c "
import json
from pathlib import Path

detect = json.loads(Path('graphify-out/.aag_detect.json').read_text())
all_files = [Path(f) for files in detect['files'].values() for f in files]
domain_nodes, domain_edges = [], []

for domain_name in ['finance', 'diligence']:
    mod = __import__(f'graphify.domains.{domain_name}', fromlist=['_SPEC'])
    spec = mod._SPEC
    for extractor in spec.extractors:
        for fpath in all_files:
            if any(fpath.match(pat) for pat in extractor.file_patterns):
                content = fpath.read_text(errors='replace')
                result = extractor.extract(fpath, content)
                for n in result.get('nodes', []):
                    n['domain'] = domain_name
                domain_nodes.extend(result.get('nodes', []))
                domain_edges.extend(result.get('edges', []))
    if spec.post_extract:
        combined = spec.post_extract({'nodes': domain_nodes, 'edges': domain_edges})
        domain_nodes = combined['nodes']
        domain_edges = combined['edges']

extract = json.loads(Path('graphify-out/.aag_extract.json').read_text())
seen_ids = {n['id'] for n in extract['nodes']}
for n in domain_nodes:
    if n['id'] not in seen_ids:
        extract['nodes'].append(n)
        seen_ids.add(n['id'])
extract['edges'].extend(domain_edges)
Path('graphify-out/.aag_extract.json').write_text(json.dumps(extract, indent=2))
print(f'Domain: +{len(domain_nodes)} nodes, +{len(domain_edges)} edges')
print(f'Total: {len(extract[\"nodes\"])} nodes, {len(extract[\"edges\"])} edges')
"
```

**Verify (baseline: +236 domain nodes, +404 domain edges):**
- Domain extractors add >= 150 nodes from tables
- Total nodes >= 300 after domain extraction

## Step 4: Build graph, cluster, analyze

```bash
$PYTHON -c "
import json
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.store import save as _gx_save
from pathlib import Path

extraction = json.loads(Path('graphify-out/.aag_extract.json').read_text())
detection = json.loads(Path('graphify-out/.aag_detect.json').read_text())

G = build_from_json(extraction)
communities = cluster(G)
cohesion = score_all(G, communities)
gods = god_nodes(G)
surprises = surprising_connections(G, communities)
labels = {cid: 'Community ' + str(cid) for cid in communities}
questions = suggest_questions(G, communities, labels)

report = generate(G, communities, labels, gods, surprises, detection, {'input':0,'output':0}, 'raw/', cohesion_scores=cohesion, suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report)
_gx_save('graphify-out', G, communities, backend='db')

analysis = {
    'communities': {str(k): v for k, v in communities.items()},
    'cohesion': {str(k): v for k, v in cohesion.items()},
    'gods': gods,
    'surprises': surprises,
    'questions': questions,
}
Path('graphify-out/.aag_analysis.json').write_text(json.dumps(analysis, indent=2))
print(f'Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities')
"
```

## Step 4B: Domain analyzers

```bash
$PYTHON -c "
import json
from pathlib import Path
from graphify.store import load as _gx_load, save as _gx_save
from graphify.cluster import cluster

G = _gx_load('graphify-out')

for domain_name in ['finance', 'diligence']:
    mod = __import__(f'graphify.domains.{domain_name}', fromlist=['_SPEC'])
    spec = mod._SPEC
    if spec.post_build:
        spec.post_build(G)

domain_analysis = {}
for domain_name in ['finance', 'diligence']:
    mod = __import__(f'graphify.domains.{domain_name}', fromlist=['_SPEC'])
    spec = mod._SPEC
    for analyzer in spec.analyzers:
        result = analyzer(G)
        key = f'{domain_name}.{analyzer.__name__}'
        domain_analysis[key] = result
        print(f'  {key}: {len(result)} findings')

analysis = json.loads(Path('graphify-out/.aag_analysis.json').read_text())
analysis['domain_analysis'] = domain_analysis
analysis['synthesized_narratives'] = []
Path('graphify-out/.aag_analysis.json').write_text(json.dumps(analysis, indent=2))

communities = cluster(G)
_gx_save('graphify-out', G, communities, backend='db')
print(f'Graph after hooks: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges')
"
```

**Verify (CRITICAL):**
- `diligence.red_flag_analyzer` returns >= 15 findings
- At least 4 findings have severity "high"
- Finding types must include: `related_party_exposure`, `key_person_risk`, `compensation_concentration`
- `diligence.key_person_risk_analyzer` returns >= 3 findings (Adam Neumann, SoftBank, etc.)

## Step 5B: Narrative synthesis

```bash
$PYTHON -c "
import json
from pathlib import Path
from graphify.store import load as _gx_load
from graphify.synthesize import synthesize_risks_offline

G = _gx_load('graphify-out')
analysis = json.loads(Path('graphify-out/.aag_analysis.json').read_text())

red_flags = analysis.get('domain_analysis', {}).get('diligence.red_flag_analyzer', [])
key_persons = analysis.get('domain_analysis', {}).get('diligence.key_person_risk_analyzer', [])

prompts = synthesize_risks_offline(G, red_flags, key_persons)
Path('graphify-out/.aag_synthesis_prompts.json').write_text(json.dumps(prompts, indent=2))
print(f'Generated {len(prompts)} synthesis prompts')
for p in prompts:
    print(f'  - {p[\"label\"]} ({p[\"finding_count\"]} findings)')
"
```

**Verify (baseline: 3 prompts):** At least 2 synthesis prompts generated. Expected themes: Related-Party Exposure, Governance & Control, Financial Risk.

After reading the prompts, write narratives following the structure (What's happening / Who benefits / Why worse / What to investigate). Then inject into `.aag_analysis.json` under `synthesized_narratives`.

## Step 6+7e: HTML viz and dashboard

```bash
$PYTHON -m graphify export html
$PYTHON -c "
from pathlib import Path
from graphify.dashboard import render_dashboard_from_file
out = render_dashboard_from_file(Path('graphify-out/.aag_analysis.json'), Path('graphify-out/graph.db'))
print(f'Dashboard: {out}')
"
```

**Verify:**
- `graphify-out/graph.html` exists
- `graphify-out/dashboard.html` exists
- Dashboard contains red flag data (grep for "related_party_exposure" in the HTML)
- Dashboard shows narratives (grep for "What's happening" in the HTML)

## Final Verification Checklist

```bash
$PYTHON -c "
import json
from pathlib import Path

print('=== FINAL VERIFICATION ===')
errors = []

# 1. Files exist
for f in ['graph.db', 'graph.html', 'dashboard.html', 'GRAPH_REPORT.md', '.aag_analysis.json']:
    if not Path(f'graphify-out/{f}').exists():
        errors.append(f'MISSING: graphify-out/{f}')
    else:
        print(f'  OK: graphify-out/{f}')

# 2. HTML→MD conversion
md_path = Path('graphify-out/.aag_converted_d781982ds1.md')
if md_path.exists():
    htm_size = Path('raw/d781982ds1.htm').stat().st_size
    md_size = md_path.stat().st_size
    reduction = 100 - md_size * 100 // htm_size
    print(f'\n  HTML→MD: {htm_size:,} → {md_size:,} bytes ({reduction}% reduction)')
    if reduction < 60:
        errors.append(f'FAIL: Expected >= 60% reduction, got {reduction}%')
else:
    errors.append('MISSING: graphify-out/.aag_converted_d781982ds1.md')

# 3. Graph size
from graphify.store import load as _gx_load
G = _gx_load('graphify-out')
print(f'\n  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges')
if G.number_of_nodes() < 250:
    errors.append(f'FAIL: Expected >= 250 nodes, got {G.number_of_nodes()}')
if G.number_of_edges() < 400:
    errors.append(f'FAIL: Expected >= 400 edges, got {G.number_of_edges()}')

# 4. Domain nodes
domain_nodes = [n for n, d in G.nodes(data=True) if d.get('domain')]
print(f'  Domain nodes: {len(domain_nodes)}')
semantic_nodes = G.number_of_nodes() - len(domain_nodes)
print(f'  Semantic nodes: {semantic_nodes}')
if len(domain_nodes) < 150:
    errors.append(f'FAIL: Expected >= 150 domain nodes, got {len(domain_nodes)}')

# 5. Red flags
analysis = json.loads(Path('graphify-out/.aag_analysis.json').read_text())
red_flags = analysis.get('domain_analysis', {}).get('diligence.red_flag_analyzer', [])
print(f'\n  Red flags: {len(red_flags)}')
if len(red_flags) < 15:
    errors.append(f'FAIL: Expected >= 15 red flags, got {len(red_flags)}')
high_flags = [f for f in red_flags if f.get('severity') == 'high']
print(f'  HIGH severity: {len(high_flags)}')
if len(high_flags) < 4:
    errors.append(f'FAIL: Expected >= 4 HIGH severity flags, got {len(high_flags)}')
for rf in red_flags:
    print(f'    [{rf[\"severity\"].upper():6}] {rf[\"type\"]}: {rf.get(\"label\",rf.get(\"node\",\"\"))[:60]}')

# 6. Key-person risks
key_persons = analysis.get('domain_analysis', {}).get('diligence.key_person_risk_analyzer', [])
print(f'\n  Key-person risks: {len(key_persons)}')
if len(key_persons) < 3:
    errors.append(f'FAIL: Expected >= 3 key-person risks, got {len(key_persons)}')
for kp in key_persons:
    print(f'    - {kp.get(\"label\", kp.get(\"node\", \"\"))[:60]}')

# 7. Narratives
narratives = analysis.get('synthesized_narratives', [])
print(f'\n  Narratives: {len(narratives)}')
if len(narratives) < 2:
    errors.append(f'FAIL: Expected >= 2 narratives, got {len(narratives)}')
for n in narratives:
    print(f'    - {n[\"label\"]} ({n[\"finding_count\"]} findings)')

# 8. Dashboard has red flags and narratives
dashboard = Path('graphify-out/dashboard.html').read_text()
if 'related_party_exposure' not in dashboard:
    errors.append('FAIL: dashboard.html missing red flag data')
else:
    print('\n  Dashboard: contains red flag data')
if 'narrative' not in dashboard.lower():
    errors.append('FAIL: dashboard.html missing narratives')
else:
    print('  Dashboard: contains narratives')

# Summary
print()
if errors:
    print('FAILURES:')
    for e in errors:
        print(f'  {e}')
    raise SystemExit(1)
else:
    print('ALL CHECKS PASSED')
"
```

## Expected Results

Thresholds are set conservatively below observed baselines (in parentheses) to allow for LLM variance.

| Metric | Pass threshold | Observed baseline |
|--------|---------------|-------------------|
| HTML→MD reduction | >= 60% | 68% (4,704,976 → 1,540,161 bytes) |
| Nodes (semantic) | >= 100 | 129 |
| Nodes (domain) | >= 150 | 219 (from table extractors) |
| Nodes (total) | >= 250 | 348 |
| Edges (total) | >= 400 | 541 |
| Communities | >= 30 | 52 |
| Red flags | >= 15, with >= 4 HIGH | 20 (5 HIGH, 15 MEDIUM) |
| Flag types | must include `related_party_exposure`, `key_person_risk`, `compensation_concentration` | all present |
| Key-person risks | >= 3 | 4 (Adam Neumann, ChinaCo, SoftBank, M. Steven Langman) |
| Synthesis prompts | >= 2 | 3 |
| Narratives | >= 2 | 3 (Related-Party Exposure, Governance & Control, Financial Risk) |
| Dashboard red flags visible | Yes | Yes |
| Dashboard narratives visible | Yes | Yes |

## Notes

- The raw file (`raw/d781982ds1.htm`) is a real SEC S-1 filing (4.7MB, ~418K words)
- HTML→markdown conversion reduces to ~1.5MB before subagent dispatch
- Semantic extraction requires 4 parallel LLM subagents (one per ~375K-char chunk)
- Domain table extractors are deterministic and produce the bulk of nodes (219 of 348)
- Key entities: Adam Neumann (CEO/landlord/borrower), SoftBank, WE Holdings LLC, ARK Capital
- Total runtime excluding LLM: ~15 seconds
- Total runtime with LLM extraction: ~3-5 minutes (4 parallel subagents)
- The `raw/` file is large (~4.7MB); it is gitignored if repo size is a concern
