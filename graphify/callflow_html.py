#!/usr/bin/env python3
"""
callflow_html.py — Generate call-flow architecture HTML from graphify knowledge graph outputs.

Reads graph.json plus optional GRAPH_REPORT.md, .graphify_labels.json, and sections JSON,
then produces a self-contained HTML file with:
  - Dark-themed CSS (fixed template)
  - Navigation bar from section list
  - Architecture overview flowchart LR (aggregated section-level edges)
  - Per-section flowchart LR (auto-generated representative intra-section edges)
  - Call detail table scaffolding (headers + representative node rows)
  - Auto-generated section intros and key-file cards

Usage:
  python3 -m graphify export callflow-html
  python3 -m graphify export callflow-html /path/to/project/graphify-out/graph.json
  python3 -m graphify export callflow-html --graph /path/to/graph.json --output docs/architecture.html
"""

from __future__ import annotations

import json
import argparse
import os
import re
import sys
import hashlib
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html import escape


# ──────────────────────────────────────────────
# 1. CSS template (fixed, project-agnostic)
# ──────────────────────────────────────────────

CSS = """:root {
  --bg: #0f172a; --surface: #1e293b; --border: #334155;
  --text: #e2e8f0; --muted: #94a3b8; --accent: #38bdf8;
  --warn: #fbbf24; --err: #f87171; --ok: #34d399;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; }
.container { max-width: 1200px; margin: 0 auto; padding: 40px 24px; }
h1 { font-size: 2.4rem; margin-bottom: 8px; background: linear-gradient(135deg, var(--accent), #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
h2 { font-size: 1.7rem; margin: 48px 0 16px; padding-bottom: 8px; border-bottom: 2px solid var(--accent); }
h3 { font-size: 1.25rem; margin: 32px 0 12px; color: var(--accent); }
h4 { font-size: 1.05rem; margin: 20px 0 8px; color: var(--warn); }
p { margin: 8px 0; color: var(--muted); }
.subtitle { color: var(--muted); font-size: 1.1rem; margin-bottom: 32px; }
.mermaid { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 24px; margin: 20px 0; overflow-x: auto; position: relative; }
.mermaid.is-enhanced { padding: 0; overflow: hidden; min-height: 260px; }
.mermaid-viewport { padding: 54px 24px 24px; overflow: hidden; cursor: grab; touch-action: none; min-height: 260px; }
.mermaid-viewport.is-dragging { cursor: grabbing; }
.mermaid-viewport svg { max-width: none !important; height: auto; transform-origin: 0 0; transition: transform 120ms ease; }
.mermaid-toolbar { position: absolute; top: 10px; right: 10px; z-index: 3; display: flex; align-items: center; gap: 6px; padding: 6px; background: rgba(15,23,42,0.92); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.28); }
.mermaid-toolbar button, .mermaid-toolbar .zoom-level { height: 28px; min-width: 32px; border: 1px solid var(--border); border-radius: 6px; background: #1e293b; color: var(--text); font: 600 0.78rem system-ui, sans-serif; display: inline-flex; align-items: center; justify-content: center; }
.mermaid-toolbar button { cursor: pointer; }
.mermaid-toolbar button:hover { border-color: var(--accent); color: var(--accent); }
.mermaid-toolbar .zoom-level { min-width: 52px; color: var(--muted); background: transparent; }
.call-table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 0.92rem; }
.call-table th { background: #1a2744; color: var(--accent); text-align: left; padding: 10px 14px; border: 1px solid var(--border); }
.call-table td { padding: 8px 14px; border: 1px solid var(--border); vertical-align: top; }
.call-table tr:nth-child(even) { background: rgba(255,255,255,0.02); }
.tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 600; }
.tag-async { background: #7c3aed33; color: #a78bfa; }
.tag-class { background: #05966933; color: var(--ok); }
.tag-func { background: #2563eb33; color: var(--accent); }
.tag-cmd { background: #d9770633; color: var(--warn); }
.tag-endpoint { background: #dc262633; color: var(--err); }
.tag-hook { background: #db277733; color: #f472b6; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin: 16px 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; margin: 16px 0; }
.arrow-chain { font-family: 'Fira Code', monospace; font-size: 0.85rem; color: var(--accent); padding: 10px; background: rgba(56,189,248,0.06); border-radius: 6px; }
code { font-family: 'Fira Code', 'Cascadia Code', monospace; background: rgba(255,255,255,0.06); padding: 1px 6px; border-radius: 3px; font-size: 0.88em; }
ul, ol { margin: 8px 0 8px 24px; color: var(--muted); }
li { margin: 4px 0; }
a { color: var(--accent); }
hr { border: none; border-top: 1px solid var(--border); margin: 40px 0; }
.nav { position: sticky; top: 0; background: var(--bg); z-index: 10; padding: 12px 0; border-bottom: 1px solid var(--border); display: flex; gap: 20px; flex-wrap: wrap; font-size: 0.9rem; }
.nav a { text-decoration: none; }
.nav a:hover { text-decoration: underline; }
@media (max-width: 768px) { .container { padding: 16px; } h1 { font-size: 1.8rem; } }
"""


# ──────────────────────────────────────────────
# 2. Data loading and normalization helpers
# ──────────────────────────────────────────────

def read_json(path: str | Path, default=None):
    """Read JSON with a useful error message."""
    if not path:
        return default
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: invalid JSON in {path}: {exc}") from exc


def first_present(mapping: dict, *keys, default=None):
    """Return the first non-empty value for any candidate key."""
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def first_list(*values) -> list:
    """Return the first list from a set of possible schema locations."""
    for value in values:
        if isinstance(value, list):
            return value
    return []


def to_float(value, default: float = 0.0) -> float:
    """Convert graph numeric fields that may be serialized as strings."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def endpoint_id(value) -> str:
    """Normalize edge endpoints that may be strings or node-like objects."""
    if isinstance(value, dict):
        value = first_present(value, "id", "node_id", "key", "name", "qualified_name")
    return str(value or "")


def normalize_node(raw: dict, index: int) -> dict:
    """Normalize a graphify node across common graph.json schema variants."""
    node = dict(raw)
    node_id = first_present(
        node,
        "id",
        "node_id",
        "key",
        "uid",
        "name",
        "qualified_name",
        "fqname",
        "symbol",
        default=f"node_{index + 1}",
    )
    source_file = first_present(
        node,
        "source_file",
        "file",
        "file_path",
        "filepath",
        "path",
        "module_path",
        "defined_in",
        default="",
    )
    label = first_present(
        node,
        "label",
        "display_name",
        "title",
        "name",
        "qualified_name",
        "fqname",
        "symbol",
        default=node_id,
    )
    community = first_present(
        node,
        "community",
        "community_id",
        "cluster",
        "cluster_id",
        "group",
        "group_id",
        "modularity_class",
        default="unknown",
    )
    node_type = first_present(node, "node_type", "kind", "type", "category", default="")
    file_type = first_present(node, "file_type", "content_type", "artifact_type", default="")
    if not file_type:
        suffix = Path(str(source_file)).suffix.lower()
        file_type = "document" if suffix in {".md", ".mdx", ".rst", ".txt"} else "code"

    node["id"] = str(node_id)
    node["label"] = str(label)
    node["community"] = community
    node["source_file"] = str(source_file or "")
    node["node_type"] = str(node_type or "")
    node["file_type"] = str(file_type or "code")
    return node


def normalize_edge(raw: dict, index: int) -> dict | None:
    """Normalize graphify edges while preserving original fields."""
    edge = dict(raw)
    source = endpoint_id(first_present(edge, "source", "src", "from", "from_id", "start", "u"))
    target = endpoint_id(first_present(edge, "target", "dst", "to", "to_id", "end", "v"))
    if not source or not target:
        return None

    relation = first_present(edge, "relation", "type", "kind", "label", "predicate", default="relates")
    confidence = first_present(edge, "confidence", "evidence", "provenance", default="EXTRACTED")
    score = first_present(edge, "confidence_score", "score", "weight", "probability", default=1.0)

    edge["id"] = str(first_present(edge, "id", "edge_id", default=f"edge_{index + 1}"))
    edge["source"] = source
    edge["target"] = target
    edge["relation"] = str(relation or "relates").lower()
    edge["confidence"] = str(confidence or "EXTRACTED").upper()
    edge["confidence_score"] = to_float(score, 1.0)
    return edge


def _node_link_payload(data: dict) -> tuple[list, list] | None:
    """Read current graphify graph.json via NetworkX's node-link parser."""
    if not isinstance(data.get("nodes"), list):
        return None
    if not isinstance(data.get("links"), list) and not isinstance(data.get("edges"), list):
        return None

    try:
        from networkx.readwrite import json_graph

        try:
            graph = json_graph.node_link_graph(data, edges="links")
        except TypeError:
            graph = json_graph.node_link_graph(data)
    except Exception:
        return None

    nodes = []
    for node_id, attrs in graph.nodes(data=True):
        node = dict(attrs)
        node["id"] = node_id
        nodes.append(node)

    edges = []
    for index, (source, target, attrs) in enumerate(graph.edges(data=True), 1):
        edge = dict(attrs)
        edge["source"] = edge.get("_src", edge.get("source", source))
        edge["target"] = edge.get("_tgt", edge.get("target", target))
        edge.setdefault("id", f"edge_{index}")
        edges.append(edge)
    return nodes, edges


