import sys
from unittest.mock import MagicMock, patch
import pytest
from pathlib import Path
from graphify.pg_introspect import introspect_postgres
from graphify.validate import validate_extraction

def test_pg_introspect_success():
    # Canned database catalog details
    mock_tables = [
        ("public", "users", "BASE TABLE"),
        ("public", "orders", "BASE TABLE"),
    ]
    mock_views = [
        ("public", "active_users", "SELECT * FROM public.users WHERE active = true"),
    ]
    mock_routines = [
        ("public", "calculate_total", "FUNCTION", "SELECT 42;"),
        ("public", "do_nothing", "PROCEDURE", None),
    ]
    mock_fks = [
        ("public", "orders", "user_id", "public", "users", "id"),
    ]

    # Mock psycopg cursors and connections
    class MockCursor:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def execute(self, query, params=None):
            self.query = query
        def fetchall(self):
            q = self.query.strip().lower()
            if "information_schema.tables" in q:
                return mock_tables
            elif "information_schema.views" in q:
                return mock_views
            elif "information_schema.routines" in q:
                return mock_routines
            elif "information_schema.referential_constraints" in q:
                return mock_fks
            return []

    class MockConnection:
        def execute(self, query):
            pass
        def cursor(self):
            return MockCursor()
        def close(self):
            pass
        @property
        def info(self):
            info_mock = MagicMock()
            info_mock.dsn = "host=myhost dbname=mydb user=myuser password=mypassword"
            return info_mock

    mock_connect = MagicMock(return_value=MockConnection())

    mock_psycopg = MagicMock()
    mock_psycopg.connect = mock_connect
    mock_psycopg.conninfo.conninfo_to_dict = MagicMock(return_value={
        "host": "myhost",
        "dbname": "mydb",
    })

    with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
        res = introspect_postgres("postgresql://myuser:mypassword@myhost/mydb")

    # Assertions
    # 1. Check validate_extraction passes
    errors = validate_extraction(res)
    assert errors == [], f"Validation errors: {errors}"

    # 2. Check source_file is sanitized virtual path (without credentials)
    expected_source = "postgresql:/myhost/mydb"
    for node in res["nodes"]:
        assert node["source_file"] == expected_source
    for edge in res["edges"]:
        assert edge["source_file"] == expected_source

    # 3. Check correct node labels were created
    node_labels = {n["label"] for n in res["nodes"]}
    assert "public.users" in node_labels
    assert "public.orders" in node_labels
    assert "public.active_users" in node_labels
    assert "public.calculate_total()" in node_labels
    assert "public.do_nothing()" in node_labels

    # 4. Verify edge relationships (contains edges for all items, and references edge from orders to users)
    file_nodes = [n for n in res["nodes"] if n["file_type"] == "code" and n["label"] == "mydb"]
    assert len(file_nodes) == 1

    # Verify orders references users edge exists
    users_nid = [n["id"] for n in res["nodes"] if n["label"] == "public.users"][0]
    orders_nid = [n["id"] for n in res["nodes"] if n["label"] == "public.orders"][0]
    
    ref_edges = [e for e in res["edges"] if e["source"] == orders_nid and e["target"] == users_nid and e["relation"] == "references"]
    assert len(ref_edges) == 1

def test_pg_introspect_import_error():
    # If psycopg module is missing or cannot be imported, introspect_postgres raises ImportError
    with patch.dict("sys.modules", {"psycopg": None}):
        with pytest.raises(ImportError, match="psycopg is required"):
            introspect_postgres("postgresql://localhost/db")
