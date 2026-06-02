import sys
from unittest.mock import MagicMock, patch
import pytest
from pathlib import Path
from graphify.pg_introspect import introspect_postgres
from graphify.validate import validate_extraction


# ---------------------------------------------------------------------------
# Shared mock infrastructure
# ---------------------------------------------------------------------------

def _make_mock_psycopg(tables, views, routines, fks,
                        host="myhost", dbname="mydb",
                        connect_raises=None):
    """Return a mock psycopg module wired to the provided catalog data.

    ``routines`` rows must be 5-tuples: (schema, name, rtype, body, ext_lang).
    ``fks`` rows must be 7-tuples:
        (constraint_name, t_schema, t_name, [cols], r_schema, r_name, [r_cols])
    ``connect_raises``, if set, is an exception *instance* raised by connect().
    """

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
                return tables
            elif "information_schema.views" in q:
                return views
            elif "information_schema.routines" in q:
                return routines
            elif "information_schema.referential_constraints" in q:
                return fks
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
            info_mock.dsn = f"host={host} dbname={dbname} user=myuser password=secret"
            return info_mock

    mock_psycopg = MagicMock()
    if connect_raises is not None:
        mock_psycopg.connect.side_effect = connect_raises
        # Make the exception type available as an attribute so the module can
        # reference psycopg.OperationalError in the except clause.
        mock_psycopg.OperationalError = type(connect_raises)
    else:
        mock_psycopg.connect.return_value = MockConnection()
        mock_psycopg.OperationalError = Exception  # unused path but must exist
    mock_psycopg.conninfo.conninfo_to_dict.return_value = {
        "host": host,
        "dbname": dbname,
    }
    return mock_psycopg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q(schema: str, name: str) -> str:
    """Return the label form that tree-sitter produces for a quoted identifier.

    pg_introspect emits  CREATE TABLE "schema"."name" — tree-sitter reads the
    object_reference text verbatim (quotes included), so the node label is
    '"schema"."name"', not 'schema.name'.
    """
    return f'"{schema}"."{name}"'


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_pg_introspect_success():
    """Baseline: tables, views, routines, and a single-column FK all survive."""
    mock_tables = [
        ("public", "users", "BASE TABLE"),
        ("public", "orders", "BASE TABLE"),
    ]
    mock_views = [
        ("public", "active_users", "SELECT * FROM public.users WHERE active = true"),
    ]
    # 5-tuple: schema, name, rtype, body, ext_lang
    mock_routines = [
        ("public", "calculate_total", "FUNCTION", "SELECT 42;", "SQL"),
        ("public", "do_nothing", "PROCEDURE", None, "PLPGSQL"),
    ]
    # 7-tuple: constraint_name, t_schema, t_name, cols[], r_schema, r_name, r_cols[]
    mock_fks = [
        ("fk_orders_user_id", "public", "orders", ["user_id"], "public", "users", ["id"]),
    ]

    mock_psycopg = _make_mock_psycopg(mock_tables, mock_views, mock_routines, mock_fks)

    with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
        res = introspect_postgres("postgresql://myuser:mypassword@myhost/mydb")

    # 1. validate_extraction must pass
    errors = validate_extraction(res)
    assert errors == [], f"Validation errors: {errors}"

    # 2. source_file must be the sanitized virtual path (no credentials)
    expected_source = "postgresql:/myhost/mydb"
    for node in res["nodes"]:
        assert node["source_file"] == expected_source
    for edge in res["edges"]:
        assert edge["source_file"] == expected_source

    # 3. Expected node labels. pg_introspect double-quotes identifiers in DDL,
    #    so tree-sitter returns the raw quoted text as the object_reference.
    node_labels = {n["label"] for n in res["nodes"]}
    assert _q("public", "users") in node_labels, f"users missing; got {node_labels}"
    assert _q("public", "orders") in node_labels, f"orders missing; got {node_labels}"
    # Views keep the schema-qualified label (quoted schema, unquoted body)
    assert _q("public", "active_users") in node_labels, f"active_users missing; got {node_labels}"
    # Functions: label is "<quoted-sig>()"
    assert f'{_q("public", "calculate_total")}()' in node_labels, f"calculate_total() missing; got {node_labels}"
    assert f'{_q("public", "do_nothing")}()' in node_labels, f"do_nothing() missing; got {node_labels}"

    # 4. File node (label = dbname)
    file_nodes = [n for n in res["nodes"] if n["file_type"] == "code" and n["label"] == "mydb"]
    assert len(file_nodes) == 1

    # 5. FK references edge: orders → users, exactly once
    users_nid = next(n["id"] for n in res["nodes"] if n["label"] == _q("public", "users"))
    orders_nid = next(n["id"] for n in res["nodes"] if n["label"] == _q("public", "orders"))
    ref_edges = [
        e for e in res["edges"]
        if e["source"] == orders_nid and e["target"] == users_nid and e["relation"] == "references"
    ]
    assert len(ref_edges) == 1, f"Expected exactly 1 references edge, got {len(ref_edges)}"