def load_graph(path: str | Path) -> tuple:
    """Load graph.json. Returns normalized (nodes, edges, hyperedges, metadata)."""
    data = read_json(path)
    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: graph file must contain a JSON object: {path}")

    graph_block = data.get("graph") if isinstance(data.get("graph"), dict) else {}
    meta_block = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}

    node_link = _node_link_payload(data)
    if node_link:
        raw_nodes, raw_edges = node_link
    else:
        raw_nodes = first_list(data.get("nodes"), data.get("vertices"), graph_block.get("nodes"), graph_block.get("vertices"))
        raw_edges = first_list(data.get("links"), data.get("edges"), graph_block.get("links"), graph_block.get("edges"))
    hyperedges = first_list(data.get("hyperedges"), graph_block.get("hyperedges"), data.get("groups"), graph_block.get("groups"))

    nodes = [normalize_node(n, i) for i, n in enumerate(raw_nodes) if isinstance(n, dict)]
    edges = []
    for i, raw_edge in enumerate(raw_edges):
        if not isinstance(raw_edge, dict):
            continue
        edge = normalize_edge(raw_edge, i)
        if edge:
            edges.append(edge)

    meta = dict(graph_block)
    meta.update(meta_block)
    for key in ("built_at_commit", "commit", "project_name", "repo", "repository", "language_breakdown"):
        if data.get(key) and not meta.get(key):
            meta[key] = data.get(key)
    if meta.get("commit") and not meta.get("built_at_commit"):
        meta["built_at_commit"] = meta["commit"]

    return nodes, edges, hyperedges, meta


def load_labels(path: str | Path | None) -> dict:
    """Load community labels from .graphify_labels.json, tolerating wrapper keys."""
    data = read_json(path, default={})
    if not isinstance(data, dict):
        return {}
    if isinstance(data.get("labels"), dict):
        data = data["labels"]
    if isinstance(data.get("communities"), dict):
        data = data["communities"]
    labels = {}
    for key, value in data.items():
        if isinstance(value, dict):
            value = first_present(value, "label", "name", "title", default=key)
        labels[str(key)] = str(value)
    return labels


def load_sections(path: str | Path | None) -> list:
    """Load section definitions from JSON file."""
    data = read_json(path, default=[])
    if isinstance(data, dict) and isinstance(data.get("sections"), list):
        data = data["sections"]
    if not isinstance(data, list):
        raise SystemExit(f"ERROR: sections file must contain a JSON array: {path}")
    return data


def load_report(path: str | Path | None) -> str:
    """Load GRAPH_REPORT.md if it exists."""
    if path and os.path.exists(path):
        return Path(path).read_text(encoding="utf-8")
    return ""


# ──────────────────────────────────────────────
# 3. Mermaid-safe label helpers
# ──────────────────────────────────────────────

def safe_mermaid_text(text: str) -> str:
    """Sanitize text for use inside a Mermaid node label.

    Replaces characters that Mermaid interprets as syntax:
    - -> (edge arrow) -> text
    - # (comment) -> removed
    - {} (shape syntax) -> removed
    - backticks -> removed
    - " -> '
    - HTML metacharacters -> entities
    """
    text = str(text or "")
    text = text.replace('"', "'")
    text = text.replace('`', '')
    text = text.replace('#', '')
    text = text.replace('|', ' ')
    text = text.replace('{', '').replace('}', '')
    text = text.replace("->>", " to ").replace("-->", " to ").replace("->", " to ")
    text = " ".join(text.split())
    return escape(text, quote=False)


def html_comment_text(text: str) -> str:
    """Keep generated HTML comments well-formed."""
    return str(text or "").replace("--", "- -").replace("\n", " ")


def stable_ascii_id(raw: str, prefix: str = "node", limit: int = 48) -> str:
    """Build a Mermaid-safe ASCII identifier with a hash suffix to avoid collisions."""
    raw = str(raw or "")
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", raw)
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        slug = prefix
    if slug[0].isdigit():
        slug = f"{prefix}_{slug}"
    return f"{slug[:limit].rstrip('_')}_{digest}"


def node_mermaid_id(node: dict) -> str:
    """Generate a safe Mermaid node ID from a graph node.

    Mermaid IDs must match [a-zA-Z][a-zA-Z0-9_]* — no dots, hyphens, slashes.
    """
    return stable_ascii_id(node.get("id", "unknown"), "node")


def mermaid_section_id(section_id: str) -> str:
    """Convert a section ID (like 'cli-entry') to a safe Mermaid ID (like 'CLI_ENTRY')."""
    return stable_ascii_id(section_id, "section").upper()


def safe_file_path(path: str) -> str:
    """Return a short, safe display path."""
    # Truncate long paths for display
    parts = path.split("/")
    if len(parts) > 3:
        return "/".join(parts[-3:])
    return path


def safe_filename(text: str, fallback: str = "project") -> str:
    """Create a conservative filename stem from a project name."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", str(text or "")).strip("-._")
    return stem or fallback


def infer_project_name(graph_path: str, meta: dict) -> str:
    """Infer a display project name when graph metadata does not include one."""
    if meta.get("project_name"):
        return meta["project_name"]
    path = Path(graph_path).resolve()
    if path.parent.name == "graphify-out" and len(path.parents) > 1:
        return path.parents[1].name
    return path.parent.name or "Project"


def resolve_graphify_paths(args) -> dict:
    """Resolve project root, graphify output dir, and optional files."""
    base = Path(args.project).expanduser() if args.project else Path.cwd()
    if args.graphify_out:
        graphify_out = Path(args.graphify_out).expanduser()
    elif args.graph:
        graphify_out = Path(args.graph).expanduser().parent
    elif (base / "graph.json").exists():
        graphify_out = base
    else:
        graphify_out = base / "graphify-out"

    project_root = graphify_out.parent if graphify_out.name == "graphify-out" else base
    graph = Path(args.graph).expanduser() if args.graph else graphify_out / "graph.json"
    report = Path(args.report).expanduser() if args.report else graphify_out / "GRAPH_REPORT.md"
    labels = Path(args.labels).expanduser() if args.labels else graphify_out / ".graphify_labels.json"
    sections = Path(args.sections).expanduser() if args.sections else None
    return {
        "base": project_root,
        "graphify_out": graphify_out,
        "graph": graph,
        "report": report,
        "labels": labels,
        "sections": sections,
    }


def is_zh(lang: str) -> bool:
    """Return true when localized strings should be Chinese."""
    return (lang or "").lower().startswith("zh")


def pick_text(lang: str, zh: str, en: str) -> str:
    """Small localization helper for generated copy."""
    return zh if is_zh(lang) else en


def detect_lang(lang: str, nodes: list, labels: dict) -> str:
    """Resolve auto language from labels and node names."""
    if lang and lang.lower() != "auto":
        return lang
    sample = " ".join(
        list(labels.values())[:50]
        + [str(n.get("label", "")) for n in nodes[:200]]
        + [str(n.get("source_file", "")) for n in nodes[:100]]
    )
    return "zh-CN" if re.search(r"[\u4e00-\u9fff]", sample) else "en"


def truncate_text(text: str, limit: int) -> str:
    """Truncate without splitting Mermaid syntax."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def humanize_label(label: str, source_file: str = "") -> str:
    """Convert graph labels into short labels people can scan in a diagram."""
    label = str(label or "").strip()
    if not label:
        return Path(source_file).name if source_file else "Unknown"
    if label.startswith(".") and label.endswith("()"):
        return label[1:]
    if label.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".rb")):
        return Path(label).name
    if "_" in label and " " not in label and len(label) > 28:
        parts = [p for p in label.split("_") if p]
        if parts:
            label = " ".join(parts[-3:])
    return truncate_text(label, 42)


def node_kind(node: dict) -> str:
    """Classify a graph node for Mermaid styling and table tags."""
    label = str(node.get("label") or node.get("id") or "").lower()
    source_file = str(node.get("source_file") or "").lower()
    file_type = str(node.get("file_type") or "").lower()
    node_type = str(node.get("node_type") or "").lower()
    if node_type in {"class", "klass", "struct", "interface", "enum", "trait", "model"}:
        return "klass"
    if node_type in {"module", "file", "package", "namespace"}:
        return "module"
    if node_type in {"endpoint", "route", "api", "handler", "controller"}:
        return "api"
    if node_type in {"test", "spec"}:
        return "test"
    if node_type in {"component", "hook", "view", "page"}:
        return "ui"
    if file_type in {"rationale", "document"}:
        return "concept"
    if "test" in source_file or label.startswith("test_") or "spec" in source_file:
        return "test"
    if any(word in label for word in ("endpoint", "router", "api", "route")):
        return "api"
    if any(word in label for word in ("cli", "command", "click", "typer")):
        return "entry"
    if any(word in label for word in ("async", "await", "stream", "sse")):
        return "async"
    raw_label = str(node.get("label") or "")
    hook_like = raw_label.startswith("use") and len(raw_label) > 3 and (raw_label[3].isupper() or raw_label[3] in "_-")
    if any(word in label for word in ("component", "props", "hook", "store")) or hook_like or source_file.endswith((".tsx", ".jsx", ".vue", ".svelte")):
        return "ui"
    raw = raw_label
    if raw[:1].isupper() and not raw.endswith("()"):
        return "klass"
    if raw.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs", ".swift", ".vue", ".svelte")):
        return "module"
    return "function"


