"""
Memory index exporter — optimized for LLM context retention.

Generates three files that allow Claude/LLMs to resume work without re-reading
the entire codebase:
- memory_index.json: Compact graph of key modules and dependencies
- MEMORY_REPORT.md: Markdown summary for quick onboarding
- memory_index.html: Interactive filterable UI
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from graphify.security import sanitize_label


def write_memory_index(
    graph: Optional[Union[str, Path]] = None,
    report: Optional[Union[str, Path]] = None,
    output: Optional[Union[str, Path]] = None,
    *,
    next_steps: Optional[List[str]] = None,
    project_name: Optional[str] = None,
) -> Path:
    """Generate memory-index files optimized for LLM context retention.

    Reads an existing graph.json and generates:
    - memory_index.json: compact index of key modules and critical edges
    - MEMORY_REPORT.md: markdown summary with next steps
    - memory_index.html: interactive filterable table

    Args:
        graph: Path to graph.json (e.g., graphify-out/graph.json)
        report: Path to GRAPH_REPORT.md (optional, for context)
        output: Output HTML file path (directory inferred from extension)
        next_steps: List of next action items to include in report
        project_name: Project name override (defaults to directory name)

    Returns:
        Path to the generated HTML file
    """
    if graph is None:
        raise ValueError("--graph is required for memory-index export")

    graph_path = Path(graph)
    if not graph_path.exists():
        raise FileNotFoundError(f"Graph file not found: {graph_path}")

    output_path = Path(output) if output else graph_path.parent / "memory_index.html"
    output_dir = output_path.parent if output_path.suffix else output_path

    # Load graph data
    graph_data = json.loads(graph_path.read_text())
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("links", [])

    # Infer project name
    if project_name is None:
        project_name = graph_path.parent.parent.name or "Unknown Project"

    # Extract key modules (top ~15% by degree)
    key_modules, key_ids, degrees = _extract_key_modules(nodes, edges)

    # Extract clusters
    clusters = _extract_clusters(nodes, key_modules)

    # Extract critical edges (EXTRACTED confidence only)
    critical_edges = _extract_critical_edges(edges, key_ids)

    # Calculate token estimate (rough: 1 token per 4 characters)
    token_estimate = sum(
        len(sanitize_label(m.get("label", m["id"]))) // 4
        for m in key_modules
    ) + sum(
        len(e.get("relation", "")) // 4
        for e in critical_edges
    )

    # Build memory index dict
    memory_index = {
        "project": project_name,
        "generated_at": datetime.now().isoformat(),
        "key_modules": key_modules,
        "clusters": clusters,
        "critical_edges": critical_edges,
        "next_steps": next_steps or [],
        "token_estimate": token_estimate,
    }

    # Write files
    _write_memory_json(output_dir, memory_index)
    _write_memory_report(output_dir, memory_index, graph_data, clusters, degrees)
    _write_memory_html(output_dir, memory_index, clusters)

    html_path = output_dir / "memory_index.html"
    return html_path


def _extract_key_modules(
    nodes: list[dict], edges: list[dict]
) -> tuple[list[dict], set[str], dict]:
    """Extract top 15% of nodes by degree.

    Returns:
        (key_modules list, key_ids set, degrees dict)
    """
    degrees = Counter()
    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src:
            degrees[src] += 1
        if tgt:
            degrees[tgt] += 1

    if not degrees:
        return [], set(), {}

    # Top 15% by degree
    threshold = sorted(set(degrees.values()), reverse=True)[
        max(0, len(set(degrees.values())) // 7) - 1
    ] if len(set(degrees.values())) > 1 else min(degrees.values())

    key_ids = {node_id for node_id, deg in degrees.items() if deg >= threshold}

    key_modules = []
    for node in nodes:
        node_id = node.get("id")
        if node_id in key_ids:
            label = sanitize_label(node.get("label", node_id))
            source_file = node.get("source_file", "")
            degree = degrees.get(node_id, 0)

            key_modules.append({
                "id": node_id,
                "label": label,
                "file": source_file,
                "degree": degree,
                "community": node.get("community"),
            })

    # Sort by degree descending
    key_modules.sort(key=lambda x: x["degree"], reverse=True)
    return key_modules, key_ids, degrees


def _extract_clusters(
    nodes: list[dict], key_modules: list[dict]
) -> list[dict]:
    """Extract clusters from nodes with community attribute."""
    community_map = {}

    for node in nodes:
        comm_id = node.get("community")
        if comm_id is None:
            continue

        label = sanitize_label(node.get("label", node.get("id", "Unknown")))
        if comm_id not in community_map:
            community_map[comm_id] = {
                "id": comm_id,
                "label": f"Community {comm_id}",
                "members": [],
            }
        community_map[comm_id]["members"].append(label)

    # Sort clusters by size
    clusters = sorted(community_map.values(), key=lambda c: len(c["members"]), reverse=True)
    return clusters


def _extract_critical_edges(edges: list[dict], key_ids: set) -> list[dict]:
    """Extract EXTRACTED-confidence edges between key modules."""
    critical = []

    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        confidence = edge.get("confidence", "EXTRACTED")

        # Only include EXTRACTED edges between key modules
        if confidence == "EXTRACTED" and src in key_ids and tgt in key_ids:
            critical.append({
                "source": src,
                "target": tgt,
                "relation": edge.get("relation", "unknown"),
                "confidence": confidence,
            })

    return critical


def _write_memory_json(output_dir: Path, memory_index: dict) -> None:
    """Write memory_index.json."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "memory_index.json"
    json_path.write_text(json.dumps(memory_index, indent=2))


