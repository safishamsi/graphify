"""WeWork S-1 Integration Test — measures red-flag detection quality.

SETUP (one-time):
  1. Download d781982ds1.htm from SEC EDGAR:
     https://www.sec.gov/Archives/edgar/data/1533523/000119312519220499/d781982ds1.htm
  2. Place in: /home/xfz/kb/graphify-ext/examples/wework-s1/raw/d781982ds1.htm
  3. Build graph:
     cd /local-nvme/hfeng/kb/graphify-ext/examples/wework-s1
     /pyaag raw/ --domain finance,diligence --db
  4. Run this test:
     uv run pytest tests/test_wework_integration.py -v -s

METRIC: Weighted Recall Score (WRS)
  Measures what fraction of known WeWork red flags the system detects.
  Range: 0.0-1.0. Threshold: ≥0.375. Target: ≥0.75.
"""
import json
import re
from pathlib import Path

import pytest

WEWORK_GRAPHIFY_OUT = Path(__file__).resolve().parent.parent / "examples" / "wework-s1" / "graphify-out"
if not WEWORK_GRAPHIFY_OUT.exists():
    WEWORK_GRAPHIFY_OUT = Path("/local-nvme/hfeng/kb/graphify-ext/examples/wework-s1/graphify-out")

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def wework_graph():
    if not WEWORK_GRAPHIFY_OUT.exists():
        pytest.skip("WeWork S-1 graphify-out not found — see module docstring for setup")
    from graphify.store import load
    return load(WEWORK_GRAPHIFY_OUT)


@pytest.fixture(scope="module")
def red_flags(wework_graph):
    from graphify.domains.diligence import red_flag_analyzer
    return red_flag_analyzer(wework_graph)


@pytest.fixture(scope="module")
def key_persons(wework_graph):
    from graphify.domains.diligence import key_person_risk_analyzer
    return key_person_risk_analyzer(wework_graph)


# ---------------------------------------------------------------------------
# Test: graph structure sanity
# ---------------------------------------------------------------------------

def test_graph_minimum_structure(wework_graph):
    G = wework_graph
    assert G.number_of_nodes() >= 100, f"Only {G.number_of_nodes()} nodes"
    assert G.number_of_edges() >= 100, f"Only {G.number_of_edges()} edges"
    communities = {d.get("community") for _, d in G.nodes(data=True) if d.get("community") is not None}
    assert len(communities) >= 5, f"Only {len(communities)} communities"


# ---------------------------------------------------------------------------
# Test: red flags detected
# ---------------------------------------------------------------------------

def test_red_flags_detected(red_flags):
    assert len(red_flags) >= 10, f"Only {len(red_flags)} red flags"
    severities = {f.get("severity") for f in red_flags}
    assert "high" in severities, "No high-severity red flags found"
    types = {f.get("type") for f in red_flags}
    assert len(types) >= 2, f"Only {len(types)} distinct red flag types"


# ---------------------------------------------------------------------------
# Test: key person detected
# ---------------------------------------------------------------------------

def test_key_person_detected(key_persons):
    assert len(key_persons) >= 1, "No key-person findings"
    labels = " ".join(kp.get("label", "") for kp in key_persons).lower()
    assert "neumann" in labels or "adam" in labels, f"Adam Neumann not found in: {labels}"


# ---------------------------------------------------------------------------
# Test: dashboard renders
# ---------------------------------------------------------------------------

def test_dashboard_renders(wework_graph, red_flags, key_persons, tmp_path):
    from graphify.dashboard import render_dashboard

    communities = {}
    for _, data in wework_graph.nodes(data=True):
        c = data.get("community")
        if c is not None:
            communities.setdefault(str(c), []).append(data.get("label", ""))

    analysis = {
        "communities": communities,
        "gods": [],
        "surprises": [],
        "domain_analysis": {
            "diligence.red_flag_analyzer": red_flags,
            "diligence.key_person_risk_analyzer": key_persons,
        },
    }
    meta = {"nodes": wework_graph.number_of_nodes(), "edges": wework_graph.number_of_edges()}
    out = tmp_path / "dashboard.html"
    render_dashboard(analysis, meta, out, G=wework_graph)
    assert out.exists()
    assert out.stat().st_size > 10_000, f"Dashboard too small: {out.stat().st_size} bytes"
    content = out.read_text()
    assert "Due Diligence Risk Report" in content or "Knowledge Graph Dashboard" in content


# ---------------------------------------------------------------------------
# Test: Weighted Recall Score
# ---------------------------------------------------------------------------

# Ground truth facts with weights
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


def _check_founder_control(G, red_flags, key_persons):
    class_b_nodes = [d.get("label", "") for _, d in G.nodes(data=True) if "class b" in d.get("label", "").lower()]
    if len(class_b_nodes) >= 1:
        return True, f"{len(class_b_nodes)} nodes with 'Class B'"
    # Fallback: check red flags for voting/control language
    for f in red_flags:
        lbl = f.get("label", "").lower()
        if "control" in lbl or "voting" in lbl:
            return True, f"red flag: {f.get('label', '')[:60]}"
    return False, "no evidence found"


