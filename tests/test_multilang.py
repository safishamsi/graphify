"""Tests for multi-language AST extraction: JS/TS, Go, Rust, SQL."""
from __future__ import annotations
import shutil
from pathlib import Path
import pytest
from graphify.extract import extract_js, extract_go, extract_rust, extract, extract_sql

FIXTURES = Path(__file__).parent / "fixtures"


# ── helpers ──────────────────────────────────────────────────────────────────

def _labels(result):
    return [n["label"] for n in result["nodes"]]

def _call_pairs(result):
    node_by_id = {n["id"]: n["label"] for n in result["nodes"]}
    return {
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in result["edges"] if e["relation"] == "calls"
    }

def _confidences(result):
    return {e["confidence"] for e in result["edges"]}


def _edges_with_relation(result, *relations):
    return [e for e in result["edges"] if e["relation"] in relations]


# ── TypeScript ────────────────────────────────────────────────────────────────

def test_ts_finds_class():
    r = extract_js(FIXTURES / "sample.ts")
    assert "error" not in r
    assert "HttpClient" in _labels(r)

def test_ts_finds_methods():
    r = extract_js(FIXTURES / "sample.ts")
    labels = _labels(r)
    assert any("get" in l for l in labels)
    assert any("post" in l for l in labels)

def test_ts_finds_function():
    r = extract_js(FIXTURES / "sample.ts")
    assert any("buildHeaders" in l for l in _labels(r))

def test_ts_emits_calls():
    r = extract_js(FIXTURES / "sample.ts")
    calls = _call_pairs(r)
    # .post() calls .get()
    assert any("post" in src and "get" in tgt for src, tgt in calls)

def test_ts_calls_are_extracted():
    r = extract_js(FIXTURES / "sample.ts")
    for e in r["edges"]:
        if e["relation"] == "calls":
            assert e["confidence"] == "EXTRACTED"


def test_ts_import_edges_have_import_context():
    r = extract_js(FIXTURES / "sample.ts")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_ts_call_edges_have_call_context():
    r = extract_js(FIXTURES / "sample.ts")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)

def test_ts_no_dangling_edges():
    r = extract_js(FIXTURES / "sample.ts")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        if e["relation"] in ("contains", "method", "calls"):
            assert e["source"] in node_ids


# ── Go ────────────────────────────────────────────────────────────────────────

def test_go_finds_struct():
    r = extract_go(FIXTURES / "sample.go")
    assert "error" not in r
    assert "Server" in _labels(r)

def test_go_finds_methods():
    r = extract_go(FIXTURES / "sample.go")
    labels = _labels(r)
    assert any("Start" in l for l in labels)
    assert any("Stop" in l for l in labels)

def test_go_finds_constructor():
    r = extract_go(FIXTURES / "sample.go")
    assert any("NewServer" in l for l in _labels(r))

def test_go_emits_calls():
    r = extract_go(FIXTURES / "sample.go")
    # main() calls NewServer and Start
    assert len(_call_pairs(r)) > 0

def test_go_has_extracted_calls():
    r = extract_go(FIXTURES / "sample.go")
    assert "EXTRACTED" in _confidences(r)


def test_go_import_edges_have_import_context():
    r = extract_go(FIXTURES / "sample.go")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_go_call_edges_have_call_context():
    r = extract_go(FIXTURES / "sample.go")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)

def test_go_no_dangling_edges():
    r = extract_go(FIXTURES / "sample.go")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        if e["relation"] in ("contains", "method", "calls"):
            assert e["source"] in node_ids


# ── Rust ──────────────────────────────────────────────────────────────────────

def test_rust_finds_struct():
    r = extract_rust(FIXTURES / "sample.rs")
    assert "error" not in r
    assert "Graph" in _labels(r)

def test_rust_finds_impl_methods():
    r = extract_rust(FIXTURES / "sample.rs")
    labels = _labels(r)
    assert any("add_node" in l for l in labels)
    assert any("add_edge" in l for l in labels)

def test_rust_finds_function():
    r = extract_rust(FIXTURES / "sample.rs")
    assert any("build_graph" in l for l in _labels(r))

def test_rust_emits_calls():
    r = extract_rust(FIXTURES / "sample.rs")
    calls = _call_pairs(r)
    assert any("build_graph" in src for src, _ in calls)

def test_rust_calls_are_extracted():
    r = extract_rust(FIXTURES / "sample.rs")
    for e in r["edges"]:
        if e["relation"] == "calls":
            assert e["confidence"] == "EXTRACTED"


def test_rust_import_edges_have_import_context():
    r = extract_rust(FIXTURES / "sample.rs")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_rust_call_edges_have_call_context():
    r = extract_rust(FIXTURES / "sample.rs")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)

def test_rust_no_dangling_edges():
    r = extract_rust(FIXTURES / "sample.rs")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        if e["relation"] in ("contains", "method", "calls"):
            assert e["source"] in node_ids


