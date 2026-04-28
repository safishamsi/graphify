"""Human-friendly dashboard generator. Merges fine-grained communities into
macro-modules and renders a single-page HTML architecture overview."""
from __future__ import annotations
import html as _html
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import networkx as nx
from networkx.readwrite import json_graph

from graphify.analyze import _node_community_map, god_nodes, _is_file_node


DASHBOARD_COLORS = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
]


def _community_functional_key(G, communities, cid):
    dir_counts = Counter()
    for nid in communities[cid]:
        sf = G.nodes[nid].get("source_file", "")
        if sf:
            parts = Path(sf).parts
            if len(parts) >= 3:
                key = "/".join(parts[:3])
            elif len(parts) >= 2:
                key = "/".join(parts[:2])
            else:
                key = parts[0] if parts else "."
            dir_counts[key] += 1
    return dir_counts.most_common(1)[0][0] if dir_counts else "."


def _cross_community_weights(G, communities):
    node_comm = _node_community_map(communities)
    weights = defaultdict(int)
    for u, v in G.edges():
        cu, cv = node_comm.get(u), node_comm.get(v)
        if cu is not None and cv is not None and cu != cv:
            key = (min(cu, cv), max(cu, cv))
            weights[key] += 1
    return dict(weights)


def merge_communities(G, communities, min_count=5, max_count=10):
    n = len(communities)
    if n <= max_count:
        return {i: [i] for i in communities}

    total_nodes = sum(len(v) for v in communities.values())
    max_macro_size = total_nodes * 0.30

    # Step 1: Group by functional key (sub-directory depth 2-3)
    func_groups = defaultdict(list)
    for cid in communities:
        key = _community_functional_key(G, communities, cid)
        func_groups[key].append(cid)

    # Step 2: If too many groups, merge by parent directory
    if len(func_groups) > max_count:
        parent_groups = defaultdict(list)
        for key, cids in func_groups.items():
            parts = key.split("/")
            parent_key = "/".join(parts[:2]) if len(parts) > 2 else key
            parent_groups[parent_key].extend(cids)
        func_groups = parent_groups

    # Step 3: Split oversized groups using community edge structure
    final_groups = {}
    cross_weights = _cross_community_weights(G, communities)

    for key, cids in func_groups.items():
        group_size = sum(len(communities[c]) for c in cids)
        if group_size <= max_macro_size or len(cids) <= 1:
            final_groups[key] = cids
            continue

        sub_G = nx.Graph()
        for c in cids:
            sub_G.add_node(c, size=len(communities[c]))
        for (ca, cb), w in cross_weights.items():
            if ca in sub_G and cb in sub_G:
                sub_G.add_edge(ca, cb, weight=w)

        if sub_G.number_of_edges() > 0:
            try:
                sub_comms = nx.community.louvain_communities(sub_G, seed=42)
                for i, sc in enumerate(sub_comms):
                    final_groups[f"{key}#{i}"] = list(sc)
            except Exception:
                final_groups[key] = cids
        else:
            deeper = defaultdict(list)
            for c in cids:
                dk = _community_functional_key(G, communities, c)
                deeper[dk].append(c)
            if len(deeper) > 1:
                for i, (dk, dcids) in enumerate(deeper.items()):
                    final_groups[f"{key}#{i}"] = dcids
            else:
                final_groups[key] = cids

    # Step 4: Absorb tiny groups into nearest large group
    large = {k: v for k, v in final_groups.items() if sum(len(communities[c]) for c in v) >= 5}
    small = {k: v for k, v in final_groups.items() if sum(len(communities[c]) for c in v) < 5}

    if large and small:
        for sk, scids in small.items():
            best_key = next(iter(large))
            best_score = 0
            sk_base = sk.split("#")[0]
            for lk in large:
                lk_base = lk.split("#")[0]
                score = len([1 for a, b in zip(sk_base.split("/"), lk_base.split("/")) if a == b])
                if score > best_score:
                    best_score = score
                    best_key = lk
            large[best_key].extend(scids)
        final_groups = large

    # Step 5: Merge smallest if too many
    groups_list = list(final_groups.values())
    while len(groups_list) > max_count:
        groups_list.sort(key=lambda x: sum(len(communities[c]) for c in x))
        groups_list[1].extend(groups_list[0])
        groups_list.pop(0)

    # Step 6: Split largest if too few
    while len(groups_list) < min_count and len(groups_list) > 0:
        groups_list.sort(key=lambda x: sum(len(communities[c]) for c in x), reverse=True)
        largest = groups_list[0]
        if len(largest) <= 1:
            break
        mid = len(largest) // 2
        groups_list[0] = largest[:mid]
        groups_list.insert(1, largest[mid:])

    groups_list.sort(key=lambda x: sum(len(communities[c]) for c in x), reverse=True)
    return {i: cids for i, cids in enumerate(groups_list)}