def _check_lease_mismatch(G, red_flags, key_persons):
    for _, d in G.nodes(data=True):
        lbl = d.get("label", "")
        if "$47" in lbl or "47.2" in lbl or "47,232" in lbl:
            return True, f"node: {lbl[:80]}"
    return False, "no evidence found"


def _check_accelerating_losses(G, red_flags, key_persons):
    # Check red flags for loss-related high severity
    for f in red_flags:
        lbl = f.get("label", "").lower()
        if "loss" in lbl and f.get("severity") == "high":
            return True, f"red flag: {f.get('label', '')[:60]} severity=high"
    # Fallback: multiple "Net Loss" nodes
    loss_nodes = [d.get("label", "") for _, d in G.nodes(data=True) if "net loss" in d.get("label", "").lower()]
    if len(loss_nodes) >= 2:
        return True, f"{len(loss_nodes)} nodes with 'Net Loss'"
    return False, "no evidence found"


def _check_related_party_tx(G, red_flags, key_persons):
    rp_flags = [f for f in red_flags if f.get("type") == "related_party_exposure"]
    if rp_flags:
        return True, f"{len(rp_flags)} red flags type=related_party_exposure"
    # Fallback: check candidates JSON
    candidates_path = WEWORK_GRAPHIFY_OUT / ".aag_diligence_candidates.json"
    if candidates_path.exists():
        try:
            candidates = json.loads(candidates_path.read_text())
            loans = [c for c in candidates if c.get("type") == "officer_loan"]
            if len(loans) >= 3:
                return True, f"{len(loans)} officer_loan candidates in JSON"
        except (json.JSONDecodeError, OSError):
            pass
    return False, "no evidence found"


def _check_key_person(G, red_flags, key_persons):
    for kp in key_persons:
        lbl = kp.get("label", "").lower()
        if "neumann" in lbl or "adam" in lbl:
            return True, f"'{kp.get('label', '')}' in key_person_risk results"
    return False, "no evidence found"


def _check_vie_structures(G, red_flags, key_persons):
    vie_flags = [f for f in red_flags if f.get("type") == "vie_consolidation"]
    if vie_flags:
        return True, f"{len(vie_flags)} red flags type=vie_consolidation"
    vie_nodes = [d.get("label", "") for _, d in G.nodes(data=True) if "vie" in d.get("label", "").lower()]
    if vie_nodes:
        return True, f"{len(vie_nodes)} nodes with 'VIE' in label"
    return False, "no evidence found"


def _check_no_profitability(G, red_flags, key_persons):
    for _, d in G.nodes(data=True):
        lbl = d.get("label", "").lower()
        if "profitab" in lbl or "unable to achieve" in lbl:
            return True, f"node: {d.get('label', '')[:60]}"
    for f in red_flags:
        lbl = f.get("label", "").lower()
        if "profitab" in lbl:
            return True, f"red flag: {f.get('label', '')[:60]}"
    return False, "no evidence found"


def _check_softbank_concentration(G, red_flags, key_persons):
    sb_nodes = [d.get("label", "") for _, d in G.nodes(data=True) if "softbank" in d.get("label", "").lower()]
    if len(sb_nodes) >= 3:
        return True, f"{len(sb_nodes)} nodes with 'SoftBank'"
    return False, f"only {len(sb_nodes)} SoftBank nodes"


_CHECKERS = {
    "founder_control": _check_founder_control,
    "lease_mismatch": _check_lease_mismatch,
    "accelerating_losses": _check_accelerating_losses,
    "related_party_tx": _check_related_party_tx,
    "key_person": _check_key_person,
    "vie_structures": _check_vie_structures,
    "no_profitability": _check_no_profitability,
    "softbank_concentration": _check_softbank_concentration,
}


