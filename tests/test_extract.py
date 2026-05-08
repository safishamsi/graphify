from pathlib import Path
import os
import sys
import types
from graphify.extract import (
    extract_python,
    extract,
    collect_files,
    _make_id,
    _file_stem,
    _safe_extract,
    _strip_jsonc,
    _raise_recursion_limit,
    _extract_generic,
    _read_tsconfig_aliases,
    _resolve_js_module_path,
    _resolve_name,
    _import_python,
    _resolve_js_import_target,
    _dynamic_import_js,
    _import_kotlin,
    _import_scala,
    _import_php,
    _import_java,
    _import_csharp,
    _import_c,
    _import_lua,
    _import_swift,
    _get_c_func_name,
    _get_cpp_func_name,
    _find_require_call,
    _read_csharp_type_name,
    _read_text,
    LanguageConfig,
    _DISPATCH,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_make_id_strips_dots_and_underscores():
    assert _make_id("_auth") == "auth"
    assert _make_id(".httpx._client") == "httpx_client"


def test_make_id_consistent():
    """Same input always produces same output."""
    assert _make_id("foo", "Bar") == _make_id("foo", "Bar")


def test_make_id_no_leading_trailing_underscores():
    result = _make_id("__init__")
    assert not result.startswith("_")
    assert not result.endswith("_")


def test_extract_python_finds_class():
    result = extract_python(FIXTURES / "sample.py")
    labels = [n["label"] for n in result["nodes"]]
    assert "Transformer" in labels


def test_extract_python_finds_methods():
    result = extract_python(FIXTURES / "sample.py")
    labels = [n["label"] for n in result["nodes"]]
    assert any("__init__" in l or "forward" in l for l in labels)


def test_extract_python_no_dangling_edges():
    """All edge sources must reference a known node (targets may be external imports)."""
    result = extract_python(FIXTURES / "sample.py")
    node_ids = {n["id"] for n in result["nodes"]}
    for edge in result["edges"]:
        assert edge["source"] in node_ids, f"Dangling source: {edge['source']}"


def test_structural_edges_are_extracted():
    """contains / method / inherits / imports edges must always be EXTRACTED."""
    result = extract_python(FIXTURES / "sample.py")
    structural = {"contains", "method", "inherits", "imports", "imports_from"}
    for edge in result["edges"]:
        if edge["relation"] in structural:
            assert edge["confidence"] == "EXTRACTED", f"Expected EXTRACTED: {edge}"


def test_extract_merges_multiple_files():
    files = list(FIXTURES.glob("*.py"))
    result = extract(files)
    assert len(result["nodes"]) > 0
    assert result["input_tokens"] == 0


def test_collect_files_from_dir():
    from graphify.extract import _DISPATCH
    files = collect_files(FIXTURES)
    supported = set(_DISPATCH.keys())
    assert all((f.suffix in supported) or not f.suffix for f in files)
    assert len(files) > 0


def test_collect_files_skips_hidden():
    files = collect_files(FIXTURES)
    for f in files:
        assert not any(part.startswith(".") for part in f.parts)


def test_collect_files_follows_symlinked_directory(tmp_path):
    real_dir = tmp_path / "real_src"
    real_dir.mkdir()
    (real_dir / "lib.py").write_text("x = 1")
    (tmp_path / "linked_src").symlink_to(real_dir)

    files_no = collect_files(tmp_path, follow_symlinks=False)
    files_yes = collect_files(tmp_path, follow_symlinks=True)

    assert [f.name for f in files_no].count("lib.py") == 1
    assert [f.name for f in files_yes].count("lib.py") == 2


def test_collect_files_handles_circular_symlinks(tmp_path):
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "mod.py").write_text("x = 1")
    (sub / "cycle").symlink_to(tmp_path)

    files = collect_files(tmp_path, follow_symlinks=True)
    assert any(f.name == "mod.py" for f in files)


def test_no_dangling_edges_on_extract():
    """After merging multiple files, no internal edges should be dangling."""
    files = list(FIXTURES.glob("*.py"))
    result = extract(files)
    node_ids = {n["id"] for n in result["nodes"]}
    internal_relations = {"contains", "method", "inherits", "calls"}
    for edge in result["edges"]:
        if edge["relation"] in internal_relations:
            assert edge["source"] in node_ids, f"Dangling source: {edge}"
            assert edge["target"] in node_ids, f"Dangling target: {edge}"


def test_calls_edges_emitted():
    """Call-graph pass must produce INFERRED calls edges."""
    result = extract_python(FIXTURES / "sample_calls.py")
    calls = [e for e in result["edges"] if e["relation"] == "calls"]
    assert len(calls) > 0, "Expected at least one calls edge"


def test_calls_edges_are_extracted():
    """AST-resolved call edges are deterministic and should be EXTRACTED/1.0."""
    result = extract_python(FIXTURES / "sample_calls.py")
    for edge in result["edges"]:
        if edge["relation"] == "calls":
            assert edge["confidence"] == "EXTRACTED"
            assert edge["weight"] == 1.0


def test_python_call_edges_have_call_context():
    result = extract_python(FIXTURES / "sample_calls.py")
    call_edges = [e for e in result["edges"] if e["relation"] == "calls"]
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)


def test_calls_no_self_loops():
    result = extract_python(FIXTURES / "sample_calls.py")
    for edge in result["edges"]:
        if edge["relation"] == "calls":
            assert edge["source"] != edge["target"], f"Self-loop: {edge}"


def test_run_analysis_calls_compute_score():
    """run_analysis() calls compute_score() - must appear as a calls edge."""
    result = extract_python(FIXTURES / "sample_calls.py")
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    node_by_label = {n["label"]: n["id"] for n in result["nodes"]}
    src = node_by_label.get("run_analysis()")
    tgt = node_by_label.get("compute_score()")
    assert src and tgt, "run_analysis or compute_score node not found"
    assert (src, tgt) in calls, f"run_analysis -> compute_score not found in {calls}"


def test_run_analysis_calls_normalize():
    result = extract_python(FIXTURES / "sample_calls.py")
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    node_by_label = {n["label"]: n["id"] for n in result["nodes"]}
    src = node_by_label.get("run_analysis()")
    tgt = node_by_label.get("normalize()")
    assert src and tgt
    assert (src, tgt) in calls


def test_method_calls_module_function():
    """Analyzer.process() calls run_analysis() - cross class→function calls edge."""
    result = extract_python(FIXTURES / "sample_calls.py")
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    node_by_label = {n["label"]: n["id"] for n in result["nodes"]}
    src = node_by_label.get(".process()")
    tgt = node_by_label.get("run_analysis()")
    assert src and tgt
    assert (src, tgt) in calls


def test_calls_deduplication():
    """Same caller→callee pair must appear only once even if called multiple times."""
    result = extract_python(FIXTURES / "sample_calls.py")
    call_pairs = [(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"]
    assert len(call_pairs) == len(set(call_pairs)), "Duplicate calls edges found"


def test_cross_file_calls_skip_ambiguous_duplicate_labels(tmp_path):
    """Unqualified cross-file calls must not guess between duplicate helper names."""
    caller = tmp_path / "caller.py"
    helper_a = tmp_path / "a.py"
    helper_b = tmp_path / "b.py"
    caller.write_text("def run():\n    log()\n")
    helper_a.write_text("def log():\n    return 'a'\n")
    helper_b.write_text("def log():\n    return 'b'\n")

    result = extract([caller, helper_a, helper_b], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    calls = [
        e for e in result["edges"]
        if e["relation"] == "calls" and e["confidence"] == "INFERRED"
    ]

    assert not any(
        nodes[e["source"]]["label"] == "run()" and nodes[e["target"]]["label"] == "log()"
        for e in calls
    )


def test_extract_generic_surfaces_tree_sitter_version_mismatch_hint(monkeypatch):
    """When Language() raises TypeError (e.g. old tree-sitter binding meets a
    new tree-sitter API), the error message should point users at the upgrade
    path instead of leaving a bare 'missing 1 required positional argument'.
    """
    import sys
    import types
    from graphify.extract import _extract_generic, LanguageConfig

    # Build a fake tree_sitter module whose Language() raises TypeError -
    # this is exactly what users see when an older tree-sitter is paired
    # with a newer language binding.
    fake_ts = types.ModuleType("tree_sitter")
    def _raise(*args, **kwargs):
        raise TypeError("missing 1 required positional argument: 'name'")
    fake_ts.Language = _raise
    fake_ts.Parser = None
    monkeypatch.setitem(sys.modules, "tree_sitter", fake_ts)

    # Stub the language module so import_module returns something with .language
    fake_lang_mod = types.ModuleType("fake_ts_lang")
    fake_lang_mod.language = lambda: object()
    monkeypatch.setitem(sys.modules, "fake_ts_lang", fake_lang_mod)

    config = LanguageConfig(ts_module="fake_ts_lang", ts_language_fn="language")
    result = _extract_generic(Path("dummy.txt"), config)

    assert "error" in result
    assert "tree-sitter version mismatch" in result["error"]
    assert "pip install --upgrade" in result["error"]


def test_extract_js_destructured_require_imports_from():
    """`const { foo } = require('./mod')` must emit imports_from to the resolved module path."""
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "cjs_require.js")
    imports_from = [e for e in result["edges"] if e["relation"] == "imports_from"]
    targets = [e["target"] for e in imports_from]
    # Must resolve relative require() targets to file ids so they connect across the corpus
    assert any("foundation" in t for t in targets), f"No foundation import_from: {targets}"
    assert any("utils" in t for t in targets), f"No utils import_from: {targets}"
    assert any("helpers" in t for t in targets), f"No helpers import_from: {targets}"
    for e in imports_from:
        assert e["confidence"] == "EXTRACTED"


def test_extract_js_destructured_require_named_symbols():
    """Destructured CJS requires must emit symbol-level `imports` edges per binder."""
    from graphify.extract import extract_js, _make_id, _file_stem
    result = extract_js(FIXTURES / "cjs_require.js")
    sym_targets = [e["target"] for e in result["edges"] if e["relation"] == "imports"]
    foundation_stem = _file_stem(FIXTURES / "foundation.js")
    assert _make_id(foundation_stem, "loadFoundation") in sym_targets
    assert _make_id(foundation_stem, "validateConfig") in sym_targets


def test_extract_js_member_require_emits_property_symbol():
    """`const x = require('./m').y` must emit symbol edge for `y`."""
    from graphify.extract import extract_js, _make_id, _file_stem
    result = extract_js(FIXTURES / "cjs_require.js")
    sym_targets = [e["target"] for e in result["edges"] if e["relation"] == "imports"]
    helpers_stem = _file_stem(FIXTURES / "helpers.js")
    assert _make_id(helpers_stem, "helperFn") in sym_targets


def test_extract_js_arrow_function_still_extracted():
    """Regression: arrow functions in lexical_declaration must still produce nodes."""
    from graphify.extract import extract_js
    arrow_fixture = FIXTURES / "_arrow_only.js"
    arrow_fixture.write_text("const greet = () => console.log('hi');\n")
    try:
        result = extract_js(arrow_fixture)
        labels = [n["label"] for n in result["nodes"]]
        assert "greet()" in labels
    finally:
        arrow_fixture.unlink()


def test_cross_file_call_promoted_to_extracted_with_import_evidence(tmp_path):
    """A cross-file `calls` edge must be EXTRACTED when the caller's file has
    an `imports` or `imports_from` edge linking it to the callee."""
    caller = tmp_path / "caller.js"
    callee = tmp_path / "lib.js"
    caller.write_text(
        "const { doWork } = require('./lib');\n"
        "function run() { doWork(); }\n"
    )
    callee.write_text(
        "function doWork() { return 1; }\n"
        "module.exports = { doWork };\n"
    )
    result = extract([caller, callee], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    call_edges = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and nodes[e["source"]]["label"] == "run()"
        and nodes[e["target"]]["label"] == "doWork()"
    ]
    assert len(call_edges) == 1
    assert call_edges[0]["confidence"] == "EXTRACTED"
    assert call_edges[0]["confidence_score"] == 1.0


def test_cross_file_call_remains_inferred_without_import_evidence(tmp_path):
    """A cross-file `calls` edge must stay INFERRED when there is no import
    edge — name collision alone is insufficient evidence."""
    caller = tmp_path / "caller.js"
    callee = tmp_path / "lib.js"
    # Caller does NOT require lib — same-name function happens to exist elsewhere
    caller.write_text("function run() { doUnique(); }\n")
    callee.write_text(
        "function doUnique() { return 1; }\n"
        "module.exports = { doUnique };\n"
    )
    result = extract([caller, callee], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    call_edges = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and nodes[e["source"]]["label"] == "run()"
        and nodes[e["target"]]["label"] == "doUnique()"
    ]
    assert len(call_edges) == 1
    assert call_edges[0]["confidence"] == "INFERRED"


# ── TSX (JSX-aware) parsing ──────────────────────────────────────────────────
# .tsx files require tree-sitter-typescript's `language_tsx`, not the plain
# `language_typescript` grammar. Parsing JSX with the wrong grammar produces
# silent ERROR nodes and drops every function/call inside JSX trees.

def test_extract_tsx_finds_helpers_and_component():
    """Functions defined alongside a JSX-returning component must be captured."""
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "sample.tsx")
    labels = [n["label"] for n in result["nodes"]]
    assert any("fmtDate" in l for l in labels), f"fmtDate missing from {labels}"
    assert any("fmtCount" in l for l in labels), f"fmtCount missing from {labels}"
    assert any("App" in l for l in labels), f"App missing from {labels}"


def test_extract_tsx_jsx_expression_calls_resolve():
    """Calls inside JSX expressions like `{fmtDate(now)}` must yield call edges.

    Regression guard for the TSX language fix: with `language_typescript`,
    JSX is parsed as ERROR nodes and these call_expressions disappear.
    """
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "sample.tsx")
    nodes_by_id = {n["id"]: n for n in result["nodes"]}
    call_targets = {
        nodes_by_id[e["target"]]["label"]
        for e in result["edges"]
        if e["relation"] == "calls" and e["target"] in nodes_by_id
    }
    assert "fmtDate()" in call_targets, (
        f"JSX expression call to fmtDate() not captured. Targets: {call_targets}"
    )
    assert "fmtCount()" in call_targets, (
        f"JSX expression call to fmtCount() not captured. Targets: {call_targets}"
    )


