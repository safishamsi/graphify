"""Generate a self-contained dashboard.html from .graphify_analysis.json."""
from __future__ import annotations

import json
import re
from pathlib import Path


def _compute_domain_nodes_by_type(G) -> dict:
    """Section 1: Group nodes with a domain attribute by type, top 10 per type by degree."""
    from collections import defaultdict
    by_type: dict[str, list] = defaultdict(list)
    for node, data in G.nodes(data=True):
        domain = data.get("domain")
        if not domain:
            continue
        ntype = data.get("type", "unknown")
        by_type[ntype].append({
            "id": node,
            "label": data.get("label", str(node)),
            "domain": domain,
            "degree": G.degree(node),
        })
    # Keep top 10 per type by degree
    result = {}
    for t, items in by_type.items():
        items.sort(key=lambda x: x["degree"], reverse=True)
        result[t] = items[:10]
    return result


def _compute_related_party_edges(G) -> list:
    """Section 2: Related-party transaction edges."""
    target_relations = {
        "loan_to_officer", "ip_transfer", "asset_leaseback",
        "related_party_transaction", "self_dealing", "proceeds_to_insider",
        "nepotism", "conflict_of_interest",
    }
    results = []
    for u, v, data in G.edges(data=True):
        rel = data.get("relation", "")
        if rel in target_relations:
            results.append({
                "source_label": G.nodes[u].get("label", str(u)),
                "target_label": G.nodes[v].get("label", str(v)),
                "relation": rel,
                "confidence": data.get("confidence", ""),
                "confidence_score": data.get("confidence_score", data.get("confidence", "")),
            })
    return results


def _parse_amount(text: str) -> float:
    """Try to parse a dollar amount from text for sorting."""
    # Look for $X,XXX patterns
    m = re.search(r'\$([\d,]+(?:\.\d+)?)', text)
    if m:
        val = float(m.group(1).replace(",", ""))
        # Check for million/billion suffix after the number
        after = text[m.end():m.end() + 20].lower()
        if "billion" in after:
            val *= 1_000_000_000
        elif "million" in after:
            val *= 1_000_000
        return val
    # Look for "X million" or "X billion" patterns
    m = re.search(r'([\d,]+(?:\.\d+)?)\s*(million|billion)', text, re.IGNORECASE)
    if m:
        val = float(m.group(1).replace(",", ""))
        if m.group(2).lower() == "billion":
            val *= 1_000_000_000
        else:
            val *= 1_000_000
        return val
    return 0.0


def _compute_financial_obligations(G) -> list:
    """Section 3: Nodes whose labels contain dollar amounts."""
    pattern = re.compile(r'\$[\d,.]+|million|billion', re.IGNORECASE)
    results = []
    for node, data in G.nodes(data=True):
        label = data.get("label", str(node))
        if pattern.search(label):
            amount_match = re.search(r'\$[\d,.]+(?:\s*(?:million|billion))?', label, re.IGNORECASE)
            amount_raw = amount_match.group(0) if amount_match else label[:50]
            results.append({
                "label": label,
                "amount_raw": amount_raw,
                "domain": data.get("domain", ""),
                "community": data.get("community", ""),
                "_sort_val": _parse_amount(label),
            })
    results.sort(key=lambda x: x["_sort_val"], reverse=True)
    results = results[:30]
    for r in results:
        del r["_sort_val"]
    return results


def _compute_cross_domain_bridges(G) -> list:
    """Section 4: Edges where source and target have different domains."""
    results = []
    for u, v, data in G.edges(data=True):
        u_domain = G.nodes[u].get("domain")
        v_domain = G.nodes[v].get("domain")
        if u_domain and v_domain and u_domain != v_domain:
            results.append({
                "source_label": G.nodes[u].get("label", str(u)),
                "source_domain": u_domain,
                "target_label": G.nodes[v].get("label", str(v)),
                "target_domain": v_domain,
                "relation": data.get("relation", ""),
            })
    return results[:20]


def _compute_community_domain_mix(G) -> dict:
    """Section 5: For each community, count finance/diligence/other nodes."""
    from collections import defaultdict
    mix: dict[str, dict] = defaultdict(lambda: {"finance": 0, "diligence": 0, "other": 0, "total": 0})
    for node, data in G.nodes(data=True):
        comm = data.get("community")
        if comm is None:
            continue
        comm_key = str(comm)
        domain = data.get("domain", "")
        mix[comm_key]["total"] += 1
        if domain == "finance":
            mix[comm_key]["finance"] += 1
        elif domain == "diligence":
            mix[comm_key]["diligence"] += 1
        else:
            mix[comm_key]["other"] += 1
    return dict(mix)


_CANDIDATE_TYPE_LABELS = {
    "officer_loan": "Possible Loan to/from Officer",
    "related_party_lease": "Related-Party Lease",
    "insider_transaction": "Insider Transaction",
    "self_dealing": "Potential Self-Dealing",
}


def _clean_window_text(text: str) -> str:
    """Clean raw extracted text: collapse whitespace, remove HTML artifacts."""
    import re
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n", "\n", text)
    text = re.sub(r"^\s+", "", text, flags=re.MULTILINE)
    return text.strip()


def _generate_candidate_finding(item: dict) -> str:
    """Generate a layman-readable description of what this candidate means."""
    ctype = item.get("type", "")
    amount = item.get("amount", "")
    window = _clean_window_text(item.get("window", ""))

    if ctype == "officer_loan":
        # Try to identify what the money is for from context
        wl = window.lower()
        if "convertible" in wl and "note" in wl:
            return (
                f"A convertible note worth {amount} involves a related party. "
                "This means an insider holds debt that could convert to ownership shares, "
                "giving them preferential treatment over regular shareholders."
            )
        elif "repurchase" in wl and ("stock" in wl or "share" in wl):
            return (
                f"The company repurchased {amount} in shares from an insider. "
                "If the price paid exceeded fair market value, this may be a way "
                "to funnel cash to insiders disguised as a stock transaction."
            )
        elif "lease" in wl or "rent" in wl:
            return (
                f"A {amount} financial arrangement involves property leased from "
                "or to a company insider. The company may be overpaying rent to "
                "enrich an officer who is also the landlord."
            )
        elif "promissory" in wl or "loan" in wl:
            return (
                f"A {amount} promissory note or loan involves a related party. "
                "Money flowing between the company and its insiders creates conflicts "
                "of interest — the insider benefits regardless of company performance."
            )
        elif "acqui" in wl or "investment" in wl:
            return (
                f"A {amount} acquisition or investment involves a related party. "
                "Insiders may be selling assets to the company at inflated prices, "
                "or the company may be funding entities that benefit insiders."
            )
        else:
            return (
                f"A {amount} financial transaction may involve a company officer or insider. "
                "This requires review to determine whether the terms are fair to shareholders "
                "or if insiders are extracting value."
            )
    return f"A {amount} transaction of type '{ctype}' needs review to confirm whether it represents a conflict of interest."


