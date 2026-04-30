# Graph storage abstraction — MemoryStore (JSON) and SQLiteStore (sqlite3)
from __future__ import annotations

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import networkx as nx
from networkx.readwrite import json_graph

from graphify.schema import upgrade_graph, SCHEMA_VERSION


class GraphStore(ABC):
    """Abstract base class for graph persistence backends."""

    @abstractmethod
    def save(self, G: nx.Graph, communities: dict[int, list[str]], metadata: dict | None = None) -> None:
        """Persist a NetworkX graph with community assignments."""
        ...

    @abstractmethod
    def load(self) -> tuple[nx.Graph, dict[int, list[str]], dict]:
        """Load graph, communities, and metadata."""
        ...

    @abstractmethod
    def query_nodes(
        self,
        label: str | None = None,
        file_type: str | None = None,
        community: int | None = None,
        limit: int = 100,
    ) -> list[dict]:
        ...

    @abstractmethod
    def query_edges(
        self,
        source: str | None = None,
        target: str | None = None,
        relation: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        ...

    @abstractmethod
    def get_neighbors(self, node_id: str, relation: str | None = None) -> list[dict]:
        ...

    @abstractmethod
    def get_stats(self) -> dict:
        ...

    @abstractmethod
    def search_nodes(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text search over node labels (backend-dependent quality)."""
        ...


# ---------------------------------------------------------------------------
# MemoryStore — wraps the current JSON-on-disk approach
# ---------------------------------------------------------------------------

class MemoryStore(GraphStore):
    """In-memory graph backed by a JSON file."""

    def __init__(self, graph_path: str = "graphify-out/graph.json") -> None:
        self.graph_path = Path(graph_path)
        self._G: nx.Graph | None = None
        self._communities: dict[int, list[str]] | None = None
        self._metadata: dict = {}

    def _load_if_needed(self) -> None:
        if self._G is not None:
            return
        if not self.graph_path.exists():
            self._G = nx.Graph()
            self._communities = {}
            self._metadata = {}
            return
        data = json.loads(self.graph_path.read_text(encoding="utf-8"))
        data = upgrade_graph(data)
        try:
            self._G = json_graph.node_link_graph(data, edges="links")
        except TypeError:
            self._G = json_graph.node_link_graph(data)
        self._metadata = dict(data.get("graph", {}))
        self._communities = self._reconstruct_communities(data)

    def _reconstruct_communities(self, data: dict) -> dict[int, list[str]]:
        communities: dict[int, list[str]] = {}
        for node in data.get("nodes", []):
            cid = node.get("community")
            if cid is not None:
                communities.setdefault(int(cid), []).append(node["id"])
        return communities

    def save(self, G: nx.Graph, communities: dict[int, list[str]], metadata: dict | None = None) -> None:
        self._G = G
        self._communities = communities
        self._metadata = metadata or {}
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        # Set community attributes on nodes before serializing
        node_community = {n: cid for cid, nodes in communities.items() for n in nodes}
        for nid in G.nodes:
            G.nodes[nid]["community"] = node_community.get(nid)
        try:
            data = json_graph.node_link_data(G, edges="links")
        except TypeError:
            data = json_graph.node_link_data(G)
        data["graph"] = dict(self._metadata, schema_version=SCHEMA_VERSION)
        self.graph_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self) -> tuple[nx.Graph, dict[int, list[str]], dict]:
        self._load_if_needed()
        assert self._G is not None
        return self._G, self._communities or {}, self._metadata

    def query_nodes(
        self,
        label: str | None = None,
        file_type: str | None = None,
        community: int | None = None,
        limit: int = 100,
    ) -> list[dict]:
        self._load_if_needed()
        results = []
        for nid, data in self._G.nodes(data=True):  # type: ignore[union-attr]
            d = dict(data, id=nid)
            if label and label.lower() not in d.get("label", "").lower():
                continue
            if file_type and d.get("file_type") != file_type:
                continue
            if community is not None and d.get("community") != community:
                continue
            results.append(d)
            if len(results) >= limit:
                break
        return results

    def query_edges(
        self,
        source: str | None = None,
        target: str | None = None,
        relation: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        self._load_if_needed()
        results = []
        for u, v, data in self._G.edges(data=True):  # type: ignore[union-attr]
            if source and u != source:
                continue
            if target and v != target:
                continue
            if relation and data.get("relation") != relation:
                continue
            results.append(dict(data, source=u, target=v))
            if len(results) >= limit:
                break
        return results

    def get_neighbors(self, node_id: str, relation: str | None = None) -> list[dict]:
        self._load_if_needed()
        if node_id not in self._G:  # type: ignore[operator]
            return []
        results = []
        for neighbor in self._G.neighbors(node_id):  # type: ignore[union-attr]
            data = self._G.nodes[neighbor]  # type: ignore[index]
            if relation:
                edge_data = self._G.edges[node_id, neighbor]  # type: ignore[index]
                if edge_data.get("relation") != relation:
                    continue
            results.append(dict(data, id=neighbor))
        return results

    def get_stats(self) -> dict:
        self._load_if_needed()
        return {
            "nodes": self._G.number_of_nodes(),  # type: ignore[union-attr]
            "edges": self._G.number_of_edges(),  # type: ignore[union-attr]
            "communities": len(self._communities or {}),
            "schema_version": self._metadata.get("schema_version"),
        }

    def search_nodes(self, query: str, limit: int = 20) -> list[dict]:
        return self.query_nodes(label=query, limit=limit)


# ---------------------------------------------------------------------------
# SQLiteStore — concurrent-safe, queryable backend
# ---------------------------------------------------------------------------

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    file_type TEXT,
    source_file TEXT,
    source_location TEXT,
    source_url TEXT,
    captured_at TEXT,
    author TEXT,
    contributor TEXT,
    community INTEGER,
    norm_label TEXT,
    attrs TEXT  -- JSON blob for extra attributes
);

CREATE TABLE IF NOT EXISTS edges (
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    relation TEXT NOT NULL,
    confidence TEXT,
    confidence_score REAL,
    source_file TEXT,
    source_location TEXT,
    weight REAL,
    _src TEXT,
    _tgt TEXT,
    attrs TEXT,  -- JSON blob for extra attributes
    PRIMARY KEY (source, target, relation)
);

CREATE TABLE IF NOT EXISTS communities (
    id INTEGER PRIMARY KEY,
    label TEXT,
    node_count INTEGER,
    cohesion REAL
);

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_nodes_community ON nodes(community);
CREATE INDEX IF NOT EXISTS idx_nodes_file_type ON nodes(file_type);
CREATE INDEX IF NOT EXISTS idx_nodes_label ON nodes(label);
CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
"""


class SQLiteStore(GraphStore):
    """SQLite-backed graph store. One sqlite3 connection per thread.

    The previous implementation cached a single connection with
    check_same_thread=False and shared it across all callers without a
    lock — sqlite3 cursors are not safe to interleave that way. We now
    keep connections in thread-local storage so each thread gets its
    own, which is the supported sqlite3 pattern for concurrent access.
    """

    def __init__(self, db_path: str = "graphify-out/graph.db") -> None:
        self.db_path = Path(db_path)
        self._tls = threading.local()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._tls, "conn", None)
        if conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            self._tls.conn = conn
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        conn.executescript(_SQLITE_SCHEMA)
        conn.commit()

    def _node_to_row(self, node: dict) -> tuple:
        attrs = {k: v for k, v in node.items() if k not in {
            "id", "label", "file_type", "source_file", "source_location",
            "source_url", "captured_at", "author", "contributor", "community", "norm_label"
        }}
        return (
            node["id"],
            node.get("label", ""),
            node.get("file_type"),
            node.get("source_file"),
            node.get("source_location"),
            node.get("source_url"),
            node.get("captured_at"),
            node.get("author"),
            node.get("contributor"),
            node.get("community"),
            node.get("norm_label"),
            json.dumps(attrs) if attrs else None,
        )

    def _edge_to_row(self, edge: dict) -> tuple:
        attrs = {k: v for k, v in edge.items() if k not in {
            "source", "target", "relation", "confidence", "confidence_score",
            "source_file", "source_location", "weight", "_src", "_tgt"
        }}
        return (
            edge["source"],
            edge["target"],
            edge.get("relation", ""),
            edge.get("confidence"),
            edge.get("confidence_score"),
            edge.get("source_file"),
            edge.get("source_location"),
            edge.get("weight", 1.0),
            edge.get("_src"),
            edge.get("_tgt"),
            json.dumps(attrs) if attrs else None,
        )

    def save(self, G: nx.Graph, communities: dict[int, list[str]], metadata: dict | None = None) -> None:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM edges")
        cursor.execute("DELETE FROM nodes")
        cursor.execute("DELETE FROM communities")
        cursor.execute("DELETE FROM metadata")

        node_community = {n: cid for cid, nodes in communities.items() for n in nodes}
        for nid, data in G.nodes(data=True):
            d = dict(data, id=nid)
            d["community"] = node_community.get(nid)
            row = self._node_to_row(d)
            cursor.execute(
                "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                row,
            )

        for u, v, data in G.edges(data=True):
            row = self._edge_to_row(dict(data, source=u, target=v))
            cursor.execute(
                "INSERT OR REPLACE INTO edges VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                row,
            )

        for cid, nodes in communities.items():
            cursor.execute(
                "INSERT INTO communities VALUES (?,?,?,?)",
                (cid, None, len(nodes), None),
            )

        meta = dict(metadata or {}, schema_version=SCHEMA_VERSION)
        for k, v in meta.items():
            cursor.execute("INSERT INTO metadata VALUES (?,?)", (k, str(v)))

        conn.commit()

    def load(self) -> tuple[nx.Graph, dict[int, list[str]], dict]:
        conn = self._connect()
        cursor = conn.cursor()

        G = nx.Graph()
        cursor.execute("SELECT * FROM nodes")
        for row in cursor.fetchall():
            d = dict(row)
            nid = d.pop("id")
            attrs = json.loads(d.pop("attrs") or "{}")
            G.add_node(nid, **{k: v for k, v in {**d, **attrs}.items() if v is not None})

        cursor.execute("SELECT * FROM edges")
        for row in cursor.fetchall():
            d = dict(row)
            src = d.pop("source")
            tgt = d.pop("target")
            attrs = json.loads(d.pop("attrs") or "{}")
            G.add_edge(src, tgt, **{k: v for k, v in {**d, **attrs}.items() if v is not None})

        communities: dict[int, list[str]] = {}
        cursor.execute("SELECT id, label FROM communities")
        for row in cursor.fetchall():
            communities[row["id"]] = []

        cursor.execute("SELECT id, community FROM nodes WHERE community IS NOT NULL")
        for row in cursor.fetchall():
            cid = row["community"]
            if cid in communities:
                communities[cid].append(row["id"])

        metadata = {}
        cursor.execute("SELECT key, value FROM metadata")
        for row in cursor.fetchall():
            metadata[row["key"]] = row["value"]

        return G, communities, metadata

    def query_nodes(
        self,
        label: str | None = None,
        file_type: str | None = None,
        community: int | None = None,
        limit: int = 100,
    ) -> list[dict]:
        conn = self._connect()
        where_clauses: list[str] = []
        params: list[Any] = []
        if label:
            where_clauses.append("label LIKE ?")
            params.append(f"%{label}%")
        if file_type:
            where_clauses.append("file_type = ?")
            params.append(file_type)
        if community is not None:
            where_clauses.append("community = ?")
            params.append(community)
        sql = "SELECT * FROM nodes"
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += f" LIMIT {int(limit)}"
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def query_edges(
        self,
        source: str | None = None,
        target: str | None = None,
        relation: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        conn = self._connect()
        where_clauses: list[str] = []
        params: list[Any] = []
        if source:
            where_clauses.append("source = ?")
            params.append(source)
        if target:
            where_clauses.append("target = ?")
            params.append(target)
        if relation:
            where_clauses.append("relation = ?")
            params.append(relation)
        sql = "SELECT * FROM edges"
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += f" LIMIT {int(limit)}"
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_neighbors(self, node_id: str, relation: str | None = None) -> list[dict]:
        conn = self._connect()
        sql = """
            SELECT n.* FROM nodes n
            WHERE n.id IN (
                SELECT target FROM edges WHERE source = ?
                UNION
                SELECT source FROM edges WHERE target = ?
            )
        """
        params = [node_id, node_id]
        if relation:
            sql = """
                SELECT n.* FROM nodes n
                WHERE n.id IN (
                    SELECT target FROM edges WHERE source = ? AND relation = ?
                    UNION
                    SELECT source FROM edges WHERE target = ? AND relation = ?
                )
            """
            params = [node_id, relation, node_id, relation]
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> dict:
        conn = self._connect()
        node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        community_count = conn.execute("SELECT COUNT(*) FROM communities").fetchone()[0]
        schema_row = conn.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()
        return {
            "nodes": node_count,
            "edges": edge_count,
            "communities": community_count,
            "schema_version": schema_row[0] if schema_row else None,
        }

    def search_nodes(self, query: str, limit: int = 20) -> list[dict]:
        return self.query_nodes(label=query, limit=limit)


def store_for(path: str) -> GraphStore:
    """Return the appropriate GraphStore for a path.

    - .db  → SQLiteStore
    - .json → MemoryStore
    """
    p = Path(path)
    if p.suffix == ".db":
        return SQLiteStore(str(p))
    if p.suffix == ".json":
        return MemoryStore(str(p))
    raise ValueError(f"Unknown graph store format: {path}. Use .json or .db")


def migrate_json_to_sqlite(json_path: str, db_path: str) -> SQLiteStore:
    """Migrate an existing graph.json to a SQLite database."""
    store = SQLiteStore(db_path)
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    data = upgrade_graph(data)
    try:
        G = json_graph.node_link_graph(data, edges="links")
    except TypeError:
        G = json_graph.node_link_graph(data)

    communities: dict[int, list[str]] = {}
    for node in data.get("nodes", []):
        cid = node.get("community")
        if cid is not None:
            communities.setdefault(int(cid), []).append(node["id"])

    metadata = dict(data.get("graph", {}))
    store.save(G, communities, metadata)
    print(f"Migrated {G.number_of_nodes()} nodes, {G.number_of_edges()} edges → {db_path}")
    return store
