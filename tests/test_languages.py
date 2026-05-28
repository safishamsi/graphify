"""Tests for language extractors: Java, C, C++, Ruby, C#, Kotlin, Scala, PHP, Swift, Go, Julia, Fortran, JS/TS, .NET project files."""
from __future__ import annotations
from pathlib import Path
import pytest
from graphify.extract import (
    extract_java, extract_c, extract_cpp, extract_ruby,
    extract_csharp, extract_kotlin, extract_scala, extract_php,
    extract_swift, extract_go, extract_julia, extract_js, extract_fortran,
    extract_groovy, extract_sln, extract_csproj, extract_razor, extract_rescript,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _labels(r):
    return [n["label"] for n in r["nodes"]]

def _relations(r):
    return {e["relation"] for e in r["edges"]}

def _calls(r):
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == "calls"
    }


def _references(r):
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    return [
        (
            node_by_id.get(e["source"], e["source"]),
            node_by_id.get(e["target"], e["target"]),
            e,
        )
        for e in r["edges"] if e["relation"] == "references"
    ]


def _edges_with_relation(r, *relations):
    return [e for e in r["edges"] if e["relation"] in relations]


def _normalize_symbol_label(label: str) -> str:
    return label.strip("()").lstrip(".")


def _node_by_label(result: dict, label: str) -> dict:
    for node in result["nodes"]:
        if node.get("label") == label or _normalize_symbol_label(node.get("label", "")) == label:
            return node
    raise AssertionError(f"missing node label {label!r}")


def _edge_labels(result: dict, relation: str, context: str | None = None) -> set[tuple[str, str]]:
    labels = {node["id"]: _normalize_symbol_label(node["label"]) for node in result["nodes"]}
    pairs = set()
    for edge in result["edges"]:
        if edge.get("relation") != relation:
            continue
        if context is not None and edge.get("context") != context:
            continue
        pairs.add((labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"])))
    return pairs


# ── Java ──────────────────────────────────────────────────────────────────────

def test_java_no_error():
    r = extract_java(FIXTURES / "sample.java")
    assert "error" not in r

def test_java_finds_class():
    r = extract_java(FIXTURES / "sample.java")
    assert any("DataProcessor" in l for l in _labels(r))

def test_java_finds_interface():
    r = extract_java(FIXTURES / "sample.java")
    assert any("Processor" in l for l in _labels(r))

def test_java_finds_methods():
    r = extract_java(FIXTURES / "sample.java")
    labels = _labels(r)
    assert any("addItem" in l for l in labels)
    assert any("process" in l for l in labels)

def test_java_finds_imports():
    r = extract_java(FIXTURES / "sample.java")
    assert "imports" in _relations(r)


def test_java_import_edges_have_import_context():
    r = extract_java(FIXTURES / "sample.java")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)

def test_java_no_dangling_edges():
    r = extract_java(FIXTURES / "sample.java")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids


# ── C ────────────────────────────────────────────────────────────────────────

def test_c_no_error():
    r = extract_c(FIXTURES / "sample.c")
    assert "error" not in r

def test_c_finds_functions():
    r = extract_c(FIXTURES / "sample.c")
    labels = _labels(r)
    assert any("process" in l for l in labels)
    assert any("main" in l for l in labels)

def test_c_finds_includes():
    r = extract_c(FIXTURES / "sample.c")
    assert "imports" in _relations(r)

def test_c_emits_calls():
    r = extract_c(FIXTURES / "sample.c")
    assert any(e["relation"] == "calls" for e in r["edges"])

def test_c_calls_are_extracted():
    r = extract_c(FIXTURES / "sample.c")
    for e in r["edges"]:
        if e["relation"] == "calls":
            assert e["confidence"] == "EXTRACTED"


def test_c_import_edges_have_import_context():
    r = extract_c(FIXTURES / "sample.c")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_c_call_edges_have_call_context():
    r = extract_c(FIXTURES / "sample.c")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)


# ── C++ ───────────────────────────────────────────────────────────────────────

def test_cpp_no_error():
    r = extract_cpp(FIXTURES / "sample.cpp")
    assert "error" not in r

def test_cpp_finds_class():
    r = extract_cpp(FIXTURES / "sample.cpp")
    assert any("HttpClient" in l for l in _labels(r))

def test_cpp_finds_methods():
    r = extract_cpp(FIXTURES / "sample.cpp")
    labels = _labels(r)
    # C++ extractor captures the constructor and public-visible methods
    assert any("HttpClient" in l for l in labels)

def test_cpp_finds_includes():
    r = extract_cpp(FIXTURES / "sample.cpp")
    assert "imports" in _relations(r)


def test_cpp_import_edges_have_import_context():
    r = extract_cpp(FIXTURES / "sample.cpp")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_cpp_class_inherits_edge():
    """Regression for #915: `class Derived : public Base {}` should emit an inherits edge."""
    r = extract_cpp(FIXTURES / "sample.cpp")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    found = any(
        "AuthedHttpClient" in node_by_id.get(e["source"], "")
        and "HttpClient" in node_by_id.get(e["target"], "")
        for e in r["edges"] if e["relation"] == "inherits"
    )
    assert found, "AuthedHttpClient should have inherits edge to HttpClient"


def test_cpp_struct_inherits_edge():
    """Structs use the same `: Base` syntax as classes and must also emit inherits."""
    r = extract_cpp(FIXTURES / "sample.cpp")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    found = any(
        "RetryingHttpClient" in node_by_id.get(e["source"], "")
        and "HttpClient" in node_by_id.get(e["target"], "")
        for e in r["edges"] if e["relation"] == "inherits"
    )
    assert found, "RetryingHttpClient (struct) should have inherits edge to HttpClient"


# ── Ruby ─────────────────────────────────────────────────────────────────────

def test_ruby_no_error():
    r = extract_ruby(FIXTURES / "sample.rb")
    assert "error" not in r

def test_ruby_finds_class():
    r = extract_ruby(FIXTURES / "sample.rb")
    assert any("ApiClient" in l for l in _labels(r))

def test_ruby_finds_methods():
    r = extract_ruby(FIXTURES / "sample.rb")
    labels = _labels(r)
    assert any("get" in l for l in labels)
    assert any("post" in l for l in labels)

def test_ruby_finds_function():
    r = extract_ruby(FIXTURES / "sample.rb")
    assert any("parse_response" in l for l in _labels(r))


# ── C# ───────────────────────────────────────────────────────────────────────

def test_csharp_no_error():
    r = extract_csharp(FIXTURES / "sample.cs")
    assert "error" not in r

def test_csharp_finds_class():
    r = extract_csharp(FIXTURES / "sample.cs")
    assert any("DataProcessor" in l for l in _labels(r))

def test_csharp_finds_interface():
    r = extract_csharp(FIXTURES / "sample.cs")
    assert any("IProcessor" in l for l in _labels(r))

def test_csharp_finds_methods():
    r = extract_csharp(FIXTURES / "sample.cs")
    labels = _labels(r)
    assert any("Process" in l for l in labels)

def test_csharp_finds_usings():
    r = extract_csharp(FIXTURES / "sample.cs")
    assert "imports" in _relations(r)