def _macro_metadata(G, communities, macros):
    degree = dict(G.degree())
    node_macro = {}
    for mid, mcids in macros.items():
        for cid in mcids:
            for nid in communities[cid]:
                node_macro[nid] = mid

    modules = []
    for macro_id, cids in sorted(macros.items()):
        all_nodes = []
        for cid in cids:
            all_nodes.extend(communities[cid])

        files = set()
        for nid in all_nodes:
            sf = G.nodes[nid].get("source_file", "")
            if sf:
                files.add(sf)

        top_nodes = sorted(
            [(nid, degree.get(nid, 0)) for nid in all_nodes if not _is_file_node(G, nid)],
            key=lambda x: x[1], reverse=True,
        )[:5]

        file_scores = Counter()
        for nid in all_nodes:
            sf = G.nodes[nid].get("source_file", "")
            if sf:
                file_scores[sf] += degree.get(nid, 0)
        key_files = [f for f, _ in file_scores.most_common(5)]

        deps_out = Counter()
        for nid in all_nodes:
            for neighbor in G.neighbors(nid):
                other_macro = node_macro.get(neighbor)
                if other_macro is not None and other_macro != macro_id:
                    deps_out[other_macro] += 1

        modules.append({
            "id": macro_id,
            "community_ids": cids,
            "node_count": len(all_nodes),
            "file_count": len(files),
            "files": sorted(files),
            "key_files": key_files,
            "top_nodes": [(G.nodes[nid].get("label", nid), deg) for nid, deg in top_nodes],
            "deps": dict(deps_out.most_common()),
        })
    return modules


def _infer_module_name(module):
    files = module["key_files"]
    all_files = module.get("files", files)

    # Strategy 1: Most common meaningful directory across ALL files
    dir_counts = {}
    for f in all_files:
        parts = Path(f).parts
        for depth in range(min(3, len(parts)), 0, -1):
            d = parts[depth - 1] if depth <= len(parts) else None
            if d and d.lower() not in ("src", "lib", "app", ".", "", "__init__.py", "temp", "output"):
                if not d.endswith(".py") and not d.endswith(".js"):
                    dir_counts[d] = dir_counts.get(d, 0) + 1
                    break

    if dir_counts:
        best_dir = max(dir_counts, key=dir_counts.get)
        name = best_dir.replace("_", " ").replace("-", " ").strip()
        if name:
            return name.title()

    # Strategy 2: Top node labels
    labels = [label for label, _ in module["top_nodes"]]
    if labels:
        words = []
        for label in labels:
            for w in label.replace("_", " ").replace("()", "").replace(".", "").split():
                w = w.strip()
                if len(w) > 3 and w.lower() not in (
                    "self", "none", "true", "false", "main", "init", "test",
                    "run", "data", "result", "params",
                ):
                    words.append(w.lower())
        if words:
            from collections import Counter as _C
            most_common = _C(words).most_common(2)
            return " ".join(w.title() for w, _ in most_common)

    return f"Module {module['id']}"


def _deduplicate_names(modules):
    """Ensure unique names. For duplicates, use top node labels as the name."""
    from collections import Counter as _C
    name_counts = _C(m["name"] for m in modules)
    dupes = {name for name, count in name_counts.items() if count > 1}
    if not dupes:
        return
    for name in dupes:
        dupe_modules = [m for m in modules if m["name"] == name]
        for m in dupe_modules:
            if m["top_nodes"]:
                # Use top 1-2 meaningful node labels
                labels = []
                for label, deg in m["top_nodes"][:3]:
                    clean = label.replace("()", "").replace(".", "").replace("_", " ").strip()
                    # Skip generic names
                    if clean.lower() in ("main", "run", "init", "self", "counter", "start"):
                        continue
                    labels.append(clean.title())
                    if len(labels) >= 2:
                        break
                if labels:
                    m["name"] = " & ".join(labels)
                    continue
            m["name"] = f"{name} #{dupe_modules.index(m) + 1}"
    # Final pass: if still duplicated, append index
    name_counts2 = _C(m["name"] for m in modules)
    for name, count in name_counts2.items():
        if count > 1:
            idx = 1
            for m in modules:
                if m["name"] == name:
                    m["name"] = f"{name} ({idx})"
                    idx += 1



