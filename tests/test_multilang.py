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


def _normalize_symbol_label(label: str) -> str:
    return label.strip("()").lstrip(".")


def _edge_labels(result, relation, context=None):
    labels = {n["id"]: _normalize_symbol_label(n["label"]) for n in result["nodes"]}
    pairs = set()
    for e in result["edges"]:
        if e.get("relation") != relation:
            continue
        if context is not None and e.get("context") != context:
            continue
        pairs.add((labels.get(e["source"], e["source"]), labels.get(e["target"], e["target"])))
    return pairs


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


def test_go_embeds_struct_field():
    r = extract_go(FIXTURES / "sample.go")
    assert ("DataProcessor", "BaseProcessor") in _edge_labels(r, "embeds")


def test_go_interface_embedding_emits_embeds():
    r = extract_go(FIXTURES / "sample.go")
    assert ("ReaderLogger", "Logger") in _edge_labels(r, "embeds")


def test_go_struct_named_field_emits_field_context():
    r = extract_go(FIXTURES / "sample.go")
    assert ("DataProcessor", "Result") in _edge_labels(r, "references", "field")


def test_go_method_parameter_return_contexts():
    r = extract_go(FIXTURES / "sample.go")
    assert ("Build", "DataProcessor") in _edge_labels(r, "references", "parameter_type")
    assert ("Build", "Result") in _edge_labels(r, "references", "return_type")


def test_go_method_declaration_emits_refs_only_when_name_present():
    """Regression: review feedback flagged a hypothetical UnboundLocalError in
    extract_go's method_declaration branch if `name_node` were None. Statically
    verify that every use of `method_nid` (and the `emit_go_method_refs` call
    that consumes it) is guarded by a `name_node` truthiness check — either
    nested inside `if name_node:` or following an early `if not name_node: return`.
    Same for function_declaration and `func_nid`.
    """
    import ast
    import inspect
    from graphify.extract import extract_go

    tree = ast.parse(inspect.getsource(extract_go))

    def _find_branch(root: ast.AST, type_literal: str) -> ast.If | None:
        """Return the `if t == '<type_literal>':` branch inside the walk function."""
        for child in ast.walk(root):
            if (isinstance(child, ast.If)
                    and isinstance(child.test, ast.Compare)
                    and isinstance(child.test.left, ast.Name)
                    and child.test.left.id == "t"
                    and len(child.test.comparators) == 1
                    and isinstance(child.test.comparators[0], ast.Constant)
                    and child.test.comparators[0].value == type_literal):
                return child
        return None

    method_branch = _find_branch(tree, "method_declaration")
    function_branch = _find_branch(tree, "function_declaration")
    assert method_branch is not None, "method_declaration branch not found in extract_go"
    assert function_branch is not None, "function_declaration branch not found in extract_go"

    def _is_early_return_on_falsy_name_node(stmt: ast.AST) -> bool:
        """True iff `stmt` is `if not name_node: return` (or raise/continue/break)."""
        if not isinstance(stmt, ast.If):
            return False
        test = stmt.test
        is_falsy_check = (
            isinstance(test, ast.UnaryOp)
            and isinstance(test.op, ast.Not)
            and isinstance(test.operand, ast.Name)
            and test.operand.id == "name_node"
        )
        if not is_falsy_check:
            return False
        terminators = (ast.Return, ast.Raise, ast.Continue, ast.Break)
        return any(isinstance(s, terminators) for s in stmt.body)

    def _guarded_by_name_node(branch: ast.If, var_name: str) -> bool:
        """True iff every read of `var_name` in `branch` is guarded by a
        `name_node` truthiness check — either lexically nested under
        `if name_node:` or after a preceding `if not name_node: return`."""
        parents: dict[int, ast.AST] = {}
        for parent in ast.walk(branch):
            for child in ast.iter_child_nodes(parent):
                parents[id(child)] = parent

        def _stmt_chain(start: ast.AST) -> list[tuple[ast.stmt, list[ast.stmt]]]:
            """Walk up to each enclosing statement-list, returning (stmt, siblings)."""
            chain: list[tuple[ast.stmt, list[ast.stmt]]] = []
            cur: ast.AST | None = start
            while cur is not None:
                parent = parents.get(id(cur))
                if parent is None:
                    break
                if isinstance(cur, ast.stmt):
                    for attr in ("body", "orelse", "finalbody"):
                        siblings = getattr(parent, attr, None)
                        if isinstance(siblings, list) and cur in siblings:
                            chain.append((cur, siblings))
                            break
                cur = parent
            return chain

        def _is_guarded(use: ast.AST) -> bool:
            for stmt, siblings in _stmt_chain(use):
                parent = parents.get(id(stmt))
                # Case 1: lexically nested under `if name_node:` body
                if (isinstance(parent, ast.If)
                        and isinstance(parent.test, ast.Name)
                        and parent.test.id == "name_node"
                        and stmt in parent.body):
                    return True
                # Case 2: a preceding sibling is `if not name_node: return`
                idx = siblings.index(stmt)
                if any(_is_early_return_on_falsy_name_node(s) for s in siblings[:idx]):
                    return True
            return False

        for node in ast.walk(branch):
            if isinstance(node, ast.Name) and node.id == var_name:
                if not _is_guarded(node):
                    return False
        return True

    assert _guarded_by_name_node(method_branch, "method_nid"), (
        "method_nid use is not guarded by a name_node check in method_declaration branch"
    )
    assert _guarded_by_name_node(function_branch, "func_nid"), (
        "func_nid use is not guarded by a name_node check in function_declaration branch"
    )

    # Negative control: confirm the checker would actually reject the buggy
    # layout the reviewer described. A `method_nid` reference dangling without
    # any name_node guard must be caught.
    bad_source = (
        "def walk(node):\n"
        "    if t == 'method_declaration':\n"
        "        name_node = node.child_by_field_name('name')\n"
        "        if name_node:\n"
        "            method_nid = make_id('x')\n"
        "        emit_go_method_refs(node, method_nid, 1)\n"
        "        return\n"
    )
    bad_tree = ast.parse(bad_source)
    bad_branch = _find_branch(bad_tree, "method_declaration")
    assert bad_branch is not None
    assert not _guarded_by_name_node(bad_branch, "method_nid"), (
        "checker should reject method_nid used without a name_node guard"
    )


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


def test_rust_trait_impl_emits_implements():
    r = extract_rust(FIXTURES / "sample.rs")
    assert ("DataProcessor", "Processor") in _edge_labels(r, "implements")


def test_rust_supertrait_emits_inherits():
    r = extract_rust(FIXTURES / "sample.rs")
    assert ("Logger", "Processor") in _edge_labels(r, "inherits")


def test_rust_struct_field_emits_field_context():
    r = extract_rust(FIXTURES / "sample.rs")
    assert ("DataProcessor", "Result") in _edge_labels(r, "references", "field")
    assert ("DataProcessor", "DataProcessor") not in _edge_labels(r, "references", "field")


def test_rust_method_parameter_return_and_generic_contexts():
    r = extract_rust(FIXTURES / "sample.rs")
    assert ("build", "DataProcessor") in _edge_labels(r, "references", "parameter_type")
    assert ("build", "Result") in _edge_labels(r, "references", "return_type")
    assert ("build", "DataProcessor") in _edge_labels(r, "references", "generic_arg")


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