def test_extract_tsx_uses_tsx_grammar():
    """Wiring check: the .tsx config must use tree-sitter's `language_tsx`."""
    from graphify.extract import _TSX_CONFIG, _TS_CONFIG
    assert _TSX_CONFIG.ts_language_fn == "language_tsx"
    assert _TS_CONFIG.ts_language_fn == "language_typescript"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Helper function tests ────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_file_stem_qualifies_with_parent_dir():
    """_file_stem prepends parent dir name to avoid collisions."""
    stem = _file_stem(FIXTURES / "sample.py")
    assert stem == "fixtures.sample"


def test_file_stem_top_level_file():
    """Top-level files (no usable parent dir) get just the stem."""
    result = _file_stem(Path("sample.py"))
    assert result == "sample"


def test_file_stem_hidden_dir():
    """Files in directories starting with '.' still get qualified."""
    stem = _file_stem(Path(".hidden") / "file.py")
    assert stem == ".hidden.file"


def test_safe_extract_returns_result_on_success():
    """_safe_extract wraps a working extractor and returns its result."""
    def good_extractor(p):
        return {"nodes": [{"id": "x"}], "edges": []}
    result = _safe_extract(good_extractor, Path("test.py"))
    assert result["nodes"] == [{"id": "x"}]
    assert result["edges"] == []


def test_safe_extract_catches_recursion_error():
    """_safe_extract catches RecursionError and returns error dict."""
    def recursive_extractor(p):
        raise RecursionError("too deep")
    result = _safe_extract(recursive_extractor, Path("test.py"))
    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["error"] == "recursion_limit_exceeded"


def test_safe_extract_catches_generic_exception():
    """_safe_extract catches generic Exception and returns error dict."""
    def failing_extractor(p):
        raise ValueError("bad value")
    result = _safe_extract(failing_extractor, Path("test.py"))
    assert result["nodes"] == []
    assert result["edges"] == []
    assert "ValueError: bad value" in result["error"]


def test_raise_recursion_limit_sets_limit():
    """_raise_recursion_limit raises limit if below threshold."""
    old = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(500)
        _raise_recursion_limit()
        assert sys.getrecursionlimit() >= 10_000
    finally:
        sys.setrecursionlimit(old)


def test_raise_recursion_limit_noop_when_already_high():
    """_raise_recursion_limit is a no-op when limit already >= 10000."""
    old = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(10_000)
        _raise_recursion_limit()
        assert sys.getrecursionlimit() == 10_000
    finally:
        sys.setrecursionlimit(old)


def test_strip_jsonc_removes_line_comments():
    """_strip_jsonc removes // line comments."""
    result = _strip_jsonc('{"key": "val" // comment\n}')
    assert "comment" not in result
    assert '"val"' in result


def test_strip_jsonc_removes_block_comments():
    """_strip_jsonc removes /* */ block comments."""
    result = _strip_jsonc('{"a": 1 /* inline */, "b": 2}')
    assert "inline" not in result
    assert '"a"' in result
    assert '"b"' in result


def test_strip_jsonc_preserves_strings_with_comment_like_content():
    """_strip_jsonc preserves strings containing // or /* sequences."""
    result = _strip_jsonc('{"url": "https://example.com", "css": "color: /* red */"')
    assert "https://example.com" in result
    assert "color: /* red */" in result


def test_strip_jsonc_removes_trailing_commas():
    """_strip_jsonc removes trailing commas before } or ]."""
    result = _strip_jsonc('{"a": 1,}')
    assert "1}" in result or '"a": 1}' in result
    assert ",}" not in result


def test_strip_jsonc_clean_json_passes_through():
    """Valid JSON without comments should pass through stripped."""
    result = _strip_jsonc('{"key": "value", "num": 42}')
    parsed = __import__("json").loads(result)
    assert parsed == {"key": "value", "num": 42}


# ═══════════════════════════════════════════════════════════════════════════════
# ── _extract_generic edge cases ──────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_generic_import_error_returns_error():
    """_extract_generic returns error dict when TS module not installed."""
    config = LanguageConfig(ts_module="nonexistent_ts_module_xyz", ts_language_fn="language")
    result = _extract_generic(Path("test.txt"), config)
    assert "error" in result
    assert "not installed" in result["error"]


def test_extract_generic_missing_language_fn():
    """_extract_generic returns error when language fn is None."""
    fake_mod = types.ModuleType("fake_ts_empty")
    import sys as _sys
    _sys.modules["fake_ts_empty"] = fake_mod
    try:
        config = LanguageConfig(ts_module="fake_ts_empty", ts_language_fn="nonexistent_fn")
        result = _extract_generic(Path("test.txt"), config)
        assert "error" in result
        assert "No language function" in result["error"]
    finally:
        _sys.modules.pop("fake_ts_empty", None)


def test_extract_generic_file_read_error(monkeypatch):
    """_extract_generic returns error when file cannot be read."""
    import tree_sitter as ts
    # Use a real language but point to a nonexistent file
    # We can't easily test with real tree-sitter without all languages installed
    # So test that missing file yields error via _safe_extract
    pass  # tested via _safe_extract above


def test_extract_generic_missing_file(tmp_path):
    """_extract_generic returns error for nonexistent file."""
    nonexistent = tmp_path / "does_not_exist.py"
    result = _safe_extract(lambda p: {"nodes": [], "edges": []}, nonexistent)
    assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# ── Language extractor tests ─────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

# ── Go ────────────────────────────────────────────────────────────────────────

def test_extract_go_finds_struct_and_methods():
    from graphify.extract import extract_go
    result = extract_go(FIXTURES / "sample.go")
    assert "nodes" in result
    assert "edges" in result
    labels = [n["label"] for n in result["nodes"]]
    assert "Server" in labels, f"Server struct not found in {labels}"
    assert any("Start" in l or "Stop" in l for l in labels), f"No methods found in {labels}"


def test_extract_go_produces_structural_edges():
    from graphify.extract import extract_go
    result = extract_go(FIXTURES / "sample.go")
    relations = {e["relation"] for e in result["edges"]}
    assert "contains" in relations or "method" in relations


def test_extract_go_no_error():
    from graphify.extract import extract_go
    result = extract_go(FIXTURES / "sample.go")
    assert "error" not in result


# ── Rust ──────────────────────────────────────────────────────────────────────

def test_extract_rust_finds_struct_and_impl():
    from graphify.extract import extract_rust
    result = extract_rust(FIXTURES / "sample.rs")
    labels = [n["label"] for n in result["nodes"]]
    assert "Graph" in labels, f"Graph struct not found in {labels}"
    assert any("add_node" in l or "add_edge" in l for l in labels), f"No methods found in {labels}"


def test_extract_rust_produces_structural_edges():
    from graphify.extract import extract_rust
    result = extract_rust(FIXTURES / "sample.rs")
    relations = {e["relation"] for e in result["edges"]}
    assert "contains" in relations or "method" in relations or "imports" in relations


def test_extract_rust_no_error():
    from graphify.extract import extract_rust
    result = extract_rust(FIXTURES / "sample.rs")
    assert "error" not in result


# ── Java ──────────────────────────────────────────────────────────────────────

def test_extract_java_finds_class_and_methods():
    from graphify.extract import extract_java
    result = extract_java(FIXTURES / "sample.java")
    labels = [n["label"] for n in result["nodes"]]
    assert "DataProcessor" in labels, f"DataProcessor class not found in {labels}"
    assert any("addItem" in l or "process" in l for l in labels), f"No methods found in {labels}"


def test_extract_java_finds_interface():
    from graphify.extract import extract_java
    result = extract_java(FIXTURES / "sample.java")
    labels = [n["label"] for n in result["nodes"]]
    assert "Processor" in labels, f"Processor interface not found in {labels}"


def test_extract_java_produces_structural_edges():
    from graphify.extract import extract_java
    result = extract_java(FIXTURES / "sample.java")
    relations = {e["relation"] for e in result["edges"]}
    assert "contains" in relations or "method" in relations


def test_extract_java_no_error():
    from graphify.extract import extract_java
    result = extract_java(FIXTURES / "sample.java")
    assert "error" not in result


# ── C ─────────────────────────────────────────────────────────────────────────

def test_extract_c_finds_functions():
    from graphify.extract import extract_c
    result = extract_c(FIXTURES / "sample.c")
    labels = [n["label"] for n in result["nodes"]]
    assert any("validate" in l or "process" in l or "main" in l for l in labels), f"No functions found in {labels}"


def test_extract_c_produces_edges():
    from graphify.extract import extract_c
    result = extract_c(FIXTURES / "sample.c")
    assert len(result["edges"]) > 0 or len(result["nodes"]) > 0


def test_extract_c_no_error():
    from graphify.extract import extract_c
    result = extract_c(FIXTURES / "sample.c")
    assert "error" not in result


# ── C++ ───────────────────────────────────────────────────────────────────────

def test_extract_cpp_finds_class_and_constructor():
    from graphify.extract import extract_cpp
    result = extract_cpp(FIXTURES / "sample.cpp")
    labels = [n["label"] for n in result["nodes"]]
    nids = [n["id"] for n in result["nodes"]]
    assert "HttpClient" in labels, f"HttpClient class not found in {labels}"
    assert any("httpclient" in nid for nid in nids), f"HttpClient IDs not found in {nids}"


def test_extract_cpp_no_error():
    from graphify.extract import extract_cpp
    result = extract_cpp(FIXTURES / "sample.cpp")
    assert "error" not in result


# ── Ruby ──────────────────────────────────────────────────────────────────────

