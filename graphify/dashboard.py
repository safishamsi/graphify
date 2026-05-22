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
        window = item.get("window", "")
        if len(window) > 150:
            window = window[:150]
        results.append({
            "type": item.get("type", ""),
            "amount": item.get("amount", ""),
            "window_snippet": window,
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
<title>Graphify Dashboard</title>
<style>
:root {
  --bg: #f0f2f5; --fg: #1a1a2e; --card: #ffffff; --border: #e2e8f0;
  --accent: #3b82f6; --accent-soft: #eff6ff;
  --danger: #dc2626; --danger-soft: #fef2f2;
  --warn: #d97706; --warn-soft: #fffbeb;
  --ok: #059669; --ok-soft: #ecfdf5;
  --muted: #64748b; --subtle: #f8fafc;
  --finance: #3b82f6; --diligence: #dc2626; --other: #64748b;
  --shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.06), 0 2px 4px rgba(0,0,0,0.04);
  --radius: 10px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f172a; --fg: #e2e8f0; --card: #1e293b; --border: #334155;
    --accent: #60a5fa; --accent-soft: #1e3a5f;
    --danger: #f87171; --danger-soft: #3b1c1c;
    --warn: #fbbf24; --warn-soft: #3b2e1c;
    --ok: #34d399; --ok-soft: #1c3b2e;
    --muted: #94a3b8; --subtle: #1e293b;
    --finance: #60a5fa; --diligence: #f87171; --other: #94a3b8;
    --shadow: 0 1px 3px rgba(0,0,0,0.3); --shadow-md: 0 4px 6px rgba(0,0,0,0.3);
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: auto; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--fg); }

.shell { display: flex; flex-direction: column; min-height: 100vh; max-width: 1500px; margin: 0 auto; padding: 1.25rem 2rem 2rem; }

/* Header row */
.header { display: flex; align-items: baseline; gap: 1.5rem; margin-bottom: 1rem; flex-shrink: 0; }
.header h1 { font-size: 1.4rem; font-weight: 700; letter-spacing: -0.02em; white-space: nowrap; }
.header .meta { font-size: 0.78rem; color: var(--muted); }
.header .domain-badges { margin-left: auto; display: flex; gap: 0.4rem; }

/* KPI strip */
.kpi-strip { display: flex; gap: 0.75rem; margin-bottom: 1rem; flex-shrink: 0; flex-wrap: wrap; }
.kpi { background: var(--card); border-radius: 8px; padding: 0.6rem 1.1rem; box-shadow: var(--shadow); border-left: 3px solid var(--accent); display: flex; align-items: baseline; gap: 0.5rem; }
.kpi-danger { border-left-color: var(--danger); }
.kpi-warn { border-left-color: var(--warn); }
.kpi .kpi-value { font-size: 1.5rem; font-weight: 800; }
.kpi .kpi-label { font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }

/* Tabs */
.tab-bar { display: flex; gap: 0; border-bottom: 2px solid var(--border); margin-bottom: 0; flex-shrink: 0; }
.tab { padding: 0.5rem 1.25rem; font-size: 0.82rem; font-weight: 600; color: var(--muted); cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px; transition: color 0.15s, border-color 0.15s; user-select: none; }
.tab:hover { color: var(--fg); }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }

/* Tab content */
.tab-content { display: none; padding-top: 1rem; }
.tab-content.active { display: grid; }

/* Two-col layout inside tabs */
.col-layout { display: grid; grid-template-columns: 3fr 2fr; gap: 1rem; }
@media (max-width: 900px) { .col-layout { grid-template-columns: 1fr; } }

/* Panels */
.panel { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 1rem 1.25rem; box-shadow: var(--shadow); min-height: 0; }
.panel-danger { border-left: 4px solid var(--danger); }
.panel-warn { border-left: 4px solid var(--warn); }
.panel-accent { border-left: 4px solid var(--accent); }
.panel h2 { font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); margin-bottom: 0.25rem; padding-bottom: 0.4rem; border-bottom: 1px solid var(--border); }
.panel .section-desc { font-size: 0.74rem; color: var(--muted); margin-bottom: 0.75rem; line-height: 1.4; font-style: italic; }
.panel-stack { display: flex; flex-direction: column; gap: 1rem; min-height: 0; }

/* Tables */
table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
thead { position: sticky; top: 0; background: var(--card); z-index: 1; }
th { padding: 0.5rem 0.6rem; text-align: left; font-weight: 600; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.03em; color: var(--muted); border-bottom: 2px solid var(--border); cursor: pointer; user-select: none; white-space: nowrap; }
th:hover { color: var(--accent); }
td { padding: 0.45rem 0.6rem; border-bottom: 1px solid var(--border); }
tbody tr:hover { background: var(--accent-soft); }

