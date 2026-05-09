# SQLite backend for graphify graphs.
#
# Mirrors graph.json semantics 1:1 — load_db(save_db(G)) is structurally
# equivalent to G round-tripped through to_json + build_from_json.
# Edge direction is preserved via _src/_tgt attributes the same way the JSON
# loader preserves it (NetworkX undirected Graph canonicalizes endpoint order).
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import networkx as nx

from graphify.analyze import _node_community_map
from graphify.export import _strip_diacritics


SCHEMA_VERSION = 1


_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS nodes (
    id              TEXT PRIMARY KEY,
    label           TEXT,
    file_type       TEXT,
    source_file     TEXT,
    source_location TEXT,
    source_url      TEXT,
    captured_at     TEXT,
    author          TEXT,
    contributor     TEXT,
    community       INTEGER,
    norm_label      TEXT,
    attrs           TEXT
);
CREATE INDEX IF NOT EXISTS nodes_source_file ON nodes(source_file);
CREATE INDEX IF NOT EXISTS nodes_community   ON nodes(community);
CREATE INDEX IF NOT EXISTS nodes_norm_label  ON nodes(norm_label);

CREATE TABLE IF NOT EXISTS edges (
    src              TEXT NOT NULL,
    dst              TEXT NOT NULL,
    relation         TEXT,
    confidence       TEXT,
    confidence_score REAL,
    source_file      TEXT,
    source_location  TEXT,
    weight           REAL,
    attrs            TEXT,
    FOREIGN KEY(src) REFERENCES nodes(id) ON DELETE CASCADE,
    FOREIGN KEY(dst) REFERENCES nodes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS edges_src         ON edges(src);
CREATE INDEX IF NOT EXISTS edges_dst         ON edges(dst);
CREATE INDEX IF NOT EXISTS edges_source_file ON edges(source_file);

CREATE TABLE IF NOT EXISTS hyperedges (
    id               TEXT PRIMARY KEY,
    label            TEXT,
    relation         TEXT,
    confidence       TEXT,
    confidence_score REAL,
    source_file      TEXT,
    attrs            TEXT
);

CREATE TABLE IF NOT EXISTS hyperedge_members (
    hid     TEXT,
    node_id TEXT,
    FOREIGN KEY(hid)     REFERENCES hyperedges(id) ON DELETE CASCADE,
    FOREIGN KEY(node_id) REFERENCES nodes(id)      ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS hyperedge_members_hid ON hyperedge_members(hid);
"""


# Columns with their own typed slots — anything else spills into the JSON `attrs` blob.
_NODE_TYPED = {
    "id", "label", "file_type", "source_file", "source_location",
    "source_url", "captured_at", "author", "contributor", "community", "norm_label",
}
_EDGE_TYPED = {
    "source", "target", "relation", "confidence", "confidence_score",
    "source_file", "source_location", "weight", "_src", "_tgt",
}
_HE_TYPED = {
    "id", "label", "nodes", "relation", "confidence",
    "confidence_score", "source_file",
}


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )
    return conn


def _norm_label(label: str | None) -> str:
    return _strip_diacritics(label or "").lower()


def _count_nodes(path: Path) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    finally:
        conn.close()


def save_db(
    path: str | Path,
    G: nx.Graph,
    communities: dict[int, list[str]] | None,
    *,
    force: bool = False,
    built_at_commit: str | None = None,
) -> bool:
    """Persist G + communities to SQLite. Mirrors export.to_json safety contract:
    refuses to silently shrink an existing graph unless force=True."""
    path = Path(path)
    if path.exists() and not force:
        try:
            existing_n = _count_nodes(path)
            new_n = G.number_of_nodes()
            if new_n < existing_n:
                print(
                    f"[graphify] WARNING: new graph has {new_n} nodes but existing "
                    f"graph.db has {existing_n}. Refusing to overwrite — pass "
                    f"force=True to override.",
                    file=sys.stderr,
                )
                return False
        except sqlite3.DatabaseError:
            pass  # corrupt/empty existing db — proceed with rewrite

    node_community = _node_community_map(communities or {})
    conn = _connect(path)
    try:
        with conn:
            conn.execute("DELETE FROM hyperedge_members")
            conn.execute("DELETE FROM hyperedges")
            conn.execute("DELETE FROM edges")
            conn.execute("DELETE FROM nodes")
            for node_id, attrs in G.nodes(data=True):
                _insert_node(conn, node_id, attrs, node_community.get(node_id))
            for u, v, attrs in G.edges(data=True):
                _insert_edge(conn, u, v, attrs)
            for he in G.graph.get("hyperedges", []) or []:
                _insert_hyperedge(conn, he)

            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('directed', ?)",
                ("1" if G.is_directed() else "0",),
            )
            commit = built_at_commit
            if commit is None:
                # mirror to_json: only stamp if caller didn't pass an explicit value
                commit = G.graph.get("built_at_commit")
            if commit:
                conn.execute(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES ('built_at_commit', ?)",
                    (commit,),
                )
    finally:
        conn.close()
    return True


def _insert_node(conn, node_id, attrs, community):
    norm = attrs.get("norm_label") or _norm_label(attrs.get("label"))
    extra = {k: v for k, v in attrs.items() if k not in _NODE_TYPED}
    conn.execute(
        """INSERT INTO nodes(
            id, label, file_type, source_file, source_location,
            source_url, captured_at, author, contributor,
            community, norm_label, attrs)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            node_id,
            attrs.get("label"),
            attrs.get("file_type"),
            attrs.get("source_file"),
            attrs.get("source_location"),
            attrs.get("source_url"),
            attrs.get("captured_at"),
            attrs.get("author"),
            attrs.get("contributor"),
            community if community is not None else attrs.get("community"),
            norm,
            json.dumps(extra) if extra else None,
        ),
    )


