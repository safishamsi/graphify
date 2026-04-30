"""Tests for graphify.store — GraphStore abstraction layer."""
from __future__ import annotations

import json

import networkx as nx
import pytest
from networkx.readwrite import json_graph

from graphify.store import MemoryStore, SQLiteStore, store_for, migrate_json_to_sqlite


def _make_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("a", label="A", file_type="code", source_file="a.py")
    G.add_node("b", label="B", file_type="code", source_file="b.py")
    G.add_node("c", label="C", file_type="document", source_file="c.md")
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED", source_file="a.py")
    G.add_edge("b", "c", relation="references", confidence="INFERRED", source_file="b.py")
    return G


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------

def test_memory_store_roundtrip(tmp_path):
    G = _make_graph()
    communities = {0: ["a", "b"], 1: ["c"]}
    path = tmp_path / "graph.json"
    store = MemoryStore(str(path))
    store.save(G, communities, {"key": "value"})

    G2, comm2, meta = store.load()
    assert G2.number_of_nodes() == 3
    assert G2.number_of_edges() == 2
    assert comm2 == communities
    assert meta.get("key") == "value"
    assert path.exists()


def test_memory_store_query_nodes_by_label(tmp_path):
    G = _make_graph()
    store = MemoryStore(str(tmp_path / "g.json"))
    store.save(G, {})
    results = store.query_nodes(label="A")
    assert len(results) == 1
    assert results[0]["id"] == "a"


def test_memory_store_query_nodes_by_file_type(tmp_path):
    G = _make_graph()
    store = MemoryStore(str(tmp_path / "g.json"))
    store.save(G, {})
    results = store.query_nodes(file_type="document")
    assert len(results) == 1
    assert results[0]["id"] == "c"


def test_memory_store_query_nodes_by_community(tmp_path):
    G = _make_graph()
    store = MemoryStore(str(tmp_path / "g.json"))
    store.save(G, {0: ["a"], 1: ["b", "c"]})
    results = store.query_nodes(community=1)
    assert len(results) == 2


def test_memory_store_query_edges_by_relation(tmp_path):
    G = _make_graph()
    store = MemoryStore(str(tmp_path / "g.json"))
    store.save(G, {})
    results = store.query_edges(relation="calls")
    assert len(results) == 1
    assert results[0]["source"] == "a"


def test_memory_store_get_neighbors(tmp_path):
    G = _make_graph()
    store = MemoryStore(str(tmp_path / "g.json"))
    store.save(G, {})
    neighbors = store.get_neighbors("a")
    assert len(neighbors) == 1
    assert neighbors[0]["id"] == "b"


def test_memory_store_get_stats(tmp_path):
    G = _make_graph()
    store = MemoryStore(str(tmp_path / "g.json"))
    store.save(G, {0: ["a", "b", "c"]}, {})
    stats = store.get_stats()
    assert stats["nodes"] == 3
    assert stats["edges"] == 2
    assert stats["communities"] == 1


# ---------------------------------------------------------------------------
# SQLiteStore
# ---------------------------------------------------------------------------

def test_sqlite_store_roundtrip(tmp_path):
    G = _make_graph()
    communities = {0: ["a", "b"], 1: ["c"]}
    db = tmp_path / "graph.db"
    store = SQLiteStore(str(db))
    store.save(G, communities, {"key": "value"})

    G2, comm2, meta = store.load()
    assert G2.number_of_nodes() == 3
    assert G2.number_of_edges() == 2
    assert sorted(comm2[0]) == ["a", "b"]
    assert sorted(comm2[1]) == ["c"]
    assert meta.get("key") == "value"
    assert db.exists()


def test_sqlite_store_query_nodes_by_label(tmp_path):
    G = _make_graph()
    store = SQLiteStore(str(tmp_path / "g.db"))
    store.save(G, {})
    results = store.query_nodes(label="B")
    assert len(results) == 1
    assert results[0]["id"] == "b"


def test_sqlite_store_query_nodes_by_file_type(tmp_path):
    G = _make_graph()
    store = SQLiteStore(str(tmp_path / "g.db"))
    store.save(G, {})
    results = store.query_nodes(file_type="document")
    assert len(results) == 1
    assert results[0]["id"] == "c"


def test_sqlite_store_query_nodes_by_community(tmp_path):
    G = _make_graph()
    store = SQLiteStore(str(tmp_path / "g.db"))
    store.save(G, {0: ["a"], 1: ["b", "c"]})
    results = store.query_nodes(community=1)
    ids = {r["id"] for r in results}
    assert ids == {"b", "c"}


def test_sqlite_store_query_edges_by_relation(tmp_path):
    G = _make_graph()
    store = SQLiteStore(str(tmp_path / "g.db"))
    store.save(G, {})
    results = store.query_edges(relation="references")
    assert len(results) == 1
    assert results[0]["source"] == "b"


def test_sqlite_store_get_neighbors(tmp_path):
    G = _make_graph()
    store = SQLiteStore(str(tmp_path / "g.db"))
    store.save(G, {})
    neighbors = store.get_neighbors("b")
    ids = {n["id"] for n in neighbors}
    assert ids == {"a", "c"}


def test_sqlite_store_get_stats(tmp_path):
    G = _make_graph()
    store = SQLiteStore(str(tmp_path / "g.db"))
    store.save(G, {0: ["a", "b", "c"]}, {})
    stats = store.get_stats()
    assert stats["nodes"] == 3
    assert stats["edges"] == 2
    assert stats["communities"] == 1


def test_migrate_json_to_sqlite(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    data["graph"] = {"schema_version": "0.5.5"}
    json_path = tmp_path / "graph.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")

    db_path = tmp_path / "graph.db"
    store = migrate_json_to_sqlite(str(json_path), str(db_path))
    stats = store.get_stats()
    assert stats["nodes"] == 3
    assert stats["edges"] == 2
    assert db_path.exists()


def test_store_for_dispatch():
    assert isinstance(store_for("graph.json"), MemoryStore)
    assert isinstance(store_for("graph.db"), SQLiteStore)
    with pytest.raises(ValueError):
        store_for("graph.xml")


def test_sqlite_store_concurrent_reads(tmp_path):
    # Each worker thread must get its own sqlite3 connection. Sharing a
    # single connection across threads (the previous behavior) raises
    # ProgrammingError on cursor reuse — a regression here surfaces as
    # any thread reporting a non-3 node count or any exception.
    import threading

    G = _make_graph()
    store = SQLiteStore(str(tmp_path / "g.db"))
    store.save(G, {0: ["a", "b", "c"]})

    errors: list[BaseException] = []
    counts: list[int] = []

    def worker():
        try:
            for _ in range(20):
                stats = store.get_stats()
                counts.append(stats["nodes"])
                rows = store.query_nodes(file_type="code")
                assert len(rows) == 2
        except BaseException as exc:  # noqa: BLE001 — surface any error
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert counts and all(c == 3 for c in counts)