def relation_label(relation: str, lang: str) -> str:
    """Map graph edge relation names to short diagram labels."""
    relation = str(relation or "").strip()
    zh = {
        "calls": "调用",
        "uses": "使用",
        "imports": "导入",
        "imports_from": "导入",
        "method": "方法",
        "contains": "包含",
        "rationale_for": "说明",
        "conceptually_related_to": "相关",
        "participate_in": "参与",
        "form": "组成",
    }
    en = {
        "calls": "calls",
        "uses": "uses",
        "imports": "imports",
        "imports_from": "imports",
        "method": "method",
        "contains": "contains",
        "rationale_for": "explains",
        "conceptually_related_to": "relates",
        "participate_in": "joins",
        "form": "forms",
    }
    mapped = (zh if is_zh(lang) else en).get(relation, relation.replace("_", " "))
    return safe_mermaid_text(mapped)


def preferred_edges(edges: list, allow_structure: bool = False) -> list:
    """Filter to edges that make a readable call-flow diagram."""
    primary = {"calls", "uses", "method", "imports", "imports_from"}
    secondary = {"contains", "rationale_for", "conceptually_related_to"}
    selected = []
    for edge in edges:
        if not should_include_edge(edge):
            continue
        relation = edge.get("relation", "")
        if relation in primary or (allow_structure and relation in secondary):
            selected.append(edge)
    if selected:
        return selected
    return [edge for edge in edges if should_include_edge(edge)]


def edge_score(edge: dict) -> float:
    """Rank edges by confidence and usefulness for diagrams."""
    relation = edge.get("relation", "")
    score = to_float(edge.get("confidence_score", 1.0), 1.0)
    if str(edge.get("confidence", "")).upper() == "EXTRACTED":
        score += 2.0
    if relation in {"calls", "uses", "method"}:
        score += 1.0
    elif relation in {"imports", "imports_from"}:
        score += 0.6
    elif relation == "contains":
        score -= 0.2
    elif relation == "rationale_for":
        score -= 0.6
    return score


def mermaid_init(scale: float, direction: str = "LR") -> str:
    """Return a Mermaid init directive that scales diagrams using Mermaid config."""
    scale = max(0.65, min(float(scale or 1.0), 1.8))
    config = {
        "theme": "dark",
        "themeVariables": {
            "fontSize": f"{round(15 * scale, 1)}px",
            "fontFamily": "Segoe UI, system-ui, sans-serif",
            "primaryColor": "#1e293b",
            "primaryTextColor": "#e2e8f0",
            "primaryBorderColor": "#38bdf8",
            "secondaryColor": "#0f172a",
            "tertiaryColor": "#334155",
            "lineColor": "#64748b",
            "textColor": "#e2e8f0",
        },
        "flowchart": {
            "htmlLabels": True,
            "curve": "basis",
            "nodeSpacing": round(48 * scale),
            "rankSpacing": round(64 * scale),
            "padding": round(14 * scale),
            "diagramPadding": round(10 * scale),
            "useMaxWidth": True,
        },
    }
    return f"%%{{init: {json.dumps(config, ensure_ascii=False)}}}%%\nflowchart {direction}"


def mermaid_class_defs() -> list:
    """Shared Mermaid-native styles for readable diagrams."""
    return [
        "    classDef entry fill:#422006,stroke:#fbbf24,color:#fde68a,stroke-width:1px;",
        "    classDef api fill:#450a0a,stroke:#f87171,color:#fee2e2,stroke-width:1px;",
        "    classDef async fill:#2e1065,stroke:#a78bfa,color:#ede9fe,stroke-width:1px;",
        "    classDef klass fill:#064e3b,stroke:#34d399,color:#d1fae5,stroke-width:1px;",
        "    classDef ui fill:#831843,stroke:#f472b6,color:#fce7f3,stroke-width:1px;",
        "    classDef module fill:#172554,stroke:#60a5fa,color:#dbeafe,stroke-width:1px;",
        "    classDef test fill:#3f3f46,stroke:#a1a1aa,color:#f4f4f5,stroke-width:1px;",
        "    classDef concept fill:#292524,stroke:#a8a29e,color:#fafaf9,stroke-dasharray:4 3;",
        "    classDef function fill:#0f172a,stroke:#38bdf8,color:#e0f2fe,stroke-width:1px;",
    ]


# ──────────────────────────────────────────────
# 4. Community and section indexing
# ──────────────────────────────────────────────

def build_community_index(nodes: list) -> dict:
    """Map community_id (str) -> list of nodes."""
    idx = defaultdict(list)
    for n in nodes:
        cid = str(n.get("community", "unknown"))
        idx[cid].append(n)
    return idx


def html_anchor_id(raw: str, fallback: str, used: set) -> str:
    """Generate a stable, unique HTML anchor ID."""
    raw = str(raw or fallback or "")
    base = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    if not base:
        base = re.sub(r"[^a-z0-9]+", "-", str(fallback or "section").lower()).strip("-")
    if not base:
        base = "section"
    base = base[:48].strip("-") or "section"
    candidate = base
    if candidate in used:
        candidate = f"{base}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:6]}"
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def normalize_communities(value) -> list:
    """Normalize section community lists from JSON or simple strings."""
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [value]


def normalize_sections(sections: list, lang: str) -> list:
    """Ensure sections have safe unique IDs and an overview section first."""
    overview_name = pick_text(lang, "架构总览", "Architecture Overview")
    normalized = [{"id": "overview", "name": overview_name, "communities": []}]
    used = {"overview", "hyperedges", "stats"}

    for index, raw in enumerate(sections or [], 1):
        if not isinstance(raw, dict):
            continue
        raw_id = str(raw.get("id") or raw.get("key") or raw.get("name") or f"section-{index}")
        raw_name = str(raw.get("name") or raw.get("label") or raw_id)
        if raw_id.lower() == "overview":
            normalized[0]["name"] = raw_name or overview_name
            continue

        sid = html_anchor_id(raw_id, f"section-{index}", used)
        normalized.append({
            "id": sid,
            "name": raw_name,
            "communities": normalize_communities(raw.get("communities", raw.get("community"))),
        })
    return normalized


def label_for_community(cid: str, labels: dict, nodes: list, lang: str) -> str:
    """Choose a readable section name for a community."""
    if str(cid) in labels and labels[str(cid)]:
        return labels[str(cid)]
    keywords = section_keywords(nodes, 3)
    if keywords:
        return " ".join(word.title() for word in keywords[:3])
    return pick_text(lang, f"社区 {cid}", f"Community {cid}")


SECTION_ARCHETYPES = [
    (
        "extract-pipeline",
        "提取管线",
        "Extraction Pipeline",
        {
            "extract", "extractor", "tree", "sitter", "parser", "language",
            "python", "javascript", "typescript", "rust", "java", "go",
            "ast", "calls", "imports", "multilang",
        },
    ),
    (
        "build-graph",
        "图谱构建",
        "Graph Build",
        {
            "build", "graph", "merge", "dedup", "node", "edge", "hyperedge",
            "json", "schema", "normalize", "confidence",
        },
    ),
    (
        "analysis-clustering",
        "分析聚类",
        "Analysis & Clustering",
        {
            "cluster", "community", "leiden", "cohesion", "analyze", "god",
            "surprise", "question", "query", "path", "explain", "benchmark",
        },
    ),
    (
        "outputs-docs",
        "输出文档",
        "Outputs & Docs",
        {
            "export", "html", "wiki", "obsidian", "canvas", "svg", "graphml",
            "report", "callflow", "mermaid", "tree", "documentation",
        },
    ),
    (
        "cli-skills",
        "CLI 与技能安装",
        "CLI & Skill Installers",
        {
            "main", "install", "uninstall", "skill", "agent", "claude",
            "codex", "opencode", "aider", "copilot", "kiro", "vscode",
            "hook", "command",
        },
    ),
    (
        "ingest-cache-update",
        "摄取与增量更新",
        "Ingestion & Updates",
        {
            "ingest", "fetch", "download", "url", "html", "markdown",
            "cache", "manifest", "watch", "update", "incremental",
            "transcribe", "video", "audio", "google",
        },
    ),
    (
        "serve-api",
        "服务 API",
        "Serving API",
        {
            "serve", "api", "request", "response", "endpoint", "router",
            "handle", "upload", "search", "delete", "enrich",
        },
    ),
    (
        "security-global",
        "安全与全局图",
        "Security & Global Graph",
        {
            "security", "safe", "ssrf", "xss", "path", "traversal",
            "global", "prefix", "prune", "repo", "clone",
        },
    ),
    (
        "tests-fixtures",
        "测试与样例",
        "Tests & Fixtures",
        {
            "test", "tests", "fixture", "fixtures", "sample", "assert",
            "pytest", "mock",
        },
    ),
]


def _community_text(nodes: list, label: str = "") -> str:
    parts = [label]
    for node in nodes[:80]:
        parts.append(str(node.get("label", "")))
        parts.append(str(node.get("source_file", "")))
        parts.append(str(node.get("node_type", "")))
        parts.append(str(node.get("file_type", "")))
    return " ".join(parts).lower()


def _keyword_score(text: str, keywords: set[str]) -> int:
    score = 0
    for keyword in keywords:
        score += len(re.findall(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text))
    return score


