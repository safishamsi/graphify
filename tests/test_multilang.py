"""Tests for multi-language AST extraction: JS/TS, Go, Rust, SQL, Solidity."""
from __future__ import annotations
import shutil
from pathlib import Path
import pytest
from graphify.extract import extract_js, extract_go, extract_rust, extract, extract_sql, extract_solidity

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

def test_sql_finds_tables():
    r = extract_sql(FIXTURES / "sample.sql")
    labels = [n["label"] for n in r["nodes"]]
    assert any("users" in l for l in labels)
    assert any("organizations" in l for l in labels)

def test_sql_finds_view():
    r = extract_sql(FIXTURES / "sample.sql")
    labels = [n["label"] for n in r["nodes"]]
    assert any("active_users" in l for l in labels)

def test_sql_finds_function():
    r = extract_sql(FIXTURES / "sample.sql")
    labels = [n["label"] for n in r["nodes"]]
    assert any("get_user" in l for l in labels)

def test_sql_emits_foreign_key_edge():
    r = extract_sql(FIXTURES / "sample.sql")
    relations = {e["relation"] for e in r["edges"]}
    assert "references" in relations

def test_sql_emits_reads_from_edge():
    r = extract_sql(FIXTURES / "sample.sql")
    relations = {e["relation"] for e in r["edges"]}
    assert "reads_from" in relations

def test_sql_no_dangling_edges():
    r = extract_sql(FIXTURES / "sample.sql")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"dangling source: {e['source']}"

def test_sql_alter_table_fk_edge():
    """ALTER TABLE ... FOREIGN KEY ... REFERENCES produces a references edge."""
    r = extract_sql(FIXTURES / "sample_alter_fk.sql")
    fk_edges = [e for e in r["edges"] if e["relation"] == "references"]
    assert len(fk_edges) >= 1
    node_ids = {n["id"] for n in r["nodes"]}
    for e in fk_edges:
        assert e["source"] in node_ids, f"dangling source: {e['source']}"
        assert e["target"] in node_ids, f"dangling target: {e['target']}"

def test_sql_schema_qualified_names():
    """Schema-qualified table names (Schema.Table) are preserved."""
    r = extract_sql(FIXTURES / "sample_schema_qualified.sql")
    labels = [n["label"] for n in r["nodes"]]
    assert any("Sales.Customer" in l for l in labels)
    assert any("Sales.SalesOrder" in l for l in labels)

def test_sql_schema_qualified_alter_fk():
    """ALTER TABLE with schema-qualified names produces correct edges."""
    r = extract_sql(FIXTURES / "sample_schema_qualified.sql")
    fk_edges = [e for e in r["edges"] if e["relation"] == "references"]
    assert len(fk_edges) >= 1
    node_ids = {n["id"] for n in r["nodes"]}
    for e in fk_edges:
        assert e["source"] in node_ids, f"dangling source: {e['source']}"
        assert e["target"] in node_ids, f"dangling target: {e['target']}"


# ── Solidity ──────────────────────────────────────────────────────────────────

def _sol():
    pytest.importorskip("tree_sitter_solidity")
    return extract_solidity(FIXTURES / "sample.sol")


def test_solidity_no_error():
    r = _sol()
    assert "error" not in r, r.get("error")


def test_solidity_finds_contract_interface_library():
    labels = [n["label"] for n in _sol()["nodes"]]
    assert "Token" in labels
    assert "IERC20" in labels
    assert "MathLib" in labels
    assert "Ownable" in labels


def test_solidity_finds_functions_modifier_constructor():
    labels = [n["label"] for n in _sol()["nodes"]]
    assert "transfer()" in labels
    assert "add()" in labels
    assert "onlyOwner()" in labels
    assert "constructor()" in labels
    assert "receive()" in labels
    assert "fallback()" in labels


def test_solidity_finds_events_errors_struct_enum_state_var():
    labels = [n["label"] for n in _sol()["nodes"]]
    assert "Minted" in labels
    assert "InsufficientBalance" in labels
    assert "Account" in labels
    assert "Status" in labels
    assert "balances" in labels


def test_solidity_finds_free_function():
    labels = [n["label"] for n in _sol()["nodes"]]
    assert "freeFunction()" in labels


def test_solidity_inheritance_edges():
    relations = {e["relation"] for e in _sol()["edges"]}
    assert "inherits" in relations


def test_solidity_import_edges():
    relations = {e["relation"] for e in _sol()["edges"]}
    assert "imports" in relations
    assert "imports_from" in relations


def test_solidity_emits_edge():
    relations = {e["relation"] for e in _sol()["edges"]}
    assert "emits" in relations


def test_solidity_applies_modifier_edge():
    relations = {e["relation"] for e in _sol()["edges"]}
    assert "applies_modifier" in relations