def build_description_prompt(modules):
    lines = [
        "Below are software modules extracted from a codebase knowledge graph.",
        "For each module, write a one-sentence business description in the SAME LANGUAGE",
        "as the file paths and node labels (if Chinese paths, write Chinese; if English, write English).",
        "Focus on WHAT it does for the user, not implementation details.",
        "",
        'Return ONLY a JSON object: {"0": "description", "1": "description", ...}',
        "",
    ]
    for m in modules:
        top = ", ".join(f"{label} ({deg} connections)" for label, deg in m["top_nodes"][:3])
        mfiles = ", ".join(m["key_files"][:3])
        lines.append(f"Module {m['id']} \"{m['name']}\":")
        lines.append(f"  Key files: {mfiles}")
        lines.append(f"  Top nodes: {top}")
        lines.append(f"  {m['node_count']} nodes, {m['file_count']} files")
        lines.append("")
    return "\n".join(lines)




# ── API & External Service Scanner ─────────────────────────────────────

def _scan_exposed_endpoints(files):
    """Scan Python files for exposed API endpoints (FastAPI/Flask decorators)."""
    import re as _re
    pattern = _re.compile(r'@(?:app|router)\.(get|post|put|delete|patch)\(["\'](.*?)["\']')
    endpoints = []
    for f in files:
        try:
            text = Path(f).read_text(errors="ignore")
            for match in pattern.finditer(text):
                method = match.group(1).upper()
                route = match.group(2)
                endpoints.append({"method": method, "route": route, "file": f})
        except Exception:
            continue
    return endpoints


def _scan_external_calls(files):
    """Scan Python files for external HTTP calls and SDK usage."""
    import re as _re
    url_pattern = _re.compile(r'https?://([a-zA-Z0-9][-a-zA-Z0-9]*\.[-a-zA-Z0-9.]+)')
    sdk_pattern = _re.compile(r'^(?:import|from)\s+(akshare|yfinance|tushare|baostock|boto3|openai|anthropic|httpx|cloudscraper|selenium|playwright|tdxpy|requests)', _re.MULTILINE)

    external_urls = {}  # domain -> [files]
    sdks = {}  # sdk_name -> [files]

    skip_domains = {"localhost", "127.0.0.1", "0.0.0.0", "example.com", "graphify.net",
                    "github.com", "cdn.jsdelivr.net", "d3js.org", "unpkg.com",
                    "schemas.microsoft.com", "www.w3.org", "json-schema.org"}

    for f in files:
        try:
            text = Path(f).read_text(errors="ignore")
            fname = str(f)

            # URLs
            for match in url_pattern.finditer(text):
                domain = match.group(1).lower()
                if domain not in skip_domains and not domain.endswith(".local"):
                    external_urls.setdefault(domain, set()).add(fname)

            # SDKs
            for match in sdk_pattern.finditer(text):
                sdk = match.group(1)
                sdks.setdefault(sdk, set()).add(fname)
        except Exception:
            continue

    # Convert sets to sorted lists
    return {
        "urls": {d: sorted(fs) for d, fs in sorted(external_urls.items())},
        "sdks": {s: sorted(fs) for s, fs in sorted(sdks.items())},
    }


