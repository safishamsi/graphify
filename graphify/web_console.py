"""
graphify Web Console - A web interface for graphify knowledge graph tool.
Provides a user-friendly interface to scan projects, view graphs, and export reports.
"""
from __future__ import annotations
import asyncio
import json
import os
import shutil
import sys
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from zipfile import ZipFile

import networkx as nx
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from networkx.readwrite import json_graph

# Import existing graphify modules
from graphify.detect import detect, detect_incremental
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json, to_html, to_graphml, to_svg

# Global state for scan tracking
scan_sessions: Dict[str, Dict[str, Any]] = {}
active_scans: Dict[str, threading.Thread] = {}
scan_lock = threading.Lock()


class ScanRequest(BaseModel):
    project_path: str
    mode: str = "standard"  # standard, deep
    directed: bool = False
    no_viz: bool = False
    include_obsidian: bool = False
    include_svg: bool = False
    include_graphml: bool = False


class NodeSearchRequest(BaseModel):
    query: str
    graph_path: Optional[str] = None
    limit: int = 20


class ScanStatus(BaseModel):
    scan_id: str
    status: str  # pending, running, completed, failed, cancelled
    project_path: str
    progress: float
    current_step: str
    steps_completed: int
    total_steps: int
    error_message: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    results: Optional[Dict[str, Any]] = None


# Initialize FastAPI app
app = FastAPI(
    title="graphify Web Console",
    description="Web interface for graphify knowledge graph tool",
    version="0.1.0",
)

# Add CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create static and templates directories if they don't exist
STATIC_DIR = Path(__file__).parent / "web" / "static"
TEMPLATES_DIR = Path(__file__).parent / "web" / "templates"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _get_graph_path(project_path: str) -> Path:
    """Get the path to graph.json for a project."""
    return Path(project_path) / "graphify-out" / "graph.json"


def _get_report_path(project_path: str) -> Path:
    """Get the path to GRAPH_REPORT.md for a project."""
    return Path(project_path) / "graphify-out" / "GRAPH_REPORT.md"


def _get_graph_html_path(project_path: str) -> Path:
    """Get the path to graph.html for a project."""
    return Path(project_path) / "graphify-out" / "graph.html"


def _get_output_dir(project_path: str) -> Path:
    """Get the output directory for a project."""
    return Path(project_path) / "graphify-out"


def _load_graph(graph_path: str) -> nx.Graph:
    """Load a graph from JSON file."""
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


def _communities_from_graph(G: nx.Graph) -> Dict[int, List[str]]:
    """Reconstruct community dict from community property stored on nodes."""
    communities: Dict[int, List[str]] = {}
    for node_id, data in G.nodes(data=True):
        cid = data.get("community")
        if cid is not None:
            communities.setdefault(int(cid), []).append(node_id)
    return communities


