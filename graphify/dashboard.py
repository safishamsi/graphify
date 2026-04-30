# FastAPI web dashboard for graphify graphs.
# Usage: python -m graphify.dashboard --graph graphify-out/graph.json --port 8000
from __future__ import annotations

import json
import sys
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph


try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    FastAPI = object  # type: ignore[misc, assignment]
    BaseModel = object  # type: ignore[misc, assignment]
    HTTPException = Exception  # type: ignore[misc, assignment]


_GRAPH_PATH: Path | None = None
_G: nx.Graph | None = None
_COMMUNITIES: dict[int, list[str]] = {}
_LABELS: dict[int, str] = {}


def _load_graph(graph_path: str | Path) -> nx.Graph:
    global _G, _COMMUNITIES, _LABELS
    path = Path(graph_path)
    if not path.exists():
        raise FileNotFoundError(f"Graph not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    try:
        G = json_graph.node_link_graph(data, edges="links", multigraph=False)
    except TypeError:
        G = json_graph.node_link_graph(data, multigraph=False)
    _G = G

    # Reconstruct communities from node attributes
    comm_map: dict[int, list[str]] = {}
    for nid, ndata in G.nodes(data=True):
        cid = ndata.get("community")
        if cid is not None:
            comm_map.setdefault(int(cid), []).append(nid)
    _COMMUNITIES = comm_map

    # Auto-label if missing
    from graphify.label import label_communities
    _LABELS = label_communities(G, _COMMUNITIES)
    return G


def create_app(graph_path: str | Path = "graphify-out/graph.json") -> "FastAPI":
    if not HAS_FASTAPI:
        raise ImportError("fastapi not installed. Run: pip install fastapi")

    app = FastAPI(title="graphify dashboard")
    _load_graph(graph_path)

    # Cached embedding index, lazily built on first /api/search hit.
    # Previously each request rebuilt the index from scratch — with
    # sentence-transformers installed, that meant reloading the model
    # on every search, which dominated latency on real graphs.
    embedding_index_holder: dict = {"idx": None}

    def _get_embedding_index():
        if embedding_index_holder["idx"] is None:
            from graphify.embeddings import EmbeddingIndex
            embedding_index_holder["idx"] = EmbeddingIndex().build(_G)
        return embedding_index_holder["idx"]

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _html_page()

    @app.get("/api/graph")
    def api_graph() -> dict:
        if _G is None:
            raise HTTPException(status_code=503, detail="Graph not loaded")
        node_community = {n: cid for cid, nodes in _COMMUNITIES.items() for n in nodes}
        nodes = []
        degree = dict(_G.degree())
        max_deg = max(degree.values(), default=1) or 1
        for nid, data in _G.nodes(data=True):
            cid = node_community.get(nid, 0)
            nodes.append({
                "id": nid,
                "label": data.get("label", nid),
                "community": cid,
                "community_name": _LABELS.get(cid, f"Community {cid}"),
                "file_type": data.get("file_type", ""),
                "source_file": data.get("source_file", ""),
                "degree": degree.get(nid, 0),
                "size": 10 + 30 * (degree.get(nid, 1) / max_deg),
            })
        edges = [
            {"source": u, "target": v, "relation": d.get("relation", ""),
             "confidence": d.get("confidence", "EXTRACTED")}
            for u, v, d in _G.edges(data=True)
        ]
        return {"nodes": nodes, "edges": edges}

    @app.get("/api/search")
    def api_search(q: str = Query(...), top_k: int = 10) -> list[dict]:
        if _G is None:
            raise HTTPException(status_code=503, detail="Graph not loaded")
        idx = _get_embedding_index()
        results = idx.search(q, top_k=top_k)
        return [
            {"id": nid, "score": round(score, 4),
             "label": _G.nodes[nid].get("label", nid),
             **{k: v for k, v in _G.nodes[nid].items() if k != "label"}}
            for nid, score in results
        ]

    @app.get("/api/node/{node_id}")
    def api_node(node_id: str) -> dict:
        if _G is None:
            raise HTTPException(status_code=503, detail="Graph not loaded")
        if node_id not in _G:
            raise HTTPException(status_code=404, detail="Node not found")
        data = dict(_G.nodes[node_id])
        neighbors = [
            {"id": nb, "label": _G.nodes[nb].get("label", nb),
             "relation": _G.edges[node_id, nb].get("relation", "")}
            for nb in _G.neighbors(node_id)
        ]
        return {"id": node_id, **data, "neighbors": neighbors}

    @app.get("/api/communities")
    def api_communities() -> list[dict]:
        if _G is None:
            raise HTTPException(status_code=503, detail="Graph not loaded")
        return [
            {"id": cid, "label": _LABELS.get(cid, f"Community {cid}"),
             "size": len(nodes),
             "members": [{"id": n, "label": _G.nodes[n].get("label", n)} for n in nodes[:50]]}
            for cid, nodes in _COMMUNITIES.items()
        ]

    @app.post("/api/cypher")
    def api_cypher(body: dict) -> dict:
        if _G is None:
            raise HTTPException(status_code=503, detail="Graph not loaded")
        from graphify.cypher import execute_cypher, render_results
        query = body.get("query", "")
        results = execute_cypher(_G, query)
        return {"results": results, "rendered": render_results(results)}

    return app


def _html_page() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>graphify dashboard</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f0f1a; color: #e0e0e0; }
#layout { display: flex; height: 100vh; }
#graph { flex: 1; }
#sidebar { width: 320px; background: #1a1a2e; border-left: 1px solid #2a2a4e; display: flex; flex-direction: column; overflow: hidden; }
#search-wrap { padding: 12px; border-bottom: 1px solid #2a2a4e; }
#search { width: 100%; background: #0f0f1a; border: 1px solid #3a3a5e; color: #e0e0e0; padding: 7px 10px; border-radius: 6px; font-size: 13px; outline: none; }
#cypher-wrap { padding: 8px 12px; border-bottom: 1px solid #2a2a4e; }
#cypher { width: 100%; background: #0f0f1a; border: 1px solid #3a3a5e; color: #e0e0e0; padding: 6px 10px; border-radius: 6px; font-size: 12px; outline: none; }
#info-panel { padding: 14px; border-bottom: 1px solid #2a2a4e; min-height: 140px; overflow-y: auto; }
#info-panel h3 { font-size: 13px; color: #aaa; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }
#info-content { font-size: 13px; color: #ccc; line-height: 1.6; }
#legend-wrap { flex: 1; overflow-y: auto; padding: 12px; }
#legend-wrap h3 { font-size: 13px; color: #aaa; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
.legend-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; cursor: pointer; border-radius: 4px; font-size: 12px; }
.legend-item:hover { background: #2a2a4e; padding-left: 4px; }
.legend-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
.neighbor-link { display: block; padding: 2px 6px; margin: 2px 0; border-radius: 3px; cursor: pointer; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-left: 3px solid #333; }
.neighbor-link:hover { background: #2a2a4e; }
</style>
</head>
<body>
<div id="layout">
<div id="graph"></div>
<div id="sidebar">
  <div id="search-wrap">
    <input id="search" type="text" placeholder="Semantic search..." autocomplete="off">
  </div>
  <div id="cypher-wrap">
    <input id="cypher" type="text" placeholder="Cypher: MATCH (n) RETURN n.label" autocomplete="off">
  </div>
  <div id="info-panel">
    <h3>Node Info</h3>
    <div id="info-content"><i>Click a node to inspect it</i></div>
  </div>
  <div id="legend-wrap">
    <h3>Communities</h3>
    <div id="legend"></div>
  </div>
</div>
</div>
<script>
const COLORS = ["#4E79A7","#F28E2B","#E15759","#76B7B2","#59A14F","#EDC948","#B07AA1","#FF9DA7","#9C755F","#BAB0AC"];

fetch('/api/graph').then(r=>r.json()).then(data=>{
  const nodes = new vis.DataSet(data.nodes.map(n=>({
    id:n.id, label:n.label,
    color:{background:COLORS[n.community%COLORS.length],border:COLORS[n.community%COLORS.length]},
    size:n.size, font:{size:12,color:'#fff'},
    title:`${n.label} (${n.community_name})`,
    ...n
  })));
  const edges = new vis.DataSet(data.edges.map((e,i)=>({
    id:i, from:e.source, to:e.target,
    title:e.relation+' ['+e.confidence+']',
    dashes:e.confidence!=='EXTRACTED',
    width:e.confidence==='EXTRACTED'?2:1,
    color:{opacity:e.confidence==='EXTRACTED'?0.7:0.35}
  })));

  const network = new vis.Network(document.getElementById('graph'), {nodes,edges}, {
    physics:{solver:'forceAtlas2Based',forceAtlas2Based:{gravitationalConstant:-60,centralGravity:0.005,springLength:120,springConstant:0.08,damping:0.4,avoidOverlap:0.8},stabilization:{iterations:200}},
    interaction:{hover:true,tooltipDelay:100,hideEdgesOnDrag:true},
    nodes:{shape:'dot',borderWidth:1.5},
    edges:{smooth:{type:'continuous',roundness:0.2}}
  });

  network.once('stabilizationIterationsDone',()=>network.setOptions({physics:{enabled:false}}));

  network.on('click',params=>{
    if(params.nodes.length) showInfo(params.nodes[0]);
  });

  function showInfo(id){
    fetch('/api/node/'+encodeURIComponent(id)).then(r=>r.json()).then(d=>{
      let html=`<b>${d.label||d.id}</b><br>Type: ${d.file_type||'-'}<br>Community: ${d.community_name||'-'}<br>Degree: ${d.degree||'-'}<br>Source: ${d.source_file||'-'}`;
      if(d.neighbors&&d.neighbors.length){
        html+='<br><br><b>Neighbors</b>';
        d.neighbors.forEach(nb=>{
          html+=`<span class="neighbor-link" onclick="focusNode('${nb.id}')">${nb.label} — ${nb.relation}</span>`;
        });
      }
      document.getElementById('info-content').innerHTML=html;
    });
  }
  window.focusNode=function(id){ network.focus(id,{scale:1.4,animation:true}); network.selectNodes([id]); showInfo(id); };

  document.getElementById('search').addEventListener('keydown',e=>{
    if(e.key==='Enter'){
      fetch('/api/search?q='+encodeURIComponent(e.target.value)).then(r=>r.json()).then(list=>{
        if(list.length) focusNode(list[0].id);
      });
    }
  });

  document.getElementById('cypher').addEventListener('keydown',e=>{
    if(e.key==='Enter'){
      fetch('/api/cypher',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:e.target.value})}).then(r=>r.json()).then(d=>{
        document.getElementById('info-content').innerHTML='<pre style="font-size:11px">'+d.rendered+'</pre>';
      });
    }
  });

  // Legend
  const legend=document.getElementById('legend');
  const comms=[...new Set(data.nodes.map(n=>n.community))].sort((a,b)=>a-b);
  comms.forEach(cid=>{
    const name=data.nodes.find(n=>n.community===cid)?.community_name||('Community '+cid);
    const el=document.createElement('div');
    el.className='legend-item';
    el.innerHTML=`<div class="legend-dot" style="background:${COLORS[cid%COLORS.length]}"></div><span>${name}</span>`;
    legend.appendChild(el);
  });
});
</script>
</body>
</html>"""


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="graphify web dashboard")
    parser.add_argument("--graph", default="graphify-out/graph.json", help="Path to graph.json")
    parser.add_argument("--port", type=int, default=8000, help="Port to serve on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()

    if not HAS_FASTAPI:
        print("error: fastapi not installed. Run: pip install fastapi", file=sys.stderr)
        sys.exit(1)

    import uvicorn
    app = create_app(args.graph)
    print(f"Serving graphify dashboard at http://{args.host}:{args.port}/")
    print(f"Graph: {args.graph}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