def _render_api_section(endpoints, external):
    """Render the API & External Services HTML sections."""
    html_parts = []

    # Exposed endpoints
    if endpoints:
        # Group by prefix
        groups = {}
        for ep in endpoints:
            parts = ep["route"].strip("/").split("/")
            prefix = "/".join(parts[:3]) if len(parts) >= 3 else ep["route"]
            groups.setdefault(prefix, []).append(ep)

        rows = []
        for prefix, eps in sorted(groups.items()):
            for ep in eps:
                method_colors = {"GET": "#59A14F", "POST": "#4E79A7", "PUT": "#F28E2B", "DELETE": "#E15759", "PATCH": "#B07AA1"}
                color = method_colors.get(ep["method"], "#888")
                rows.append(
                    f'<tr><td><span style="color:{color};font-weight:600">{ep["method"]}</span></td>'
                    f'<td><code>{ep["route"]}</code></td>'
                    f'<td style="color:#666">{Path(ep["file"]).name}</td></tr>'
                )

        html_parts.append(
            f'<div class="section-title">Exposed API Endpoints ({len(endpoints)})</div>'
            f'<div class="api-table-wrap"><table class="api-table">'
            f'<thead><tr><th>Method</th><th>Route</th><th>File</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
        )

    # External services
    urls = external.get("urls", {})
    sdks = external.get("sdks", {})
    if urls or sdks:
        items = []
        for domain, files in urls.items():
            file_list = ", ".join(Path(f).name for f in files[:3])
            if len(files) > 3:
                file_list += f" +{len(files)-3}"
            items.append(
                f'<tr><td><code>{domain}</code></td>'
                f'<td>HTTP</td>'
                f'<td style="color:#666">{file_list}</td></tr>'
            )
        for sdk, files in sdks.items():
            file_list = ", ".join(Path(f).name for f in files[:3])
            if len(files) > 3:
                file_list += f" +{len(files)-3}"
            items.append(
                f'<tr><td><code>{sdk}</code></td>'
                f'<td>SDK</td>'
                f'<td style="color:#666">{file_list}</td></tr>'
            )

        html_parts.append(
            f'<div class="section-title">External Services ({len(urls)} domains, {len(sdks)} SDKs)</div>'
            f'<div class="api-table-wrap"><table class="api-table">'
            f'<thead><tr><th>Service</th><th>Type</th><th>Used in</th></tr></thead>'
            f'<tbody>{"".join(items)}</tbody></table></div>'
        )

    return "".join(html_parts)

def _reading_order(modules):
    dep_graph = nx.DiGraph()
    for m in modules:
        dep_graph.add_node(m["id"])
        for target_id in m["deps"]:
            dep_graph.add_edge(m["id"], target_id)
    try:
        pr = nx.pagerank(dep_graph)
    except Exception:
        pr = {m["id"]: 1.0 / max(len(modules), 1) for m in modules}
    ranked = sorted(modules, key=lambda m: (pr.get(m["id"], 0), m["node_count"]), reverse=True)
    order = []
    for i, m in enumerate(ranked):
        in_deg = dep_graph.in_degree(m["id"]) if m["id"] in dep_graph else 0
        if i == 0:
            reason = "Most depended-on module — start here"
        elif in_deg > 0:
            reason = f"Depended on by {in_deg} other module(s)"
        else:
            reason = "Leaf module — read after its dependencies"
        order.append({"module": m, "rank": i + 1, "reason": reason})
    return order


def _dashboard_css():
    return """<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f0f1a;color:#e0e0e0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.6}
.container{max-width:1200px;margin:0 auto;padding:24px}
.header{text-align:center;padding:40px 0 20px}
.header h1{font-size:28px;font-weight:600}
.header .subtitle{color:#888;font-size:14px;margin-top:8px}
.stats{display:flex;gap:16px;justify-content:center;flex-wrap:wrap;margin:24px 0}
.stat-card{background:#1a1a2e;border:1px solid #2a2a4e;border-radius:12px;padding:16px 24px;text-align:center;min-width:120px}
.stat-card .value{font-size:24px;font-weight:700;color:#4E79A7}
.stat-card .label{font-size:12px;color:#888;margin-top:4px}
#graph-container{background:#1a1a2e;border:1px solid #2a2a4e;border-radius:12px;margin:24px 0;min-height:200px;position:relative;overflow:visible;padding:20px}
#force-graph-container{background:#1a1a2e;border:1px solid #2a2a4e;border-radius:12px;margin:24px 0;height:420px;position:relative;overflow:hidden}
.section-title{font-size:20px;font-weight:600;margin:32px 0 16px;padding-bottom:8px;border-bottom:1px solid #2a2a4e}
.module-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}
.module-card{background:#1a1a2e;border:1px solid #2a2a4e;border-radius:12px;padding:20px;transition:border-color .2s}
.module-card:hover{border-color:#4E79A7}
.module-card .name{font-size:16px;font-weight:600;display:flex;align-items:center;gap:8px}
.module-card .dot{width:12px;height:12px;border-radius:50%;flex-shrink:0}
.module-card .desc{color:#aaa;font-size:13px;margin:8px 0 12px}
.module-card .meta{font-size:12px;color:#666}
.module-card .files{margin-top:10px;display:flex;flex-wrap:wrap;gap:4px}
.module-card .files code{font-size:11px;background:#0f0f1a;padding:2px 6px;border-radius:4px;color:#76B7B2}
.module-card .deps{margin-top:10px;font-size:12px;color:#888}
.module-card .deps a{color:#4E79A7;text-decoration:none;cursor:pointer}
.module-card .deps a:hover{text-decoration:underline}
.reading-order{background:#1a1a2e;border:1px solid #2a2a4e;border-radius:12px;padding:20px;margin:24px 0}
.reading-order ol{padding-left:20px}
.reading-order li{margin:8px 0}
.reading-order .reason{color:#888;font-size:12px}
.footer{text-align:center;color:#555;font-size:12px;padding:24px 0}
.footer a{color:#4E79A7}
.api-table-wrap{background:#1a1a2e;border:1px solid #2a2a4e;border-radius:12px;padding:16px;margin:8px 0;overflow-x:auto}
.api-table{width:100%;border-collapse:collapse;font-size:13px}
.api-table th{text-align:left;color:#888;font-size:11px;text-transform:uppercase;letter-spacing:0.05em;padding:6px 12px;border-bottom:1px solid #2a2a4e}
.api-table td{padding:5px 12px;border-bottom:1px solid #1a1a2e}
.api-table code{font-size:12px;color:#76B7B2}
.api-table tr:hover{background:#0f0f1a}
</style>"""