def _strip_diacritics(text: str) -> str:
    """Strip diacritics from text for case-insensitive search."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _score_nodes(G: nx.Graph, terms: List[str]) -> List[tuple]:
    """Score nodes based on search terms."""
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
        # Exact match bonus
        if any(t == norm_label or t == norm_label.rstrip("()") for t in norm_terms):
            score += 100.0
        if score > 0:
            scored.append((score, nid))
    return sorted(scored, reverse=True)


# === Scan Worker ===


def run_scan(scan_id: str, request: ScanRequest):
    """Run the full graphify scan pipeline in a background thread."""
    try:
        with scan_lock:
            scan_sessions[scan_id] = {
                "scan_id": scan_id,
                "status": "running",
                "project_path": request.project_path,
                "progress": 0.0,
                "current_step": "Initializing...",
                "steps_completed": 0,
                "total_steps": 8,
                "start_time": datetime.now(),
                "error_message": None,
                "results": None,
            }

        project_path = Path(request.project_path)
        output_dir = project_path / "graphify-out"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Detect files
        _update_scan_status(scan_id, 1, 8, "Detecting files...")
        detection_result = detect(project_path)

        # Save detection result
        (output_dir / ".graphify_detect.json").write_text(
            json.dumps(detection_result, indent=2), encoding="utf-8"
        )

        # Check if we have files to process
        if detection_result.get("total_files", 0) == 0:
            raise ValueError(f"No supported files found in {project_path}")

        # Step 2: Extract code (AST)
        _update_scan_status(scan_id, 2, 8, "Extracting code structure (AST)...")
        
        # Import extract module
        from graphify.extract import collect_files, extract
        
        code_files = []
        for f in detection_result.get("files", {}).get("code", []):
            if Path(f).is_dir():
                code_files.extend(collect_files(Path(f)))
            else:
                code_files.append(Path(f))
        
        ast_result = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
        if code_files:
            try:
                ast_result = extract(code_files, cache_root=Path("."))
            except Exception as e:
                print(f"Warning: AST extraction failed: {e}")
        
        # Save AST result
        (output_dir / ".graphify_ast.json").write_text(
            json.dumps(ast_result, indent=2), encoding="utf-8"
        )

        # Step 3: For now, we'll skip semantic extraction since it requires LLM/subagents
        # In a real implementation, this would dispatch to subagents
        _update_scan_status(scan_id, 3, 8, "Preparing extraction results...")
        
        # Create merged extraction (just AST for now)
        merged_extraction = {
            "nodes": ast_result.get("nodes", []),
            "edges": ast_result.get("edges", []),
            "hyperedges": [],
            "input_tokens": ast_result.get("input_tokens", 0),
            "output_tokens": ast_result.get("output_tokens", 0),
        }
        
        # Save merged extraction
        (output_dir / ".graphify_extract.json").write_text(
            json.dumps(merged_extraction, indent=2), encoding="utf-8"
        )

        # Step 4: Build graph
        _update_scan_status(scan_id, 4, 8, "Building knowledge graph...")
        G = build_from_json(merged_extraction, directed=request.directed)

        # Check if graph is empty
        if G.number_of_nodes() == 0:
            raise ValueError(
                "Graph is empty - extraction produced no nodes. "
                "Possible causes: all files were skipped, binary-only corpus, or extraction failed."
            )

        # Step 5: Cluster
        _update_scan_status(scan_id, 5, 8, "Running community detection...")
        communities = cluster(G)
        cohesion = score_all(G, communities)

        # Step 6: Analyze
        _update_scan_status(scan_id, 6, 8, "Analyzing graph...")
        gods = god_nodes(G)
        surprises = surprising_connections(G, communities)
        labels = {cid: f"Community {cid}" for cid in communities}
        questions = suggest_questions(G, communities, labels)

        # Token cost
        token_cost = {
            "input": merged_extraction.get("input_tokens", 0),
            "output": merged_extraction.get("output_tokens", 0),
        }

        # Step 7: Generate report
        _update_scan_status(scan_id, 7, 8, "Generating report...")
        report = generate(
            G,
            communities,
            cohesion,
            labels,
            gods,
            surprises,
            detection_result,
            token_cost,
            str(project_path),
            suggested_questions=questions,
        )
        report_path = output_dir / "GRAPH_REPORT.md"
        report_path.write_text(report, encoding="utf-8")

        # Step 8: Export outputs
        _update_scan_status(scan_id, 8, 8, "Exporting graph outputs...")
        
        # Export JSON
        to_json(G, communities, str(output_dir / "graph.json"))
        
        # Export HTML if not disabled
        if not request.no_viz:
            try:
                to_html(
                    G,
                    communities,
                    str(output_dir / "graph.html"),
                    community_labels=labels,
                )
            except Exception as e:
                print(f"Warning: HTML generation failed: {e}")
        
        # Export optional formats
        if request.include_svg:
            try:
                to_svg(
                    G,
                    communities,
                    str(output_dir / "graph.svg"),
                    community_labels=labels,
                )
            except Exception as e:
                print(f"Warning: SVG generation failed: {e}")
        
        if request.include_graphml:
            try:
                to_graphml(
                    G,
                    communities,
                    str(output_dir / "graph.graphml"),
                )
            except Exception as e:
                print(f"Warning: GraphML generation failed: {e}")

        # Save analysis data
        analysis = {
            "communities": {str(k): v for k, v in communities.items()},
            "cohesion": {str(k): v for k, v in cohesion.items()},
            "gods": gods,
            "surprises": surprises,
            "questions": questions,
        }
        (output_dir / ".graphify_analysis.json").write_text(
            json.dumps(analysis, indent=2), encoding="utf-8"
        )
        
        # Save labels
        (output_dir / ".graphify_labels.json").write_text(
            json.dumps({str(k): v for k, v in labels.items()}, indent=2),
            encoding="utf-8",
        )

        # Prepare results
        results = {
            "project_path": str(project_path),
            "output_dir": str(output_dir),
            "node_count": G.number_of_nodes(),
            "edge_count": G.number_of_edges(),
            "community_count": len(communities),
            "god_nodes": gods,
            "surprising_connections": surprises,
            "files": {
                "graph_json": str(output_dir / "graph.json"),
                "graph_html": str(output_dir / "graph.html") if not request.no_viz else None,
                "graph_report": str(output_dir / "GRAPH_REPORT.md"),
            },
        }

        # Update final status
        with scan_lock:
            scan_sessions[scan_id].update({
                "status": "completed",
                "progress": 1.0,
                "current_step": "Scan completed successfully!",
                "steps_completed": 8,
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


def _update_scan_status(scan_id: str, step: int, total: int, message: str):
    """Update scan status with progress."""
    with scan_lock:
        if scan_id in scan_sessions:
            scan_sessions[scan_id].update({
                "progress": step / total,
                "current_step": message,
                "steps_completed": step,
                "total_steps": total,
            })


# === API Routes ===

@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serve the main web console page."""
    index_path = TEMPLATES_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    else:
        # Return a simple placeholder if template doesn't exist yet
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
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/projects")
async def list_projects(path: str = Query(".", description="Base path to search for projects")):
    """List projects that have graphify outputs."""
    base_path = Path(path).resolve()
    projects = []
    
    if not base_path.exists():
        return {"projects": [], "error": f"Path not found: {base_path}"}
    
    # Look for graphify-out directories
    for item in base_path.iterdir():
        if item.is_dir():
            graphify_out = item / "graphify-out"
            if graphify_out.exists():
                # Check for key output files
                has_graph_json = (graphify_out / "graph.json").exists()
                has_graph_html = (graphify_out / "graph.html").exists()
                has_report = (graphify_out / "GRAPH_REPORT.md").exists()
                
                # Get modification time
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
async def start_scan(request: ScanRequest, background_tasks: BackgroundTasks):
    """Start a new scan session."""
    project_path = Path(request.project_path).resolve()
    
    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Project path not found: {project_path}")
    
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {project_path}")
    
    scan_id = str(uuid.uuid4())[:8]
    
    # Start scan in background thread
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
    """Get the status of a scan session."""
    with scan_lock:
        if scan_id not in scan_sessions:
            raise HTTPException(status_code=404, detail=f"Scan not found: {scan_id}")
        return scan_sessions[scan_id]


