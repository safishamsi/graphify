"""Tests for graphify.storage — NeuG adapter layer."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

try:
    import neug
    _has_neug = True
except ImportError:
    _has_neug = False

pytestmark = pytest.mark.skipif(not _has_neug, reason="neug not installed")

FIXTURES = Path(__file__).parent / "fixtures"
EXTRACTION_JSON = FIXTURES / "extraction.json"


def _load_extraction() -> dict:
    return json.loads(EXTRACTION_JSON.read_text())


@pytest.fixture()
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    yield db_path


def _init(db_path):
    from graphify.storage import init_db, ensure_schema
    db, conn = init_db(db_path)
    ensure_schema(conn)
    return db, conn


def _close(db, conn):
    from graphify.storage import close_db
    close_db(db, conn)


def _query(conn, cypher):
    from graphify.storage import execute_cypher
    return execute_cypher(conn, cypher)


# --- init_db ---

def test_init_db_creates_tables(tmp_db):
    db, conn = _init(tmp_db)
    for tbl in ("code", "document", "paper", "image", "concept", "rationale"):
        rows = _query(conn, f"MATCH (n:{tbl}) RETURN count(n)")
        assert rows == [[0]]
    _close(db, conn)


# --- ingest_extraction: CREATE mode ---

def test_ingest_extraction_create_mode(tmp_db):
    from graphify.storage import ingest_extraction
    db, conn = _init(tmp_db)
    ext = _load_extraction()
    ingest_extraction(conn, ext, incremental=False)
    rows = _query(conn, "MATCH (n:code) RETURN n.id ORDER BY n.id")
    ids = sorted([r[0] for r in rows])
    assert "n_attention" in ids
    assert "n_transformer" in ids
    assert "n_layernorm" in ids
    edge_rows = _query(conn, "MATCH (a:code)-[e:edge_code_code_contains]->(b:code) RETURN count(e)")
    assert edge_rows[0][0] == 2
    _close(db, conn)


# --- ingest_extraction: MERGE mode ---

def test_ingest_extraction_merge_mode(tmp_db):
    from graphify.storage import ingest_extraction
    db, conn = _init(tmp_db)
    ext = _load_extraction()
    ingest_extraction(conn, ext, incremental=False)
    ext["nodes"][0]["label"] = "TransformerV2"
    ingest_extraction(conn, ext, incremental=True)
    rows = _query(conn, "MATCH (n:code) WHERE n.id = 'n_transformer' RETURN n.label")
    assert rows[0][0] == "TransformerV2"
    count = _query(conn, "MATCH (n:code) RETURN count(n)")
    assert count[0][0] == 3
    _close(db, conn)


# --- file_type routing ---

def test_ingest_extraction_file_type_routing(tmp_db):
    from graphify.storage import ingest_extraction
    db, conn = _init(tmp_db)
    ext = _load_extraction()
    ingest_extraction(conn, ext, incremental=False)
    doc_rows = _query(conn, "MATCH (n:document) RETURN n.id")
    assert len(doc_rows) == 1
    assert doc_rows[0][0] == "n_concept_attn"
    _close(db, conn)


# --- prune_sources ---

def test_ingest_extraction_prune(tmp_db):
    from graphify.storage import ingest_extraction
    db, conn = _init(tmp_db)
    ext = _load_extraction()
    ingest_extraction(conn, ext, incremental=False)
    before = _query(conn, "MATCH (n:code) RETURN count(n)")[0][0]
    assert before == 3
    ingest_extraction(conn, ext, incremental=True, prune_sources=["model.py"])
    after_prune = _query(conn, "MATCH (n:code) RETURN count(n)")[0][0]
    assert after_prune == 3
    _close(db, conn)


# --- fallback rel table ---

def test_fallback_rel_table(tmp_db):
    from graphify.storage import _ensure_rel_table, ensure_schema
    db, conn = _init(tmp_db)
    known = ensure_schema(conn)
    tbl = _ensure_rel_table(conn, "paper", "document", "cites", known)
    assert tbl == "edge_paper_document_cites"
    assert tbl in known
    _close(db, conn)


# --- communities ---

def test_ingest_communities(tmp_db):
    from graphify.storage import ingest_extraction, ingest_communities
    db, conn = _init(tmp_db)
    ext = _load_extraction()
    ingest_extraction(conn, ext, incremental=False)
    communities = {0: ["n_transformer", "n_attention"], 1: ["n_layernorm"]}
    ingest_communities(conn, communities)
    rows = _query(conn, "MATCH (n:code) WHERE n.id = 'n_transformer' RETURN n.community")
    assert rows[0][0] == 0
    rows = _query(conn, "MATCH (n:code) WHERE n.id = 'n_layernorm' RETURN n.community")
    assert rows[0][0] == 1
    _close(db, conn)


# --- execute_cypher ---

def test_execute_cypher(tmp_db):
    from graphify.storage import ingest_extraction
    db, conn = _init(tmp_db)
    ext = _load_extraction()
    ingest_extraction(conn, ext, incremental=False)
    rows = _query(conn, "MATCH (n:code) RETURN n.label ORDER BY n.id")
    labels = [r[0] for r in rows]
    assert "MultiHeadAttention" in labels
    assert "Transformer" in labels
    _close(db, conn)


def test_execute_cypher_bad_query(tmp_db):
    db, conn = _init(tmp_db)
    with pytest.raises(RuntimeError):
        _query(conn, "THIS IS NOT VALID CYPHER")
    _close(db, conn)


# --- roundtrip consistency ---

def test_roundtrip_node_count(tmp_db):
    from graphify.storage import ingest_extraction
    db, conn = _init(tmp_db)
    ext = _load_extraction()
    ingest_extraction(conn, ext, incremental=False)
    total = 0
    for tbl in ("code", "document", "paper", "image", "concept", "rationale"):
        rows = _query(conn, f"MATCH (n:{tbl}) RETURN count(n)")
        total += rows[0][0]
    assert total == len(ext["nodes"])
    _close(db, conn)