def _detect_layer(module):
    """Auto-detect which architectural layer a module belongs to.
    Returns one of: 'frontend', 'backend', 'data', 'engine', 'tools', 'tests'."""
    files = module.get("files", [])
    all_text = " ".join(files).lower()
    labels = " ".join(l for l, _ in module.get("top_nodes", [])).lower()
    name = module.get("name", "").lower()

    # Count directory-level signals (more reliable than substring matching)
    dir_signals = {"frontend": 0, "backend": 0, "engine": 0, "data": 0, "tools": 0, "tests": 0}
    for f in files:
        fl = f.lower()
        parts = Path(f).parts
        part_set = set(p.lower() for p in parts)
        if "frontend" in part_set or any(fl.endswith(e) for e in (".html", ".vue", ".tsx", ".jsx", ".css")):
            dir_signals["frontend"] += 1
        if "backend" in part_set or "api" in part_set or "app.py" in fl or "server" in part_set:
            dir_signals["backend"] += 1
        if "tests" in part_set and "backtest" not in fl:
            dir_signals["tests"] += 1
        elif Path(f).name.startswith("test_") and "backtest" not in fl and "tests" in part_set:
            dir_signals["tests"] += 1
        if "backtest" in part_set or "strategy" in fl or "rotation" in fl:
            dir_signals["engine"] += 1
        if "tools" in part_set or "calculator" in fl:
            dir_signals["tools"] += 1
        if any(k in fl for k in ("crawl", "scraper", "fetch", "spider")):
            if "backend" in part_set:
                dir_signals["backend"] += 1
            else:
                dir_signals["data"] += 1
        if any(k in fl for k in ("基金", "fund", "filter", "analyze", "估值")):
            dir_signals["data"] += 1

    # Pick the layer with the strongest signal
    best = max(dir_signals, key=dir_signals.get)
    if dir_signals[best] > 0:
        return best

    # Fallback: keyword matching on labels
    if any(k in labels for k in ("app", "server", "fastapi", "flask", "endpoint")):
        return "backend"
    if any(k in labels for k in ("backtest", "strategy", "rotation", "momentum")):
        return "engine"
    if any(k in labels for k in ("crawl", "scraper", "fetch")):
        return "data"

    return "engine"