@app.get("/api/scan/{scan_id}/cancel")
async def cancel_scan(scan_id: str):
    """Cancel a running scan."""
    with scan_lock:
        if scan_id not in scan_sessions:
            raise HTTPException(status_code=404, detail=f"Scan not found: {scan_id}")
        
        if scan_sessions[scan_id]["status"] != "running":
            return {"message": f"Scan is not running: {scan_sessions[scan_id]['status']}"}
        
        # Mark as cancelled
        scan_sessions[scan_id]["status"] = "cancelled"
        scan_sessions[scan_id]["error_message"] = "Scan cancelled by user"
        
        return {"message": "Scan cancelled successfully"}


@app.get("/api/graph/exists")
async def check_graph_exists(project_path: str = Query(..., description="Project path")):
    """Check if a graph exists for a project."""
    graph_path = _get_graph_path(project_path)
    return {"exists": graph_path.exists()}


@app.get("/api/graph/stats")
async def get_graph_stats(project_path: str = Query(..., description="Project path")):
    """Get statistics about a graph."""
    graph_path = _get_graph_path(project_path)
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_path}")
    
    G = _load_graph(str(graph_path))
    communities = _communities_from_graph(G)
    
    # Calculate confidence breakdown
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
    """Get nodes from a graph with pagination."""
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
    """Search for nodes in a graph."""
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
    """Get detailed information about a specific node."""
    graph_path = _get_graph_path(project_path)
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_path}")
    
    G = _load_graph(str(graph_path))
    
    if node_id not in G.nodes():
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
    
    data = G.nodes[node_id]
    
    # Get neighbors
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
    """Get all communities in the graph."""
    graph_path = _get_graph_path(project_path)
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_path}")
    
    G = _load_graph(str(graph_path))
    communities = _communities_from_graph(G)
    
    # Try to load community labels
    labels_path = Path(project_path) / "graphify-out" / ".graphify_labels.json"
    labels = {}
    if labels_path.exists():
        try:
            labels = json.loads(labels_path.read_text(encoding="utf-8"))
            labels = {int(k): v for k, v in labels.items()}
        except:
            pass
    
    result = []
    for cid, members in sorted(communities.items(), key=lambda x: -len(x[1])):
        # Get top nodes by degree
        member_degrees = [(n, G.degree(n)) for n in members]
        member_degrees.sort(key=lambda x: -x[1])
        
        result.append({
            "community_id": cid,
            "label": labels.get(cid, f"Community {cid}"),
            "member_count": len(members),
            "top_nodes": [
                {
                    "id": n,
                    "label": G.nodes[n].get("label", n),
                    "degree": deg,
                }
                for n, deg in member_degrees[:10]
            ],
        })
    
    return {"communities": result}


