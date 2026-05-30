from pathlib import Path
from graphify.extract import extract_python, extract, collect_files, _make_id, extract_bash, extract_json, _DISPATCH

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


def test_extract_disambiguates_duplicate_symbol_ids_by_source_path(tmp_path):
    first = tmp_path / "apps/api/Program.cs"
    second = tmp_path / "tools/api/Program.cs"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("class Program { void Run() {} }\n", encoding="utf-8")
    second.write_text("class Program { void Run() {} }\n", encoding="utf-8")

    result = extract([first, second], cache_root=tmp_path)
    program_nodes = [
        node for node in result["nodes"]
        if node["label"] == "Program" and node.get("source_file", "").endswith("Program.cs")
    ]

    assert len(program_nodes) == 2
    assert len({node["id"] for node in program_nodes}) == 2

    node_ids = {node["id"] for node in result["nodes"]}
    program_by_source = {node["source_file"]: node["id"] for node in program_nodes}
    file_nodes_by_source = {
        node["source_file"]: node["id"]
        for node in result["nodes"]
        if node["label"] == "Program.cs"
    }

    assert set(program_by_source) == set(file_nodes_by_source)
    contains_edges = [
        edge for edge in result["edges"]
        if edge["relation"] == "contains" and edge["source_file"] in program_by_source
    ]
    assert len(contains_edges) == 2
    for edge in contains_edges:
        assert edge["source"] == file_nodes_by_source[edge["source_file"]]
        assert edge["target"] == program_by_source[edge["source_file"]]

    for edge in result["edges"]:
        if edge["relation"] in {"contains", "method"}:
            assert edge["source"] in node_ids, f"Dangling structural source: {edge}"
            assert edge["target"] in node_ids, f"Dangling structural target: {edge}"


def test_extract_updates_raw_call_callers_after_duplicate_id_disambiguation(tmp_path):
    first = tmp_path / "apps/api/Program.cs"
    second = tmp_path / "tools/api/Program.cs"
    target = tmp_path / "shared/Helper.cs"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    first.write_text("class Program { void Run() { SharedHelper(); } }\n", encoding="utf-8")
    second.write_text("class Program { void Run() {} }\n", encoding="utf-8")
    target.write_text("class Helper { void SharedHelper() {} }\n", encoding="utf-8")

    result = extract([first, second, target], cache_root=tmp_path)
    node_ids = {node["id"] for node in result["nodes"]}

    for edge in result["edges"]:
        if edge["relation"] == "calls":
            assert edge["source"] in node_ids
            assert edge["target"] in node_ids


def test_extract_rewires_unique_inheritance_stub_to_real_definition(tmp_path):
    definition = tmp_path / "interfaces.py"
    implementation = tmp_path / "services/BookStore.cs"
    definition.write_text("class BookStore:\n    pass\n", encoding="utf-8")
    implementation.parent.mkdir(parents=True)
    implementation.write_text("class SqliteBookStore : BookStore { }\n", encoding="utf-8")

    result = extract([definition, implementation], cache_root=tmp_path)
    node_by_id = {node["id"]: node for node in result["nodes"]}
    inherits_edges = [edge for edge in result["edges"] if edge["relation"] == "inherits"]

    matching = [
        edge for edge in inherits_edges
        if node_by_id[edge["source"]]["label"] == "SqliteBookStore"
        and node_by_id[edge["target"]]["label"] == "BookStore"
    ]

    assert matching
    assert matching[0]["target"] == next(
        node["id"] for node in result["nodes"]
        if node["label"] == "BookStore" and node.get("source_file") == "interfaces.py"
    )
    assert all(
        not (node["label"] == "BookStore" and not node.get("source_file"))
        for node in result["nodes"]
    )


def test_extract_keeps_stub_when_multiple_real_definitions_match(tmp_path):
    first = tmp_path / "a/interfaces.py"
    second = tmp_path / "b/interfaces.py"
    implementation = tmp_path / "services/BookStore.cs"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    implementation.parent.mkdir(parents=True)
    first.write_text("class BookStore:\n    pass\n", encoding="utf-8")
    second.write_text("class BookStore:\n    pass\n", encoding="utf-8")
    implementation.write_text("class SqliteBookStore : BookStore { }\n", encoding="utf-8")

    result = extract([first, second, implementation], cache_root=tmp_path)
    stubs = [
        node for node in result["nodes"]
        if node["label"] == "BookStore" and not node.get("source_file")
    ]

    assert stubs


