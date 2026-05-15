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


def test_collect_files_from_dir():
    files = collect_files(FIXTURES)
    supported = {".py", ".js", ".ts", ".tsx", ".go", ".rs",
                 ".java", ".c", ".cpp", ".cc", ".cxx", ".rb",
                 ".cs", ".kt", ".kts", ".scala", ".php", ".h", ".hpp"}
    assert all(f.suffix in supported for f in files)
    assert len(files) > 0


def test_collect_files_skips_hidden():
    files = collect_files(FIXTURES)
    for f in files:
        assert not any(part.startswith(".") for part in f.parts)


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


def test_calls_edges_are_inferred():
    result = extract_python(FIXTURES / "sample_calls.py")
    for edge in result["edges"]:
        if edge["relation"] == "calls":
            assert edge["confidence"] == "INFERRED"
            assert edge["weight"] == 0.8


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


# ---------------------------------------------------------------------------
# source_file contract: stub nodes for cross-corpus symbols
# ---------------------------------------------------------------------------

def test_external_base_emits_sentinel_source_file():
    """
    When a class inherits from a symbol not defined in the parsed corpus
    (e.g. a framework base class), the extractor adds a stub node so the
    `inherits` edge survives. That stub MUST carry source_file="<external>"
    rather than an empty string or None, so downstream validators can
    distinguish "outside the corpus" from "extraction bug".
    """
    result = extract_python(FIXTURES / "sample_external_base.py")
    stubs = [n for n in result["nodes"] if n["label"] == "ExternalBase"]
    assert len(stubs) == 1, f"Expected exactly one stub for ExternalBase, got {len(stubs)}"
    assert stubs[0]["source_file"] == "<external>", (
        f"External-symbol stub must use the '<external>' sentinel, "
        f"got {stubs[0]['source_file']!r}"
    )


def test_external_base_stub_is_never_empty_string():
    """Regression: no node may emit source_file as an empty string."""
    result = extract_python(FIXTURES / "sample_external_base.py")
    for n in result["nodes"]:
        assert n["source_file"] != "", f"Node {n['id']} has empty source_file"
        assert n["source_file"] is not None, f"Node {n['id']} has None source_file"


def test_inherits_edge_survives_for_external_base():
    """The whole point of the stub: the `inherits` edge must still be emitted."""
    result = extract_python(FIXTURES / "sample_external_base.py")
    inherits = [e for e in result["edges"] if e["relation"] == "inherits"]
    assert any(
        result_node["label"] == "ExternalBase" and result_node["id"] == edge["target"]
        for edge in inherits
        for result_node in result["nodes"]
    ), "Expected an inherits edge whose target is the ExternalBase stub"
