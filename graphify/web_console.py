"""
graphify Web Console - A web interface for graphify knowledge graph tool.
Provides a user-friendly interface to scan projects, view graphs, and export reports.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from zipfile import ZipFile

import networkx as nx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from networkx.readwrite import json_graph

from graphify.analyze import god_nodes, surprising_connections
from graphify.pipeline import (
    CancelHandler,
    GraphifyPipeline,
    ScanConfig,
    ScanProgress,
    ScanResult,
)


scan_sessions: Dict[str, Dict[str, Any]] = {}
scan_cancel_handlers: Dict[str, CancelHandler] = {}
active_scans: Dict[str, threading.Thread] = {}
scan_lock = threading.Lock()


class ScanRequest(BaseModel):
    project_path: str
    directed: bool = False
    no_viz: bool = False
    include_obsidian: bool = False
    obsidian_dir: Optional[str] = None
    include_svg: bool = False
    include_graphml: bool = False


class NodeSearchRequest(BaseModel):
    query: str
    graph_path: Optional[str] = None
    limit: int = 20


class ScanStatus(BaseModel):
    scan_id: str
    status: str
    project_path: str
    progress: float
    current_step: str
    steps_completed: int
    total_steps: int
    error_message: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    results: Optional[Dict[str, Any]] = None


app = FastAPI(
    title="graphify Web Console",
    description="Web interface for graphify knowledge graph tool",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "web" / "static"
TEMPLATES_DIR = Path(__file__).parent / "web" / "templates"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _get_graph_path(project_path: str) -> Path:
    return Path(project_path) / "graphify-out" / "graph.json"


def _get_report_path(project_path: str) -> Path:
    return Path(project_path) / "graphify-out" / "GRAPH_REPORT.md"


def _get_graph_html_path(project_path: str) -> Path:
    return Path(project_path) / "graphify-out" / "graph.html"


def _get_output_dir(project_path: str) -> Path:
    return Path(project_path) / "graphify-out"


def _load_graph(graph_path: str) -> nx.Graph:
    try:
        resolved = Path(graph_path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Graph file not found: {resolved}")
        data = json.loads(resolved.read_text(encoding="utf-8"))
        try:
            return json_graph.node_link_graph(data, edges="links")
        except TypeError:
            return json_graph.node_link_graph(data)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"graph.json is corrupted ({exc}). Re-run scan to rebuild.",
        )


def _communities_from_graph(G: nx.Graph) -> Dict[int, Any]:
    communities: Dict[int, Any] = {}
    for node_id, data in G.nodes(data=True):
        cid = data.get("community")
        if cid is not None:
            communities.setdefault(int(cid), []).append(node_id)
    return communities


def _strip_diacritics(text: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _score_nodes(G: nx.Graph, terms: list[str]) -> list[tuple]:
    scored = []
    norm_terms = [_strip_diacritics(t).lower() for t in terms]
    for nid, data in G.nodes(data=True):
        norm_label = data.get("norm_label") or _strip_diacritics(
            data.get("label") or ""
        ).lower()
        source = (data.get("source_file") or "").lower()
        score = sum(1 for t in norm_terms if t in norm_label) + sum(
            0.5 for t in norm_terms if t in source
        )
        if any(t == norm_label or t == norm_label.rstrip("()") for t in norm_terms):
            score += 100.0
        if score > 0:
            scored.append((score, nid))
    return sorted(scored, reverse=True)


def _detect_backend() -> Optional[str]:
    if os.environ.get("MOONSHOT_API_KEY"):
        return "kimi"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    return None


def _create_progress_callback(scan_id: str):
    def callback(progress: ScanProgress):
        with scan_lock:
            if scan_id in scan_sessions:
                scan_sessions[scan_id].update({
                    "progress": progress.step / progress.total_steps,
                    "current_step": progress.message,
                    "steps_completed": progress.step,
                    "total_steps": progress.total_steps,
                })
    return callback


def run_scan(scan_id: str, request: ScanRequest):
    try:
        cancel_handler = CancelHandler()
        
        with scan_lock:
            scan_sessions[scan_id] = {
                "scan_id": scan_id,
                "status": "running",
                "project_path": request.project_path,
                "progress": 0.0,
                "current_step": "Initializing...",
                "steps_completed": 0,
                "total_steps": GraphifyPipeline.TOTAL_STEPS,
                "start_time": datetime.now(),
                "error_message": None,
                "results": None,
            }
            scan_cancel_handlers[scan_id] = cancel_handler

        config = ScanConfig(
            project_path=request.project_path,
            directed=request.directed,
            no_viz=request.no_viz,
            include_obsidian=request.include_obsidian,
            obsidian_dir=request.obsidian_dir,
            include_svg=request.include_svg,
            include_graphml=request.include_graphml,
        )
        
        pipeline = GraphifyPipeline(
            config=config,
            progress_callback=_create_progress_callback(scan_id),
            cancel_handler=cancel_handler,
        )
        
        result = pipeline.run()
        
        if result.cancelled:
            with scan_lock:
                scan_sessions[scan_id].update({
                    "status": "cancelled",
                    "error_message": "Scan cancelled by user",
                    "end_time": datetime.now(),
                })
            return
        
        if not result.success:
            with scan_lock:
                scan_sessions[scan_id].update({
                    "status": "failed",
                    "error_message": result.error_message or "Scan failed",
                    "end_time": datetime.now(),
                })
            return
        
        results = {
            "project_path": str(request.project_path),
            "output_dir": str(result.output_dir) if result.output_dir else None,
            "node_count": result.nodes,
            "edge_count": result.edges,
            "community_count": result.communities,
            "semantic_backend": _detect_backend(),
            "files": {
                "graph_json": str(result.graph_path) if result.graph_path else None,
                "graph_html": str(result.html_path) if result.html_path else None,
                "graph_report": str(result.report_path) if result.report_path else None,
                "obsidian_dir": str(result.obsidian_dir) if result.obsidian_dir else None,
                "svg_path": str(result.svg_path) if result.svg_path else None,
                "graphml_path": str(result.graphml_path) if result.graphml_path else None,
            },
        }
        
        if result.graph_path and result.graph_path.exists():
            try:
                G = _load_graph(str(result.graph_path))
                communities = _communities_from_graph(G)
                gods = god_nodes(G)
                surprises = surprising_connections(G, communities)
                results["god_nodes"] = gods
                results["surprising_connections"] = surprises
            except Exception:
                pass
        
        with scan_lock:
            scan_sessions[scan_id].update({
                "status": "completed",
                "progress": 1.0,
                "current_step": "Scan completed successfully!",
                "steps_completed": GraphifyPipeline.TOTAL_STEPS,
                "end_time": datetime.now(),
                "results": results,
            })

    except Exception as e:
        with scan_lock:
            scan_sessions[scan_id].update({
                "status": "failed",
                "error_message": str(e),
                "end_time": datetime.now(),
            })
        import traceback
        traceback.print_exc()
    finally:
        with scan_lock:
            if scan_id in active_scans:
                del active_scans[scan_id]
            if scan_id in scan_cancel_handlers:
                del scan_cancel_handlers[scan_id]


@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = TEMPLATES_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    else:
        return HTMLResponse(content="""
        <html>
        <head>
            <title>graphify Web Console</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #0f0f1a; color: #e0e0e0; }
                h1 { color: #4E79A7; }
                .container { max-width: 1200px; margin: 0 auto; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>graphify Web Console</h1>
                <p>Web interface is starting. Please visit <a href="/docs">API Documentation</a> for available endpoints.</p>
            </div>
        </body>
        </html>
        """)


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/backend/status")
async def get_backend_status():
    backend = _detect_backend()
    return {
        "backend_available": backend is not None,
        "backend": backend,
        "message": (
            f"Semantic extraction enabled using {backend}" 
            if backend 
            else "No LLM API key set. Set MOONSHOT_API_KEY or ANTHROPIC_API_KEY for semantic extraction."
        )
    }


@app.get("/api/projects")
async def list_projects(path: str = Query(".", description="Base path to search for projects")):
    base_path = Path(path).resolve()
    projects = []
    
    if not base_path.exists():
        return {"projects": [], "error": f"Path not found: {base_path}"}
    
    for item in base_path.iterdir():
        if item.is_dir():
            graphify_out = item / "graphify-out"
            if graphify_out.exists():
                has_graph_json = (graphify_out / "graph.json").exists()
                has_graph_html = (graphify_out / "graph.html").exists()
                has_report = (graphify_out / "GRAPH_REPORT.md").exists()
                
                try:
                    mtime = datetime.fromtimestamp(graphify_out.stat().st_mtime)
                except:
                    mtime = None
                
                projects.append({
                    "name": item.name,
                    "path": str(item),
                    "has_graph_json": has_graph_json,
                    "has_graph_html": has_graph_html,
                    "has_report": has_report,
                    "last_modified": mtime.isoformat() if mtime else None,
                })
    
    return {"projects": projects, "base_path": str(base_path)}


@app.post("/api/scan")
async def start_scan(request: ScanRequest):
    project_path = Path(request.project_path).resolve()
    
    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Project path not found: {project_path}")
    
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {project_path}")
    
    scan_id = str(uuid.uuid4())[:8]
    
    scan_thread = threading.Thread(
        target=run_scan,
        args=(scan_id, request),
        daemon=True,
    )
    scan_thread.start()
    
    with scan_lock:
        active_scans[scan_id] = scan_thread
    
    return {
        "scan_id": scan_id,
        "status": "pending",
        "project_path": str(project_path),
        "message": "Scan started successfully",
    }


@app.get("/api/scan/{scan_id}")
async def get_scan_status(scan_id: str):
    with scan_lock:
        if scan_id not in scan_sessions:
            raise HTTPException(status_code=404, detail=f"Scan not found: {scan_id}")
        return scan_sessions[scan_id]


@app.post("/api/scan/{scan_id}/cancel")
async def cancel_scan(scan_id: str):
    with scan_lock:
        if scan_id not in scan_sessions:
            raise HTTPException(status_code=404, detail=f"Scan not found: {scan_id}")
        
        if scan_sessions[scan_id]["status"] != "running":
            return {"message": f"Scan is not running: {scan_sessions[scan_id]['status']}"}
        
        if scan_id in scan_cancel_handlers:
            scan_cancel_handlers[scan_id].cancel()
        
        scan_sessions[scan_id]["status"] = "cancelled"
        scan_sessions[scan_id]["error_message"] = "Scan cancellation requested - stopping at next safe point..."
        
        return {"message": "Scan cancellation requested. The scan will stop at the next safe point."}


@app.get("/api/graph/exists")
async def check_graph_exists(project_path: str = Query(..., description="Project path")):
    graph_path = _get_graph_path(project_path)
    return {"exists": graph_path.exists()}


@app.get("/api/graph/stats")
async def get_graph_stats(project_path: str = Query(..., description="Project path")):
    graph_path = _get_graph_path(project_path)
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_path}")
    
    G = _load_graph(str(graph_path))
    communities = _communities_from_graph(G)
    
    confs = [d.get("confidence", "EXTRACTED") for _, _, d in G.edges(data=True)]
    total = len(confs) or 1
    
    return {
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "community_count": len(communities),
        "confidence_breakdown": {
            "extracted": round(confs.count("EXTRACTED") / total * 100),
            "inferred": round(confs.count("INFERRED") / total * 100),
            "ambiguous": round(confs.count("AMBIGUOUS") / total * 100),
        },
    }


@app.get("/api/graph/nodes")
async def get_nodes(
    project_path: str = Query(..., description="Project path"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum nodes to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    graph_path = _get_graph_path(project_path)
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_path}")
    
    G = _load_graph(str(graph_path))
    
    nodes = []
    for idx, (nid, data) in enumerate(G.nodes(data=True)):
        if idx < offset:
            continue
        if len(nodes) >= limit:
            break
        
        nodes.append({
            "id": nid,
            "label": data.get("label", nid),
            "file_type": data.get("file_type", ""),
            "source_file": data.get("source_file", ""),
            "community": data.get("community"),
            "degree": G.degree(nid),
        })
    
    return {
        "nodes": nodes,
        "total": G.number_of_nodes(),
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/graph/nodes/search")
async def search_nodes(
    query: str = Query(..., description="Search query"),
    project_path: str = Query(..., description="Project path"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
):
    graph_path = _get_graph_path(project_path)
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_path}")
    
    G = _load_graph(str(graph_path))
    
    terms = [t.lower() for t in query.split() if len(t) > 1]
    if not terms:
        return {"nodes": [], "query": query}
    
    scored = _score_nodes(G, terms)
    results = []
    
    for score, nid in scored[:limit]:
        data = G.nodes[nid]
        results.append({
            "id": nid,
            "label": data.get("label", nid),
            "file_type": data.get("file_type", ""),
            "source_file": data.get("source_file", ""),
            "community": data.get("community"),
            "degree": G.degree(nid),
            "score": score,
        })
    
    return {"nodes": results, "query": query, "total": len(scored)}


@app.get("/api/graph/nodes/{node_id}")
async def get_node_details(
    node_id: str,
    project_path: str = Query(..., description="Project path"),
):
    graph_path = _get_graph_path(project_path)
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_path}")
    
    G = _load_graph(str(graph_path))
    
    if node_id not in G.nodes():
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
    
    data = G.nodes[node_id]
    
    neighbors = []
    for neighbor in G.neighbors(node_id):
        edge_data = G.edges[node_id, neighbor]
        neighbors.append({
            "id": neighbor,
            "label": G.nodes[neighbor].get("label", neighbor),
            "relation": edge_data.get("relation", ""),
            "confidence": edge_data.get("confidence", ""),
            "confidence_score": edge_data.get("confidence_score"),
        })
    
    return {
        "id": node_id,
        "label": data.get("label", node_id),
        "file_type": data.get("file_type", ""),
        "source_file": data.get("source_file", ""),
        "source_location": data.get("source_location"),
        "community": data.get("community"),
        "degree": G.degree(node_id),
        "neighbors": neighbors,
        "neighbor_count": len(neighbors),
    }


@app.get("/api/graph/communities")
async def get_communities(
    project_path: str = Query(..., description="Project path"),
):
    graph_path = _get_graph_path(project_path)
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_path}")
    
    G = _load_graph(str(graph_path))
    communities = _communities_from_graph(G)
    
    labels_path = Path(project_path) / "graphify-out" / ".graphify_labels.json"
    labels = {}
    if labels_path.exists():
        try:
            labels = json.loads(labels_path.read_text(encoding="utf-8"))
        except:
            pass
    
    result = []
    for cid, members in communities.items():
        top_nodes = []
        for nid in sorted(members, key=lambda n: G.degree(n), reverse=True)[:5]:
            top_nodes.append({
                "id": nid,
                "label": G.nodes[nid].get("label", nid),
                "degree": G.degree(nid),
            })
        
        label_key = str(cid)
        result.append({
            "community_id": cid,
            "label": labels.get(label_key, f"Community {cid}"),
            "member_count": len(members),
            "top_nodes": top_nodes,
        })
    
    return {"communities": result, "total": len(communities)}


@app.get("/api/graph/god-nodes")
async def get_god_nodes(
    project_path: str = Query(..., description="Project path"),
    limit: int = Query(20, ge=1, le=100),
):
    graph_path = _get_graph_path(project_path)
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_path}")
    
    G = _load_graph(str(graph_path))
    gods = god_nodes(G)
    
    result = []
    for g in gods[:limit]:
        nid = g.get("node_id") or g.get("id")
        if nid and nid in G.nodes():
            data = G.nodes[nid]
            result.append({
                "id": nid,
                "label": data.get("label", nid),
                "degree": G.degree(nid),
                "file_type": data.get("file_type", ""),
                "source_file": data.get("source_file", ""),
            })
    
    return {"god_nodes": result, "total": len(gods)}


@app.get("/api/graph/surprising-connections")
async def get_surprising_connections(
    project_path: str = Query(..., description="Project path"),
    limit: int = Query(20, ge=1, le=100),
):
    graph_path = _get_graph_path(project_path)
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_path}")
    
    G = _load_graph(str(graph_path))
    communities = _communities_from_graph(G)
    surprises = surprising_connections(G, communities)
    
    result = []
    for s in surprises[:limit]:
        result.append({
            "source": s.get("source"),
            "target": s.get("target"),
            "source_files": s.get("source_files", []),
            "relation": s.get("relation"),
            "note": s.get("note"),
        })
    
    return {"surprising_connections": result, "total": len(surprises)}


@app.get("/api/report")
async def get_report(
    project_path: str = Query(..., description="Project path"),
    format: str = Query("text", description="Format: text or html"),
):
    report_path = _get_report_path(project_path)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {report_path}")
    
    content = report_path.read_text(encoding="utf-8")
    
    if format == "html":
        html_content = f"<pre>{content}</pre>"
        return HTMLResponse(content=html_content)
    
    return {"content": content}


@app.get("/api/view/graph")
async def view_graph_html(
    project_path: str = Query(..., description="Project path"),
):
    graph_html_path = _get_graph_html_path(project_path)
    if not graph_html_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph HTML not found: {graph_html_path}")
    
    return FileResponse(
        path=str(graph_html_path),
        media_type="text/html",
    )


@app.get("/api/export/graph")
async def export_graph_json(
    project_path: str = Query(..., description="Project path"),
):
    graph_path = _get_graph_path(project_path)
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_path}")
    
    return FileResponse(
        path=str(graph_path),
        media_type="application/json",
        filename="graph.json",
    )


@app.get("/api/export/report")
async def export_report(
    project_path: str = Query(..., description="Project path"),
):
    report_path = _get_report_path(project_path)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {report_path}")
    
    return FileResponse(
        path=str(report_path),
        media_type="text/markdown",
        filename="GRAPH_REPORT.md",
    )


@app.get("/api/export/html")
async def export_html(
    project_path: str = Query(..., description="Project path"),
):
    graph_html_path = _get_graph_html_path(project_path)
    if not graph_html_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph HTML not found: {graph_html_path}")
    
    return FileResponse(
        path=str(graph_html_path),
        media_type="text/html",
        filename="graph.html",
    )


@app.get("/api/export/all")
async def export_all(
    project_path: str = Query(..., description="Project path"),
):
    output_dir = _get_output_dir(project_path)
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail=f"Output directory not found: {output_dir}")
    
    temp_dir = tempfile.mkdtemp()
    zip_path = Path(temp_dir) / f"graphify_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    
    with ZipFile(zip_path, 'w') as zipf:
        graph_path = output_dir / "graph.json"
        if graph_path.exists():
            zipf.write(graph_path, "graph.json")
        
        report_path = output_dir / "GRAPH_REPORT.md"
        if report_path.exists():
            zipf.write(report_path, "GRAPH_REPORT.md")
        
        html_path = output_dir / "graph.html"
        if html_path.exists():
            zipf.write(html_path, "graph.html")
        
        svg_path = output_dir / "graph.svg"
        if svg_path.exists():
            zipf.write(svg_path, "graph.svg")
        
        graphml_path = output_dir / "graph.graphml"
        if graphml_path.exists():
            zipf.write(graphml_path, "graph.graphml")
    
    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=zip_path.name,
    )
