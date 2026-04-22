"""tests/test_languages_sql.py

Tests for the SQL AST extractor. Run with:
    pytest tests/test_languages_sql.py -q
"""
from __future__ import annotations
import pytest
from pathlib import Path
from graphify.extract import extract_sql


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

_DDL = """\
-- User accounts
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    total DECIMAL(10,2)
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100)
);

CREATE TABLE order_items (
    order_id INT REFERENCES orders(id),
    product_id INT REFERENCES products(id),
    qty INT DEFAULT 1
);

-- Reporting view
CREATE VIEW active_orders AS
    SELECT o.id, u.email
    FROM orders o
    JOIN users u ON o.user_id = u.id;

CREATE INDEX idx_orders_user ON orders(user_id);
"""


@pytest.fixture
def sql_file(tmp_path: Path) -> Path:
    f = tmp_path / "schema.sql"
    f.write_text(_DDL, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# schema compliance
# ---------------------------------------------------------------------------

def test_returns_nodes_and_edges_keys(sql_file):
    result = extract_sql(sql_file)
    assert "nodes" in result
    assert "edges" in result
    assert "error" not in result


def test_node_schema(sql_file):
    result = extract_sql(sql_file)
    required = {"id", "label", "file_type", "source_file", "source_location"}
    for node in result["nodes"]:
        missing = required - node.keys()
        assert not missing, f"node missing fields {missing}: {node}"
        assert node["file_type"] == "code"
        assert node["source_file"].endswith("schema.sql")


def test_edge_schema(sql_file):
    result = extract_sql(sql_file)
    valid_conf = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}
    required = {"source", "target", "relation", "confidence", "confidence_score",
                "source_file", "source_location", "weight"}
    for edge in result["edges"]:
        missing = required - edge.keys()
        assert not missing, f"edge missing fields {missing}: {edge}"
        assert edge["confidence"] in valid_conf
        assert edge["weight"] == 1.0


# ---------------------------------------------------------------------------
# node extraction
# ---------------------------------------------------------------------------

def test_tables_extracted(sql_file):
    labels = {n["label"] for n in extract_sql(sql_file)["nodes"]}
    assert "users" in labels
    assert "orders" in labels
    assert "products" in labels


def test_view_extracted(sql_file):
    labels = {n["label"] for n in extract_sql(sql_file)["nodes"]}
    assert "active_orders" in labels


def test_index_extracted(sql_file):
    labels = {n["label"] for n in extract_sql(sql_file)["nodes"]}
    assert "idx_orders_user" in labels


def test_columns_extracted(sql_file):
    labels = {n["label"] for n in extract_sql(sql_file)["nodes"]}
    assert "users.email" in labels
    assert "orders.user_id" in labels
    assert "order_items.order_id" in labels


# ---------------------------------------------------------------------------
# edge correctness
# ---------------------------------------------------------------------------

def test_has_column_edges(sql_file):
    edges = [e for e in extract_sql(sql_file)["edges"] if e["relation"] == "has_column"]
    targets = {e["target"] for e in edges}
    # At least one column per table should appear
    assert any("users" in t for t in targets)
    assert any("orders" in t for t in targets)


def test_fk_reference_edges(sql_file):
    refs = [e for e in extract_sql(sql_file)["edges"] if e["relation"] == "references"]
    assert len(refs) >= 3, "Expected FK edges: orders→users, order_items→orders, order_items→products"
    fk_targets = {e["target"] for e in refs}
    assert any("users" in t for t in fk_targets)
    assert any("orders" in t for t in fk_targets)
    assert any("products" in t for t in fk_targets)


def test_fk_confidence_is_extracted(sql_file):
    refs = [e for e in extract_sql(sql_file)["edges"] if e["relation"] == "references"]
    for e in refs:
        assert e["confidence"] == "EXTRACTED"
        assert e["confidence_score"] == 1.0


def test_index_edge(sql_file):
    idx_edges = [e for e in extract_sql(sql_file)["edges"] if e["relation"] == "indexed_on"]
    assert len(idx_edges) >= 1
    tgt_labels = {e["target"] for e in idx_edges}
    assert any("orders" in t for t in tgt_labels)


def test_view_joins_edges(sql_file):
    joins = [e for e in extract_sql(sql_file)["edges"] if e["relation"] == "joins"]
    assert len(joins) >= 1
    joined = {e["target"] for e in joins}
    assert any("users" in t for t in joined)


def test_join_edges_are_inferred(sql_file):
    joins = [e for e in extract_sql(sql_file)["edges"] if e["relation"] == "joins"]
    for e in joins:
        assert e["confidence"] == "INFERRED"
        assert e["confidence_score"] == pytest.approx(0.9)


def test_rationale_comment_edge(sql_file):
    rationale = [e for e in extract_sql(sql_file)["edges"] if e["relation"] == "rationale_for"]
    assert len(rationale) >= 1


# ---------------------------------------------------------------------------
# edge / empty cases
# ---------------------------------------------------------------------------

def test_empty_file(tmp_path):
    f = tmp_path / "empty.sql"
    f.write_bytes(b"")
    result = extract_sql(f)
    assert result["nodes"] == []
    assert result["edges"] == []
    assert "error" not in result


def test_comments_only_no_crash(tmp_path):
    f = tmp_path / "comments.sql"
    f.write_text("-- just a comment\n-- another\n", encoding="utf-8")
    result = extract_sql(f)
    assert "nodes" in result
    assert "error" not in result


def test_multiple_fks_on_same_table(tmp_path):
    f = tmp_path / "multi_fk.sql"
    f.write_text("""\
CREATE TABLE order_items (
    order_id   INT REFERENCES orders(id),
    product_id INT REFERENCES products(id),
    qty INT
);
""", encoding="utf-8")
    result = extract_sql(f)
    refs = [e for e in result["edges"] if e["relation"] == "references"]
    fk_targets = {e["target"] for e in refs}
    assert any("orders" in t for t in fk_targets)
    assert any("products" in t for t in fk_targets)


def test_index_on_join_table(tmp_path):
    f = tmp_path / "idx.sql"
    f.write_text("""\
CREATE TABLE order_items (id SERIAL PRIMARY KEY);
CREATE INDEX idx_oi_order ON order_items(order_id);
""", encoding="utf-8")
    result = extract_sql(f)
    idx_edges = [e for e in result["edges"] if e["relation"] == "indexed_on"]
    assert len(idx_edges) == 1
    assert any("order_items" in e["target"] for e in idx_edges)