def test_csharp_inherits_edge():
    r = extract_csharp(FIXTURES / "sample.cs")
    inherits = [e for e in r["edges"] if e["relation"] == "inherits"]
    assert len(inherits) >= 1

def test_csharp_implements_iprocessor():
    r = extract_csharp(FIXTURES / "sample.cs")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    found = any(
        "DataProcessor" in node_by_id.get(e["source"], "") and
        "IProcessor" in node_by_id.get(e["target"], "")
        for e in r["edges"] if e["relation"] == "implements"
    )
    assert found, "DataProcessor should have implements edge to IProcessor"


def test_csharp_splits_inherits_and_implements_edges():
    result = extract_csharp(FIXTURES / "sample.cs")
    assert ("DataProcessor", "Processor") in _edge_labels(result, "inherits")
    assert ("DataProcessor", "IProcessor") in _edge_labels(result, "implements")


def test_csharp_parameter_return_and_generic_contexts():
    result = extract_csharp(FIXTURES / "sample.cs")
    assert ("Build", "HttpClient") in _edge_labels(result, "references", "parameter_type")
    assert ("Build", "Result") in _edge_labels(result, "references", "return_type")
    assert ("Build", "DataProcessor") in _edge_labels(result, "references", "generic_arg")


def test_java_normalizes_inherits_and_implements():
    result = extract_java(FIXTURES / "sample.java")
    assert ("DataProcessor", "BaseProcessor") in _edge_labels(result, "inherits")
    assert ("DataProcessor", "Processor") in _edge_labels(result, "implements")


def test_java_parameter_return_generic_and_attribute_contexts():
    result = extract_java(FIXTURES / "sample.java")
    assert ("build", "HttpClient") in _edge_labels(result, "references", "parameter_type")
    assert ("build", "Result") in _edge_labels(result, "references", "return_type")
    assert ("build", "DataProcessor") in _edge_labels(result, "references", "generic_arg")
    assert ("build", "Override") in _edge_labels(result, "references", "attribute")


def test_csharp_field_type_references_have_field_context():
    r = extract_csharp(FIXTURES / "sample.cs")
    refs = _references(r)
    assert any(
        "DataProcessor" in src and "HttpClient" in tgt and edge.get("context") == "field"
        for src, tgt, edge in refs
    ), "DataProcessor field declarations should reference HttpClient with field context"


def test_csharp_call_edges_have_call_context():
    r = extract_csharp(FIXTURES / "sample.cs")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    assert any(
        "Process" in node_by_id.get(e["source"], "")
        and "Validate" in node_by_id.get(e["target"], "")
        and e.get("context") == "call"
        for e in r["edges"] if e["relation"] == "calls"
    ), "C# call edges should retain call context"


def test_csharp_import_edges_have_import_context():
    r = extract_csharp(FIXTURES / "sample.cs")
    import_edges = [e for e in r["edges"] if e["relation"] == "imports"]
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


# ── Kotlin ───────────────────────────────────────────────────────────────────

def test_kotlin_no_error():
    r = extract_kotlin(FIXTURES / "sample.kt")
    assert "error" not in r

def test_kotlin_finds_class():
    r = extract_kotlin(FIXTURES / "sample.kt")
    assert any("HttpClient" in l for l in _labels(r))

def test_kotlin_finds_data_class():
    r = extract_kotlin(FIXTURES / "sample.kt")
    assert any("Config" in l for l in _labels(r))

def test_kotlin_finds_methods():
    r = extract_kotlin(FIXTURES / "sample.kt")
    labels = _labels(r)
    assert any("get" in l for l in labels)
    assert any("post" in l for l in labels)

def test_kotlin_finds_function():
    r = extract_kotlin(FIXTURES / "sample.kt")
    assert any("createClient" in l for l in _labels(r))

def test_kotlin_emits_in_file_calls():
    """Regression test for the call-walker `simple_identifier` /
    `identifier` rename — see graphify-kmp's PythonParityTest."""
    r = extract_kotlin(FIXTURES / "sample.kt")
    calls = _calls(r)
    # In sample.kt: get() and post() both call buildRequest(), and
    # createClient() invokes Config and HttpClient (constructor calls).
    assert (".get()", ".buildRequest()") in calls
    assert (".post()", ".buildRequest()") in calls
    assert ("createClient()", "Config") in calls
    assert ("createClient()", "HttpClient") in calls


# ── Scala ─────────────────────────────────────────────────────────────────────

def test_scala_no_error():
    r = extract_scala(FIXTURES / "sample.scala")
    assert "error" not in r

def test_scala_finds_class():
    r = extract_scala(FIXTURES / "sample.scala")
    assert any("HttpClient" in l for l in _labels(r))

def test_scala_finds_object():
    r = extract_scala(FIXTURES / "sample.scala")
    assert any("HttpClientFactory" in l for l in _labels(r))

def test_scala_finds_methods():
    r = extract_scala(FIXTURES / "sample.scala")
    labels = _labels(r)
    assert any("get" in l for l in labels)
    assert any("post" in l for l in labels)


def test_scala_import_edges_have_import_context():
    r = extract_scala(FIXTURES / "sample.scala")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_scala_call_edges_have_call_context():
    r = extract_scala(FIXTURES / "sample.scala")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)


# ── PHP ───────────────────────────────────────────────────────────────────────

def test_php_no_error():
    r = extract_php(FIXTURES / "sample.php")
    assert "error" not in r

def test_php_finds_class():
    r = extract_php(FIXTURES / "sample.php")
    assert any("ApiClient" in l for l in _labels(r))

def test_php_finds_methods():
    r = extract_php(FIXTURES / "sample.php")
    labels = _labels(r)
    assert any("get" in l for l in labels)
    assert any("post" in l for l in labels)

def test_php_finds_function():
    r = extract_php(FIXTURES / "sample.php")
    assert any("parseResponse" in l for l in _labels(r))

def test_php_finds_imports():
    r = extract_php(FIXTURES / "sample.php")
    assert "imports" in _relations(r)


def test_php_import_edges_have_import_context():
    r = extract_php(FIXTURES / "sample.php")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_php_call_edges_have_call_context():
    r = extract_php(FIXTURES / "sample.php")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)

def test_php_finds_static_property_access():
    r = extract_php(FIXTURES / "sample_php_static_prop.php")
    assert "uses_static_prop" in _relations(r)

def test_php_static_prop_target_is_holding_class():
    r = extract_php(FIXTURES / "sample_php_static_prop.php")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    uses_prop = [
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == "uses_static_prop"
    ]
    assert any("DefaultPalette" in tgt for _, tgt in uses_prop)

def test_php_finds_config_helper_call():
    r = extract_php(FIXTURES / "sample_php_config.php")
    assert "uses_config" in _relations(r)

def test_php_config_helper_target_matches_first_segment():
    r = extract_php(FIXTURES / "sample_php_config.php")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    uses_cfg = [
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == "uses_config"
    ]
    assert any("Throttle" in tgt for _, tgt in uses_cfg)

def test_php_finds_container_bind():
    r = extract_php(FIXTURES / "sample_php_container.php")
    assert "bound_to" in _relations(r)

def test_php_container_bind_links_contract_to_implementation():
    r = extract_php(FIXTURES / "sample_php_container.php")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    bound = [
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == "bound_to"
    ]
    assert any("PaymentGateway" in src and "StripeGateway" in tgt for src, tgt in bound)