def _rank_grouped_sections(grouped: dict, max_sections: int) -> tuple[list, list]:
    """Return selected grouped sections and overflow communities."""
    ranked = sorted(
        grouped.values(),
        key=lambda sec: (sec["priority"], -sec["node_count"], sec["id"]),
    )
    cap = max(1, int(max_sections or 15))
    selected = ranked[:cap]
    overflow = ranked[cap:]
    overflow_communities = []
    for sec in overflow:
        overflow_communities.extend(sec["communities"])
    return selected, overflow_communities


def derive_sections_from_communities(nodes: list, labels: dict, lang: str, max_sections: int) -> list:
    """Derive architecture-oriented sections when no sections JSON is supplied."""
    comm_idx = build_community_index(nodes)
    sections = [{"id": "overview", "name": pick_text(lang, "架构总览", "Architecture Overview"), "communities": []}]
    grouped = {}
    unassigned = []

    for cid, community_nodes in sorted(comm_idx.items(), key=lambda item: (-len(item[1]), str(item[0]))):
        label = label_for_community(cid, labels, community_nodes, lang)
        text = _community_text(community_nodes, label)
        best = None
        best_score = 0
        for priority, (sid, zh_name, en_name, keywords) in enumerate(SECTION_ARCHETYPES):
            score = _keyword_score(text, keywords)
            if score > best_score:
                best = (priority, sid, zh_name, en_name)
                best_score = score

        if best and best_score >= 2:
            priority, sid, zh_name, en_name = best
            sec = grouped.setdefault(
                sid,
                {
                    "id": sid,
                    "name": pick_text(lang, zh_name, en_name),
                    "communities": [],
                    "node_count": 0,
                    "priority": priority,
                },
            )
            sec["communities"].append(cid)
            sec["node_count"] += len(community_nodes)
        else:
            unassigned.append((cid, community_nodes, label))

    selected, overflow_communities = _rank_grouped_sections(grouped, max(1, int(max_sections or 15)) - 1)
    sections.extend(
        {"id": sec["id"], "name": sec["name"], "communities": sec["communities"]}
        for sec in selected
    )

    remaining_slots = max(0, int(max_sections or 15) - (len(sections) - 1) - 1)
    for cid, community_nodes, label in unassigned[:remaining_slots]:
        sections.append({"id": str(label or f"community-{cid}"), "name": label, "communities": [cid]})

    other_communities = overflow_communities + [cid for cid, _, _ in unassigned[remaining_slots:]]
    if other_communities:
        sections.append({
            "id": "other",
            "name": pick_text(lang, "其他", "Other"),
            "communities": other_communities,
        })
    return sections


def build_section_node_map(sections: list, comm_idx: dict) -> dict:
    """Map section_id -> list of nodes belonging to its communities."""
    section_nodes = {}
    for sec in sections:
        sid = sec["id"]
        if sid == "overview":
            section_nodes[sid] = []
            continue
        nodes = []
        for cid in sec.get("communities", []):
            nodes.extend(comm_idx.get(str(cid), []))
        section_nodes[sid] = nodes
    return section_nodes


def node_in_section(node_id: str, section_node_ids: set) -> bool:
    """Check if a node belongs to a section."""
    return node_id in section_node_ids


# ──────────────────────────────────────────────
# 5. Edge analysis
# ──────────────────────────────────────────────

def classify_edges(edges: list, section_nodes_map: dict) -> dict:
    """Classify edges as intra-section or inter-section.

    Returns:
        {
            "intra": {section_id: [edges]},
            "inter": [edges],
            "orphan": [edges]  # one endpoint not in any section
        }
    """
    # Build node -> section lookup
    node_section = {}
    for sid, nodes in section_nodes_map.items():
        for n in nodes:
            node_section[n.get("id")] = sid

    intra = defaultdict(list)
    inter = []
    orphan = []

    for e in edges:
        src = e.get("source", "")
        tgt = e.get("target", "")
        src_sec = node_section.get(src)
        tgt_sec = node_section.get(tgt)

        if src_sec is None or tgt_sec is None:
            orphan.append(e)
        elif src_sec == tgt_sec:
            intra[src_sec].append(e)
        else:
            inter.append(e)

    return {"intra": dict(intra), "inter": inter, "orphan": orphan, "node_section": node_section}


def should_include_edge(edge: dict) -> bool:
    """Decide whether to auto-include an edge in Mermaid output."""
    conf = str(edge.get("confidence", "EXTRACTED")).upper()
    score = to_float(edge.get("confidence_score", 1.0), 1.0)

    if conf == "EXTRACTED":
        return True
    if conf == "INFERRED" and score >= 0.85:
        return True
    # Low-confidence INFERRED or AMBIGUOUS: comment out for LLM review
    return False


# ──────────────────────────────────────────────
# 6. Mermaid diagram generators
# ──────────────────────────────────────────────

def node_degree_scores(edges: list) -> Counter:
    """Score nodes by useful edge participation."""
    scores = Counter()
    for edge in edges:
        score = edge_score(edge)
        scores[edge.get("source", "")] += score
        scores[edge.get("target", "")] += score
    return scores


def node_importance(node: dict) -> float:
    """Use graphify centrality fields when available."""
    for key in ("pagerank", "page_rank", "pageRank", "rank", "centrality", "score"):
        if key in node:
            return to_float(node.get(key), 0.0)
    return 0.0


def select_diagram_nodes(nodes: list, edges: list, max_nodes: int) -> list:
    """Select a compact, connected subset of nodes for readable diagrams."""
    node_by_id = {n.get("id"): n for n in nodes}
    usable_edges = preferred_edges(edges, allow_structure=False)
    if not usable_edges:
        usable_edges = preferred_edges(edges, allow_structure=True)
    scores = node_degree_scores(usable_edges)
    outgoing = Counter(edge.get("source", "") for edge in usable_edges)
    incoming = Counter(edge.get("target", "") for edge in usable_edges)
    selected = []
    seen = set()

    def add_node(nid: str) -> bool:
        node = node_by_id.get(nid)
        if not node or nid in seen:
            return False
        kind = node_kind(node)
        if kind == "concept" and len(selected) >= max(4, max_nodes // 3):
            return False
        selected.append(node)
        seen.add(nid)
        return len(selected) >= max_nodes

    # Start with likely entry points: nodes that call out more than they are called.
    entry_candidates = sorted(
        node_by_id,
        key=lambda nid: (-(outgoing[nid] - incoming[nid]), -outgoing[nid], str(nid)),
    )
    for nid in entry_candidates[: max(3, max_nodes // 3)]:
        if outgoing[nid] > 0 and add_node(nid):
            return selected

    # Then pull in the most useful neighbors from the strongest edges.
    for edge in sorted(usable_edges, key=edge_score, reverse=True):
        for nid in (edge.get("source"), edge.get("target")):
            if add_node(nid):
                return selected

    def fallback_key(node: dict) -> tuple:
        nid = node.get("id", "")
        kind_penalty = 1 if node_kind(node) == "concept" else 0
        return (
            kind_penalty,
            -scores.get(nid, 0),
            -node_importance(node),
            safe_file_path(node.get("source_file", "")),
            humanize_label(node.get("label", nid)),
        )

    for node in sorted(nodes, key=fallback_key):
        nid = node.get("id")
        if nid not in seen:
            selected.append(node)
            seen.add(nid)
        if len(selected) >= max_nodes:
            break
    return selected


def node_label(node: dict) -> str:
    """Build a readable Mermaid node label."""
    label = humanize_label(node.get("label") or node.get("id"), node.get("source_file", ""))
    source_file = safe_file_path(node.get("source_file", ""))
    if source_file and not label.endswith(Path(source_file).name):
        return f"{safe_mermaid_text(label)}<br/><small>{safe_mermaid_text(source_file)}</small>"
    return safe_mermaid_text(label)


def group_nodes_by_file(nodes: list) -> dict:
    """Group selected nodes by source file for Mermaid subgraphs."""
    groups = defaultdict(list)
    for node in nodes:
        source_file = safe_file_path(node.get("source_file", "")) or "External / generated"
        groups[source_file].append(node)
    return dict(sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])))


def section_edge_summary(classified_edges: dict) -> dict:
    """Aggregate inter-section edge counts and relation names."""
    node_section = classified_edges.get("node_section", {})
    summary = defaultdict(lambda: {"count": 0, "relations": Counter()})
    for edge in classified_edges.get("inter", []):
        if not should_include_edge(edge):
            continue
        src_sec = node_section.get(edge.get("source"))
        tgt_sec = node_section.get(edge.get("target"))
        if not src_sec or not tgt_sec or src_sec == tgt_sec:
            continue
        key = (src_sec, tgt_sec)
        summary[key]["count"] += 1
        summary[key]["relations"][edge.get("relation", "relates")] += 1
    return summary


