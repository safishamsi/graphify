"""tree_html — emit a D3 v7 collapsible-tree HTML view of a graph.

A self-contained printable / browseable tree-of-modules view
intended to complement the existing force-directed ``graph.html``.
Key visual elements:

  * Expand-all / collapse-all / reset-view buttons.
  * Multi-line label wrapping (``wrapText``) with separately-coloured
    name and descendant-count.
  * Depth-based colour palette (top-level directories get distinct
    accent colours; deeper levels follow a level-specific palette).
  * Click-to-toggle subtree.

Tree-data shape:

    {
      "name": "<root label>",
      "total_count": <int>,
      "children": [ { "name", "total_count", "children": [...] }, ... ]
    }

CLI: ``graphify tree [--graph PATH] [--output HTML] [--root PATH]
[--max-children N] [--label NAME]``.

Implementation notes:
  - ``total_count`` is the descendant leaf count, so collapsed nodes
    can show ``(Total Count: 95)`` without needing the children loaded.
  - ``--max-children`` (default 200) caps how many children render
    under any one node; a synthetic ``(+N more)`` leaf appears when the
    cap fires so very wide directories stay usable.
  - The first-level palette is auto-populated from the live top-level
    directories so each gets a stable accent colour.
"""

from __future__ import annotations

import html as _html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_MAX_CHILDREN = 200


# ── Tree builder (filesystem hierarchy → JSON) ──────────────────


def _common_root(paths: List[str]) -> str:
    if not paths:
        return ""
    parts = [Path(p).parts for p in paths if p]
    if not parts:
        return ""
    common = parts[0]
    for p in parts[1:]:
        i = 0
        while i < len(common) and i < len(p) and common[i] == p[i]:
            i += 1
        common = common[:i]
    return str(Path(*common)) if common else ""


def _make_truncation_leaf(extra: int) -> Dict[str, Any]:
    return {"name": f"(+{extra} more)", "total_count": extra, "children": []}