def test_pg_introspect_quoted_identifiers():
    """Reserved-word and special-character table names must survive DDL round-trip.

    'order' is a SQL reserved word; 'user-data' contains a hyphen — both would
    produce invalid DDL without quoting, causing tree-sitter to silently drop
    those tables and any FK touching them.
    """
    mock_tables = [
        ("public", "order", "BASE TABLE"),      # reserved word
        ("public", "user-data", "BASE TABLE"),  # hyphen
    ]
    mock_views = []
    mock_routines = []
    # FK: user-data.owner_id → order.id
    mock_fks = [
        ("fk_userdata_order", "public", "user-data", ["owner_id"], "public", "order", ["id"]),
    ]

    mock_psycopg = _make_mock_psycopg(mock_tables, mock_views, mock_routines, mock_fks)

    with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
        res = introspect_postgres("postgresql://myuser:secret@myhost/mydb")

    errors = validate_extraction(res)
    assert errors == [], f"Validation errors: {errors}"

    node_labels = {n["label"] for n in res["nodes"]}

    # Both tables must appear as nodes (quoted form expected from tree-sitter)
    assert _q("public", "order") in node_labels, \
        f"'order' table missing; labels={node_labels}"
    assert _q("public", "user-data") in node_labels, \
        f"'user-data' table missing; labels={node_labels}"

    # FK references edge must exist
    ref_edges = [e for e in res["edges"] if e["relation"] == "references"]
    assert len(ref_edges) >= 1, "Expected at least one references edge for the FK"


def test_pg_introspect_composite_fk():
    """A 2-column composite FK must produce exactly ONE references edge, not two.

    The old code emitted one ADD CONSTRAINT per row of the FK query (one row
    per key column), causing duplicate edges for composite keys.
    """
    mock_tables = [
        ("public", "products", "BASE TABLE"),
        ("public", "order_items", "BASE TABLE"),
    ]
    mock_views = []
    mock_routines = []
    # Single composite FK: order_items(order_id, product_id) → products(order_id, product_id)
    mock_fks = [
        (
            "fk_order_items_composite",
            "public", "order_items",
            ["order_id", "product_id"],
            "public", "products",
            ["order_id", "product_id"],
        ),
    ]

    mock_psycopg = _make_mock_psycopg(mock_tables, mock_views, mock_routines, mock_fks)

    with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
        res = introspect_postgres("postgresql://myuser:secret@myhost/mydb")

    errors = validate_extraction(res)
    assert errors == [], f"Validation errors: {errors}"

    products_nid = next(
        n["id"] for n in res["nodes"] if n["label"] == _q("public", "products")
    )
    order_items_nid = next(
        n["id"] for n in res["nodes"] if n["label"] == _q("public", "order_items")
    )

    ref_edges = [
        e for e in res["edges"]
        if e["source"] == order_items_nid
        and e["target"] == products_nid
        and e["relation"] == "references"
    ]
    assert len(ref_edges) == 1, (
        f"Expected exactly 1 references edge for composite FK, got {len(ref_edges)}"
    )


def test_pg_introspect_connection_error():
    """A psycopg.OperationalError must be re-raised as ConnectionError with a
    sanitized message (no DSN/credentials) and no stack-trace noise."""

    class FakeOperationalError(Exception):
        pass

    raw_error = FakeOperationalError(
        'connection to server at "myhost" (127.0.0.1), port 5432 failed: '
        'FATAL: password authentication failed for user "myuser"\n'
        "DETAIL: Connection matched pg_hba.conf line 1: …"
    )

    mock_psycopg = _make_mock_psycopg([], [], [], [], connect_raises=raw_error)

    with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
        with pytest.raises(ConnectionError) as exc_info:
            introspect_postgres("postgresql://myuser:secret@myhost/mydb")

    msg = str(exc_info.value)
    assert "could not connect to PostgreSQL" in msg
    # Credentials must not appear in the surfaced message
    assert "secret" not in msg
    # Only the first line of the OperationalError should be present (no DETAIL)
    assert "DETAIL" not in msg


def test_pg_introspect_import_error():
    """If psycopg is missing, introspect_postgres raises ImportError."""
    with patch.dict("sys.modules", {"psycopg": None}):
        with pytest.raises(ImportError, match="psycopg is required"):
            introspect_postgres("postgresql://localhost/db")