def generate_overview_graph(sections: list, section_nodes_map: dict,
                             classified_edges: dict, labels: dict, lang: str,
                             diagram_scale: float) -> str:
    """Generate a readable section-level architecture overview."""
    lines = [mermaid_init(diagram_scale, "LR")]
    section_defs = [sec for sec in sections if sec["id"] != "overview"]

    for sec in section_defs:
        sid = mermaid_section_id(sec["id"])
        node_count = len(section_nodes_map.get(sec["id"], []))
        label = (
            f"{safe_mermaid_text(sec.get('name', sec['id']))}"
            f"<br/><small>{node_count} {safe_mermaid_text('nodes')}</small>"
        )
        lines.append(f'    {sid}("{label}")')
        lines.append(f"    class {sid} module;")

    aggregated = section_edge_summary(classified_edges)
    for (src, tgt), data in sorted(aggregated.items(), key=lambda item: item[1]["count"], reverse=True)[:12]:
        src_id = mermaid_section_id(src)
        tgt_id = mermaid_section_id(tgt)
        relation, _ = data["relations"].most_common(1)[0]
        label = relation_label(relation, lang)
        if data["count"] > 1:
            label = f"{label} x{data['count']}"
        lines.append(f"    {src_id} -->|{label}| {tgt_id}")

    if not aggregated and len(section_defs) > 1:
        for prev, cur in zip(section_defs, section_defs[1:]):
            lines.append(f"    {mermaid_section_id(prev['id'])} -.-> {mermaid_section_id(cur['id'])}")

    lines.extend(mermaid_class_defs())
    return "\n".join(lines)


def generate_section_flowchart(section_id: str, section_name: str,
                                nodes: list, edges: list, lang: str,
                                diagram_scale: float, max_nodes: int,
                                max_edges: int) -> str:
    """Generate a compact, human-readable call-flow chart for a section."""
    lines = [mermaid_init(diagram_scale, "LR")]
    lines.append(f"    %% Section: {safe_mermaid_text(section_name)} ({len(nodes)} nodes, {len(edges)} edges)")

    if not nodes:
        empty_label = pick_text(lang, f"{section_name} - 无节点", f"{section_name} - no nodes")
        lines.append(f'    empty("{safe_mermaid_text(empty_label)}")')
        lines.extend(mermaid_class_defs())
        return "\n".join(lines)

    selected_nodes = select_diagram_nodes(nodes, edges, max_nodes)
    selected_ids = {node.get("id") for node in selected_nodes}
    visible_edges = [
        edge for edge in preferred_edges(edges, allow_structure=False)
        if edge.get("source") in selected_ids and edge.get("target") in selected_ids
    ]
    if not visible_edges:
        visible_edges = [
            edge for edge in preferred_edges(edges, allow_structure=True)
            if edge.get("source") in selected_ids and edge.get("target") in selected_ids
        ]

    groups = group_nodes_by_file(selected_nodes)
    class_lines = []
    for source_file, group in groups.items():
        group_id = node_mermaid_id({"id": f"{section_id}_{source_file}"})
        if len(groups) > 1 and len(group) > 1:
            lines.append(f'    subgraph {group_id}["{safe_mermaid_text(source_file)}"]')
            indent = "        "
        else:
            indent = "    "
        for node in group:
            mid = node_mermaid_id(node)
            lines.append(f'{indent}{mid}("{node_label(node)}")')
            class_lines.append(f"    class {mid} {node_kind(node)};")
        if len(groups) > 1 and len(group) > 1:
            lines.append("    end")

    included = 0
    for edge in sorted(visible_edges, key=edge_score, reverse=True):
        if included >= max_edges:
            break
        src_id = node_mermaid_id({"id": edge.get("source", "")})
        tgt_id = node_mermaid_id({"id": edge.get("target", "")})
        rel = relation_label(edge.get("relation", ""), lang)
        lines.append(f"    {src_id} -->|{rel}| {tgt_id}")
        included += 1

    omitted_nodes = max(0, len(nodes) - len(selected_nodes))
    omitted_edges = max(0, len(visible_edges) - included)
    if omitted_nodes or omitted_edges:
        lines.append(f"    %% Omitted for readability: {omitted_nodes} nodes, {omitted_edges} edges")
    lines.extend(class_lines)
    lines.extend(mermaid_class_defs())
    return "\n".join(lines)


# ──────────────────────────────────────────────
# 7. HTML generators
# ──────────────────────────────────────────────

def generate_nav(sections: list) -> str:
    """Generate the sticky navigation bar."""
    links = []
    for sec in sections:
        links.append(f'    <a href="#{escape(sec["id"], quote=True)}">{escape(sec["name"])}</a>')
    return '<div class="nav">\n' + "\n".join(links) + "\n</div>"


def node_display_name(node: dict | None, fallback: str = "") -> str:
    """Readable node label for tables and summaries."""
    if not node:
        return str(fallback or "")
    label = str(node.get("label") or node.get("id") or fallback or "")
    return humanize_label(label, node.get("source_file", ""))


def format_node_refs(node_ids: set, node_by_id: dict, lang: str, empty_text: str, limit: int = 3) -> str:
    """Render node references as readable labels instead of internal IDs."""
    if not node_ids:
        return escape(empty_text)
    parts = []
    for nid in sorted(node_ids, key=lambda item: node_display_name(node_by_id.get(item), item).lower())[:limit]:
        node = node_by_id.get(nid)
        label = node_display_name(node, nid)
        source = safe_file_path((node or {}).get("source_file", ""))
        if source:
            parts.append(f"<code>{escape(label)}</code><br><small style=\"color:var(--muted)\">{escape(source)}</small>")
        else:
            parts.append(f"<code>{escape(label)}</code>")
    if len(node_ids) > limit:
        parts.append(escape(pick_text(lang, f"+{len(node_ids) - limit} 个更多", f"+{len(node_ids) - limit} more")))
    return "<br>".join(parts)


def generate_call_table_rows(nodes: list, section_edges: list, lang: str) -> str:
    """Generate call table row scaffolding for a section's nodes."""
    if not nodes:
        return ""

    # Build source/target lookup from edges
    node_by_id = {n.get("id"): n for n in nodes}
    callers = defaultdict(set)
    callees = defaultdict(set)
    for e in section_edges:
        src = e.get("source", "")
        tgt = e.get("target", "")
        if e.get("relation") in ("calls", "imports", "imports_from", "uses", "method"):
            callers[tgt].add(src)
            callees[src].add(tgt)

    rows = []
    for i, n in enumerate(nodes[:30], 1):  # cap at 30 rows
        nid = n.get("id", "")
        label = n.get("label", nid)
        source_file = safe_file_path(n.get("source_file", ""))
        file_type = n.get("file_type", "code")

        # Suggest a tag type based on file_type and label heuristics
        tag = _suggest_tag(label, file_type, lang, node_kind(n))

        caller_text = format_node_refs(
            callers.get(nid, set()),
            node_by_id,
            lang,
            pick_text(lang, "外部入口 / 无直接入边", "External entry / no inbound edge"),
        )
        callee_text = format_node_refs(
            callees.get(nid, set()),
            node_by_id,
            lang,
            pick_text(lang, "无直接出边", "No direct outbound edge"),
        )

        rows.append(f"""<tr>
  <td>{i}</td>
  <td><code>{escape(label)}</code><br><small style="color:var(--muted)">{escape(source_file)}</small></td>
  <td>{tag}</td>
  <td>{caller_text}</td>
  <td>{callee_text}</td>
  <td>{escape(_describe_node(label, source_file, file_type, lang))}</td>
</tr>""")

    return "\n".join(rows)


def _suggest_tag(label: str, file_type: str, lang: str, kind: str = "") -> str:
    """Heuristic tag suggestion based on label name and file type."""
    lower = label.lower()
    names = {
        "concept": ("概念", "Concept", "tag-func"),
        "entry": ("入口", "Entry", "tag-cmd"),
        "api": ("API", "API", "tag-endpoint"),
        "async": ("异步", "Async", "tag-async"),
        "klass": ("类", "Class", "tag-class"),
        "ui": ("UI", "UI", "tag-hook"),
        "module": ("模块", "Module", "tag-class"),
        "test": ("测试", "Test", "tag-func"),
        "function": ("函数", "Function", "tag-func"),
    }
    if kind in names:
        zh, en, cls = names[kind]
        return f'<span class="tag {cls}">{pick_text(lang, zh, en)}</span>'
    if file_type == "rationale":
        return f'<span class="tag tag-func">{pick_text(lang, "概念", "Concept")}</span>'
    if any(kw in lower for kw in ("cli", "command", "scan", "serve", "chat", "config")):
        if "group" in lower or "command" in lower:
            return f'<span class="tag tag-cmd">{pick_text(lang, "CLI命令", "CLI")}</span>'
    if any(kw in lower for kw in ("router", "endpoint", "api", "/api/")):
        return f'<span class="tag tag-endpoint">{pick_text(lang, "API端点", "API")}</span>'
    if any(kw in lower for kw in ("async", "await", "stream")):
        return f'<span class="tag tag-async">{pick_text(lang, "异步", "Async")}</span>'
    if any(kw in lower for kw in ("class", "model", "schema", "dataclass", "pydantic")):
        return f'<span class="tag tag-class">{pick_text(lang, "类", "Class")}</span>'
    if any(kw in lower for kw in ("hook", "usestate", "useeffect", "store")):
        return '<span class="tag tag-hook">Hook</span>'
    if any(kw in lower for kw in ("component", "props", "tsx", "jsx", "render")):
        return f'<span class="tag tag-class">{pick_text(lang, "组件", "Component")}</span>'
    return f'<span class="tag tag-func">{pick_text(lang, "函数", "Function")}</span>'