def build_tree(
    graph: Dict[str, Any],
    *,
    root: Optional[str] = None,
    max_children: int = DEFAULT_MAX_CHILDREN,
    project_label: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a ``{name, total_count, children}`` hierarchy.

    Each leaf is either a code symbol (class / top-level function) or
    a synthetic "(+N more)" placeholder for truncated wide directories.
    Each interior node carries ``total_count = sum of leaf counts``.
    """
    nodes: List[Dict[str, Any]] = list(graph.get("nodes", []))
    file_nodes = [n for n in nodes if n.get("source_file")]
    if not file_nodes:
        return {"name": "(empty graph)", "total_count": 0, "children": []}

    if root is None:
        root = _common_root([n["source_file"] for n in file_nodes])
    root_path = Path(root)

    by_file: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for n in file_nodes:
        by_file[n["source_file"]].append(n)

    # Build dir tree.
    dir_index: Dict[str, Dict[str, Any]] = {}
    label_root = project_label or root_path.name or root or "/"
    root_node: Dict[str, Any] = {
        "name": label_root, "total_count": 0, "children": [],
    }
    dir_index[str(root_path)] = root_node

    def _ensure_dir(abs_path: Path) -> Dict[str, Any]:
        key = str(abs_path)
        if key in dir_index:
            return dir_index[key]
        if abs_path == abs_path.parent:
            return root_node
        parent = (_ensure_dir(abs_path.parent)
                  if abs_path.parent != abs_path else root_node)
        node = {"name": abs_path.name, "total_count": 0, "children": []}
        dir_index[key] = node
        parent["children"].append(node)
        return node

    for src_file, syms in sorted(by_file.items()):
        src_path = Path(src_file)
        try:
            rel = src_path.relative_to(root_path)
            parent_path = (root_path / rel).parent
        except ValueError:
            parent_path = root_path
        parent_dir = _ensure_dir(parent_path)

        # File node — children are the symbols.
        sym_children: List[Dict[str, Any]] = []
        for n in syms:
            label = n.get("label", n.get("id", "?"))
            # Skip the redundant file-name node graphify emits.
            if label == src_path.name and n.get("file_type") == "code":
                continue
            sym_children.append({
                "name": label,
                "total_count": 1,
                "children": [],
            })
        # Sort: code symbols first by name, then anything else.
        sym_children.sort(key=lambda c: (
            c["name"].startswith("_"),
            c["name"].lower(),
        ))
        if len(sym_children) > max_children:
            extra = len(sym_children) - max_children
            sym_children = sym_children[:max_children] + [
                _make_truncation_leaf(extra),
            ]
        file_node = {
            "name": src_path.name,
            "total_count": len(sym_children) or 1,
            "children": sym_children,
        }
        parent_dir["children"].append(file_node)

    # Sort each dir's children + propagate total_count up.
    def _finalise(d: Dict[str, Any]) -> int:
        kids = d.get("children") or []
        kids.sort(key=lambda c: (
            0 if (c.get("children") and len(c["children"]) > 0) else 1,
            c["name"].lower(),
        ))
        if not kids:
            return d.get("total_count") or 1
        n = 0
        for c in kids:
            n += _finalise(c)
        d["total_count"] = n or 1
        return d["total_count"]

    _finalise(root_node)
    return root_node


# ── HTML emitter (single-data-blob substitution) ──────────────────


# We emit a Python f-string with literal CSS/JS braces escaped as {{ }}.
_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <style>
    body {{
      font-family: 'Segoe UI', sans-serif;
      margin: 0;
      padding: 0;
      background: #f9f9f9;
      color: #333;
    }}
    h1 {{
      margin: 20px 0 0 24px;
      font-size: 2.2rem;
      font-weight: bold;
      color: #1e3a56;
    }}
    .controls {{
      margin: 20px 0 15px 24px;
    }}
    button {{
      margin-right: 10px;
      padding: 8px 18px;
      background: #007bff;
      color: #fff;
      border: none;
      border-radius: 5px;
      font-size: 0.95rem;
      cursor: pointer;
      transition: background 0.2s ease-in-out;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }}
    button:hover {{
      background: #0056b3;
    }}
    button:active {{
      background: #004085;
    }}
    #tree-container {{
      width: calc(100vw - 48px); /* Adjust for body margin/padding */
      height: 85vh;
      overflow: auto;
      border-radius: 8px;
      background: #fff;
      margin-left: 24px;
      margin-right: 24px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.08);
      border: 1px solid #ddd;
    }}
    svg {{
      background: #fff;
      border-radius: 8px;
      display: block; /* Important for D3 */
    }}
    .node circle {{
      stroke-width: 2.5px;
    }}
    .node text {{ /* Base style for the <text> container */
      font: 13px 'Segoe UI', sans-serif;
      paint-order: stroke fill; /* Ensures text is readable over lines */
      stroke: #fff; /* White halo */
      stroke-width: 3px; /* Halo thickness */
      stroke-linejoin: round;
      stroke-opacity: 0.85; /* Halo opacity */
    }}
    .link {{
      fill: none;
      stroke-opacity: 0.7;
      stroke-width: 2px;
    }}
  </style>
</head>
<body>
  <h1>{header}</h1>
  <div class="controls">
    <button onclick="expandAll()">Expand All</button>
    <button onclick="collapseAll()">Collapse All</button>
    <button onclick="resetView()">Reset View</button>
  </div>
  <div id="tree-container">
    <svg id="tree-svg" width="{svg_width}" height="{svg_height}"></svg>
  </div>

  <script src="https://d3js.org/d3.v7.min.js"></script>
  <script>
    const initialJsonData = {data_json};

    function transformData(jsonData) {{
        // Helper function to recursively build the children structure
        function processNode(node, parentL1StageName) {{
            let displayName = node.name;
            // Append total_count if it exists and is not already in the name
            if (node.total_count !== undefined) {{
                if (!/\(Total Count: \d+\)$/.test(displayName)) {{
                    displayName += ` (Total Count: ${{node.total_count}})`;
                }}
            }}

            const newNode = {{ name: displayName }};

            if (parentL1StageName === "Root") {{
                 newNode.originalStageName = node.name;
            }} else {{
                newNode.originalStageName = parentL1StageName;
            }}

            if (node.children && node.children.length > 0) {{
                const stageNameToPass = (parentL1StageName === "Root") ? node.name : parentL1StageName;
                newNode.children = node.children.map(child => processNode(child, stageNameToPass));
            }}

            return newNode;
        }}

        let rootDisplayName = jsonData.name;
        if (jsonData.total_count !== undefined && !/\(Total Count: \d+\)$/.test(rootDisplayName)) {{
            rootDisplayName += ` (Total Count: ${{jsonData.total_count}})`;
        }}

        return {{
            name: rootDisplayName,
            originalStageName: "Root",
            children: (jsonData.children || []).map(child => processNode(child, "Root"))
        }};
    }}

    const treeData = transformData(initialJsonData);

    // Auto-populated phaseColors: every depth-1 child of the root gets
    // a stable colour from a bigger palette so all top-level dirs are
    // distinguishable.
    const PALETTE = [
      ["#3498DB","#2980B9","#AED6F1"], ["#2ECC71","#27AE60","#A9DFBF"],
      ["#E74C3C","#C0392B","#F5B7B1"], ["#9B59B6","#8E44AD","#D7BDE2"],
      ["#F39C12","#D68910","#FAD7A0"], ["#1ABC9C","#117864","#A2D9CE"],
      ["#34495E","#1B2631","#ABB2B9"], ["#E67E22","#BA4A00","#F5CBA7"],
      ["#16A085","#0E6655","#A2D9CE"], ["#D35400","#A04000","#EDBB99"],
      ["#7F8C8D","#566573","#D5DBDB"], ["#C0392B","#7B241C","#F5B7B1"],
      ["#2E86C1","#1B4F72","#A9CCE3"], ["#28B463","#196F3D","#A9DFBF"],
      ["#AF7AC5","#6C3483","#D2B4DE"],
    ];
    const phaseColors = {{ "Root": {{ fill: "#4A4A4A", stroke: "#333333", collapsedFill: "#6C757D" }},
                          "Default": {{ fill: "#BDC3C7", stroke: "#95A5A6", collapsedFill: "#ECF0F1" }} }};
    (initialJsonData.children || []).forEach((c, i) => {{
      const pal = PALETTE[i % PALETTE.length];
      phaseColors[c.name] = {{ fill: pal[0], stroke: pal[1], collapsedFill: pal[2] }};
    }});

    const levelSpecificPalettes = {{
      0: {{ fill: "#4A4A4A", stroke: "#333333", collapsedFill: "#6C757D" }},
      2: {{ fill: "#6ab04c", stroke: "#508a38", collapsedFill: "#a3d391" }},
      3: {{ fill: "#f0932b", stroke: "#d0730f", collapsedFill: "#f6c07e" }},
      4: {{ fill: "#be2edd", stroke: "#a01cb3", collapsedFill: "#e08bf2" }},
      5: {{ fill: "#00a8ff", stroke: "#007ac1", collapsedFill: "#74d2ff" }},
      6: {{ fill: "#e55039", stroke: "#c23620", collapsedFill: "#f09a8d" }},
      default: {{ fill: "#747d8c", stroke: "#57606f", collapsedFill: "#a4b0be" }}
    }};

    const svgElement = d3.select("#tree-svg");
    const initialSvgWidth = +svgElement.attr("width");
    const initialSvgHeight = +svgElement.attr("height");
    const margin = {{ top: 40, right: 120, bottom: 80, left: 450 }};
    let width = initialSvgWidth - margin.left - margin.right;
    let height = initialSvgHeight - margin.top - margin.bottom;
    const duration = 500;
    let nodeCounter = 0;
    const g = svgElement.append("g").attr("transform", `translate(${{margin.left}},${{margin.top}})`);
    const treemap = d3.tree().nodeSize([40, 0]);
    let rootNode = d3.hierarchy(treeData, d => d.children);
    rootNode.x0 = 0;
    rootNode.y0 = 0;

    if (rootNode.children) {{
      rootNode.children.forEach(d_child => {{
        if (d_child.children) {{ collapseBranch(d_child); }}
      }});
    }}
    updateTree(rootNode);

    function collapseBranch(d) {{ if (d.children) {{ d._children = d.children; d._children.forEach(collapseBranch); d.children = null; }} }}
    function expandBranch(d) {{ if (d._children) {{ d.children = d._children; d._children = null; }} if (d.children) {{ d.children.forEach(expandBranch); }} }}
    window.expandAll = () => {{ expandBranch(rootNode); updateTree(rootNode); }};
    window.collapseAll = () => {{ if (rootNode.children) {{ rootNode.children.forEach(collapseBranch); }} updateTree(rootNode); }};
    window.resetView = () => {{ if (rootNode.children) {{ rootNode.children.forEach(d_child => {{ if (d_child.children || d_child._children) {{ collapseBranch(d_child); }} }}); }} if (rootNode._children && !rootNode.children) {{ rootNode.children = rootNode._children; rootNode._children = null; }} updateTree(rootNode); }};

    function updateTree(source) {{
      const treeLayoutData = treemap(rootNode);
      let nodes = treeLayoutData.descendants();
      let links = treeLayoutData.descendants().slice(1);

      let minX = 0;
      let maxX = 0;
      if (nodes.length > 0) {{
        minX = d3.min(nodes, d => d.x);
        maxX = d3.max(nodes, d => d.x);
      }}

      let neededHeight = Math.max(initialSvgHeight, maxX - minX + margin.top + margin.bottom + 100);
      svgElement.transition().duration(duration / 2).attr("height", neededHeight);
      g.transition().duration(duration / 2).attr("transform", `translate(${{margin.left}},${{margin.top - minX + 40}})`);

      nodes.forEach(d => {{ d.y = d.depth * 400; }}); // Adjust horizontal separation if needed

      const node = g.selectAll('g.node').data(nodes, d => d.id || (d.id = ++nodeCounter));
      const nodeEnter = node.enter().append('g')
        .attr('class', d => "node" + (d.children || d._children ? " node--internal" : " node--leaf") + (d._children ? " _children" : ""))
        .attr('transform', d => `translate(${{source.y0}},${{source.x0}})`)
        .on('click', (event, d) => {{ if (d.children) {{ d._children = d.children; d.children = null; }} else if (d._children) {{ d.children = d._children; d._children = null; }} updateTree(d); }})
        .style('cursor', d => (d.children || d._children) ? 'pointer' : 'default');

      nodeEnter.append('circle').attr('r', 1e-6);

      nodeEnter.append('text')
        .attr('dy', '.35em')
        .attr('x', d => d.children || d._children ? -14 : 14)
        .attr('text-anchor', d => d.children || d._children ? 'end' : 'start')
        .style("fill-opacity", 1e-6)
        .call(wrapText, 380);

      const nodeUpdate = nodeEnter.merge(node);
      nodeUpdate.transition().duration(duration)
        .attr('transform', d => `translate(${{d.y}},${{d.x}})`)
        .attr('class', d => "node" + (d.children ? " node--internal" : " node--leaf") + (d._children ? " node--internal _children" : ""));

      nodeUpdate.select('circle').attr('r', 8.5)
        .style('fill', d => {{
            let palette;
            if (d.depth === 0) {{
                palette = levelSpecificPalettes[0];
            }} else if (d.depth === 1) {{
                palette = phaseColors[d.data.originalStageName] || phaseColors.Default;
            }} else {{
                palette = levelSpecificPalettes[d.depth] || levelSpecificPalettes.default;
            }}
            if (d._children) return palette.collapsedFill;
            if (d.children) return palette.fill;
            return "#fff";
        }})
        .style('stroke', d => {{
            let palette;
            if (d.depth === 0) {{
                palette = levelSpecificPalettes[0];
            }} else if (d.depth === 1) {{
                palette = phaseColors[d.data.originalStageName] || phaseColors.Default;
            }} else {{
                palette = levelSpecificPalettes[d.depth] || levelSpecificPalettes.default;
            }}
            return palette.stroke;
        }});
      nodeUpdate.select('text').style("fill-opacity", 1).call(wrapText, 380);

      const nodeExit = node.exit().transition().duration(duration).attr('transform', d => `translate(${{source.y}},${{source.x}})`).remove();
      nodeExit.select('circle').attr('r', 1e-6);
      nodeExit.select('text').style('fill-opacity', 1e-6);

      const link = g.selectAll('path.link').data(links, d => d.id);
      const linkEnter = link.enter().insert('path', "g").attr('class', 'link').attr('d', d => {{ const o = {{ x: source.x0, y: source.y0 }}; return diagonal(o, o); }});

      linkEnter.merge(link).transition().duration(duration).attr('d', d => diagonal(d, d.parent))
        .style('stroke', d => {{
            const sourceNode = d.parent;
            if (!sourceNode) return phaseColors.Default.stroke;
            const l1AncestorName = sourceNode.data.originalStageName;
            const colorPalette = phaseColors[l1AncestorName] || phaseColors.Default;
            return colorPalette.stroke;
        }});
      link.exit().transition().duration(duration).attr('d', d => {{ const o = {{ x: source.x, y: source.y }}; return diagonal(o, o); }}).remove();
      nodes.forEach(d => {{ d.x0 = d.x; d.y0 = d.y; }});
    }}

    function diagonal(s, d) {{ return `M ${{s.y}} ${{s.x}} C ${{(s.y + d.y) / 2}} ${{s.x}}, ${{(s.y + d.y) / 2}} ${{d.x}}, ${{d.y}} ${{d.x}}`; }}

    function wrapText(textElements, maxWidth) {{
        const textPartColors = {{
            name: '#343a40',
            count: '#0056b3'
        }};
        const countRegex = /(\s\(Total Count: \d+\))$/;

        textElements.each(function () {{
            const textD3 = d3.select(this);
            const originalNodeText = textD3.datum().data.name;
            const x = parseFloat(textD3.attr("x") || 0);
            const initialDy = textD3.attr("dy");
            const textAnchor = textD3.attr("text-anchor");
            const lineHeight = 1.1;

            textD3.text(null);

            let namePart = originalNodeText;
            let countPartText = "";

            const countMatch = originalNodeText.match(countRegex);
            if (countMatch && originalNodeText.endsWith(countMatch[0])) {{
                namePart = originalNodeText.substring(0, originalNodeText.length - countMatch[0].length).trim();
                countPartText = countMatch[0].trim();
            }}

            const tokens = [];
            namePart.split(/\s+/).filter(Boolean).forEach(word => {{
                tokens.push({{ text: word, type: 'name' }});
            }});
            if (countPartText) {{
                tokens.push({{ text: countPartText, type: 'count' }});
            }}

            if (tokens.length === 0 && originalNodeText) {{
                tokens.push({{ text: originalNodeText, type: 'name' }});
            }}

            let currentTspan = textD3.append("tspan").attr("x", x).attr("dy", initialDy);
            if (textAnchor === "end") currentTspan.attr("text-anchor", "end");

            let lineTokens = [];

            for (let i = 0; i < tokens.length; i++) {{
                const tokenObj = tokens[i];

                lineTokens.push(tokenObj);
                currentTspan.text(lineTokens.map(t => t.text).join(" "));

                if (currentTspan.node().getComputedTextLength() > maxWidth && lineTokens.length > 1) {{
                    lineTokens.pop();

                    currentTspan.text(null);
                    lineTokens.forEach((prevToken, idx) => {{
                        currentTspan.append("tspan")
                            .text((idx > 0 ? " " : "") + prevToken.text)
                            .style("fill", textPartColors[prevToken.type] || textPartColors.name)
                            .style("font-weight", prevToken.type === 'count' ? "bold" : "normal");
                    }});

                    lineTokens = [tokenObj];
                    currentTspan = textD3.append("tspan").attr("x", x).attr("dy", lineHeight + "em");
                    if (textAnchor === "end") currentTspan.attr("text-anchor", "end");
                }}
            }}

            currentTspan.text(null);
            lineTokens.forEach((token, idx) => {{
                currentTspan.append("tspan")
                    .text((idx > 0 ? " " : "") + token.text)
                    .style("fill", textPartColors[token.type] || textPartColors.name)
                    .style("font-weight", token.type === 'count' ? "bold" : "normal");
            }});

            if (textD3.selectAll("tspan > tspan").empty() && textD3.select("tspan").text().length === 0 && originalNodeText) {{
                let t = textD3.select("tspan");
                let displayText = originalNodeText;
                t.text(displayText).style("fill", textPartColors.name);
                if (t.node() && t.node().getComputedTextLength() > maxWidth && displayText.length > 20) {{
                    let estimatedChars = Math.floor(maxWidth / (t.node().getComputedTextLength()/displayText.length) );
                    displayText = displayText.substring(0, Math.max(0, estimatedChars - 3)) + "...";
                    t.text(displayText);
                }}
            }}
        }});
    }}
  </script>
</body>
</html>
"""


def emit_html(
    tree: Dict[str, Any],
    *,
    title: str,
    header: str,
    svg_width: int = 6000,
    svg_height: int = 8000,
) -> str:
    # Escape </script> sequences so embedded JSON cannot break out of the
    # <script> tag, and HTML-escape values that land in <title>/<h1>.
    data_json = json.dumps(tree, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return _HTML_TEMPLATE.format(
        title=_html.escape(title),
        header=_html.escape(header),
        svg_width=svg_width,
        svg_height=svg_height,
        data_json=data_json,
    )


def write_tree_html(
    graph_path: Path,
    output_path: Path,
    *,
    root: Optional[str] = None,
    max_children: int = DEFAULT_MAX_CHILDREN,
    project_label: Optional[str] = None,
    # kept for CLI compatibility with the older signature; ignored now
    top_k_edges: int = 0,
) -> Path:
    from graphify.security import check_graph_file_size_cap
    check_graph_file_size_cap(graph_path)
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    tree = build_tree(graph, root=root, max_children=max_children,
                      project_label=project_label)
    title = f"{tree['name']} — graphify tree viewer"
    header = f"{tree['name']} — Knowledge Graph"
    html = emit_html(tree, title=title, header=header)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
