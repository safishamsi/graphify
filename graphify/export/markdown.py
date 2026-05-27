# write graph to HTML, JSON, SVG, GraphML, Obsidian vault, and Neo4j Cypher
from __future__ import annotations
import hashlib
import html as _html
import json
import math
import os
import re
import shutil
from collections import Counter
from datetime import date
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph
from graphify.security import sanitize_label
from graphify.analyze import _node_community_map
from graphify.build import edge_data


# Artifacts worth preserving across rebuilds (non-regenerable without LLM or curation).
_BACKUP_ARTIFACTS = [
    "graph.json",
    "GRAPH_REPORT.md",
    ".graphify_labels.json",
    ".graphify_analysis.json",
    "manifest.json",
    ".graphify_semantic_marker",
    "cost.json",
]


def backup_if_protected(out_dir: Path) -> "Path | None":
    """Snapshot graph artifacts to a dated subfolder before an overwrite.

    Triggers when graph.json exists AND either:
    - .graphify_semantic_marker is present (graph cost real LLM tokens), or
    - .graphify_labels.json contains at least one non-default community label
      (graph has been curated by a human or skill).

    Returns the backup folder path, or None if no backup was taken.
    Never raises — backup failure prints a warning but never blocks the write.
    Set GRAPHIFY_NO_BACKUP=1 to disable.
    """
    if os.environ.get("GRAPHIFY_NO_BACKUP"):
        return None
    out = Path(out_dir)
    if not (out / "graph.json").exists():
        return None

    is_semantic = (out / ".graphify_semantic_marker").exists()
    is_curated = False
    labels_file = out / ".graphify_labels.json"
    if labels_file.exists():
        try:
            labels = json.loads(labels_file.read_text(encoding="utf-8"))
            is_curated = any(v != f"Community {k}" for k, v in labels.items())
        except Exception:
            pass

    if not is_semantic and not is_curated:
        return None

    reason = "+".join(filter(None, ["semantic" if is_semantic else "", "curated" if is_curated else ""]))
    today = date.today().isoformat()
    backup_dir = out / today
    graph_src = out / "graph.json"

    # Skip re-copying if today's backup already has identical graph.json content.
    # If content differs (graph changed since the last backup today), overwrite
    # the backup in place — one folder per day, always the latest pre-overwrite state.
    if backup_dir.exists() and (backup_dir / "graph.json").exists():
        src_hash = hashlib.sha256(graph_src.read_bytes()).hexdigest()
        bak_hash = hashlib.sha256((backup_dir / "graph.json").read_bytes()).hexdigest()
        if src_hash == bak_hash:
            return backup_dir  # identical content, nothing to do

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for name in _BACKUP_ARTIFACTS:
            src = out / name
            if src.exists():
                try:
                    shutil.copy2(src, backup_dir / name)
                    copied += 1
                except Exception:
                    pass
        if copied:
            print(f"[graphify] backed up {reason} graph ({copied} files) → {backup_dir.name}/")
        return backup_dir
    except Exception as exc:
        import sys
        print(f"[graphify] warning: backup failed ({exc}) — continuing with overwrite", file=sys.stderr)
        return None

def _obsidian_tag(name: str) -> str:
    """Sanitize a community name for use as an Obsidian tag.

    Obsidian tags only allow alphanumerics, hyphens, underscores, and slashes.
    Spaces become underscores; everything else is stripped.
    """
    return re.sub(r"[^a-zA-Z0-9_\-/]", "", name.replace(" ", "_"))


