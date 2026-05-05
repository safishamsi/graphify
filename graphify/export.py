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
    return r'''<style>
:root{--bg:#111;--panel:#191a1c;--panel2:#212225;--line:#34363a;--text:#f2f2f2;--muted:#a9adb5;--faint:#747982;--accent:#f4f4f5;--gold:#f4b860;--danger:#ff6b6b;--card:#242529;--input:#121315;--grid:#ffffff1f}
body.light{--bg:#f4efe4;--panel:#fffaf0f2;--panel2:#eee3d1;--line:#d8c9b2;--text:#16181c;--muted:#525866;--faint:#77808c;--accent:#111827;--gold:#a86107;--danger:#b42318;--card:#ffffffd9;--input:#fffdf6;--grid:#1118271f}
*{box-sizing:border-box;margin:0;padding:0}::-webkit-scrollbar{width:0;height:0}*{scrollbar-width:none;-ms-overflow-style:none}
body{height:100vh;overflow:hidden;display:flex;color:var(--text);font-family:"Segoe UI",Aptos,sans-serif;background:var(--bg)}
body:before{content:"";position:fixed;inset:0;pointer-events:none;background-image:radial-gradient(circle,var(--grid) 1px,transparent 1.15px);background-size:10px 10px;opacity:.82}
body:after{content:"";position:fixed;inset:0;pointer-events:none;background:radial-gradient(circle at 25% 12%,#ffffff08,transparent 28%),radial-gradient(circle at 80% 20%,#35d0ba14,transparent 26%),linear-gradient(180deg,transparent,#0000001c)}
#stage{flex:1;position:relative;min-width:0}#graph{position:absolute;inset:0}.topbar{position:absolute;top:18px;left:28px;right:22px;z-index:10;display:flex;justify-content:flex-end;gap:12px;pointer-events:none}.glass{pointer-events:auto;background:#17181bcc;border:1px solid #ffffff1c;border-radius:999px;box-shadow:0 18px 50px #0006;backdrop-filter:blur(16px)}body.light .glass{background:#fffaf0d9;border-color:var(--line)}.controls{display:flex;gap:6px;align-items:center;padding:6px}button{border:0;border-radius:999px;background:transparent;color:var(--muted);cursor:pointer;padding:8px 12px;font:inherit;font-size:12px;font-weight:700}button:hover{background:#ffffff12;color:var(--text)}button.active{background:var(--accent);color:var(--bg);font-weight:900}
#sidebar{position:absolute;left:16px;top:76px;bottom:16px;width:360px;z-index:8;display:flex;flex-direction:column;overflow:hidden;border:1px solid #ffffff1c;border-radius:18px;background:#191a1ce8;box-shadow:0 24px 80px #0009;backdrop-filter:blur(18px)}body.light #sidebar{background:#fffaf0ed;border-color:var(--line);box-shadow:0 24px 80px #7a685030}.head{padding:20px 16px 14px;border-bottom:1px solid var(--line)}.eyebrow{color:#ffffff;font-size:11px;font-weight:900;letter-spacing:.16em;text-transform:uppercase}body.light .eyebrow{color:#111827}.title{margin-top:8px;font-size:24px;line-height:1.05;font-weight:950;letter-spacing:-.05em}.copy{margin-top:8px;color:var(--muted);font-size:12px;line-height:1.48}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:14px}.metric{border:1px solid var(--line);border-radius:15px;background:var(--card);padding:10px 9px}.metric b{display:block;font-size:17px}.metric span{display:block;margin-top:4px;color:var(--faint);font-size:10px;text-transform:uppercase;letter-spacing:.08em}
.searchBox{padding:14px 16px;border-bottom:1px solid var(--line)}#search{width:100%;border:1px solid #ffffff20;border-radius:16px;background:var(--input);color:var(--text);outline:0;padding:12px 13px;font-size:13px}body.light #search{border-color:var(--line)}#search:focus{border-color:var(--accent);box-shadow:0 0 0 3px #ffffff18}#search-results{display:none;max-height:230px;overflow:auto;margin-top:10px;padding-right:3px}.section{padding:14px 16px;border-bottom:1px solid var(--line)}.sideTabs{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:12px 16px;border-bottom:1px solid var(--line)}.tabBtn{border:1px solid var(--line);border-radius:14px;background:var(--card);padding:9px 8px}.tabBtn.active{background:var(--accent);color:var(--bg)}.panelStack{flex:1;min-height:0;overflow:hidden}.panel{display:none;height:100%;overflow:auto;border-bottom:0}.panel.active{display:block}.sectionHead{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.sectionHead h3{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.14em}.note{color:var(--faint);font-size:11px}#info-content{font-size:13px;color:var(--text);line-height:1.5}.empty{color:var(--faint);font-style:italic}.nodeTitle{font-size:17px;font-weight:950;word-break:break-word}.path{margin-top:7px;color:var(--muted);font:11px/1.45 Consolas,monospace;word-break:break-all}.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.chip{border:1px solid var(--line);border-radius:999px;padding:5px 8px;background:var(--card);color:var(--muted);font-size:11px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}.item,.neighbor,.hub{display:block;width:100%;border:1px solid transparent;border-radius:14px;background:var(--card);color:var(--text);text-align:left;padding:9px 10px;cursor:pointer}.item+.item,.neighbor+.neighbor,.hub+.hub{margin-top:7px}.item:hover,.neighbor:hover,.hub:hover{background:#ffffff12;border-color:#ffffff2a}.it{font-size:12px;font-weight:850;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.im{margin-top:4px;color:var(--faint);font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}#neighbors-list{max-height:300px;overflow:auto;margin-top:8px;padding-right:3px}
#legend-wrap{height:100%;min-height:0;overflow:auto;padding:14px 16px}.legendControls{display:flex;justify-content:space-between;gap:8px;margin-bottom:10px}.evidenceControls{border:1px solid var(--line);border-radius:16px;background:var(--card);padding:10px;margin-bottom:12px}.evidenceControls b{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.14em;margin-bottom:8px}.evidenceControls label{display:flex;align-items:center;justify-content:space-between;gap:8px;color:var(--muted);font-size:12px;padding:5px 0;cursor:pointer}.evidenceControls input{appearance:none;width:15px;height:15px;border:1.5px solid #ffffff44;border-radius:5px;background:var(--input);cursor:pointer}.evidenceControls input:checked{background:var(--accent);border-color:var(--accent)}.legendControls label{display:flex;align-items:center;gap:7px;color:var(--muted);font-size:12px;cursor:pointer}#community-search{width:145px;border:1px solid var(--line);border-radius:999px;background:var(--input);color:var(--text);outline:0;padding:7px 10px;font-size:11px}.legend-item{display:flex;align-items:center;gap:8px;padding:7px 4px;border-radius:12px;cursor:pointer;font-size:12px}.legend-item:hover{background:#ffffff0d}.legend-item.dimmed{opacity:.35}.legend-dot{width:11px;height:11px;border-radius:50%;flex:0 0 auto}.legend-label{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.legend-count{color:var(--faint);font-size:11px}.legend-cb,#select-all-cb{appearance:none;width:15px;height:15px;border:1.5px solid #ffffff44;border-radius:5px;background:var(--input);cursor:pointer}.legend-cb:checked,#select-all-cb:checked{background:var(--accent);border-color:var(--accent)}#footer{position:absolute;left:50%;bottom:18px;transform:translateX(-50%);width:min(560px,calc(100vw - 430px));padding:14px 18px;border:1px solid #ffffff1c;border-radius:18px;background:#17181ce8;color:var(--muted);font-size:12px;line-height:1.45;box-shadow:0 24px 80px #0008;backdrop-filter:blur(18px)}body.light #footer{background:#fffaf0e8;border-color:var(--line)}#stats{display:none}.kbd{border:1px solid var(--line);border-radius:6px;padding:1px 6px;background:var(--card);color:var(--muted);font-size:10px}.canvasRail{position:absolute;right:18px;top:50%;transform:translateY(-50%);z-index:9;display:flex;flex-direction:column;gap:8px;padding:8px;border:1px solid #ffffff1c;border-radius:999px;background:#17181ccc;box-shadow:0 20px 60px #0008;backdrop-filter:blur(16px)}.canvasRail button{width:34px;height:34px;padding:0;display:grid;place-items:center;font-size:14px}.canvasRail .sep{height:1px;background:var(--line);margin:3px 4px}
#loader{position:fixed;inset:0;z-index:1000;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:13px;background:#111;color:var(--muted)}.spinner{width:42px;height:42px;border:4px solid #ffffff22;border-top-color:#fff;border-radius:50%;animation:spin .85s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:900px){body{flex-direction:column}#stage{min-height:58vh}#sidebar{position:relative;left:auto;top:auto;bottom:auto;width:100%;height:42vh;border-radius:18px 18px 0 0;border-left:0}.topbar{left:12px;right:12px}.controls{max-width:calc(100vw - 24px);overflow:auto}#footer{display:none}.canvasRail{display:none}}
.canvasRail{display:none!important}
#footer{display:none!important}
#sidebar{display:flex!important;width:310px!important;left:12px!important;top:64px!important;bottom:12px!important;border-radius:14px!important}
.topbar{top:12px!important;left:330px!important;right:12px!important;justify-content:center!important}
#bottomSearch{position:absolute!important;left:calc(330px + (100vw - 330px)/2)!important;right:auto!important;top:auto!important;bottom:14px!important;transform:translateX(-50%)!important;z-index:50!important;width:min(520px,44vw)!important;display:flex!important;align-items:center!important;gap:7px!important;border:1px solid #ffffff22!important;border-radius:15px!important;background:#17181cf0!important;box-shadow:0 18px 60px #0009!important;backdrop-filter:blur(18px)!important;padding:7px 9px!important}
body.light #bottomSearch{background:#fffaf0f0!important;border-color:var(--line)!important}
#bottomSearch .cmdIcon{flex:0 0 auto!important;color:var(--faint)!important;font-size:9px!important;font-weight:900!important;letter-spacing:.12em!important;text-transform:uppercase!important;border:1px solid var(--line)!important;border-radius:999px!important;padding:5px 8px!important;background:var(--card)!important}
#bottomSearch #search{flex:1!important;width:auto!important;min-width:0!important;border:0!important;background:transparent!important;color:var(--text)!important;outline:0!important;padding:6px 2px!important;font-size:12px!important;box-shadow:none!important}
#bottomSearch #search::placeholder{color:var(--faint)!important}
#bottomSearch .cmdAction{flex:0 0 auto!important;border:1px solid var(--line)!important;border-radius:999px!important;background:var(--card)!important;color:var(--muted)!important;padding:5px 8px!important;font-size:10px!important;font-weight:800!important}
#bottomSearch #search-results{position:absolute!important;left:0!important;right:0!important;bottom:calc(100% + 7px)!important;top:auto!important;max-height:260px!important;margin:0!important;padding:6px!important;background:#17181cf2!important;border:1px solid #ffffff1c!important;border-radius:13px!important;box-shadow:0 20px 70px #0009!important;backdrop-filter:blur(16px)!important}
.metrics{display:flex!important;align-items:center!important;gap:0!important;margin-top:9px!important;border:1px solid var(--line)!important;border-radius:12px!important;background:var(--card)!important;overflow:hidden!important}.metric{flex:1!important;min-height:0!important;border:0!important;border-radius:0!important;background:transparent!important;padding:7px 8px!important}.metric+.metric{border-left:1px solid var(--line)!important}.metric b{font-size:14px!important;line-height:1!important;font-weight:950!important}.metric span{font-size:8px!important;margin-top:3px!important;letter-spacing:.14em!important}
@media(max-width:900px){#sidebar{width:100%!important;left:auto!important;top:auto!important;bottom:auto!important}.topbar{left:12px!important;right:12px!important}#bottomSearch{left:50%!important;width:calc(100vw - 20px)!important}.cmdAction{display:none!important}}</style>'''
def _hyperedge_script(hyperedges_json: str) -> str:
    return f"""<script>
// Render hyperedges as shaded regions
const hyperedges = {hyperedges_json};
// afterDrawing passes ctx already transformed to network coordinate space.
// Draw node positions raw - no manual pan/zoom/DPR math needed.
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
    # legend_json is accepted for backward compatibility; this UI derives groups from nodes.
    script = r'''<script>

const RAW_NODES = __NODES__;
const RAW_EDGES = __EDGES__;
let LEGEND=[],TOP_HUBS=[],nodesDS,edgesDS,network,explorationMode=true,labelsVisible=false,communityQuery='',searchTimer=0,lightTheme=false;
const hiddenCommunities=new Set(),hiddenConfidences=new Set(),visibleNodeIds=new Set(),visibleEdgeIds=new Set(),nodeById=new Map(),edgesByNode=new Map(),communitiesById=new Map();
const MAX_SEED_HUBS=38,MAX_SEED_COMMUNITIES=14,MAX_EXPAND_NEIGHBORS=32,MAX_SEARCH_RESULTS=24,MAX_INFO_NEIGHBORS=120;
function esc(s){return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}function fmt(n){return Number(n||0).toLocaleString()}
function init(){try{buildIndexes();renderMetrics();renderLegend();renderHubs();document.querySelector(`[data-panel="infoPanel"]`)?.click();setupNetwork();bindControls();loadSeedGraph();document.getElementById('loader').style.display='none'}catch(e){console.error(e);document.getElementById('loader').innerHTML='<p style="color:var(--danger)">Error rendering graph: '+esc(e.message)+'</p>'}}
function buildIndexes(){nodeById.clear();edgesByNode.clear();communitiesById.clear();RAW_NODES.forEach(n=>{nodeById.set(n.id,n);const cid=n.community??'unknown';const c=communitiesById.get(cid)||{cid,label:n.community_name||('Community '+cid),color:n.color?.background||'#94a3b8',count:0,topNode:null};c.count++;if(!c.topNode||Number(n.degree||0)>Number(c.topNode.degree||0))c.topNode=n;communitiesById.set(cid,c)});RAW_EDGES.forEach((e,i)=>{e.__id=i;if(!edgesByNode.has(e.from))edgesByNode.set(e.from,[]);if(!edgesByNode.has(e.to))edgesByNode.set(e.to,[]);edgesByNode.get(e.from).push(e);edgesByNode.get(e.to).push(e)});LEGEND=[...communitiesById.values()].sort((a,b)=>b.count-a.count||String(a.label).localeCompare(String(b.label)));TOP_HUBS=[...RAW_NODES].sort((a,b)=>Number(b.degree||0)-Number(a.degree||0)).slice(0,10)}
function renderMetrics(){mNodes.textContent=fmt(RAW_NODES.length);mEdges.textContent=fmt(RAW_EDGES.length);cCount.textContent=fmt(LEGEND.length)+' groups';updateVisibleStats()}function updateVisibleStats(){const n=nodesDS?nodesDS.getIds().length:0,e=edgesDS?edgesDS.getIds().length:0;mVisible.textContent=fmt(n);footer.innerHTML=(explorationMode?'Explore':'Full')+': '+fmt(n)+' visible nodes, '+fmt(e)+' visible edges. Shortcuts: <span class="kbd">/</span> search, <span class="kbd">F</span> fit, <span class="kbd">R</span> reset.'}
function graphTheme(){return lightTheme?{nodeFont:"#102033",stroke:"#fffaf0",edge:.56}:{nodeFont:"#dbeafe",stroke:"#08111f",edge:.42}}
function setupNetwork(){nodesDS=new vis.DataSet();edgesDS=new vis.DataSet();network=new vis.Network(graph,{nodes:nodesDS,edges:edgesDS},{layout:{improvedLayout:false},physics:{enabled:true,solver:'forceAtlas2Based',forceAtlas2Based:{gravitationalConstant:-72,centralGravity:.008,springLength:115,springConstant:.055,damping:.46,avoidOverlap:.18},stabilization:{enabled:true,iterations:130,updateInterval:20}},nodes:{shape:'dot',borderWidth:1.5,shadow:{enabled:true,color:'rgba(0,0,0,.3)',size:10,x:0,y:4},font:{size:0,color:graphTheme().nodeFont,face:'Segoe UI',strokeWidth:5,strokeColor:graphTheme().stroke}},edges:{smooth:{type:'dynamic',roundness:.42},color:{inherit:'both',opacity:graphTheme().edge},selectionWidth:1.5,hoverWidth:1.2},interaction:{hover:true,tooltipDelay:180,hideEdgesOnDrag:true,hideEdgesOnZoom:true,multiselect:false}});network.on('click',p=>{if(!p.nodes.length)return;const id=p.nodes[0];showInfo(id);document.querySelector(`[data-panel="infoPanel"]`)?.click();if(explorationMode)expandNode(id)});network.on('stabilizationIterationsDone',()=>{if(!explorationMode)network.setOptions({physics:false})})}
function transformNode(n){const color=n.color||{background:'#94a3b8',border:'#94a3b8'},deg=Number(n.degree||0),size=Math.max(8,Math.min(34,Number(n.size||10)+Math.sqrt(deg)*1.4));return{id:n.id,label:n.label||n.id,title:n.title||n.label||n.id,color,size,font:labelsVisible?{size:deg>=8?13:11,color:graphTheme().nodeFont,face:'Segoe UI',strokeWidth:5,strokeColor:graphTheme().stroke}:{size:0},_community:n.community,_degree:deg}}
function edgeConfidence(e){return String(e.confidence||'EXTRACTED').toUpperCase()}function edgeAllowed(e){return !hiddenConfidences.has(edgeConfidence(e))}function transformEdge(e){const conf=edgeConfidence(e),weak=conf==='AMBIGUOUS',inferred=conf==='INFERRED';return{id:e.__id,from:e.from,to:e.to,label:'',title:(e.title||e.label||'')+' ['+conf+']',dashes:weak?[4,6]:(inferred?[8,5]:!!e.dashes),width:Math.max(1,Math.min(4,Number(e.width||1)))*(weak?.7:1),color:e.color||{opacity:weak?.22:(inferred?.34:.48)},arrows:{to:{enabled:true,scaleFactor:.45}}}}
function loadSeedGraph(){network?.setOptions({physics:{enabled:true}});nodesDS.clear();edgesDS.clear();visibleNodeIds.clear();visibleEdgeIds.clear();const ids=new Set();[...RAW_NODES].filter(n=>Number(n.degree||0)>0&&!hiddenCommunities.has(n.community)).sort((a,b)=>Number(b.degree||0)-Number(a.degree||0)).slice(0,MAX_SEED_HUBS).forEach(n=>ids.add(n.id));LEGEND.filter(c=>c.topNode&&!hiddenCommunities.has(c.cid)).slice(0,MAX_SEED_COMMUNITIES).forEach(c=>ids.add(c.topNode.id));addNodesToView([...ids]);addEdgesToView();setTimeout(fitGraph,150)}
function loadFullGraph(){network?.setOptions({physics:{enabled:true,stabilization:{enabled:true,iterations:90}}});nodesDS.clear();edgesDS.clear();visibleNodeIds.clear();visibleEdgeIds.clear();const ns=RAW_NODES.filter(n=>!hiddenCommunities.has(n.community));nodesDS.add(ns.map(transformNode));ns.forEach(n=>visibleNodeIds.add(n.id));const es=RAW_EDGES.filter(e=>edgeAllowed(e)&&visibleNodeIds.has(e.from)&&visibleNodeIds.has(e.to));edgesDS.add(es.map(transformEdge));es.forEach(e=>visibleEdgeIds.add(e.__id));updateVisibleStats();setTimeout(fitGraph,180)}
function addNodesToView(ids){const add=[];ids.forEach(id=>{if(visibleNodeIds.has(id))return;const n=nodeById.get(id);if(!n||hiddenCommunities.has(n.community))return;add.push(transformNode(n));visibleNodeIds.add(id)});if(add.length)nodesDS.add(add)}function addEdgesToView(){const add=[];RAW_EDGES.forEach(e=>{if(visibleEdgeIds.has(e.__id))return;if(edgeAllowed(e)&&visibleNodeIds.has(e.from)&&visibleNodeIds.has(e.to)){add.push(transformEdge(e));visibleEdgeIds.add(e.__id)}});if(add.length)edgesDS.add(add);updateVisibleStats()}
function expandNode(id){const ns=(edgesByNode.get(id)||[]).map(e=>e.from===id?e.to:e.from).filter(x=>nodeById.has(x)).sort((a,b)=>Number(nodeById.get(b).degree||0)-Number(nodeById.get(a).degree||0)).slice(0,MAX_EXPAND_NEIGHBORS);addNodesToView(ns);addEdgesToView()}
function showInfo(id){const n=nodeById.get(id);if(!n)return;const rel=(edgesByNode.get(id)||[]).map(e=>({edge:e,node:nodeById.get(e.from===id?e.to:e.from),dir:e.from===id?'out':'in'})).filter(x=>x.node).sort((a,b)=>Number(b.node.degree||0)-Number(a.node.degree||0));let html='<div class="nodeTitle">'+esc(n.label||n.id)+'</div><div class="path">'+esc(n.source_file||'No source path')+'</div><div class="chips"><span class="chip"><span class="dot" style="background:'+esc(n.color?.background||'#94a3b8')+'"></span>'+esc(n.community_name||'Unknown community')+'</span><span class="chip">'+esc(n.file_type||'unknown')+'</span><span class="chip">'+fmt(n.degree)+' links</span></div><div class="sectionHead" style="margin-top:14px;margin-bottom:7px"><h3>Neighbors</h3><span class="note">'+fmt(rel.length)+' total</span></div><div id="neighbors-list">';rel.slice(0,MAX_INFO_NEIGHBORS).forEach(x=>{const nb=x.node;html+='<button class="neighbor" data-node="'+esc(nb.id)+'" title="'+esc(nb.source_file||'')+'"><div class="it"><span class="dot" style="background:'+esc(nb.color?.background||'#94a3b8')+'"></span>'+esc(nb.label||nb.id)+'</div><div class="im">'+esc(x.dir)+' / '+esc(x.edge.label||x.edge.title||'related')+' / degree '+fmt(nb.degree)+'</div></button>'});if(rel.length>MAX_INFO_NEIGHBORS)html+='<div class="im" style="padding:8px 2px">'+fmt(rel.length-MAX_INFO_NEIGHBORS)+' more hidden for speed.</div>';infoContent.innerHTML=html+'</div>'}
function focusOnNode(id){const n=nodeById.get(id);if(!n)return;if(hiddenCommunities.has(n.community)){hiddenCommunities.delete(n.community);renderLegend();refreshVisibility(true)}if(explorationMode&&!visibleNodeIds.has(id)){addNodesToView([id]);addEdgesToView()}network.focus(id,{scale:1.25,animation:{duration:420,easingFunction:'easeInOutQuad'}});network.selectNodes([id]);showInfo(id)}
function renderHubs(){hubList.innerHTML='';TOP_HUBS.forEach(n=>{const b=document.createElement('button');b.className='hub';b.dataset.node=n.id;b.innerHTML='<div class="it">'+esc(n.label||n.id)+'</div><div class="im">'+esc(n.source_file||'')+' / degree '+fmt(n.degree)+'</div>';hubList.appendChild(b)})}
function renderEvidence(){document.querySelectorAll('.evidence-cb').forEach(cb=>{cb.checked=!hiddenConfidences.has(cb.dataset.conf)})}
function renderLegend(){legend.innerHTML='';const q=communityQuery.toLowerCase().trim();(q?LEGEND.filter(c=>String(c.label).toLowerCase().includes(q)||String(c.cid).includes(q)):LEGEND).forEach(c=>{const item=document.createElement('div');item.className='legend-item'+(hiddenCommunities.has(c.cid)?' dimmed':'');item.innerHTML='<input type="checkbox" class="legend-cb" data-cid="'+esc(c.cid)+'" '+(!hiddenCommunities.has(c.cid)?'checked':'')+'><span class="legend-dot" style="background:'+esc(c.color)+'"></span><span class="legend-label">'+esc(c.label)+'</span><span class="legend-count">'+fmt(c.count)+'</span>';legend.appendChild(item)});selectAllCb.checked=hiddenCommunities.size===0;selectAllCb.indeterminate=hiddenCommunities.size>0&&hiddenCommunities.size<LEGEND.length}
function refreshVisibility(reseed){if(!explorationMode){loadFullGraph();return}if(reseed){loadSeedGraph();return}const rm=nodesDS.get().filter(n=>hiddenCommunities.has(n._community)).map(n=>n.id);if(rm.length){nodesDS.remove(rm);rm.forEach(id=>visibleNodeIds.delete(id))}const re=edgesDS.get().filter(e=>!visibleNodeIds.has(e.from)||!visibleNodeIds.has(e.to)||!edgeAllowed(RAW_EDGES[e.id])).map(e=>e.id);if(re.length){edgesDS.remove(re);re.forEach(id=>visibleEdgeIds.delete(id))}updateVisibleStats()}
function fitGraph(){network&&network.fit({animation:{duration:420,easingFunction:'easeInOutQuad'}})}function resetExplore(){explorationMode=true;modeExploration.classList.add('active');modeFull.classList.remove('active');loadSeedGraph()}function toggleTheme(){lightTheme=!lightTheme;document.body.classList.toggle("light",lightTheme);themeBtn.textContent=lightTheme?"Dark":"Light";network?.setOptions({nodes:{font:{color:graphTheme().nodeFont,strokeColor:graphTheme().stroke}},edges:{color:{inherit:"both",opacity:graphTheme().edge}}});nodesDS?.update(nodesDS.get().map(n=>transformNode(nodeById.get(n.id))).filter(Boolean))}
function toggleLabels(){labelsVisible=!labelsVisible;labelsBtn.textContent=labelsVisible?'Labels On':'Labels Off';labelsBtn.classList.toggle('active',labelsVisible);nodesDS.update(nodesDS.get().map(n=>transformNode(nodeById.get(n.id))).filter(Boolean))}
function runSearch(){const q=search.value.toLowerCase().trim();searchResults.innerHTML='';if(!q){searchResults.style.display='none';return}const matches=RAW_NODES.map(n=>{const l=String(n.label||'').toLowerCase(),s=String(n.source_file||'').toLowerCase();let score=0;if(l===q)score+=100;if(l.startsWith(q))score+=40;if(l.includes(q))score+=20;if(s.includes(q))score+=12;score+=Math.min(10,Number(n.degree||0)/8);return{n,score}}).filter(x=>x.score>0).sort((a,b)=>b.score-a.score).slice(0,MAX_SEARCH_RESULTS).map(x=>x.n);if(!matches.length){searchResults.style.display='none';return}searchResults.style.display='block';matches.forEach(n=>{const el=document.createElement('button');el.className='item';el.dataset.node=n.id;el.innerHTML='<div class="it">'+esc(n.label||n.id)+'</div><div class="im">'+esc(n.source_file||'')+' / degree '+fmt(n.degree)+'</div>';searchResults.appendChild(el)})}
function bindControls(){modeExploration.onclick=()=>{if(explorationMode)return;explorationMode=true;modeExploration.classList.add('active');modeFull.classList.remove('active');loadSeedGraph()};modeFull.onclick=()=>{if(!explorationMode)return;const n=RAW_NODES.filter(x=>!hiddenCommunities.has(x.community)).length;if(n>=1200&&!confirm('Load '+fmt(n)+' nodes at once? Explore mode is faster.'))return;explorationMode=false;modeFull.classList.add('active');modeExploration.classList.remove('active');loadFullGraph()};fitBtn.onclick=fitGraph;resetBtn.onclick=resetExplore;document.getElementById("cmdFit")?.addEventListener("click",fitGraph);document.getElementById("cmdReset")?.addEventListener("click",resetExplore);labelsBtn.onclick=toggleLabels;themeBtn.onclick=toggleTheme;document.getElementById("rail-fit")?.addEventListener("click",fitGraph);document.getElementById("rail-reset")?.addEventListener("click",resetExplore);document.getElementById("rail-labels")?.addEventListener("click",toggleLabels);document.getElementById("rail-theme")?.addEventListener("click",toggleTheme);document.querySelectorAll(".tabBtn").forEach(b=>b.onclick=()=>{document.querySelectorAll(".tabBtn").forEach(x=>x.classList.remove("active"));document.querySelectorAll(".panel").forEach(x=>x.classList.remove("active"));b.classList.add("active");document.getElementById(b.dataset.panel).classList.add("active")});selectAllCb.onchange=function(){if(this.checked)hiddenCommunities.clear();else LEGEND.forEach(c=>hiddenCommunities.add(c.cid));renderLegend();refreshVisibility(this.checked)};document.querySelectorAll('.evidence-cb').forEach(cb=>cb.onchange=()=>{if(cb.checked)hiddenConfidences.delete(cb.dataset.conf);else hiddenConfidences.add(cb.dataset.conf);renderEvidence();if(explorationMode){visibleEdgeIds.clear();edgesDS.clear();addEdgesToView()}else loadFullGraph()});legend.addEventListener('click',e=>{const item=e.target.closest('.legend-item');if(!item)return;const cb=item.querySelector('.legend-cb');if(e.target!==cb)cb.checked=!cb.checked;const raw=cb.dataset.cid,cid=communitiesById.has(Number(raw))?Number(raw):raw;if(cb.checked)hiddenCommunities.delete(cid);else hiddenCommunities.add(cid);renderLegend();refreshVisibility(false)});communitySearch.oninput=e=>{communityQuery=e.target.value;renderLegend()};search.oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(runSearch,80)};searchResults.addEventListener('click',e=>{const item=e.target.closest('.item');if(!item)return;focusOnNode(item.dataset.node);if(explorationMode)expandNode(item.dataset.node);searchResults.style.display='none';search.value=''});infoContent.addEventListener('click',e=>{const item=e.target.closest('.neighbor');if(!item)return;focusOnNode(item.dataset.node);if(explorationMode)expandNode(item.dataset.node)});hubList.addEventListener('click',e=>{const item=e.target.closest('.hub');if(!item)return;focusOnNode(item.dataset.node);if(explorationMode)expandNode(item.dataset.node)});document.addEventListener('keydown',e=>{const t=document.activeElement&&['INPUT','TEXTAREA'].includes(document.activeElement.tagName);if(e.key==='/'&&!t){e.preventDefault();search.focus()}if(!t&&e.key.toLowerCase()==='f')fitGraph();if(!t&&e.key.toLowerCase()==='r')resetExplore()})}
const statsEl=document.getElementById('stats'),modeExploration=document.getElementById('mode-exploration'),modeFull=document.getElementById('mode-full'),fitBtn=document.getElementById('fit-btn'),resetBtn=document.getElementById('reset-btn'),labelsBtn=document.getElementById('labels-btn'),themeBtn=document.getElementById('theme-btn'),selectAllCb=document.getElementById('select-all-cb'),communitySearch=document.getElementById('community-search'),searchResults=document.getElementById('search-results'),infoContent=document.getElementById('info-content'),hubList=document.getElementById('hub-list');
init();

</script>'''
    return script.replace("__NODES__", nodes_json).replace("__EDGES__", edges_json)

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
            existing_data = json.loads(existing_path.read_text(encoding="utf-8"))
            existing_n = len(existing_data.get("nodes", []))
            new_n = G.number_of_nodes()
            if new_n < existing_n:
                import sys as _sys
                print(
                    f"[graphify] WARNING: new graph has {new_n} nodes but existing "
                    f"graph.json has {existing_n}. Refusing to overwrite - you may be "
                    f"missing chunk files from a previous session. "
                    f"Pass force=True to override.",
                    file=_sys.stderr,
                )
                return False
        except Exception:
            pass  # unreadable existing file - proceed with write

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
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
{_html_styles()}
</head>
<body>
<div id="loader"><div class="spinner"></div><p>Rendering code graph...</p></div>
<main id="stage"><div id="graph"></div><div class="topbar"><div class="controls glass"><button id="mode-exploration" class="active">Explore</button><button id="mode-full">Full Graph</button><button id="fit-btn">Fit</button><button id="reset-btn">Reset</button><button id="labels-btn">Labels Off</button><button id="theme-btn">Light</button></div></div><div class="canvasRail"><button id="rail-fit" title="Fit">Fit</button><button id="rail-labels" title="Labels">T</button><button id="rail-theme" title="Theme">Theme</button><div class="sep"></div><button id="rail-reset" title="Reset">Reset</button></div></main><div id="bottomSearch"><span class="cmdIcon">Search</span><input id="search" placeholder="Search nodes, files, functions..." autocomplete="off"><button class="cmdAction" id="cmdFit" type="button">Fit</button><button class="cmdAction" id="cmdReset" type="button">Reset</button><div id="search-results"></div></div>
<aside id="sidebar"><header class="head"><div class="eyebrow">Code Graph</div><div class="title">Better view, same data.</div><p class="copy">Explore mode keeps it light. Search, inspect hubs, filter communities, then load full graph only when needed.</p><div class="metrics"><div class="metric"><b id="mNodes">-</b><span>Nodes</span></div><div class="metric"><b id="mEdges">-</b><span>Edges</span></div><div class="metric"><b id="mVisible">-</b><span>Visible</span></div></div></header><nav class="sideTabs"><button class="tabBtn active" data-panel="infoPanel">Info</button><button class="tabBtn" data-panel="hubPanel">Hubs</button><button class="tabBtn" data-panel="groupPanel">Groups</button></nav><div class="panelStack"><section id="infoPanel" class="section panel active"><div class="sectionHead"><h3>Node Info</h3><span class="note">click graph</span></div><div id="info-content"><span class="empty">Select a node to inspect source path, community and neighbors.</span></div></section><section id="hubPanel" class="section panel"><div class="sectionHead"><h3>Top Hubs</h3><span class="note">high degree</span></div><div id="hub-list"></div></section><section id="groupPanel" class="panel"><div id="legend-wrap"><div class="sectionHead"><h3>Communities</h3><span class="note" id="cCount">-</span></div><div class="evidenceControls"><b>Evidence</b><label>Extracted <input class="evidence-cb" data-conf="EXTRACTED" type="checkbox" checked></label><label>Inferred <input class="evidence-cb" data-conf="INFERRED" type="checkbox" checked></label><label>Ambiguous <input class="evidence-cb" data-conf="AMBIGUOUS" type="checkbox" checked></label></div><div class="legendControls"><label><input type="checkbox" id="select-all-cb" checked> Select All</label><input id="community-search" placeholder="Filter groups"></div><div id="legend"></div></div></section></div><div id="footer">Shortcuts: <span class="kbd">/</span> search, <span class="kbd">F</span> fit, <span class="kbd">R</span> reset.</div><div id="stats" hidden>{stats}</div></aside>
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

    # Map node_id â†’ safe filename so wikilinks stay consistent.
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

    # Map file_type â†’ graphify tag
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

    # Map from cid â†’ (group_x, group_y, group_w, group_h)
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