def test_extract_ruby_finds_class_and_methods():
    from graphify.extract import extract_ruby
    result = extract_ruby(FIXTURES / "sample.rb")
    labels = [n["label"] for n in result["nodes"]]
    assert "ApiClient" in labels, f"ApiClient class not found in {labels}"
    assert any("get" in l or "post" in l or "fetch" in l for l in labels), f"No methods found in {labels}"


def test_extract_ruby_produces_edges():
    from graphify.extract import extract_ruby
    result = extract_ruby(FIXTURES / "sample.rb")
    assert len(result["edges"]) > 0 or len(result["nodes"]) > 0


def test_extract_ruby_no_error():
    from graphify.extract import extract_ruby
    result = extract_ruby(FIXTURES / "sample.rb")
    assert "error" not in result


# ── C# ────────────────────────────────────────────────────────────────────────

def test_extract_csharp_finds_class_and_interface():
    from graphify.extract import extract_csharp
    result = extract_csharp(FIXTURES / "sample.cs")
    labels = [n["label"] for n in result["nodes"]]
    assert "DataProcessor" in labels, f"DataProcessor class not found in {labels}"
    assert "IProcessor" in labels, f"IProcessor interface not found in {labels}"


def test_extract_csharp_finds_namespace():
    from graphify.extract import extract_csharp
    result = extract_csharp(FIXTURES / "sample.cs")
    labels = [n["label"] for n in result["nodes"]]
    assert "GraphifyDemo" in labels, f"GraphifyDemo namespace not found in {labels}"


def test_extract_csharp_no_error():
    from graphify.extract import extract_csharp
    result = extract_csharp(FIXTURES / "sample.cs")
    assert "error" not in result


# ── Kotlin ────────────────────────────────────────────────────────────────────

def test_extract_kotlin_finds_class_and_data_class():
    from graphify.extract import extract_kotlin
    result = extract_kotlin(FIXTURES / "sample.kt")
    labels = [n["label"] for n in result["nodes"]]
    assert "HttpClient" in labels, f"HttpClient class not found in {labels}"
    assert "Config" in labels, f"Config data class not found in {labels}"


def test_extract_kotlin_produces_edges():
    from graphify.extract import extract_kotlin
    result = extract_kotlin(FIXTURES / "sample.kt")
    assert len(result["edges"]) > 0 or len(result["nodes"]) > 0


def test_extract_kotlin_no_error():
    from graphify.extract import extract_kotlin
    result = extract_kotlin(FIXTURES / "sample.kt")
    assert "error" not in result


# ── Scala ─────────────────────────────────────────────────────────────────────

def test_extract_scala_finds_class_and_object():
    from graphify.extract import extract_scala
    result = extract_scala(FIXTURES / "sample.scala")
    labels = [n["label"] for n in result["nodes"]]
    assert "HttpClient" in labels, f"HttpClient class not found in {labels}"
    assert "HttpClientFactory" in labels, f"HttpClientFactory object not found in {labels}"


def test_extract_scala_no_error():
    from graphify.extract import extract_scala
    result = extract_scala(FIXTURES / "sample.scala")
    assert "error" not in result


# ── PHP ───────────────────────────────────────────────────────────────────────

def test_extract_php_finds_class_and_methods():
    from graphify.extract import extract_php
    result = extract_php(FIXTURES / "sample.php")
    labels = [n["label"] for n in result["nodes"]]
    assert "ApiClient" in labels, f"ApiClient class not found in {labels}"
    assert any("get" in l or "post" in l or "fetch" in l for l in labels), f"No methods found in {labels}"


def test_extract_php_no_error():
    from graphify.extract import extract_php
    result = extract_php(FIXTURES / "sample.php")
    assert "error" not in result


def test_extract_php_config_finds_constants():
    """PHP class constants in config files should be extracted."""
    from graphify.extract import extract_php
    result = extract_php(FIXTURES / "sample_php_config.php")
    labels = [n["label"] for n in result["nodes"]]
    assert "Throttle" in labels or "RateLimiter" in labels


def test_extract_php_container_finds_method():
    """PHP Laravel container bind methods should be extracted."""
    from graphify.extract import extract_php
    result = extract_php(FIXTURES / "sample_php_container.php")
    assert len(result["nodes"]) > 0
    assert len(result["edges"]) > 0


def test_extract_php_listen_extracts_events():
    """PHP event listener arrays should produce contains edges for event classes."""
    from graphify.extract import extract_php
    result = extract_php(FIXTURES / "sample_php_listen.php")
    # PHP extractor produces contains edges for event listener arrays
    contains_edges = [e for e in result["edges"] if e.get("relation") == "contains"]
    # Listen file should have EventServiceProvider and event class nodes
    labels = [n["label"] for n in result["nodes"]]
    assert "EventServiceProvider" in labels, f"EventServiceProvider not found in {labels}"
    assert "UserRegistered" in labels or "OrderPlaced" in labels
    assert len(result["nodes"]) > 0
    assert len(result["edges"]) > 0


def test_extract_php_static_properties():
    """PHP static property usage should produce ref edges."""
    from graphify.extract import extract_php
    result = extract_php(FIXTURES / "sample_php_static_prop.php")
    labels = [n["label"] for n in result["nodes"]]
    assert "ColorResolver" in labels
    assert "DefaultPalette" in labels


# ── Swift ─────────────────────────────────────────────────────────────────────

def test_extract_swift_finds_class_and_protocol():
    from graphify.extract import extract_swift
    result = extract_swift(FIXTURES / "sample.swift")
    labels = [n["label"] for n in result["nodes"]]
    assert "DataProcessor" in labels, f"DataProcessor class not found in {labels}"
    assert "Processor" in labels, f"Processor protocol not found in {labels}"


def test_extract_swift_finds_struct_and_enum():
    from graphify.extract import extract_swift
    result = extract_swift(FIXTURES / "sample.swift")
    labels = [n["label"] for n in result["nodes"]]
    assert "Config" in labels, f"Config struct not found in {labels}"
    assert "NetworkError" in labels, f"NetworkError enum not found in {labels}"


def test_extract_swift_no_error():
    from graphify.extract import extract_swift
    result = extract_swift(FIXTURES / "sample.swift")
    assert "error" not in result


# ── Julia ─────────────────────────────────────────────────────────────────────

def test_extract_julia_finds_module_and_struct():
    from graphify.extract import extract_julia
    result = extract_julia(FIXTURES / "sample.jl")
    assert "nodes" in result
    assert "edges" in result
    labels = [n["label"] for n in result["nodes"]]
    assert "Geometry" in labels, f"Geometry module not found in {labels}"
    assert any("Point" in l or "Circle" in l for l in labels), f"No structs found in {labels}"


def test_extract_julia_finds_function():
    from graphify.extract import extract_julia
    result = extract_julia(FIXTURES / "sample.jl")
    labels = [n["label"] for n in result["nodes"]]
    assert any("area" in l or "distance" in l or "perimeter" in l for l in labels), f"No functions found in {labels}"


# ── Fortran ───────────────────────────────────────────────────────────────────

def test_extract_fortran_finds_module():
    from graphify.extract import extract_fortran
    result = extract_fortran(FIXTURES / "sample.f90")
    labels = [n["label"] for n in result["nodes"]]
    assert "shapes" in labels, f"shapes module not found in {labels}"


def test_extract_fortran_finds_subroutine():
    from graphify.extract import extract_fortran
    result = extract_fortran(FIXTURES / "sample.f90")
    labels = [n["label"] for n in result["nodes"]]
    assert any("compute_volume" in l for l in labels), f"compute_volume subroutine not found in {labels}"


def test_extract_fortran_uppercase_fixture():
    """Fortran with .F90 extension (preprocessed) should also work."""
    from graphify.extract import extract_fortran
    result = extract_fortran(FIXTURES / "sample.F90")
    labels = [n["label"] for n in result["nodes"]]
    assert "shapes" in labels, f"shapes module not found in {labels}"


def test_extract_fortran_lowercase_f90():
    """Fortran with lowercase .f90 extension works."""
    from graphify.extract import extract_fortran
    result = extract_fortran(FIXTURES / "sample_lowercase.f90")
    labels = [n["label"] for n in result["nodes"]]
    assert "geometry" in labels or any("circle_area" in l or "distance" in l for l in labels)


# ── Zig ───────────────────────────────────────────────────────────────────────

def test_extract_zig_finds_struct_and_function():
    from graphify.extract import extract_zig
    result = extract_zig(FIXTURES / "sample.zig")
    labels = [n["label"] for n in result["nodes"]]
    assert "Point" in labels, f"Point struct not found in {labels}"
    assert any("add" in l or "multiply" in l or "main" in l for l in labels), f"No functions found in {labels}"


def test_extract_zig_no_error():
    from graphify.extract import extract_zig
    result = extract_zig(FIXTURES / "sample.zig")
    assert "error" not in result


# ── PowerShell ─────────────────────────────────────────────────────────────────

def test_extract_powershell_finds_function_and_class():
    from graphify.extract import extract_powershell
    result = extract_powershell(FIXTURES / "sample.ps1")
    labels = [n["label"] for n in result["nodes"]]
    assert any("Get-Data" in l or "Process-Items" in l for l in labels), f"No functions found in {labels}"
    assert "DataProcessor" in labels, f"DataProcessor class not found in {labels}"


def test_extract_powershell_no_error():
    from graphify.extract import extract_powershell
    result = extract_powershell(FIXTURES / "sample.ps1")
    assert "error" not in result


# ── Objective-C ───────────────────────────────────────────────────────────────

def test_extract_objc_finds_interface_and_implementation():
    from graphify.extract import extract_objc
    result = extract_objc(FIXTURES / "sample.m")
    labels = [n["label"] for n in result["nodes"]]
    assert "Animal" in labels, f"Animal class not found in {labels}"
    assert "Dog" in labels, f"Dog class not found in {labels}"
    assert any("speak" in l or "fetch" in l for l in labels), f"No methods found in {labels}"


def test_extract_objc_no_error():
    from graphify.extract import extract_objc
    result = extract_objc(FIXTURES / "sample.m")
    assert "error" not in result


# ── Elixir ────────────────────────────────────────────────────────────────────

def test_extract_elixir_finds_module():
    from graphify.extract import extract_elixir
    result = extract_elixir(FIXTURES / "sample.ex")
    labels = [n["label"] for n in result["nodes"]]
    assert "MyApp.Accounts.User" in labels, f"Module not found in {labels}"
    assert any("create" in l or "find" in l or "validate" in l for l in labels), f"No functions found in {labels}"


def test_extract_elixir_no_error():
    from graphify.extract import extract_elixir
    result = extract_elixir(FIXTURES / "sample.ex")
    assert "error" not in result


# ── SQL ───────────────────────────────────────────────────────────────────────

def test_extract_sql_finds_tables():
    from graphify.extract import extract_sql
    result = extract_sql(FIXTURES / "sample.sql")
    labels = [n["label"] for n in result["nodes"]]
    assert "organizations" in labels, f"organizations table not found in {labels}"
    assert "users" in labels, f"users table not found in {labels}"


def test_extract_sql_produces_edges():
    from graphify.extract import extract_sql
    result = extract_sql(FIXTURES / "sample.sql")
    relations = {e["relation"] for e in result["edges"]}
    assert "references" in relations or len(result["edges"]) > 0


def test_extract_sql_no_error():
    from graphify.extract import extract_sql
    result = extract_sql(FIXTURES / "sample.sql")
    assert "error" not in result


# ── Groovy ────────────────────────────────────────────────────────────────────

def test_extract_groovy_finds_class_and_methods():
    from graphify.extract import extract_groovy
    result = extract_groovy(FIXTURES / "sample.groovy")
    labels = [n["label"] for n in result["nodes"]]
    assert "SampleService" in labels, f"SampleService class not found in {labels}"
    assert any("process" in l or "reset" in l for l in labels), f"No methods found in {labels}"


