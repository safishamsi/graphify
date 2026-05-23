# WeWork S-1 End-to-End Test Guide

Run this guide top-to-bottom to validate graphify's ability to detect financial red flags from an SEC filing.

## Prerequisites

- Python 3.11+, `uv` installed
- graphify installed: `uv pip install -e ".[test]"` from the aa-graphify repo
- An LLM API key in environment (GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY)
- ~5 minutes for extraction (LLM calls)

## Step 1: Download the S-1 Filing

```bash
mkdir -p /tmp/wework-s1/raw
curl -o /tmp/wework-s1/raw/d781982ds1.htm \
  "https://www.sec.gov/Archives/edgar/data/1533523/000119312519220499/d781982ds1.htm"
```

Verify: file should be ~15-25 MB.

```bash
ls -lh /tmp/wework-s1/raw/d781982ds1.htm
# Expected: ~24M
```

## Step 2: Install Skill and Build Graph (from Agent)

First, install the `pyaag` skill for your AI assistant. This uses your local Python environment directly, which is ideal for development:

```bash
# Using the local source
uv run python -m graphify pyinstall gemini
```

Now, **from within your AI assistant (e.g., Gemini CLI)**, run the extraction. This activates the specialized `finance` and `diligence` domains, performs clustering, and generates the audit report:

```bash
# Type this into your agent prompt:
/pyaag /tmp/wework-s1/raw --domain finance,diligence --db
```

Verify output exists:

```bash
ls /tmp/wework-s1/graphify-out/graph.db /tmp/wework-s1/graphify-out/.graphify_analysis.json
```

## Step 3: Verify Graph Structure

```python
from pathlib import Path
from graphify.store import load

G = load(Path("/tmp/wework-s1/graphify-out"))

assert G.number_of_nodes() >= 100, f"FAIL: Only {G.number_of_nodes()} nodes (need >=100)"
assert G.number_of_edges() >= 100, f"FAIL: Only {G.number_of_edges()} edges (need >=100)"

communities = {d.get("community") for _, d in G.nodes(data=True) if d.get("community") is not None}
assert len(communities) >= 5, f"FAIL: Only {len(communities)} communities (need >=5)"

print(f"PASS: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities")
```

## Step 4: Red Flag Detection

```python
from graphify.domains.diligence import red_flag_analyzer

red_flags = red_flag_analyzer(G)

assert len(red_flags) >= 10, f"FAIL: Only {len(red_flags)} red flags (need >=10)"

severities = {f.get("severity") for f in red_flags}
assert "high" in severities, "FAIL: No high-severity red flags found"

types = {f.get("type") for f in red_flags}
assert len(types) >= 2, f"FAIL: Only {len(types)} distinct red flag types (need >=2)"

high = sum(1 for f in red_flags if f.get("severity") == "high")
med = sum(1 for f in red_flags if f.get("severity") == "medium")
low = sum(1 for f in red_flags if f.get("severity") == "low")
print(f"PASS: {len(red_flags)} red flags ({high} high, {med} medium, {low} low), {len(types)} types")
```

## Step 5: Key Person Detection

```python
from graphify.domains.diligence import key_person_risk_analyzer

key_persons = key_person_risk_analyzer(G)

assert len(key_persons) >= 1, "FAIL: No key-person findings"
labels = " ".join(kp.get("label", "") for kp in key_persons).lower()
assert "neumann" in labels or "adam" in labels, f"FAIL: Adam Neumann not found in: {labels}"

print(f"PASS: {len(key_persons)} key person(s) detected, includes Neumann")
```

## Step 6: Dashboard Renders

```python
from pathlib import Path
from graphify.dashboard import render_dashboard

communities_dict = {}
for _, data in G.nodes(data=True):
    c = data.get("community")
    if c is not None:
        communities_dict.setdefault(str(c), []).append(data.get("label", ""))

analysis = {
    "communities": communities_dict,
    "gods": [],
    "surprises": [],
    "domain_analysis": {
        "diligence.red_flag_analyzer": red_flags,
        "diligence.key_person_risk_analyzer": key_persons,
    },
}
meta = {"nodes": G.number_of_nodes(), "edges": G.number_of_edges()}
out = Path("/tmp/wework-s1/graphify-out/dashboard.html")
render_dashboard(analysis, meta, out, G=G)

assert out.exists(), "FAIL: dashboard.html not created"
assert out.stat().st_size > 10_000, f"FAIL: dashboard too small ({out.stat().st_size} bytes)"
content = out.read_text()
assert "Knowledge Graph Dashboard" in content, "FAIL: missing title in dashboard"

print(f"PASS: dashboard.html generated ({out.stat().st_size:,} bytes)")
```