@app.get("/api/graph/god-nodes")
async def get_god_nodes(
    project_path: str = Query(..., description="Project path"),
    top_n: int = Query(10, ge=1, le=50, description="Number of top god nodes"),
):
    """Get the most connected nodes (god nodes) in the graph."""
    graph_path = _get_graph_path(project_path)
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_path}")
    
    G = _load_graph(str(graph_path))
    
    from graphify.analyze import god_nodes as _god_nodes
    gods = _god_nodes(G, top_n=top_n)
    
    return {"god_nodes": gods}


@app.get("/api/graph/surprising-connections")
async def get_surprising_connections(
    project_path: str = Query(..., description="Project path"),
    limit: int = Query(10, ge=1, le=50, description="Maximum connections to return"),
):
    """Get surprising connections in the graph."""
    graph_path = _get_graph_path(project_path)
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_path}")
    
    G = _load_graph(str(graph_path))
    communities = _communities_from_graph(G)
    
    from graphify.analyze import surprising_connections as _surprising_connections
    surprises = _surprising_connections(G, communities)
    
    return {"surprising_connections": surprises[:limit]}


@app.get("/api/report")
async def get_report(
    project_path: str = Query(..., description="Project path"),
    format: str = Query("text", description="Output format: text or json"),
):
    """Get the GRAPH_REPORT.md content."""
    report_path = _get_report_path(project_path)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {report_path}")
    
    content = report_path.read_text(encoding="utf-8")
    
    if format == "json":
        # Parse sections from markdown
        sections = []
        current_section = {"title": "Overview", "content": ""}
        
        for line in content.split("\n"):
            if line.startswith("# "):
                if current_section["content"]:
                    sections.append(current_section)
                current_section = {
                    "title": line[2:].strip(),
                    "content": "",
                }
            elif current_section:
                current_section["content"] += line + "\n"
        
        if current_section["content"]:
            sections.append(current_section)
        
        return {"sections": sections, "raw": content}
    
    return {"content": content}


@app.get("/api/export/graph")
async def export_graph_json(
    project_path: str = Query(..., description="Project path"),
):
    """Export graph.json file for download."""
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
    """Export GRAPH_REPORT.md file for download."""
    report_path = _get_report_path(project_path)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {report_path}")
    
    return FileResponse(
        path=str(report_path),
        media_type="text/markdown",
        filename="GRAPH_REPORT.md",
    )


@app.get("/api/export/html")
async def export_graph_html(
    project_path: str = Query(..., description="Project path"),
):
    """Export graph.html file for download or viewing."""
    html_path = _get_graph_html_path(project_path)
    if not html_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph HTML not found: {html_path}")
    
    return FileResponse(
        path=str(html_path),
        media_type="text/html",
        filename="graph.html",
    )


@app.get("/api/export/all")
async def export_all(
    project_path: str = Query(..., description="Project path"),
):
    """Export all graphify outputs as a ZIP file."""
    output_dir = _get_output_dir(project_path)
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail=f"Output directory not found: {output_dir}")
    
    # Create a temporary ZIP file
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_path = Path(tmp.name)
    
    try:
        with ZipFile(zip_path, "w") as zipf:
            # Add key output files
            key_files = [
                "graph.json",
                "graph.html",
                "GRAPH_REPORT.md",
            ]
            
            for filename in key_files:
                file_path = output_dir / filename
                if file_path.exists():
                    zipf.write(file_path, arcname=filename)
            
            # Add optional files if they exist
            optional_files = [
                "graph.svg",
                "graph.graphml",
                "cypher.txt",
            ]
            
            for filename in optional_files:
                file_path = output_dir / filename
                if file_path.exists():
                    zipf.write(file_path, arcname=filename)
        
        return FileResponse(
            path=str(zip_path),
            media_type="application/zip",
            filename=f"graphify-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip",
        )
    except Exception as e:
        if zip_path.exists():
            zip_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to create ZIP: {e}")


@app.get("/api/view/graph")
async def view_graph(
    project_path: str = Query(..., description="Project path"),
):
    """View the interactive graph HTML in the browser."""
    html_path = _get_graph_html_path(project_path)
    if not html_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph HTML not found: {html_path}")
    
    # Read and return the HTML content
    content = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=content)


# === CLI Entry Point ===

def run_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
):
    """Run the FastAPI server."""
    import uvicorn
    
    print(f"Starting graphify Web Console on http://{host}:{port}")
    print(f"API Documentation: http://{host}:{port}/docs")
    print(f"OpenAPI Schema: http://{host}:{port}/openapi.json")
    print()
    print("Press Ctrl+C to stop the server.")
    
    uvicorn.run(
        "graphify.web_console:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="graphify Web Console")
    parser.add_argument("--host", default="127.0.0.1", help="Host address")
    parser.add_argument("--port", type=int, default=8000, help="Port number")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (development)")
    
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, reload=args.reload)