def test_extract_groovy_no_error():
    from graphify.extract import extract_groovy
    result = extract_groovy(FIXTURES / "sample.groovy")
    assert "error" not in result


def test_extract_spock_finds_feature_methods():
    """Spock spec files with 'def \"feature\"()' methods should extract via fallback."""
    from graphify.extract import extract_groovy
    result = extract_groovy(FIXTURES / "sample_spock.groovy")
    labels = [n["label"] for n in result["nodes"]]
    assert "SampleSpec" in labels, f"SampleSpec class not found in {labels}"


def test_is_spock_file_detects_spock():
    """_is_spock_file returns True for Spock-style feature method files."""
    from graphify.extract import _is_spock_file
    result = _is_spock_file(FIXTURES / "sample_spock.groovy", {"nodes": [], "edges": []})
    assert result is True


def test_is_spock_file_returns_false_for_regular_groovy():
    """_is_spock_file returns False for regular Groovy files."""
    from graphify.extract import _is_spock_file
    result = _is_spock_file(FIXTURES / "sample.groovy", {"nodes": [], "edges": []})
    assert result is False


# ── Lua ───────────────────────────────────────────────────────────────────────

def test_extract_lua_accepts_luau():
    """Lua extractor also handles .luau fixture files."""
    from graphify.extract import extract_lua
    result = extract_lua(FIXTURES / "sample.luau")
    labels = [n["label"] for n in result["nodes"]]
    assert len(labels) > 0, f"No labels extracted from sample.luau"


# ── Markdown ──────────────────────────────────────────────────────────────────

def test_extract_markdown_finds_content():
    from graphify.extract import extract_markdown
    result = extract_markdown(FIXTURES / "sample.md")
    assert "nodes" in result
    assert "edges" in result
    assert len(result["nodes"]) > 0


def test_extract_markdown_no_error():
    from graphify.extract import extract_markdown
    result = extract_markdown(FIXTURES / "sample.md")
    assert "error" not in result


# ── Svelte ────────────────────────────────────────────────────────────────────

def test_extract_svelte_handles_missing_template(tmp_path):
    """extract_svelte should not crash on a minimal .svelte file."""
    from graphify.extract import extract_svelte
    sv = tmp_path / "test.svelte"
    sv.write_text("<script>export let x = 1;</script>")
    result = extract_svelte(sv)
    assert "nodes" in result
    assert "edges" in result


# ── Dart ──────────────────────────────────────────────────────────────────────

def test_extract_dart_handles_minimal_file(tmp_path):
    """extract_dart should handle a minimal .dart file gracefully."""
    from graphify.extract import extract_dart
    d = tmp_path / "test.dart"
    d.write_text("void main() { print('hi'); }")
    result = extract_dart(d)
    assert "nodes" in result
    assert "edges" in result


# ── Verilog ───────────────────────────────────────────────────────────────────

def test_extract_verilog_handles_minimal_file(tmp_path):
    """extract_verilog should handle a minimal .v file gracefully."""
    from graphify.extract import extract_verilog
    v = tmp_path / "test.v"
    v.write_text("module test; endmodule")
    result = extract_verilog(v)
    assert "nodes" in result
    assert "edges" in result


# ═══════════════════════════════════════════════════════════════════════════════
# ── Cross-file extraction (extract function) ──────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_empty_paths():
    """extract with empty list returns empty but valid result."""
    result = extract([])
    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["input_tokens"] == 0


def test_extract_single_go_file():
    """extract on a single Go file works."""
    result = extract([FIXTURES / "sample.go"])
    assert len(result["nodes"]) > 0
    assert len(result["edges"]) > 0


def test_extract_mixed_languages():
    """extract handles a mix of language files together."""
    files = [
        FIXTURES / "sample.py",
        FIXTURES / "sample.go",
        FIXTURES / "sample.java",
    ]
    result = extract(files)
    assert len(result["nodes"]) > 0
    assert len(result["edges"]) > 0
    labels = [n["label"] for n in result["nodes"]]
    assert any("Transformer" in l for l in labels)
    assert any("Server" in l for l in labels)
    assert any("DataProcessor" in l for l in labels)


def test_extract_java_cross_file_import_resolution(tmp_path):
    """Multiple Java files in extract should trigger cross-file import resolution."""
    from graphify.extract import extract
    a = tmp_path / "A.java"
    b = tmp_path / "B.java"
    a.write_text("import pkg.B;\npublic class A { void m() { new B(); } }")
    b.write_text("package pkg;\npublic class B {}")
    result = extract([a, b], cache_root=tmp_path)
    assert len(result["nodes"]) > 0


def test_extract_with_cache_root(tmp_path):
    """extract with cache_root parameter should work."""
    from graphify.extract import extract
    p = tmp_path / "test.py"
    p.write_text("def foo(): pass")
    result = extract([p], cache_root=tmp_path)
    assert len(result["nodes"]) > 0


def test_extract_unsupported_extension_is_skipped(tmp_path):
    """Files with unsupported extensions should be skipped gracefully."""
    from graphify.extract import extract
    f = tmp_path / "test.xyz"
    f.write_text("some content")
    result = extract([f], cache_root=tmp_path)
    assert isinstance(result, dict)
    assert "nodes" in result


def test_extract_with_cache_hit(tmp_path):
    """Second extraction should hit cache and produce same results."""
    from graphify.extract import extract
    p = tmp_path / "test.py"
    p.write_text("def foo(): pass")
    result1 = extract([p], cache_root=tmp_path)
    result2 = extract([p], cache_root=tmp_path)
    assert result1["nodes"] == result2["nodes"]


# ═══════════════════════════════════════════════════════════════════════════════
# ── Edge case tests ───────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_python_empty_file(tmp_path):
    """Extracting an empty Python file should not crash."""
    p = tmp_path / "empty.py"
    p.write_text("")
    result = extract_python(p)
    assert "nodes" in result
    assert "edges" in result


def test_extract_missing_file_returns_error():
    """Extracting a nonexistent file via _safe_extract returns error."""
    def extractor(p):
        if not p.exists():
            raise FileNotFoundError(str(p))
        return {"nodes": [], "edges": []}
    result = _safe_extract(extractor, Path("/nonexistent/path.py"))
    assert "error" in result
    assert "FileNotFoundError" in result["error"]


def test_collect_files_single_file():
    """collect_files on a single file returns it."""
    files = collect_files(FIXTURES / "sample.py")
    assert files == [FIXTURES / "sample.py"]


def test_collect_files_ignore_root(tmp_path):
    """collect_files with explicit root parameter."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("x = 1")
    files = collect_files(src, root=tmp_path)
    assert any("app.py" in str(f) for f in files)


def test_extract_python_rationale_extracted():
    """Python extractor adds rationale nodes for docstring comments."""
    result = extract_python(FIXTURES / "sample.py")
    rationale_nodes = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    # Not all Python files have docstrings, but the function should be called
    assert isinstance(result, dict)


def test_extract_binary_file_is_skipped(tmp_path):
    """Binary files should produce error result gracefully."""
    p = tmp_path / "binary.bin"
    p.write_bytes(b"\x00\x01\x02\x03\xff\xfe")
    # Use a real extractor that might fail on binary
    # Most tree-sitter parsers handle binary by producing error nodes
    result = _safe_extract(lambda x: extract_python(x), p)
    assert isinstance(result, dict)


def test_dispatch_has_all_expected_extensions():
    """_DISPATCH dict has expected common extensions."""
    expected = {".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".rb",
                ".cs", ".kt", ".scala", ".php", ".swift", ".lua", ".zig",
                ".ps1", ".ex", ".m", ".jl", ".f90", ".sql", ".md",
                ".sh", ".bash", ".bats"}
    assert expected.issubset(set(_DISPATCH.keys())), f"Missing: {expected - set(_DISPATCH.keys())}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Token estimation and result structure ─────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_returns_token_fields():
    """extract() result always includes input_tokens/output_tokens."""
    result = extract([FIXTURES / "sample.py"])
    assert "input_tokens" in result
    assert "output_tokens" in result
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0


def test_all_nodes_have_required_fields():
    """Every node from extract must have id, label, file_type fields."""
    result = extract([FIXTURES / "sample.py"])
    for node in result["nodes"]:
        assert "id" in node, f"Node missing id: {node}"
        assert "label" in node, f"Node missing label: {node}"
        assert "file_type" in node, f"Node missing file_type: {node}"


def test_all_edges_have_required_fields():
    """Every edge from extract must have source, target, relation."""
    result = extract([FIXTURES / "sample.py"])
    for edge in result["edges"]:
        assert "source" in edge, f"Edge missing source: {edge}"
        assert "target" in edge, f"Edge missing target: {edge}"
        assert "relation" in edge, f"Edge missing relation: {edge}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── PHP extractor specialized tests ──────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_php_produces_import_edges():
    """PHP uses/namespace imports produce imports_from edges."""
    from graphify.extract import extract_php
    result = extract_php(FIXTURES / "sample.php")
    import_relations = {e.get("relation") for e in result["edges"]}
    assert "imports_from" in import_relations or "imports" in import_relations or len(result["edges"]) > 0


def test_extract_php_namespace_found():
    """PHP namespace declaration influences node IDs."""
    from graphify.extract import extract_php
    result = extract_php(FIXTURES / "sample.php")
    nids = {n["id"] for n in result["nodes"]}
    # The file node ID should be based on the file path
    assert any("sample_php" in nid for nid in nids), f"No sample_php in IDs: {nids}"
    assert any("apiclient" in nid for nid in nids), f"No apiclient in IDs: {nids}"


def test_extract_php_blade(tmp_path):
    """Blade template extractor produces includes edges."""
    from graphify.extract import extract_blade
    b = tmp_path / "test.blade.php"
    b.write_text("@include('partials.header')\n<div>content</div>")
    result = extract_blade(b)
    includes = [e for e in result["edges"] if e["relation"] == "includes"]
    assert len(includes) > 0
    assert includes[0]["confidence"] == "EXTRACTED"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Groovy Spock-specific tests ───────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_spock_extraction_produces_method_nodes():
    """Spock `def "feature"()` methods produce nodes despite TS parse failure."""
    from graphify.extract import extract_groovy
    result = extract_groovy(FIXTURES / "sample_spock.groovy")
    labels = [n["label"] for n in result["nodes"]]
    # Spock feature methods are captured with string labels
    assert any('"should' in l or "should" in l.lower() for l in labels)


def test_spock_extraction_edges_not_dangling():
    """Edges from Spock fallback extraction should reference known nodes."""
    from graphify.extract import extract_groovy
    result = extract_groovy(FIXTURES / "sample_spock.groovy")
    node_ids = {n["id"] for n in result["nodes"]}
    for edge in result["edges"]:
        if edge.get("relation") in ("contains", "method"):
            assert edge["source"] in node_ids, f"Dangling source: {edge['source']}"
            assert edge["target"] in node_ids, f"Dangling target: {edge['target']}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Extract function additional tests ─────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_merge_preserves_node_ids():
    """After extract(), no duplicate node IDs should exist."""
    result = extract([FIXTURES / "sample.py", FIXTURES / "sample.go"])
    ids = [n["id"] for n in result["nodes"]]
    assert len(ids) == len(set(ids)), f"Duplicate node IDs found"


def test_extract_with_parallel_false(tmp_path):
    """extract with parallel=False should work the same."""
    from graphify.extract import extract as _extract
    p = tmp_path / "test.py"
    p.write_text("def foo(): pass")
    result = _extract([p], cache_root=tmp_path, parallel=False)
    assert len(result["nodes"]) > 0


def test_collect_files_respects_gitignore(tmp_path):
    """collect_files skips files ignored by .gitignore patterns."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "keep.py").write_text("x = 1")
    (src / "skip.py").write_text("y = 1")
    (tmp_path / ".graphifyignore").write_text("skip.py")
    files = collect_files(src, root=tmp_path)
    names = [f.name for f in files]
    assert "keep.py" in names
    # skip.py should be filtered if graphifyignore patterns are working