def _describe_node(label: str, source_file: str, file_type: str, lang: str) -> str:
    """Generate a compact human-readable description for a graph node."""
    lower = label.lower()
    source = source_file or pick_text(lang, "项目", "project")
    if file_type == "rationale":
        return pick_text(lang, f"设计说明：{label}", f"Design note for {label}.")
    if file_type == "document":
        return pick_text(lang, f"文档入口，描述 {label} 相关能力。", f"Documentation node describing {label}.")
    if label.endswith(".py") or label.endswith(".tsx") or label.endswith(".ts"):
        return pick_text(lang, f"{source} 中的模块文件，承载该层主要实现。", f"Module file in {source}.")
    if "config" in lower:
        return pick_text(lang, "读取、解析或持久化项目配置。", "Reads, resolves, or persists project configuration.")
    if "scan" in lower:
        return pick_text(lang, "触发项目扫描或处理扫描状态。", "Starts scanning or handles scan status.")
    if "ingest" in lower or "clone" in lower or "git" in lower:
        return pick_text(lang, "把本地目录或远程仓库转换为分析上下文。", "Turns a local path or remote repository into analysis context.")
    if "prompt" in lower:
        return pick_text(lang, "构造发送给 LLM 的结构化提示。", "Builds structured prompts for model calls.")
    if "analy" in lower:
        return pick_text(lang, "编排分析流程并产出结构化文档数据。", "Orchestrates analysis and returns structured documentation data.")
    if "graph" in lower or "dependency" in lower:
        return pick_text(lang, "构建依赖关系并提供排序或图形化数据。", "Builds dependency relationships and graph data.")
    if "export" in lower or "markdown" in lower or "html" in lower:
        return pick_text(lang, "将文档数据导出为目标格式。", "Exports documentation data to a target format.")
    if "chat" in lower or "rag" in lower or "retrieve" in lower:
        return pick_text(lang, "支撑检索增强问答或流式聊天。", "Supports retrieval-augmented Q&A or streaming chat.")
    if "wiki" in lower or "page" in lower or "sidebar" in lower:
        return pick_text(lang, "组织文档页面、侧边栏或内容读取。", "Organizes documentation pages, navigation, or content lookup.")
    if "cache" in lower or "hash" in lower:
        return pick_text(lang, "缓存分析结果或生成缓存键。", "Caches analysis results or computes cache keys.")
    if "test" in lower:
        return pick_text(lang, "验证导入、入口点或版本等基础行为。", "Verifies imports, entry points, or version behavior.")
    return pick_text(lang, f"{source} 中的 {label} 节点。", f"{label} node in {source}.")


def generate_header(sections: list, meta: dict, lang: str) -> str:
    """Generate the HTML header, title, subtitle, and nav."""
    project_name = str(meta.get("project_name", "Project"))
    commit = str(meta.get("built_at_commit", "unknown"))[:7]

    if lang.startswith("zh"):
        title = f"{project_name} — 完整调用流程与架构文档"
        subtitle = (
            f"由 graphify 知识图谱生成：{meta.get('node_count', '?')} 个节点、"
            f"{meta.get('edge_count', '?')} 条边、{meta.get('community_count', '?')} 个社区。"
            f"Commit: {commit}"
        )
    else:
        title = f"{project_name} — Complete Call Flow & Architecture Documentation"
        subtitle = (
            f"Generated from graphify knowledge graph: {meta.get('node_count', '?')} nodes, "
            f"{meta.get('edge_count', '?')} edges, {meta.get('community_count', '?')} communities. "
            f"Commit: {commit}"
        )

    return f"""<h1>{escape(title)}</h1>
<p class="subtitle">{escape(subtitle)}</p>

{generate_nav(sections)}
"""


def derive_flow_chain(sections: list, classified_edges: dict) -> str:
    """Derive a readable section flow from inter-section edges."""
    section_names = {sec["id"]: sec.get("name", sec["id"]) for sec in sections}
    order = [sec["id"] for sec in sections if sec["id"] != "overview"]
    if not order:
        return "Graph nodes -> documentation"

    outgoing = defaultdict(Counter)
    incoming = Counter()
    for (src, tgt), data in section_edge_summary(classified_edges).items():
        outgoing[src][tgt] += data["count"]
        incoming[tgt] += data["count"]

    start = min(order, key=lambda sid: (incoming.get(sid, 0), order.index(sid)))
    chain = [start]
    seen = {start}
    current = start
    while len(chain) < min(7, len(order)):
        candidates = [(count, tgt) for tgt, count in outgoing.get(current, {}).items() if tgt not in seen]
        if candidates:
            _, nxt = max(candidates)
        else:
            remaining = [sid for sid in order if sid not in seen]
            if not remaining:
                break
            nxt = remaining[0]
        chain.append(nxt)
        seen.add(nxt)
        current = nxt
    return " -> ".join(section_names.get(sid, sid) for sid in chain)


def generate_overview_cards(meta: dict, report_text: str, sections: list,
                            section_nodes_map: dict, classified_edges: dict,
                            lang: str) -> str:
    """Generate generic overview cards."""
    rows = []
    for sec in sections:
        if sec["id"] == "overview":
            continue
        communities = ", ".join(str(c) for c in sec.get("communities", []))
        node_count = len(section_nodes_map.get(sec["id"], []))
        rows.append(
            f"<tr><td>{escape(sec['name'])}</td><td>{node_count}</td><td><code>{escape(communities)}</code></td></tr>"
        )

    flow = derive_flow_chain(sections, classified_edges)
    layer_title = pick_text(lang, "架构层次", "Architecture Layers")
    layer_cols = pick_text(lang, "<tr><th>层</th><th>节点</th><th>社区</th></tr>", "<tr><th>Layer</th><th>Nodes</th><th>Communities</th></tr>")
    flow_title = pick_text(lang, "核心数据流", "Core Flow")
    return f"""<div class="grid">
  <div class="card">
    <h4>{layer_title}</h4>
    <table style="width:100%;font-size:0.85rem;">
      {layer_cols}
      {''.join(rows)}
    </table>
  </div>
  <div class="card">
    <h4>{flow_title}</h4>
    <div class="arrow-chain">{escape(flow)}</div>
  </div>
</div>"""


def section_keywords(nodes: list, limit: int = 5) -> list:
    """Pick representative words from labels and file names."""
    counts = Counter()
    stopwords = {
        "the", "and", "for", "with", "from", "this", "that", "class", "function",
        "method", "file", "src", "lib", "core", "index", "main", "init", "py",
        "ts", "tsx", "js", "jsx", "go", "rs", "java", "html", "css",
    }
    for node in nodes:
        text = f"{node.get('label', '')} {node.get('source_file', '')}".replace("/", " ").replace("_", " ").replace("-", " ")
        for raw in text.split():
            word = "".join(ch for ch in raw.lower() if ch.isalnum())
            if len(word) < 3 or word in stopwords:
                continue
            counts[word] += 1
    return [word for word, _ in counts.most_common(limit)]


def generate_section_intro(sec: dict, nodes: list, edge_count: int, lang: str) -> str:
    """Generate the section introductory paragraph."""
    file_counts = Counter(n.get("source_file") for n in nodes if n.get("source_file"))
    files = [safe_file_path(path) for path, _ in file_counts.most_common(3)]
    keywords = section_keywords(nodes, 4)
    if is_zh(lang):
        file_text = "、".join(files) if files else "未标注源文件"
        keyword_text = "、".join(keywords) if keywords else sec.get("name", sec["id"])
        text = (
            f"{sec.get('name', sec['id'])} 汇集了与 {keyword_text} 相关的实现，"
            f"主要分布在 {file_text}。本节覆盖 {len(nodes)} 个节点、{edge_count} 条内部边，"
            "图中只展示最有代表性的调用关系以保持可读性。"
        )
    else:
        file_text = ", ".join(files) if files else "unmapped files"
        keyword_text = ", ".join(keywords) if keywords else sec.get("name", sec["id"])
        text = (
            f"{sec.get('name', sec['id'])} groups implementation around {keyword_text}, "
            f"mostly in {file_text}. This section covers {len(nodes)} nodes and {edge_count} internal edges; "
            "the diagram shows only representative relationships to stay readable."
        )
    return f"<p>{escape(text)}</p>"