## Step 7: Weighted Recall Score (WRS)

This is the primary quality metric. It checks 8 known WeWork red flags against what the graph captured.

```python
import json

GROUND_TRUTH = [
    {"id": "founder_control", "weight": 3, "desc": "Neumann controls majority voting (Class B 20:1)"},
    {"id": "lease_mismatch", "weight": 3, "desc": "$47.2B lease obligations vs ~$2.5B cash"},
    {"id": "accelerating_losses", "weight": 2, "desc": "Losses doubled yearly 2016-2018"},
    {"id": "related_party_tx", "weight": 3, "desc": "CEO property leases, trademark, officer loans"},
    {"id": "key_person", "weight": 2, "desc": "Adam Neumann dependency"},
    {"id": "vie_structures", "weight": 1, "desc": "Variable interest entities (Creator Fund, Waller Creek)"},
    {"id": "no_profitability", "weight": 1, "desc": "Filing admits no path to profitability"},
    {"id": "softbank_concentration", "weight": 1, "desc": "$1B+ SoftBank convertible exposure"},
]

GRAPHIFY_OUT = Path("/tmp/wework-s1/graphify-out")

def check_founder_control():
    nodes = [d.get("label", "") for _, d in G.nodes(data=True) if "class b" in d.get("label", "").lower()]
    if nodes:
        return True, f"{len(nodes)} Class B nodes"
    for f in red_flags:
        if "control" in f.get("label", "").lower() or "voting" in f.get("label", "").lower():
            return True, f"red flag: {f.get('label', '')[:60]}"
    return False, "no evidence"

def check_lease_mismatch():
    for _, d in G.nodes(data=True):
        lbl = d.get("label", "")
        if "$47" in lbl or "47.2" in lbl or "47,232" in lbl:
            return True, f"node: {lbl[:80]}"
    return False, "no evidence"

def check_accelerating_losses():
    for f in red_flags:
        if "loss" in f.get("label", "").lower() and f.get("severity") == "high":
            return True, f"red flag: {f.get('label', '')[:60]}"
    loss_nodes = [d for _, d in G.nodes(data=True) if "net loss" in d.get("label", "").lower()]
    if len(loss_nodes) >= 2:
        return True, f"{len(loss_nodes)} Net Loss nodes"
    return False, "no evidence"

def check_related_party_tx():
    rp = [f for f in red_flags if f.get("type") == "related_party_exposure"]
    if rp:
        return True, f"{len(rp)} related_party_exposure flags"
    candidates_path = GRAPHIFY_OUT / ".aag_diligence_candidates.json"
    if candidates_path.exists():
        candidates = json.loads(candidates_path.read_text())
        loans = [c for c in candidates if c.get("type") == "officer_loan"]
        if len(loans) >= 3:
            return True, f"{len(loans)} officer_loan candidates"
    return False, "no evidence"

def check_key_person():
    for kp in key_persons:
        if "neumann" in kp.get("label", "").lower() or "adam" in kp.get("label", "").lower():
            return True, f"'{kp.get('label', '')}'"
    return False, "no evidence"

def check_vie_structures():
    vie = [f for f in red_flags if f.get("type") == "vie_consolidation"]
    if vie:
        return True, f"{len(vie)} vie_consolidation flags"
    vie_nodes = [d for _, d in G.nodes(data=True) if "vie" in d.get("label", "").lower()]
    if vie_nodes:
        return True, f"{len(vie_nodes)} VIE nodes"
    return False, "no evidence"

def check_no_profitability():
    for _, d in G.nodes(data=True):
        lbl = d.get("label", "").lower()
        if "profitab" in lbl or "unable to achieve" in lbl:
            return True, f"node: {d.get('label', '')[:60]}"
    for f in red_flags:
        if "profitab" in f.get("label", "").lower():
            return True, f"red flag: {f.get('label', '')[:60]}"
    return False, "no evidence"

def check_softbank_concentration():
    sb = [d for _, d in G.nodes(data=True) if "softbank" in d.get("label", "").lower()]
    if len(sb) >= 3:
        return True, f"{len(sb)} SoftBank nodes"
    return False, f"only {len(sb)} SoftBank nodes"

CHECKERS = {
    "founder_control": check_founder_control,
    "lease_mismatch": check_lease_mismatch,
    "accelerating_losses": check_accelerating_losses,
    "related_party_tx": check_related_party_tx,
    "key_person": check_key_person,
    "vie_structures": check_vie_structures,
    "no_profitability": check_no_profitability,
    "softbank_concentration": check_softbank_concentration,
}

total_weight = sum(f["weight"] for f in GROUND_TRUTH)
earned = 0

print()
print("=" * 60)
print(" WEIGHTED RECALL SCORE")
print("=" * 60)

for fact in GROUND_TRUTH:
    hit, evidence = CHECKERS[fact["id"]]()
    if hit:
        earned += fact["weight"]
    status = "[HIT] " if hit else "[MISS]"
    print(f" {status} {fact['id']:<22} (w={fact['weight']})  {evidence}")

wrs = earned / total_weight
print("-" * 60)
status_label = "PASS" if wrs >= 0.75 else "MARGINAL" if wrs >= 0.375 else "FAIL"
print(f" WRS: {wrs:.2f} ({earned}/{total_weight} pts)  Status: {status_label}")
print(f" Threshold: 0.375 | Target: 0.75")
print("=" * 60)

assert wrs >= 0.375, f"FAIL: WRS {wrs:.2f} below minimum 0.375"
```

