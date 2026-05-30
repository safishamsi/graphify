# MiniCorp Diligence Domain E2E Test

This test verifies the diligence domain pipeline: semantic extraction with domain prompts → domain table extractors → red flag analyzer → narrative synthesis → dashboard.

## Prerequisites

Ensure you have installed the `pyaag` skill as described in `SETUP.md`:

```bash
uv run graphify pyinstall gemini
```

## Step 1: Setup

```bash
WORKDIR=/home/xfz/aa/aa-graphify-dev/examples/minicorp-diligence
cd $WORKDIR
rm -rf graphify-out
```

## Step 2: Run `/pyaag`

In your Gemini CLI session, run:

```bash
/pyaag . --domain finance,diligence
```

This will:
1.  **Detect** the `minicorp_s1.htm` file.
2.  **Convert** it to Markdown (Step 2.5a).
3.  **Extract** entities and relationships using the domain prompts.
4.  **Parse** the structured tables (Step 3D).
5.  **Build** the graph and run **Diligence Analyzers** (Step 4B).
6.  **Synthesize** narratives and generate the **Dashboard**.

## Step 3: Final Verification

Once the agent completes the extraction, run this script to confirm all outputs meet the quality thresholds:

```bash
PYTHON=python3
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

# 2. Red flags (baseline: ~9 findings, 4 HIGH)
analysis = json.loads(Path('graphify-out/.aag_analysis.json').read_text())
red_flags = analysis.get('domain_analysis', {}).get('diligence.red_flag_analyzer', [])
print(f'\n  Red flags: {len(red_flags)}')
if len(red_flags) < 7:
    errors.append(f'FAIL: Expected >= 7 red flags, got {len(red_flags)}')
high_flags = [f for f in red_flags if f.get(\"severity\") == \"high\"]
if len(high_flags) < 3:
    errors.append(f'FAIL: Expected >= 3 HIGH severity flags, got {len(high_flags)}')
else:
    print(f'  HIGH severity: {len(high_flags)}')

# 3. Narratives
narratives = analysis.get('synthesized_narratives', [])
print(f'\n  Narratives: {len(narratives)}')
if not narratives:
    errors.append('FAIL: No synthesized narratives')

# 4. Dashboard has red flags
dashboard = Path('graphify-out/dashboard.html').read_text()
if 'related_party_exposure' not in dashboard:
    errors.append('FAIL: dashboard.html missing red flag data')
else:
    print('  Dashboard: contains red flag data')

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

| Metric | Pass threshold | Observed baseline |
|--------|---------------|-------------------|
| Nodes (semantic) | >= 20 | 29 |
| Nodes (total after domain) | >= 35 | 48 |
| Red flags | >= 7, with >= 3 HIGH | 9 (4 HIGH, 5 MEDIUM) |
| Flag types | must include `related_party_exposure` | also saw `key_person_risk` |
| Synthesis prompts | >= 1 | 2 |
| Narratives | >= 1 | 2 |
| Dashboard red flags visible | Yes | Yes |

## Notes
- Total runtime with LLM extraction: ~60-90 seconds.
- The `/pyaag` skill handles the HTML→Markdown conversion automatically before sending to sub-agents.