def test_extract_does_not_rewire_inheritance_stub_to_same_named_function(tmp_path):
    definition = tmp_path / "factory.py"
    implementation = tmp_path / "services/BookStore.cs"
    definition.write_text("def BookStore():\n    return object()\n", encoding="utf-8")
    implementation.parent.mkdir(parents=True)
    implementation.write_text("class SqliteBookStore : BookStore { }\n", encoding="utf-8")

    result = extract([definition, implementation], cache_root=tmp_path)
    node_by_id = {node["id"]: node for node in result["nodes"]}
    inherits_edges = [edge for edge in result["edges"] if edge["relation"] == "inherits"]

    assert any(
        node["label"] == "BookStore" and not node.get("source_file")
        for node in result["nodes"]
    )
    assert not any(
        node_by_id[edge["source"]]["label"] == "SqliteBookStore"
        and node_by_id[edge["target"]]["label"] == "BookStore()"
        for edge in inherits_edges
    )


def test_extract_does_not_rewire_constructor_method_to_same_named_class(tmp_path):
    source = tmp_path / "Sample.java"
    source.write_text(
        "class DataProcessor {\n"
        "    public DataProcessor() {}\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    constructor_nodes = [
        node for node in result["nodes"]
        if node["label"] == ".DataProcessor()"
    ]
    assert constructor_nodes
    assert not any(
        edge["source"] == edge["target"]
        for edge in result["edges"]
    )


def test_collect_files_from_dir():
    from graphify.extract import _DISPATCH
    files = collect_files(FIXTURES)
    supported = set(_DISPATCH.keys())
    assert all(f.suffix in supported for f in files)
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


# --- Windows-spawn ProcessPool fallback (regression for #?) ---
# When the caller has no `if __name__ == "__main__":` guard, ProcessPoolExecutor
# on Windows raises BrokenProcessPool before any work completes. extract() must
# detect this, warn, and fall back to sequential extraction rather than
# propagating a 290-line traceback.

def test_extract_falls_back_to_sequential_when_parallel_returns_false(tmp_path, monkeypatch):
    """extract() must run sequential when _extract_parallel signals failure (returns False)."""
    from graphify import extract as extract_mod

    files = [FIXTURES / "sample.py"] * 25  # >= _PARALLEL_THRESHOLD triggers parallel branch
    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    calls = {"parallel": 0, "sequential": 0}
    real_sequential = extract_mod._extract_sequential

    def fake_parallel(uncached_work, per_file, effective_root, max_workers, total_files):
        calls["parallel"] += 1
        return False  # simulate the post-fix BrokenProcessPool branch

    def wrapped_sequential(*args, **kwargs):
        calls["sequential"] += 1
        return real_sequential(*args, **kwargs)

    monkeypatch.setattr(extract_mod, "_extract_parallel", fake_parallel)
    monkeypatch.setattr(extract_mod, "_extract_sequential", wrapped_sequential)

    result = extract_mod.extract(files, cache_root=cache_root)
    assert calls["parallel"] == 1, "parallel path should have been attempted once"
    assert calls["sequential"] == 1, "sequential fallback should have run exactly once"
    assert result["nodes"], "extract should still produce nodes after fallback"


def test_extract_parallel_returns_false_on_broken_pool(tmp_path, monkeypatch, capsys):
    """_extract_parallel must catch BrokenProcessPool internally and return False."""
    from concurrent.futures.process import BrokenProcessPool
    import concurrent.futures
    from graphify import extract as extract_mod

    class FakePool:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def submit(self, *a, **kw):
            raise BrokenProcessPool("simulated spawn failure")

    monkeypatch.setattr(
        concurrent.futures, "ProcessPoolExecutor", lambda *a, **kw: FakePool()
    )

    uncached = [(0, FIXTURES / "sample.py")]
    per_file: list = [None]
    ok = extract_mod._extract_parallel(uncached, per_file, tmp_path, 2, 1)
    assert ok is False, "function should report failure via return value, not raise"
    out = capsys.readouterr().out
    assert "BrokenProcessPool" in out, "user-facing warning must mention the failure"
    assert "__main__" in out, "warning must hint at the Windows __main__ guard idiom"


# ---------------------------------------------------------------------------
# Bash extractor tests (#866)
# ---------------------------------------------------------------------------

def test_dispatch_includes_sh_and_json():
    assert ".sh" in _DISPATCH
    assert ".bash" in _DISPATCH
    assert ".json" in _DISPATCH