def test_php_finds_event_listeners():
    r = extract_php(FIXTURES / "sample_php_listen.php")
    assert "listened_by" in _relations(r)

def test_php_event_listener_links_event_to_listener():
    r = extract_php(FIXTURES / "sample_php_listen.php")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    listened = [
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == "listened_by"
    ]
    assert any("UserRegistered" in src and "SendWelcomeEmail" in tgt for src, tgt in listened)


# ── Swift ────────────────────────────────────────────────────────────────────

def test_swift_no_error():
    r = extract_swift(FIXTURES / "sample.swift")
    assert "error" not in r

def test_swift_finds_class():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("DataProcessor" in l for l in _labels(r))

def test_swift_finds_protocol():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("Processor" in l for l in _labels(r))

def test_swift_finds_struct():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("Config" in l for l in _labels(r))

def test_swift_finds_methods():
    r = extract_swift(FIXTURES / "sample.swift")
    labels = _labels(r)
    assert any("addItem" in l for l in labels)
    assert any("process" in l for l in labels)

def test_swift_finds_function():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("createProcessor" in l for l in _labels(r))

def test_swift_finds_imports():
    r = extract_swift(FIXTURES / "sample.swift")
    assert "imports" in _relations(r)


def test_swift_import_edges_have_import_context():
    r = extract_swift(FIXTURES / "sample.swift")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)

def test_swift_no_dangling_edges():
    r = extract_swift(FIXTURES / "sample.swift")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids

def test_swift_finds_actor():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("CacheManager" in l for l in _labels(r))

def test_swift_finds_enum():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("NetworkError" in l for l in _labels(r))

def test_swift_finds_enum_methods():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("describe" in l for l in _labels(r))

def test_swift_finds_enum_cases():
    r = extract_swift(FIXTURES / "sample.swift")
    labels = _labels(r)
    assert any("timeout" in l for l in labels)
    assert any("connectionFailed" in l for l in labels)

def test_swift_enum_cases_have_case_of_edge():
    r = extract_swift(FIXTURES / "sample.swift")
    case_edges = [e for e in r["edges"] if e["relation"] == "case_of"]
    assert len(case_edges) >= 2

def test_swift_finds_deinit():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("deinit" in l for l in _labels(r))

def test_swift_finds_subscript():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("subscript" in l for l in _labels(r))

def test_swift_extension_methods_attach_to_type():
    r = extract_swift(FIXTURES / "sample.swift")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    method_edges = [e for e in r["edges"] if e["relation"] == "method"]
    found = False
    for e in method_edges:
        src_label = node_by_id.get(e["source"], "")
        tgt_label = node_by_id.get(e["target"], "")
        if "Config" in src_label and "isValid" in tgt_label:
            found = True
            break
    assert found, "extension method isValid should attach to Config"

def test_swift_extension_does_not_duplicate_type_node():
    r = extract_swift(FIXTURES / "sample.swift")
    config_nodes = [n for n in r["nodes"] if n["label"] == "Config"]
    assert len(config_nodes) == 1, f"Config should appear once, got {len(config_nodes)}"

def test_swift_conformance_edge():
    r = extract_swift(FIXTURES / "sample.swift")
    inherits_edges = [e for e in r["edges"] if e["relation"] == "inherits"]
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    found = False
    for e in inherits_edges:
        src_label = node_by_id.get(e["source"], "")
        tgt_label = node_by_id.get(e["target"], "")
        if "DataProcessor" in src_label and "Processor" in tgt_label:
            found = True
            break
    assert found, "DataProcessor should have inherits edge to Processor"

def test_swift_extension_conformance_edge():
    r = extract_swift(FIXTURES / "sample.swift")
    inherits_edges = [e for e in r["edges"] if e["relation"] == "inherits"]
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    found = False
    for e in inherits_edges:
        src_label = node_by_id.get(e["source"], "")
        tgt_label = node_by_id.get(e["target"], "")
        if "DataProcessor" in src_label and "Loggable" in tgt_label:
            found = True
            break
    assert found, "extension should add conformance edge DataProcessor -> Loggable"

def test_swift_emits_calls():
    r = extract_swift(FIXTURES / "sample.swift")
    calls = _calls(r)
    assert any("process" in src and "validate" in tgt for src, tgt in calls)

def test_swift_call_edges_have_call_context():
    r = extract_swift(FIXTURES / "sample.swift")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)


def test_swift_extension_across_files_merges_into_canonical_type():
    """`extension Foo` in a separate file from `class Foo` must resolve to a
    single Foo node. tree-sitter-swift parses both as `class_declaration` and
    node ids carry the file stem, so without a corpus-level merge each file
    would emit its own Foo."""
    from graphify.extract import extract
    paths = sorted((FIXTURES / "swift_cross_file").glob("*.swift"))
    r = extract(paths, cache_root=Path("/tmp/graphify-test-no-cache"))
    foo_nodes = [n for n in r["nodes"] if n["label"] == "Foo"]
    assert len(foo_nodes) == 1, f"Foo should appear once, got {len(foo_nodes)}: {[n['id'] for n in foo_nodes]}"
    foo_id = foo_nodes[0]["id"]
    method_targets = {
        e["target"] for e in r["edges"]
        if e["relation"] == "method" and e["source"] == foo_id
    }
    method_labels = {n["label"] for n in r["nodes"] if n["id"] in method_targets}
    assert any("one" in l for l in method_labels), f"one() should attach to Foo, got {method_labels}"
    assert any("two" in l for l in method_labels), f"extension method two() should attach to Foo, got {method_labels}"


# ── Elixir ────────────────────────────────────────────────────────────────────

from graphify.extract import extract_elixir

def test_elixir_finds_module():
    r = extract_elixir(FIXTURES / "sample.ex")
    assert "error" not in r
    labels = [n["label"] for n in r["nodes"]]
    assert any("MyApp.Accounts.User" in l for l in labels)

def test_elixir_finds_functions():
    r = extract_elixir(FIXTURES / "sample.ex")
    labels = [n["label"] for n in r["nodes"]]
    assert any("create" in l for l in labels)
    assert any("find" in l for l in labels)
    assert any("validate" in l for l in labels)

def test_elixir_finds_imports():
    r = extract_elixir(FIXTURES / "sample.ex")
    import_edges = [e for e in r["edges"] if e["relation"] == "imports"]
    assert len(import_edges) >= 2


def test_elixir_import_edges_have_import_context():
    r = extract_elixir(FIXTURES / "sample.ex")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)

def test_elixir_finds_calls():
    r = extract_elixir(FIXTURES / "sample.ex")
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    labels = {n["id"]: n["label"] for n in r["nodes"]}
    assert any("create" in labels.get(src, "") and "validate" in labels.get(tgt, "") for src, tgt in calls)


def test_elixir_call_edges_have_call_context():
    r = extract_elixir(FIXTURES / "sample.ex")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)

def test_elixir_method_edges():
    r = extract_elixir(FIXTURES / "sample.ex")
    methods = [e for e in r["edges"] if e["relation"] == "method"]
    assert len(methods) >= 3


# ── Objective-C ──────────────────────────────────────────────────────────────
from graphify.extract import extract_objc