def _compute_pending_candidates(out_path: Path) -> list:
    """Section 6: Read .aag_diligence_candidates.json if it exists."""
    candidates_path = out_path.parent / ".aag_diligence_candidates.json"
    if not candidates_path.exists():
        return []
    try:
        raw = json.loads(candidates_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    results = []
    for item in raw:
        window = _clean_window_text(item.get("window", ""))
        results.append({
            "type": _CANDIDATE_TYPE_LABELS.get(item.get("type", ""), item.get("type", "")),
            "amount": item.get("amount", ""),
            "finding": _generate_candidate_finding(item),
            "context": window[:400],
        })
    return results


def render_dashboard(analysis: dict, graph_meta: dict, out_path: Path, G=None) -> Path:
    """Write dashboard.html embedding analysis data. Returns the output path."""
    extra = {}
    if G is not None:
        extra["domain_nodes_by_type"] = _compute_domain_nodes_by_type(G)
        extra["related_party_edges"] = _compute_related_party_edges(G)
        extra["financial_obligations"] = _compute_financial_obligations(G)
        extra["cross_domain_bridges"] = _compute_cross_domain_bridges(G)
        extra["community_domain_mix"] = _compute_community_domain_mix(G)
        extra["pending_candidates"] = _compute_pending_candidates(out_path)
    extra["narratives"] = analysis.get("synthesized_narratives", [])

    payload = json.dumps({"analysis": analysis, "meta": graph_meta, "extra": extra}, indent=None)
    html = _TEMPLATE.replace("/*__DATA__*/", f"const DATA = {payload};")
    out_path.write_text(html, encoding="utf-8")
    return out_path


def render_dashboard_from_file(analysis_path: Path, graph_path: Path | None = None) -> Path:
    """Convenience: read analysis JSON from disk, generate dashboard next to it."""
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    # Derive basic graph meta from analysis if no graph available
    meta: dict = {}
    G = None
    if graph_path and graph_path.exists():
        from graphify.store import load
        G = load(graph_path.parent)
        meta = {"nodes": len(G), "edges": G.size()}
    else:
        communities = analysis.get("communities", {})
        node_count = sum(len(v) for v in communities.values())
        meta = {"nodes": node_count, "edges": 0}
    out_path = analysis_path.parent / "dashboard.html"
    return render_dashboard(analysis, meta, out_path, G=G)


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Due Diligence Risk Report</title>
<style>
:root, [data-theme="light"] {
  --bg: #f8f9fb; --fg: #1a1a2e; --card: #ffffff; --border: #e2e8f0;
  --accent: #2563eb; --accent-soft: #eff6ff;
  --danger: #b91c1c; --danger-soft: #fef2f2;
  --warn: #b45309; --warn-soft: #fffbeb;
  --ok: #047857; --ok-soft: #ecfdf5;
  --muted: #64748b; --subtle: #f8fafc;
  --finance: #2563eb; --diligence: #b91c1c; --other: #64748b;
  --shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.03);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.04);
  --radius: 8px;
  --bg-offset: #f1f5f9;
  --font-mono: 'SF Mono', 'Fira Code', 'JetBrains Mono', monospace;
}
[data-theme="dark"] {
    --bg: #0f172a; --fg: #e2e8f0; --card: #1e293b; --border: #334155;
    --accent: #60a5fa; --accent-soft: #1e3a5f;
    --danger: #f87171; --danger-soft: #3b1c1c;
    --warn: #fbbf24; --warn-soft: #3b2e1c;
    --ok: #34d399; --ok-soft: #1c3b2e;
    --muted: #94a3b8; --subtle: #1e293b;
    --finance: #60a5fa; --diligence: #f87171; --other: #94a3b8;
    --shadow: 0 1px 3px rgba(0,0,0,0.3); --shadow-md: 0 4px 6px rgba(0,0,0,0.3);
    --bg-offset: rgba(255,255,255,0.03);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0f172a; --fg: #e2e8f0; --card: #1e293b; --border: #334155;
    --accent: #60a5fa; --accent-soft: #1e3a5f;
    --danger: #f87171; --danger-soft: #3b1c1c;
    --warn: #fbbf24; --warn-soft: #3b2e1c;
    --ok: #34d399; --ok-soft: #1c3b2e;
    --muted: #94a3b8; --subtle: #1e293b;
    --finance: #60a5fa; --diligence: #f87171; --other: #94a3b8;
    --shadow: 0 1px 3px rgba(0,0,0,0.3); --shadow-md: 0 4px 6px rgba(0,0,0,0.3);
    --bg-offset: rgba(255,255,255,0.03);
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: auto; }
body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 16px; background: var(--bg); color: var(--fg); line-height: 1.55; -webkit-font-smoothing: antialiased; }

.shell { display: flex; flex-direction: column; min-height: 100vh; max-width: 1440px; margin: 0 auto; padding: 1.5rem 2.5rem 3rem; }

/* Report header */
.report-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1.5rem; padding-bottom: 1.25rem; border-bottom: 2px solid var(--border); }
.report-header-left { display: flex; flex-direction: column; gap: 0.25rem; }
.report-title { font-size: 1.6rem; font-weight: 800; letter-spacing: -0.03em; color: var(--fg); }
.report-subject { font-size: 1rem; font-weight: 500; color: var(--accent); }
.report-meta { font-size: 0.85rem; color: var(--muted); margin-top: 0.2rem; }
.report-header-right { display: flex; align-items: center; gap: 0.5rem; }
.theme-toggle { width: 34px; height: 34px; border-radius: 50%; border: 1px solid var(--border); background: var(--card); cursor: pointer; font-size: 1rem; display: flex; align-items: center; justify-content: center; transition: background 0.2s, border-color 0.2s; flex-shrink: 0; }
.theme-toggle:hover { background: var(--accent-soft); border-color: var(--accent); }
.theme-toggle::after { content: '\263d'; }
[data-theme="dark"] .theme-toggle::after { content: '\2600'; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .theme-toggle::after { content: '\2600'; } }

/* KPI strip */
.kpi-strip { display: flex; gap: 0.6rem; margin-bottom: 1.5rem; flex-shrink: 0; flex-wrap: wrap; }
.kpi { background: var(--card); border-radius: var(--radius); padding: 0.9rem 1.25rem; box-shadow: var(--shadow); border-top: 3px solid var(--accent); display: flex; flex-direction: column; align-items: flex-start; min-width: 110px; }
.kpi-danger { border-top-color: var(--danger); }
.kpi-warn { border-top-color: var(--warn); }
.kpi .kpi-value { font-size: 1.75rem; font-weight: 800; line-height: 1.1; }
.kpi .kpi-label { font-size: 0.78rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-top: 0.2rem; }
.kpi .kpi-sub { font-size: 0.72rem; color: var(--danger); font-weight: 600; }

/* Tabs */
.tab-bar { display: flex; gap: 0; border-bottom: 2px solid var(--border); margin-bottom: 0; flex-shrink: 0; }
.tab { padding: 0.6rem 1.4rem; font-size: 0.88rem; font-weight: 600; color: var(--muted); cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px; transition: color 0.15s, border-color 0.15s; user-select: none; letter-spacing: 0.01em; }
.tab:hover { color: var(--fg); }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }

/* Tab content */
.tab-content { display: none; padding-top: 1.25rem; }
.tab-content.active { display: grid; }

/* Two-col layout inside tabs */
.col-layout { display: grid; grid-template-columns: 3fr 2fr; gap: 1rem; }
@media (max-width: 900px) { .col-layout { grid-template-columns: 1fr; } }

/* Panels */
.panel { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.25rem 1.5rem; box-shadow: var(--shadow); min-height: 0; }
.panel-danger { border-left: 4px solid var(--danger); }
.panel-warn { border-left: 4px solid var(--warn); }
.panel-accent { border-left: 4px solid var(--accent); }
.panel h2 { font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin-bottom: 0.3rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border); }
.panel .section-desc { font-size: 0.84rem; color: var(--muted); margin-bottom: 0.9rem; line-height: 1.45; }
.panel-stack { display: flex; flex-direction: column; gap: 1.25rem; min-height: 0; }

/* Tables */
table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
thead { position: sticky; top: 0; background: var(--card); z-index: 1; }
th { padding: 0.55rem 0.7rem; text-align: left; font-weight: 600; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); border-bottom: 2px solid var(--border); cursor: pointer; user-select: none; white-space: nowrap; }
th:hover { color: var(--accent); }
td { padding: 0.5rem 0.7rem; border-bottom: 1px solid var(--border); }
tbody tr:nth-child(even) { background: var(--bg-offset); }
tbody tr:hover { background: var(--accent-soft); }

/* Badges */
.badge { display: inline-flex; align-items: center; padding: 0.2rem 0.55rem; border-radius: 10px; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.02em; }
.badge-high { background: var(--danger-soft); color: var(--danger); }
.badge-medium { background: var(--warn-soft); color: var(--warn); }
.badge-low { background: var(--ok-soft); color: var(--ok); }
.badge-finance { background: var(--accent-soft); color: var(--finance); }
.badge-diligence { background: var(--danger-soft); color: var(--diligence); }
.badge-other { background: var(--subtle); color: var(--other); }

/* Risk tab nav */
.risk-nav { display: flex; gap: 0.4rem; padding: 0.5rem 0.7rem; background: var(--card); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 1rem; position: sticky; top: 0; z-index: 10; }
.risk-nav-item { font-size: 0.88rem; font-weight: 600; padding: 0.35rem 0.7rem; border-radius: 5px; color: var(--muted); text-decoration: none; transition: background 0.15s, color 0.15s; }
.risk-nav-item:hover { background: var(--accent-soft); color: var(--accent); }

/* Risk tab layout */
.risk-layout { display: flex; flex-direction: column; gap: 1.5rem; }
.risk-mid-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }
@media (max-width: 900px) { .risk-mid-row { grid-template-columns: 1fr; } }
.panel-muted { border-left: 4px solid var(--border); }
.pending-head { display: flex; align-items: center; gap: 0.8rem; }
.pending-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 0.6rem; }
/* Key-person cards */
.kp-card { border: 1px solid var(--border); border-radius: 6px; padding: 0.6rem 0.8rem; margin-bottom: 0.5rem; }
.kp-card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.3rem; }
.kp-name { font-weight: 600; font-size: 0.95rem; }
.kp-stats { display: flex; gap: 1.2rem; font-size: 0.85rem; color: var(--muted); }
.kp-frag-high { color: var(--danger); font-weight: 600; }

/* Red flag type labels */
.rf-type-cell { max-width: 180px; }
.rf-type-name { font-weight: 600; font-size: 0.88rem; }
.rf-type-hint { font-size: 0.78rem; color: var(--muted); line-height: 1.3; margin-top: 0.15rem; }
/* Red flag finding */
.rf-finding-cell { max-width: 480px; }
.rf-finding { font-size: 0.9rem; line-height: 1.5; }
.rf-raw-label { font-size: 0.78rem; color: var(--muted); margin-top: 0.3rem; font-family: var(--font-mono, monospace); white-space: pre-wrap; word-break: break-word; }