def test_extract_bash_finds_functions():
    result = extract_bash(FIXTURES / "sample.sh")
    assert "error" not in result
    labels = {n["label"] for n in result["nodes"]}
    assert "build()" in labels
    assert "test_suite()" in labels
    assert "deploy()" in labels


def test_extract_bash_emits_defines_edges():
    result = extract_bash(FIXTURES / "sample.sh")
    relations = {e["relation"] for e in result["edges"]}
    assert "defines" in relations


def test_extract_bash_emits_calls_edges():
    result = extract_bash(FIXTURES / "sample.sh")
    calls = [(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"]
    # deploy() calls build() and test_suite(); test_suite() calls build()
    assert any("deploy" in s and "build" in t for s, t in calls)
    assert any("deploy" in s and "test_suite" in t for s, t in calls)
    assert any("test_suite" in s and "build" in t for s, t in calls)


def test_extract_bash_calls_have_extracted_confidence():
    result = extract_bash(FIXTURES / "sample.sh")
    for e in result["edges"]:
        if e["relation"] == "calls":
            assert e["confidence"] == "EXTRACTED"
            assert e.get("context") == "call"


def test_extract_bash_emits_source_imports_from(tmp_path):
    helpers = tmp_path / "helpers.sh"
    helpers.write_text("# helper\n")
    script = tmp_path / "deploy.sh"
    script.write_text(f"#!/bin/bash\nsource ./helpers.sh\nfoo() {{ echo hi; }}\n")
    result = extract_bash(script)
    import_edges = [e for e in result["edges"] if e["relation"] == "imports_from"]
    assert len(import_edges) >= 1
    assert import_edges[0].get("context") == "import"


def test_extract_bash_no_self_loops():
    result = extract_bash(FIXTURES / "sample.sh")
    for e in result["edges"]:
        assert e["source"] != e["target"], f"Self-loop: {e}"


def test_extract_bash_no_dangling_edges():
    result = extract_bash(FIXTURES / "sample.sh")
    node_ids = {n["id"] for n in result["nodes"]}
    for e in result["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e['source']}"
        # targets may reference external files (imports_from) — only check non-import edges
        if e["relation"] not in ("imports_from", "imports"):
            assert e["target"] in node_ids, f"Dangling target: {e['target']}"


def test_extract_bash_skip_builtins_in_calls():
    result = extract_bash(FIXTURES / "sample.sh")
    builtins = {"echo", "cd", "set", "export", "local", "mkdir", "if", "then"}
    call_targets = {e["target"] for e in result["edges"] if e["relation"] == "calls"}
    for b in builtins:
        assert not any(b in t for t in call_targets), f"Builtin '{b}' appeared as calls target"


def test_extract_bash_missing_grammar_returns_error():
    """extract_bash returns error dict when tree-sitter-bash not installed (mocked)."""
    import unittest.mock as mock
    import builtins
    real_import = builtins.__import__

    def patched(name, *args, **kwargs):
        if name == "tree_sitter_bash":
            raise ImportError("mocked")
        return real_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", side_effect=patched):
        result = extract_bash(FIXTURES / "sample.sh")
    assert "error" in result
    assert result["nodes"] == []


def test_extract_bash_rejects_command_substitution_as_call(tmp_path):
    """`$(build)` must not be recorded as a call edge to build()."""
    script = tmp_path / "command_substitution.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "build() { echo build; }\n"
        "$(build)\n"
    )
    result = extract_bash(script)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    call_pairs = [
        (labels.get(e["source"], e["source"]), labels.get(e["target"], e["target"]))
        for e in result["edges"]
        if e["relation"] == "calls"
    ]
    assert call_pairs == [], f"Command substitution erroneously emitted call edges: {call_pairs}"


def test_extract_bash_process_substitution_not_recorded(tmp_path):
    """`<(helper)` (process substitution) must not be recorded as a call edge."""
    script = tmp_path / "process_substitution.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "helper() { echo h; }\n"
        "diff <(helper) <(helper)\n"
    )
    result = extract_bash(script)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    call_pairs = [
        (labels.get(e["source"], e["source"]), labels.get(e["target"], e["target"]))
        for e in result["edges"]
        if e["relation"] == "calls"
    ]
    assert call_pairs == [], f"Process substitution erroneously emitted call edges: {call_pairs}"


def test_extract_bash_shadowing_function_is_recorded(tmp_path):
    """User-defined function shadowing an external command (install/find/etc.) must still produce a call edge."""
    script = tmp_path / "shadowing.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "install() { echo install; }\n"
        "deploy() { install; }\n"
    )
    result = extract_bash(script)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    call_pairs = [
        (labels.get(e["source"], e["source"]), labels.get(e["target"], e["target"]))
        for e in result["edges"]
        if e["relation"] == "calls"
    ]
    assert ("deploy()", "install()") in call_pairs, (
        f"Shadowing function call not recorded; got: {call_pairs}"
    )