def _strip_diacritics(text: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _yaml_str(s: str) -> str:
    """Escape a value for safe embedding in a YAML double-quoted scalar (F-009).

    See `graphify.ingest._yaml_str` for the full rationale; duplicated here to
    avoid pulling the URL-fetching `ingest` module into export's dependency
    graph. Handles backslash, double-quote, all line breaks (\\n, \\r,
    U+2028, U+2029), tab, NUL, and other C0/DEL control characters that
    would otherwise let a hostile `source_file` / `community` / etc. break
    out of the YAML scalar and inject sibling keys.
    """
    if s is None:
        return ""
    out: list[str] = []
    for ch in str(s):
        cp = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\0":
            out.append("\\0")
        elif cp == 0x2028:
            out.append("\\L")
        elif cp == 0x2029:
            out.append("\\P")
        elif cp < 0x20 or cp == 0x7F:
            out.append(f"\\x{cp:02x}")
        else:
            out.append(ch)
    return "".join(out)


COMMUNITY_COLORS = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
]

MAX_NODES_FOR_VIZ = 5_000


def _viz_node_limit() -> int:
    """Return the effective viz node limit, honoring GRAPHIFY_VIZ_NODE_LIMIT env var.

    Falls back to MAX_NODES_FOR_VIZ when the env var is unset, empty, or non-integer.
    Set to 0 to disable HTML viz unconditionally (useful for CI runners).
    """
    import os
    raw = os.environ.get("GRAPHIFY_VIZ_NODE_LIMIT")
    if raw is None or not raw.strip():
        return MAX_NODES_FOR_VIZ
    try:
        return int(raw)
    except ValueError:
        return MAX_NODES_FOR_VIZ


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
  #legend-controls { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; padding: 4px 0; }
  #legend-controls label { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; color: #aaa; user-select: none; }
  #legend-controls label:hover { color: #e0e0e0; }
  .legend-cb, #select-all-cb { appearance: none; -webkit-appearance: none; width: 14px; height: 14px; border: 1.5px solid #3a3a5e; border-radius: 3px; background: #0f0f1a; cursor: pointer; position: relative; flex-shrink: 0; }
  .legend-cb:checked, #select-all-cb:checked { background: #4E79A7; border-color: #4E79A7; }
  .legend-cb:checked::after, #select-all-cb:checked::after { content: ''; position: absolute; left: 3.5px; top: 1px; width: 4px; height: 7px; border: solid #fff; border-width: 0 2px 2px 0; transform: rotate(45deg); }
  #select-all-cb:indeterminate { background: #4E79A7; border-color: #4E79A7; }
  #select-all-cb:indeterminate::after { content: ''; position: absolute; left: 2px; top: 5px; width: 8px; height: 2px; background: #fff; border: none; transform: none; }
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

const selectAllCb = document.getElementById('select-all-cb');

function updateSelectAllState() {{
  const total = LEGEND.length;
  const hidden = hiddenCommunities.size;
  selectAllCb.checked = hidden === 0;
  selectAllCb.indeterminate = hidden > 0 && hidden < total;
}}

function toggleAllCommunities(hide) {{
  document.querySelectorAll('.legend-item').forEach(item => {{
    hide ? item.classList.add('dimmed') : item.classList.remove('dimmed');
  }});
  document.querySelectorAll('.legend-cb').forEach(cb => {{
    cb.checked = !hide;
  }});
  LEGEND.forEach(c => {{
    if (hide) hiddenCommunities.add(c.cid); else hiddenCommunities.delete(c.cid);
  }});
  const updates = RAW_NODES.map(n => ({{ id: n.id, hidden: hide }}));
  nodesDS.update(updates);
  updateSelectAllState();
}}

