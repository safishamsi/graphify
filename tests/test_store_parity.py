"""Parity tests for graphify.store / graphify.db.

Slice 1: validates that the SQLite backend round-trips a graph with the same
semantics as the JSON backend, and that the dispatcher correctly selects
between them by file presence.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from graphify import db, store
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import attach_hyperedges, to_json


FIXTURES = Path(__file__).parent / "fixtures"


def _fixture_graph():
    extraction = json.loads((FIXTURES / "extraction.json").read_text())
    G = build_from_json(extraction)
    attach_hyperedges(
        G,
        [
            {
                "id": "he_attn_block",
                "label": "Attention block",
                "nodes": ["n_transformer", "n_attention", "n_layernorm"],
                "relation": "participate_in",
                "confidence": "INFERRED",
                "confidence_score": 0.85,
                "source_file": "model.py",
            }
        ],
    )
    return G


def _node_set(G):
    return {nid: dict(attrs) for nid, attrs in G.nodes(data=True)}


def _edge_set(G):
    """Canonical edge set keyed by (true_src, true_dst, relation) so
    direction-preserved comparison works on undirected NetworkX graphs."""
    out = {}
    for u, v, attrs in G.edges(data=True):
        src = attrs.get("_src", u)
        dst = attrs.get("_tgt", v)
        key = (src, dst, attrs.get("relation"))
        cleaned = {k: val for k, val in attrs.items() if k not in ("_src", "_tgt")}
        out[key] = cleaned
    return out


# ---- detect_backend ----

def test_detect_none():
    with tempfile.TemporaryDirectory() as tmp:
        assert store.detect_backend(tmp) == "none"


def test_detect_json_only():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "graph.json").write_text("{}")
        assert store.detect_backend(tmp) == "json"


def test_detect_db_only():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "graph.db").write_bytes(b"")
        assert store.detect_backend(tmp) == "db"


def test_detect_both_is_error():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "graph.json").write_text("{}")
        (Path(tmp) / "graph.db").write_bytes(b"")
        assert store.detect_backend(tmp) == "both"
        with pytest.raises(RuntimeError, match="Both graph.json and graph.db"):
            store.load(tmp)


def test_load_missing_raises():
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(FileNotFoundError):
            store.load(tmp)


# ---- save/load round-trip parity ----

def test_db_round_trip_preserves_nodes():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "graph.db"
        assert db.save_db(db_path, G, communities)
        G2 = db.load_db(db_path)

    expected = _node_set(G)
    actual = _node_set(G2)
    assert set(expected) == set(actual)
    for nid in expected:
        for k in ("label", "file_type", "source_file", "source_location"):
            assert actual[nid].get(k) == expected[nid].get(k), nid


def test_db_round_trip_preserves_edges_and_direction():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "graph.db"
        db.save_db(db_path, G, communities)
        G2 = db.load_db(db_path)

    expected = _edge_set(G)
    actual = _edge_set(G2)
    assert set(expected) == set(actual)
    for key in expected:
        for k in ("relation", "confidence", "confidence_score", "source_file", "weight"):
            assert actual[key].get(k) == expected[key].get(k), (key, k)


def test_db_round_trip_assigns_communities():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "graph.db"
        db.save_db(db_path, G, communities)
        G2 = db.load_db(db_path)
    for nid in G2.nodes:
        assert G2.nodes[nid].get("community") is not None, nid


def test_db_round_trip_preserves_hyperedges():
    G = _fixture_graph()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "graph.db"
        db.save_db(db_path, G, communities=None)
        G2 = db.load_db(db_path)
    hes = G2.graph.get("hyperedges", [])
    assert len(hes) == 1
    he = hes[0]
    assert he["id"] == "he_attn_block"
    assert set(he["nodes"]) == {"n_transformer", "n_attention", "n_layernorm"}
    assert he["confidence"] == "INFERRED"
    assert he["confidence_score"] == 0.85


def test_db_matches_json_for_same_input():
    """Cross-backend parity: saving the same G to both backends and reloading
    should yield the same node set + edge-by-direction set."""
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        json_path = Path(tmp) / "graph.json"
        db_path = Path(tmp) / "graph.db"
        to_json(G, communities, str(json_path))
        db.save_db(db_path, G, communities)

        # Use the dispatcher's JSON loader for symmetry
        from graphify.store import _load_json
        G_json = _load_json(json_path)
        G_db = db.load_db(db_path)

    assert set(G_json.nodes) == set(G_db.nodes)
    assert set(_edge_set(G_json)) == set(_edge_set(G_db))


# ---- save() refuses silent shrink, force overrides ----

def test_save_refuses_shrink_unless_forced():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "graph.db"
        db.save_db(db_path, G, communities)

        import networkx as nx
        smaller = nx.Graph()
        smaller.add_node("only_one", label="solo", file_type="document")
        ok = db.save_db(db_path, smaller, {0: ["only_one"]})
        assert ok is False  # refused
        assert db.load_db(db_path).number_of_nodes() == G.number_of_nodes()

        ok2 = db.save_db(db_path, smaller, {0: ["only_one"]}, force=True)
        assert ok2 is True
        assert db.load_db(db_path).number_of_nodes() == 1


# ---- apply_update ----

def test_apply_update_db_prunes_deleted_files():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "graph.db"
        db.save_db(db_path, G, communities)

        # Simulate: paper.md was deleted, no new extraction
        empty = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
        merged = db.apply_update(db_path, empty, deleted_files=["paper.md"])

    survivors = {nid for nid in merged.nodes}
    assert "n_concept_attn" not in survivors  # the only paper.md node
    assert "n_transformer" in survivors  # model.py untouched


def test_apply_update_db_merges_new_nodes():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "graph.db"
        db.save_db(db_path, G, communities)

        # Mirror real extraction behaviour: edges only connect endpoints that
        # appear in the same extraction (build_from_json drops dangling edges).
        new_extract = {
            "nodes": [
                {"id": "n_new_a", "label": "NewA", "file_type": "code",
                 "source_file": "new.py", "source_location": "L1"},
                {"id": "n_new_b", "label": "NewB", "file_type": "code",
                 "source_file": "new.py", "source_location": "L20"},
            ],
            "edges": [
                {"source": "n_new_a", "target": "n_new_b", "relation": "calls",
                 "confidence": "EXTRACTED", "confidence_score": 1.0,
                 "source_file": "new.py", "weight": 1.0}
            ],
            "input_tokens": 100,
            "output_tokens": 20,
        }
        merged = db.apply_update(db_path, new_extract, deleted_files=[])

    # Existing nodes preserved
    assert "n_transformer" in merged.nodes
    # New nodes merged
    assert "n_new_a" in merged.nodes
    assert merged.nodes["n_new_a"]["label"] == "NewA"
    assert merged.has_edge("n_new_a", "n_new_b")


# ---- store dispatcher ----

def test_store_dispatcher_selects_db_when_only_db_present():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        db.save_db(Path(tmp) / "graph.db", G, communities)
        loaded = store.load(tmp)
    assert set(loaded.nodes) == set(G.nodes)


def test_store_dispatcher_selects_json_when_only_json_present():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        to_json(G, communities, str(Path(tmp) / "graph.json"))
        loaded = store.load(tmp)
    assert set(loaded.nodes) == set(G.nodes)


def test_store_save_defaults_to_json_on_fresh_dir():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        store.save(tmp, G, communities)
        assert (Path(tmp) / "graph.json").exists()
        assert not (Path(tmp) / "graph.db").exists()


def test_store_save_respects_existing_backend():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        # seed DB
        db.save_db(Path(tmp) / "graph.db", G, communities)
        # save() should detect existing DB and rewrite the DB, not create JSON
        store.save(tmp, G, communities, force=True)
        assert (Path(tmp) / "graph.db").exists()
        assert not (Path(tmp) / "graph.json").exists()


def test_store_save_explicit_backend_wins():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        store.save(tmp, G, communities, backend="db")
        assert (Path(tmp) / "graph.db").exists()
        assert not (Path(tmp) / "graph.json").exists()


def test_store_get_node_db_and_json_agree():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp_json, tempfile.TemporaryDirectory() as tmp_db:
        to_json(G, communities, str(Path(tmp_json) / "graph.json"))
        db.save_db(Path(tmp_db) / "graph.db", G, communities)
        n_json = store.get_node(tmp_json, "n_transformer")
        n_db = store.get_node(tmp_db, "n_transformer")
    assert n_json is not None and n_db is not None
    assert n_json["label"] == n_db["label"] == "Transformer"
    assert n_json["file_type"] == n_db["file_type"] == "code"


def test_save_rejects_backend_switch_without_migrate():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        # Seed with JSON backend
        store.save(tmp, G, communities, backend="json")
        # Attempting to save with backend="db" must error — no silent dual writes
        with pytest.raises(RuntimeError, match="Backend mismatch"):
            store.save(tmp, G, communities, backend="db")
        # Sanity: graph.json still exists, graph.db does not
        assert (Path(tmp) / "graph.json").exists()
        assert not (Path(tmp) / "graph.db").exists()


def test_migrate_json_to_db():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        store.save(tmp, G, communities, backend="json")
        src, tgt = store.migrate(tmp, "db")
        assert (src, tgt) == ("json", "db")
        assert (Path(tmp) / "graph.db").exists()
        assert not (Path(tmp) / "graph.json").exists()
        # Graph survives the migration
        loaded = store.load(tmp)
        assert set(loaded.nodes) == set(G.nodes)


def test_migrate_db_to_json():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        store.save(tmp, G, communities, backend="db")
        src, tgt = store.migrate(tmp, "json")
        assert (src, tgt) == ("db", "json")
        assert (Path(tmp) / "graph.json").exists()
        assert not (Path(tmp) / "graph.db").exists()
        loaded = store.load(tmp)
        assert set(loaded.nodes) == set(G.nodes)


def test_migrate_no_op_when_target_matches():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        store.save(tmp, G, communities, backend="db")
        src, tgt = store.migrate(tmp, "db")
        assert (src, tgt) == ("db", "db")
        assert (Path(tmp) / "graph.db").exists()


def test_migrate_invalid_target():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "graph.json").write_text("{}")
        with pytest.raises(ValueError, match="must be 'json' or 'db'"):
            store.migrate(tmp, "neo4j")  # type: ignore[arg-type]


def test_artifact_name():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        # Empty dir defaults to graph.json
        assert store.artifact_name(tmp) == "graph.json"
        # JSON KB
        store.save(tmp, G, communities, backend="json")
        assert store.artifact_name(tmp) == "graph.json"
    with tempfile.TemporaryDirectory() as tmp:
        # DB KB
        store.save(tmp, G, communities, backend="db")
        assert store.artifact_name(tmp) == "graph.db"


def test_build_merge_compat_db_merges_existing_with_new():
    """Mirror the JSON build_merge behaviour on a DB-backed KB:
    existing graph + new chunk → merged graph contains both."""
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        store.save(tmp, G, communities, backend="db")
        new_chunk = {
            "nodes": [
                {"id": "n_new_x", "label": "NewX", "file_type": "code",
                 "source_file": "x.py", "source_location": "L1"},
            ],
            "edges": [],
            "input_tokens": 0, "output_tokens": 0,
        }
        merged = store.build_merge_compat([new_chunk], tmp, dedup=False)
    # Existing nodes preserved, new node added
    assert "n_transformer" in merged.nodes
    assert "n_new_x" in merged.nodes


def test_build_merge_compat_db_prunes_deleted():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        store.save(tmp, G, communities, backend="db")
        empty = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
        merged = store.build_merge_compat(
            [empty], tmp, prune_sources=["paper.md"], dedup=False
        )
    # paper.md was the only source for n_concept_attn
    assert "n_concept_attn" not in merged.nodes
    assert "n_transformer" in merged.nodes


def test_make_and_remove_backup():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        store.save(tmp, G, communities, backend="db")
        backup = store.make_backup(tmp)
        assert backup.name == ".graphify_old.db"
        assert backup.exists()
        assert store.backup_path(tmp) == backup
        store.remove_backup(tmp)
        assert store.backup_path(tmp) is None


def test_store_search_label_db_and_json_agree():
    G = _fixture_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp_json, tempfile.TemporaryDirectory() as tmp_db:
        to_json(G, communities, str(Path(tmp_json) / "graph.json"))
        db.save_db(Path(tmp_db) / "graph.db", G, communities)
        r_json = {n["id"] for n in store.search_label(tmp_json, "attention")}
        r_db = {n["id"] for n in store.search_label(tmp_db, "attention")}
    assert r_json == r_db
    assert "n_attention" in r_json
