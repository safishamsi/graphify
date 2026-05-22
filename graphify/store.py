# Backend dispatcher: routes graph persistence to graph.json or graph.db.
#
# Both backends share semantics — load() returns a NetworkX graph
# indistinguishable (for graphify's purposes) from one round-tripped through
# to_json + build_from_json. Existence of graph.json or graph.db in
# graphify-out/ selects the backend; both present is a hard error.
#
# Slice 1: this module is self-contained. No existing call sites import it
# yet; the wiring happens in slice 2.
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import networkx as nx
from networkx.readwrite import json_graph

from graphify import db as _db
from graphify.build import build_from_json
from graphify.export import to_json


Backend = Literal["json", "db", "both", "none"]

_JSON_NAME = "graph.json"
_DB_NAME = "graph.db"


def detect_backend(out_dir: str | Path) -> Backend:
    out = Path(out_dir)
    has_json = (out / _JSON_NAME).exists()
    has_db = (out / _DB_NAME).exists()
    if has_json and has_db:
        return "both"
    if has_db:
        return "db"
    if has_json:
        return "json"
    return "none"


def _resolve(out_dir: str | Path, *, allow_none: bool = False) -> Backend:
    b = detect_backend(out_dir)
    if b == "both":
        raise RuntimeError(
            f"Both graph.json and graph.db exist in {out_dir!s}. "
            "Only one backend is supported per knowledge base — delete one or "
            "migrate explicitly."
        )
    if b == "none" and not allow_none:
        raise FileNotFoundError(
            f"No graph found in {out_dir!s} (neither graph.json nor graph.db)."
        )
    return b


def load(out_dir: str | Path) -> nx.Graph:
    out = Path(out_dir)
    backend = _resolve(out)
    if backend == "db":
        return _db.load_db(out / _DB_NAME)
    return _load_json(out / _JSON_NAME)


def load_with_communities(out_dir: str | Path) -> tuple[nx.Graph, dict[int, list[str]]]:
    """Load graph and reconstruct communities dict from node attributes."""
    G = load(out_dir)
    communities: dict[int, list[str]] = {}
    for nid, attrs in G.nodes(data=True):
        cid = attrs.get("community")
        if cid is not None:
            communities.setdefault(int(cid), []).append(nid)
    return G, communities


def load_path(path: str | Path) -> nx.Graph:
    """Load from a directory (auto-dispatch) or an explicit file path.

    Used by CLI handlers that accept --graph <path>: a directory triggers
    backend detection; a file path uses the suffix (.db or .json) directly.
    """
    p = Path(path)
    if p.is_dir():
        return load(p)
    if p.suffix == ".db":
        return _db.load_db(p)
    return _load_json(p)


def to_extraction(out_dir: str | Path) -> dict:
    """Return the persisted graph in extraction shape: {nodes, edges, hyperedges}.

    Used by callers (e.g. watch.py) that need to merge the persisted graph
    with a fresh AST extraction at the dict level rather than the NetworkX level.
    """
    out = Path(out_dir)
    backend = _resolve(out)
    if backend == "json":
        data = json.loads((out / _JSON_NAME).read_text(encoding="utf-8"))
        return {
            "nodes": data.get("nodes", []),
            "edges": data.get("links", data.get("edges", [])),
            "hyperedges": data.get("hyperedges", []),
        }
    G = _db.load_db(out / _DB_NAME)
    nodes = [
        {"id": nid, **{k: v for k, v in attrs.items() if k != "id"}}
        for nid, attrs in G.nodes(data=True)
    ]
    edges = []
    for u, v, attrs in G.edges(data=True):
        e = {"source": attrs.get("_src", u), "target": attrs.get("_tgt", v)}
        e.update({k: val for k, val in attrs.items() if k not in ("_src", "_tgt")})
        edges.append(e)
    return {
        "nodes": nodes,
        "edges": edges,
        "hyperedges": G.graph.get("hyperedges", []),
    }


