# graph diff engine — compare two graph.json snapshots
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx
from networkx.readwrite import json_graph

from graphify.analyze import god_nodes
from graphify.cluster import cluster


def _load_graph(path: str | Path) -> nx.Graph:
    """Load a graph.json file into a NetworkX Graph."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data = _canonicalize(data)
    try:
        return json_graph.node_link_graph(data, edges="links")
    except TypeError:
        return json_graph.node_link_graph(data)


def _canonicalize(data: dict) -> dict:
    """Ensure old-format graphs are compatible."""
    if "links" not in data and "edges" in data:
        data = dict(data, links=data.pop("edges"))
    return data


def _node_key(node: dict) -> str:
    return node["id"]


def _edge_key(edge: dict) -> tuple:
    return (edge.get("source"), edge.get("target"), edge.get("relation", ""))


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def diff_graphs(old_path: str | Path, new_path: str | Path) -> dict:
    """Compare two graph.json files and return a structured diff.

    Returns dict with:
      - old_nodes, new_nodes, nodes_added, nodes_removed, nodes_changed
      - old_edges, new_edges, edges_added, edges_removed
      - communities_changed (splits/merges)
      - god_nodes_changed (promoted/demoted)
    """
    old_G = _load_graph(old_path)
    new_G = _load_graph(new_path)

    old_nodes: dict[str, dict] = {n: dict(d) for n, d in old_G.nodes(data=True)}
    new_nodes: dict[str, dict] = {n: dict(d) for n, d in new_G.nodes(data=True)}

    old_node_ids = set(old_nodes.keys())
    new_node_ids = set(new_nodes.keys())

    nodes_added = [dict(new_nodes[nid], id=nid) for nid in (new_node_ids - old_node_ids)]
    nodes_removed = [dict(old_nodes[nid], id=nid) for nid in (old_node_ids - new_node_ids)]
    nodes_changed = []
    for nid in (old_node_ids & new_node_ids):
        old_attrs = old_nodes[nid]
        new_attrs = new_nodes[nid]
        changed = {}
        all_keys = set(old_attrs.keys()) | set(new_attrs.keys())
        for k in all_keys:
            if old_attrs.get(k) != new_attrs.get(k):
                changed[k] = {"old": old_attrs.get(k), "new": new_attrs.get(k)}
        if changed:
            nodes_changed.append({"id": nid, "label": new_attrs.get("label", nid), "changes": changed})

    old_edges_raw = [
        dict(d, source=u, target=v)
        for u, v, d in old_G.edges(data=True)
    ]
    new_edges_raw = [
        dict(d, source=u, target=v)
        for u, v, d in new_G.edges(data=True)
    ]
    old_edge_map = {_edge_key(e): e for e in old_edges_raw}
    new_edge_map = {_edge_key(e): e for e in new_edges_raw}
    old_edge_keys = set(old_edge_map.keys())
    new_edge_keys = set(new_edge_map.keys())

    edges_added = [new_edge_map[k] for k in (new_edge_keys - old_edge_keys)]
    edges_removed = [old_edge_map[k] for k in (old_edge_keys - new_edge_keys)]

    communities_changed = _diff_communities(old_G, new_G)
    god_nodes_changed = _diff_god_nodes(old_G, new_G)

    return {
        "old_nodes": old_G.number_of_nodes(),
        "new_nodes": new_G.number_of_nodes(),
        "nodes_added": nodes_added,
        "nodes_removed": nodes_removed,
        "nodes_changed": nodes_changed,
        "old_edges": old_G.number_of_edges(),
        "new_edges": new_G.number_of_edges(),
        "edges_added": edges_added,
        "edges_removed": edges_removed,
        "communities_changed": communities_changed,
        "god_nodes_changed": god_nodes_changed,
        "schema_version": "0.5.5",
    }


def _existing_communities(G: nx.Graph) -> dict[int, list[str]]:
    """Reconstruct communities from per-node 'community' attributes."""
    out: dict[int, list[str]] = {}
    for nid, data in G.nodes(data=True):
        cid = data.get("community")
        if cid is None:
            continue
        out.setdefault(int(cid), []).append(nid)
    return out


def _diff_communities(old_G: nx.Graph, new_G: nx.Graph,
                         old_communities: dict | None = None,
                         new_communities: dict | None = None) -> list[dict]:
    """Detect community splits and merges using Jaccard similarity.

    Prefers community assignments already stored on the graph (set by
    save() during the original build). Re-running cluster() here was
    non-deterministic — Leiden / Louvain assignments can differ across
    runs, so two diffs of the same pair of files produced different
    splits/merges. Only fall back to fresh clustering if neither graph
    carries community labels.
    """
    if old_communities is None:
        existing = _existing_communities(old_G)
        old_communities = existing if existing else cluster(old_G)
    if new_communities is None:
        existing = _existing_communities(new_G)
        new_communities = existing if existing else cluster(new_G)

    old_sets = {cid: set(nodes) for cid, nodes in old_communities.items()}
    new_sets = {cid: set(nodes) for cid, nodes in new_communities.items()}

    changed: list[dict] = []
    threshold = 0.5

    # Detect splits: one old community → multiple new communities
    for old_cid, old_set in old_sets.items():
        matches = []
        for new_cid, new_set in new_sets.items():
            sim = _jaccard(old_set, new_set)
            if sim >= threshold:
                matches.append((new_cid, sim, new_set))
        if len(matches) > 1:
            changed.append({
                "type": "split",
                "old_community": old_cid,
                "old_size": len(old_set),
                "new_communities": [
                    {"id": cid, "size": len(ns), "jaccard": round(sim, 2)}
                    for cid, sim, ns in sorted(matches, key=lambda x: -x[1])
                ],
            })

    # Detect merges: multiple old communities → one new community
    for new_cid, new_set in new_sets.items():
        matches = []
        for old_cid, old_set in old_sets.items():
            sim = _jaccard(old_set, new_set)
            if sim >= threshold:
                matches.append((old_cid, sim, old_set))
        if len(matches) > 1:
            changed.append({
                "type": "merge",
                "new_community": new_cid,
                "new_size": len(new_set),
                "old_communities": [
                    {"id": cid, "size": len(os), "jaccard": round(sim, 2)}
                    for cid, sim, os in sorted(matches, key=lambda x: -x[1])
                ],
            })

    return changed


def _diff_god_nodes(old_G: nx.Graph, new_G: nx.Graph, top_n: int = 10) -> dict:
    """Compare god node rankings between two graphs."""
    old_gods = {g["id"]: g for g in god_nodes(old_G, top_n)}
    new_gods = {g["id"]: g for g in god_nodes(new_G, top_n)}

    old_set = set(old_gods.keys())
    new_set = set(new_gods.keys())

    promoted = [
        {"id": nid, "label": new_gods[nid]["label"], "degree": new_gods[nid]["degree"]}
        for nid in (new_set - old_set)
    ]
    demoted = [
        {"id": nid, "label": old_gods[nid]["label"], "degree": old_gods[nid]["degree"]}
        for nid in (old_set - new_set)
    ]
    stable = []
    for nid in (old_set & new_set):
        old_deg = old_gods[nid]["degree"]
        new_deg = new_gods[nid]["degree"]
        if old_deg != new_deg:
            stable.append({
                "id": nid,
                "label": new_gods[nid]["label"],
                "old_degree": old_deg,
                "new_degree": new_deg,
                "delta": new_deg - old_deg,
            })

    return {
        "old_gods": list(old_gods.values()),
        "new_gods": list(new_gods.values()),
        "promoted": promoted,
        "demoted": demoted,
        "changed": stable,
    }


def render_diff(diff: dict, fmt: str = "markdown") -> str:
    """Render a diff dict as markdown or json."""
    if fmt == "json":
        return json.dumps(diff, indent=2)

    lines: list[str] = [
        "# Graph Diff Report",
        "",
        "## Summary",
        f"- Nodes: {diff['old_nodes']} → {diff['new_nodes']} ({diff['new_nodes'] - diff['old_nodes']:+,})",
        f"- Edges: {diff['old_edges']} → {diff['new_edges']} ({diff['new_edges'] - diff['old_edges']:+,})",
        "",
    ]

    # Nodes
    lines += ["## Nodes", ""]
    if diff["nodes_added"]:
        lines.append(f"### Added ({len(diff['nodes_added'])})")
        for n in diff["nodes_added"][:20]:
            lines.append(f"- `{n['id']}` — {n.get('label', '')}")
        if len(diff["nodes_added"]) > 20:
            lines.append(f"- ... and {len(diff['nodes_added']) - 20} more")
        lines.append("")
    if diff["nodes_removed"]:
        lines.append(f"### Removed ({len(diff['nodes_removed'])})")
        for n in diff["nodes_removed"][:20]:
            lines.append(f"- `{n['id']}` — {n.get('label', '')}")
        if len(diff["nodes_removed"]) > 20:
            lines.append(f"- ... and {len(diff['nodes_removed']) - 20} more")
        lines.append("")
    if diff["nodes_changed"]:
        lines.append(f"### Changed ({len(diff['nodes_changed'])})")
        for n in diff["nodes_changed"][:20]:
            changed_keys = ", ".join(n["changes"].keys())
            lines.append(f"- `{n['id']}` — changed: {changed_keys}")
        if len(diff["nodes_changed"]) > 20:
            lines.append(f"- ... and {len(diff['nodes_changed']) - 20} more")
        lines.append("")

    # Edges
    lines += ["## Edges", ""]
    if diff["edges_added"]:
        lines.append(f"### Added ({len(diff['edges_added'])})")
        for e in diff["edges_added"][:20]:
            lines.append(f"- `{e['source']}` --{e.get('relation', '')}--> `{e['target']}`")
        if len(diff["edges_added"]) > 20:
            lines.append(f"- ... and {len(diff['edges_added']) - 20} more")
        lines.append("")
    if diff["edges_removed"]:
        lines.append(f"### Removed ({len(diff['edges_removed'])})")
        for e in diff["edges_removed"][:20]:
            lines.append(f"- `{e['source']}` --{e.get('relation', '')}--> `{e['target']}`")
        if len(diff["edges_removed"]) > 20:
            lines.append(f"- ... and {len(diff['edges_removed']) - 20} more")
        lines.append("")

    # Communities
    if diff["communities_changed"]:
        lines += ["## Communities", ""]
        for c in diff["communities_changed"]:
            if c["type"] == "split":
                lines.append(f"### Split: Community {c['old_community']} ({c['old_size']} nodes)")
                for nc in c["new_communities"]:
                    lines.append(f"- → Community {nc['id']} ({nc['size']} nodes, Jaccard {nc['jaccard']})")
            elif c["type"] == "merge":
                lines.append(f"### Merge: Community {c['new_community']} ({c['new_size']} nodes)")
                for oc in c["old_communities"]:
                    lines.append(f"- ← Community {oc['id']} ({oc['size']} nodes, Jaccard {oc['jaccard']})")
        lines.append("")

    # God nodes
    gods = diff["god_nodes_changed"]
    lines += ["## God Nodes", ""]
    if gods["promoted"]:
        lines.append(f"### Promoted ({len(gods['promoted'])})")
        for g in gods["promoted"]:
            lines.append(f"- `{g['label']}` — {g['degree']} edges")
        lines.append("")
    if gods["demoted"]:
        lines.append(f"### Demoted ({len(gods['demoted'])})")
        for g in gods["demoted"]:
            lines.append(f"- `{g['label']}` — {g['degree']} edges")
        lines.append("")
    if gods["changed"]:
        lines.append(f"### Degree Changed ({len(gods['changed'])})")
        for g in gods["changed"]:
            lines.append(f"- `{g['label']}` — {g['old_degree']} → {g['new_degree']} ({g['delta']:+,})")
        lines.append("")

    return "\n".join(lines)