const legendEl = document.getElementById('legend');
LEGEND.forEach(c => {{
  const item = document.createElement('div');
  item.className = 'legend-item';
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.className = 'legend-cb';
  cb.checked = true;
  cb.addEventListener('change', (e) => {{
    e.stopPropagation();
    if (cb.checked) {{
      hiddenCommunities.delete(c.cid);
      item.classList.remove('dimmed');
    }} else {{
      hiddenCommunities.add(c.cid);
      item.classList.add('dimmed');
    }}
    const updates = RAW_NODES
      .filter(n => n.community === c.cid)
      .map(n => ({{ id: n.id, hidden: !cb.checked }}));
    nodesDS.update(updates);
    updateSelectAllState();
  }});
  item.innerHTML = `<div class="legend-dot" style="background:${{c.color}}"></div>
    <span class="legend-label">${{c.label}}</span>
    <span class="legend-count">${{c.count}}</span>`;
  item.prepend(cb);
  item.onclick = (e) => {{
    if (e.target === cb) return;
    cb.checked = !cb.checked;
    cb.dispatchEvent(new Event('change'));
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


def _git_head() -> str | None:
    """Return the current git HEAD commit hash, or None if not in a git repo."""
    import subprocess as _sp
    try:
        r = _sp.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def to_json(G: nx.Graph, communities: dict[int, list[str]], output_path: str, *, force: bool = False, built_at_commit: str | None = None) -> bool:
    # Safety check: refuse to silently shrink an existing graph (#479)
    existing_path = Path(output_path)
    if not force and existing_path.exists():
        try:
            from graphify.security import check_graph_file_size_cap
            check_graph_file_size_cap(existing_path)
            existing_data = json.loads(existing_path.read_text(encoding="utf-8"))
            existing_n = len(existing_data.get("nodes", []))
            new_n = G.number_of_nodes()
            if new_n < existing_n:
                import sys as _sys
                print(
                    f"[graphify] WARNING: new graph has {new_n} nodes but existing "
                    f"graph.json has {existing_n}. Refusing to overwrite — you may be "
                    f"missing chunk files from a previous session. "
                    f"Pass force=True to override.",
                    file=_sys.stderr,
                )
                return False
        except Exception:
            pass  # unreadable existing file — proceed with write

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
        # Restore original edge direction. Undirected NetworkX storage may
        # canonicalize endpoint order, flipping `calls` and other directional
        # edges in graph.json. The build path stashes the true endpoints in
        # _src/_tgt for exactly this purpose (#563).
        true_src = link.pop("_src", None)
        true_tgt = link.pop("_tgt", None)
        if true_src is not None and true_tgt is not None:
            link["source"] = true_src
            link["target"] = true_tgt
    data["hyperedges"] = getattr(G, "graph", {}).get("hyperedges", [])
    commit = built_at_commit if built_at_commit is not None else _git_head()
    if commit:
        data["built_at_commit"] = commit
    with open(output_path, "w", encoding="utf-8") as f:  # nosec
        json.dump(data, f, indent=2)
    return True


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
    """Escape a string for safe embedding in a Cypher single-quoted literal.

    Handles all characters that could prematurely terminate the literal or
    inject control sequences:
      - `\\` and `'` (literal terminators)
      - newlines/CRs (would break the per-line statement framing)
      - NUL/control bytes (defensive — Neo4j errors on raw NULs)

    Also strips any leading/trailing whitespace that would let an attacker
    break the `;`-terminated statement boundary used by `cypher-shell`.
    Closing `}` and `)` are NOT special inside a single-quoted Cypher string,
    so escaping the quote and backslash correctly is sufficient (a `}` inside
    a properly-closed `'...'` literal is just a character) — but we previously
    missed `\\n` / `\\r` which DO let a payload break out of the statement
    line and inject a fresh MATCH/DELETE on the following line. See F-008.
    """
    # First normalise: drop NUL and other C0 control chars except tab.
    s = "".join(ch for ch in s if ch >= " " or ch == "\t")
    return (
        s.replace("\\", "\\\\")
         .replace("'", "\\'")
         .replace("\n", "\\n")
         .replace("\r", "\\r")
    )


# Restrict identifier-position values (labels and relationship types are NOT
# quoted in Cypher and so cannot be safely escaped — they must be allowlisted).
_CYPHER_IDENT_RE = re.compile(r"[^A-Za-z0-9_]")


def _cypher_label(raw: str, fallback: str) -> str:
    """Sanitise a value used in identifier position (node label / rel type).

    Cypher does not provide a way to escape `:Foo` label syntax, so we must
    strip everything except `[A-Za-z0-9_]` and require the result to start
    with a letter; otherwise we fall back to a safe constant.
    """
    cleaned = _CYPHER_IDENT_RE.sub("", raw or "")
    if not cleaned or not cleaned[0].isalpha():
        return fallback
    return cleaned


def to_cypher(G: nx.Graph, output_path: str) -> None:
    lines = ["// Neo4j Cypher import - generated by /graphify", ""]
    for node_id, data in G.nodes(data=True):
        label = _cypher_escape(data.get("label", node_id))
        node_id_esc = _cypher_escape(node_id)
        ftype = _cypher_label(
            (data.get("file_type", "unknown") or "unknown").capitalize(),
            "Entity",
        )
        lines.append(f"MERGE (n:{ftype} {{id: '{node_id_esc}', label: '{label}'}});")
    lines.append("")
    for u, v, data in G.edges(data=True):
        rel = _cypher_label(
            (data.get("relation", "RELATES_TO") or "RELATES_TO").upper(),
            "RELATES_TO",
        )
        conf = _cypher_escape(data.get("confidence", "EXTRACTED"))
        u_esc = _cypher_escape(u)
        v_esc = _cypher_escape(v)
        lines.append(
            f"MATCH (a {{id: '{u_esc}'}}), (b {{id: '{v_esc}'}}) "
            f"MERGE (a)-[:{rel} {{confidence: '{conf}'}}]->(b);"
        )
    with open(output_path, "w", encoding="utf-8") as f:  # nosec
        f.write("\n".join(lines))


def to_html(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    member_counts: dict[int, int] | None = None,
    node_limit: int | None = None,
) -> None:
    """Generate an interactive vis.js HTML visualization of the graph.

    Features: node size by degree, click-to-inspect panel, search box,
    community filter, physics clustering by community, confidence-styled edges.
    Raises ValueError if graph exceeds MAX_NODES_FOR_VIZ.

    If member_counts is provided (aggregated community view), node sizes are
    based on community member counts rather than graph degree.

    If node_limit is set and the graph exceeds it, automatically builds an
    aggregated community-level meta-graph instead of raising ValueError.
    """
    limit = node_limit if node_limit is not None else _viz_node_limit()
    if G.number_of_nodes() > limit:
        if node_limit is not None:
            # Build aggregated community meta-graph
            from collections import Counter as _Counter
            import networkx as _nx
            print(f"Graph has {G.number_of_nodes()} nodes (above {limit} limit). Building aggregated community view...")
            node_to_community = {nid: cid for cid, members in communities.items() for nid in members}
            meta = _nx.Graph()
            for cid, members in communities.items():
                meta.add_node(str(cid), label=(community_labels or {}).get(cid, f"Community {cid}"))
            edge_counts = _Counter()
            for u, v in G.edges():
                cu, cv = node_to_community.get(u), node_to_community.get(v)
                if cu is not None and cv is not None and cu != cv:
                    edge_counts[(min(cu, cv), max(cu, cv))] += 1
            for (cu, cv), w in edge_counts.items():
                meta.add_edge(str(cu), str(cv), weight=w,
                              relation=f"{w} cross-community edges", confidence="AGGREGATED")
            if meta.number_of_nodes() <= 1:
                print("Single community - aggregated view not useful. Skipping graph.html.")
                return
            meta_communities = {cid: [str(cid)] for cid in communities}
            mc = {cid: len(members) for cid, members in communities.items()}
            to_html(meta, meta_communities, output_path,
                    community_labels=community_labels, member_counts=mc)
            print(f"graph.html written (aggregated: {meta.number_of_nodes()} community nodes, {meta.number_of_edges()} cross-community edges)")
            print("Tip: run with --obsidian for full node-level detail.")
            return
        raise ValueError(
            f"Graph has {G.number_of_nodes()} nodes - too large for HTML viz "
            f"(limit: {limit}). Use --no-viz, raise GRAPHIFY_VIZ_NODE_LIMIT, "
            f"or reduce input size."
        )

    node_community = _node_community_map(communities)
    degree = dict(G.degree())
    max_deg = max(degree.values(), default=1) or 1
    max_mc = (max(member_counts.values(), default=1) or 1) if member_counts else 1

    # Build nodes list for vis.js
    vis_nodes = []
    for node_id, data in G.nodes(data=True):
        cid = node_community.get(node_id, 0)
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        label = sanitize_label(data.get("label", node_id))
        deg = degree.get(node_id, 1)
        if member_counts:
            mc = member_counts.get(cid, 1)
            size = 10 + 30 * (mc / max_mc)
            font_size = 12
        else:
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

    # Build edges list. Restore original edge direction from _src/_tgt
    # (stashed by build.py for exactly this reason): undirected NetworkX
    # canonicalizes endpoint order, which would otherwise flip the arrow
    # for `calls` and `rationale_for` in the rendered graph (#563).
    vis_edges = []
    for u, v, data in G.edges(data=True):
        confidence = data.get("confidence", "EXTRACTED")
        relation = data.get("relation", "")
        true_src = data.get("_src", u)
        true_tgt = data.get("_tgt", v)
        vis_edges.append({
            "from": true_src,
            "to": true_tgt,
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
        n = member_counts.get(cid, len(communities.get(cid, []))) if member_counts else len(communities.get(cid, []))
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
<script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"
        integrity="sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1"
        crossorigin="anonymous"></script>
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
    <div id="legend-controls">
      <label><input type="checkbox" id="select-all-cb" checked onchange="toggleAllCommunities(!this.checked)">Select All</label>
    </div>
    <div id="legend"></div>
  </div>
  <div id="stats">{stats}</div>
</div>
{_html_script(nodes_json, edges_json, legend_json)}
{_hyperedge_script(hyperedges_json)}
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")  # nosec


# Keep backward-compatible alias - skill.md calls generate_html
generate_html = to_html


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
        cleaned = re.sub(r"\.(md|mdx|qmd|markdown)$", "", cleaned, flags=re.IGNORECASE)
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
        comm_tag = f"community/{_obsidian_tag(community_name)}"
        node_tags = [ftype_tag, conf_tag, comm_tag]

        lines: list[str] = []

        # YAML frontmatter - readable in Obsidian's properties panel.
        # All scalars pass through _yaml_str so a hostile source_file or
        # community label cannot break out and inject sibling keys (F-009).
        lines += [
            "---",
            f'source_file: "{_yaml_str(data.get("source_file", ""))}"',
            f'type: "{_yaml_str(ftype)}"',
            f'community: "{_yaml_str(community_name)}"',
        ]
        if data.get("source_location"):
            lines.append(f'location: "{_yaml_str(str(data["source_location"]))}"')
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
                edata = edge_data(G, node_id, neighbor)
                neighbor_label = node_filename[neighbor]
                relation = edata.get("relation", "")
                confidence = edata.get("confidence", "EXTRACTED")
                lines.append(f"- [[{neighbor_label}]] - `{relation}` [{confidence}]")
            lines.append("")

        # Inline tags at bottom of note body (for Obsidian tag panel)
        inline_tags = " ".join(f"#{t}" for t in node_tags)
        lines.append(inline_tags)

        fname = node_filename[node_id] + ".md"
        (out / fname).write_text("\n".join(lines), encoding="utf-8")  # nosec

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
        comm_tag_name = _obsidian_tag(community_name)
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
        (out / fname).write_text("\n".join(lines), encoding="utf-8")  # nosec
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
    (obsidian_dir / "graph.json").write_text(json.dumps(graph_config, indent=2), encoding="utf-8")  # nosec

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
        cleaned = re.sub(r"\.(md|mdx|qmd|markdown)$", "", cleaned, flags=re.IGNORECASE)
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
                "file": f"{fname}.md",
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
    Path(output_path).write_text(json.dumps(canvas_data, indent=2), encoding="utf-8")  # nosec


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
