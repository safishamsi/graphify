# write graph to HTML, JSON, SVG, GraphML, Obsidian vault, and Neo4j Cypher
from __future__ import annotations
import html as _html
import json
import math
import re
from collections import Counter
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph
from graphify.security import sanitize_label
from graphify.analyze import _node_community_map

def _strip_diacritics(text: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


COMMUNITY_COLORS = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
]

MAX_NODES_FOR_VIZ = 5_000


def _html_styles() -> str:
    return """<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f0f1a; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; display: flex; height: 100vh; overflow: hidden; }
  #graph { flex: 1; }
  #sidebar { width: 280px; background: #1a1a2e; border-left: 1px solid #2a2a4e; display: flex; flex-direction: column; overflow: hidden; }
  #search-wrap { padding: 12px; border-bottom: 1px solid #2a2a4e; }
  #search { width: 100%; background: #0f0f1a; border: 1px solid #3a3a5e; color: #e0e0e0; padding: 7px 10px; border-radius: 6px; font-size: 13px; outline: none; }
  #search:focus { border-color: #4E79A7; }
  #search-results { max-height: 140px; overflow-y: auto; padding: 4px 12px; border-bottom: 1px solid #2a2a4e; display: none; }
  .search-item { padding: 4px 6px; cursor: pointer; border-radius: 4px; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .search-item:hover { background: #2a2a4e; }
  #info-panel { padding: 14px; border-bottom: 1px solid #2a2a4e; min-height: 140px; }
  #info-panel h3 { font-size: 13px; color: #aaa; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }
  #info-content { font-size: 13px; color: #ccc; line-height: 1.6; }
  #info-content .field { margin-bottom: 5px; }
  #info-content .field b { color: #e0e0e0; }
  #info-content .empty { color: #555; font-style: italic; }
  .neighbor-link { display: block; padding: 2px 6px; margin: 2px 0; border-radius: 3px; cursor: pointer; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-left: 3px solid #333; }
  .neighbor-link:hover { background: #2a2a4e; }
  #neighbors-list { max-height: 160px; overflow-y: auto; margin-top: 4px; }
  #legend-wrap { flex: 1; overflow-y: auto; padding: 12px; }
  #legend-wrap h3 { font-size: 13px; color: #aaa; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
  .legend-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; cursor: pointer; border-radius: 4px; font-size: 12px; }
  .legend-item:hover { background: #2a2a4e; padding-left: 4px; }
  .legend-item.dimmed { opacity: 0.35; }
  .legend-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
  .legend-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .legend-count { color: #666; font-size: 11px; }
  #stats { padding: 10px 14px; border-top: 1px solid #2a2a4e; font-size: 11px; color: #555; }
</style>"""


def _hyperedge_script(hyperedges_json: str) -> str:
    return f"""<script>
// Render hyperedges as shaded regions
const hyperedges = {hyperedges_json};
// afterDrawing passes ctx already transformed to network coordinate space.
// Draw node positions raw — no manual pan/zoom/DPR math needed.
network.on('afterDrawing', function(ctx) {{
    hyperedges.forEach(h => {{
        const positions = h.nodes
            .map(nid => network.getPositions([nid])[nid])
            .filter(p => p !== undefined);
        if (positions.length < 2) return;
        ctx.save();
        ctx.globalAlpha = 0.12;
        ctx.fillStyle = '#6366f1';
        ctx.strokeStyle = '#6366f1';
        ctx.lineWidth = 2;
        ctx.beginPath();
        // Centroid and expanded hull in network coordinates
        const cx = positions.reduce((s, p) => s + p.x, 0) / positions.length;
        const cy = positions.reduce((s, p) => s + p.y, 0) / positions.length;
        const expanded = positions.map(p => ({{
            x: cx + (p.x - cx) * 1.15,
            y: cy + (p.y - cy) * 1.15
        }}));
        ctx.moveTo(expanded[0].x, expanded[0].y);
        expanded.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
        ctx.closePath();
        ctx.fill();
        ctx.globalAlpha = 0.4;
        ctx.stroke();
        // Label
        ctx.globalAlpha = 0.8;
        ctx.fillStyle = '#4f46e5';
        ctx.font = 'bold 11px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(h.label, cx, cy - 5);
        ctx.restore();
    }});
}});
</script>"""


def _html_script(nodes_json: str, edges_json: str, legend_json: str) -> str:
    return f"""<script>
const RAW_NODES = {nodes_json};
const RAW_EDGES = {edges_json};
const LEGEND = {legend_json};

// HTML-escape helper — prevents XSS when injecting graph data into innerHTML
function esc(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}}

// Build vis datasets
const nodesDS = new vis.DataSet(RAW_NODES.map(n => ({{
  id: n.id, label: n.label, color: n.color, size: n.size,
  font: n.font, title: n.title,
  _community: n.community, _community_name: n.community_name,
  _source_file: n.source_file, _file_type: n.file_type, _degree: n.degree,
}})));

const edgesDS = new vis.DataSet(RAW_EDGES.map((e, i) => ({{
  id: i, from: e.from, to: e.to,
  label: '',
  title: e.title,
  dashes: e.dashes,
  width: e.width,
  color: e.color,
  arrows: {{ to: {{ enabled: true, scaleFactor: 0.5 }} }},
}})));

const container = document.getElementById('graph');
const network = new vis.Network(container, {{ nodes: nodesDS, edges: edgesDS }}, {{
  physics: {{
    enabled: true,
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {{
      gravitationalConstant: -60,
      centralGravity: 0.005,
      springLength: 120,
      springConstant: 0.08,
      damping: 0.4,
      avoidOverlap: 0.8,
    }},
    stabilization: {{ iterations: 200, fit: true }},
  }},
  interaction: {{
    hover: true,
    tooltipDelay: 100,
    hideEdgesOnDrag: true,
    navigationButtons: false,
    keyboard: false,
  }},
  nodes: {{ shape: 'dot', borderWidth: 1.5 }},
  edges: {{ smooth: {{ type: 'continuous', roundness: 0.2 }}, selectionWidth: 3 }},
}});

network.once('stabilizationIterationsDone', () => {{
  network.setOptions({{ physics: {{ enabled: false }} }});
}});

function showInfo(nodeId) {{
  const n = nodesDS.get(nodeId);
  if (!n) return;
  const neighborIds = network.getConnectedNodes(nodeId);
  const neighborItems = neighborIds.map(nid => {{
    const nb = nodesDS.get(nid);
    const color = nb ? nb.color.background : '#555';
    return `<span class="neighbor-link" style="border-left-color:${{esc(color)}}" onclick="focusNode(${{JSON.stringify(nid)}})">${{esc(nb ? nb.label : nid)}}</span>`;
  }}).join('');
  document.getElementById('info-content').innerHTML = `
    <div class="field"><b>${{esc(n.label)}}</b></div>
    <div class="field">Type: ${{esc(n._file_type || 'unknown')}}</div>
    <div class="field">Community: ${{esc(n._community_name)}}</div>
    <div class="field">Source: ${{esc(n._source_file || '-')}}</div>
    <div class="field">Degree: ${{n._degree}}</div>
    ${{neighborIds.length ? `<div class="field" style="margin-top:8px;color:#aaa;font-size:11px">Neighbors (${{neighborIds.length}})</div><div id="neighbors-list">${{neighborItems}}</div>` : ''}}
  `;
}}

function focusNode(nodeId) {{
  network.focus(nodeId, {{ scale: 1.4, animation: true }});
  network.selectNodes([nodeId]);
  showInfo(nodeId);
}}

// Track hovered node — hover detection is more reliable than click params
let hoveredNodeId = null;
network.on('hoverNode', params => {{
  hoveredNodeId = params.node;
  container.style.cursor = 'pointer';
}});
network.on('blurNode', () => {{
  hoveredNodeId = null;
  container.style.cursor = 'default';
}});
container.addEventListener('click', () => {{
  if (hoveredNodeId !== null) {{
    showInfo(hoveredNodeId);
    network.selectNodes([hoveredNodeId]);
  }}
}});
network.on('click', params => {{
  if (params.nodes.length > 0) {{
    showInfo(params.nodes[0]);
  }} else if (hoveredNodeId === null) {{
    document.getElementById('info-content').innerHTML = '<span class="empty">Click a node to inspect it</span>';
  }}
}});

const searchInput = document.getElementById('search');
const searchResults = document.getElementById('search-results');
searchInput.addEventListener('input', () => {{
  const q = searchInput.value.toLowerCase().trim();
  searchResults.innerHTML = '';
  if (!q) {{ searchResults.style.display = 'none'; return; }}
  const matches = RAW_NODES.filter(n => n.label.toLowerCase().includes(q)).slice(0, 20);
  if (!matches.length) {{ searchResults.style.display = 'none'; return; }}
  searchResults.style.display = 'block';
  matches.forEach(n => {{
    const el = document.createElement('div');
    el.className = 'search-item';
    el.textContent = n.label;
    el.style.borderLeft = `3px solid ${{n.color.background}}`;
    el.style.paddingLeft = '8px';
    el.onclick = () => {{
      network.focus(n.id, {{ scale: 1.5, animation: true }});
      network.selectNodes([n.id]);
      showInfo(n.id);
      searchResults.style.display = 'none';
      searchInput.value = '';
    }};
    searchResults.appendChild(el);
  }});
}});
document.addEventListener('click', e => {{
  if (!searchResults.contains(e.target) && e.target !== searchInput)
    searchResults.style.display = 'none';
}});

const hiddenCommunities = new Set();
const legendEl = document.getElementById('legend');
LEGEND.forEach(c => {{
  const item = document.createElement('div');
  item.className = 'legend-item';
  item.innerHTML = `<div class="legend-dot" style="background:${{c.color}}"></div>
    <span class="legend-label">${{c.label}}</span>
    <span class="legend-count">${{c.count}}</span>`;
  item.onclick = () => {{
    if (hiddenCommunities.has(c.cid)) {{
      hiddenCommunities.delete(c.cid);
      item.classList.remove('dimmed');
    }} else {{
      hiddenCommunities.add(c.cid);
      item.classList.add('dimmed');
    }}
    const updates = RAW_NODES
      .filter(n => n.community === c.cid)
      .map(n => ({{ id: n.id, hidden: hiddenCommunities.has(c.cid) }}));
    nodesDS.update(updates);
  }};
  legendEl.appendChild(item);
}});
</script>"""


