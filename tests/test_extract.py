from pathlib import Path
from graphify.extract import extract_python, extract, collect_files, _make_id

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


def test_collect_files_from_dir():
    files = collect_files(FIXTURES)
    supported = {".py", ".js", ".ts", ".tsx", ".go", ".rs",
                 ".java", ".c", ".cpp", ".cc", ".cxx", ".rb",
                 ".cs", ".kt", ".kts", ".scala", ".php", ".h", ".hpp",
                 ".swift", ".lua", ".toc", ".zig", ".ps1", ".ex", ".exs",
                 ".m", ".mm"}
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