/* Pending candidates */
.pending-card { border: 1px solid var(--border); border-radius: 6px; padding: 0.7rem 0.9rem; margin-bottom: 0.5rem; }
.pending-header { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.4rem; }
.pending-amount { font-weight: 700; font-size: 0.95rem; }
.pending-finding { font-size: 0.9rem; line-height: 1.5; margin-bottom: 0.4rem; }
.pending-ctx-row { display: flex; align-items: center; gap: 0.4rem; }
.pending-context { font-size: 0.8rem; font-family: var(--font-mono, monospace); white-space: pre-wrap; word-break: break-word; line-height: 1.4; color: var(--muted); margin-top: 0.3rem; padding: 0.4rem 0.6rem; background: var(--bg-offset, #f8f9fa); border-radius: 4px; max-height: 10em; overflow-y: auto; }

/* Evidence drawer */
.evidence-table-wrap table { width: 100%; }
.evidence-btn { background: var(--subtle); border: 1px solid var(--border); border-radius: 3px; cursor: pointer; font-size: 0.8rem; width: 1.5em; height: 1.5em; display: flex; align-items: center; justify-content: center; color: var(--text); }
.evidence-btn:hover { background: var(--border); }
.evidence-drawer { background: var(--bg-offset, #f8f9fa); }
.evidence-cell { padding: 0.6rem 1rem !important; border-left: 3px solid var(--accent); }
.ev-section { margin-bottom: 0.4rem; font-size: 0.85rem; line-height: 1.4; }
.ev-label { font-weight: 600; color: var(--muted); }
.ev-desc { font-style: italic; color: var(--muted); }
.xref-block { background: var(--accent-soft, rgba(59,130,246,0.06)); border-radius: 4px; padding: 0.5rem 0.7rem; margin-top: 0.3rem; }
.xref-block .ev-label { color: var(--accent); font-size: 0.82rem; }
.ev-excerpt { font-family: var(--font-mono, monospace); font-size: 0.8rem; color: var(--text); white-space: pre-wrap; margin-top: 0.2rem; max-height: 8em; overflow-y: auto; }
[data-theme="dark"] .evidence-drawer { background: rgba(255,255,255,0.03); }
[data-theme="dark"] .xref-block { background: rgba(59,130,246,0.08); }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .evidence-drawer { background: rgba(255,255,255,0.03); } :root:not([data-theme="light"]) .xref-block { background: rgba(59,130,246,0.08); } }

/* Bar charts */
.bar-item { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.4rem; }
.bar-label { font-size: 0.88rem; font-weight: 500; min-width: 140px; max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar-track { flex: 1; height: 7px; border-radius: 4px; background: var(--border); overflow: hidden; }
.bar-fill { height: 100%; border-radius: 4px; }
.bar-fill-accent { background: var(--accent); }
.bar-fill-danger { background: var(--danger); }
.bar-fill-ok { background: var(--ok); }
.bar-val { font-size: 0.82rem; color: var(--muted); min-width: 28px; text-align: right; }

/* Stacked bars */
.stacked-bar { display: flex; height: 20px; border-radius: 5px; overflow: hidden; margin: 0.3rem 0; }
.seg { height: 100%; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 700; color: white; }
.seg-finance { background: var(--finance); }
.seg-diligence { background: var(--diligence); }
.seg-other { background: var(--other); }

/* Misc */
.empty { color: var(--muted); font-style: italic; padding: 1rem 0; text-align: center; font-size: 0.9rem; }
.banner { padding: 0.5rem 0.8rem; border-radius: 6px; font-weight: 700; font-size: 0.88rem; margin-bottom: 0.75rem; display: flex; align-items: center; gap: 0.4rem; }
.banner-warn { background: var(--warn-soft); color: var(--warn); }
.highlight-billion { font-weight: 700; color: var(--danger); }
.text-trunc { max-width: 220px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: inline-block; vertical-align: bottom; }
.legend { display: flex; gap: 0.75rem; font-size: 0.8rem; margin-top: 0.5rem; }
.legend-item { display: flex; align-items: center; gap: 0.25rem; }
.legend-dot { width: 8px; height: 8px; border-radius: 2px; }
.collapsible-hdr { cursor: pointer; display: flex; align-items: center; gap: 0.4rem; padding: 0.3rem 0; font-weight: 600; font-size: 0.9rem; color: var(--fg); }
.collapsible-hdr::before { content: '\25b8'; font-size: 0.8rem; color: var(--muted); transition: transform 0.15s; }
.collapsible-hdr.open::before { transform: rotate(90deg); }
.collapsible-body { display: none; padding-left: 0.75rem; border-left: 2px solid var(--border); margin-top: 0.3rem; }
.collapsible-body.open { display: block; }
.sev-row { display: flex; gap: 0.5rem; margin-bottom: 0.75rem; }

/* Narrative cards */
.narrative-card { border-left: 4px solid var(--accent); margin-bottom: 1.25rem; }
.narrative-card h3 { font-size: 0.95rem; font-weight: 700; color: var(--fg); margin-top: 0.75rem; margin-bottom: 0.3rem; }
.narrative-card .narrative-body { font-size: 0.9rem; line-height: 1.6; color: var(--fg); white-space: pre-wrap; margin-bottom: 0.5rem; }
.narrative-card .narrative-meta { font-size: 0.82rem; color: var(--muted); margin-bottom: 0.5rem; }

/* Executive summary / Critical findings */
.exec-summary { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.25rem 1.5rem; margin-bottom: 1.5rem; box-shadow: var(--shadow-md); }
.exec-summary h2 { font-size: 0.82rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--danger); margin-bottom: 0.75rem; }
.exec-item { display: flex; gap: 0.75rem; align-items: flex-start; padding: 0.6rem 0; border-bottom: 1px solid var(--border); }
.exec-item:last-child { border-bottom: none; }
.exec-rank { font-size: 0.8rem; font-weight: 800; color: var(--danger); background: var(--danger-soft); width: 1.6rem; height: 1.6rem; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.exec-text { font-size: 0.9rem; line-height: 1.5; }
.exec-text strong { font-weight: 700; }

/* Print */
@media print {
  .theme-toggle, .risk-nav, .tab-bar, .evidence-btn, .report-header-right { display: none !important; }
  .tab-content { display: block !important; page-break-before: always; }
  .tab-content:first-of-type { page-break-before: avoid; }
  .panel { break-inside: avoid; box-shadow: none; border: 1px solid #ddd; }
  .evidence-drawer { display: table-row !important; }
  .kpi-strip { gap: 0.4rem; }
  .kpi { box-shadow: none; border: 1px solid #ddd; }
  body { font-size: 11pt; background: white; color: black; }
  .shell { padding: 0; max-width: 100%; }
}
</style>
</head>
<body>
<div class="shell">
<div class="report-header">
  <div class="report-header-left">
    <div class="report-title">Due Diligence Risk Report</div>
    <div class="report-subject" id="report-subject"></div>
    <div class="report-meta" id="report-meta"></div>
  </div>
  <div class="report-header-right">
    <div class="domain-badges" id="domain-badges"></div>
    <button class="theme-toggle" id="theme-toggle" title="Toggle dark/light mode" aria-label="Toggle theme"></button>
  </div>
</div>
<div class="kpi-strip" id="kpi-strip"></div>
<div class="exec-summary" id="exec-summary"></div>
<div class="tab-bar" id="tab-bar"></div>
<div id="tabs-container"></div>
</div>
<script>
/*__DATA__*/

// --- Theme toggle ---
(function() {
  const stored = localStorage.getItem('graphify-theme');
  if (stored) document.documentElement.setAttribute('data-theme', stored);
  document.getElementById('theme-toggle').addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const isDark = current === 'dark' || (!current && window.matchMedia('(prefers-color-scheme: dark)').matches);
    const next = isDark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('graphify-theme', next);
  });
})();

// --- Helpers ---
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) Object.entries(attrs).forEach(([k, v]) => {
    if (k === 'className') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
    else el.setAttribute(k, v);
  });
  children.flat().forEach(c => {
    if (typeof c === 'string' || typeof c === 'number') el.appendChild(document.createTextNode(String(c)));
    else if (c) el.appendChild(c);
  });
  return el;
}
function severityBadge(sev) { return h('span', {className: 'badge badge-' + (sev === 'high' ? 'high' : sev === 'medium' ? 'medium' : 'low')}, sev.toUpperCase()); }
function domainBadge(d) { const c = d === 'finance' ? 'badge-finance' : d === 'diligence' ? 'badge-diligence' : 'badge-other'; return h('span', {className: 'badge ' + c}, d || 'other'); }

function sortableTable(headers, rows) {
  let sortCol = -1, sortAsc = true;
  const container = h('div');
  function render() {
    while (container.firstChild) container.removeChild(container.firstChild);
    const sorted = [...rows];
    if (sortCol >= 0) sorted.sort((a, b) => { const va = a[sortCol], vb = b[sortCol]; if (va instanceof HTMLElement || vb instanceof HTMLElement) return 0; const cmp = typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb)); return sortAsc ? cmp : -cmp; });
    container.appendChild(h('table', null,
      h('thead', null, h('tr', null, headers.map((hdr, i) => h('th', {onClick: () => { if (sortCol === i) sortAsc = !sortAsc; else { sortCol = i; sortAsc = true; } render(); }}, hdr + (sortCol === i ? (sortAsc ? ' \u25b2' : ' \u25bc') : ''))))),
      h('tbody', null, sorted.map(row => h('tr', null, row.map(cell => h('td', null, cell instanceof HTMLElement ? cell : String(cell != null ? cell : ''))))))
    ));
  }
  render();
  return container;
}

