"""Tests for the `graphify cypher` CLI command."""
import json
import subprocess
import sys
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


def _build_db(tmp_path) -> str:
    from graphify.storage import init_db, ingest_extraction, close_db
    db_path = str(tmp_path / "graph.db")
    ext = json.loads(EXTRACTION_JSON.read_text())
    db, conn = init_db(db_path)
    ingest_extraction(conn, ext, incremental=False)
    close_db(db, conn)
    return db_path


def test_cypher_command_basic(tmp_path):
    db_path = _build_db(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "graphify", "cypher",
         "MATCH (n:code) RETURN count(n)", "--db", db_path],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "3" in result.stdout


def test_cypher_command_db_not_found(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "graphify", "cypher",
         "MATCH (n) RETURN n", "--db", str(tmp_path / "nonexistent.db")],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()


def test_cypher_command_no_query():
    result = subprocess.run(
        [sys.executable, "-m", "graphify", "cypher"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