def test_extract_bash_creates_entrypoint_node(tmp_path):
    """Every bash file produces a `bash_entrypoint` node distinct from the file node, joined by a `contains` edge."""
    script = tmp_path / "with_entrypoint.sh"
    script.write_text("#!/usr/bin/env bash\nfoo() { :; }\n")
    result = extract_bash(script)
    kinds = [n.get("metadata", {}).get("kind") for n in result["nodes"]]
    assert "bash_entrypoint" in kinds, f"No bash_entrypoint node; kinds={kinds}"
    assert "file" in kinds, f"No file node; kinds={kinds}"
    file_node = next(n for n in result["nodes"] if n.get("metadata", {}).get("kind") == "file")
    entry_node = next(n for n in result["nodes"] if n.get("metadata", {}).get("kind") == "bash_entrypoint")
    contains_edges = [
        e for e in result["edges"]
        if e["relation"] == "contains" and e["source"] == file_node["id"] and e["target"] == entry_node["id"]
    ]
    assert contains_edges, "Missing contains edge from file → bash_entrypoint"


def test_extract_bash_top_level_call_attributes_to_entrypoint(tmp_path):
    """Top-level function call attaches to the entrypoint node, not orphaned."""
    script = tmp_path / "top_level_call.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "build() { echo build; }\n"
        "build\n"
    )
    result = extract_bash(script)
    entry_node = next(
        (n for n in result["nodes"] if n.get("metadata", {}).get("kind") == "bash_entrypoint"),
        None,
    )
    assert entry_node is not None, "No entrypoint node created"
    call_pairs = [
        (e["source"], e["target"])
        for e in result["edges"]
        if e["relation"] == "calls"
    ]
    target_ids = {tgt for _, tgt in call_pairs if any(n["id"] == tgt and n["label"] == "build()" for n in result["nodes"])}
    source_ids_to_build = {src for src, tgt in call_pairs if tgt in target_ids}
    assert entry_node["id"] in source_ids_to_build, (
        f"Top-level call to build not attributed to entrypoint; calls={call_pairs}"
    )


# ---------------------------------------------------------------------------
# PR #893 regression tests — bash extractor Copilot review findings
# ---------------------------------------------------------------------------


def test_extract_bash_entrypoint_no_collision_with_function_named_script(tmp_path):
    """Entrypoint node must have a distinct ID from a function also named 'script'.

    _make_id strips leading/trailing '_.' from each part, so
    _make_id(stem, "__script__") strips to _make_id(stem, "script"), which is
    identical to _make_id(stem, "script") for a function named 'script'.
    """
    script = tmp_path / "deploy.sh"
    script.write_text("#!/usr/bin/env bash\nfunction script() { echo hi; }\n")
    result = extract_bash(script)
    entry_nodes = [n for n in result["nodes"] if n.get("metadata", {}).get("kind") == "bash_entrypoint"]
    func_nodes = [n for n in result["nodes"] if n.get("metadata", {}).get("kind") == "bash_function"]
    assert entry_nodes, "Must have a bash_entrypoint node"
    assert func_nodes, "Must have a bash_function node for 'script'"
    entry_id = entry_nodes[0]["id"]
    func_id = func_nodes[0]["id"]
    assert entry_id != func_id, (
        f"Entrypoint ID must not collide with function 'script' ID; both are '{entry_id}'"
    )


def test_extract_bash_nested_function_calls_recorded(tmp_path):
    """Calls made inside a nested (inner) function body must be collected."""
    script = tmp_path / "nested.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "function do_work() { :; }\n"
        "function outer() {\n"
        "    function inner() {\n"
        "        do_work\n"
        "    }\n"
        "    inner\n"
        "}\n"
    )
    result = extract_bash(script)
    node_id_by_label = {n["label"].rstrip("()"): n["id"] for n in result["nodes"]}
    assert "inner" in node_id_by_label, f"inner function must be discovered; labels={list(node_id_by_label)}"
    assert "do_work" in node_id_by_label, f"do_work function must be discovered; labels={list(node_id_by_label)}"
    calls = {(e["source"], e["target"]) for e in result["edges"] if e.get("relation") == "calls"}
    inner_id = node_id_by_label["inner"]
    do_work_id = node_id_by_label["do_work"]
    assert (inner_id, do_work_id) in calls, (
        f"inner→do_work call edge must be recorded; got calls={calls}"
    )