const RF_TYPE_LABELS = {
  'related_party_exposure': 'Related-Party Exposure',
  'vie_consolidation': 'Off-Balance-Sheet / VIE Risk',
  'key_person_risk': 'Key-Person Dependency',
  'compensation_concentration': 'Compensation Concentration',
  'conflict_of_interest': 'Conflict of Interest',
  'risk_factor': 'Disclosed Risk Factor',
  'concentration_risk': 'Revenue Concentration',
  'burn_rate': 'Cash Burn Rate',
  'cash_flow_divergence': 'Cash Flow vs. Earnings Gap',
  'working_capital_flag': 'Working Capital Deterioration',
  'debt_maturity': 'Debt Maturity Wall',
  'total_dilution': 'Shareholder Dilution Risk',
  'liquidity_runway': 'Liquidity Runway Warning',
  'valuation_inflated_by': 'Valuation Without Price Discovery',
};
const RF_TYPE_HINTS = {
  'related_party_exposure': 'Transaction between insiders or affiliated entities that may indicate self-dealing',
  'vie_consolidation': 'Variable interest entity or off-balance-sheet structure that obscures true obligations',
  'key_person_risk': 'Organization depends critically on this individual; removal would fragment operations',
  'compensation_concentration': 'Equity compensation disproportionately benefits a single individual',
  'conflict_of_interest': 'Same person holds roles on both sides of a transaction or decision',
  'risk_factor': 'Risk explicitly disclosed in the filing',
  'concentration_risk': 'Material portion of revenue depends on a single counterparty',
  'burn_rate': 'Company is losing more cash than it earns in revenue',
  'cash_flow_divergence': 'Operating cash flow is negative while adjusted metrics claim profitability',
  'working_capital_flag': 'Receivables growing faster than revenue signals collection or channel-stuffing issues',
  'debt_maturity': 'Large portion of debt matures in near term, creating refinancing risk',
  'total_dilution': 'Outstanding options, warrants, and convertibles could significantly dilute shareholders',
  'liquidity_runway': 'Cash reserves cover less than 12 months of operations at current burn rate',
  'valuation_inflated_by': 'Valuation set by single investor without competitive market price discovery',
};

function evidenceTable(flags) {
  const container = h('div', {className: 'evidence-table-wrap'});
  const table = h('table');
  table.appendChild(h('thead', null, h('tr', null,
    h('th', null, 'Sev'), h('th', null, 'Risk Category'), h('th', null, 'Finding'), h('th', {style:'width:2.5em'}, '')
  )));
  const tbody = h('tbody');
  flags.forEach((d, idx) => {
    const ev = d.evidence || {};
    const hasEvidence = ev.source_file || (ev.cross_references && ev.cross_references.length) || (ev.neighbors && ev.neighbors.length);
    const row = h('tr', {className: 'rf-row'});
    row.appendChild(h('td', null, severityBadge(d.severity||'medium')));
    const typeLabel = RF_TYPE_LABELS[d.type] || d.type || '';
    const typeHint = RF_TYPE_HINTS[d.type] || '';
    const typeCell = h('td', {className: 'rf-type-cell', title: typeHint});
    typeCell.appendChild(h('div', {className: 'rf-type-name'}, typeLabel));
    if (typeHint) typeCell.appendChild(h('div', {className: 'rf-type-hint'}, typeHint));
    row.appendChild(typeCell);
    const findingCell = h('td', {className: 'rf-finding-cell'});
    findingCell.appendChild(h('div', {className: 'rf-finding'}, d.finding||d.label||d.node||''));
    if (d.finding && d.label && d.finding !== d.label) {
      findingCell.appendChild(h('div', {className: 'rf-raw-label'}, d.label));
    }
    row.appendChild(findingCell);
    const btnCell = h('td');
    if (hasEvidence) {
      const btn = h('button', {className: 'evidence-btn', onClick: () => {
        const drawer = document.getElementById('ev-drawer-' + idx);
        if (drawer) { drawer.style.display = drawer.style.display === 'none' ? 'table-row' : 'none'; btn.textContent = drawer.style.display === 'none' ? '+' : '\u2212'; }
      }}, '+');
      btnCell.appendChild(btn);
    }
    row.appendChild(btnCell);
    tbody.appendChild(row);

    if (hasEvidence) {
      const drawerRow = h('tr', {className: 'evidence-drawer', style: 'display:none'});
      drawerRow.id = 'ev-drawer-' + idx;
      const drawerCell = h('td', {className: 'evidence-cell'});
      drawerCell.setAttribute('colspan', '4');

      // Source file + section
      if (ev.source_file) {
        const srcName = ev.source_file.replace(/.*\//, '');
        const srcText = ev.section ? srcName + ' \u2014 ' + ev.section : srcName;
        drawerCell.appendChild(h('div', {className: 'ev-section'}, h('span', {className: 'ev-label'}, 'Source: '), srcText));
      }

      // Table data
      if (ev.data && Object.keys(ev.data).length) {
        const dataDiv = h('div', {className: 'ev-section'});
        dataDiv.appendChild(h('span', {className: 'ev-label'}, 'Table data: '));
        const pairs = Object.entries(ev.data).filter(([k,v]) => k !== 'col_0' && v).slice(0, 6);
        dataDiv.appendChild(document.createTextNode(pairs.map(([k,v]) => k + '=' + String(v).substring(0, 40)).join(', ')));
        drawerCell.appendChild(dataDiv);
      }

      // Description
      if (ev.description) {
        drawerCell.appendChild(h('div', {className: 'ev-section ev-desc'}, ev.description));
      }

      // Cross-references
      if (ev.cross_references && ev.cross_references.length) {
        ev.cross_references.forEach(xref => {
          const xdiv = h('div', {className: 'ev-section xref-block'});
          xdiv.appendChild(h('div', {className: 'ev-label'}, '\ud83d\udccc ' + xref.heading));
          xdiv.appendChild(h('div', {className: 'ev-excerpt'}, xref.excerpt));
          drawerCell.appendChild(xdiv);
        });
      }

      // Neighbor context
      if (ev.neighbors && ev.neighbors.length) {
        const nDiv = h('div', {className: 'ev-section'});
        nDiv.appendChild(h('span', {className: 'ev-label'}, 'Graph context: '));
        const nList = ev.neighbors.slice(0, 5).map(n => (n.direction === 'inbound' ? '\u2190 ' : '\u2192 ') + n.relation + ' \u2190 ' + n.label);
        nDiv.appendChild(document.createTextNode(nList.join(' | ')));
        drawerCell.appendChild(nDiv);
      }

      drawerRow.appendChild(drawerCell);
      tbody.appendChild(drawerRow);
    }
  });
  table.appendChild(tbody);
  container.appendChild(table);
  return container;
}

function barChart(items, fillClass) {
  const max = Math.max(...items.map(i => i.value), 1);
  const frag = document.createDocumentFragment();
  items.forEach(i => {
    const row = h('div', {className: 'bar-item'});
    row.appendChild(h('div', {className: 'bar-label', title: i.label}, i.label));
    const track = h('div', {className: 'bar-track'});
    track.appendChild(h('div', {className: 'bar-fill ' + fillClass, style: 'width:' + ((i.value / max) * 100) + '%'}));
    row.appendChild(track);
    row.appendChild(h('div', {className: 'bar-val'}, String(i.value)));
    frag.appendChild(row);
  });
  return frag;
}

// --- Data ---
const {analysis, meta, extra} = DATA;
const da = analysis.domain_analysis || {};
const redFlags = da['diligence.red_flag_analyzer'] || [];
const keyPerson = da['diligence.key_person_risk_analyzer'] || [];
const pending = (extra || {}).pending_candidates || [];
const relParty = (extra || {}).related_party_edges || [];
const financialObl = (extra || {}).financial_obligations || [];
const communityMix = (extra || {}).community_domain_mix || {};
const domainNodes = (extra || {}).domain_nodes_by_type || {};
const summary = (da['_summary'] || [null])[0];

// --- Report Header ---
const gods = analysis.gods || [];
const subjectEntity = gods.length ? gods[0].label || gods[0].node || '' : '';
const sourceFiles = new Set();
if (extra && extra.pending_candidates) extra.pending_candidates.forEach(c => { if (c.source_file) sourceFiles.add(c.source_file); });
const subjectLine = subjectEntity + (sourceFiles.size ? ' \u2014 Filing Analysis' : '');
document.getElementById('report-subject').textContent = subjectLine;
const communityCount = Object.keys(analysis.communities||{}).length;
document.getElementById('report-meta').textContent = 'Generated ' + new Date().toLocaleDateString('en-US', {year:'numeric', month:'short', day:'numeric'}) + ' \u2022 ' + (meta.nodes||0) + ' entities \u2022 ' + (meta.edges||0) + ' relationships \u2022 ' + communityCount + ' clusters';
if (summary && summary.domains) {
  const db = document.getElementById('domain-badges');
  Object.entries(summary.domains).forEach(([d, c]) => db.appendChild(domainBadge(d)));
}

// --- KPI ---
const kpiStrip = document.getElementById('kpi-strip');
const highCount = redFlags.filter(f=>f.severity==='high').length;
const medCount = redFlags.filter(f=>f.severity==='medium').length;
const kpis = [
  {v: redFlags.length, l: 'Red Flags', sub: highCount + ' high', c: 'kpi-danger'},
  {v: keyPerson.length, l: 'Key Persons', sub: keyPerson.filter(k=>(k.fragments_into||0)>3).length + ' critical', c: 'kpi-warn'},
  {v: pending.length, l: 'Pending Review', sub: '', c: 'kpi-warn'},
  {v: meta.nodes||0, l: 'Entities', sub: '', c: ''},
  {v: meta.edges||0, l: 'Relationships', sub: '', c: ''},
  {v: communityCount, l: 'Clusters', sub: '', c: ''},
];
kpis.forEach(k => {
  const el = h('div', {className: 'kpi ' + k.c}, h('span', {className: 'kpi-value'}, String(k.v)), h('span', {className: 'kpi-label'}, k.l));
  if (k.sub) el.appendChild(h('span', {className: 'kpi-sub'}, k.sub));
  kpiStrip.appendChild(el);
});

// --- Executive Summary ---
const execEl = document.getElementById('exec-summary');
const topRisks = redFlags.filter(f => f.severity === 'high').slice(0, 3);
if (topRisks.length) {
  execEl.appendChild(h('h2', null, 'Critical Findings'));
  topRisks.forEach((r, i) => {
    const item = h('div', {className: 'exec-item'});
    item.appendChild(h('span', {className: 'exec-rank'}, String(i + 1)));
    const text = h('div', {className: 'exec-text'});
    const typeName = RF_TYPE_LABELS[r.type] || r.type;
    text.appendChild(h('strong', null, typeName + ': '));
    text.appendChild(document.createTextNode(r.finding || r.label || ''));
    item.appendChild(text);
    execEl.appendChild(item);
  });
} else {
  execEl.style.display = 'none';
}

// --- Tabs ---
const tabDefs = [
  {id: 'risk', label: 'Findings'},
  {id: 'narratives', label: 'Narratives'},
  {id: 'structure', label: 'Structure'},
  {id: 'deep', label: 'Data'},
];
const tabBar = document.getElementById('tab-bar');
const tabsContainer = document.getElementById('tabs-container');
const tabContents = {};

tabDefs.forEach((td, i) => {
  const tab = h('div', {className: 'tab' + (i === 0 ? ' active' : ''), 'data-tab': td.id}, td.label);
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    Object.values(tabContents).forEach(tc => tc.classList.remove('active'));
    tabContents[td.id].classList.add('active');
  });
  tabBar.appendChild(tab);
  const content = h('div', {className: 'tab-content' + (i === 0 ? ' active' : '')});
  tabsContainer.appendChild(content);
  tabContents[td.id] = content;
});