def test_rust_no_cross_crate_spurious_edges():
    """Scoped calls (Type::method) and blocklisted names must not produce
    INFERRED cross-crate calls edges (#908)."""
    from graphify.extract import extract
    crate_a = FIXTURES / "crate_a" / "src" / "lib.rs"
    crate_b = FIXTURES / "crate_b" / "src" / "lib.rs"
    r = extract([crate_a, crate_b])
    node_ids_a = {n["id"] for n in r["nodes"] if "crate_a" in (n.get("source_file") or "")}
    node_ids_b = {n["id"] for n in r["nodes"] if "crate_b" in (n.get("source_file") or "")}
    # No calls edge should cross from crate_b into crate_a
    cross_crate_calls = [
        e for e in r["edges"]
        if e["relation"] == "calls"
        and e["source"] in node_ids_b
        and e["target"] in node_ids_a
    ]
    assert cross_crate_calls == [], (
        f"Spurious cross-crate edges: {cross_crate_calls}"
    )


# ── extract() dispatch ────────────────────────────────────────────────────────

def test_extract_dispatches_all_languages():
    files = [
        FIXTURES / "sample.py",
        FIXTURES / "sample.ts",
        FIXTURES / "sample.go",
        FIXTURES / "sample.rs",
    ]
    r = extract(files)
    source_files = {n["source_file"] for n in r["nodes"] if n["source_file"]}
    # All four files should contribute nodes
    assert any("sample.py" in f for f in source_files)
    assert any("sample.ts" in f for f in source_files)
    assert any("sample.go" in f for f in source_files)
    assert any("sample.rs" in f for f in source_files)


# ── Cache ─────────────────────────────────────────────────────────────────────

def test_cache_hit_returns_same_result(tmp_path):
    src = FIXTURES / "sample.py"
    dst = tmp_path / "sample.py"
    dst.write_bytes(src.read_bytes())

    r1 = extract([dst])
    r2 = extract([dst])
    assert len(r1["nodes"]) == len(r2["nodes"])
    assert len(r1["edges"]) == len(r2["edges"])

def test_cache_miss_after_file_change(tmp_path):
    dst = tmp_path / "a.py"
    dst.write_text("def foo(): pass\n")
    r1 = extract([dst])

    dst.write_text("def foo(): pass\ndef bar(): pass\n")
    r2 = extract([dst])
    # bar() should appear in the second result
    labels2 = [n["label"] for n in r2["nodes"]]
    assert any("bar" in l for l in labels2)


# ── SQL ───────────────────────────────────────────────────────────────────────

def _extract_sql_or_skip(fixture: str = "sample.sql"):
    pytest.importorskip("tree_sitter_sql")
    return extract_sql(FIXTURES / fixture)


def test_sql_finds_tables():
    r = _extract_sql_or_skip()
    labels = [n["label"] for n in r["nodes"]]
    assert any("users" in l for l in labels)
    assert any("organizations" in l for l in labels)

def test_sql_finds_view():
    r = _extract_sql_or_skip()
    labels = [n["label"] for n in r["nodes"]]
    assert any("active_users" in l for l in labels)

def test_sql_finds_function():
    r = _extract_sql_or_skip()
    labels = [n["label"] for n in r["nodes"]]
    assert any("get_user" in l for l in labels)

def test_sql_emits_foreign_key_edge():
    r = _extract_sql_or_skip()
    relations = {e["relation"] for e in r["edges"]}
    assert "references" in relations

def test_sql_emits_reads_from_edge():
    r = _extract_sql_or_skip()
    relations = {e["relation"] for e in r["edges"]}
    assert "reads_from" in relations

def test_sql_no_dangling_edges():
    r = _extract_sql_or_skip()
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"dangling source: {e['source']}"

def test_sql_alter_table_fk_edge():
    """ALTER TABLE ... FOREIGN KEY ... REFERENCES produces a references edge."""
    r = _extract_sql_or_skip("sample_alter_fk.sql")
    fk_edges = [e for e in r["edges"] if e["relation"] == "references"]
    assert len(fk_edges) >= 1
    node_ids = {n["id"] for n in r["nodes"]}
    for e in fk_edges:
        assert e["source"] in node_ids, f"dangling source: {e['source']}"
        assert e["target"] in node_ids, f"dangling target: {e['target']}"

def test_sql_schema_qualified_names():
    """Schema-qualified table names (Schema.Table) are preserved."""
    r = _extract_sql_or_skip("sample_schema_qualified.sql")
    labels = [n["label"] for n in r["nodes"]]
    assert any("Sales.Customer" in l for l in labels)
    assert any("Sales.SalesOrder" in l for l in labels)

def test_sql_schema_qualified_alter_fk():
    """ALTER TABLE with schema-qualified names produces correct edges."""
    r = _extract_sql_or_skip("sample_schema_qualified.sql")
    fk_edges = [e for e in r["edges"] if e["relation"] == "references"]
    assert len(fk_edges) >= 1
    node_ids = {n["id"] for n in r["nodes"]}
    for e in fk_edges:
        assert e["source"] in node_ids, f"dangling source: {e['source']}"
        assert e["target"] in node_ids, f"dangling target: {e['target']}"
