from pathlib import Path
from graphify.extract import (
    extract_python, extract, collect_files, _make_id,
    hcl_make_file_id, hcl_make_block_id, hcl_make_target_id,
    hcl_make_diagnostic, hcl_cap_diagnostics, _hcl_scrub_secrets,
    _HCL_DIAGNOSTIC_CODES, _HCL_MAX_DIAGNOSTICS_PER_FILE,
    hcl_make_node, hcl_make_edge, hcl_make_result,
    hcl_redact_for_external, _hcl_hash_redact,
    resolve_module_source, _hcl_classify_source, _hcl_canonicalize_remote_uri,
    extract_hcl,
    _HCL_MAX_FILE_BYTES, _HCL_MAX_AST_NODES,
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
    supported = set(_DISPATCH.keys()) | {".tf", ".tfvars"}
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


# --- HCL node ID tests ---

def test_hcl_make_file_id_basic():
    repo = Path("/repo")
    fid = hcl_make_file_id(repo, Path("/repo/terraform/main.tf"))
    assert fid == "hcl_file:terraform/main.tf"


def test_hcl_make_file_id_forward_slashes():
    repo = Path("/repo")
    fid = hcl_make_file_id(repo, Path("/repo/terraform/modules/vpc/main.tf"))
    assert "/" in fid
    assert "\\" not in fid


def test_hcl_make_file_id_deterministic():
    repo = Path("/repo")
    p = Path("/repo/modules/main.tf")
    assert hcl_make_file_id(repo, p) == hcl_make_file_id(repo, p)


def test_hcl_make_file_id_prefix():
    fid = hcl_make_file_id(Path("/r"), Path("/r/a.tf"))
    assert fid.startswith("hcl_file:")


def test_hcl_make_block_id_resource():
    fid = "hcl_file:modules/vpc/main.tf"
    bid = hcl_make_block_id(fid, "resource", "aws_vpc.main")
    assert bid == "hcl_file:modules/vpc/main.tf::resource:aws_vpc.main"


def test_hcl_make_block_id_module():
    fid = "hcl_file:clusters/main.tf"
    bid = hcl_make_block_id(fid, "module", "network")
    assert bid == "hcl_file:clusters/main.tf::module:network"


def test_hcl_make_block_id_locals():
    fid = "hcl_file:main.tf"
    bid = hcl_make_block_id(fid, "locals", "locals_ab12cd34")
    assert bid == "hcl_file:main.tf::locals:locals_ab12cd34"


def test_hcl_make_block_id_preserves_colons():
    """Block IDs must preserve colon namespace prefixes (not use _make_id)."""
    fid = "hcl_file:main.tf"
    bid = hcl_make_block_id(fid, "resource", "aws_s3_bucket.my_bucket")
    assert "hcl_file:" in bid
    assert "::resource:" in bid


def test_hcl_make_target_id_local():
    tid = hcl_make_target_id("module_source_local", "modules/vpc")
    assert tid == "hcl_target:module_source_local:modules/vpc"


def test_hcl_make_target_id_remote():
    tid = hcl_make_target_id("module_source_remote", "github.com:path_sha256=abc123:ref=v1.0")
    assert tid.startswith("hcl_target:")
    assert "module_source_remote" in tid


def test_hcl_make_target_id_deterministic():
    a = hcl_make_target_id("module_source_local", "modules/vpc")
    b = hcl_make_target_id("module_source_local", "modules/vpc")
    assert a == b


def test_hcl_ids_different_kinds_distinct():
    """Identically named blocks of different kinds produce different IDs."""
    fid = "hcl_file:main.tf"
    resource_id = hcl_make_block_id(fid, "resource", "foo")
    data_id = hcl_make_block_id(fid, "data", "foo")
    module_id = hcl_make_block_id(fid, "module", "foo")
    assert resource_id != data_id != module_id


# --- HCL diagnostic collector tests ---

def test_hcl_diagnostic_schema_file_scoped():
    d = hcl_make_diagnostic(
        "hcl_partial_parse", "Partial parse in main.tf",
        file_path="terraform/main.tf",
        source_span={"start_line": 1, "start_column": 1, "end_line": 5, "end_column": 2},
    )
    assert d["code"] == "hcl_partial_parse"
    assert d["severity"] == "warning"
    assert d["file_path"] == "terraform/main.tf"
    assert d["source_span"]["start_line"] == 1
    assert d["reason"] is None
    assert d["related_entity_id"] is None


def test_hcl_diagnostic_schema_run_scoped():
    d = hcl_make_diagnostic("hcl_parse_error", "tree-sitter-hcl not installed", reason="missing_dependency")
    assert d["file_path"] is None
    assert d["source_span"] is None
    assert d["reason"] == "missing_dependency"
    assert d["severity"] == "error"


def test_hcl_diagnostic_all_codes_have_severity():
    for code, expected_severity in _HCL_DIAGNOSTIC_CODES.items():
        d = hcl_make_diagnostic(code, f"test {code}")
        assert d["severity"] == expected_severity


def test_hcl_diagnostic_cap_under_limit():
    diags = [hcl_make_diagnostic("hcl_partial_parse", f"msg {i}") for i in range(10)]
    capped = hcl_cap_diagnostics(diags)
    assert len(capped) == 10


def test_hcl_diagnostic_cap_over_limit():
    diags = [hcl_make_diagnostic("hcl_partial_parse", f"msg {i}") for i in range(250)]
    capped = hcl_cap_diagnostics(diags)
    assert len(capped) == _HCL_MAX_DIAGNOSTICS_PER_FILE
    assert capped[0]["message"] == "msg 0"  # deterministic: keeps first entries


def test_hcl_scrub_secrets_token():
    text = "source = https://github.com?token=abc123secret"
    scrubbed = _hcl_scrub_secrets(text)
    assert "abc123secret" not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_hcl_scrub_secrets_aws_key():
    text = "Found key AKIAIOSFODNN7EXAMPLE in config"
    scrubbed = _hcl_scrub_secrets(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed


def test_hcl_scrub_secrets_clean_text():
    text = "Normal diagnostic message about module vpc"
    assert _hcl_scrub_secrets(text) == text


def test_hcl_diagnostic_scrubs_message():
    d = hcl_make_diagnostic("hcl_parse_error", "Failed with token=supersecret123")
    assert "supersecret123" not in d["message"]


# --- HCL output builder tests ---

def test_hcl_make_node_required_fields():
    n = hcl_make_node("hcl_file:main.tf", "main.tf", "main.tf", 1)
    assert n["id"] == "hcl_file:main.tf"
    assert n["label"] == "main.tf"
    assert n["file_type"] == "code"
    assert n["source_file"] == "main.tf"
    assert n["source_location"] == "L1"
    assert n["confidence_score"] == 1.0


def test_hcl_make_node_empty_source_file():
    """Non-repo-backed target nodes use empty string for source_file."""
    n = hcl_make_node("hcl_target:module_source_remote:x", "remote:x", "", 5)
    assert n["source_file"] == ""
    assert n["source_location"] == "L5"


def test_hcl_make_edge_resolved():
    e = hcl_make_edge("src", "tgt", "contains", "main.tf", 3)
    assert e["confidence"] == "EXTRACTED"
    assert e["confidence_score"] == 1.0
    assert e["resolution_status"] == "resolved"
    assert e["unresolved_target_key"] is None


def test_hcl_make_edge_declared_only():
    e = hcl_make_edge(
        "src", "tgt", "module_source", "main.tf", 10,
        resolved=False, resolution_reason="remote_source",
        unresolved_target_key="hcl:module_source_remote:example.com",
    )
    assert e["confidence"] == "INFERRED"
    assert e["confidence_score"] == 0.8
    assert e["resolution_status"] == "declared_only"
    assert e["resolution_reason"] == "remote_source"
    assert e["unresolved_target_key"] == "hcl:module_source_remote:example.com"


def test_hcl_make_edge_has_weight():
    e = hcl_make_edge("s", "t", "contains", "a.tf", 1)
    assert e["weight"] == 1.0


def test_hcl_make_result_shape():
    r = hcl_make_result([], [], [], [])
    assert set(r.keys()) == {
        "nodes", "edges", "raw_calls", "diagnostics",
        "hcl_deferred_refs", "input_tokens", "output_tokens", "error",
    }
    assert r["raw_calls"] == []
    assert r["input_tokens"] == 0
    assert r["output_tokens"] == 0
    assert r["error"] is None


def test_hcl_make_result_with_error():
    r = hcl_make_result([], [], [], [], error="parse failed")
    assert r["error"] == "parse failed"


def test_hcl_make_result_passes_validate():
    """Output must pass Graphify's validate.py checks."""
    from graphify.validate import validate_extraction
    node = hcl_make_node("hcl_file:main.tf", "main.tf", "main.tf", 1)
    block = hcl_make_node("hcl_file:main.tf::resource:aws_vpc.main", "resource:aws_vpc.main", "main.tf", 3)
    edge = hcl_make_edge("hcl_file:main.tf", block["id"], "contains", "main.tf", 1)
    r = hcl_make_result([node, block], [edge], [], [])
    errors = validate_extraction(r)
    assert errors == [], f"validate_extraction errors: {errors}"


# --- HCL redaction tests ---

def test_hcl_scrub_deterministic():
    """Same input always produces same scrubbed output."""
    text = "error with token=abc123 in module"
    assert _hcl_scrub_secrets(text) == _hcl_scrub_secrets(text)


def test_hcl_hash_redact_deterministic():
    assert _hcl_hash_redact("modules/vpc") == _hcl_hash_redact("modules/vpc")


def test_hcl_hash_redact_different_inputs():
    assert _hcl_hash_redact("a") != _hcl_hash_redact("b")


def test_hcl_redact_external_source_file():
    node = hcl_make_node("hcl_file:main.tf", "resource:aws_vpc.main", "terraform/main.tf", 1)
    r = hcl_redact_for_external(hcl_make_result([node], [], [], []))
    assert r["nodes"][0]["source_file"] != "terraform/main.tf"
    assert len(r["nodes"][0]["source_file"]) == 16  # sha256[:16]


def test_hcl_redact_external_unresolved_key():
    edge = hcl_make_edge(
        "s", "t", "module_source", "main.tf", 1,
        resolved=False, unresolved_target_key="hcl:module_source_remote:github.com/org/repo",
    )
    r = hcl_redact_for_external(hcl_make_result([], [edge], [], []))
    assert "github.com" not in r["edges"][0]["unresolved_target_key"]


def test_hcl_redact_external_target_id():
    node = hcl_make_node("hcl_target:module_source_remote:github.com/org/repo", "remote:x", "", 1)
    r = hcl_redact_for_external(hcl_make_result([node], [], [], []))
    assert "github.com" not in r["nodes"][0]["id"]
    assert r["nodes"][0]["id"].startswith("hcl_target:")


def test_hcl_redact_preserves_file_node_ids():
    """File node IDs (hcl_file:) are not target nodes and keep their IDs."""
    node = hcl_make_node("hcl_file:main.tf", "main.tf", "main.tf", 1)
    r = hcl_redact_for_external(hcl_make_result([node], [], [], []))
    assert r["nodes"][0]["id"] == "hcl_file:main.tf"


# --- Module source resolver tests ---

def test_classify_local_relative():
    assert _hcl_classify_source("./modules/vpc") == "local_relative"
    assert _hcl_classify_source("../modules/vpc") == "local_relative"


def test_classify_local_absolute():
    assert _hcl_classify_source("/opt/modules/vpc") == "local_absolute"
    assert _hcl_classify_source("C:/modules/vpc") == "local_absolute"


def test_classify_remote_url():
    assert _hcl_classify_source("https://github.com/org/repo") == "remote_url"
    assert _hcl_classify_source("git::https://github.com/org/repo") == "remote_url"


def test_classify_registry():
    assert _hcl_classify_source("hashicorp/consul/aws") == "registry"


def test_classify_opaque():
    assert _hcl_classify_source("s3::https://bucket/key") == "remote_url"
    assert _hcl_classify_source("some-unknown-source") == "opaque"


def test_resolve_missing_source():
    r = resolve_module_source(None, Path("/repo"), Path("/repo"), set())
    assert r["resolution_status"] == "declared_only"
    assert r["resolution_reason"] == "missing_source_attr"
    assert len(r["diagnostics"]) == 1
    assert r["diagnostics"][0]["code"] == "hcl_ineligible_module"


def test_resolve_empty_source():
    r = resolve_module_source("", Path("/repo"), Path("/repo"), set())
    assert r["resolution_reason"] == "empty_source_literal"


def test_resolve_local_relative_resolved(tmp_path):
    (tmp_path / "modules" / "vpc").mkdir(parents=True)
    (tmp_path / "clusters").mkdir()
    r = resolve_module_source(
        "../modules/vpc",
        tmp_path / "clusters",
        tmp_path,
        {"modules/vpc"},
    )
    assert r["resolution_status"] == "resolved"
    assert r["target_nid"] == "hcl_target:module_source_local:modules/vpc"
    assert r["unresolved_target_key"] is None


def test_resolve_local_relative_excluded_by_scope(tmp_path):
    (tmp_path / "other" / "mod").mkdir(parents=True)
    r = resolve_module_source(
        "./other/mod",
        tmp_path,
        tmp_path,
        set(),
        dependency_discovery_dirs={"other/mod"},
    )
    assert r["resolution_status"] == "declared_only"
    assert r["resolution_reason"] == "excluded_by_scope"


def test_resolve_local_relative_not_in_scope(tmp_path):
    (tmp_path / "somewhere").mkdir()
    r = resolve_module_source("./somewhere", tmp_path, tmp_path, set())
    assert r["resolution_status"] == "declared_only"
    assert r["resolution_reason"] == "not_in_scope"
    assert r["unresolved_target_key"] is not None


def test_resolve_local_absolute_never_resolved():
    r = resolve_module_source("/etc/terraform/modules", Path("/repo"), Path("/repo"), set())
    assert r["resolution_status"] == "declared_only"
    assert r["resolution_reason"] == "absolute_source_path"
    assert "/etc" not in r["target_nid"]  # raw path must not leak


def test_resolve_outside_repo(tmp_path):
    (tmp_path / "repo").mkdir()
    r = resolve_module_source(
        "../../outside",
        tmp_path / "repo",
        tmp_path / "repo",
        set(),
    )
    assert r["resolution_status"] == "declared_only"
    assert r["resolution_reason"] == "outside_repo"


def test_resolve_remote_url():
    r = resolve_module_source(
        "git::https://GitHub.com/org/repo//subdir?ref=v1.0",
        Path("/repo"), Path("/repo"), set(),
    )
    assert r["resolution_status"] == "declared_only"
    assert r["resolution_reason"] == "remote_source"
    assert "github.com" in r["target_nid"].lower()
    assert r["collision_suffix_sha256"] is not None


def test_resolve_remote_mutable_ref():
    r = resolve_module_source(
        "git::https://github.com/org/repo?ref=main",
        Path("/repo"), Path("/repo"), set(),
    )
    assert r["resolution_reason"] == "temporal_instability"


def test_resolve_registry():
    r = resolve_module_source("hashicorp/consul/aws", Path("/repo"), Path("/repo"), set())
    assert r["resolution_status"] == "declared_only"
    assert r["resolution_reason"] == "registry_source"


def test_resolve_control_chars_rejected():
    r = resolve_module_source("./modules/\x00evil", Path("/repo"), Path("/repo"), set())
    assert r["resolution_reason"] == "non_literal_source"


def test_canonical_uri_lowercase_host():
    canonical, _, _ = _hcl_canonicalize_remote_uri("https://GitHub.COM/org/repo")
    assert "github.com" in canonical


def test_canonical_uri_sorted_params():
    c1, _, _ = _hcl_canonicalize_remote_uri("https://host/p?b=2&a=1")
    c2, _, _ = _hcl_canonicalize_remote_uri("https://host/p?a=1&b=2")
    assert c1 == c2


def test_canonical_uri_strips_default_port():
    c, _, _ = _hcl_canonicalize_remote_uri("https://host:443/path")
    assert ":443" not in c


def test_canonical_uri_preserves_ref():
    c, _, _ = _hcl_canonicalize_remote_uri("https://host/p?ref=v1.0")
    assert "ref=v1.0" in c


def test_canonical_uri_strips_sensitive_keys():
    c, _, _ = _hcl_canonicalize_remote_uri("https://host/p?token=secret&ref=v1")
    assert "secret" not in c
    assert "ref=v1" in c


def test_canonical_uri_deterministic():
    a, _, _ = _hcl_canonicalize_remote_uri("git::https://github.com/org/repo//sub?ref=v1")
    b, _, _ = _hcl_canonicalize_remote_uri("git::https://github.com/org/repo//sub?ref=v1")
    assert a == b


def test_resolve_hmac_absent():
    """Missing HMAC key produces empty fingerprint, extraction still works."""
    r = resolve_module_source("./modules/vpc", Path("/repo"), Path("/repo"), set())
    assert r["source_fingerprint_hmac_sha256"] == ""
    assert r["resolution_status"] in ("resolved", "declared_only")


# --- AST walker / extract_hcl tests ---

def test_extract_hcl_all_7_block_types():
    result = extract_hcl(FIXTURES / "sample.tf", FIXTURES)
    labels = [n["label"] for n in result["nodes"]]
    assert any("resource:aws_vpc.main" in l for l in labels)
    assert any("data:aws_ami.ubuntu" in l for l in labels)
    assert any("module:network" in l for l in labels)
    assert any("variable:region" in l for l in labels)
    assert any("output:vpc_id" in l for l in labels)
    assert any("locals:" in l for l in labels)
    assert any("provider:aws" in l for l in labels)


def test_extract_hcl_file_node():
    result = extract_hcl(FIXTURES / "sample.tf", FIXTURES)
    file_nodes = [n for n in result["nodes"] if n["id"].startswith("hcl_file:") and "::" not in n["id"]]
    assert len(file_nodes) == 1
    assert file_nodes[0]["label"] == "sample.tf"


def test_extract_hcl_containment_edges():
    result = extract_hcl(FIXTURES / "sample.tf", FIXTURES)
    block_nodes = [n for n in result["nodes"] if "::" in n["id"]]
    contains_edges = [e for e in result["edges"] if e["relation"] == "contains"]
    assert len(contains_edges) == len(block_nodes)
    block_ids = {n["id"] for n in block_nodes}
    for edge in contains_edges:
        assert edge["target"] in block_ids


def test_extract_hcl_no_attribute_nodes():
    """No nodes for individual attributes within blocks."""
    result = extract_hcl(FIXTURES / "sample.tf", FIXTURES)
    for node in result["nodes"]:
        assert "cidr_block" not in node["label"]
        assert "most_recent" not in node["label"]
        assert "default" not in node["label"]


def test_extract_hcl_node_count():
    """1 file + 7 blocks = 8 nodes."""
    result = extract_hcl(FIXTURES / "sample.tf", FIXTURES)
    assert len(result["nodes"]) == 8


def test_extract_hcl_deterministic():
    r1 = extract_hcl(FIXTURES / "sample.tf", FIXTURES)
    r2 = extract_hcl(FIXTURES / "sample.tf", FIXTURES)
    assert r1["nodes"] == r2["nodes"]
    assert r1["edges"] == r2["edges"]


def test_extract_hcl_tfvars_file_node_only():
    result = extract_hcl(FIXTURES / "sample.tfvars", FIXTURES)
    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["id"].startswith("hcl_file:")
    assert len(result["edges"]) == 0


def test_extract_hcl_result_shape():
    result = extract_hcl(FIXTURES / "sample.tf", FIXTURES)
    assert "nodes" in result
    assert "edges" in result
    assert "raw_calls" in result
    assert "diagnostics" in result
    assert "hcl_deferred_refs" in result
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0
    assert result["error"] is None


def test_extract_hcl_block_ids_use_namespaces():
    result = extract_hcl(FIXTURES / "sample.tf", FIXTURES)
    for node in result["nodes"]:
        assert node["id"].startswith("hcl_file:") or node["id"].startswith("hcl_target:")


def test_extract_hcl_passes_validate():
    from graphify.validate import validate_extraction
    result = extract_hcl(FIXTURES / "sample.tf", FIXTURES)
    errors = validate_extraction(result)
    assert errors == [], f"validate_extraction errors: {errors}"


# --- Module source detection and deferred refs tests ---

def test_extract_hcl_module_deferred_refs():
    """Module blocks emit deferred refs for non-meta argument keys."""
    result = extract_hcl(FIXTURES / "sample_modules.tf", FIXTURES)
    refs = result["hcl_deferred_refs"]
    input_refs = [r for r in refs if r["kind"] == "module_input"]
    # "network" module has cidr and name as non-meta args
    network_refs = [r for r in input_refs if r["module_name"] == "network"]
    keys = {r["argument_key"] for r in network_refs}
    assert "cidr" in keys
    assert "name" in keys
    # Meta-arguments must be excluded
    assert "providers" not in keys
    assert "depends_on" not in keys
    assert "source" not in keys


def test_extract_hcl_module_no_refs_for_remote():
    """Remote/registry modules don't produce deferred refs (no resolvable source_dir)."""
    result = extract_hcl(FIXTURES / "sample_modules.tf", FIXTURES)
    refs = result["hcl_deferred_refs"]
    remote_refs = [r for r in refs if r["module_name"] == "remote"]
    assert len(remote_refs) == 0


def test_extract_hcl_interpolated_source_diagnostic():
    """Non-literal source expression emits hcl_ineligible_module diagnostic."""
    result = extract_hcl(FIXTURES / "sample_modules.tf", FIXTURES)
    diags = [d for d in result["diagnostics"] if d["code"] == "hcl_ineligible_module"
             and d.get("reason") == "non_literal_source"]
    assert len(diags) >= 1


def test_extract_hcl_missing_source_diagnostic():
    """Module with no source attribute emits hcl_ineligible_module diagnostic."""
    result = extract_hcl(FIXTURES / "sample_modules.tf", FIXTURES)
    diags = [d for d in result["diagnostics"] if d["code"] == "hcl_ineligible_module"
             and d.get("reason") == "missing_source_attr"]
    assert len(diags) >= 1


def test_extract_hcl_deferred_ref_schema():
    """Deferred refs have all required fields."""
    result = extract_hcl(FIXTURES / "sample_modules.tf", FIXTURES)
    for ref in result["hcl_deferred_refs"]:
        assert "kind" in ref
        assert "caller_nid" in ref
        assert "module_name" in ref
        assert "argument_key" in ref
        assert "source_file" in ref
        assert "source_location" in ref


# --- Error resilience and resource limits tests ---

def test_extract_hcl_complete_parse_failure(tmp_path):
    """Unparseable file returns valid result shape with error and diagnostic."""
    bad_file = tmp_path / "bad.tf"
    bad_file.write_bytes(b'\x00\x01\x02\x03')  # binary garbage
    result = extract_hcl(bad_file, tmp_path)
    # Must still return valid shape
    assert "nodes" in result
    assert "edges" in result
    assert "diagnostics" in result
    # File node should exist
    assert len(result["nodes"]) >= 1


def test_extract_hcl_partial_parse(tmp_path):
    """File with ERROR nodes emits hcl_partial_parse and still returns valid shape."""
    mixed = tmp_path / "mixed.tf"
    # A block followed by a malformed attribute — tree-sitter recovers the block
    mixed.write_text('resource "aws_vpc" "main" {\n  cidr = "10.0.0.0/16"\n}\n\nthis is not valid hcl at all\n')
    result = extract_hcl(mixed, tmp_path)
    # Must always return valid result shape
    assert "nodes" in result and "diagnostics" in result
    # File node always present
    assert len(result["nodes"]) >= 1
    # Should emit partial parse warning if ERROR nodes detected
    partial_diags = [d for d in result["diagnostics"] if d["code"] == "hcl_partial_parse"]
    assert len(partial_diags) >= 1


def test_extract_hcl_file_too_large(tmp_path):
    """File exceeding size limit returns diagnostic without parsing."""
    big_file = tmp_path / "huge.tf"
    big_file.write_bytes(b'x' * (_HCL_MAX_FILE_BYTES + 1))
    result = extract_hcl(big_file, tmp_path)
    assert result["error"] is not None
    assert "too large" in result["error"]
    diags = [d for d in result["diagnostics"] if d["code"] == "hcl_resource_limit_exceeded"]
    assert len(diags) == 1


def test_extract_hcl_missing_file(tmp_path):
    """Non-existent file returns error result."""
    result = extract_hcl(tmp_path / "nonexistent.tf", tmp_path)
    assert result["error"] is not None


def test_extract_hcl_error_result_shape(tmp_path):
    """Error results still have all required keys."""
    big_file = tmp_path / "huge.tf"
    big_file.write_bytes(b'x' * (_HCL_MAX_FILE_BYTES + 1))
    result = extract_hcl(big_file, tmp_path)
    assert set(result.keys()) == {
        "nodes", "edges", "raw_calls", "diagnostics",
        "hcl_deferred_refs", "input_tokens", "output_tokens", "error",
    }


# --- Pipeline dispatch and discovery tests ---

def test_collect_files_includes_tf():
    """collect_files() discovers .tf and .tfvars files."""
    files = collect_files(FIXTURES)
    tf_files = [f for f in files if f.suffix in (".tf", ".tfvars")]
    assert len(tf_files) >= 2  # sample.tf + sample.tfvars + sample_modules.tf


def test_extract_dispatches_tf():
    """extract() processes .tf files through the HCL extractor."""
    tf_files = [FIXTURES / "sample.tf"]
    result = extract(tf_files)
    labels = [n["label"] for n in result["nodes"]]
    assert any("resource:" in l for l in labels)


def test_extract_dispatches_tfvars():
    """extract() processes .tfvars files."""
    result = extract([FIXTURES / "sample.tfvars"])
    assert len(result["nodes"]) >= 1


def test_detect_classifies_tf_as_code():
    from graphify.detect import classify_file, FileType
    assert classify_file(Path("main.tf")) == FileType.CODE
    assert classify_file(Path("terraform.tfvars")) == FileType.CODE