// ==================== TAB: RISK ====================
(function buildRiskTab() {
  const tc = tabContents['risk'];

  // Nav bar
  const navItems = [
    {id: 'risk-redflags', label: '\u26a0 Red Flags', count: redFlags.length},
    {id: 'risk-keyperson', label: '\ud83d\udc64 Key Person', count: keyPerson.length},
  ];
  if (relParty.length) navItems.push({id: 'risk-relparty', label: '\ud83d\udd04 Related-Party', count: relParty.length});
  if (pending.length) navItems.push({id: 'risk-pending', label: '\u23f3 Pending', count: pending.length});
  const nav = h('div', {className: 'risk-nav'});
  navItems.forEach(item => {
    const link = h('a', {className: 'risk-nav-item', href: '#' + item.id, onClick: (e) => {
      e.preventDefault();
      document.getElementById(item.id).scrollIntoView({behavior: 'smooth', block: 'start'});
    }}, item.label + ' (' + item.count + ')');
    nav.appendChild(link);
  });
  tc.appendChild(nav);

  const riskStack = h('div', {className: 'risk-layout'});

  // Section 1: Red Flags (full width)
  const rfPanel = h('div', {className: 'panel panel-danger', id: 'risk-redflags'});
  rfPanel.appendChild(h('h2', null, '\u26a0 Red Flags'));
  rfPanel.appendChild(h('p', {className: 'section-desc'}, 'Governance and structural risks detected in the graph. Higher severity items represent greater potential exposure.'));
  if (redFlags.length) {
    const sev = h('div', {className: 'sev-row'});
    const high = redFlags.filter(f=>f.severity==='high').length;
    const med = redFlags.filter(f=>f.severity==='medium').length;
    const low = redFlags.filter(f=>f.severity==='low').length;
    if (high) sev.appendChild(h('span', {className: 'badge badge-high'}, high + ' HIGH'));
    if (med) sev.appendChild(h('span', {className: 'badge badge-medium'}, med + ' MEDIUM'));
    if (low) sev.appendChild(h('span', {className: 'badge badge-low'}, low + ' LOW'));
    rfPanel.appendChild(sev);
    rfPanel.appendChild(evidenceTable(redFlags));
  } else {
    rfPanel.appendChild(h('div', {className: 'empty'}, 'No red flags detected.'));
  }
  riskStack.appendChild(rfPanel);

  // Section 2: Key-Person Risk + Related-Party (side by side)
  const midRow = h('div', {className: 'risk-mid-row'});

  const kpPanel = h('div', {className: 'panel panel-warn', id: 'risk-keyperson'});
  kpPanel.appendChild(h('h2', null, '\u{1f464} Key-Person Risk'));
  kpPanel.appendChild(h('p', {className: 'section-desc'}, 'Individuals whose removal would fragment the graph into disconnected components.'));
  if (keyPerson.length) {
    keyPerson.forEach(d => {
      const conns = d.connections||d.degree||0, frags = d.fragments_into||0;
      const risk = frags > 5 ? 'high' : conns > 10 ? 'medium' : 'low';
      const card = h('div', {className: 'kp-card'});
      const cardHead = h('div', {className: 'kp-card-header'});
      cardHead.appendChild(h('span', {className: 'kp-name'}, d.label||d.person));
      cardHead.appendChild(severityBadge(risk));
      card.appendChild(cardHead);
      card.appendChild(h('div', {className: 'kp-stats'},
        h('span', null, '\ud83d\udd17 ' + conns + ' connections'),
        h('span', {className: frags > 3 ? 'kp-frag-high' : ''}, '\u26a1 Fragments into ' + frags + ' pieces if removed')
      ));
      kpPanel.appendChild(card);
    });
  } else { kpPanel.appendChild(h('div', {className: 'empty'}, 'No key-person risk.')); }
  midRow.appendChild(kpPanel);

  if (relParty.length) {
    const rpPanel = h('div', {className: 'panel panel-accent', id: 'risk-relparty'});
    rpPanel.appendChild(h('h2', null, '\ud83d\udd04 Related-Party Transactions'));
    rpPanel.appendChild(h('p', {className: 'section-desc'}, 'Transactions between insiders or affiliated entities.'));
    const rpRows = relParty.map(d => [d.source_label, d.target_label, d.relation, String(d.confidence_score||d.confidence||'')]);
    rpPanel.appendChild(sortableTable(['Source', 'Target', 'Relation', 'Conf.'], rpRows));
    midRow.appendChild(rpPanel);
  }
  riskStack.appendChild(midRow);

  // Section 3: Pending Candidates (full width)
  if (pending.length) {
    const pendPanel = h('div', {className: 'panel panel-muted', id: 'risk-pending'});
    const pendHead = h('div', {className: 'pending-head'});
    pendHead.appendChild(h('h2', null, '\u23f3 Pending Review'));
    pendHead.appendChild(h('span', {className: 'badge badge-medium'}, pending.length + ' candidates'));
    pendPanel.appendChild(pendHead);
    pendPanel.appendChild(h('p', {className: 'section-desc'}, 'Transactions detected by pattern-matching that need human review to confirm or dismiss. Expand source context to see the original text.'));
    const pendGrid = h('div', {className: 'pending-grid'});
    pending.forEach((d, idx) => {
      const card = h('div', {className: 'pending-card'});
      const header = h('div', {className: 'pending-header'});
      header.appendChild(h('span', {className: 'badge badge-medium'}, d.type||''));
      header.appendChild(h('span', {className: 'pending-amount'}, d.amount||''));
      card.appendChild(header);
      card.appendChild(h('div', {className: 'pending-finding'}, d.finding||''));
      if (d.context) {
        const toggle = h('button', {className: 'evidence-btn', onClick: () => {
          const ctx = document.getElementById('pend-ctx-' + idx);
          if (ctx) { ctx.style.display = ctx.style.display === 'none' ? 'block' : 'none'; toggle.textContent = ctx.style.display === 'none' ? '+' : '\u2212'; }
        }}, '+');
        const ctxLabel = h('div', {className: 'pending-ctx-row'});
        ctxLabel.appendChild(h('span', {className: 'ev-label'}, 'Source context '));
        ctxLabel.appendChild(toggle);
        card.appendChild(ctxLabel);
        card.appendChild(h('div', {className: 'pending-context', style: 'display:none', id: 'pend-ctx-' + idx}, d.context));
      }
      pendGrid.appendChild(card);
    });
    pendPanel.appendChild(pendGrid);
    riskStack.appendChild(pendPanel);
  }

  tc.appendChild(riskStack);
})();