def _insert_edge(conn, u, v, attrs):
    # _src/_tgt carry the true source/target for undirected graphs whose edge
    # storage may have canonicalized endpoint order; fall back to u/v for directed.
    src = attrs.get("_src", u)
    dst = attrs.get("_tgt", v)
    extra = {k: v for k, v in attrs.items() if k not in _EDGE_TYPED}
    conn.execute(
        """INSERT INTO edges(
            src, dst, relation, confidence, confidence_score,
            source_file, source_location, weight, attrs)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            src,
            dst,
            attrs.get("relation"),
            attrs.get("confidence"),
            attrs.get("confidence_score"),
            attrs.get("source_file"),
            attrs.get("source_location"),
            attrs.get("weight"),
            json.dumps(extra) if extra else None,
        ),
    )


def _insert_hyperedge(conn, he):
    extra = {k: v for k, v in he.items() if k not in _HE_TYPED}
    hid = he.get("id")
    conn.execute(
        """INSERT OR REPLACE INTO hyperedges(
            id, label, relation, confidence, confidence_score, source_file, attrs)
           VALUES (?,?,?,?,?,?,?)""",
        (
            hid,
            he.get("label"),
            he.get("relation"),
            he.get("confidence"),
            he.get("confidence_score"),
            he.get("source_file"),
            json.dumps(extra) if extra else None,
        ),
    )
    conn.execute("DELETE FROM hyperedge_members WHERE hid = ?", (hid,))
    for member in he.get("nodes", []) or []:
        conn.execute(
            "INSERT INTO hyperedge_members(hid, node_id) VALUES (?, ?)",
            (hid, member),
        )


def load_db(path: str | Path) -> nx.Graph:
    """Reconstruct a NetworkX graph from graph.db.

    Returns a Graph or DiGraph matching what was saved. Edge attributes include
    `_src`/`_tgt` so a subsequent save preserves true direction even if the
    in-memory undirected Graph canonicalizes endpoint order.
    """
    path = Path(path)
    conn = _connect(path)
    try:
        directed_row = conn.execute(
            "SELECT value FROM meta WHERE key='directed'"
        ).fetchone()
        directed = bool(directed_row) and directed_row[0] == "1"
        G: nx.Graph = nx.DiGraph() if directed else nx.Graph()

        for row in conn.execute(
            """SELECT id, label, file_type, source_file, source_location,
                      source_url, captured_at, author, contributor,
                      community, norm_label, attrs FROM nodes"""
        ):
            (id_, label, ft, sf, sl, su, ca, au, co, com, norm, attrs_json) = row
            attrs = {
                "label": label,
                "file_type": ft,
                "source_file": sf,
                "source_location": sl,
                "source_url": su,
                "captured_at": ca,
                "author": au,
                "contributor": co,
                "community": com,
                "norm_label": norm,
            }
            attrs = {k: v for k, v in attrs.items() if v is not None}
            if attrs_json:
                attrs.update(json.loads(attrs_json))
            G.add_node(id_, **attrs)

        for row in conn.execute(
            """SELECT src, dst, relation, confidence, confidence_score,
                      source_file, source_location, weight, attrs FROM edges"""
        ):
            (src, dst, rel, conf, score, sf, sl, w, attrs_json) = row
            attrs = {
                "relation": rel,
                "confidence": conf,
                "confidence_score": score,
                "source_file": sf,
                "source_location": sl,
                "weight": w,
                "_src": src,
                "_tgt": dst,
            }
            attrs = {k: v for k, v in attrs.items() if v is not None}
            if attrs_json:
                attrs.update(json.loads(attrs_json))
            G.add_edge(src, dst, **attrs)

        hyperedges: list[dict] = []
        for row in conn.execute(
            """SELECT id, label, relation, confidence, confidence_score,
                      source_file, attrs FROM hyperedges"""
        ):
            (hid, label, rel, conf, score, sf, attrs_json) = row
            members = [
                r[0]
                for r in conn.execute(
                    "SELECT node_id FROM hyperedge_members WHERE hid = ?", (hid,)
                )
            ]
            he = {
                "id": hid,
                "label": label,
                "relation": rel,
                "confidence": conf,
                "confidence_score": score,
                "source_file": sf,
                "nodes": members,
            }
            he = {k: v for k, v in he.items() if v is not None and v != []}
            he["nodes"] = members  # always present, even if empty
            if attrs_json:
                he.update(json.loads(attrs_json))
            hyperedges.append(he)
        if hyperedges:
            G.graph["hyperedges"] = hyperedges

        commit_row = conn.execute(
            "SELECT value FROM meta WHERE key='built_at_commit'"
        ).fetchone()
        if commit_row:
            G.graph["built_at_commit"] = commit_row[0]
    finally:
        conn.close()
    return G


def apply_update(
    path: str | Path,
    new_extraction: dict,
    deleted_files: list[str] | None = None,
) -> nx.Graph:
    """Merge new_extraction into the persisted graph.db. Mirrors the JSON
    update flow: load, prune nodes from deleted files, merge new graph, return
    the merged in-memory graph. Caller is responsible for save_db() after."""
    from graphify.build import build_from_json

    G = load_db(path)
    if deleted_files:
        deleted = set(deleted_files)
        to_remove = [
            n for n, d in G.nodes(data=True) if d.get("source_file") in deleted
        ]
        G.remove_nodes_from(to_remove)
    G_new = build_from_json(new_extraction)
    G.update(G_new)
    return G


def get_node(path: str | Path, node_id: str) -> dict | None:
    conn = _connect(Path(path))
    try:
        row = conn.execute(
            """SELECT id, label, file_type, source_file, source_location,
                      source_url, captured_at, author, contributor,
                      community, norm_label, attrs FROM nodes WHERE id = ?""",
            (node_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    (id_, label, ft, sf, sl, su, ca, au, co, com, norm, attrs_json) = row
    out = {
        "id": id_,
        "label": label,
        "file_type": ft,
        "source_file": sf,
        "source_location": sl,
        "source_url": su,
        "captured_at": ca,
        "author": au,
        "contributor": co,
        "community": com,
        "norm_label": norm,
    }
    out = {k: v for k, v in out.items() if v is not None}
    if attrs_json:
        out.update(json.loads(attrs_json))
    return out


def search_label(path: str | Path, query: str, limit: int = 100) -> list[dict]:
    """Substring search by label, case + diacritics insensitive (uses norm_label)."""
    needle = _norm_label(query)
    if not needle:
        return []
    pattern = f"%{needle}%"
    conn = _connect(Path(path))
    try:
        rows = conn.execute(
            """SELECT id, label, file_type, source_file, community
               FROM nodes WHERE norm_label LIKE ? LIMIT ?""",
            (pattern, limit),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r[0],
            "label": r[1],
            "file_type": r[2],
            "source_file": r[3],
            "community": r[4],
        }
        for r in rows
    ]