_CONFIDENCE_SCORE_DEFAULTS = {"EXTRACTED": 1.0, "INFERRED": 0.5, "AMBIGUOUS": 0.2}


def attach_hyperedges(G: nx.Graph, hyperedges: list) -> None:
    """Store hyperedges in the graph's metadata dict."""
    existing = G.graph.get("hyperedges", [])
    seen_ids = {h["id"] for h in existing}
    for h in hyperedges:
        if h.get("id") and h["id"] not in seen_ids:
            existing.append(h)
            seen_ids.add(h["id"])
    G.graph["hyperedges"] = existing


def to_json(G: nx.Graph, communities: dict[int, list[str]], output_path: str) -> None:
    node_community = _node_community_map(communities)
    try:
        data = json_graph.node_link_data(G, edges="links")
    except TypeError:
        data = json_graph.node_link_data(G)
    for node in data["nodes"]:
        node["community"] = node_community.get(node["id"])
        node["norm_label"] = _strip_diacritics(node.get("label", "")).lower()
    for link in data["links"]:
        if "confidence_score" not in link:
            conf = link.get("confidence", "EXTRACTED")
            link["confidence_score"] = _CONFIDENCE_SCORE_DEFAULTS.get(conf, 1.0)
    data["hyperedges"] = getattr(G, "graph", {}).get("hyperedges", [])
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def prune_dangling_edges(graph_data: dict) -> tuple[dict, int]:
    """Remove edges whose source or target node is not in the node set.

    Returns the cleaned graph_data dict and the number of pruned edges.
    """
    node_ids = {n["id"] for n in graph_data["nodes"]}
    links_key = "links" if "links" in graph_data else "edges"
    before = len(graph_data[links_key])
    graph_data[links_key] = [
        e for e in graph_data[links_key]
        if e["source"] in node_ids and e["target"] in node_ids
    ]
    return graph_data, before - len(graph_data[links_key])


