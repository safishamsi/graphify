# BurnCo Finance Domain E2E Test

Quick-verify test for the finance domain pipeline: semantic extraction with domain prompts → domain table extractors → concentration risk analyzer → narrative synthesis → dashboard.

BurnCo is a fictional high-burn SaaS company with aggressive accounting, customer concentration, a debt maturity wall, and going-concern risk.

## Prerequisites

```bash
PYTHON=/local-nvme/hfeng/aa/aa-graphify-devel/.venv/bin/python3
WORKDIR=/local-nvme/hfeng/aa/aa-graphify-devel/examples/burnco-finance
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

**Verify:** 1 document file, total_words > 500

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

**Verify:** 2 fragments loaded; file contains "Finance Domain" and "LIQUIDITY RUNWAY"

## Step 3B2: Semantic extraction (LLM subagent)

Dispatch a subagent to read `raw/burnco_10k.htm` and extract a knowledge graph.

The subagent prompt MUST include the contents of `graphify-out/.aag_domain_prompt.txt` as the DOMAIN_PROMPT section.

The subagent should write output to `graphify-out/.aag_chunk_01.json`.

**Verify after extraction (baseline: ~30 nodes, ~40 edges):**
- At least 20 nodes extracted
- Nodes include: `burnco_10k_burnco`, `burnco_10k_megabank_corp`, `burnco_10k_datamesh_corp`
- Edges include at least 5 of these relation types: `burn_rate`, `cash_flow_divergence`, `excludes_from_metric`, `total_dilution`, `liquidity_runway`, `debt_maturity`, `revenue_quality`, `working_capital_flag`, `valuation_inflated_by`, `revenue_from`, `concentration_risk`
- Each edge has `confidence` and `confidence_score` fields

## Step 3C: Merge into extraction

```bash
$PYTHON -c "
import json
from pathlib import Path
chunk = json.loads(Path('graphify-out/.aag_chunk_01.json').read_text())
Path('graphify-out/.aag_semantic.json').write_text(json.dumps(chunk, indent=2))
ast = json.loads(Path('graphify-out/.aag_ast.json').read_text())
seen = {n['id'] for n in ast['nodes']}
merged_nodes = list(ast['nodes'])
for n in chunk['nodes']:
    if n['id'] not in seen:
        merged_nodes.append(n)
        seen.add(n['id'])
merged = {'nodes': merged_nodes, 'edges': ast['edges'] + chunk['edges'], 'hyperedges': chunk.get('hyperedges', []), 'input_tokens': 0, 'output_tokens': 0}
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

**Verify:** Domain extractors add nodes from financial tables

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
- `finance.concentration_risk_analyzer` returns >= 1 finding (MegaBank 19%)
- `diligence.red_flag_analyzer` may also fire on deferred revenue or related items

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
concentration = analysis.get('domain_analysis', {}).get('finance.concentration_risk_analyzer', [])

# Combine all findings for synthesis
all_flags = red_flags + concentration
prompts = synthesize_risks_offline(G, all_flags, key_persons)
Path('graphify-out/.aag_synthesis_prompts.json').write_text(json.dumps(prompts, indent=2))
print(f'Generated {len(prompts)} synthesis prompts')
for p in prompts:
    print(f'  - {p[\"label\"]} ({p[\"finding_count\"]} findings)')