def _mermaid_graph_script(modules, colors):
    """Generate a Mermaid.js flowchart embedded in the dashboard."""

    LAYER_ORDER = ["frontend", "backend", "engine", "data", "tools", "tests"]
    LAYER_LABELS = {
        "frontend": "Frontend",
        "backend": "Backend / API",
        "engine": "Core Engine",
        "data": "Data Layer",
        "tools": "Tools",
        "tests": "Tests",
    }
    LAYER_STYLES = {
        "frontend": "fill:#1a2a1a,stroke:#3a5a3a,color:#aaa",
        "backend": "fill:#1a1a2e,stroke:#3a3a5e,color:#aaa",
        "engine": "fill:#2e1a1a,stroke:#5e3a3a,color:#aaa",
        "data": "fill:#1a2e2e,stroke:#3a5e5e,color:#aaa",
        "tools": "fill:#2e2e1a,stroke:#5e5e3a,color:#aaa",
        "tests": "fill:#1e1e1e,stroke:#3e3e3e,color:#aaa",
    }
    NODE_COLORS = {
        "frontend": "fill:#59A14F,stroke:#59A14F,color:#fff",
        "backend": "fill:#4E79A7,stroke:#4E79A7,color:#fff",
        "engine": "fill:#E15759,stroke:#E15759,color:#fff",
        "data": "fill:#76B7B2,stroke:#76B7B2,color:#fff",
        "tools": "fill:#EDC948,stroke:#EDC948,color:#333",
        "tests": "fill:#BAB0AC,stroke:#BAB0AC,color:#333",
    }

    # Assign layers
    for m in modules:
        m["_layer"] = _detect_layer(m)

    # Group by layer
    layers = {}
    for m in modules:
        layers.setdefault(m["_layer"], []).append(m)
    active_layers = [l for l in LAYER_ORDER if l in layers]

    # Build Mermaid flowchart
    lines = ["flowchart TB"]

    # Subgraphs for each layer
    style_lines = []
    for layer in active_layers:
        label = LAYER_LABELS.get(layer, layer.title())
        lines.append(f"  subgraph {layer}[\"{label}\"]")
        lines.append(f"    direction LR")
        for m in layers[layer]:
            mid = f"m{m['id']}"
            name = m["name"].replace('"', "'")
            lines.append(f'    {mid}["{name}<br/><small>{m["node_count"]} nodes · {m["file_count"]} files</small>"]')
            style_lines.append(f"  style {mid} {NODE_COLORS.get(layer, 'fill:#666,stroke:#888,color:#fff')}")
        lines.append(f"  end")

    # Edges between modules (deps)
    seen = set()
    for m in modules:
        for tid, weight in m["deps"].items():
            pair = (min(m["id"], tid), max(m["id"], tid))
            if pair not in seen:
                seen.add(pair)
                src_id = f"m{m['id']}"
                tgt_id = f"m{tid}"
                if weight > 50:
                    lines.append(f"  {src_id} ===> {tgt_id}")
                elif weight > 10:
                    lines.append(f"  {src_id} ==> {tgt_id}")
                else:
                    lines.append(f"  {src_id} --> {tgt_id}")

    # Style lines
    lines.extend(style_lines)

    mermaid_code = "\n".join(lines)

    # Click handlers
    click_js = "\n".join(
        f'document.querySelector(\'[data-id="m{m["id"]}"]\')'
        for m in modules
    )

    mermaid_div = f'<div class="mermaid">\n{mermaid_code}\n</div>'
    mermaid_script = """<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  themeVariables: {
    primaryColor: '#1a1a2e',
    primaryTextColor: '#e0e0e0',
    primaryBorderColor: '#2a2a4e',
    lineColor: '#555',
    secondaryColor: '#2e1a1a',
    tertiaryColor: '#1a2e2e',
    fontSize: '14px',
  },
  flowchart: {
    htmlLabels: true,
    curve: 'basis',
    padding: 15,
    nodeSpacing: 30,
    rankSpacing: 40,
    useMaxWidth: true,
  },
  securityLevel: 'loose',
});
mermaid.run().then(() => {
  document.querySelectorAll('.node').forEach(node => {
    const id = node.id;
    const match = id.match(/m(\\d+)/);
    if (match) {
      node.style.cursor = 'pointer';
      node.addEventListener('click', () => {
        const el = document.getElementById('module-' + match[1]);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.style.borderColor = '#4E79A7';
          setTimeout(() => el.style.borderColor = '', 2000);
        }
      });
    }
  });
});
</script>"""
    return {"div": mermaid_div, "script": mermaid_script}