// ==================== TAB: STRUCTURE ====================
(function buildStructureTab() {
  const tc = tabContents['structure'];
  tc.style.gridTemplateColumns = '1fr';
  const layout = h('div', {className: 'col-layout'});

  // Left: God Nodes + Surprises
  const leftStack = h('div', {className: 'panel-stack'});

  const godsPanel = h('div', {className: 'panel panel-accent'});
  godsPanel.appendChild(h('h2', null, '\u2b50 God Nodes (High-Degree Hubs)'));
  godsPanel.appendChild(h('p', {className: 'section-desc'}, 'Nodes with the most connections in the graph. These are central entities that link many concepts\u2014potential bottlenecks, key decision-makers, or core organizational structures that everything else depends on.'));
  const gods = analysis.gods || [];
  if (gods.length) {
    godsPanel.appendChild(barChart(gods.map(g => ({label: g.label||g.node||'', value: g.degree||0})), 'bar-fill-accent'));
  } else { godsPanel.appendChild(h('div', {className: 'empty'}, 'No god nodes.')); }
  leftStack.appendChild(godsPanel);

  const surprPanel = h('div', {className: 'panel'});
  surprPanel.appendChild(h('h2', null, '\u{1f50d} Surprising Cross-Community Edges'));
  surprPanel.appendChild(h('p', {className: 'section-desc'}, 'Edges that connect nodes in different communities. These reveal unexpected relationships or hidden dependencies between otherwise separate clusters\u2014often the most insightful findings in due diligence.'));
  const surprises = analysis.surprises || [];
  if (surprises.length) {
    const rows = surprises.map(s => {
      const why = s.why || '';
      const whyEl = why.length > 50 ? h('span', {className: 'text-trunc', title: why}, why) : h('span', null, why);
      return [s.source||s.from||'', s.target||s.to||'', s.relation||'', whyEl];
    });
    surprPanel.appendChild(sortableTable(['From', 'To', 'Relation', 'Why'], rows));
  } else { surprPanel.appendChild(h('div', {className: 'empty'}, 'No surprising edges.')); }
  leftStack.appendChild(surprPanel);

  layout.appendChild(leftStack);

  // Right: Communities
  const commPanel = h('div', {className: 'panel'});
  commPanel.appendChild(h('h2', null, '\u{1f3d8} Communities'));
  commPanel.appendChild(h('p', {className: 'section-desc'}, 'Clusters of tightly-connected nodes detected by community algorithms. Each community represents a group of entities that interact more with each other than with outsiders\u2014business units, deal structures, or thematic groupings.'));
  const entries = Object.entries(analysis.communities || {}).sort((a, b) => b[1].length - a[1].length);
  if (entries.length) {
    commPanel.appendChild(barChart(entries.map(([id, nodes]) => ({label: 'C' + id + ' (' + nodes.length + ')', value: nodes.length})), 'bar-fill-ok'));
  } else { commPanel.appendChild(h('div', {className: 'empty'}, 'No communities.')); }
  layout.appendChild(commPanel);

  tc.appendChild(layout);
})();