def test_extract_bash_source_user_defined_emits_calls_not_imports_from(tmp_path):
    """When 'source' is a user-defined function, 'source ./file.sh' must emit a
    calls edge, not an imports_from edge.  The user-defined function shadows the
    built-in source command."""
    helpers = tmp_path / "helpers.sh"
    helpers.write_text("#!/bin/bash\n")
    script = tmp_path / "run.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "function source() { echo 'custom source'; }\n"
        "source ./helpers.sh\n"
    )
    result = extract_bash(script)
    import_edges = [e for e in result["edges"] if e.get("relation") == "imports_from"]
    assert not import_edges, (
        f"'source' is a user-defined function; 'source ./helpers.sh' must not emit imports_from; got: {import_edges}"
    )


# ---------------------------------------------------------------------------
# JSON extractor tests (#866)
# ---------------------------------------------------------------------------

def test_extract_json_top_level_keys():
    result = extract_json(FIXTURES / "sample.json")
    assert "error" not in result
    labels = {n["label"] for n in result["nodes"]}
    assert "name" in labels
    assert "version" in labels
    assert "scripts" in labels
    assert "dependencies" in labels


def test_extract_json_nested_contains():
    result = extract_json(FIXTURES / "sample.json")
    contains = [(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "contains"]
    assert any("scripts" in s and "build" in t for s, t in contains)
    assert any("scripts" in s and "test" in t for s, t in contains)
    assert any("dependencies" in s and "react" in t for s, t in contains)


def test_extract_json_dependencies_become_imports():
    result = extract_json(FIXTURES / "sample.json")
    import_edges = [e for e in result["edges"] if e["relation"] == "imports"]
    targets = {e["target"] for e in import_edges}
    assert any("react" in t for t in targets)
    assert any("axios" in t for t in targets)
    assert any("typescript" in t for t in targets)


def test_extract_json_extends_resolved():
    result = extract_json(FIXTURES / "sample_tsconfig.json")
    extends_edges = [e for e in result["edges"] if e["relation"] == "extends"]
    assert len(extends_edges) >= 1
    assert extends_edges[0].get("context") == "import"


def test_extract_json_large_file_skipped(tmp_path):
    big = tmp_path / "big.json"
    # Write a JSON file just over 1 MiB
    big.write_bytes(b'{"x": "' + b"a" * (1_048_576) + b'"}')
    result = extract_json(big)
    assert "error" in result
    assert result["nodes"] == []


def test_extract_json_handles_invalid_json(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{this is not: valid json!!!")
    result = extract_json(bad)
    # Should not crash — returns empty or error result
    assert isinstance(result, dict)
    assert "nodes" in result


def test_extract_json_no_self_loops():
    result = extract_json(FIXTURES / "sample.json")
    for e in result["edges"]:
        assert e["source"] != e["target"], f"Self-loop: {e}"


def test_extract_bash_via_dispatch():
    from graphify.extract import _get_extractor
    assert _get_extractor(Path("foo.sh")) is extract_bash
    assert _get_extractor(Path("foo.bash")) is extract_bash


def test_extract_json_via_dispatch():
    from graphify.extract import _get_extractor
    assert _get_extractor(Path("foo.json")) is extract_json


def test_extract_bash_node_metadata_is_sanitized():
    """Bash extractor must route node metadata through sanitize_metadata so
    HTML-sensitive characters cannot reach downstream graph viewers raw."""
    result = extract_bash(FIXTURES / "sample.sh")
    assert "error" not in result
    for node in result["nodes"]:
        meta = node.get("metadata", {})
        # Static bash metadata is currently {"language": "bash", "kind": "code"};
        # both pass through sanitisation unchanged, but the values must be the
        # post-sanitisation strings (not raw objects).
        for value in meta.values():
            if isinstance(value, str):
                assert "<" not in value
                assert "\x00" not in value


# ── Barrel re-export tests ────────────────────────────────────────────────────


def test_barrel_reexport_emits_re_exports_edges():
    """export { X } from './mod' must emit re_exports edges for each named specifier."""
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "barrel_reexport.ts")
    reexports = [e for e in result["edges"] if e["relation"] == "re_exports"]
    targets = [e["target"] for e in reexports]
    # Should find re_exports for readCookie, writeCookie, getFullUrl, basePathRewrite
    assert len(reexports) >= 4, f"Expected >=4 re_exports, got {len(reexports)}: {targets}"
    assert any("readcookie" in t for t in targets)
    assert any("writecookie" in t for t in targets)
    assert any("getfullurl" in t for t in targets)
    assert any("basepathrewrite" in t for t in targets)


def test_barrel_reexport_emits_imports_from():
    """Barrel file must emit file-level imports_from edges to source modules."""
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "barrel_reexport.ts")
    imports_from = [e for e in result["edges"] if e["relation"] == "imports_from"]
    targets = [e["target"] for e in imports_from]
    assert any("cookiehelpers" in t for t in targets)
    assert any("urlhelpers" in t for t in targets)
    assert any("storagehelpers" in t for t in targets)


def test_barrel_reexport_context_tagged():
    """re_exports edges should have context='re-export'."""
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "barrel_reexport.ts")
    reexports = [e for e in result["edges"] if e["relation"] == "re_exports"]
    for e in reexports:
        assert e.get("context") == "re-export"