def _d3_force_graph_script(modules, colors):
    """D3 force layout for interactive exploration. Complements the Mermaid overview."""
    nodes_data = [{"id": m["id"], "name": m["name"], "nodeCount": m["node_count"],
                   "color": colors[m["id"] % len(colors)]} for m in modules]
    links_data = []
    seen = set()
    for m in modules:
        for tid, w in m["deps"].items():
            pair = (min(m["id"], tid), max(m["id"], tid))
            if pair not in seen:
                seen.add(pair)
                links_data.append({"source": m["id"], "target": tid, "weight": w})

    return '<script src="https://d3js.org/d3.v7.min.js"></script>\n<script>\n' + """
(function() {
const nodes2=__NODES__;
const links2=__LINKS__;
const ctr2=document.getElementById('force-graph-container');
const W2=ctr2.clientWidth,H2=400;
const svg2=d3.select('#force-graph-container').append('svg').attr('width',W2).attr('height',H2);
const maxN2=Math.max(1,...nodes2.map(n=>n.nodeCount));
const rS2=d3.scaleSqrt().domain([1,maxN2]).range([24,60]);
const maxW2=Math.max(1,...links2.map(l=>l.weight));
const wS2=d3.scaleLinear().domain([1,maxW2]).range([1.5,6]);
const sim2=d3.forceSimulation(nodes2)
  .force('link',d3.forceLink(links2).id(d=>d.id).distance(150))
  .force('charge',d3.forceManyBody().strength(-400))
  .force('center',d3.forceCenter(W2/2,H2/2))
  .force('collision',d3.forceCollide().radius(d=>rS2(d.nodeCount)+12));
const link2=svg2.selectAll('line').data(links2).join('line')
  .attr('stroke','#3a3a5e').attr('stroke-width',d=>wS2(d.weight)).attr('stroke-opacity',0.6);
const node2=svg2.selectAll('g').data(nodes2).join('g')
  .call(d3.drag().on('start',(e,d)=>{if(!e.active)sim2.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y})
  .on('drag',(e,d)=>{d.fx=e.x;d.fy=e.y})
  .on('end',(e,d)=>{if(!e.active)sim2.alphaTarget(0);d.fx=null;d.fy=null}));
node2.append('circle').attr('r',d=>rS2(d.nodeCount))
  .attr('fill',d=>d.color).attr('opacity',0.85).attr('stroke','#fff').attr('stroke-width',1.5);
node2.append('text').text(d=>d.name.length>12?d.name.slice(0,11)+'…':d.name)
  .attr('text-anchor','middle').attr('dy',d=>rS2(d.nodeCount)+16)
  .attr('fill','#ccc').attr('font-size','11px').attr('font-weight','500');
node2.append('text').text(d=>d.nodeCount+' nodes')
  .attr('text-anchor','middle').attr('dy',4)
  .attr('fill','#fff').attr('font-size','10px').attr('opacity',0.7);
node2.append('title').text(d=>d.name+' ('+d.nodeCount+' nodes)');
node2.style('cursor','pointer').on('click',(e,d)=>{
  const el=document.getElementById('module-'+d.id);
  if(el){el.scrollIntoView({behavior:'smooth',block:'center'});
  el.style.borderColor='#4E79A7';setTimeout(()=>el.style.borderColor='',2000);}
});
sim2.on('tick',()=>{
  link2.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y)
      .attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);
  node2.attr('transform',d=>'translate('+d.x+','+d.y+')');
});
})();
""".replace("__NODES__", json.dumps(nodes_data)).replace("__LINKS__", json.dumps(links_data)) + '\n</script>'


def _dashboard_graph_script(modules, colors):
    """Combined: Mermaid architecture diagram + D3 force graph.
    Returns dict with 'mermaid_div' (goes in container), 'scripts' (goes at end of body)."""
    mermaid = _mermaid_graph_script(modules, colors)
    d3_script = _d3_force_graph_script(modules, colors)
    return {
        "mermaid_div": mermaid["div"],
        "scripts": mermaid["script"] + "\n" + d3_script,
    }