def test_objc_finds_interface():
    r = extract_objc(FIXTURES / "sample.m")
    labels = [n["label"] for n in r["nodes"]]
    assert "Animal" in labels


def test_objc_finds_subclass():
    r = extract_objc(FIXTURES / "sample.m")
    labels = [n["label"] for n in r["nodes"]]
    assert "Dog" in labels


def test_objc_finds_methods():
    r = extract_objc(FIXTURES / "sample.m")
    labels = [n["label"] for n in r["nodes"]]
    assert any("speak" in l or "fetch" in l or "initWithName" in l for l in labels)


def test_objc_finds_imports():
    r = extract_objc(FIXTURES / "sample.m")
    import_edges = [e for e in r["edges"] if e["relation"] == "imports"]
    assert len(import_edges) >= 1


def test_objc_import_edges_have_import_context():
    r = extract_objc(FIXTURES / "sample.m")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_objc_inherits_edge():
    r = extract_objc(FIXTURES / "sample.m")
    inherits = [e for e in r["edges"] if e["relation"] == "inherits"]
    assert len(inherits) >= 1


def test_objc_no_dangling_edges():
    r = extract_objc(FIXTURES / "sample.m")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------

def test_go_receiver_methods_share_type_node():
    """Methods on the same receiver type must share one canonical type node."""
    r = extract_go(FIXTURES / "sample.go")
    server_nodes = [n for n in r["nodes"] if n["label"] == "Server"]
    # Both Start() and Stop() are on *Server — should produce exactly one Server node
    assert len(server_nodes) == 1

def test_go_receiver_uses_pkg_scope():
    """Type node id should be scoped to directory, not file stem."""
    r = extract_go(FIXTURES / "sample.go")
    server_nodes = [n for n in r["nodes"] if n["label"] == "Server"]
    assert server_nodes
    # Should NOT contain the file stem "sample" in the type node id
    assert "sample" not in server_nodes[0]["id"].split(":")[0]


# ---------------------------------------------------------------------------
# Julia
# ---------------------------------------------------------------------------

def test_julia_finds_module():
    r = extract_julia(FIXTURES / "sample.jl")
    labels = [n["label"] for n in r["nodes"]]
    assert "Geometry" in labels


def test_julia_finds_structs():
    r = extract_julia(FIXTURES / "sample.jl")
    labels = [n["label"] for n in r["nodes"]]
    assert "Point" in labels
    assert "Circle" in labels


def test_julia_finds_abstract_type():
    r = extract_julia(FIXTURES / "sample.jl")
    labels = [n["label"] for n in r["nodes"]]
    assert "Shape" in labels


def test_julia_finds_functions():
    r = extract_julia(FIXTURES / "sample.jl")
    labels = [n["label"] for n in r["nodes"]]
    assert any("area" in l for l in labels)
    assert any("distance" in l for l in labels)


def test_julia_finds_short_function():
    r = extract_julia(FIXTURES / "sample.jl")
    labels = [n["label"] for n in r["nodes"]]
    assert any("perimeter" in l for l in labels)


def test_julia_finds_imports():
    r = extract_julia(FIXTURES / "sample.jl")
    import_edges = [e for e in r["edges"] if e["relation"] == "imports"]
    assert len(import_edges) >= 1


def test_julia_import_edges_have_import_context():
    r = extract_julia(FIXTURES / "sample.jl")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_julia_finds_inherits():
    r = extract_julia(FIXTURES / "sample.jl")
    inherits = [e for e in r["edges"] if e["relation"] == "inherits"]
    assert len(inherits) >= 1


def test_julia_finds_calls():
    r = extract_julia(FIXTURES / "sample.jl")
    call_edges = [e for e in r["edges"] if e["relation"] == "calls"]
    assert len(call_edges) >= 1


def test_julia_call_edges_have_call_context():
    r = extract_julia(FIXTURES / "sample.jl")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)


def test_julia_no_dangling_edges():
    r = extract_julia(FIXTURES / "sample.jl")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"


# ── Fortran extractor ────────────────────────────────────────────────────────

def test_fortran_finds_module():
    r = extract_fortran(FIXTURES / "sample.f90")
    assert "error" not in r
    labels = [n["label"] for n in r["nodes"]]
    assert "geometry" in labels


def test_fortran_finds_subroutines():
    r = extract_fortran(FIXTURES / "sample.f90")
    labels = [n["label"] for n in r["nodes"]]
    assert any("circle_area" in l for l in labels)
    assert any("print_area" in l for l in labels)


def test_fortran_finds_function():
    r = extract_fortran(FIXTURES / "sample.f90")
    labels = [n["label"] for n in r["nodes"]]
    assert any("distance" in l for l in labels)


def test_fortran_finds_program():
    r = extract_fortran(FIXTURES / "sample.f90")
    labels = [n["label"] for n in r["nodes"]]
    assert "main" in labels


def test_fortran_finds_use_imports():
    r = extract_fortran(FIXTURES / "sample.f90")
    import_edges = [e for e in r["edges"] if e["relation"] == "imports"]
    assert len(import_edges) >= 2


def test_fortran_use_edges_have_use_context():
    r = extract_fortran(FIXTURES / "sample.f90")
    import_edges = [e for e in r["edges"] if e["relation"] == "imports"]
    assert all(e.get("context") == "use" for e in import_edges)


def test_fortran_finds_calls():
    r = extract_fortran(FIXTURES / "sample.f90")
    call_edges = [e for e in r["edges"] if e["relation"] == "calls"]
    assert len(call_edges) >= 1


def test_fortran_case_insensitive_names():
    r = extract_fortran(FIXTURES / "sample.f90")
    labels = [n["label"] for n in r["nodes"]]
    assert all(l == l.lower() or "(" in l for l in labels if l.endswith(("()", "")) and not "." in l)
    assert "geometry" in labels
    assert "main" in labels


def test_fortran_no_dangling_edges():
    r = extract_fortran(FIXTURES / "sample.f90")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"


def test_fortran_capital_F_parses_preprocessed():
    r = extract_fortran(FIXTURES / "sample_preprocessed.F90")
    assert "error" not in r
    labels = [n["label"] for n in r["nodes"]]
    assert "shapes" in labels
    assert any("compute_volume" in l for l in labels)


# ── TypeScript dynamic imports ───────────────────────────────────────────────

def test_ts_dynamic_import_no_error():
    r = extract_js(FIXTURES / "dynamic_import.ts")
    assert "error" not in r

def test_ts_dynamic_import_extracts_edges():
    """Dynamic import() calls inside functions should produce imports_from edges."""
    r = extract_js(FIXTURES / "dynamic_import.ts")
    dyn_edges = [e for e in r["edges"] if e["relation"] == "imports_from"]
    targets = {e["target"] for e in dyn_edges}
    # Should find: static ./logger, dynamic ./mayaEngine.js, dynamic ./queue.js
    assert any("logger" in t for t in targets), f"Missing static import of logger: {targets}"
    assert any("mayaengine" in t.lower() for t in targets), f"Missing dynamic import of mayaEngine: {targets}"
    assert any("queue" in t.lower() for t in targets), f"Missing dynamic import of queue: {targets}"