def test_barrel_local_exports_still_extracted():
    """export function/const in a barrel file must still create nodes."""
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "barrel_reexport.ts")
    labels = [n["label"] for n in result["nodes"]]
    assert "localHelper()" in labels or "localHelper" in labels
    # File node should also exist
    assert any("barrel_reexport" in n["label"] for n in result["nodes"])


def test_barrel_reexport_confidence_extracted():
    """All re_exports edges should have confidence=EXTRACTED."""
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "barrel_reexport.ts")
    reexports = [e for e in result["edges"] if e["relation"] == "re_exports"]
    for e in reexports:
        assert e["confidence"] == "EXTRACTED"


def test_semantic_reference_edges_carry_context_and_source():
    from graphify.extract import _semantic_reference_edge

    edge = _semantic_reference_edge(
        "source_node",
        "target_node",
        "parameter_type",
        "/repo/src/Foo.cs",
        12,
    )

    assert edge == {
        "source": "source_node",
        "target": "target_node",
        "relation": "references",
        "context": "parameter_type",
        "confidence": "EXTRACTED",
        "source_file": "/repo/src/Foo.cs",
        "source_location": "L12",
        "weight": 1.0,
    }


def test_pure_export_no_from_not_treated_as_reexport():
    """export { localVar } without 'from' should NOT create re_exports edges."""
    from graphify.extract import extract_js
    import tempfile
    code = b"const x = 1;\nexport { x };\n"
    with tempfile.NamedTemporaryFile(suffix=".ts", delete=False) as f:
        f.write(code)
        f.flush()
        result = extract_js(Path(f.name))
    reexports = [e for e in result["edges"] if e["relation"] == "re_exports"]
    assert reexports == [], f"Pure export should not create re_exports: {reexports}"


def test_dart_child_node_ids_are_stem_based(tmp_path):
    """Dart child node IDs must be built from _file_stem rather than absolute path."""
    from graphify.extract import extract_dart, _file_stem, _make_id

    src_file = tmp_path / "mydir" / "sample.dart"
    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_bytes(b"class MyClass {}\nvoid myFunc() {}\n")

    result = extract_dart(src_file)

    stem = _file_stem(src_file)  # -> "mydir.sample"
    expected_class_nid = _make_id(stem, "MyClass")   # -> "mydir_sample_myclass"
    expected_func_nid  = _make_id(stem, "myFunc")    # -> "mydir_sample_myfunc"

    node_ids = {n["id"] for n in result["nodes"]}

    assert expected_class_nid in node_ids, (
        f"Class node ID '{expected_class_nid}' not found in {node_ids}. "
        "extract_dart may still be using str(path) instead of _file_stem(path)."
    )
    assert expected_func_nid in node_ids, (
        f"Function node ID '{expected_func_nid}' not found in {node_ids}. "
        "extract_dart may still be using str(path) instead of _file_stem(path)."
    )

    # Sanity-check: no child node ID should contain any path separator fragment.
    file_nid = next(n["id"] for n in result["nodes"] if n.get("label") == src_file.name)
    for node in result["nodes"]:
        if node["id"] == file_nid:
            continue
        assert "_" + stem.replace(".", "_") in node["id"] or node["id"].startswith(stem.replace(".", "_")), (
            f"Child node ID '{node['id']}' does not start with the expected stem prefix '{stem}'. "
            "This suggests an absolute path is still leaking into the ID."
        )