/* Badges */
.badge { display: inline-flex; align-items: center; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.02em; }
.badge-high { background: var(--danger-soft); color: var(--danger); }
.badge-medium { background: var(--warn-soft); color: var(--warn); }
.badge-low { background: var(--ok-soft); color: var(--ok); }
.badge-finance { background: var(--accent-soft); color: var(--finance); }
.badge-diligence { background: var(--danger-soft); color: var(--diligence); }
.badge-other { background: var(--subtle); color: var(--other); }

/* Bar charts */
.bar-item { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.4rem; }
.bar-label { font-size: 0.78rem; font-weight: 500; min-width: 140px; max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar-track { flex: 1; height: 7px; border-radius: 4px; background: var(--border); overflow: hidden; }
.bar-fill { height: 100%; border-radius: 4px; }
.bar-fill-accent { background: var(--accent); }
.bar-fill-danger { background: var(--danger); }
.bar-fill-ok { background: var(--ok); }
.bar-val { font-size: 0.72rem; color: var(--muted); min-width: 28px; text-align: right; }

/* Stacked bars */
.stacked-bar { display: flex; height: 20px; border-radius: 5px; overflow: hidden; margin: 0.3rem 0; }
.seg { height: 100%; display: flex; align-items: center; justify-content: center; font-size: 0.65rem; font-weight: 700; color: white; }
.seg-finance { background: var(--finance); }
.seg-diligence { background: var(--diligence); }
.seg-other { background: var(--other); }

/* Misc */
.empty { color: var(--muted); font-style: italic; padding: 1rem 0; text-align: center; font-size: 0.82rem; }
.banner { padding: 0.5rem 0.8rem; border-radius: 6px; font-weight: 700; font-size: 0.78rem; margin-bottom: 0.75rem; display: flex; align-items: center; gap: 0.4rem; }
.banner-warn { background: var(--warn-soft); color: var(--warn); }
.highlight-billion { font-weight: 700; color: var(--danger); }
.text-trunc { max-width: 220px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: inline-block; vertical-align: bottom; }
.legend { display: flex; gap: 0.75rem; font-size: 0.7rem; margin-top: 0.5rem; }
.legend-item { display: flex; align-items: center; gap: 0.25rem; }
.legend-dot { width: 8px; height: 8px; border-radius: 2px; }
.collapsible-hdr { cursor: pointer; display: flex; align-items: center; gap: 0.4rem; padding: 0.3rem 0; font-weight: 600; font-size: 0.8rem; color: var(--fg); }
.collapsible-hdr::before { content: '\25b8'; font-size: 0.7rem; color: var(--muted); transition: transform 0.15s; }
.collapsible-hdr.open::before { transform: rotate(90deg); }
.collapsible-body { display: none; padding-left: 0.75rem; border-left: 2px solid var(--border); margin-top: 0.3rem; }
.collapsible-body.open { display: block; }
.sev-row { display: flex; gap: 0.5rem; margin-bottom: 0.75rem; }

/* Narrative cards */
.narrative-card { border-left: 4px solid var(--accent); margin-bottom: 1.25rem; }
.narrative-card h3 { font-size: 0.85rem; font-weight: 700; color: var(--fg); margin-top: 0.75rem; margin-bottom: 0.3rem; }
.narrative-card .narrative-body { font-size: 0.82rem; line-height: 1.55; color: var(--fg); white-space: pre-wrap; margin-bottom: 0.5rem; }
.narrative-card .narrative-meta { font-size: 0.72rem; color: var(--muted); margin-bottom: 0.5rem; }
</style>
</head>
<body>
<div class="shell">
<div class="header">
  <h1>Knowledge Graph Dashboard</h1>
  <span class="meta" id="meta-line"></span>
  <div class="domain-badges" id="domain-badges"></div>
</div>
<div class="kpi-strip" id="kpi-strip"></div>
<div class="tab-bar" id="tab-bar"></div>
<div id="tabs-container"></div>
</div>
<script>
/*__DATA__*/

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

// --- Header ---
document.getElementById('meta-line').textContent = (meta.nodes||0) + ' nodes \u2022 ' + (meta.edges||0) + ' edges \u2022 ' + Object.keys(analysis.communities||{}).length + ' communities \u2022 ' + new Date().toLocaleDateString();
if (summary && summary.domains) {
  const db = document.getElementById('domain-badges');
  Object.entries(summary.domains).forEach(([d, c]) => db.appendChild(domainBadge(d + ': ' + c)));
}

// --- KPI ---
const kpiStrip = document.getElementById('kpi-strip');
const kpis = [
  {v: meta.nodes||0, l: 'Nodes', c: ''},
  {v: meta.edges||0, l: 'Edges', c: ''},
  {v: Object.keys(analysis.communities||{}).length, l: 'Communities', c: ''},
  {v: redFlags.length, l: redFlags.filter(f=>f.severity==='high').length + ' high risk', c: 'kpi-danger'},
  {v: keyPerson.length, l: 'Key Persons', c: 'kpi-warn'},
];
if (pending.length) kpis.push({v: pending.length, l: 'Pending Review', c: 'kpi-warn'});
kpis.forEach(k => kpiStrip.appendChild(h('div', {className: 'kpi ' + k.c}, h('span', {className: 'kpi-value'}, String(k.v)), h('span', {className: 'kpi-label'}, k.l))));

// --- Tabs ---
const tabDefs = [
  {id: 'risk', label: 'Risk'},
  {id: 'structure', label: 'Structure'},
  {id: 'deep', label: 'Deep Dive'},
  {id: 'narratives', label: 'Narratives'},
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
  tc.style.gridTemplateColumns = '1fr';
  const layout = h('div', {className: 'col-layout'});

  // Left: Red Flags
  const leftPanel = h('div', {className: 'panel panel-danger'});
  leftPanel.appendChild(h('h2', null, '\u26a0 Red Flags'));
  leftPanel.appendChild(h('p', {className: 'section-desc'}, 'Governance and structural risks detected in the graph: related-party transactions, VIE consolidation risks, key-person dependencies, and conflict-of-interest patterns. Higher severity items represent greater potential exposure.'));
  if (redFlags.length) {
    const sev = h('div', {className: 'sev-row'});
    const high = redFlags.filter(f=>f.severity==='high').length;
    const med = redFlags.filter(f=>f.severity==='medium').length;
    const low = redFlags.filter(f=>f.severity==='low').length;
    if (high) sev.appendChild(h('span', {className: 'badge badge-high'}, high + ' HIGH'));
    if (med) sev.appendChild(h('span', {className: 'badge badge-medium'}, med + ' MEDIUM'));
    if (low) sev.appendChild(h('span', {className: 'badge badge-low'}, low + ' LOW'));
    leftPanel.appendChild(sev);
    const rows = redFlags.map(d => [severityBadge(d.severity||'medium'), d.type||'', d.label||d.node||'']);
    leftPanel.appendChild(sortableTable(['Sev', 'Type', 'Detail'], rows));
    // Related-party merged in
    if (relParty.length) {
      leftPanel.appendChild(h('h2', {style:'margin-top:1rem'}, 'Related-Party Transactions'));
      leftPanel.appendChild(h('p', {className: 'section-desc'}, 'Transactions between insiders, officers, or affiliated entities\u2014may indicate self-dealing or conflicts of interest requiring disclosure.'));
      const rpRows = relParty.map(d => [d.source_label, d.target_label, d.relation, String(d.confidence_score||d.confidence||'')]);
      leftPanel.appendChild(sortableTable(['Source', 'Target', 'Relation', 'Confidence'], rpRows));
    }
  } else {
    leftPanel.appendChild(h('div', {className: 'empty'}, 'No red flags detected.'));
  }
  layout.appendChild(leftPanel);

  // Right: Key Person + Pending
  const rightStack = h('div', {className: 'panel-stack'});

  const kpPanel = h('div', {className: 'panel panel-warn'});
  kpPanel.appendChild(h('h2', null, '\u{1f464} Key-Person Risk'));
  kpPanel.appendChild(h('p', {className: 'section-desc'}, 'Individuals whose removal would fragment the graph into disconnected components. High connectivity means the organization\u2019s operations or knowledge flow depend critically on this person.'));
  if (keyPerson.length) {
    const rows = keyPerson.map(d => {
      const conns = d.connections||d.degree||0, frags = d.fragments_into||0;
      const risk = frags > 5 ? 'high' : conns > 10 ? 'medium' : 'low';
      return [d.label||d.person, conns, frags, severityBadge(risk)];
    });
    kpPanel.appendChild(sortableTable(['Entity', 'Conn.', 'Fragments', 'Risk'], rows));
  } else { kpPanel.appendChild(h('div', {className: 'empty'}, 'No key-person risk.')); }
  rightStack.appendChild(kpPanel);

  if (pending.length) {
    const pendPanel = h('div', {className: 'panel panel-warn'});
    pendPanel.appendChild(h('div', {className: 'banner banner-warn'}, '\u23f3 ' + pending.length + ' candidates awaiting resolution'));
    pendPanel.appendChild(h('h2', null, 'Pending Candidates'));
    const rows = pending.map(d => [d.type||'', d.amount||'', d.window_snippet||'']);
    pendPanel.appendChild(sortableTable(['Type', 'Amount', 'Context'], rows));
    rightStack.appendChild(pendPanel);
  }

  layout.appendChild(rightStack);
  tc.appendChild(layout);
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