def test_ts_dynamic_import_confidence():
    """Dynamic imports should have EXTRACTED confidence (they are deterministic string literals)."""
    r = extract_js(FIXTURES / "dynamic_import.ts")
    dyn_edges = [e for e in r["edges"]
                 if e["relation"] == "imports_from"
                 and "mayaengine" in e["target"].lower()]
    assert len(dyn_edges) >= 1
    assert dyn_edges[0]["confidence"] == "EXTRACTED"

def test_ts_dynamic_import_source_is_function():
    """Dynamic import edge source should be the enclosing function, not the file."""
    r = extract_js(FIXTURES / "dynamic_import.ts")
    node_labels = {n["id"]: n["label"] for n in r["nodes"]}
    dyn_edges = [e for e in r["edges"]
                 if e["relation"] == "imports_from"
                 and "mayaengine" in e["target"].lower()]
    assert len(dyn_edges) >= 1
    src_label = node_labels.get(dyn_edges[0]["source"], "")
    assert "processInbound" in src_label, f"Expected processInbound as source, got {src_label}"

def test_ts_no_dynamic_import_in_sync_fn():
    """Functions without dynamic imports should not get spurious imports_from edges."""
    r = extract_js(FIXTURES / "dynamic_import.ts")
    node_ids = {n["label"]: n["id"] for n in r["nodes"]}
    sync_nid = node_ids.get("syncOnly()")
    if sync_nid:
        sync_imports = [e for e in r["edges"]
                        if e["source"] == sync_nid and e["relation"] == "imports_from"]
        assert len(sync_imports) == 0

def test_ts_dynamic_template_literal_skipped():
    """Dynamic template literals (with ${}) must not produce an imports_from edge."""
    r = extract_js(FIXTURES / "dynamic_import.ts")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports_from"}
    # loadHandler uses `./handlers/${handlerName}` — no static path, must be absent
    assert not any("handler" in t.lower() and "$" in t for t in targets), \
        f"Garbage edge from dynamic template literal found: {targets}"
    # More robust: no target should contain a brace character
    assert not any("{" in t or "}" in t for t in targets), \
        f"Target contains unresolved template expression: {targets}"

def test_ts_static_template_literal_resolved():
    """Static template literals (no ${}) should resolve the same as a plain string."""
    r = extract_js(FIXTURES / "dynamic_import.ts")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports_from"}
    assert any("statichelper" in t.lower() for t in targets), \
        f"Static template literal import not resolved: {targets}"


# ── Markdown ─────────────────────────────────────────────────────────────────

from graphify.extract import extract_markdown

def test_markdown_no_error():
    r = extract_markdown(FIXTURES / "deploy_guide.md")
    assert "error" not in r

def test_markdown_finds_headings():
    r = extract_markdown(FIXTURES / "deploy_guide.md")
    labels = _labels(r)
    assert any("Deploy Guide" in l for l in labels)
    assert any("Prerequisites" in l for l in labels)
    assert any("Full Deploy" in l for l in labels)
    assert any("Rollback" in l for l in labels)

def test_markdown_finds_nested_heading():
    """### Database Migration is nested under ## Full Deploy."""
    r = extract_markdown(FIXTURES / "deploy_guide.md")
    labels = _labels(r)
    assert any("Database Migration" in l for l in labels)

def test_markdown_finds_code_blocks():
    r = extract_markdown(FIXTURES / "deploy_guide.md")
    labels = _labels(r)
    assert any("code:bash" in l for l in labels)
    assert any("code:sql" in l for l in labels)
    assert any("code:python" in l for l in labels)

def test_markdown_contains_edges():
    """Headings and code blocks should be connected via 'contains' edges."""
    r = extract_markdown(FIXTURES / "deploy_guide.md")
    assert "contains" in _relations(r)
    contains_edges = [e for e in r["edges"] if e["relation"] == "contains"]
    assert len(contains_edges) >= 5  # file->h1, h1->h2s, h2->h3, h2->codeblocks

def test_markdown_no_dangling_edges():
    r = extract_markdown(FIXTURES / "deploy_guide.md")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"


# ── Groovy ───────────────────────────────────────────────────────────────────


def test_groovy_no_error():
    r = extract_groovy(FIXTURES / "sample.groovy")
    assert "error" not in r


def test_groovy_finds_class():
    r = extract_groovy(FIXTURES / "sample.groovy")
    assert any("SampleService" in l for l in _labels(r))


def test_groovy_finds_methods():
    r = extract_groovy(FIXTURES / "sample.groovy")
    labels = _labels(r)
    assert any("process" in l for l in labels)
    assert any("reset" in l for l in labels)


def test_groovy_finds_imports():
    r = extract_groovy(FIXTURES / "sample.groovy")
    assert "imports" in _relations(r)


def test_groovy_import_edges_have_import_context():
    r = extract_groovy(FIXTURES / "sample.groovy")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_groovy_no_dangling_edges():
    r = extract_groovy(FIXTURES / "sample.groovy")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids


def test_groovy_spock_finds_class():
    r = extract_groovy(FIXTURES / "sample_spock.groovy")
    assert any("SampleSpec" in l for l in _labels(r))


def test_groovy_spock_finds_feature_methods():
    r = extract_groovy(FIXTURES / "sample_spock.groovy")
    feature_labels = [l for l in _labels(r) if l.startswith('"')]
    assert len(feature_labels) >= 2


def test_groovy_spock_finds_method_with_apostrophe():
    r = extract_groovy(FIXTURES / "sample_spock.groovy")
    assert any("it's" in l for l in _labels(r))


def test_groovy_spock_preserves_import_edges():
    r = extract_groovy(FIXTURES / "sample_spock.groovy")
    assert "imports" in _relations(r)


def test_groovy_spock_no_dangling_edges():
    r = extract_groovy(FIXTURES / "sample_spock.groovy")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids


# -- .NET project files (.sln, .csproj, .razor) -------------------------------

def test_sln_no_error():
    r = extract_sln(FIXTURES / "sample.sln")
    assert "error" not in r

def test_sln_finds_projects():
    r = extract_sln(FIXTURES / "sample.sln")
    labels = _labels(r)
    assert any("WebApi" in l for l in labels)
    assert any("Domain" in l for l in labels)

def test_sln_contains_edges():
    r = extract_sln(FIXTURES / "sample.sln")
    assert "contains" in _relations(r)

def test_sln_project_dependency_edges():
    r = extract_sln(FIXTURES / "sample.sln")
    assert "imports" in _relations(r)

def test_csproj_no_error():
    r = extract_csproj(FIXTURES / "sample.csproj")
    assert "error" not in r

def test_csproj_finds_packages():
    r = extract_csproj(FIXTURES / "sample.csproj")
    labels = _labels(r)
    assert any("MediatR" in l for l in labels)
    assert any("FluentValidation" in l for l in labels)

def test_csproj_finds_project_references():
    r = extract_csproj(FIXTURES / "sample.csproj")
    labels = _labels(r)
    assert any("Domain.csproj" in l for l in labels)

def test_csproj_finds_target_framework():
    r = extract_csproj(FIXTURES / "sample.csproj")
    assert any("net8.0" in l for l in _labels(r))

def test_csproj_finds_sdk():
    r = extract_csproj(FIXTURES / "sample.csproj")
    assert any("Microsoft.NET.Sdk.Web" in l for l in _labels(r))