// ==================== TAB: DEEP DIVE ====================
(function buildDeepTab() {
  const tc = tabContents['deep'];
  tc.style.gridTemplateColumns = '1fr';
  const layout = h('div', {className: 'col-layout'});

  // Left: Financial Obligations
  const leftPanel = h('div', {className: 'panel'});
  leftPanel.appendChild(h('h2', null, '\u{1f4b0} Financial Obligations'));
  leftPanel.appendChild(h('p', {className: 'section-desc'}, 'Nodes in the graph whose labels reference monetary amounts. Sorted by value to surface the largest commitments, liabilities, or revenue figures extracted from filings and contracts.'));
  if (financialObl.length) {
    const rows = financialObl.map(d => {
      const isBillion = /billion/i.test(d.amount_raw);
      const amtEl = h('span', {className: isBillion ? 'highlight-billion' : ''}, d.amount_raw);
      return [d.label, amtEl, domainBadge(d.domain||'')];
    });
    leftPanel.appendChild(sortableTable(['Label', 'Amount', 'Domain'], rows));
  } else { leftPanel.appendChild(h('div', {className: 'empty'}, 'No financial obligation nodes.')); }
  layout.appendChild(leftPanel);

  // Right: Community Mix + Domain Explorer
  const rightStack = h('div', {className: 'panel-stack'});

  const mixPanel = h('div', {className: 'panel'});
  mixPanel.appendChild(h('h2', null, 'Community Domain Composition'));
  mixPanel.appendChild(h('p', {className: 'section-desc'}, 'How finance and diligence domain nodes distribute across communities. A community dominated by one domain is well-scoped; mixed communities may indicate cross-cutting concerns or shared entities.'));
  const mixEntries = Object.entries(communityMix).filter(([_, v]) => v.finance > 0 || v.diligence > 0).sort((a,b) => (b[1].total||0) - (a[1].total||0));
  if (mixEntries.length) {
    mixEntries.slice(0, 10).forEach(([id, counts]) => {
      const total = counts.total || 1;
      const row = h('div', {style: 'margin-bottom: 0.4rem'});
      row.appendChild(h('div', {style: 'font-size:0.72rem; color:var(--muted); margin-bottom:2px'}, 'C' + id + ' \u2022 ' + total));
      const bar = h('div', {className: 'stacked-bar'});
      if (counts.finance > 0) bar.appendChild(h('div', {className: 'seg seg-finance', style: 'width:' + ((counts.finance/total)*100) + '%'}, counts.finance > 1 ? String(counts.finance) : ''));
      if (counts.diligence > 0) bar.appendChild(h('div', {className: 'seg seg-diligence', style: 'width:' + ((counts.diligence/total)*100) + '%'}, counts.diligence > 1 ? String(counts.diligence) : ''));
      if (counts.other > 0) bar.appendChild(h('div', {className: 'seg seg-other', style: 'width:' + ((counts.other/total)*100) + '%'}, counts.other > 1 ? String(counts.other) : ''));
      row.appendChild(bar);
      mixPanel.appendChild(row);
    });
    const legend = h('div', {className: 'legend'});
    legend.appendChild(h('div', {className: 'legend-item'}, h('div', {className: 'legend-dot', style: 'background:var(--finance)'}), 'Finance'));
    legend.appendChild(h('div', {className: 'legend-item'}, h('div', {className: 'legend-dot', style: 'background:var(--diligence)'}), 'Diligence'));
    legend.appendChild(h('div', {className: 'legend-item'}, h('div', {className: 'legend-dot', style: 'background:var(--other)'}), 'Other'));
    mixPanel.appendChild(legend);
  } else { mixPanel.appendChild(h('div', {className: 'empty'}, 'No domain-tagged communities.')); }
  rightStack.appendChild(mixPanel);

  // Domain explorer (collapsible)
  if (Object.keys(domainNodes).length) {
    const expPanel = h('div', {className: 'panel'});
    expPanel.appendChild(h('h2', null, 'Node Explorer'));
    expPanel.appendChild(h('p', {className: 'section-desc'}, 'Browse domain-tagged nodes grouped by type (person, organization, obligation, etc.). Top 10 per type ranked by degree\u2014higher degree means more connected and potentially more significant.'));
    Object.entries(domainNodes).forEach(([type, nodes]) => {
      const hdr = h('div', {className: 'collapsible-hdr', onClick: function() { this.classList.toggle('open'); body.classList.toggle('open'); }}, type + ' (' + nodes.length + ')');
      const body = h('div', {className: 'collapsible-body'});
      body.appendChild(sortableTable(['Label', 'Domain', 'Deg'], nodes.map(n => [n.label, domainBadge(n.domain), n.degree])));
      expPanel.appendChild(hdr);
      expPanel.appendChild(body);
    });
    rightStack.appendChild(expPanel);
  }

  layout.appendChild(rightStack);
  tc.appendChild(layout);
})();

// ==================== TAB: NARRATIVES ====================
(function buildNarrativesTab() {
  const tc = tabContents['narratives'];
  tc.style.gridTemplateColumns = '1fr';
  const narratives = (extra || {}).narratives || [];

  if (!narratives.length) {
    const emptyPanel = h('div', {className: 'panel'});
    emptyPanel.appendChild(h('h2', null, 'Synthesized Risk Narratives'));
    emptyPanel.appendChild(h('p', {className: 'section-desc'}, 'LLM-generated analysis that explains how multiple red flags combine into systemic risks. Each narrative synthesizes a cluster of findings into a plain-language explanation of who benefits, who loses, and what to investigate.'));
    emptyPanel.appendChild(h('div', {className: 'empty'}, 'No narratives available. Set GEMINI_API_KEY or ANTHROPIC_API_KEY to enable LLM synthesis.'));
    tc.appendChild(emptyPanel);
    return;
  }

  const introPanel = h('div', {className: 'panel', style: 'margin-bottom: 1rem'});
  introPanel.appendChild(h('h2', null, 'Synthesized Risk Narratives'));
  introPanel.appendChild(h('p', {className: 'section-desc'}, 'LLM-generated analysis that explains how multiple red flags combine into systemic risks. The LLM receives a subgraph of connected entities around each risk theme and identifies patterns that no single finding reveals alone.'));
  tc.appendChild(introPanel);

  narratives.forEach(function(n, i) {
    const card = h('div', {className: 'panel narrative-card'});
    card.appendChild(h('h2', null, '[' + (i + 1) + '] ' + (n.label || 'Untitled')));
    card.appendChild(h('div', {className: 'narrative-meta'}, 'Center: ' + (n.center_entity || 'unknown') + ' \u2022 ' + (n.finding_count || 0) + ' findings \u2022 Types: ' + (n.findings_summary || []).join(', ')));

    // Parse narrative into sections by ## headings
    const text = n.narrative || '';
    const parts = text.split(/^## /m);
    parts.forEach(function(part) {
      if (!part.trim()) return;
      const lines = part.split('\n');
      const title = lines[0].trim();
      const body = lines.slice(1).join('\n').trim();
      if (title) card.appendChild(h('h3', null, title));
      if (body) card.appendChild(h('div', {className: 'narrative-body'}, body));
    });

    tc.appendChild(card);
  });
})();
</script>
</body>
</html>
"""