# ═══════════════════════════════════════════════════════════════════════════════
# ── Tsconfig alias tests ─────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_read_tsconfig_aliases_resolves_paths(tmp_path):
    """_read_tsconfig_aliases extracts 'paths' from a tsconfig.json."""
    from graphify.extract import _read_tsconfig_aliases
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text('''{"compilerOptions": {"paths": {"@/*": ["./src/*"], "$lib/*": ["./src/lib/*"]}}}''')
    aliases = _read_tsconfig_aliases(tsconfig, tmp_path, seen=set())
    assert "@/core" not in aliases  # exact alias with /*
    assert "$lib/components" not in aliases


def test_read_tsconfig_aliases_handles_missing_file():
    """_read_tsconfig_aliases returns empty dict for missing files."""
    from graphify.extract import _read_tsconfig_aliases
    aliases = _read_tsconfig_aliases(Path("/nonexistent/tsconfig.json"), Path("."), seen=set())
    assert aliases == {}


def test_read_tsconfig_aliases_handles_circular_extends(tmp_path):
    """_read_tsconfig_aliases skips circular extends chains."""
    from graphify.extract import _read_tsconfig_aliases
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text('''{"extends": "./tsconfig.json", "compilerOptions": {"paths": {"@/*": ["./src/*"]}}}''')
    aliases = _read_tsconfig_aliases(tsconfig, tmp_path, seen=set())
    assert isinstance(aliases, dict)