def test_razor_no_error():
    r = extract_razor(FIXTURES / "sample.razor")
    assert "error" not in r

def test_razor_finds_using_directives():
    r = extract_razor(FIXTURES / "sample.razor")
    assert "imports" in _relations(r)

def test_razor_finds_component_references():
    r = extract_razor(FIXTURES / "sample.razor")
    assert "calls" in _relations(r)

def test_razor_finds_inherits():
    r = extract_razor(FIXTURES / "sample.razor")
    assert "inherits" in _relations(r)

def test_razor_finds_code_block_methods():
    r = extract_razor(FIXTURES / "sample.razor")
    labels = _labels(r)
    assert any("IncrementCount" in l for l in labels)
    assert any("LoadData" in l for l in labels)

def test_razor_no_dangling_edges():
    r = extract_razor(FIXTURES / "sample.razor")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids

# ── ReScript ─────────────────────────────────────────────────────────────────


def test_rescript_no_error():
    r = _extract_rescript_or_skip(FIXTURES / "sample.res")
    assert "error" not in r


def test_rescript_finds_type():
    """Polyvariant, variant, alias, and record types all emit Type nodes."""
    r = _extract_rescript_or_skip(FIXTURES / "sample.res")
    labels = _labels(r)
    assert "theme" in labels       # polyvariant
    assert "direction" in labels   # variant
    assert "label" in labels       # alias
    assert "entry" in labels       # record


def test_rescript_finds_value_let():
    """Plain value lets are bare labels (no parens). Covers number, array,
    record, tuple-destructure, record-destructure, and annotated value lets."""
    r = _extract_rescript_or_skip(FIXTURES / "sample.res")
    labels = _labels(r)
    assert "allThemes" in labels      # array literal
    assert "origin" in labels         # record literal
    assert "width" in labels          # tuple destructure
    assert "height" in labels         # tuple destructure
    assert "name" in labels           # record destructure
    assert "position" in labels       # record destructure
    assert "defaultEntry" in labels   # type-annotated value


def test_rescript_finds_function_let():
    """Function lets carry the `name()` label shape. Covers simple, typed,
    intra-file-call-bearing, qualified-call-bearing, and pipe-bearing fns."""
    r = _extract_rescript_or_skip(FIXTURES / "sample.res")
    labels = _labels(r)
    assert "identity()" in labels
    assert "move()" in labels          # typed params + return
    assert "pair()" in labels          # intra-file call
    assert "firstTheme()" in labels    # qualified call
    assert "counts()" in labels        # pipe expression


def test_rescript_finds_externals():
    """`external f: T => U = "js"` → Function node `f()`; `external v: T = "js"`
    → Variable node `v` (callable discrimination on annotation type)."""
    r = _extract_rescript_or_skip(FIXTURES / "sample.res")
    labels = _labels(r)
    assert "alert()" in labels   # function_type annotation
    assert "pi" in labels        # plain type annotation
    assert "pi()" not in labels


def test_rescript_finds_module():
    r = _extract_rescript_or_skip(FIXTURES / "sample.res")
    assert "Internal" in _labels(r)


def test_rescript_finds_module_members():
    """Members of `module Internal` attach to Internal with the right
    label shapes: types and value lets are bare, function lets are
    `.name()` (method shape)."""
    r = _extract_rescript_or_skip(FIXTURES / "sample.res")
    labels = _labels(r)
    assert "cached" in labels           # nested type
    assert "defaultCache" in labels     # nested value
    assert ".parse()" in labels         # nested function


def test_rescript_intra_file_call_edge():
    """`let pair = (a, b) => identity(b)` produces a `calls` edge from
    `pair()` to the local `identity()` function."""
    r = _extract_rescript_or_skip(FIXTURES / "sample.res")
    calls = _calls(r)
    assert ("pair()", "identity()") in calls


def test_rescript_call_edges_have_call_context():
    r = _extract_rescript_or_skip(FIXTURES / "sample.res")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)


def test_rescript_call_edges_have_extracted_confidence():
    """Intra-file calls (caller and callee both in this file) are
    EXTRACTED, not INFERRED. INFERRED is reserved for cross-file
    resolution in the multi-file `extract()` pass."""
    r = _extract_rescript_or_skip(FIXTURES / "sample.res")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("confidence") == "EXTRACTED" for e in call_edges), \
        f"single-file call edges should be EXTRACTED, got: {[e.get('confidence') for e in call_edges]}"


def test_rescript_sample_no_bare_type_references():
    """`int`, `string`, `float`, `unit` in the fixture annotations are
    bare `type_identifier`s, not `type_identifier_path`s, so they emit
    no `references_type` edges. The only references_type targets should
    be qualified module paths."""
    r = _extract_rescript_or_skip(FIXTURES / "sample.res")
    type_ref_targets = {
        e["target"] for e in r["edges"]
        if e["relation"] == "references_type"
    }
    for bare in ("int", "string", "float", "unit", "bool"):
        assert bare not in type_ref_targets, \
            f"bare local type {bare!r} should not emit references_type edge"


def test_rescript_sample_references_type_multiplicity():
    """`let move = (a: Animal.point, ...): Animal.point => ...` references
    `Animal.point` twice — once in the parameter annotation, once in the
    return type annotation. The extractor preserves both emissions
    (downstream build-step dedup is a separate concern)."""
    r = _extract_rescript_or_skip(FIXTURES / "sample.res")
    nb = {n["id"]: n["label"] for n in r["nodes"]}
    move_to_point = [
        e for e in r["edges"]
        if e["relation"] == "references_type"
        and nb.get(e["source"]) == "move()"
        and e["target"] == "animal_point"
    ]
    assert len(move_to_point) == 2, (
        f"expected 2 move()→animal_point references_type edges, "
        f"got {len(move_to_point)}"
    )


def test_rescript_sample_node_labels_complete():
    """Snapshot test — asserts the EXACT set of node labels emitted by
    the canonical fixture. A drift (extractor adds or drops a node) will
    surface here as a test failure, forcing an explicit review of the
    behaviour change. Pair with `test_rescript_sample_edge_summary_complete`."""
    r = _extract_rescript_or_skip(FIXTURES / "sample.res")
    actual = {n["label"] for n in r["nodes"]}
    expected = {
        "sample.res",
        # Type nodes
        "theme", "direction", "label", "entry",
        # Externals
        "alert()", "pi",
        # Value lets (incl. destructure outputs and annotated value)
        "allThemes", "origin", "width", "height", "name", "position", "defaultEntry",
        # Function lets
        "identity()", "move()", "pair()", "firstTheme()", "counts()",
        # Module + its members
        "Internal", "cached", "defaultCache", ".parse()",
    }
    assert actual == expected, (
        f"node-label drift on sample.res\n"
        f"  missing: {sorted(expected - actual)}\n"
        f"  extra:   {sorted(actual - expected)}"
    )