def _render_dashboard(project_name, G, modules, reading_order, api_html=""):
    graph_parts = _dashboard_graph_script(modules, DASHBOARD_COLORS)
    total_nodes = G.number_of_nodes()
    total_edges = G.number_of_edges()
    total_files = len({G.nodes[n].get("source_file", "") for n in G.nodes() if G.nodes[n].get("source_file")})
    n_modules = len(modules)
    module_map = {m["id"]: m for m in modules}

    cards = []
    for m in modules:
        color = DASHBOARD_COLORS[m["id"] % len(DASHBOARD_COLORS)]
        desc = _html.escape(m.get("description", ""))
        desc_html = f'<div class="desc">{desc}</div>' if desc else ""
        files_html = " ".join(f'<code>{_html.escape(Path(f).name)}</code>' for f in m["key_files"][:5])
        dep_links = []
        for dep_id, weight in list(m["deps"].items())[:3]:
            if dep_id in module_map:
                dn = _html.escape(module_map[dep_id]["name"])
                dep_links.append(f'<a onclick="document.getElementById(\'module-{dep_id}\').scrollIntoView({{behavior:\'smooth\',block:\'center\'}})">{dn}</a> ({weight})')
        deps_html = f'<div class="deps">\u2192 {", ".join(dep_links)}</div>' if dep_links else ""
        top_str = ", ".join(_html.escape(label) for label, _ in m["top_nodes"][:3])
        ne = _html.escape(m["name"])
        cards.append(f'<div class="module-card" id="module-{m["id"]}">'
                     f'<div class="name"><span class="dot" style="background:{color}"></span>{ne}</div>'
                     f'{desc_html}'
                     f'<div class="meta">{m["node_count"]} nodes \u00b7 {m["file_count"]} files \u00b7 Top: {top_str}</div>'
                     f'<div class="files">{files_html}</div>'
                     f'{deps_html}</div>')

    ri = []
    for item in reading_order:
        m = item["module"]
        ri.append(f'<li><strong>{_html.escape(m["name"])}</strong> '
                   f'<span class="reason">\u2014 {_html.escape(item["reason"])}</span></li>')

    pn = _html.escape(project_name)
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1.0">'
            f'<title>{pn} \u2014 Architecture Dashboard</title>{_dashboard_css()}</head><body>'
            f'<div class="container">'
            f'<div class="header"><h1>{pn}</h1>'
            f'<div class="subtitle">Architecture Dashboard \u00b7 Generated by Graphify</div></div>'
            f'<div class="stats">'
            f'<div class="stat-card"><div class="value">{n_modules}</div><div class="label">Modules</div></div>'
            f'<div class="stat-card"><div class="value">{total_files}</div><div class="label">Files</div></div>'
            f'<div class="stat-card"><div class="value">{total_nodes:,}</div><div class="label">Nodes</div></div>'
            f'<div class="stat-card"><div class="value">{total_edges:,}</div><div class="label">Edges</div></div>'
            f'</div>'
            f'<div class="section-title">Architecture Overview</div><div id="graph-container">{graph_parts["mermaid_div"]}</div><div class="section-title">Module Relationships (Interactive)</div><div id="force-graph-container"></div>'
            f'<div class="section-title">Modules</div>'
            f'<div class="module-grid">{"".join(cards)}</div>'
            f'{api_html}<div class="section-title">Recommended Reading Order</div>'
            f'<div class="reading-order"><ol>{"".join(ri)}</ol></div>'
            f'<div class="footer"><a href="graph.html">Full Knowledge Graph</a> · <a href="GRAPH_REPORT.md">Graph Report</a> · Generated by <a href="https://graphify.net">Graphify</a></div>'
            f'</div>'
            + graph_parts['scripts']
            + '</body></html>')


def generate_dashboard(graph_path, output_path="graphify-out/dashboard.html",
                       descriptions=None, names=None, project_name=None):
    raw = json.loads(Path(graph_path).read_text())
    try:
        G = json_graph.node_link_graph(raw, edges="links")
    except TypeError:
        G = json_graph.node_link_graph(raw)

    communities = defaultdict(list)
    for nid, data in G.nodes(data=True):
        cid = data.get("community")
        if cid is not None:
            communities[int(cid)].append(nid)
    if not communities:
        communities = {0: list(G.nodes())}

    macros = merge_communities(G, communities)
    modules = _macro_metadata(G, communities, macros)
    for m in modules:
        m["name"] = _infer_module_name(m)
    _deduplicate_names(modules)
    if names:
        for m in modules:
            if m["id"] in names:
                m["name"] = names[m["id"]]
    if descriptions:
        for m in modules:
            if m["id"] in descriptions:
                m["description"] = descriptions[m["id"]]
    if not project_name:
        project_name = Path(graph_path).resolve().parent.parent.name

    # Scan for API endpoints and external services
    all_py_files = []
    for nid, data in G.nodes(data=True):
        sf = data.get("source_file", "")
        if sf and sf.endswith(".py"):
            p = Path(graph_path).resolve().parent.parent / sf
            if p.exists():
                all_py_files.append(str(p))
    all_py_files = sorted(set(all_py_files))
    endpoints = _scan_exposed_endpoints(all_py_files)
    external = _scan_external_calls(all_py_files)

    reading_order = _reading_order(modules)
    api_html = _render_api_section(endpoints, external)
    html = _render_dashboard(project_name, G, modules, reading_order, api_html)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html, encoding="utf-8")
    return {"modules": modules, "macros": macros}
