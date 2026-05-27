from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import networkx as nx
from .models import PRInfo, _STATUS_ORDER
from .github import fetch_pr_files
def _path_match(graph_src: str, pr_file: str) -> bool:
    """True if graph_src and pr_file refer to the same file (path-boundary safe)."""
    if graph_src == pr_file:
        return True
    return graph_src.endswith("/" + pr_file) or pr_file.endswith("/" + graph_src)


def compute_pr_impact(files: list[str], G: "nx.Graph") -> tuple[list[int], int]:
    """Return (communities_touched, nodes_affected) for a set of changed files.

    Builds a file→(communities, count) index first so lookup is O(nodes + files)
    rather than O(nodes × files).
    """
    # Build index once
    file_comms: dict[str, set[int]] = {}
    file_count: dict[str, int] = {}
    for _, data in G.nodes(data=True):
        src = data.get("source_file") or ""
        if not src:
            continue
        if src not in file_comms:
            file_comms[src] = set()
            file_count[src] = 0
        c = data.get("community")
        if c is not None:
            file_comms[src].add(int(c))
        file_count[src] += 1

    comms: set[int] = set()
    nodes = 0
    matched: set[str] = set()
    for f in files:
        for src, src_comms in file_comms.items():
            if src not in matched and _path_match(src, f):
                comms |= src_comms
                nodes += file_count[src]
                matched.add(src)
    return sorted(comms), nodes


def format_prs_text(prs: list["PRInfo"], base: str) -> str:
    """Plain-text PR summary for MCP output (no ANSI)."""
    actionable = [p for p in prs if p.base_branch == base]
    wrong = len(prs) - len(actionable)
    lines = [f"Open PRs targeting {base}: {len(actionable)}  ({wrong} on wrong base, not shown)\n"]
    for p in sorted(actionable, key=lambda x: (_STATUS_ORDER.index(x.status) if x.status in _STATUS_ORDER else 99, x.days_old)):
        impact = f"  blast_radius={p.blast_radius}" if p.blast_radius else ""
        lines.append(
            f"#{p.number} [{p.status}] CI={p.ci_status} review={p.review_decision or 'none'} "
            f"age={p.days_old}d author={p.author}{impact}\n  {p.title}"
        )
    return "\n\n".join(lines)


def _load_graph_json(graph_path: Path) -> dict | None:
    if not graph_path.exists():
        return None
    from graphify.security import check_graph_file_size_cap
    try:
        check_graph_file_size_cap(graph_path)
        return json.loads(graph_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def build_community_labels(data: dict, top_n: int = 4) -> dict[int, list[str]]:
    """Return {community_id: [top_labels]} extracted from graph node data."""
    comm_labels: dict[int, list[str]] = defaultdict(list)
    for node in data.get("nodes", []):
        c = node.get("community")
        if c is None:
            continue
        label = node.get("label") or node.get("id") or ""
        if label:
            comm_labels[int(c)].append(label)
    return {c: labels[:top_n] for c, labels in comm_labels.items()}


def attach_graph_impact(
    prs: list[PRInfo], graph_path: Path, repo: str | None = None
) -> dict[int, list[str]]:
    """Fetch PR file lists concurrently, compute graph impact, return community labels."""
    data = _load_graph_json(graph_path)
    if not data:
        return {}

    # Build file → {community, node_count} index
    file_to_communities: dict[str, set[int]] = {}
    file_to_nodes: dict[str, int] = {}
    for node in data.get("nodes", []):
        src = node.get("source_file") or ""
        if not src:
            continue
        comm = node.get("community")
        if src not in file_to_communities:
            file_to_communities[src] = set()
            file_to_nodes[src] = 0
        if comm is not None:
            file_to_communities[src].add(int(comm))
        file_to_nodes[src] += 1

    # Fetch diffs concurrently — gh pr diff is the bottleneck (network I/O)
    actionable = [pr for pr in prs if pr.status != "WRONG-BASE"]
    workers = min(8, len(actionable)) if actionable else 1
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_pr = {
            pool.submit(fetch_pr_files, pr.number, repo): pr
            for pr in actionable
        }
        for fut in as_completed(future_to_pr):
            pr = future_to_pr[fut]
            try:
                files = fut.result()
            except Exception:
                files = []
            pr.files_changed = files

            comms: set[int] = set()
            nodes = 0
            matched: set[str] = set()
            for f in files:
                for gf, gcomms in file_to_communities.items():
                    if gf not in matched and _path_match(gf, f):
                        comms |= gcomms
                        nodes += file_to_nodes.get(gf, 0)
                        matched.add(gf)
            pr.communities_touched = sorted(comms)
            pr.nodes_affected = nodes

    return build_community_labels(data)