def test_rescript_sample_edge_summary_complete():
    """Snapshot test — asserts the EXACT set of
    (relation, source_label, target_label_or_phantom_id) edge triples
    produced by the canonical fixture. Duplicate emissions (e.g. param
    and return type both naming `Animal.point` on `move()`) collapse
    here; the multiplicity is checked by
    `test_rescript_sample_references_type_multiplicity`."""
    r = _extract_rescript_or_skip(FIXTURES / "sample.res")
    nb = {n["id"]: n["label"] for n in r["nodes"]}
    actual = {
        (e["relation"], nb.get(e["source"], e["source"]),
         nb.get(e["target"], e["target"]))
        for e in r["edges"]
    }
    expected = {
        # file → child (`contains`)
        ("contains", "sample.res", "theme"),
        ("contains", "sample.res", "direction"),
        ("contains", "sample.res", "label"),
        ("contains", "sample.res", "entry"),
        ("contains", "sample.res", "alert()"),
        ("contains", "sample.res", "pi"),
        ("contains", "sample.res", "allThemes"),
        ("contains", "sample.res", "origin"),
        ("contains", "sample.res", "width"),
        ("contains", "sample.res", "height"),
        ("contains", "sample.res", "name"),
        ("contains", "sample.res", "position"),
        ("contains", "sample.res", "defaultEntry"),
        ("contains", "sample.res", "identity()"),
        ("contains", "sample.res", "move()"),
        ("contains", "sample.res", "pair()"),
        ("contains", "sample.res", "firstTheme()"),
        ("contains", "sample.res", "counts()"),
        ("contains", "sample.res", "Internal"),
        # module → member
        ("contains", "Internal", "cached"),
        ("contains", "Internal", "defaultCache"),
        ("method", "Internal", ".parse()"),
        # intra-file call
        ("calls", "pair()", "identity()"),
        # `references_type` edges keep phantom targets for cross-module
        # types; the multi-file resolver rewrites them in `extract()`
        # when both endpoints are in scan (see
        # `test_rescript_cross_file_type_ref_resolves_to_real_node`).
        ("references_type", "entry", "animal_point"),
        ("references_type", "defaultEntry", "animal_point"),
        ("references_type", "move()", "animal_point"),
        ("references_type", "cached", "animal_species"),
    }
    assert actual == expected, (
        f"edge drift on sample.res\n"
        f"  missing: {sorted(expected - actual)}\n"
        f"  extra:   {sorted(actual - expected)}"
    )


def test_rescript_open_emits_import_edge(tmp_path):
    """`open Foo` in one file produces an `imports` edge from the caller
    file to the `Foo` module. Cross-file scenario tested via `tmp_path`
    (matches the test_cross_file_call_* convention in test_extract.py)."""
    _rescript_skip_if_unavailable()
    lib = tmp_path / "lib.res"
    lib.write_text("let helper = (x) => x + 1\n")
    caller = tmp_path / "caller.res"
    caller.write_text("open Lib\nlet wrap = (x) => helper(x)\n")
    r = extract_rescript(caller)
    import_edges = _edges_with_relation(r, "imports")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)
    # Target id is _make_id("Lib") = "lib" before the multi-file resolver
    # rewrites it to the real file id; this single-file extract sees the
    # unresolved form.
    assert any(e["target"].lower() == "lib" for e in import_edges)


def test_rescript_caller_finds_local_functions(tmp_path):
    """A caller file with its own let-functions emits those as nodes
    regardless of whether the imported module is in scope."""
    _rescript_skip_if_unavailable()
    caller = tmp_path / "caller.res"
    caller.write_text(
        "open Lib\n"
        "let darkModeOn = (config) => isEnabled(config, #DarkMode)\n"
        "let betaForUser = (user) => isEnabledForUser(user, #BetaCheckout)\n"
    )
    r = extract_rescript(caller)
    labels = _labels(r)
    assert "darkModeOn()" in labels
    assert "betaForUser()" in labels


def test_rescript_no_dangling_source_edges():
    """Every edge's `source` must be a real node id. Targets are allowed
    to be phantom (unresolved) for relations that survive the per-file
    cleanup with the expectation that the multi-file resolver will
    rewrite them later: `imports`, `imports_from`, `re_exports`, and
    `references_type`."""
    r = _extract_rescript_or_skip(FIXTURES / "sample.res")
    node_ids = {n["id"] for n in r["nodes"]}
    phantom_target_allowed = {
        "imports", "imports_from", "re_exports", "references_type",
    }
    for e in r["edges"]:
        assert e["source"] in node_ids
        if e["relation"] not in phantom_target_allowed:
            assert e["target"] in node_ids, (
                f"non-phantom-allowed relation has unresolved target: {e}"
            )


# ReScript extraction is opt-in via the `[rescript]` extra (no PyPI release
# of `tree-sitter-rescript`; the extra installs it from upstream's git).
# When the extra isn't installed, skip the per-language tests — same
# pattern as `_extract_sql_or_skip` in test_multilang.py.
def _rescript_skip_if_unavailable():
    pytest.importorskip("tree_sitter_rescript")


def _extract_rescript_or_skip(path):
    _rescript_skip_if_unavailable()
    return extract_rescript(path)


# Helper: write a small .res snippet to a tmp file, extract, return result.
def _extract_rescript_snippet(tmp_path, src):
    _rescript_skip_if_unavailable()
    p = tmp_path / "Sample.res"
    p.write_text(src)
    return extract_rescript(p)


def test_rescript_external_callable_emits_function_node(tmp_path):
    r = _extract_rescript_snippet(tmp_path,
        'external alert: string => unit = "alert"\n')
    assert "alert()" in _labels(r), \
        "external with function-type annotation should emit a function node"


def test_rescript_external_value_emits_variable_node(tmp_path):
    r = _extract_rescript_snippet(tmp_path,
        'external pi: float = "Math.PI"\n')
    labels = _labels(r)
    assert "pi" in labels, \
        "external with non-function type should emit a bare-label variable node"
    assert "pi()" not in labels


def test_rescript_function_locals_are_not_nodes(tmp_path):
    """Nested let-bindings inside function bodies are locals, not module
    surface. Emitting them inflates the graph with `let url = ...`,
    `let now = Date.now()`, etc. — same convention as Python and JS,
    where nested function-scoped definitions aren't graph nodes.
    """
    src = (
        "let getKeys = () => {\n"
        "  let url = \"/api/keys\"\n"
        "  let now = Date.now()\n"
        "  let helper = (x) => x + 1\n"
        "  Js.fetch(url)\n"
        "}\n"
    )
    r = _extract_rescript_snippet(tmp_path, src)
    labels = _labels(r)
    assert "getKeys()" in labels
    # Nothing inside the function body should leak as a graph node.
    for local in ("url", "now", "helper", ".helper()", "helper()"):
        assert local not in labels, f"function-local {local!r} should not be a node"


def test_rescript_nested_module_emits_full_hierarchy(tmp_path):
    src = (
        "module Outer = {\n"
        "  module Inner = {\n"
        "    let foo = 1\n"
        "    let bar = (x) => x + 1\n"
        "  }\n"
        "  let baz = 2\n"
        "}\n"
    )
    r = _extract_rescript_snippet(tmp_path, src)
    labels = _labels(r)
    assert "Outer" in labels
    assert "Inner" in labels
    # foo and baz are values (no parens), bar is a function (.bar()).
    assert "foo" in labels
    assert ".bar()" in labels
    assert "baz" in labels
    # Edges should attach Inner to Outer (not to file).
    nb = {n["id"]: n["label"] for n in r["nodes"]}
    parent_of_inner = [
        nb.get(e["source"]) for e in r["edges"]
        if nb.get(e.get("target")) == "Inner" and e["relation"] == "contains"
    ]
    assert "Outer" in parent_of_inner