def generate_section_cards(sec: dict, nodes: list, section_edges: list, lang: str) -> str:
    """Generate key file and design-note cards for a section."""
    file_counts = defaultdict(int)
    for n in nodes:
        source_file = n.get("source_file") or ""
        if source_file:
            file_counts[source_file] += 1
    top_files = sorted(file_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    if top_files:
        file_rows = "\n".join(
            f"<tr><td><code>{escape(safe_file_path(path))}</code></td><td>{count} {escape(pick_text(lang, '个节点', 'nodes'))}</td></tr>"
            for path, count in top_files
        )
    else:
        file_rows = f'<tr><td colspan="2">{escape(pick_text(lang, "无源文件映射", "No source file mapping"))}</td></tr>'

    relation_counts = Counter(edge.get("relation", "relates") for edge in section_edges if should_include_edge(edge))
    relation_text = ", ".join(f"{relation_label(rel, lang)} x{count}" for rel, count in relation_counts.most_common(4))
    if not relation_text:
        relation_text = pick_text(lang, "未检测到高置信调用边", "No high-confidence call edges detected")
    note = pick_text(
        lang,
        f"本节由 graphify 社区聚类生成。关系概况：{relation_text}。图表优先展示高置信、跨节点调用或使用关系，完整节点清单位于表格中。",
        f"This section comes from graphify community clustering. Relationship summary: {relation_text}. The diagram prioritizes high-confidence calls or usage relationships; the table keeps the broader node inventory.",
    )
    key_files = pick_text(lang, "关键文件", "Key Files")
    role = pick_text(lang, "覆盖节点", "Coverage")
    design_notes = pick_text(lang, "设计备注", "Design Notes")
    return f"""<div class="grid">
  <div class="card">
    <h4>{key_files}</h4>
    <table style="width:100%;font-size:0.85rem;">
      <tr><th>File</th><th>{role}</th></tr>
      {file_rows}
    </table>
  </div>
  <div class="card">
    <h4>{design_notes}</h4>
    <p>{escape(note)}</p>
  </div>
</div>"""


# ──────────────────────────────────────────────
# 8. Main entry point
# ──────────────────────────────────────────────

class CallflowOptions:
    """Options for call-flow architecture HTML generation."""

    def __init__(
        self,
        project: str | Path | None = None,
        *,
        graphify_out: str | Path | None = None,
        graph: str | Path | None = None,
        report: str | Path | None = None,
        labels: str | Path | None = None,
        sections: str | Path | None = None,
        output: str | Path | None = None,
        lang: str = "auto",
        max_sections: int = 15,
        diagram_scale: float = 1.0,
        max_diagram_nodes: int = 18,
        max_diagram_edges: int = 24,
    ):
        self.project = str(project) if project is not None else None
        self.graphify_out = str(graphify_out) if graphify_out is not None else None
        self.graph = str(graph) if graph is not None else None
        self.report = str(report) if report is not None else None
        self.labels = str(labels) if labels is not None else None
        self.sections = str(sections) if sections is not None else None
        self.output = str(output) if output is not None else None
        self.lang = lang
        self.max_sections = max_sections
        self.diagram_scale = diagram_scale
        self.max_diagram_nodes = max_diagram_nodes
        self.max_diagram_edges = max_diagram_edges


def _report_highlights(report_text: str, lang: str) -> str:
    """Extract a compact highlights card from GRAPH_REPORT.md."""
    if not report_text.strip():
        return ""

    lines = report_text.splitlines()
    keep: list[str] = []
    in_gods = False
    in_summary = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_summary = stripped == "## Summary"
            in_gods = stripped.startswith("## God Nodes")
            continue
        if in_summary and stripped.startswith("- "):
            keep.append(stripped[2:])
        elif in_gods and re.match(r"^\d+\.", stripped):
            keep.append(stripped)
        if len(keep) >= 6:
            break

    if not keep:
        return ""

    title = pick_text(lang, "图谱报告摘要", "Graph Report Highlights")
    items = "\n".join(f"      <li>{escape(item)}</li>" for item in keep)
    return f"""<div class="card">
    <h4>{title}</h4>
    <ul>
{items}
    </ul>
  </div>"""


def write_callflow_html(
    project: str | Path | None = None,
    *,
    graphify_out: str | Path | None = None,
    graph: str | Path | None = None,
    report: str | Path | None = None,
    labels: str | Path | None = None,
    sections: str | Path | None = None,
    output: str | Path | None = None,
    lang: str = "auto",
    max_sections: int = 15,
    diagram_scale: float = 1.0,
    max_diagram_nodes: int = 18,
    max_diagram_edges: int = 24,
    verbose: bool = False,
) -> Path:
    """Generate call-flow architecture HTML from graphify output files."""
    args = CallflowOptions(
        project,
        graphify_out=graphify_out,
        graph=graph,
        report=report,
        labels=labels,
        sections=sections,
        output=output,
        lang=lang,
        max_sections=max_sections,
        diagram_scale=diagram_scale,
        max_diagram_nodes=max_diagram_nodes,
        max_diagram_edges=max_diagram_edges,
    )

    paths = resolve_graphify_paths(args)
    if not paths["graph"].exists():
        raise FileNotFoundError(
            f"graphify output not found: {paths['graph']}. "
            "Run graphify first or pass --graph /path/to/graph.json."
        )

    # Load data
    nodes, edges, hyperedges, meta = load_graph(paths["graph"])
    labels = load_labels(paths["labels"])
    lang = detect_lang(args.lang, nodes, labels)
    if paths["sections"]:
        sections = load_sections(paths["sections"])
    else:
        sections = derive_sections_from_communities(nodes, labels, lang, args.max_sections)
    sections = normalize_sections(sections, lang)
    report_text = load_report(paths["report"])

    if not nodes:
        raise ValueError("graph.json contains 0 nodes")
    if len(sections) <= 1:
        raise ValueError("no sections defined")

    if verbose and len(nodes) >= 5000:
        print("WARNING: Large graph -- Mermaid rendering may be slow. Consider --max-sections 5.", file=sys.stderr)

    node_ids = {node.get("id") for node in nodes}
    missing_endpoint_edges = [edge for edge in edges if edge.get("source") not in node_ids or edge.get("target") not in node_ids]
    if verbose and missing_endpoint_edges:
        print(f"WARNING: {len(missing_endpoint_edges)} edges reference nodes not present in graph.json.", file=sys.stderr)

    meta["project_name"] = infer_project_name(str(paths["graph"]), meta)
    meta["node_count"] = len(nodes)
    meta["edge_count"] = len(edges)
    meta["hyperedge_count"] = len(hyperedges)

    if args.output:
        output_path = Path(args.output).expanduser()
        if not output_path.is_absolute():
            output_path = paths["base"] / output_path
    else:
        output_path = paths["graphify_out"] / f"{safe_filename(meta['project_name'])}-callflow.html"

    if verbose:
        print(f"Loaded: {len(nodes)} nodes, {len(edges)} edges, {len(sections)} sections")
        print(f"Graph: {paths['graph']}")

    # Build index
    comm_idx = build_community_index(nodes)
    meta["community_count"] = len(comm_idx)
    section_nodes_map = build_section_node_map(sections, comm_idx)
    classified = classify_edges(edges, section_nodes_map)

    # Build HTML
    html = []
    doc_title = (
        f"{meta.get('project_name', 'Project')} — 完整调用流程与架构文档"
        if lang.startswith("zh")
        else f"{meta.get('project_name', 'Project')} — Complete Call Flow & Architecture Documentation"
    )

    # Doctype and head
    html.append(f"""<!DOCTYPE html>
<html lang="{escape(lang, quote=True)}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(doc_title)}</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
{CSS}
</style>
</head>
<body>
<div class="container">
""")

    # Header + nav
    html.append(generate_header(sections, meta, lang))

    # ── Architecture Overview (Section "overview") ──
    overview_name = sections[0].get("name", "Architecture Overview") if sections else "Architecture Overview"
    html.append(f"""<!-- ====== Architecture Overview ====== -->
<h2 id="overview">1. {escape(str(overview_name))}</h2>

<div class="mermaid">
""")
    html.append(generate_overview_graph(sections, section_nodes_map, classified, labels, lang, args.diagram_scale))
    html.append("""</div>
""")
    html.append(generate_overview_cards(meta, report_text, sections, section_nodes_map, classified, lang))
    report_card = _report_highlights(report_text, lang)
    if report_card:
        html.append(f'<div class="grid">\n  {report_card}\n</div>')
    html.append("<hr>")

    # ── Per-section content ──
    section_num = 1  # overview was #1
    for sec in sections:
        if sec["id"] == "overview":
            continue
        section_num += 1
        sid = sec["id"]
        name = sec.get("name", sid)
        sec_nodes = section_nodes_map.get(sid, [])
        sec_edges = classified.get("intra", {}).get(sid, [])

        edge_count = len(sec_edges)
        h3_title = pick_text(lang, "调用明细", "Call Details")
        number_header = "#"
        function_header = pick_text(lang, "节点", "Node")
        type_header = pick_text(lang, "类型", "Type")
        caller_header = pick_text(lang, "调用方", "Caller")
        callee_header = pick_text(lang, "被调用/依赖", "Callees")
        desc_header = pick_text(lang, "说明", "Description")

        html.append(f"""<!-- ====== {section_num}. {html_comment_text(name)} ====== -->
<h2 id="{escape(str(sid), quote=True)}">{section_num}. {escape(str(name))}</h2>
{generate_section_intro(sec, sec_nodes, edge_count, lang)}

<div class="mermaid">
{generate_section_flowchart(sid, name, sec_nodes, sec_edges, lang, args.diagram_scale, args.max_diagram_nodes, args.max_diagram_edges)}
</div>

<h3>{h3_title}</h3>
<table class="call-table">
<tr>
  <th style="width:5%">{number_header}</th>
  <th style="width:28%">{function_header}</th>
  <th style="width:10%">{type_header}</th>
  <th style="width:17%">{caller_header}</th>
  <th style="width:20%">{callee_header}</th>
  <th style="width:20%">{desc_header}</th>
</tr>
{generate_call_table_rows(sec_nodes, sec_edges, lang)}
</table>

{generate_section_cards(sec, sec_nodes, sec_edges, lang)}
<hr>
""")

    # ── Section: Hyperedges (if any) ──
    if hyperedges:
        html.append("""<h2 id="hyperedges">Group Relationships (Hyperedges)</h2>
<div class="grid">
""")
        for he in hyperedges[:9]:
            hid = he.get("id", "?")
            hlabel = he.get("label", hid)
            hnodes = he.get("nodes", [])
            hrel = he.get("relation", "")
            html.append(f"""  <div class="card">
    <h4>{escape(str(hlabel))}</h4>
    <p><code>{escape(str(hrel))}</code> — {len(hnodes)} participants</p>
    <ul>""")
            for hn in hnodes[:5]:
                html.append(f"      <li><code>{escape(str(hn))}</code></li>")
            if len(hnodes) > 5:
                html.append(f"      <li>... and {len(hnodes) - 5} more</li>")
            html.append("    </ul>\n  </div>")
        html.append("</div>\n<hr>")

    # ── Section: Statistics ──
    total_sections = sum(1 for s in sections if s["id"] != "overview")
    html.append(f"""<h2 id="stats">Project Statistics</h2>

<div class="grid">
  <div class="card">
    <h4>Graph</h4>
    <table style="width:100%;font-size:0.85rem;">
      <tr><td>Nodes</td><td>{len(nodes)}</td></tr>
      <tr><td>Edges</td><td>{len(edges)}</td></tr>
      <tr><td>Hyperedges</td><td>{len(hyperedges)}</td></tr>
      <tr><td>Communities</td><td>{len(comm_idx)}</td></tr>
      <tr><td>Documented Sections</td><td>{total_sections}</td></tr>
    </table>
  </div>
  <div class="card">
    <h4>Edge Confidence</h4>
    <table style="width:100%;font-size:0.85rem;">
      <tr><td>EXTRACTED</td><td>{sum(1 for e in edges if e.get('confidence') == 'EXTRACTED')}</td></tr>
      <tr><td>INFERRED</td><td>{sum(1 for e in edges if e.get('confidence') == 'INFERRED')}</td></tr>
      <tr><td>AMBIGUOUS</td><td>{sum(1 for e in edges if e.get('confidence') == 'AMBIGUOUS')}</td></tr>
    </table>
  </div>
</div>
""")

    # ── Footer ──
    html.append(f"""<div style="text-align:center; padding:40px 0; color: var(--muted); font-size:0.9rem;">
  <p>{escape(str(meta.get('project_name', 'Project')))} — Architecture Documentation</p>
  <p>Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · graphify callflow-html</p>
</div>
""")

    # Close
    html.append("""</div><!-- .container -->

<script>
(function () {
  const mermaidConfig = {
    startOnLoad: false,
    theme: 'dark',
    securityLevel: 'loose',
    flowchart: { htmlLabels: true, useMaxWidth: true },
    themeVariables: {
      primaryColor: '#1e293b',
      primaryTextColor: '#e2e8f0',
      primaryBorderColor: '#38bdf8',
      secondaryColor: '#0f172a',
      tertiaryColor: '#334155',
      lineColor: '#64748b',
      textColor: '#e2e8f0',
    }
  };

  mermaid.initialize(mermaidConfig);

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function enhanceMermaidDiagrams() {
    document.querySelectorAll('.mermaid').forEach((container) => {
      if (container.dataset.zoomReady === 'true') return;
      const svg = container.querySelector('svg');
      if (!svg) return;

      container.dataset.zoomReady = 'true';
      container.classList.add('is-enhanced');

      const viewport = document.createElement('div');
      viewport.className = 'mermaid-viewport';
      svg.parentNode.insertBefore(viewport, svg);
      viewport.appendChild(svg);

      const toolbar = document.createElement('div');
      toolbar.className = 'mermaid-toolbar';
      toolbar.innerHTML = [
        '<button type="button" data-action="zoom-out" title="Zoom out">-</button>',
        '<span class="zoom-level" data-role="level">100%</span>',
        '<button type="button" data-action="zoom-in" title="Zoom in">+</button>',
        '<button type="button" data-action="fit" title="Fit width">Fit</button>',
        '<button type="button" data-action="reset" title="Reset view">Reset</button>'
      ].join('');
      container.insertBefore(toolbar, viewport);

      const state = { scale: 1, x: 0, y: 0, dragging: false, startX: 0, startY: 0, originX: 0, originY: 0 };
      const level = toolbar.querySelector('[data-role="level"]');

      function applyTransform() {
        svg.style.transform = `translate(${state.x}px, ${state.y}px) scale(${state.scale})`;
        level.textContent = `${Math.round(state.scale * 100)}%`;
      }

      function zoomBy(delta) {
        state.scale = clamp(state.scale + delta, 0.25, 3);
        applyTransform();
      }

      function reset() {
        state.scale = 1;
        state.x = 0;
        state.y = 0;
        applyTransform();
      }

      function fitWidth() {
        const rawWidth = svg.viewBox && svg.viewBox.baseVal && svg.viewBox.baseVal.width
          ? svg.viewBox.baseVal.width
          : svg.getBoundingClientRect().width / state.scale;
        if (!rawWidth) {
          reset();
          return;
        }
        state.scale = clamp((viewport.clientWidth - 48) / rawWidth, 0.25, 1.4);
        state.x = 0;
        state.y = 0;
        applyTransform();
      }

      toolbar.addEventListener('click', (event) => {
        const button = event.target.closest('button[data-action]');
        if (!button) return;
        const action = button.dataset.action;
        if (action === 'zoom-in') zoomBy(0.15);
        if (action === 'zoom-out') zoomBy(-0.15);
        if (action === 'fit') fitWidth();
        if (action === 'reset') reset();
      });

      viewport.addEventListener('wheel', (event) => {
        if (!event.ctrlKey && !event.metaKey) return;
        event.preventDefault();
        zoomBy(event.deltaY < 0 ? 0.1 : -0.1);
      }, { passive: false });

      viewport.addEventListener('pointerdown', (event) => {
        if (event.button !== 0) return;
        state.dragging = true;
        state.startX = event.clientX;
        state.startY = event.clientY;
        state.originX = state.x;
        state.originY = state.y;
        viewport.classList.add('is-dragging');
        viewport.setPointerCapture(event.pointerId);
      });

      viewport.addEventListener('pointermove', (event) => {
        if (!state.dragging) return;
        state.x = state.originX + event.clientX - state.startX;
        state.y = state.originY + event.clientY - state.startY;
        applyTransform();
      });

      function endDrag(event) {
        if (!state.dragging) return;
        state.dragging = false;
        viewport.classList.remove('is-dragging');
        if (viewport.hasPointerCapture(event.pointerId)) {
          viewport.releasePointerCapture(event.pointerId);
        }
      }

      viewport.addEventListener('pointerup', endDrag);
      viewport.addEventListener('pointercancel', endDrag);
      applyTransform();
    });
  }

  function renderMermaid() {
    const result = mermaid.run
      ? mermaid.run({ querySelector: '.mermaid' })
      : Promise.resolve();
    Promise.resolve(result)
      .then(enhanceMermaidDiagrams)
      .catch((error) => {
        console.error('Mermaid render failed:', error);
        enhanceMermaidDiagrams();
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderMermaid);
  } else {
    renderMermaid();
  }
})();
</script>

</body>
</html>""")

    # Write output
    output = "\n".join(html)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")

    # Summary
    mermaid_count = output.count('<div class="mermaid">')
    table_count = output.count('<table class="call-table">')
    section_count = output.count('<h2 id=')

    if verbose:
        print(f"Call-flow HTML written: {output_path}")
        print(f"  Sections: {section_count}  |  Mermaid diagrams: {mermaid_count}  |  Call tables: {table_count}")
        print("  Diagrams use Mermaid init directives plus interactive zoom/pan controls.")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate call-flow architecture HTML from graphify knowledge graph outputs"
    )
    parser.add_argument("project", nargs="?", default=None, help="Project root or graphify output directory")
    parser.add_argument("--graphify-out", default=None, help="Path to graphify output directory")
    parser.add_argument("--graph", default=None, help="Path to graph.json")
    parser.add_argument("--report", default=None, help="Path to GRAPH_REPORT.md")
    parser.add_argument("--labels", default=None, help="Path to .graphify_labels.json")
    parser.add_argument("--sections", default=None, help="Path to sections JSON file; auto-derived when omitted")
    parser.add_argument("--output", default=None, help="Output HTML path")
    parser.add_argument("--lang", default="auto", help="HTML language: auto, zh-CN, en, etc. (default: auto)")
    parser.add_argument("--max-sections", type=int, default=15, help="Maximum auto-derived sections, excluding overview")
    parser.add_argument("--diagram-scale", type=float, default=1.0, help="Mermaid-native diagram scale via init directive (0.65-1.8)")
    parser.add_argument("--max-diagram-nodes", type=int, default=18, help="Maximum representative nodes per section diagram")
    parser.add_argument("--max-diagram-edges", type=int, default=24, help="Maximum representative edges per section diagram")
    args = parser.parse_args()

    try:
        write_callflow_html(
            args.project,
            graphify_out=args.graphify_out,
            graph=args.graph,
            report=args.report,
            labels=args.labels,
            sections=args.sections,
            output=args.output,
            lang=args.lang,
            max_sections=args.max_sections,
            diagram_scale=args.diagram_scale,
            max_diagram_nodes=args.max_diagram_nodes,
            max_diagram_edges=args.max_diagram_edges,
            verbose=True,
        )
    except (FileNotFoundError, ValueError, SystemExit) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