def _cypher_escape(s: str) -> str:
    """Escape a string for safe embedding in a Cypher single-quoted literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def to_cypher(G: nx.Graph, output_path: str) -> None:
    lines = ["// Neo4j Cypher import - generated by /graphify", ""]
    for node_id, data in G.nodes(data=True):
        label = _cypher_escape(data.get("label", node_id))
        node_id_esc = _cypher_escape(node_id)
        _ft = re.sub(r"[^A-Za-z0-9_]", "", data.get("file_type", "unknown").capitalize())
        ftype = (_ft if _ft and _ft[0].isalpha() else "Entity")
        lines.append(f"MERGE (n:{ftype} {{id: '{node_id_esc}', label: '{label}'}});")
    lines.append("")
    for u, v, data in G.edges(data=True):
        rel = re.sub(r"[^A-Za-z0-9_]", "_", data.get("relation", "RELATES_TO").upper())
        conf = _cypher_escape(data.get("confidence", "EXTRACTED"))
        u_esc = _cypher_escape(u)
        v_esc = _cypher_escape(v)
        lines.append(
            f"MATCH (a {{id: '{u_esc}'}}), (b {{id: '{v_esc}'}}) "
            f"MERGE (a)-[:{rel} {{confidence: '{conf}'}}]->(b);"
        )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def to_html(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
) -> None:
    """Generate an interactive vis.js HTML visualization of the graph.

    Features: node size by degree, click-to-inspect panel, search box,
    community filter, physics clustering by community, confidence-styled edges.
    Raises ValueError if graph exceeds MAX_NODES_FOR_VIZ.
    """
    if G.number_of_nodes() > MAX_NODES_FOR_VIZ:
        raise ValueError(
            f"Graph has {G.number_of_nodes()} nodes - too large for HTML viz. "
            f"Use --no-viz or reduce input size."
        )

    node_community = _node_community_map(communities)
    degree = dict(G.degree())
    max_deg = max(degree.values(), default=1) or 1

    # Build nodes list for vis.js
    vis_nodes = []
    for node_id, data in G.nodes(data=True):
        cid = node_community.get(node_id, 0)
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        label = sanitize_label(data.get("label", node_id))
        deg = degree.get(node_id, 1)
        size = 10 + 30 * (deg / max_deg)
        # Only show label for high-degree nodes by default; others show on hover
        font_size = 12 if deg >= max_deg * 0.15 else 0
        vis_nodes.append({
            "id": node_id,
            "label": label,
            "color": {"background": color, "border": color, "highlight": {"background": "#ffffff", "border": color}},
            "size": round(size, 1),
            "font": {"size": font_size, "color": "#ffffff"},
            "title": _html.escape(label),
            "community": cid,
            "community_name": sanitize_label((community_labels or {}).get(cid, f"Community {cid}")),
            "source_file": sanitize_label(str(data.get("source_file") or "")),
            "file_type": data.get("file_type", ""),
            "degree": deg,
        })

    # Build edges list
    vis_edges = []
    for u, v, data in G.edges(data=True):
        confidence = data.get("confidence", "EXTRACTED")
        relation = data.get("relation", "")
        vis_edges.append({
            "from": u,
            "to": v,
            "label": relation,
            "title": _html.escape(f"{relation} [{confidence}]"),
            "dashes": confidence != "EXTRACTED",
            "width": 2 if confidence == "EXTRACTED" else 1,
            "color": {"opacity": 0.7 if confidence == "EXTRACTED" else 0.35},
            "confidence": confidence,
        })

    # Build community legend data
    legend_data = []
    for cid in sorted((community_labels or {}).keys()):
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        lbl = _html.escape(sanitize_label((community_labels or {}).get(cid, f"Community {cid}")))
        n = len(communities.get(cid, []))
        legend_data.append({"cid": cid, "color": color, "label": lbl, "count": n})

    # Escape </script> sequences so embedded JSON cannot break out of the script tag
    def _js_safe(obj) -> str:
        return json.dumps(obj).replace("</", "<\\/")

    nodes_json = _js_safe(vis_nodes)
    edges_json = _js_safe(vis_edges)
    legend_json = _js_safe(legend_data)
    hyperedges_json = _js_safe(getattr(G, "graph", {}).get("hyperedges", []))
    title = _html.escape(sanitize_label(str(output_path)))
    stats = f"{G.number_of_nodes()} nodes &middot; {G.number_of_edges()} edges &middot; {len(communities)} communities"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>graphify - {title}</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
{_html_styles()}
</head>
<body>
<div id="graph"></div>
<div id="sidebar">
  <div id="search-wrap">
    <input id="search" type="text" placeholder="Search nodes..." autocomplete="off">
    <div id="search-results"></div>
  </div>
  <div id="info-panel">
    <h3>Node Info</h3>
    <div id="info-content"><span class="empty">Click a node to inspect it</span></div>
  </div>
  <div id="legend-wrap">
    <h3>Communities</h3>
    <div id="legend"></div>
  </div>
  <div id="stats">{stats}</div>
</div>
{_html_script(nodes_json, edges_json, legend_json)}
{_hyperedge_script(hyperedges_json)}
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")


# Keep backward-compatible alias - skill.md calls generate_html
generate_html = to_html


def _html_3d_styles() -> str:
    return """<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f0f1a; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; overflow: hidden; }
  #graph-3d { width: 100vw; height: 100vh; }
  #sidebar { position: fixed; top: 0; right: 0; width: 300px; height: 100vh; background: rgba(26,26,46,0.95);
    border-left: 1px solid #2a2a4e; display: flex; flex-direction: column; overflow: hidden;
    transition: transform 0.3s ease; z-index: 10; backdrop-filter: blur(8px); }
  #sidebar.collapsed { transform: translateX(300px); }
  #sidebar-toggle { position: fixed; top: 12px; right: 12px; z-index: 20; background: rgba(26,26,46,0.85);
    border: 1px solid #3a3a5e; color: #e0e0e0; padding: 6px 10px; border-radius: 6px; cursor: pointer;
    font-size: 14px; backdrop-filter: blur(6px); }
  #sidebar-toggle:hover { background: #2a2a4e; }
  #search-wrap { padding: 12px; border-bottom: 1px solid #2a2a4e; }
  #search { width: 100%; background: #0f0f1a; border: 1px solid #3a3a5e; color: #e0e0e0;
    padding: 7px 10px; border-radius: 6px; font-size: 13px; outline: none; }
  #search:focus { border-color: #4E79A7; }
  #search-results { max-height: 140px; overflow-y: auto; padding: 4px 0; display: none; }
  .search-item { padding: 4px 8px; cursor: pointer; border-radius: 4px; font-size: 12px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .search-item:hover { background: #2a2a4e; }
  #info-panel { padding: 14px; border-bottom: 1px solid #2a2a4e; min-height: 120px; }
  #info-panel h3 { font-size: 13px; color: #aaa; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }
  #info-content { font-size: 13px; color: #ccc; line-height: 1.6; }
  #info-content .field { margin-bottom: 5px; }
  #info-content .field b { color: #e0e0e0; }
  #info-content .empty { color: #555; font-style: italic; }
  .neighbor-link { display: block; padding: 2px 6px; margin: 2px 0; border-radius: 3px; cursor: pointer;
    font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-left: 3px solid #333; }
  .neighbor-link:hover { background: #2a2a4e; }
  #neighbors-list { max-height: 120px; overflow-y: auto; margin-top: 4px; }
  #legend-wrap { flex: 1; overflow-y: auto; padding: 12px; }
  #legend-wrap h3 { font-size: 13px; color: #aaa; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }
  .legend-controls { display: flex; gap: 6px; margin-bottom: 8px; }
  .legend-controls button { background: #0f0f1a; border: 1px solid #3a3a5e; color: #aaa; padding: 3px 8px;
    border-radius: 4px; cursor: pointer; font-size: 11px; }
  .legend-controls button:hover { background: #2a2a4e; color: #e0e0e0; }
  .legend-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; cursor: pointer; border-radius: 4px; font-size: 12px; }
  .legend-item:hover { background: #2a2a4e; padding-left: 4px; }
  .legend-item.dimmed { opacity: 0.35; }
  .legend-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
  .legend-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .legend-count { color: #666; font-size: 11px; }
  .legend-check { width: 14px; height: 14px; accent-color: #4E79A7; cursor: pointer; }
  #stats { padding: 10px 14px; border-top: 1px solid #2a2a4e; font-size: 11px; color: #555; }
  #settings-btn { position: fixed; bottom: 16px; left: 16px; z-index: 20; background: rgba(26,26,46,0.7);
    border: 1px solid #3a3a5e; color: #888; padding: 6px 9px; border-radius: 8px; cursor: pointer;
    font-size: 16px; backdrop-filter: blur(6px); line-height: 1; }
  #settings-btn:hover { background: #2a2a4e; color: #e0e0e0; }
  #settings-panel { position: fixed; bottom: 52px; left: 16px; z-index: 20; background: rgba(26,26,46,0.92);
    border: 1px solid #3a3a5e; border-radius: 10px; padding: 12px 14px; width: 200px;
    backdrop-filter: blur(10px); display: none; }
  #settings-panel.open { display: block; }
  .setting-row { display: flex; align-items: center; justify-content: space-between; padding: 5px 0; }
  .setting-row label { font-size: 12px; color: #bbb; cursor: pointer; }
  .toggle { position: relative; display: inline-block; width: 34px; height: 18px; flex-shrink: 0; }
  .toggle input { position: absolute; width: 100%; height: 100%; opacity: 0; margin: 0; cursor: pointer; z-index: 1; }
  .toggle .slider { position: absolute; inset: 0; background: #2a2a4e; border-radius: 9px; pointer-events: none;
    border: 1px solid #3a3a5e; transition: background 0.2s; }
  .toggle .slider::before { content: ''; position: absolute; width: 12px; height: 12px; left: 2px; top: 2px;
    background: #888; border-radius: 50%; transition: transform 0.2s, background 0.2s; }
  .toggle input:checked + .slider { background: #4E79A7; border-color: #4E79A7; }
  .toggle input:checked + .slider::before { transform: translateX(16px); background: #fff; }
  #help-hints { position: fixed; bottom: 12px; left: 50%; transform: translateX(-50%); z-index: 5;
    font-size: 11px; color: rgba(255,255,255,0.3); pointer-events: none; white-space: nowrap; }
</style>"""


def _html_3d_script(nodes_json: str, edges_json: str, legend_json: str) -> str:
    return f"""<script>
const RAW_NODES = {nodes_json};
const RAW_EDGES = {edges_json};
const LEGEND = {legend_json};

function esc(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}}

// --- State ---
const hiddenCommunities = new Set();
let selectedNodeId = null;
let hoveredNodeId = null;
const settings = {{ hoverHighlight: false, showEdges: true, showLabels: true }};

// Adjacency map for neighbor highlight
const adjacency = new Map();
RAW_EDGES.forEach(e => {{
  if (!adjacency.has(e.source)) adjacency.set(e.source, new Set());
  if (!adjacency.has(e.target)) adjacency.set(e.target, new Set());
  adjacency.get(e.source).add(e.target);
  adjacency.get(e.target).add(e.source);
}});

function isNeighbor(nodeId, activeId) {{
  if (!activeId) return false;
  if (nodeId === activeId) return true;
  const nbrs = adjacency.get(activeId);
  return nbrs ? nbrs.has(nodeId) : false;
}}

function getActiveId() {{ return hoveredNodeId || selectedNodeId; }}

// --- Build graph data (respecting community filters) ---
function buildGraphData() {{
  const visibleNodes = RAW_NODES.filter(n => !hiddenCommunities.has(n.community));
  const visibleIds = new Set(visibleNodes.map(n => n.id));
  const visibleEdges = RAW_EDGES.filter(e => visibleIds.has(e.source) && visibleIds.has(e.target));
  return {{
    nodes: visibleNodes.map(n => ({{ ...n }})),
    links: visibleEdges.map(e => ({{ source: e.source, target: e.target, relation: e.relation,
      confidence: e.confidence, width: e.confidence === 'EXTRACTED' ? 1.5 : 0.7,
      color: e.confidence === 'EXTRACTED' ? 'rgba(255,255,255,0.35)' : 'rgba(255,255,255,0.15)' }})),
  }};
}}

// --- Initialize 3D graph ---
const container = document.getElementById('graph-3d');
const graph = ForceGraph3D()(container)
  .backgroundColor('#0f0f1a')
  .showNavInfo(false)
  .nodeColor(n => {{
    const active = getActiveId();
    if (active) {{
      if (n.id === active) return '#ffffff';
      if (isNeighbor(n.id, active)) return n.color;
      return '#1a1a2e';
    }}
    return n.color;
  }})
  .nodeVal('val')
  .nodeOpacity(0.9)
  .nodeResolution(16)
  .nodeLabel(n => `<div style="background:rgba(15,15,26,0.9);padding:6px 10px;border-radius:6px;font-size:12px;max-width:260px;border:1px solid #3a3a5e">
    <b>${{esc(n.label)}}</b><br/>
    <span style="color:#aaa">Community:</span> ${{esc(n.community_name)}}<br/>
    <span style="color:#aaa">Source:</span> ${{esc(n.source_file || '-')}}<br/>
    <span style="color:#aaa">Degree:</span> ${{n.degree}}
  </div>`)
  .linkWidth(l => {{
    const active = getActiveId();
    if (active) {{
      const src = typeof l.source === 'object' ? l.source.id : l.source;
      const tgt = typeof l.target === 'object' ? l.target.id : l.target;
      if (src === active || tgt === active) return 2.0;
      return 0.2;
    }}
    return l.width;
  }})
  .linkColor(l => {{
    const active = getActiveId();
    if (active) {{
      const src = typeof l.source === 'object' ? l.source.id : l.source;
      const tgt = typeof l.target === 'object' ? l.target.id : l.target;
      if (src === active) return 'rgba(200,60,60,0.55)';
      if (tgt === active) return 'rgba(78,121,167,0.55)';
      return 'rgba(255,255,255,0.03)';
    }}
    return l.color;
  }})
  .linkOpacity(0.7)
  .linkDirectionalParticles(l => {{
    const active = getActiveId();
    if (!active) return 0;
    const src = typeof l.source === 'object' ? l.source.id : l.source;
    const tgt = typeof l.target === 'object' ? l.target.id : l.target;
    return (src === active || tgt === active) ? 2 : 0;
  }})
  .linkDirectionalParticleWidth(1.5)
  .linkDirectionalParticleSpeed(0.005)
  .linkDirectionalParticleColor(l => {{
    const active = getActiveId();
    if (!active) return 'rgba(78,121,167,0.8)';
    const src = typeof l.source === 'object' ? l.source.id : l.source;
    return src === active ? 'rgba(200,60,60,0.8)' : 'rgba(78,121,167,0.8)';
  }})
  .onNodeClick(node => {{
    if (!node) return;
    selectedNodeId = selectedNodeId === node.id ? null : node.id;
    showInfo(node.id);
    graph.nodeColor(graph.nodeColor()).linkColor(graph.linkColor()).linkWidth(graph.linkWidth())
      .linkDirectionalParticles(graph.linkDirectionalParticles());
    if (selectedNodeId && node.x !== undefined) {{
      const dist = 120;
      const r = 1 + dist / Math.hypot(node.x, node.y, node.z || 1);
      graph.cameraPosition(
        {{ x: node.x * r, y: node.y * r, z: node.z * r }},
        {{ x: node.x, y: node.y, z: node.z }}, 1000);
    }}
  }})
  .onNodeHover(node => {{
    container.style.cursor = node ? 'pointer' : 'default';
    if (settings.hoverHighlight) {{
      hoveredNodeId = node ? node.id : null;
      graph.nodeColor(graph.nodeColor()).linkColor(graph.linkColor()).linkWidth(graph.linkWidth())
        .linkDirectionalParticles(graph.linkDirectionalParticles());
    }}
  }})
  .onBackgroundClick(() => {{
    selectedNodeId = null;
    hoveredNodeId = null;
    document.getElementById('info-content').innerHTML = '<span class="empty">Click a node to inspect it</span>';
    graph.nodeColor(graph.nodeColor()).linkColor(graph.linkColor()).linkWidth(graph.linkWidth())
      .linkDirectionalParticles(graph.linkDirectionalParticles());
  }});

// ESC to deselect
document.addEventListener('keydown', e => {{
  if (e.key === 'Escape' && selectedNodeId) {{
    selectedNodeId = null;
    hoveredNodeId = null;
    document.getElementById('info-content').innerHTML = '<span class="empty">Click a node to inspect it</span>';
    graph.nodeColor(graph.nodeColor()).linkColor(graph.linkColor()).linkWidth(graph.linkWidth())
      .linkDirectionalParticles(graph.linkDirectionalParticles());
  }}
}});

// Force tuning
graph.d3AlphaDecay(0.03).d3VelocityDecay(0.5);
const charge = graph.d3Force('charge');
if (charge) {{ charge.strength(-50); charge.distanceMax(300); }}
const link = graph.d3Force('link');
if (link) {{ link.distance(30); }}

// Load initial data
graph.graphData(buildGraphData());

// Label overlay - append AFTER graph init (ForceGraph3D replaces container content)
const labelLayer = document.createElement('div');
labelLayer.id = 'label-layer';
labelLayer.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;overflow:hidden;z-index:5;';
container.style.position = 'relative';
container.appendChild(labelLayer);

const labelElements = new Map();
RAW_NODES.forEach(n => {{
  const el = document.createElement('div');
  el.className = 'node-label';
  el.textContent = n.label;
  el.style.cssText = 'position:absolute;color:#dcddde;font-size:11px;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;white-space:nowrap;opacity:0;transform:translate(-50%,-100%);text-shadow:0 0 4px #0f0f1a,0 0 8px #0f0f1a;';
  labelLayer.appendChild(el);
  labelElements.set(n.id, el);
}});

// Configure orbit controls
const controls = graph.controls();
if (controls) {{
  controls.zoomSpeed = 2.5;
  controls.enableDamping = true;
  controls.dampingFactor = 0.12;
  // Middle mouse button = rotate (same as left), disable its default zoom behavior
  if (controls.mouseButtons !== undefined) {{
    controls.mouseButtons.MIDDLE = controls.mouseButtons.LEFT;
  }}
}}

// --- Label visibility: distance-based + max cap ---
const MAX_VISIBLE_LABELS = 25;

const degreeMap = new Map();
RAW_EDGES.forEach(e => {{
  degreeMap.set(e.source, (degreeMap.get(e.source) || 0) + 1);
  degreeMap.set(e.target, (degreeMap.get(e.target) || 0) + 1);
}});
const maxDegree = Math.max(1, ...degreeMap.values());

function updateLabels() {{
  if (!settings.showLabels) {{
    labelElements.forEach(el => {{ el.style.opacity = '0'; }});
    requestAnimationFrame(updateLabels);
    return;
  }}
  const cameraPos = graph.camera().position;
  const active = getActiveId();
  const activeNbrs = active ? (adjacency.get(active) || new Set()) : null;
  const nodes = graph.graphData().nodes;

  // When a node is selected/hovered: only show labels for it and its neighbors
  if (active) {{
    for (const n of nodes) {{
      const el = labelElements.get(n.id);
      if (!el) continue;
      if (n.x === undefined) {{ el.style.opacity = '0'; continue; }}
      const isRelevant = n.id === active || activeNbrs.has(n.id);
      if (isRelevant) {{
        const screen = graph.graph2ScreenCoords(n.x, n.y, n.z);
        if (screen) {{
          el.style.left = screen.x + 'px';
          el.style.top = (screen.y - Math.cbrt(n.val) * 4 - 6) + 'px';
          el.style.opacity = '1';
        }} else {{
          el.style.opacity = '0';
        }}
      }} else {{
        el.style.opacity = '0';
      }}
    }}
    requestAnimationFrame(updateLabels);
    return;
  }}

  // No selection: show labels for the N closest nodes, weighted by degree
  const scored = [];
  for (const n of nodes) {{
    if (n.x === undefined) continue;
    const dx = n.x - cameraPos.x, dy = n.y - cameraPos.y, dz = n.z - cameraPos.z;
    const dist = Math.sqrt(dx*dx + dy*dy + dz*dz);
    const degree = degreeMap.get(n.id) || 0;
    const importance = degree / maxDegree;
    // Lower score = more visible (closer + more important)
    const score = dist / (1 + importance * 2);
    scored.push({{ id: n.id, n, dist, score }});
  }}
  scored.sort((a, b) => a.score - b.score);

  const visible = new Set();
  for (let i = 0; i < Math.min(MAX_VISIBLE_LABELS, scored.length); i++) {{
    visible.add(scored[i].id);
  }}

  for (const n of nodes) {{
    const el = labelElements.get(n.id);
    if (!el) continue;
    if (n.x === undefined || !visible.has(n.id)) {{
      el.style.opacity = '0';
      continue;
    }}
    const screen = graph.graph2ScreenCoords(n.x, n.y, n.z);
    if (!screen) {{ el.style.opacity = '0'; continue; }}
    el.style.left = screen.x + 'px';
    el.style.top = (screen.y - Math.cbrt(n.val) * 4 - 6) + 'px';
    // Fade based on rank position
    const idx = scored.findIndex(s => s.id === n.id);
    const fade = idx < MAX_VISIBLE_LABELS * 0.7 ? 1 : 1 - (idx - MAX_VISIBLE_LABELS * 0.7) / (MAX_VISIBLE_LABELS * 0.3);
    el.style.opacity = String(Math.max(0, fade));
  }}
  requestAnimationFrame(updateLabels);
}}
requestAnimationFrame(updateLabels);

// --- Sidebar: toggle ---
document.getElementById('sidebar-toggle').addEventListener('click', () => {{
  const sb = document.getElementById('sidebar');
  sb.classList.toggle('collapsed');
  const btn = document.getElementById('sidebar-toggle');
  btn.textContent = sb.classList.contains('collapsed') ? '\u25C0' : '\u25B6';
  setTimeout(() => graph.width(container.offsetWidth), 350);
}});

// --- Sidebar: info panel ---
function showInfo(nodeId) {{
  const n = RAW_NODES.find(x => x.id === nodeId);
  if (!n) return;
  const nbrs = adjacency.get(nodeId) || new Set();
  const nbrItems = [...nbrs].slice(0, 30).map(nid => {{
    const nb = RAW_NODES.find(x => x.id === nid);
    const color = nb ? nb.color : '#555';
    const label = nb ? nb.label : nid;
    return '<span class="neighbor-link" style="border-left-color:' + esc(color) + '" onclick="focusNode(\\''+nid.replace(/'/g,"\\\\'")+'\\')">'+esc(label)+'</span>';
  }}).join('');
  document.getElementById('info-content').innerHTML =
    '<div class="field"><b>' + esc(n.label) + '</b></div>' +
    '<div class="field">Community: ' + esc(n.community_name) + '</div>' +
    '<div class="field">Source: ' + esc(n.source_file || '-') + '</div>' +
    '<div class="field">Degree: ' + n.degree + '</div>' +
    (nbrs.size ? '<div class="field" style="margin-top:8px;color:#aaa;font-size:11px">Neighbors ('+nbrs.size+')</div><div id="neighbors-list">'+nbrItems+'</div>' : '');
}}

function focusNode(nodeId) {{
  const n = graph.graphData().nodes.find(x => x.id === nodeId);
  if (!n) return;
  selectedNodeId = nodeId;
  showInfo(nodeId);
  if (n.x !== undefined) {{
    const dist = 120;
    const r = 1 + dist / Math.hypot(n.x, n.y, n.z || 1);
    graph.cameraPosition(
      {{ x: n.x * r, y: n.y * r, z: n.z * r }},
      {{ x: n.x, y: n.y, z: n.z }}, 1000);
  }}
  graph.nodeColor(graph.nodeColor()).linkColor(graph.linkColor()).linkWidth(graph.linkWidth())
    .linkDirectionalParticles(graph.linkDirectionalParticles());
}}
window.focusNode = focusNode;

// --- Sidebar: search ---
const searchInput = document.getElementById('search');
const searchResults = document.getElementById('search-results');
searchInput.addEventListener('input', () => {{
  const q = searchInput.value.toLowerCase().trim();
  searchResults.innerHTML = '';
  if (!q) {{ searchResults.style.display = 'none'; return; }}
  const matches = RAW_NODES.filter(n => n.label.toLowerCase().includes(q)).slice(0, 20);
  if (!matches.length) {{ searchResults.style.display = 'none'; return; }}
  searchResults.style.display = 'block';
  matches.forEach(n => {{
    const el = document.createElement('div');
    el.className = 'search-item';
    el.textContent = n.label;
    el.style.borderLeft = '3px solid ' + n.color;
    el.style.paddingLeft = '8px';
    el.onclick = () => {{ focusNode(n.id); searchResults.style.display = 'none'; searchInput.value = ''; }};
    searchResults.appendChild(el);
  }});
}});
document.addEventListener('click', e => {{
  if (!searchResults.contains(e.target) && e.target !== searchInput)
    searchResults.style.display = 'none';
}});

// --- Sidebar: community legend with checkboxes ---
function rebuildLegend() {{
  const legendEl = document.getElementById('legend');
  legendEl.innerHTML = '';
  LEGEND.forEach(c => {{
    const item = document.createElement('div');
    item.className = 'legend-item' + (hiddenCommunities.has(c.cid) ? ' dimmed' : '');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'legend-check';
    cb.checked = !hiddenCommunities.has(c.cid);
    cb.onchange = () => {{ toggleCommunity(c.cid); }};
    const dot = document.createElement('div');
    dot.className = 'legend-dot';
    dot.style.background = c.color;
    const lbl = document.createElement('span');
    lbl.className = 'legend-label';
    lbl.textContent = c.label;
    const cnt = document.createElement('span');
    cnt.className = 'legend-count';
    cnt.textContent = c.count;
    item.appendChild(cb);
    item.appendChild(dot);
    item.appendChild(lbl);
    item.appendChild(cnt);
    legendEl.appendChild(item);
  }});
}}

function toggleCommunity(cid) {{
  if (hiddenCommunities.has(cid)) hiddenCommunities.delete(cid);
  else hiddenCommunities.add(cid);
  graph.graphData(buildGraphData());
  rebuildLegend();
}}

document.getElementById('select-all').addEventListener('click', () => {{
  hiddenCommunities.clear();
  graph.graphData(buildGraphData());
  rebuildLegend();
}});
document.getElementById('deselect-all').addEventListener('click', () => {{
  LEGEND.forEach(c => hiddenCommunities.add(c.cid));
  graph.graphData(buildGraphData());
  rebuildLegend();
}});

rebuildLegend();

// Handle window resize
window.addEventListener('resize', () => {{
  graph.width(container.offsetWidth).height(container.offsetHeight);
}});

// --- Settings panel ---
document.getElementById('settings-btn').addEventListener('click', () => {{
  document.getElementById('settings-panel').classList.toggle('open');
}});

document.getElementById('opt-hover').addEventListener('change', e => {{
  settings.hoverHighlight = e.target.checked;
}});

document.getElementById('opt-edges').addEventListener('change', e => {{
  settings.showEdges = e.target.checked;
  graph.linkVisibility(settings.showEdges);
}});

document.getElementById('opt-labels').addEventListener('change', e => {{
  settings.showLabels = e.target.checked;
  if (!settings.showLabels) {{
    labelElements.forEach(el => {{ el.style.opacity = '0'; }});
  }}
}});

// Make settings accessible to other functions
window._graphSettings = settings;
</script>"""


def to_html_3d(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
) -> None:
    """Generate an interactive 3D force-directed HTML visualization using 3d-force-graph.

    Same input signature as to_html. Produces a self-contained HTML file.
    Uses 3d-force-graph (MIT, CDN-loaded) for WebGL-based 3D rendering.
    """
    if G.number_of_nodes() > MAX_NODES_FOR_VIZ:
        raise ValueError(
            f"Graph has {G.number_of_nodes()} nodes - too large for HTML viz. "
            f"Use --no-viz or reduce input size."
        )

    node_community = _node_community_map(communities)
    degree = dict(G.degree())
    max_deg = max(degree.values()) if degree else 1
    if max_deg == 0:
        max_deg = 1

    # Build nodes list for 3d-force-graph
    fg_nodes = []
    for node_id, data in G.nodes(data=True):
        cid = node_community.get(node_id, 0)
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        label = sanitize_label(data.get("label", node_id))
        deg = degree.get(node_id, 1)
        val = 1 + 4 * (deg / max_deg)
        fg_nodes.append({
            "id": node_id,
            "label": label,
            "color": color,
            "val": round(val, 2),
            "community": cid,
            "community_name": sanitize_label(
                (community_labels or {}).get(cid, f"Community {cid}")
            ),
            "source_file": sanitize_label(data.get("source_file", "")),
            "file_type": data.get("file_type", ""),
            "degree": deg,
        })

    # Build edges list
    fg_edges = []
    for u, v, data in G.edges(data=True):
        confidence = data.get("confidence", "EXTRACTED")
        relation = data.get("relation", "")
        fg_edges.append({
            "source": u,
            "target": v,
            "relation": relation,
            "confidence": confidence,
        })

    # Build community legend data
    legend_data = []
    for cid in sorted(communities.keys()):
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        lbl = _html.escape(
            sanitize_label((community_labels or {}).get(cid, f"Community {cid}"))
        )
        n = len(communities.get(cid, []))
        legend_data.append({"cid": cid, "color": color, "label": lbl, "count": n})

    def _js_safe(obj) -> str:
        return json.dumps(obj).replace("</", "<\\/")

    nodes_json = _js_safe(fg_nodes)
    edges_json = _js_safe(fg_edges)
    legend_json = _js_safe(legend_data)
    title = _html.escape(sanitize_label(str(output_path)))
    stats = (
        f"{G.number_of_nodes()} nodes &middot; "
        f"{G.number_of_edges()} edges &middot; "
        f"{len(communities)} communities"
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>graphify 3D - {title}</title>
<script src="https://unpkg.com/3d-force-graph"></script>
{_html_3d_styles()}
</head>
<body>
<div id="graph-3d"></div>
<button id="sidebar-toggle">&#9654;</button>
<div id="sidebar">
  <div id="search-wrap">
    <input id="search" type="text" placeholder="Search nodes..." autocomplete="off">
    <div id="search-results"></div>
  </div>
  <div id="info-panel">
    <h3>Node Info</h3>
    <div id="info-content"><span class="empty">Click a node to inspect it</span></div>
  </div>
  <div id="legend-wrap">
    <h3>Communities</h3>
    <div class="legend-controls">
      <button id="select-all">Select All</button>
      <button id="deselect-all">Deselect All</button>
    </div>
    <div id="legend"></div>
  </div>
  <div id="stats">{stats}</div>
</div>
<button id="settings-btn" title="Settings">&#9881;</button>
<div id="settings-panel">
  <div class="setting-row">
    <label for="opt-hover">Hover highlight</label>
    <div class="toggle"><input type="checkbox" id="opt-hover"><span class="slider"></span></div>
  </div>
  <div class="setting-row">
    <label for="opt-edges">Show edges</label>
    <div class="toggle"><input type="checkbox" id="opt-edges" checked><span class="slider"></span></div>
  </div>
  <div class="setting-row">
    <label for="opt-labels">Show labels</label>
    <div class="toggle"><input type="checkbox" id="opt-labels" checked><span class="slider"></span></div>
  </div>
</div>
<div id="help-hints">Click node to inspect &middot; ESC to deselect &middot; Scroll to zoom &middot; Drag to orbit</div>
{_html_3d_script(nodes_json, edges_json, legend_json)}
</body>
</html>"""

    Path(output_path).write_text(html_content, encoding="utf-8")


generate_html_3d = to_html_3d


def to_obsidian(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_dir: str,
    community_labels: dict[int, str] | None = None,
    cohesion: dict[int, float] | None = None,
) -> int:
    """Export graph as an Obsidian vault - one .md file per node with [[wikilinks]],
    plus one _COMMUNITY_name.md overview note per community (sorted to top by underscore prefix).

    Open the output directory as a vault in Obsidian to get an interactive
    graph view with community colors and full-text search over node metadata.

    Returns the number of node notes + community notes written.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    node_community = _node_community_map(communities)

    # Map node_id → safe filename so wikilinks stay consistent.
    # Deduplicate: if two nodes produce the same filename, append a numeric suffix.
    def safe_name(label: str) -> str:
        cleaned = re.sub(r'[\\/*?:"<>|#^[\]]', "", label.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")).strip()
        # Strip trailing .md/.mdx/.markdown so "CLAUDE.md" doesn't become "CLAUDE.md.md"
        cleaned = re.sub(r"\.(md|mdx|markdown)$", "", cleaned, flags=re.IGNORECASE)
        return cleaned or "unnamed"

    node_filename: dict[str, str] = {}
    seen_names: dict[str, int] = {}
    for node_id, data in G.nodes(data=True):
        base = safe_name(data.get("label", node_id))
        if base in seen_names:
            seen_names[base] += 1
            node_filename[node_id] = f"{base}_{seen_names[base]}"
        else:
            seen_names[base] = 0
            node_filename[node_id] = base

    # Helper: compute dominant confidence for a node across all its edges
    def _dominant_confidence(node_id: str) -> str:
        confs = []
        for u, v, edata in G.edges(node_id, data=True):
            confs.append(edata.get("confidence", "EXTRACTED"))
        if not confs:
            return "EXTRACTED"
        return Counter(confs).most_common(1)[0][0]

    # Map file_type → graphify tag
    _FTYPE_TAG = {
        "code": "graphify/code",
        "document": "graphify/document",
        "paper": "graphify/paper",
        "image": "graphify/image",
    }

    # Write one .md file per node
    for node_id, data in G.nodes(data=True):
        label = data.get("label", node_id)
        cid = node_community.get(node_id)
        community_name = (
            community_labels.get(cid, f"Community {cid}")
            if community_labels and cid is not None
            else f"Community {cid}"
        )

        # Build tags for this node
        ftype = data.get("file_type", "")
        ftype_tag = _FTYPE_TAG.get(ftype, f"graphify/{ftype}" if ftype else "graphify/document")
        dom_conf = _dominant_confidence(node_id)
        conf_tag = f"graphify/{dom_conf}"
        comm_tag = f"community/{community_name.replace(' ', '_')}"
        node_tags = [ftype_tag, conf_tag, comm_tag]

        lines: list[str] = []

        # YAML frontmatter - readable in Obsidian's properties panel
        lines += [
            "---",
            f'source_file: "{data.get("source_file", "")}"',
            f'type: "{ftype}"',
            f'community: "{community_name}"',
        ]
        if data.get("source_location"):
            lines.append(f'location: "{data["source_location"]}"')
        # Add tags list to frontmatter
        lines.append("tags:")
        for tag in node_tags:
            lines.append(f"  - {tag}")
        lines += ["---", "", f"# {label}", ""]

        # Outgoing edges as wikilinks
        neighbors = list(G.neighbors(node_id))
        if neighbors:
            lines.append("## Connections")
            for neighbor in sorted(neighbors, key=lambda n: G.nodes[n].get("label", n)):
                edge_data = G.edges[node_id, neighbor]
                neighbor_label = node_filename[neighbor]
                relation = edge_data.get("relation", "")
                confidence = edge_data.get("confidence", "EXTRACTED")
                lines.append(f"- [[{neighbor_label}]] - `{relation}` [{confidence}]")
            lines.append("")

        # Inline tags at bottom of note body (for Obsidian tag panel)
        inline_tags = " ".join(f"#{t}" for t in node_tags)
        lines.append(inline_tags)

        fname = node_filename[node_id] + ".md"
        (out / fname).write_text("\n".join(lines), encoding="utf-8")

    # Write one _COMMUNITY_name.md overview note per community
    # Build inter-community edge counts for "Connections to other communities"
    inter_community_edges: dict[int, dict[int, int]] = {}
    for cid in communities:
        inter_community_edges[cid] = {}
    for u, v in G.edges():
        cu = node_community.get(u)
        cv = node_community.get(v)
        if cu is not None and cv is not None and cu != cv:
            inter_community_edges.setdefault(cu, {})
            inter_community_edges.setdefault(cv, {})
            inter_community_edges[cu][cv] = inter_community_edges[cu].get(cv, 0) + 1
            inter_community_edges[cv][cu] = inter_community_edges[cv].get(cu, 0) + 1

    # Precompute per-node community reach (number of distinct communities a node connects to)
    def _community_reach(node_id: str) -> int:
        neighbor_cids = {
            node_community[nb]
            for nb in G.neighbors(node_id)
            if nb in node_community and node_community[nb] != node_community.get(node_id)
        }
        return len(neighbor_cids)

    community_notes_written = 0
    for cid, members in communities.items():
        community_name = (
            community_labels.get(cid, f"Community {cid}")
            if community_labels and cid is not None
            else f"Community {cid}"
        )
        n_members = len(members)
        coh_value = cohesion.get(cid) if cohesion else None

        lines: list[str] = []

        # YAML frontmatter
        lines.append("---")
        lines.append("type: community")
        if coh_value is not None:
            lines.append(f"cohesion: {coh_value:.2f}")
        lines.append(f"members: {n_members}")
        lines.append("---")
        lines.append("")
        lines.append(f"# {community_name}")
        lines.append("")

        # Cohesion + member count summary
        if coh_value is not None:
            cohesion_desc = (
                "tightly connected" if coh_value >= 0.7
                else "moderately connected" if coh_value >= 0.4
                else "loosely connected"
            )
            lines.append(f"**Cohesion:** {coh_value:.2f} - {cohesion_desc}")
        lines.append(f"**Members:** {n_members} nodes")
        lines.append("")

        # Members section
        lines.append("## Members")
        for node_id in sorted(members, key=lambda n: G.nodes[n].get("label", n)):
            data = G.nodes[node_id]
            node_label = node_filename[node_id]
            ftype = data.get("file_type", "")
            source = data.get("source_file", "")
            entry = f"- [[{node_label}]]"
            if ftype:
                entry += f" - {ftype}"
            if source:
                entry += f" - {source}"
            lines.append(entry)
        lines.append("")

        # Dataview live query (improvement 2)
        comm_tag_name = community_name.replace(" ", "_")
        lines.append("## Live Query (requires Dataview plugin)")
        lines.append("")
        lines.append("```dataview")
        lines.append(f"TABLE source_file, type FROM #community/{comm_tag_name}")
        lines.append("SORT file.name ASC")
        lines.append("```")
        lines.append("")

        # Connections to other communities
        cross = inter_community_edges.get(cid, {})
        if cross:
            lines.append("## Connections to other communities")
            for other_cid, edge_count in sorted(cross.items(), key=lambda x: -x[1]):
                other_name = (
                    community_labels.get(other_cid, f"Community {other_cid}")
                    if community_labels and other_cid is not None
                    else f"Community {other_cid}"
                )
                other_safe = safe_name(other_name)
                lines.append(f"- {edge_count} edge{'s' if edge_count != 1 else ''} to [[_COMMUNITY_{other_safe}]]")
            lines.append("")

        # Top bridge nodes - highest degree nodes that connect to other communities
        bridge_nodes = [
            (node_id, G.degree(node_id), _community_reach(node_id))
            for node_id in members
            if _community_reach(node_id) > 0
        ]
        bridge_nodes.sort(key=lambda x: (-x[2], -x[1]))
        top_bridges = bridge_nodes[:5]
        if top_bridges:
            lines.append("## Top bridge nodes")
            for node_id, degree, reach in top_bridges:
                node_label = node_filename[node_id]
                lines.append(
                    f"- [[{node_label}]] - degree {degree}, connects to {reach} "
                    f"{'community' if reach == 1 else 'communities'}"
                )

        community_safe = safe_name(community_name)
        fname = f"_COMMUNITY_{community_safe}.md"
        (out / fname).write_text("\n".join(lines), encoding="utf-8")
        community_notes_written += 1

    # Improvement 4: write .obsidian/graph.json to color nodes by community in graph view
    obsidian_dir = out / ".obsidian"
    obsidian_dir.mkdir(exist_ok=True)
    graph_config = {
        "colorGroups": [
            {
                "query": f"tag:#community/{label.replace(' ', '_')}",
                "color": {"a": 1, "rgb": int(COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)].lstrip('#'), 16)}
            }
            for cid, label in sorted((community_labels or {}).items())
        ]
    }
    (obsidian_dir / "graph.json").write_text(json.dumps(graph_config, indent=2), encoding="utf-8")

    return G.number_of_nodes() + community_notes_written


def to_canvas(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    node_filenames: dict[str, str] | None = None,
) -> None:
    """Export graph as an Obsidian Canvas file - communities as groups, nodes as cards.

    Generates a structured layout: communities arranged in a grid, nodes within
    each community arranged in rows. Edges shown between connected nodes.
    Opens in Obsidian as an infinite canvas with community groupings visible.
    """
    # Obsidian canvas color codes (cycle through for communities)
    CANVAS_COLORS = ["1", "2", "3", "4", "5", "6"]  # red, orange, yellow, green, cyan, purple

    def safe_name(label: str) -> str:
        cleaned = re.sub(r'[\\/*?:"<>|#^[\]]', "", label.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")).strip()
        cleaned = re.sub(r"\.(md|mdx|markdown)$", "", cleaned, flags=re.IGNORECASE)
        return cleaned or "unnamed"

    # Build node_filenames if not provided (same dedup logic as to_obsidian)
    if node_filenames is None:
        node_filenames = {}
        seen_names: dict[str, int] = {}
        for node_id, data in G.nodes(data=True):
            base = safe_name(data.get("label", node_id))
            if base in seen_names:
                seen_names[base] += 1
                node_filenames[node_id] = f"{base}_{seen_names[base]}"
            else:
                seen_names[base] = 0
                node_filenames[node_id] = base

    num_communities = len(communities)
    cols = math.ceil(math.sqrt(num_communities)) if num_communities > 0 else 1
    rows = math.ceil(num_communities / cols) if num_communities > 0 else 1

    canvas_nodes: list[dict] = []
    canvas_edges: list[dict] = []

    # Lay out communities in a grid
    gap = 80
    group_x_offsets: list[int] = []
    group_y_offsets: list[int] = []

    # Precompute group sizes so we can calculate offsets
    sorted_cids = sorted(communities.keys())
    group_sizes: dict[int, tuple[int, int]] = {}
    for cid in sorted_cids:
        members = communities[cid]
        n = len(members)
        w = max(600, 220 * math.ceil(math.sqrt(n)) if n > 0 else 600)
        h = max(400, 100 * math.ceil(n / 3) + 120 if n > 0 else 400)
        group_sizes[cid] = (w, h)

    # Compute cumulative row heights and col widths for grid placement
    # Each grid cell uses the max width/height in its col/row
    col_widths: list[int] = []
    row_heights: list[int] = []
    for col_idx in range(cols):
        max_w = 0
        for row_idx in range(rows):
            linear = row_idx * cols + col_idx
            if linear < len(sorted_cids):
                cid = sorted_cids[linear]
                w, _ = group_sizes[cid]
                max_w = max(max_w, w)
        col_widths.append(max_w)

    for row_idx in range(rows):
        max_h = 0
        for col_idx in range(cols):
            linear = row_idx * cols + col_idx
            if linear < len(sorted_cids):
                cid = sorted_cids[linear]
                _, h = group_sizes[cid]
                max_h = max(max_h, h)
        row_heights.append(max_h)

    # Map from cid → (group_x, group_y, group_w, group_h)
    group_layout: dict[int, tuple[int, int, int, int]] = {}
    for idx, cid in enumerate(sorted_cids):
        col_idx = idx % cols
        row_idx = idx // cols
        gx = sum(col_widths[:col_idx]) + col_idx * gap
        gy = sum(row_heights[:row_idx]) + row_idx * gap
        gw, gh = group_sizes[cid]
        group_layout[cid] = (gx, gy, gw, gh)

    # Build set of all node_ids in canvas for edge filtering
    all_canvas_nodes: set[str] = set()
    for members in communities.values():
        all_canvas_nodes.update(members)

    # Generate group and node canvas entries
    for idx, cid in enumerate(sorted_cids):
        members = communities[cid]
        community_name = (
            community_labels.get(cid, f"Community {cid}")
            if community_labels and cid is not None
            else f"Community {cid}"
        )
        gx, gy, gw, gh = group_layout[cid]
        canvas_color = CANVAS_COLORS[idx % len(CANVAS_COLORS)]

        # Group node
        canvas_nodes.append({
            "id": f"g{cid}",
            "type": "group",
            "label": community_name,
            "x": gx,
            "y": gy,
            "width": gw,
            "height": gh,
            "color": canvas_color,
        })

        # Node cards inside the group - rows of 3
        sorted_members = sorted(members, key=lambda n: G.nodes[n].get("label", n))
        for m_idx, node_id in enumerate(sorted_members):
            col = m_idx % 3
            row = m_idx // 3
            nx_x = gx + 20 + col * (180 + 20)
            nx_y = gy + 80 + row * (60 + 20)
            fname = node_filenames.get(node_id, safe_name(G.nodes[node_id].get("label", node_id)))
            canvas_nodes.append({
                "id": f"n_{node_id}",
                "type": "file",
                "file": f"graphify/obsidian/{fname}.md",
                "x": nx_x,
                "y": nx_y,
                "width": 180,
                "height": 60,
            })

    # Generate edges - only between nodes both in canvas, cap at 200 highest-weight
    all_edges_weighted: list[tuple[float, str, str, str]] = []
    for u, v, edata in G.edges(data=True):
        if u in all_canvas_nodes and v in all_canvas_nodes:
            weight = edata.get("weight", 1.0)
            relation = edata.get("relation", "")
            conf = edata.get("confidence", "EXTRACTED")
            label = f"{relation} [{conf}]" if relation else f"[{conf}]"
            all_edges_weighted.append((weight, u, v, label))

    all_edges_weighted.sort(key=lambda x: -x[0])
    for weight, u, v, label in all_edges_weighted[:200]:
        canvas_edges.append({
            "id": f"e_{u}_{v}",
            "fromNode": f"n_{u}",
            "toNode": f"n_{v}",
            "label": label,
        })

    canvas_data = {"nodes": canvas_nodes, "edges": canvas_edges}
    Path(output_path).write_text(json.dumps(canvas_data, indent=2), encoding="utf-8")


def push_to_neo4j(
    G: nx.Graph,
    uri: str,
    user: str,
    password: str,
    communities: dict[int, list[str]] | None = None,
) -> dict[str, int]:
    """Push graph directly to a running Neo4j instance via the Python driver.

    Requires: pip install neo4j

    Uses MERGE so re-running is safe - nodes and edges are upserted, not duplicated.
    Returns a dict with counts of nodes and edges pushed.
    """
    try:
        from neo4j import GraphDatabase
    except ImportError as e:
        raise ImportError(
            "neo4j driver not installed. Run: pip install neo4j"
        ) from e

    node_community = _node_community_map(communities) if communities else {}

    def _safe_rel(relation: str) -> str:
        return re.sub(r"[^A-Z0-9_]", "_", relation.upper().replace(" ", "_").replace("-", "_")) or "RELATED_TO"

    def _safe_label(label: str) -> str:
        """Sanitize a Neo4j node label to prevent Cypher injection."""
        sanitized = re.sub(r"[^A-Za-z0-9_]", "", label)
        return sanitized if sanitized else "Entity"

    driver = GraphDatabase.driver(uri, auth=(user, password))
    nodes_pushed = 0
    edges_pushed = 0

    with driver.session() as session:
        for node_id, data in G.nodes(data=True):
            props = {k: v for k, v in data.items() if isinstance(v, (str, int, float, bool))}
            props["id"] = node_id
            cid = node_community.get(node_id)
            if cid is not None:
                props["community"] = cid
            ftype = _safe_label(data.get("file_type", "Entity").capitalize())
            session.run(
                f"MERGE (n:{ftype} {{id: $id}}) SET n += $props",
                id=node_id,
                props=props,
            )
            nodes_pushed += 1

        for u, v, data in G.edges(data=True):
            rel = _safe_rel(data.get("relation", "RELATED_TO"))
            props = {k: v for k, v in data.items() if isinstance(v, (str, int, float, bool))}
            session.run(
                f"MATCH (a {{id: $src}}), (b {{id: $tgt}}) "
                f"MERGE (a)-[r:{rel}]->(b) SET r += $props",
                src=u,
                tgt=v,
                props=props,
            )
            edges_pushed += 1

    driver.close()
    return {"nodes": nodes_pushed, "edges": edges_pushed}


def to_graphml(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
) -> None:
    """Export graph as GraphML - opens in Gephi, yEd, and any GraphML-compatible tool.

    Community IDs are written as a node attribute so Gephi can colour by community.
    Edge confidence (EXTRACTED/INFERRED/AMBIGUOUS) is preserved as an edge attribute.
    """
    H = G.copy()
    node_community = _node_community_map(communities)
    for node_id in H.nodes():
        H.nodes[node_id]["community"] = node_community.get(node_id, -1)
    nx.write_graphml(H, output_path)


def to_svg(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    figsize: tuple[int, int] = (20, 14),
) -> None:
    """Export graph as an SVG file using matplotlib + spring layout.

    Lightweight and embeddable - works in Obsidian notes, Notion, GitHub READMEs,
    and any markdown renderer. No JavaScript required.

    Node size scales with degree. Community colors match the HTML output.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError as e:
        raise ImportError("matplotlib not installed. Run: pip install matplotlib") from e

    node_community = _node_community_map(communities)

    fig, ax = plt.subplots(figsize=figsize, facecolor="#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    ax.axis("off")

    pos = nx.spring_layout(G, seed=42, k=2.0 / (G.number_of_nodes() ** 0.5 + 1))

    degree = dict(G.degree())
    max_deg = max(degree.values(), default=1) or 1

    node_colors = [COMMUNITY_COLORS[node_community.get(n, 0) % len(COMMUNITY_COLORS)] for n in G.nodes()]
    node_sizes = [300 + 1200 * (degree.get(n, 1) / max_deg) for n in G.nodes()]

    # Draw edges - dashed for non-EXTRACTED
    for u, v, data in G.edges(data=True):
        conf = data.get("confidence", "EXTRACTED")
        style = "solid" if conf == "EXTRACTED" else "dashed"
        alpha = 0.6 if conf == "EXTRACTED" else 0.3
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        ax.plot([x0, x1], [y0, y1], color="#aaaaaa", linewidth=0.8,
                linestyle=style, alpha=alpha, zorder=1)

    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors,
                           node_size=node_sizes, alpha=0.9)
    nx.draw_networkx_labels(G, pos, ax=ax,
                            labels={n: G.nodes[n].get("label", n) for n in G.nodes()},
                            font_size=7, font_color="white")

    # Legend
    if community_labels:
        patches = [
            mpatches.Patch(
                color=COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)],
                label=f"{label} ({len(communities.get(cid, []))})",
            )
            for cid, label in sorted(community_labels.items())
        ]
        ax.legend(handles=patches, loc="upper left", framealpha=0.7,
                  facecolor="#2a2a4e", labelcolor="white", fontsize=8)

    plt.tight_layout()
    plt.savefig(output_path, format="svg", bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