def test_rescript_tuple_destructure_emits_each_name(tmp_path):
    r = _extract_rescript_snippet(tmp_path, "let (first, second) = pair\n")
    labels = _labels(r)
    assert "first" in labels
    assert "second" in labels


def test_rescript_record_destructure_emits_each_name(tmp_path):
    r = _extract_rescript_snippet(tmp_path, "let {alpha, beta} = record\n")
    labels = _labels(r)
    assert "alpha" in labels
    assert "beta" in labels


def test_rescript_resi_signature_function_emits_function_node(tmp_path):
    # `.resi` interface files have signature-only let bindings (no body, just
    # a type annotation). Those whose annotated type is a function_type
    # should emit Function nodes; others should emit Variable nodes.
    _rescript_skip_if_unavailable()
    p = tmp_path / "Sample.resi"
    p.write_text(
        "let getFoo: (~base: int) => int\n"
        "let pi: float\n"
    )
    r = extract_rescript(p)
    labels = _labels(r)
    assert "getFoo()" in labels, "function-typed .resi signature should be a function node"
    assert "pi" in labels, "plain-typed .resi signature should be a variable node"
    assert "pi()" not in labels


def test_rescript_module_method_with_function_body(tmp_path):
    """Module-level let-functions with non-trivial bodies still register as
    methods of the module. The body's locals stay invisible (per the
    function_locals_are_not_nodes contract); only the method itself is on
    the graph.
    """
    src = (
        "module M = {\n"
        "  let f = (x) => {\n"
        "    let g = (y) => y + 1\n"
        "    g(x)\n"
        "  }\n"
        "}\n"
    )
    r = _extract_rescript_snippet(tmp_path, src)
    labels = _labels(r)
    assert "M" in labels
    assert ".f()" in labels       # f is a method of M
    assert ".g()" not in labels   # g is a function-local, not a graph node


# Helpers for type-reference-edge tests.

def _type_refs(r):
    """Return the set of (source_label, target_id) pairs for references_type edges."""
    nb = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (nb.get(e["source"], e["source"]), e["target"])
        for e in r["edges"]
        if e["relation"] == "references_type"
    }


def test_rescript_record_field_emits_type_ref_edge(tmp_path):
    src = "type result = {species: Animal.species}\n"
    r = _extract_rescript_snippet(tmp_path, src)
    refs = _type_refs(r)
    assert ("result", "animal_species") in refs


def test_rescript_variant_arm_payload_emits_type_ref_edge(tmp_path):
    src = (
        "type action =\n"
        "  | Eat(Animal.food)\n"
        "  | Move(Animal.location, Animal.speed)\n"
    )
    r = _extract_rescript_snippet(tmp_path, src)
    refs = _type_refs(r)
    # Both arms should contribute, with two edges from `Move`'s payload.
    assert ("action", "animal_food") in refs
    assert ("action", "animal_location") in refs
    assert ("action", "animal_speed") in refs


def test_rescript_polyvar_arm_payload_emits_type_ref_edge(tmp_path):
    src = "type act = [ #Walk(Animal.speed) | #Sleep(Animal.duration) ]\n"
    r = _extract_rescript_snippet(tmp_path, src)
    refs = _type_refs(r)
    assert ("act", "animal_speed") in refs
    assert ("act", "animal_duration") in refs


def test_rescript_function_signature_emits_type_ref_edges(tmp_path):
    src = "let feed = (a: Animal.species): Animal.food => Animal.eat(a)\n"
    r = _extract_rescript_snippet(tmp_path, src)
    refs = _type_refs(r)
    assert ("feed()", "animal_species") in refs
    assert ("feed()", "animal_food") in refs


def test_rescript_external_declaration_emits_type_ref_edges(tmp_path):
    src = 'external make: Animal.config => Animal.t = "default"\n'
    r = _extract_rescript_snippet(tmp_path, src)
    refs = _type_refs(r)
    assert ("make()", "animal_config") in refs
    assert ("make()", "animal_t") in refs


def test_rescript_nested_module_path_uses_leftmost(tmp_path):
    """`Animal.Habitat.species` should target the leftmost module
    (`Animal`), not the inner submodule (`Habitat`). Real codebases tend
    to organise around top-level modules; targeting the leaf would
    produce a flatter, less useful dependency graph."""
    src = "type t = Animal.Habitat.species\n"
    r = _extract_rescript_snippet(tmp_path, src)
    refs = _type_refs(r)
    targets = {tgt for _src, tgt in refs}
    assert "animal_species" in targets
    # The inner module name must NOT appear in any target id.
    assert not any("habitat" in t for t in targets), \
        f"nested-path target should use leftmost module only: {targets}"


def test_rescript_bare_local_type_emits_no_edge(tmp_path):
    """Plain `option`, `int`, `string`, etc. parse as `type_identifier`,
    not `type_identifier_path`. They have no module-qualifier so they
    must produce no `references_type` edge."""
    src = "type result = {value: option<int>, count: int}\n"
    r = _extract_rescript_snippet(tmp_path, src)
    refs = _type_refs(r)
    assert refs == set(), \
        f"bare local types should not emit references_type edges: {refs}"


def test_rescript_self_reference_uses_extracted_confidence(tmp_path):
    """A type reference whose leftmost module matches the current file's
    bare stem (e.g. `Animal.species` from inside `Animal.res`) is a
    self-reference and gets EXTRACTED confidence; cross-file references
    stay INFERRED until the multi-file extract() resolver runs."""
    _rescript_skip_if_unavailable()
    p = tmp_path / "Animal.res"
    p.write_text("type wrapper = Animal.species\n")
    r = extract_rescript(p)
    self_edges = [
        e for e in r["edges"]
        if e["relation"] == "references_type" and "animal_species" in e["target"]
    ]
    assert self_edges, "expected at least one self-reference edge"
    assert all(e["confidence"] == "EXTRACTED" for e in self_edges)


def test_rescript_cross_file_type_ref_resolves_to_real_node():
    """End-to-end: a `references_type` edge whose target file is in the
    same scan should be rewritten by `extract()`'s cross-file resolver
    so it points at the real node id (not the bare-module phantom)."""
    _rescript_skip_if_unavailable()
    import tempfile
    from graphify.extract import extract
    with tempfile.TemporaryDirectory() as tmp:
        animal = Path(tmp) / "Animal.res"
        animal.write_text("type species = string\n")
        zoo = Path(tmp) / "Zoo.res"
        zoo.write_text("type entry = {species: Animal.species}\n")
        r = extract([animal, zoo])
    refs = [
        e for e in r["edges"]
        if e["relation"] == "references_type"
    ]
    assert refs, "expected at least one references_type edge"
    species_node = next(
        n for n in r["nodes"]
        if n["label"] == "species" and "Animal.res" in n.get("source_file", "")
    )
    # The cross-file resolver should have rewritten the bare-module
    # target (`animal_species`) to the real node id of species in
    # Animal.res.
    assert any(e["target"] == species_node["id"] for e in refs), \
        f"expected target {species_node['id']!r} in {[e['target'] for e in refs]!r}"