def test_solidity_using_for_emits_imports_from_with_context():
    edges = [e for e in _sol()["edges"]
             if e["relation"] == "imports_from" and e.get("context") == "using_for"]
    assert edges, "expected `using ... for ...` to emit imports_from edge with context=using_for"


def test_solidity_member_call_low_confidence():
    edges = [e for e in _sol()["edges"]
             if e["relation"] == "calls" and e.get("context") == "member_call"]
    assert edges, "expected at least one member call (e.g. .add())"
    assert all(e["confidence_score"] < 1.0 for e in edges)


def test_solidity_no_dangling_sources():
    r = _sol()
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"dangling source: {e['source']}"


def test_solidity_inheritance_resolves_to_in_file_def():
    """Token is IERC20, Ownable — both ancestors are defined in the same file,
    so inherits edges should target the in-file declaration nodes (not bare names)."""
    r = _sol()
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    inherits = [(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "inherits"]
    # Token contract id contains "token"; ancestors should resolve to the contract-scoped ids
    targets = {node_by_id[t] for s, t in inherits if s in node_by_id}
    assert "IERC20" in targets
    assert "Ownable" in targets


def test_solidity_modifier_resolves_to_in_file_def():
    r = _sol()
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    mods = [e for e in r["edges"] if e["relation"] == "applies_modifier"]
    assert mods, "expected at least one applies_modifier edge"
    # Target should be the in-file modifier definition (file-stem prefix in id)
    for e in mods:
        target_id = e["target"]
        assert "_" in target_id, f"modifier target {target_id} looks like a bare unresolved name"


def test_solidity_emit_resolves_to_in_file_event():
    r = _sol()
    emits = [e for e in r["edges"] if e["relation"] == "emits"]
    assert emits, "expected at least one emits edge"
    for e in emits:
        # In-file event ids have the contract-stem prefix and 'event' segment
        assert "event" in e["target"], f"emit target {e['target']} not resolved to in-file event"


def test_solidity_revert_not_treated_as_call():
    """`revert NotOwner(msg.sender)` constructs an error — should not produce a calls edge."""
    r = _sol()
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    call_targets = {
        node_by_id.get(e["target"], e["target"])
        for e in r["edges"] if e["relation"] == "calls"
    }
    assert "NotOwner" not in call_targets
    assert "InsufficientBalance" not in call_targets


def test_solidity_builtins_filtered_from_calls():
    """require/assert/keccak256 etc. should not show up as call targets."""
    r = _sol()
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    call_targets = {
        node_by_id.get(e["target"], e["target"])
        for e in r["edges"] if e["relation"] == "calls"
    }
    for builtin in ("require", "assert", "revert", "keccak256", "address"):
        assert builtin not in call_targets, f"{builtin} leaked into calls"


# Multi-file Solidity fixture exercises cross-file imports + inheritance.
SOL_DIR = FIXTURES / "solidity"


def _sol_multi():
    pytest.importorskip("tree_sitter_solidity")
    return {
        "Ownable": extract_solidity(SOL_DIR / "Ownable.sol"),
        "Token": extract_solidity(SOL_DIR / "Token.sol"),
        "Vault": extract_solidity(SOL_DIR / "Vault.sol"),
    }


def test_solidity_multifile_no_errors():
    for name, r in _sol_multi().items():
        assert "error" not in r, f"{name}: {r.get('error')}"


def test_solidity_multifile_vault_imports_ownable_and_token():
    r = _sol_multi()["Vault"]
    relations = [(e["relation"], e.get("context", "")) for e in r["edges"]
                 if e["relation"] in ("imports", "imports_from")]
    # Named import: import {Ownable} from "./Ownable.sol"
    assert any(rel == "imports_from" for rel, _ in relations), "expected named import edge"
    # Bare import: import "./Token.sol"
    assert any(rel == "imports" for rel, _ in relations), "expected bare import edge"


def test_solidity_multifile_vault_inherits_ownable_unresolved_cross_file():
    """Vault inherits Ownable, but Ownable lives in another file — resolution is
    per-file, so the inherits target is the bare name (a known limitation)."""
    r = _sol_multi()["Vault"]
    inherits = [e for e in r["edges"] if e["relation"] == "inherits"]
    assert inherits, "Vault should have an inherits edge"
    # Cross-file ancestor — bare-name target is acceptable until cross-file resolution lands
    target_labels = {n["label"] for n in r["nodes"] if n["id"] == inherits[0]["target"]}
    assert "Ownable" in target_labels


def test_solidity_multifile_token_using_for_resolves_in_file():
    """SafeMath is defined in Token.sol — `using SafeMath for uint256` should
    resolve to the in-file library nid."""
    r = _sol_multi()["Token"]
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    using_edges = [e for e in r["edges"]
                   if e["relation"] == "imports_from" and e.get("context") == "using_for"]
    assert using_edges
    for e in using_edges:
        assert node_by_id.get(e["target"]) == "SafeMath"