def save(
    out_dir: str | Path,
    G: nx.Graph,
    communities: dict[int, list[str]] | None,
    *,
    backend: Backend | None = None,
    force: bool = False,
    built_at_commit: str | None = None,
) -> bool:
    """Persist G + communities. If backend is None, use the existing artifact
    in out_dir; default to JSON on a fresh directory.

    Refuses to write a backend that disagrees with an existing artifact —
    use migrate() for explicit conversions.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    existing = detect_backend(out)
    if existing == "both":
        _resolve(out)  # raises
    if backend is not None and existing in ("json", "db") and backend != existing:
        raise RuntimeError(
            f"Backend mismatch: requested {backend!r} but {existing!r} already "
            f"exists in {out!s}. Run 'graphify migrate-store --to {backend}' to "
            f"convert, or delete the existing artifact."
        )
    if backend is None:
        backend = existing if existing in ("json", "db") else "json"
    if backend == "db":
        return _db.save_db(
            out / _DB_NAME, G, communities or {},
            force=force, built_at_commit=built_at_commit,
        )
    return to_json(
        G, communities or {}, str(out / _JSON_NAME),
        force=force, built_at_commit=built_at_commit,
    )


def migrate(out_dir: str | Path, to: Backend) -> tuple[Backend, Backend]:
    """Convert the persisted graph between backends.

    Validates the round-trip (node-set equality) before deleting the source.
    Returns (source_backend, target_backend). No-op if already on `to`.
    """
    if to not in ("json", "db"):
        raise ValueError(f"target backend must be 'json' or 'db', got {to!r}")
    out = Path(out_dir)
    src_backend = _resolve(out)
    if src_backend == to:
        return (src_backend, to)

    G = load(out)
    communities: dict[int, list[str]] = {}
    for nid, attrs in G.nodes(data=True):
        cid = attrs.get("community")
        if cid is not None:
            communities.setdefault(int(cid), []).append(nid)

    if to == "db":
        _db.save_db(out / _DB_NAME, G, communities, force=True)
        check = _db.load_db(out / _DB_NAME)
    else:
        to_json(G, communities, str(out / _JSON_NAME), force=True)
        check = _load_json(out / _JSON_NAME)

    if set(check.nodes) != set(G.nodes):
        raise RuntimeError(
            "migration validation failed: target backend node set differs from source"
        )
    src_path = out / (_JSON_NAME if src_backend == "json" else _DB_NAME)
    src_path.unlink()
    return (src_backend, to)


def backup_path(out_dir: str | Path, backup_name: str = ".graphify_old") -> Path | None:
    """Return path to a backup copy of the persisted graph for the current
    backend, or None if neither .db nor .json backup exists."""
    out = Path(out_dir)
    for ext in (".db", ".json"):
        p = out / f"{backup_name}{ext}"
        if p.exists():
            return p
    return None


def make_backup(out_dir: str | Path, backup_name: str = ".graphify_old") -> Path:
    """Copy the current persisted graph to a backup file matching its backend.
    Returns the backup path."""
    import shutil
    out = Path(out_dir)
    backend = _resolve(out)
    src = out / (_DB_NAME if backend == "db" else _JSON_NAME)
    dst = out / f"{backup_name}{src.suffix}"
    shutil.copy2(src, dst)
    return dst


def remove_backup(out_dir: str | Path, backup_name: str = ".graphify_old") -> None:
    out = Path(out_dir)
    for ext in (".db", ".json"):
        p = out / f"{backup_name}{ext}"
        if p.exists():
            p.unlink()


def artifact_name(out_dir: str | Path) -> str:
    """Return 'graph.db' or 'graph.json' based on which exists in out_dir.
    Defaults to 'graph.json' when neither is present (fresh-build case)."""
    out = Path(out_dir)
    return _DB_NAME if (out / _DB_NAME).exists() else _JSON_NAME


def build_merge_compat(
    new_chunks: list[dict],
    out_dir: str | Path,
    *,
    prune_sources: list[str] | None = None,
    directed: bool = False,
    dedup: bool = True,
    dedup_llm_backend: str | None = None,
) -> nx.Graph:
    """Backend-aware wrapper for build.build_merge.

    For DB-backed KBs, loads the existing graph as an extraction dict, prepends
    it to new_chunks, then runs build() — same end state as build_merge() does
    for JSON-backed KBs. Falls back to build_merge() for JSON.
    """
    from graphify.build import build, build_merge
    out = Path(out_dir)
    backend = detect_backend(out)
    if backend == "db":
        from graphify.build import build as _build
        existing = to_extraction(out)
        all_chunks = [existing] + list(new_chunks)
        G = _build(
            all_chunks,
            directed=directed,
            dedup=dedup,
            dedup_llm_backend=dedup_llm_backend,
        )
        if prune_sources:
            to_remove = [
                n for n, d in G.nodes(data=True)
                if d.get("source_file") in prune_sources
            ]
            G.remove_nodes_from(to_remove)
        return G
    return build_merge(
        new_chunks,
        graph_path=out / _JSON_NAME,
        prune_sources=prune_sources,
        directed=directed,
        dedup=dedup,
        dedup_llm_backend=dedup_llm_backend,
    )


def apply_update(
    out_dir: str | Path,
    new_extraction: dict,
    deleted_files: list[str] | None = None,
) -> nx.Graph:
    """Merge new_extraction into the persisted graph and return the merged
    in-memory graph. Caller is responsible for save() after re-clustering."""
    out = Path(out_dir)
    backend = _resolve(out)
    if backend == "db":
        return _db.apply_update(out / _DB_NAME, new_extraction, deleted_files or [])
    return _apply_update_json(out / _JSON_NAME, new_extraction, deleted_files or [])


def get_node(out_dir: str | Path, node_id: str) -> dict | None:
    out = Path(out_dir)
    backend = _resolve(out)
    if backend == "db":
        return _db.get_node(out / _DB_NAME, node_id)
    G = _load_json(out / _JSON_NAME)
    if node_id not in G.nodes:
        return None
    return {"id": node_id, **G.nodes[node_id]}


def search_label(out_dir: str | Path, query: str, limit: int = 100) -> list[dict]:
    out = Path(out_dir)
    backend = _resolve(out)
    if backend == "db":
        return _db.search_label(out / _DB_NAME, query, limit=limit)
    needle = query.lower()
    if not needle:
        return []
    G = _load_json(out / _JSON_NAME)
    results: list[dict] = []
    for n, attrs in G.nodes(data=True):
        if needle in str(attrs.get("label", "")).lower() or needle in str(
            attrs.get("norm_label", "")
        ).lower():
            results.append({
                "id": n,
                "label": attrs.get("label"),
                "file_type": attrs.get("file_type"),
                "source_file": attrs.get("source_file"),
                "community": attrs.get("community"),
            })
            if len(results) >= limit:
                break
    return results


def search(out_dir: str | Path, query: str, limit: int = 20) -> list[dict]:
    """FTS5 ranked search. Falls back to scored substring matching for JSON backend."""
    out = Path(out_dir)
    backend = _resolve(out)
    if backend == "db":
        return _db.search(out / _DB_NAME, query, limit=limit)
    # JSON fallback: score against label + description + source_file
    terms = query.lower().split()
    if not terms:
        return []
    G = _load_json(out / _JSON_NAME)
    scored: list[tuple[float, str, dict]] = []
    for n, attrs in G.nodes(data=True):
        label = (attrs.get("label") or "").lower()
        desc = (attrs.get("description") or "").lower()
        sf = (attrs.get("source_file") or "").lower()
        score = (sum(1.0 for t in terms if t in label)
                 + sum(1.5 for t in terms if t in desc)
                 + sum(0.5 for t in terms if t in sf))
        if score > 0:
            scored.append((score, n, attrs))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "id": nid,
            "label": attrs.get("label", ""),
            "description": attrs.get("description", ""),
            "source_file": attrs.get("source_file", ""),
            "community": attrs.get("community"),
            "score": round(s, 4),
        }
        for s, nid, attrs in scored[:limit]
    ]


# ---- JSON backend internals (no edits to export.py / build.py required) ----

def _load_json(path: Path) -> nx.Graph:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "edges" in data and "links" not in data:
        data = dict(data, links=data["edges"])
    G = json_graph.node_link_graph(data, edges="links")
    if data.get("hyperedges"):
        G.graph["hyperedges"] = data["hyperedges"]
    if data.get("built_at_commit"):
        G.graph["built_at_commit"] = data["built_at_commit"]
    return G


def _apply_update_json(
    path: Path, new_extraction: dict, deleted_files: list[str]
) -> nx.Graph:
    G = _load_json(path)
    if deleted_files:
        deleted = set(deleted_files)
        to_remove = [
            n for n, d in G.nodes(data=True) if d.get("source_file") in deleted
        ]
        G.remove_nodes_from(to_remove)
    G_new = build_from_json(new_extraction)
    G.update(G_new)
    return G