def _write_memory_report(
    output_dir: Path,
    memory_index: dict,
    graph_data: dict,
    clusters: list[dict],
    degrees: dict,
) -> None:
    """Write MEMORY_REPORT.md."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "MEMORY_REPORT.md"

    project = memory_index["project"]
    generated = memory_index["generated_at"]
    key_modules = memory_index["key_modules"]
    critical_edges = memory_index["critical_edges"]
    next_steps = memory_index["next_steps"]

    lines = [
        f"# Memory Index — {project}",
        f"",
        f"**Generated**: {generated}",
        f"",
        f"## Quick Start",
        f"",
        f"This memory index summarizes the key modules and dependencies of {project}.",
        f"Use it to quickly understand the architecture without reading the full codebase.",
        f"",
        f"**Token estimate**: ~{memory_index['token_estimate']} tokens (vs ~50k for full graph)",
        f"",
    ]

    # Key modules table
    if key_modules:
        lines.extend([
            f"## Key Modules (top by connectivity)",
            f"",
            f"| Module | File | Connections | Community |",
            f"|--------|------|-------------|-----------|",
        ])
        for mod in key_modules[:20]:  # Limit to top 20
            label = mod["label"]
            file_name = Path(mod["file"]).name if mod["file"] else "—"
            degree = mod["degree"]
            comm = mod.get("community", "—")
            lines.append(f"| `{label}` | {file_name} | {degree} | {comm} |")
        lines.append("")

    # Clusters
    if clusters:
        lines.extend([
            f"## Architecture Clusters",
            f"",
        ])
        for cluster in clusters[:5]:  # Top 5 clusters
            cid = cluster["id"]
            members = ", ".join(cluster["members"][:5])
            if len(cluster["members"]) > 5:
                members += f", +{len(cluster['members']) - 5} more"
            lines.append(f"**Community {cid}**: {members}")
        lines.append("")

    # Critical edges
    if critical_edges:
        lines.extend([
            f"## Critical Dependencies",
            f"",
        ])
        seen = set()
        for edge in critical_edges[:10]:  # Top 10 edges
            key = (edge["source"], edge["target"])
            if key not in seen:
                src = edge["source"]
                tgt = edge["target"]
                rel = edge["relation"]
                lines.append(f"- `{src}` **{rel}** `{tgt}`")
                seen.add(key)
        lines.append("")

    # Next steps
    if next_steps:
        lines.extend([
            f"## Next Steps",
            f"",
        ])
        for i, step in enumerate(next_steps, 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    # Footer
    lines.extend([
        f"## Query the Full Graph",
        f"",
        f"For deeper exploration, use:",
        f"```bash",
        f"graphify query --graph graphify-out/graph.json 'Which modules handle facturas?'",
        f"```",
        f"",
    ])

    report_path.write_text("\n".join(lines))


def _write_memory_html(
    output_dir: Path,
    memory_index: dict,
    clusters: list[dict],
) -> None:
    """Write memory_index.html — lightweight interactive table."""
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "memory_index.html"

    key_modules = memory_index["key_modules"]
    project = memory_index["project"]

    # Build module rows
    module_rows = []
    for mod in key_modules:
        row = {
            "id": mod["id"],
            "label": mod["label"],
            "file": mod["file"],
            "degree": mod["degree"],
            "community": mod.get("community", "—"),
        }
        module_rows.append(row)

    # JSON-escape for embedding in HTML
    modules_json = json.dumps(module_rows).replace("</", "<\\/")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Memory Index — {sanitize_label(project)}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            padding: 30px;
        }}
        h1 {{
            color: #1a1a1a;
            margin-bottom: 10px;
            font-size: 28px;
        }}
        .subtitle {{
            color: #666;
            margin-bottom: 20px;
            font-size: 14px;
        }}
        .search-box {{
            margin-bottom: 20px;
        }}
        .search-box input {{
            width: 100%;
            padding: 12px 16px;
            font-size: 14px;
            border: 2px solid #ddd;
            border-radius: 6px;
            transition: border-color 0.2s;
        }}
        .search-box input:focus {{
            outline: none;
            border-color: #0066cc;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: #f0f4f8;
            padding: 12px;
            border-radius: 6px;
            text-align: center;
        }}
        .stat-card .value {{
            font-size: 24px;
            font-weight: bold;
            color: #0066cc;
        }}
        .stat-card .label {{
            font-size: 12px;
            color: #666;
            margin-top: 4px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        thead {{
            background: #f8f9fa;
            border-bottom: 2px solid #ddd;
        }}
        th {{
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #333;
            cursor: pointer;
            user-select: none;
        }}
        th:hover {{
            background: #efefef;
        }}
        td {{
            padding: 12px;
            border-bottom: 1px solid #eee;
        }}
        tr:hover {{
            background: #f9f9f9;
        }}
        .module-name {{
            font-family: "Courier New", monospace;
            color: #0066cc;
            font-weight: 500;
        }}
        .file-name {{
            color: #666;
            font-size: 12px;
        }}
        .degree {{
            background: #e8f4f8;
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: 600;
            color: #0066cc;
        }}
        .hidden {{
            display: none;
        }}
        .info {{
            background: #e8f4f8;
            border-left: 4px solid #0066cc;
            padding: 12px;
            border-radius: 4px;
            margin-bottom: 20px;
            color: #333;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Memory Index</h1>
        <p class="subtitle">{sanitize_label(project)} • {memory_index['generated_at'].split('T')[0]}</p>

        <div class="info">
            Lightweight index of key modules and dependencies. Use to understand architecture
            without reading the full codebase (~{memory_index['token_estimate']} tokens).
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="value">{len(key_modules)}</div>
                <div class="label">Key Modules</div>
            </div>
            <div class="stat-card">
                <div class="value">{len(clusters)}</div>
                <div class="label">Clusters</div>
            </div>
            <div class="stat-card">
                <div class="value">{len(memory_index['critical_edges'])}</div>
                <div class="label">Dependencies</div>
            </div>
            <div class="stat-card">
                <div class="value">{memory_index['token_estimate']}</div>
                <div class="label">Est. Tokens</div>
            </div>
        </div>

        <div class="search-box">
            <input
                type="text"
                id="searchInput"
                placeholder="Search modules (Ctrl+K)..."
                autocomplete="off"
            />
        </div>

        <table id="modulesTable">
            <thead>
                <tr>
                    <th onclick="sortTable(0)">Module</th>
                    <th onclick="sortTable(1)">File</th>
                    <th onclick="sortTable(2)" style="text-align: center;">Connections</th>
                    <th style="text-align: center;">Community</th>
                </tr>
            </thead>
            <tbody id="tableBody">
            </tbody>
        </table>
    </div>

    <script>
        const MODULES = {modules_json};

        function renderTable(modules = MODULES) {{
            const tbody = document.getElementById("tableBody");
            tbody.innerHTML = "";
            modules.forEach(mod => {{
                const row = document.createElement("tr");
                row.innerHTML = `
                    <td><span class="module-name">${{escapeHtml(mod.label)}}</span></td>
                    <td><span class="file-name">${{escapeHtml(mod.file.split('/').pop() || '—')}}</span></td>
                    <td style="text-align: center;"><span class="degree">${{mod.degree}}</span></td>
                    <td style="text-align: center;">${{mod.community}}</td>
                `;
                tbody.appendChild(row);
            }});
        }}

        function escapeHtml(unsafe) {{
            return unsafe
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }}

        function filterModules() {{
            const query = document.getElementById("searchInput").value.toLowerCase();
            const filtered = MODULES.filter(mod =>
                mod.label.toLowerCase().includes(query) ||
                mod.file.toLowerCase().includes(query)
            );
            renderTable(filtered);
        }}

        function sortTable(col) {{
            const key = ["label", "file", "degree", "community"][col];
            MODULES.sort((a, b) => {{
                const aVal = a[key];
                const bVal = b[key];
                if (typeof aVal === "number")
                    return bVal - aVal;  // descending for numbers
                return String(aVal).localeCompare(String(bVal));
            }});
            renderTable();
        }}

        document.getElementById("searchInput").addEventListener("input", filterModules);
        document.addEventListener("keydown", (e) => {{
            if ((e.ctrlKey || e.metaKey) && e.key === "k") {{
                e.preventDefault();
                document.getElementById("searchInput").focus();
            }}
        }});

        renderTable();
    </script>
</body>
</html>
"""

    html_path.write_text(html_content)