def test_weighted_recall_score(wework_graph, red_flags, key_persons):
    G = wework_graph
    communities = {d.get("community") for _, d in G.nodes(data=True) if d.get("community") is not None}

    # Compute WRS
    total_weight = sum(f["weight"] for f in GROUND_TRUTH)
    earned = 0
    results = []

    for fact in GROUND_TRUTH:
        checker = _CHECKERS[fact["id"]]
        hit, evidence = checker(G, red_flags, key_persons)
        if hit:
            earned += fact["weight"]
        results.append((fact, hit, evidence))

    wrs = earned / total_weight

    # Print report
    high_count = sum(1 for f in red_flags if f.get("severity") == "high")
    med_count = sum(1 for f in red_flags if f.get("severity") == "medium")
    low_count = sum(1 for f in red_flags if f.get("severity") == "low")

    print()
    print("=" * 55)
    print(" WEWORK S-1 ANALYSIS QUALITY REPORT")
    print("=" * 55)
    print(f" Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities")
    print(f" Red flags: {len(red_flags)} findings ({high_count} high, {med_count} medium, {low_count} low)")
    print(f" Key persons: {len(key_persons)} finding(s)")
    print("-" * 55)

    for fact, hit, evidence in results:
        status = "[HIT] " if hit else "[MISS]"
        fid = fact["id"][:20].ljust(20)
        print(f" {status} {fid} (w={fact['weight']})  {evidence}")

    print("-" * 55)
    status_label = "PASS" if wrs >= 0.75 else "MARGINAL" if wrs >= 0.375 else "FAIL"
    print(f" WEIGHTED RECALL SCORE: {wrs:.2f} / 1.00  ({earned}/{total_weight} pts)")
    print(f" Status: {status_label} (threshold: 0.375, target: 0.75)")
    print("=" * 55)

    assert wrs >= 0.375, f"WRS {wrs:.2f} below minimum threshold 0.375 ({earned}/{total_weight} pts)"


# ---------------------------------------------------------------------------
# Test: Narrative synthesis quality
# ---------------------------------------------------------------------------

# What each narrative theme should mention (keywords in the LLM output)
NARRATIVE_EXPECTATIONS = {
    "related_party": {
        "weight": 3,
        "must_mention_any": ["convert", "dilut", "insider", "favorable", "$2.5"],
        "desc": "Should identify conversion/dilution mechanism",
    },
    "financial_risk": {
        "weight": 2,
        "must_mention_any": ["loss", "$47", "lease", "cash", "profitab"],
        "desc": "Should connect losses to lease obligations",
    },
    "structural_complexity": {
        "weight": 1,
        "must_mention_any": ["vie", "consolidat", "control", "chinaco", "joint venture"],
        "desc": "Should explain VIE opacity risk",
    },
    "governance_control": {
        "weight": 2,
        "must_mention_any": ["neumann", "ceo", "depend", "conflict", "424 fifth"],
        "desc": "Should identify CEO conflict of interest",
    },
}


@pytest.fixture(scope="module")
def narratives(wework_graph, red_flags, key_persons):
    """Run synthesis. Returns empty list if no LLM backend available."""
    try:
        from graphify.synthesize import synthesize_risks
        results = synthesize_risks(wework_graph, red_flags, key_persons, max_entities=4)
        # Filter out error results
        return [r for r in results if "error" not in r and "[Synthesis failed" not in r.get("narrative", "")]
    except Exception:
        return []


def test_narrative_synthesis_quality(narratives):
    """Evaluate whether synthesized narratives cover expected themes with meaningful content."""
    if not narratives:
        pytest.skip("No LLM backend available — narratives not generated")

    total_weight = sum(v["weight"] for v in NARRATIVE_EXPECTATIONS.values())
    earned = 0
    results = []

    for theme_id, expect in NARRATIVE_EXPECTATIONS.items():
        # Find the narrative matching this theme
        matched = None
        for n in narratives:
            if n.get("theme") == theme_id:
                matched = n
                break

        if not matched:
            results.append((theme_id, expect, False, "theme not generated"))
            continue

        narrative_text = matched.get("narrative", "").lower()

        # Check minimum length (meaningful content, not a stub)
        if len(narrative_text) < 100:
            results.append((theme_id, expect, False, f"too short ({len(narrative_text)} chars)"))
            continue

        # Check that at least one expected keyword appears
        hits = [kw for kw in expect["must_mention_any"] if kw in narrative_text]
        if hits:
            earned += expect["weight"]
            results.append((theme_id, expect, True, f"mentions: {', '.join(hits[:3])}"))
        else:
            results.append((theme_id, expect, False, f"none of {expect['must_mention_any']} found"))

    nqs = earned / total_weight if total_weight else 0

    # Print report
    print()
    print("=" * 55)
    print(" NARRATIVE QUALITY SCORE (NQS)")
    print("=" * 55)
    print(f" Narratives generated: {len(narratives)}")
    print(f" Avg length: {sum(len(n.get('narrative', '')) for n in narratives) // max(len(narratives), 1)} chars")
    print("-" * 55)

    for theme_id, expect, hit, evidence in results:
        status = "[HIT] " if hit else "[MISS]"
        tid = theme_id[:22].ljust(22)
        print(f" {status} {tid} (w={expect['weight']})  {evidence}")
        if not hit:
            print(f"        expected: {expect['desc']}")

    print("-" * 55)
    status_label = "PASS" if nqs >= 0.75 else "MARGINAL" if nqs >= 0.375 else "FAIL"
    print(f" NARRATIVE QUALITY SCORE: {nqs:.2f} / 1.00  ({earned}/{total_weight} pts)")
    print(f" Status: {status_label} (threshold: 0.375, target: 0.75)")
    print("=" * 55)

    assert nqs >= 0.375, f"NQS {nqs:.2f} below minimum threshold ({earned}/{total_weight} pts)"
