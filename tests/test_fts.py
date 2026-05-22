"""Tests for FTS5 full-text search in graphify.db."""
import json
from pathlib import Path

import networkx as nx
import pytest

from graphify import db


def _make_graph():
    """Build a test graph with descriptions."""
    G = nx.Graph()
    G.add_node("auth_validate", label="validate()", description="Validates JWT tokens for API authentication", source_file="auth.py")
    G.add_node("auth_session", label="Session", description="Manages user session lifecycle", source_file="auth.py")
    G.add_node("payment_process", label="process_payment()", description="Handles credit card payment processing", source_file="payment.py")
    G.add_node("utils_log", label="log()", description="Writes structured logs to stdout", source_file="utils.py")
    G.add_node("config_load", label="load_config()", description="Reads YAML configuration files", source_file="config.py")
    G.add_edge("auth_validate", "auth_session", relation="uses")
    G.add_edge("payment_process", "auth_validate", relation="calls")
    G.graph["hyperedges"] = []
    return G


@pytest.fixture
def db_path(tmp_path):
    G = _make_graph()
    p = tmp_path / "graph.db"
    db.save_db(p, G, communities={0: ["auth_validate", "auth_session"], 1: ["payment_process", "utils_log", "config_load"]})
    return p


def test_save_db_creates_fts_table(db_path):
    import sqlite3
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='nodes_fts'").fetchone()
    conn.close()
    assert row is not None


def test_search_finds_by_label(db_path):
    results = db.search(db_path, "validate", limit=5)
    assert len(results) >= 1
    ids = [r["id"] for r in results]
    assert "auth_validate" in ids


def test_search_finds_by_description(db_path):
    # "credit card" is in description but not in label
    results = db.search(db_path, "credit card", limit=5)
    assert len(results) >= 1
    ids = [r["id"] for r in results]
    assert "payment_process" in ids


def test_search_finds_by_source_file(db_path):
    # FTS5 tokenizes on "." so search for stem, not full filename
    results = db.search(db_path, "config", limit=5)
    assert len(results) >= 1
    ids = [r["id"] for r in results]
    assert "config_load" in ids


def test_search_prefix_matching(db_path):
    # "auth" should match "auth.py" and labels containing "auth"
    results = db.search(db_path, "auth", limit=10)
    ids = [r["id"] for r in results]
    assert "auth_validate" in ids or "auth_session" in ids


def test_search_bm25_ranking(db_path):
    # "JWT" appears only in auth_validate's description
    results = db.search(db_path, "JWT", limit=5)
    assert len(results) >= 1
    assert results[0]["id"] == "auth_validate"


def test_search_empty_query(db_path):
    results = db.search(db_path, "", limit=5)
    assert results == []


def test_search_no_match(db_path):
    results = db.search(db_path, "zzzznonexistent", limit=5)
    assert results == []


def test_search_returns_score(db_path):
    results = db.search(db_path, "validate", limit=5)
    assert len(results) >= 1
    assert "score" in results[0]
    assert results[0]["score"] > 0


def test_search_returns_description(db_path):
    results = db.search(db_path, "validate", limit=5)
    hit = next(r for r in results if r["id"] == "auth_validate")
    assert "JWT" in hit["description"]


def test_description_stored_in_db(db_path):
    node = db.get_node(db_path, "auth_validate")
    assert node is not None
    assert "Validates JWT" in node.get("description", "")


def test_description_loaded_in_graph(db_path):
    G = db.load_db(db_path)
    assert "Validates JWT" in G.nodes["auth_validate"].get("description", "")