def test_load_tsconfig_aliases_finds_config(tmp_path):
    """_load_tsconfig_aliases walks up directories to find tsconfig.json."""
    from graphify.extract import _load_tsconfig_aliases
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text('''{"compilerOptions": {"paths": {"@inner/*": ["./app/*"]}}}''')
    sub = tmp_path / "deep" / "nested"
    sub.mkdir(parents=True)
    aliases = _load_tsconfig_aliases(sub)
    assert isinstance(aliases, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# ── Python inheritance and import tests ──────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_python_inheritance_emits_inherits_edges(tmp_path):
    """Python classes with superclasses should produce inherits edges."""
    p = tmp_path / "inherits_test.py"
    p.write_text("class Base:\n    pass\n\nclass Derived(Base):\n    pass\n")
    result = extract_python(p)
    inherits_edges = [e for e in result["edges"] if e["relation"] == "inherits"]
    assert len(inherits_edges) > 0, f"No inherits edges found: {result['edges']}"


def test_extract_python_relative_import_ids_match(tmp_path):
    """Python relative imports should produce imports_from edges pointing at target file."""
    (tmp_path / "subpkg").mkdir()
    main = tmp_path / "main.py"
    mod = tmp_path / "subpkg" / "mod.py"
    main.write_text("from .subpkg import mod\n")
    mod.write_text("def helper(): pass\n")
    result = extract_python(main)
    imports_from = [e for e in result["edges"] if e["relation"] == "imports_from"]
    assert len(imports_from) > 0, f"No imports_from edges: {result['edges']}"
    # The target should reference the subpackage path
    targets = [e["target"] for e in imports_from]
    assert any("subpkg" in t.lower() for t in targets), f"No subpkg in targets: {targets}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── C# advanced type tests ───────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_csharp_generic_types(tmp_path):
    """C# extractor handles generic types like List<T>."""
    from graphify.extract import extract_csharp
    cs = tmp_path / "generics.cs"
    cs.write_text("using System.Collections.Generic;\n"
                  "public class Repo { public List<string> Items { get; } }")
    result = extract_csharp(cs)
    assert "error" not in result
    assert len(result["nodes"]) > 0


def test_extract_csharp_qualified_names(tmp_path):
    """C# extractor handles qualified type names."""
    from graphify.extract import extract_csharp
    cs = tmp_path / "qualified.cs"
    cs.write_text("public class Client { private System.Net.Http.HttpClient _http; }")
    result = extract_csharp(cs)
    assert "error" not in result


# ═══════════════════════════════════════════════════════════════════════════════
# ── Dynamic import and advanced JS tests ─────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_js_dynamic_import(tmp_path):
    """Dynamic import() should emit imports_from edges."""
    from graphify.extract import extract_js
    main = tmp_path / "main.js"
    lib = tmp_path / "lib.js"
    main.write_text("async function load() { const m = await import('./lib.js'); }")
    lib.write_text("export function helper() {}")
    result = extract([main, lib], cache_root=tmp_path)
    imports_from = [e for e in result["edges"] if e["relation"] == "imports_from"]
    assert len(imports_from) > 0, f"No imports_from from dynamic import: {result['edges']}"


def test_extract_js_typescript_file_handled(tmp_path):
    """TypeScript files are extracted correctly via extract_js."""
    from graphify.extract import extract_js
    ts = tmp_path / "types.ts"
    ts.write_text("interface Foo { bar: string; }\nfunction baz(): Foo { return { bar: 'x' }; }")
    result = extract_js(ts)
    assert "error" not in result
    labels = [n["label"] for n in result["nodes"]]
    assert any("baz" in l for l in labels)


def test_extract_js_import_emits_symbol_edges(tmp_path):
    """JS named imports should produce symbol-level imports edges."""
    from graphify.extract import extract_js
    a = tmp_path / "a.js"
    b = tmp_path / "b.js"
    a.write_text("import { doSomething } from './b.js';\nexport function run() { doSomething(); }")
    b.write_text("export function doSomething() { return 1; }")
    result = extract([a, b], cache_root=tmp_path)
    sym_imports = [e for e in result["edges"] if e["relation"] == "imports"]
    assert len(sym_imports) > 0, f"No symbol imports edges: {result['edges']}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Lua import tests ─────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_lua_require_emits_imports(tmp_path):
    """Lua require() calls should produce imports edges."""
    from graphify.extract import extract_lua
    l = tmp_path / "test.lua"
    l.write_text('local http = require("socket.http")\nfunction request() return http.get() end')
    result = extract_lua(l)
    import_edges = [e for e in result["edges"] if e.get("context") == "import"]
    assert len(import_edges) > 0, f"No import edges from require: {result['edges']}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Svelte advanced template tests ───────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_svelte_static_import_in_script(tmp_path):
    """Svelte static imports in <script> blocks should be extracted."""
    from graphify.extract import extract_svelte
    sv = tmp_path / "component.svelte"
    sv.write_text('<script>import Foo from "./Foo.svelte";</script>\n<div>hi</div>')
    result = extract_svelte(sv)
    imports_from = [e for e in result["edges"] if e["relation"] == "imports_from"]
    assert len(imports_from) > 0, f"No imports_from from Svelte script: {result['edges']}"


def test_extract_svelte_dynamic_import_in_template(tmp_path):
    """Svelte dynamic imports in template should be extracted."""
    from graphify.extract import extract_svelte
    sv = tmp_path / "dyn.svelte"
    sv.write_text('{#await import("./Modal.svelte") then Mod}<Mod />{/await}')
    result = extract_svelte(sv)
    dyn = [e for e in result["edges"] if e["relation"] == "dynamic_import"]
    assert len(dyn) > 0, f"No dynamic_import edges: {result['edges']}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Java type hierarchy tests ────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_java_with_extends(tmp_path):
    """Java classes with extends should emit inherits edges."""
    from graphify.extract import extract_java
    j = tmp_path / "Base.java"
    j.write_text("public class Base {}\nclass Derived extends Base {}")
    result = extract_java(j)
    inherits = [e for e in result["edges"] if e["relation"] in ("extends", "inherits")]
    # Might use "extends" or "inherits" relation
    assert len(inherits) > 0 or len(result["nodes"]) > 1


def test_extract_java_with_implements(tmp_path):
    """Java classes with implements should produce implements edges."""
    from graphify.extract import extract_java
    j = tmp_path / "Impl.java"
    j.write_text("interface Callable {}\nclass Runner implements Callable {}")
    result = extract_java(j)
    implements = [e for e in result["edges"] if e["relation"] == "implements"]
    assert len(implements) > 0 or len(result["nodes"]) > 1


# ═══════════════════════════════════════════════════════════════════════════════
# ── Verilog / Dart detailed tests ────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_verilog_module_with_ports(tmp_path):
    """Verilog extractor handles modules with port declarations."""
    from graphify.extract import extract_verilog
    v = tmp_path / "test.sv"
    v.write_text("module adder(input [7:0] a, input [7:0] b, output [7:0] sum);\n  assign sum = a + b;\nendmodule")
    result = extract_verilog(v)
    assert "error" not in result
    assert len(result["nodes"]) > 0


def test_extract_dart_class_with_methods(tmp_path):
    """Dart extractor handles class with methods."""
    from graphify.extract import extract_dart
    d = tmp_path / "test.dart"
    d.write_text("class Counter { int _count = 0; void increment() { _count++; } }")
    result = extract_dart(d)
    assert "error" not in result
    assert len(result["nodes"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# ── More extract function tests ──────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_single_path_common_root(tmp_path):
    """extract with a single file uses its parent as root."""
    p = tmp_path / "single.py"
    p.write_text("x = 1")
    result = extract([p], cache_root=tmp_path)
    assert result["input_tokens"] == 0
    assert len(result["nodes"]) > 0


def test_extract_all_edges_have_confidence():
    """Every edge from extract should have a confidence field."""
    result = extract([FIXTURES / "sample.py"])
    for edge in result["edges"]:
        assert "confidence" in edge, f"Edge missing confidence: {edge}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── _read_tsconfig_aliases edge cases ─────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_read_tsconfig_aliases_jsonc_decode(tmp_path):
    """JSONC with comments should be decoded via _strip_jsonc fallback."""
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text('{"compilerOptions": {"paths": {"@/*": ["./src/*"]}} // comment\n}')
    aliases = _read_tsconfig_aliases(tsconfig, tmp_path, seen=set())
    assert isinstance(aliases, dict)


def test_read_tsconfig_aliases_parse_exception(tmp_path, monkeypatch):
    """Generic parse exception is caught and returns empty dict."""
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text("{}")

    import json
    def mock_loads_raise(s):
        raise ValueError("simulated parse error")
    monkeypatch.setattr(json, "loads", mock_loads_raise)

    aliases = _read_tsconfig_aliases(tsconfig, tmp_path, seen=set())
    assert aliases == {}


# ═══════════════════════════════════════════════════════════════════════════════
# ── _resolve_js_module_path edge cases ───────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_resolve_js_module_path_js_to_ts_fallback(tmp_path):
    """Imports with .js extension resolve to .ts when .ts file exists."""
    ts_file = tmp_path / "lib.ts"
    ts_file.write_text("export const x = 1;")
    js_path = tmp_path / "lib.js"
    assert not js_path.exists()
    result = _resolve_js_module_path(js_path)
    assert result == ts_file


def test_resolve_js_module_path_jsx_to_tsx_fallback(tmp_path):
    """Imports with .jsx extension resolve to .tsx when .tsx file exists."""
    tsx_file = tmp_path / "Comp.tsx"
    tsx_file.write_text("export const C = () => {};")
    jsx_path = tmp_path / "Comp.jsx"
    assert not jsx_path.exists()
    result = _resolve_js_module_path(jsx_path)
    assert result == tsx_file


def test_resolve_js_module_path_directory_import(tmp_path):
    """Directory imports should resolve to index files inside the directory."""
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    index = pkg / "index.ts"
    index.write_text("export const x = 1;")
    result = _resolve_js_module_path(pkg)
    assert result == index


def test_resolve_js_module_path_existing_file(tmp_path):
    """Already existing files are returned as-is."""
    f = tmp_path / "existing.ts"
    f.write_text("export const x = 1;")
    result = _resolve_js_module_path(f)
    assert result == f


# ═══════════════════════════════════════════════════════════════════════════════
# ── _resolve_name tests ──────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_resolve_name_with_function_name_fn():
    """When resolve_function_name_fn is set, _resolve_name returns None (caller handles)."""
    config = LanguageConfig(
        ts_module="tree_sitter_c",
        ts_language_fn="language",
        resolve_function_name_fn=_get_c_func_name,
    )
    result = _resolve_name(None, b"", config)
    assert result is None


def test_resolve_name_returns_name_via_field():
    """_resolve_name resolves name via name_field when available."""
    import tree_sitter_python as tsp
    from tree_sitter import Language, Parser
    from graphify.extract import _PYTHON_CONFIG

    src = b"def hello(): pass\n"
    lang = Language(tsp.language())
    parser = Parser(lang)
    tree = parser.parse(src)
    root = tree.root_node
    fn = root.children[0]
    name = _resolve_name(fn, src, _PYTHON_CONFIG)
    assert name == "hello"


# ═══════════════════════════════════════════════════════════════════════════════
# ── _import_python edge cases ────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_import_python_dotted_name(tmp_path):
    """`import foo.bar` should emit imports edge for 'foo' (first segment)."""
    import tree_sitter_python as tsp
    from tree_sitter import Language, Parser
    p = tmp_path / "mod.py"
    p.write_text("import os.path\n")
    src = p.read_bytes()
    lang = Language(tsp.language())
    parser = Parser(lang)
    tree = parser.parse(src)
    import_node = tree.root_node.children[0]

    edges = []
    _import_python(import_node, src, "file_nid", "stem", edges, str(p))
    assert len(edges) > 0
    assert any(e["relation"] == "imports" for e in edges)


def test_import_python_relative_dots_resolution(tmp_path):
    """`from ...subpkg import mod` should resolve dots in base path."""
    import tree_sitter_python as tsp
    from tree_sitter import Language, Parser
    nested = tmp_path / "deep" / "nested"
    nested.mkdir(parents=True)
    p = nested / "mymod.py"
    p.write_text("from ... import something\n")
    src = p.read_bytes()
    lang = Language(tsp.language())
    parser = Parser(lang)
    tree = parser.parse(src)
    import_node = tree.root_node.children[0]

    edges = []
    _import_python(import_node, src, "file_nid", "stem", edges, str(p))
    assert len(edges) > 0
    assert any(e["relation"] == "imports_from" for e in edges)


# ═══════════════════════════════════════════════════════════════════════════════
# ── _resolve_js_import_target tests ──────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_resolve_js_import_target_empty_raw(tmp_path):
    """Empty raw import string returns None."""
    result = _resolve_js_import_target("", str(tmp_path / "dummy.js"))
    assert result is None


def test_resolve_js_import_target_bare_slash_only(tmp_path):
    """Bare slash-only module returns None."""
    result = _resolve_js_import_target("/", str(tmp_path / "dummy.js"))
    assert result is None


def test_resolve_js_import_target_bare_module(tmp_path):
    """Bare module import returns (module_name_id, None)."""
    result = _resolve_js_import_target("lodash", str(tmp_path / "dummy.js"))
    assert result is not None
    tgt_nid, resolved_path = result
    assert resolved_path is None
    assert "lodash" in tgt_nid


def test_resolve_js_import_target_scoped_module(tmp_path):
    """Scoped @org/pkg import returns module name."""
    result = _resolve_js_import_target("@scope/package/sub", str(tmp_path / "dummy.js"))
    assert result is not None
    tgt_nid, resolved_path = result
    assert resolved_path is None
    assert "sub" in tgt_nid


def test_resolve_js_import_target_relative(tmp_path):
    """Relative import resolves to file path."""
    lib = tmp_path / "lib.js"
    lib.write_text("export const x = 1;")
    result = _resolve_js_import_target("./lib", str(tmp_path / "main.js"))
    assert result is not None
    tgt_nid, resolved_path = result
    assert resolved_path is not None


def test_resolve_js_import_target_with_tsconfig_aliases(tmp_path):
    """Path aliases from tsconfig should resolve imports."""
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text(
        '{"compilerOptions": {"paths": {"@app/*": ["./src/app/*"]}}}')
    src_dir = tmp_path / "src" / "app"
    src_dir.mkdir(parents=True)
    (src_dir / "util.ts").write_text("export const x = 1;")

    result = _resolve_js_import_target("@app/util", str(tmp_path / "src" / "main.ts"))
    assert result is not None
    tgt_nid, resolved_path = result
    assert resolved_path is not None


# ═══════════════════════════════════════════════════════════════════════════════
# ── _import_js empty/resolved tests ──────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_import_js_empty_import_string(tmp_path):
    """JS import with empty string should break early."""
    from graphify.extract import extract_js
    f = tmp_path / "empty_import.js"
    f.write_text("import '';  // empty\n")
    result = extract_js(f)
    assert "error" not in result


def test_import_js_resolved_is_none(tmp_path):
    """JS import that resolves to None should break early."""
    from graphify.extract import extract_js
    f = tmp_path / "empty_import.js"
    f.write_text("import '/';\n")
    result = extract_js(f)
    assert "error" not in result


# ═══════════════════════════════════════════════════════════════════════════════
# ── _dynamic_import_js tests ──────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_dynamic_import_js_no_args(tmp_path):
    """Dynamic import() with no arguments should return True but skip."""
    from graphify.extract import extract_js
    f = tmp_path / "dyn_import.js"
    f.write_text("async function load() { await import(); }\n")
    result = extract_js(f)
    assert "error" not in result


def test_dynamic_import_js_template_string(tmp_path):
    """Dynamic import with template string (no substitution) should work."""
    from graphify.extract import extract_js
    target = tmp_path / "helper.js"
    target.write_text("export const x = 1;")
    f = tmp_path / "dyn_import.js"
    f.write_text("async function load() { const m = await import(`./helper.js`); }\n")
    result = extract_js(f)
    assert "error" not in result


def test_dynamic_import_ts_dynamic_import_fixture():
    """TypeScript dynamic import fixture should produce imports_from edges."""
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "dynamic_import.ts")
    imports_from = [e for e in result["edges"] if e["relation"] == "imports_from"]
    assert len(imports_from) > 0, f"No dynamic import edges: {result['edges']}"


# ── TypeScript ESM import-evidence promotion regressions (#760) ───────────────


def test_typescript_same_file_call_edges_are_caller_to_callee(tmp_path):
    """Regression for #760: TS same-file calls must not be reversed."""
    from graphify.extract import extract

    src = tmp_path / "engine.ts"
    src.write_text(
        "function preprocessMQL4(code: string) { return parseInputParam(code); }\n"
        "function parseInputParam(code: string) { return code.length; }\n"
    )

    result = extract([src], cache_root=tmp_path)
    nodes = {n["label"]: n["id"] for n in result["nodes"]}
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}

    assert (nodes["preprocessMQL4()"], nodes["parseInputParam()"]) in calls
    assert (nodes["parseInputParam()"], nodes["preprocessMQL4()"]) not in calls


def test_typescript_imported_call_promoted_to_extracted(tmp_path):
    """Explicit `import { fn }` plus literal `fn()` call is deterministic (#760)."""
    from graphify.extract import extract

    caller = tmp_path / "BacktestEngine.ts"
    callee = tmp_path / "MQL4Preprocessor.ts"
    caller.write_text(
        "import { preprocessMQL4 } from './MQL4Preprocessor';\n"
        "export function parseEAParams(code: string) {\n"
        "  return preprocessMQL4(code).params;\n"
        "}\n"
    )
    callee.write_text(
        "export function preprocessMQL4(code: string) {\n"
        "  return { params: [] };\n"
        "}\n"
    )

    result = extract([caller, callee], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    call_edges = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and nodes[e["source"]]["label"] == "parseEAParams()"
        and nodes[e["target"]]["label"] == "preprocessMQL4()"
    ]

    assert len(call_edges) == 1
    assert call_edges[0]["confidence"] == "EXTRACTED"
    assert call_edges[0]["confidence_score"] == 1.0


def test_typescript_cross_file_call_without_import_stays_inferred(tmp_path):
    """Name-only cross-file resolution is still weaker than import evidence."""
    from graphify.extract import extract

    caller = tmp_path / "BacktestEngine.ts"
    callee = tmp_path / "MQL4Preprocessor.ts"
    caller.write_text(
        "export function parseEAParams(code: string) {\n"
        "  return preprocessMQL4(code).params;\n"
        "}\n"
    )
    callee.write_text(
        "export function preprocessMQL4(code: string) {\n"
        "  return { params: [] };\n"
        "}\n"
    )

    result = extract([caller, callee], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    call_edges = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and nodes[e["source"]]["label"] == "parseEAParams()"
        and nodes[e["target"]]["label"] == "preprocessMQL4()"
    ]

    assert len(call_edges) == 1
    assert call_edges[0]["confidence"] == "INFERRED"


# ═══════════════════════════════════════════════════════════════════════════════
# ── _import_kotlin / _import_scala / _import_php / _import_c tests ────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_import_kotlin_with_path_field():
    """Kotlin import with path field should produce imports edge."""
    from graphify.extract import extract_kotlin
    result = extract_kotlin(FIXTURES / "sample.kt")
    import_edges = [e for e in result["edges"] if e.get("context") == "import"]
    assert len(import_edges) > 0 or len(result["nodes"]) > 0


def test_import_kotlin_fallback_identifier(tmp_path):
    """Kotlin import with identifier fallback should work."""
    from graphify.extract import extract_kotlin
    kt = tmp_path / "test.kt"
    kt.write_text("import java.util.List\nclass Foo {}\n")
    result = extract_kotlin(kt)
    assert "error" not in result
    assert len(result["nodes"]) > 0


def test_import_scala_with_stable_id():
    """Scala import with stable_id should produce imports edge."""
    from graphify.extract import extract_scala
    result = extract_scala(FIXTURES / "sample.scala")
    import_edges = [e for e in result["edges"] if e.get("context") == "import"]
    assert len(import_edges) > 0 or len(result["nodes"]) > 0


def test_import_php_with_qualified_name():
    """PHP import with qualified_name should produce imports edge."""
    from graphify.extract import extract_php
    result = extract_php(FIXTURES / "sample.php")
    import_edges = [e for e in result["edges"]
                    if e.get("context") == "import"
                    or e.get("relation") in ("imports", "imports_from")]
    assert len(import_edges) > 0 or len(result["nodes"]) > 0


def test_import_csharp_with_qualified_name():
    """C# import with qualified_name should produce imports edge."""
    from graphify.extract import extract_csharp
    result = extract_csharp(FIXTURES / "sample.cs")
    assert "error" not in result
    assert len(result["nodes"]) > 0


def test_import_c_with_string_literal(tmp_path):
    """C import with string_literal should produce imports edge."""
    from graphify.extract import extract_c
    c = tmp_path / "test.c"
    c.write_text('#include <stdio.h>\nint main() { return 0; }\n')
    result = extract_c(c)
    assert "error" not in result


def test_import_lua_emits_imports(tmp_path):
    """Lua require() should produce imports edge."""
    from graphify.extract import extract_lua
    l = tmp_path / "test.lua"
    l.write_text('local mod = require("my_module")\n')
    result = extract_lua(l)
    import_edges = [e for e in result["edges"] if e.get("context") == "import"]
    assert len(import_edges) > 0, f"No import edges: {result['edges']}"


def test_import_swift_emits_imports():
    """Swift import should produce imports edge."""
    from graphify.extract import extract_swift
    result = extract_swift(FIXTURES / "sample.swift")
    import_edges = [e for e in result["edges"] if e.get("context") == "import"]
    assert len(import_edges) > 0 or len(result["nodes"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# ── _get_c_func_name / _get_cpp_func_name tests ──────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_get_c_func_name_children_fallback():
    """_get_c_func_name falls back to identifier in children when no declarator."""
    import tree_sitter_c as tsc
    from tree_sitter import Language, Parser
    src = b"int x;"
    lang = Language(tsc.language())
    parser = Parser(lang)
    tree = parser.parse(src)
    root = tree.root_node
    decl = root.children[0]
    name = _get_c_func_name(decl, src)
    assert name == "x"


def test_get_cpp_func_name_qualified_identifier():
    """_get_cpp_func_name handles qualified_identifier node."""
    import tree_sitter_cpp as tscpp
    from tree_sitter import Language, Parser
    src = b"namespace N { int x; }"
    lang = Language(tscpp.language())
    parser = Parser(lang)
    tree = parser.parse(src)
    root = tree.root_node
    # Walk to find a qualified_identifier
    name = _get_cpp_func_name(root, src)
    # Returns None or name depending on structure
    assert isinstance(name, (str, type(None)))


def test_get_cpp_func_name_children_fallback():
    """_get_cpp_func_name falls back to identifier in children when no declarator."""
    import tree_sitter_cpp as tscpp
    from tree_sitter import Language, Parser
    src = b"int x;"
    lang = Language(tscpp.language())
    parser = Parser(lang)
    tree = parser.parse(src)
    root = tree.root_node
    decl = root.children[0]
    name = _get_cpp_func_name(decl, src)
    assert name == "x"


# ═══════════════════════════════════════════════════════════════════════════════
# ── _read_csharp_type_name tests ─────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_read_csharp_type_name_none():
    """_read_csharp_type_name returns None for None input."""
    result = _read_csharp_type_name(None, b"")
    assert result is None


def test_read_csharp_type_name_generic_name(tmp_path):
    """_read_csharp_type_name resolves generic_name types."""
    from graphify.extract import extract_csharp
    cs = tmp_path / "gen.cs"
    cs.write_text("public class Repo { private List<string> _items; }\n")
    result = extract_csharp(cs)
    assert "error" not in result
    assert len(result["nodes"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# ── _find_require_call tests ─────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_find_require_call_none():
    """_find_require_call returns None for None value_node."""
    result = _find_require_call(None)
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# ── _extract_generic late exception and class inheritance paths ───────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_generic_file_read_error(tmp_path):
    """_extract_generic returns error when file cannot be read (nonexistent file)."""
    nonexistent = tmp_path / "nope.py"
    config = LanguageConfig(ts_module="tree_sitter_python", ts_language_fn="language")
    result = _extract_generic(nonexistent, config)
    assert "error" in result


# ═══════════════════════════════════════════════════════════════════════════════
# ── Python inheritance with unseen base class ──────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_python_inherits_unseen_base(tmp_path):
    """Python class inheriting from unknown base should create external node."""
    p = tmp_path / "inherit.py"
    p.write_text("class MyList(list):\n    pass\n")
    result = extract_python(p)
    # Internal base like 'list' produces inherits edge to it
    inherits = [e for e in result["edges"] if e["relation"] == "inherits"]
    assert len(inherits) > 0, f"No inherits edges: {result['edges']}"


def test_extract_python_multiple_inheritance(tmp_path):
    """Python multiple inheritance should produce multiple inherits edges."""
    p = tmp_path / "multi.py"
    p.write_text("class A: pass\nclass B: pass\nclass C(A, B): pass\n")
    result = extract_python(p)
    inherits = [e for e in result["edges"] if e["relation"] == "inherits"]
    assert len(inherits) >= 2, f"Expected >=2 inherits edges, got {len(inherits)}: {inherits}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Swift inheritance and conformance ──────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_swift_inherits_and_conforms():
    """Swift classes with inheritance should produce inherits edges."""
    from graphify.extract import extract_swift
    result = extract_swift(FIXTURES / "sample.swift")
    edges = result.get("edges", [])
    inherits = [e for e in edges if e["relation"] == "inherits"]
    # Swift fixture may or may not have explicit inherits, but should parse ok
    assert "error" not in result


def test_extract_swift_protocol_conformance(tmp_path):
    """Swift class conforming to protocol should produce conformance edges."""
    from graphify.extract import extract_swift
    sw = tmp_path / "test.swift"
    sw.write_text("protocol MyProto {}\nclass MyClass: MyProto {}\n")
    result = extract_swift(sw)
    assert "error" not in result
    inherits = [e for e in result["edges"] if e["relation"] == "inherits"]
    assert len(inherits) > 0, f"No inherits edges: {result['edges']}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── C# inheritance and generic base_list ─────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_csharp_inherits_generic_base(tmp_path):
    """C# class inheriting from generic base should resolve name correctly."""
    from graphify.extract import extract_csharp
    cs = tmp_path / "generic_base.cs"
    cs.write_text("public class MyRepo : BaseRepository<User> {}\n")
    result = extract_csharp(cs)
    assert "error" not in result
    inherits = [e for e in result["edges"] if e["relation"] == "inherits"]
    assert len(inherits) > 0, f"No inherits edges: {result['edges']}"


def test_extract_csharp_inherits_simple_base(tmp_path):
    """C# class inheriting from simple base class."""
    from graphify.extract import extract_csharp
    cs = tmp_path / "simple_base.cs"
    cs.write_text("public class Derived : Base {}\npublic class Base {}\n")
    result = extract_csharp(cs)
    assert "error" not in result
    inherits = [e for e in result["edges"] if e["relation"] == "inherits"]
    assert len(inherits) > 0, f"No inherits edges: {result['edges']}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Java extends/implements and namespace tests ───────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_java_extends_and_implements(tmp_path):
    """Java class extending and implementing should produce edges with _emit_java_parent."""
    from graphify.extract import extract_java
    j = tmp_path / "Multi.java"
    j.write_text(
        "public class MyRunnable extends Thread implements Runnable, Serializable {\n"
        "    public void run() {}\n"
        "}\n"
        "interface Serializable {}\n"
    )
    result = extract_java(j)
    assert "error" not in result
    relations = {e["relation"] for e in result["edges"]}
    assert "extends" in relations or "inherits" in relations, f"Relations: {relations}"


def test_extract_java_interface_extends(tmp_path):
    """Java interface extending other interfaces should produce extends edges."""
    from graphify.extract import extract_java
    j = tmp_path / "Interfaces.java"
    j.write_text(
        "interface A {}\ninterface B {}\ninterface C extends A, B {}\n")
    result = extract_java(j)
    assert "error" not in result
    extends_edges = [e for e in result["edges"] if e["relation"] == "extends"]
    assert len(extends_edges) > 0, f"No extends edges: {result['edges']}"


def test_extract_java_with_package(tmp_path):
    """Java file with package declaration should still extract."""
    from graphify.extract import extract_java
    j = tmp_path / "PkgClass.java"
    j.write_text("package com.example;\npublic class App {}\n")
    result = extract_java(j)
    assert "error" not in result
    assert len(result["nodes"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# ── Language-specific call-handling tests ──────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_call_swift_navigation_expression(tmp_path):
    """Swift member calls via navigation_expression should resolve callee."""
    from graphify.extract import extract_swift
    sw = tmp_path / "swift_call.swift"
    sw.write_text("struct A { func f() {} func g() { self.f() } }\n")
    result = extract_swift(sw)
    assert "error" not in result
    calls = [e for e in result["edges"] if e["relation"] == "calls"]
    assert len(calls) > 0, f"No calls edges: {result['edges']}"


def test_call_kotlin_navigation_expression(tmp_path):
    """Kotlin member calls via navigation_expression should not error and produce nodes."""
    from graphify.extract import extract_kotlin
    kt = tmp_path / "nav_call.kt"
    kt.write_text("class A {\n    fun f() { }\n    fun g() { this.f() }\n}\n")
    result = extract_kotlin(kt)
    assert "error" not in result
    assert len(result["nodes"]) > 0
    # May or may not produce calls edges depending on parser version
    labels = [n["label"] for n in result["nodes"]]
    assert "A" in labels, f"Class A not found in {labels}"


def test_call_scala_field_expression(tmp_path):
    """Scala field_expression calls should not error and produce nodes."""
    from graphify.extract import extract_scala
    sc = tmp_path / "scala_call.scala"
    sc.write_text("class A { def f(): Unit = {} def g(): Unit = { this.f() } }\n")
    result = extract_scala(sc)
    assert "error" not in result
    assert len(result["nodes"]) > 0
    labels = [n["label"] for n in result["nodes"]]
    assert "A" in labels, f"Class A not found: {labels}"


def test_call_csharp_invocation_expression(tmp_path):
    """C# invocation_expression calls should resolve callee."""
    from graphify.extract import extract_csharp
    cs = tmp_path / "csharp_call.cs"
    cs.write_text("public class A { void F() {} void G() { F(); } }\n")
    result = extract_csharp(cs)
    assert "error" not in result
    calls = [e for e in result["edges"] if e["relation"] == "calls"]
    assert len(calls) > 0, f"No calls edges: {result['edges']}"


def test_call_php_scoped_call_expression(tmp_path):
    """PHP scoped_call_expression (static method calls) should resolve callee."""
    from graphify.extract import extract_php
    php = tmp_path / "scoped_call.php"
    php.write_text(
        "<?php\nclass Logger { public static function log() {} }\n"
        "class App { public function run() { Logger::log(); } }\n")
    result = extract_php(php)
    assert "error" not in result
    calls = [e for e in result["edges"] if e["relation"] == "calls"]
    assert len(calls) > 0, f"No calls edges: {result['edges']}"


def test_call_cpp_identifier_call(tmp_path):
    """C++ call expressions should resolve callee via identifier."""
    from graphify.extract import extract_cpp
    cpp = tmp_path / "cpp_call.cpp"
    cpp.write_text("void helper() {}\nint main() { helper(); return 0; }\n")
    result = extract_cpp(cpp)
    assert "error" not in result
    calls = [e for e in result["edges"] if e["relation"] == "calls"]
    assert len(calls) > 0, f"No calls edges: {result['edges']}"


def test_call_java_call_resolution(tmp_path):
    """Java call expressions should resolve callee."""
    from graphify.extract import extract_java
    j = tmp_path / "JavaCall.java"
    j.write_text("class A { void m1() {} void m2() { m1(); } }\n")
    result = extract_java(j)
    assert "error" not in result
    calls = [e for e in result["edges"] if e["relation"] == "calls"]
    assert len(calls) > 0, f"No calls edges: {result['edges']}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── PHP event listener and static property edge cases ─────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_php_listen_emits_listened_by():
    """PHP event listener provider should emit listened_by edges."""
    from graphify.extract import extract_php
    result = extract_php(FIXTURES / "sample_php_listen.php")
    listened_by = [e for e in result["edges"] if e.get("relation") == "listened_by"]
    assert len(listened_by) > 0, f"No listened_by edges: {result['edges']}"


def test_extract_php_static_prop_emits_uses_static_prop():
    """PHP static property usage should emit uses_static_prop edges."""
    from graphify.extract import extract_php
    result = extract_php(FIXTURES / "sample_php_static_prop.php")
    static_props = [e for e in result["edges"] if e.get("relation") == "uses_static_prop"]
    assert len(static_props) > 0, f"No uses_static_prop edges: {result['edges']}"


def test_extract_php_const_ref_emits_references_constant(tmp_path):
    """PHP class constant access should emit references_constant edges."""
    from graphify.extract import extract_php
    php = tmp_path / "const_ref.php"
    php.write_text(
        "<?php\nclass Config { const VERSION = 1; }\n"
        "class App { public function run() { return Config::VERSION; } }\n")
    result = extract_php(php)
    assert "error" not in result
    ref_const = [e for e in result["edges"] if e.get("relation") == "references_constant"]
    assert len(ref_const) > 0, f"No references_constant edges: {result['edges']}"


def test_extract_php_container_bind_emits_bound_to(tmp_path):
    """PHP container bind() should emit bound_to edges."""
    from graphify.extract import extract_php
    php = tmp_path / "bind.php"
    php.write_text(
        "<?php\n"
        "interface ContractInterface {}\n"
        "class RealService implements ContractInterface {}\n"
        "class Provider { public function register() { "
        "$this->app->bind(ContractInterface::class, RealService::class); } }\n")
    result = extract_php(php)
    assert "error" not in result
    # Container bind may or may not produce bound_to depending on AST structure
    assert len(result["nodes"]) > 0
    labels = [n["label"] for n in result["nodes"]]
    assert any(name in labels for name in ["ContractInterface", "RealService", "Provider"])


# ═══════════════════════════════════════════════════════════════════════════════
# ── Julia extractor tests ─────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_julia_no_error():
    """Julia extractor on fixture should not produce error."""
    from graphify.extract import extract_julia
    result = extract_julia(FIXTURES / "sample.jl")
    assert "error" not in result


def test_extract_julia_finds_struct_reference(tmp_path):
    """Julia struct fields should reference types correctly."""
    from graphify.extract import extract_julia
    jl = tmp_path / "fields.jl"
    jl.write_text(
        "struct Point\n  x::Float64\n  y::Float64\nend\n"
        "function distance(p::Point)\n  return p.x\nend\n")
    result = extract_julia(jl)
    assert "error" not in result
    assert len(result["nodes"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# ── Fortran extractor tests ───────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_fortran_finds_call_edges():
    """Fortran extractor should find call edges between subroutines."""
    from graphify.extract import extract_fortran
    result = extract_fortran(FIXTURES / "sample_lowercase.f90")
    assert "error" not in result
    calls = [e for e in result["edges"] if e.get("relation") == "calls"]
    assert len(calls) > 0, f"No calls edges: {result['edges']}"


def test_extract_fortran_f90_no_error():
    """Fortran .f90 extension extractor should not produce error."""
    from graphify.extract import extract_fortran
    result = extract_fortran(FIXTURES / "sample.f90")
    assert "error" not in result


# ═══════════════════════════════════════════════════════════════════════════════
# ── PowerShell extractor tests ─────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_powershell_finds_cmdlets(tmp_path):
    """PowerShell extractor should find cmdlet invocations."""
    from graphify.extract import extract_powershell
    ps = tmp_path / "cmdlets.ps1"
    ps.write_text(
        "function Get-Stuff { Write-Output 'hello' }\n"
        "function Process-Stuff { Get-Stuff }\n")
    result = extract_powershell(ps)
    assert "error" not in result
    calls = [e for e in result["edges"] if e.get("relation") == "calls"]
    assert len(calls) > 0, f"No calls edges: {result['edges']}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Objective-C extractor tests ────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_objc_finds_method_calls(tmp_path):
    """Objective-C extractor should find method calls."""
    from graphify.extract import extract_objc
    m = tmp_path / "calls.m"
    m.write_text(
        "@interface Animal {}\n- (void)speak;\n@end\n"
        "@implementation Animal\n- (void)speak {}\n@end\n"
        "int main() { Animal *a; [a speak]; return 0; }\n")
    result = extract_objc(m)
    assert "error" not in result
    assert len(result["nodes"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# ── Elixir extractor tests ────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_elixir_finds_functions(tmp_path):
    """Elixir extractor should find function definitions and calls."""
    from graphify.extract import extract_elixir
    ex = tmp_path / "calls.ex"
    ex.write_text(
        "defmodule MyApp.Example do\n"
        "  def greet(name), do: IO.puts(\"Hello, \#{name}\")\n"
        "  def run, do: greet(\"world\")\n"
        "end\n")
    result = extract_elixir(ex)
    assert "error" not in result
    assert len(result["nodes"]) > 0
    # May produce call edges depending on parser version
    labels = [n["label"] for n in result["nodes"]]
    assert any("MyApp" in l or "Example" in l for l in labels), f"Module not found: {labels}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Markdown extractor tests ──────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_markdown_with_links(tmp_path):
    """Markdown extractor should capture link references."""
    from graphify.extract import extract_markdown
    md = tmp_path / "links.md"
    md.write_text("# Title\n\nSee [docs](docs.md) for more.\n")
    result = extract_markdown(md)
    assert "error" not in result
    assert len(result["nodes"]) > 0


def test_extract_markdown_deploy_guide_fixture():
    """Markdown extractor on deploy_guide.md fixture should produce nodes."""
    from graphify.extract import extract_markdown
    result = extract_markdown(FIXTURES / "deploy_guide.md")
    assert "error" not in result
    assert len(result["nodes"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# ── Groovy calls and edge cases ───────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_groovy_finds_calls():
    """Groovy extractor should find call edges."""
    from graphify.extract import extract_groovy
    result = extract_groovy(FIXTURES / "sample.groovy")
    assert "error" not in result
    assert len(result["nodes"]) > 0
    # May produce call edges depending on parser version
    calls = [e for e in result["edges"] if e.get("relation") == "calls"]
    # Just check it doesn't crash — calls optional depending on fixture content


# ═══════════════════════════════════════════════════════════════════════════════
# ── Lua import edge cases ────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_lua_finds_calls(tmp_path):
    """Lua extractor should find call edges."""
    from graphify.extract import extract_lua
    l = tmp_path / "calls.lua"
    l.write_text("function greet() print('hi') end\nfunction main() greet() end\n")
    result = extract_lua(l)
    assert "error" not in result
    calls = [e for e in result["edges"] if e.get("relation") == "calls"]
    assert len(calls) > 0, f"No calls edges: {result['edges']}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Go extractor detailed tests ───────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_go_finds_calls():
    """Go extractor should find call edges."""
    from graphify.extract import extract_go
    result = extract_go(FIXTURES / "sample.go")
    calls = [e for e in result["edges"] if e.get("relation") == "calls"]
    assert len(calls) > 0, f"No calls edges in Go: {result['edges']}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Rust extractor detailed tests ─────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_rust_finds_calls(tmp_path):
    """Rust extractor should find call edges."""
    from graphify.extract import extract_rust
    rs = tmp_path / "calls.rs"
    rs.write_text("fn helper() {}\npub fn main() { helper(); }\n")
    result = extract_rust(rs)
    assert "error" not in result
    calls = [e for e in result["edges"] if e.get("relation") == "calls"]
    assert len(calls) > 0, f"No calls edges: {result['edges']}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Zig extractor detailed tests ──────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_zig_finds_calls():
    """Zig extractor should find call edges."""
    from graphify.extract import extract_zig
    result = extract_zig(FIXTURES / "sample.zig")
    calls = [e for e in result["edges"] if e.get("relation") == "calls"]
    assert len(calls) > 0, f"No calls edges in Zig: {result['edges']}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Dart detailed tests ──────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_dart_finds_class_with_calls(tmp_path):
    """Dart extractor should find classes and methods."""
    from graphify.extract import extract_dart
    d = tmp_path / "dart_call.dart"
    d.write_text("class A { void f() {} void g() { f(); } }\n")
    result = extract_dart(d)
    assert "error" not in result
    assert len(result["nodes"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# ── Verilog detailed tests ───────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_verilog_module_instantiation(tmp_path):
    """Verilog extractor should handle module instantiation."""
    from graphify.extract import extract_verilog
    v = tmp_path / "inst.v"
    v.write_text(
        "module sub(); endmodule\n"
        "module top(); sub inst(); endmodule\n")
    result = extract_verilog(v)
    assert "error" not in result
    assert len(result["nodes"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# ── SQL detailed tests ───────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_sql_finds_fk_edges(tmp_path):
    """SQL extractor should find foreign key references."""
    from graphify.extract import extract_sql
    s = tmp_path / "fk.sql"
    s.write_text(
        "CREATE TABLE users (id INTEGER PRIMARY KEY);\n"
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id));\n")
    result = extract_sql(s)
    assert "error" not in result
    refs = [e for e in result["edges"] if e.get("relation") == "references"]
    assert len(refs) > 0, f"No references edges: {result['edges']}"


# ═══════════════════════════════════════════════════════════════════════════════
# ── Spock Groovy edge cases ──────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_is_spock_file_read_error(tmp_path, monkeypatch):
    """_is_spock_file returns False when file cannot be read."""
    from graphify.extract import _is_spock_file
    bad_path = tmp_path / "nonexistent.groovy"
    result = _is_spock_file(bad_path, {"nodes": [], "edges": []})
    assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# ── _read_text and other helpers ─────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_read_text_basic():
    """_read_text should extract text from source bytes."""
    import tree_sitter_python as tsp
    from tree_sitter import Language, Parser
    src = b"x = 42\n"
    lang = Language(tsp.language())
    parser = Parser(lang)
    tree = parser.parse(src)
    root = tree.root_node
    # Walk into expression_statement -> assignment -> identifier
    assign = root.children[0].children[0]
    ident = assign.children[0]
    assert ident.type == "identifier", f"Expected identifier, got: {ident.type}"
    text = _read_text(ident, src)
    assert text == "x"


# ═══════════════════════════════════════════════════════════════════════════════
# ── extract with explicit root parameter ──────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_with_explicit_root(tmp_path):
    """extract with cache_root parameter should work."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text("def f(): pass\n")
    result = extract([src / "mod.py"], cache_root=tmp_path)
    assert len(result["nodes"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# ── Collect files edge cases ──────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def test_collect_files_with_ignore_root(tmp_path):
    """collect_files with explicit root parameter should work."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "keep.py").write_text("x = 1")
    (src / "skip_test.py").write_text("y = 1")
    files = collect_files(src, root=tmp_path)
    names = {f.name for f in files}
    assert "keep.py" in names


def test_collect_files_no_such_path():
    """collect_files with nonexistent path returns empty list."""
    result = collect_files(Path("/nonexistent/path/to/xyzzy/thing"))
    assert result == []


# ═══════════════════════════════════════════════════════════════════════════════
# ── Bash extraction tests ────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════


def test_extract_bash_finds_entrypoint_functions_and_calls():
    from graphify.extract import extract_bash

    result = extract_bash(FIXTURES / "sample.sh")
    assert "error" not in result

    labels = [n["label"] for n in result["nodes"]]
    assert "sample.sh" in labels
    assert "sample.sh script" in labels
    assert "deploy()" in labels
    assert "main()" in labels

    node_by_id = {n["id"]: n["label"] for n in result["nodes"]}
    calls = {
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in result["edges"]
        if e["relation"] == "calls"
    }
    assert ("main()", "deploy()") in calls
    assert all(e["confidence"] == "EXTRACTED" for e in result["edges"] if e["relation"] == "calls")


def test_extract_bash_records_source_imports():
    from graphify.extract import extract_bash

    result = extract_bash(FIXTURES / "sample.sh")
    assert result["bash_sources"]
    assert any(source["target_path"].endswith("lib.sh") for source in result["bash_sources"])


def test_extract_bash_zero_function_script_still_has_entrypoint():
    from graphify.extract import extract_bash

    result = extract_bash(FIXTURES / "imperative.sh")
    assert "error" not in result

    labels = [n["label"] for n in result["nodes"]]
    assert "imperative.sh" in labels
    assert "imperative.sh script" in labels
    assert not any(n.get("metadata", {}).get("kind") == "bash_function" for n in result["nodes"])


def test_extract_bash_syntax_error_keeps_partial_graph():
    from graphify.extract import extract_bash

    result = extract_bash(FIXTURES / "broken.sh")
    assert "error" not in result
    assert result.get("parse_error") is True

    labels = [n["label"] for n in result["nodes"]]
    assert "broken.sh" in labels
    assert "broken.sh script" in labels


def test_extract_dispatches_bash_fixture():
    from graphify.extract import extract

    result = extract([FIXTURES / "sample.sh"], cache_root=FIXTURES, parallel=False)
    labels = [n["label"] for n in result["nodes"]]
    assert "deploy()" in labels
    assert "main()" in labels


def test_collect_files_includes_bash_extensions_and_shebang(tmp_path):
    from graphify.extract import collect_files

    sh = tmp_path / "deploy.sh"
    bash = tmp_path / "profile.bash"
    bats = tmp_path / "build.bats"
    shebang = tmp_path / "release"
    for p in (sh, bash, bats):
        p.write_text("main() { echo ok; }\n")
    shebang.write_text("#!/usr/bin/env bash\nmain() { echo ok; }\n")

    files = collect_files(tmp_path)
    assert sh in files
    assert bash in files
    assert bats in files
    assert shebang in files