"
```

**Verify:** At least 1 synthesis prompt generated

After reading the prompts, write narratives following the structure (What's happening / Who benefits / Why worse / What to investigate). Focus on:
- The combination of 6-month runway + $200M notes due in 18 months
- Adjusted EBITDA hiding $110M real loss behind $130M of exclusions
- AR growing 3x faster than revenue (channel stuffing signal)
- 75% potential dilution if all instruments convert

Inject narratives into `.aag_analysis.json` under `synthesized_narratives`.

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

# 2. Analyzer results
analysis = json.loads(Path('graphify-out/.aag_analysis.json').read_text())
da = analysis.get('domain_analysis', {})

# Finance concentration
conc = da.get('finance.concentration_risk_analyzer', [])
print(f'\n  Concentration risk findings: {len(conc)}')
if len(conc) < 1:
    errors.append(f'FAIL: Expected >= 1 concentration risk finding, got {len(conc)}')
for c in conc:
    print(f'    {c}')

# Diligence red flags
red_flags = da.get('diligence.red_flag_analyzer', [])
print(f'  Red flags: {len(red_flags)}')
for rf in red_flags:
    print(f'    [{rf[\"severity\"].upper():6}] {rf[\"type\"]}: {rf.get(\"label\",rf.get(\"node\",\"\"))[:60]}')

# 3. Narratives
narratives = analysis.get('synthesized_narratives', [])
print(f'\n  Narratives: {len(narratives)}')
if not narratives:
    errors.append('FAIL: No synthesized narratives')

# 4. Semantic extraction quality (check edges in graph)
from graphify.store import load as _gx_load
G = _gx_load('graphify-out')
edge_relations = set()
for u, v, d in G.edges(data=True):
    r = d.get('relation', '')
    if r:
        edge_relations.add(r)
print(f'\n  Unique edge relations in graph: {len(edge_relations)}')
print(f'    {sorted(edge_relations)[:15]}')

finance_edges = {'burn_rate', 'cash_flow_divergence', 'excludes_from_metric', 'total_dilution', 'liquidity_runway', 'debt_maturity', 'revenue_quality', 'working_capital_flag', 'valuation_inflated_by'}
found_finance = edge_relations & finance_edges
print(f'  Finance domain edges found: {len(found_finance)}/{len(finance_edges)}')
print(f'    Found: {sorted(found_finance)}')
if len(found_finance) < 3:
    errors.append(f'FAIL: Expected >= 3 finance domain edge types, got {len(found_finance)}: {sorted(found_finance)}')

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

Thresholds are set conservatively to allow for LLM variance in semantic extraction.

| Metric | Pass threshold | Notes |
|--------|---------------|-------|
| Nodes (semantic) | >= 20 | Companies, metrics, debt instruments, customers |
| Nodes (total after domain) | >= 30 | + table rows from financial statements |
| Concentration risk findings | >= 1 | MegaBank at 19% |
| Finance domain edge types | >= 3 of 9 | burn_rate, cash_flow_divergence, excludes_from_metric, etc. |
| Narratives | >= 1 | Financial risk narrative |
| Dashboard generated | Yes | |

## Key signals the LLM should extract

These are the finance-specific patterns embedded in the corpus:

1. **Burn rate:** Net loss $110M / Revenue $80M = 1.375x (losing $1.38 for every $1 earned)
2. **Cash flow divergence:** OCF = -$90M while Adjusted EBITDA = +$20M ($110M gap)
3. **Non-GAAP exclusions:** Stock comp $30M + restructuring $12M + D&A $18M = $60M stripped out
4. **Working capital flag:** AR grew 81% vs revenue grew 25% (DSO: 88→128 days)
5. **Debt maturity wall:** $200M due 2025 + $50M due 2026 = 80% of debt due within 2 years
6. **Total dilution:** 75M dilutive shares / 100M outstanding = 75% potential dilution
7. **Liquidity runway:** $45M cash / $90M annual burn = 6 months (going concern language present)
8. **Valuation inflation:** Series E at $8B by single investor vs current market cap $1.25B (84% decline)
9. **Revenue quality:** $8M acquired revenue = 50% of $16M growth (organic growth only 12.5%)
10. **Customer concentration:** MegaBank = 19% of revenue

## Notes

- This test focuses on the **finance** domain, complementing `minicorp-diligence/` which tests **diligence**
- The `concentration_risk_analyzer` is the main programmatic analyzer for finance
- Most finance red flags come from LLM-extracted semantic edges (burn_rate, cash_flow_divergence, etc.) rather than table parsers
- Total runtime excluding LLM: ~5 seconds
- Total runtime with LLM extraction: ~60-90 seconds