## Step 8: Narrative Synthesis (Optional — requires LLM)

Skip this step if no LLM API key is available.

```python
from graphify.synthesize import synthesize_risks

narratives = synthesize_risks(G, red_flags, key_persons, max_entities=4)
narratives = [r for r in narratives if "error" not in r and "[Synthesis failed" not in r.get("narrative", "")]

NARRATIVE_EXPECTATIONS = {
    "related_party": {"weight": 3, "must_mention_any": ["convert", "dilut", "insider", "favorable", "$2.5"]},
    "financial_risk": {"weight": 2, "must_mention_any": ["loss", "$47", "lease", "cash", "profitab"]},
    "structural_complexity": {"weight": 1, "must_mention_any": ["vie", "consolidat", "control", "chinaco", "joint venture"]},
    "governance_control": {"weight": 2, "must_mention_any": ["neumann", "ceo", "depend", "conflict", "424 fifth"]},
}

total_weight = sum(v["weight"] for v in NARRATIVE_EXPECTATIONS.values())
earned = 0

print()
print("=" * 60)
print(" NARRATIVE QUALITY SCORE")
print("=" * 60)

for theme_id, expect in NARRATIVE_EXPECTATIONS.items():
    matched = next((n for n in narratives if n.get("theme") == theme_id), None)
    if not matched:
        print(f" [MISS] {theme_id:<22}  theme not generated")
        continue
    text = matched.get("narrative", "").lower()
    if len(text) < 100:
        print(f" [MISS] {theme_id:<22}  too short ({len(text)} chars)")
        continue
    hits = [kw for kw in expect["must_mention_any"] if kw in text]
    if hits:
        earned += expect["weight"]
        print(f" [HIT]  {theme_id:<22}  mentions: {', '.join(hits[:3])}")
    else:
        print(f" [MISS] {theme_id:<22}  none of {expect['must_mention_any']} found")

nqs = earned / total_weight
print("-" * 60)
status_label = "PASS" if nqs >= 0.75 else "MARGINAL" if nqs >= 0.375 else "FAIL"
print(f" NQS: {nqs:.2f} ({earned}/{total_weight} pts)  Status: {status_label}")
print("=" * 60)

assert nqs >= 0.375, f"FAIL: NQS {nqs:.2f} below minimum 0.375"
```

## Pass/Fail Summary

| Check | Threshold | Target |
|-------|-----------|--------|
| Nodes | >= 100 | - |
| Edges | >= 100 | - |
| Communities | >= 5 | - |
| Red flags count | >= 10 | - |
| High severity present | yes | - |
| Key person (Neumann) | detected | - |
| Dashboard size | > 10 KB | - |
| Weighted Recall Score | >= 0.375 | >= 0.75 |
| Narrative Quality Score | >= 0.375 | >= 0.75 |

## Cleanup

```bash
rm -rf /tmp/wework-s1
```
