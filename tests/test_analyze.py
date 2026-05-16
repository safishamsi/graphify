"""Tests for analyze.py."""
import json
import networkx as nx
from pathlib import Path
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.analyze import god_nodes, surprising_connections, _is_concept_node, graph_diff, _surprise_score, _file_category

FIXTURES = Path(__file__).parent / "fixtures"


def make_graph():
    return build_from_json(json.loads((FIXTURES / "extraction.json").read_text()))


def test_god_nodes_returns_list():
    G = make_graph()
    result = god_nodes(G, top_n=3)
    assert isinstance(result, list)
    assert len(result) <= 3


def test_god_nodes_sorted_by_degree():
    G = make_graph()
    result = god_nodes(G, top_n=10)
    degrees = [r["degree"] for r in result]
    assert degrees == sorted(degrees, reverse=True)


def test_god_nodes_have_required_keys():
    G = make_graph()
    result = god_nodes(G, top_n=1)
    assert "id" in result[0]
    assert "label" in result[0]
    assert "degree" in result[0]


def test_surprising_connections_cross_source_multi_file():
    """Multi-file graph: should find cross-file edges between real entities."""
    G = make_graph()
    communities = cluster(G)
    surprises = surprising_connections(G, communities)
    assert len(surprises) > 0
    for s in surprises:
        assert s["source_files"][0] != s["source_files"][1]


def test_surprising_connections_excludes_concept_nodes():
    """Concept nodes (empty source_file) must not appear in surprises."""
    G = make_graph()
    # Add a concept node with empty source_file
    G.add_node("concept_x", label="Abstract Concept", file_type="document", source_file="")
    G.add_edge("n_transformer", "concept_x", relation="relates_to",
               confidence="INFERRED", source_file="", weight=0.5)
    communities = cluster(G)
    surprises = surprising_connections(G, communities)
    labels = [s["source"] for s in surprises] + [s["target"] for s in surprises]
    assert "Abstract Concept" not in labels


def test_surprising_connections_single_file_uses_community_bridges():
    """Single-file graph: should return cross-community edges, not empty list."""
    G = nx.Graph()
    # Build a graph with 2 clear communities + 1 bridge edge
    for i in range(5):
        G.add_node(f"a{i}", label=f"A{i}", file_type="code", source_file="single.py",
                   source_location=f"L{i}")
    for i in range(5):
        G.add_node(f"b{i}", label=f"B{i}", file_type="code", source_file="single.py",
                   source_location=f"L{i+10}")
    # Dense intra-community edges
    for i in range(4):
        G.add_edge(f"a{i}", f"a{i+1}", relation="calls", confidence="EXTRACTED",
                   source_file="single.py", weight=1.0)
    for i in range(4):
        G.add_edge(f"b{i}", f"b{i+1}", relation="calls", confidence="EXTRACTED",
                   source_file="single.py", weight=1.0)
    # One cross-community bridge
    G.add_edge("a4", "b0", relation="references", confidence="INFERRED",
               source_file="single.py", weight=0.5)

    communities = cluster(G)
    surprises = surprising_connections(G, communities)
    # Should find at least the bridge edge
    assert len(surprises) > 0


def test_surprising_connections_ambiguous_scores_higher_than_extracted():
    """AMBIGUOUS edge should score higher than an otherwise identical EXTRACTED edge."""
    G = nx.Graph()
    for nid, label, src in [
        ("a", "Alpha", "repo1/model.py"),
        ("b", "Beta", "repo2/train.py"),
        ("c", "Gamma", "repo1/data.py"),
        ("d", "Delta", "repo2/eval.py"),
    ]:
        G.add_node(nid, label=label, source_file=src, file_type="code")
    G.add_edge("a", "b", relation="calls", confidence="AMBIGUOUS", weight=1.0, source_file="repo1/model.py")
    G.add_edge("c", "d", relation="calls", confidence="EXTRACTED", weight=1.0, source_file="repo1/data.py")
    communities = {0: ["a", "c"], 1: ["b", "d"]}
    nc = {"a": 0, "c": 0, "b": 1, "d": 1}
    score_amb, _ = _surprise_score(G, "a", "b", G.edges["a", "b"], nc, "repo1/model.py", "repo2/train.py")
    score_ext, _ = _surprise_score(G, "c", "d", G.edges["c", "d"], nc, "repo1/data.py", "repo2/eval.py")
    assert score_amb > score_ext


def test_surprising_connections_cross_type_scores_higher():
    """Code↔paper edge should score higher than code↔code edge."""
    G = nx.Graph()
    for nid, label, src in [
        ("a", "Transformer", "code/model.py"),
        ("b", "FlashAttn", "papers/flash.pdf"),
        ("c", "Trainer", "code/train.py"),
        ("d", "Dataset", "code/data.py"),
    ]:
        G.add_node(nid, label=label, source_file=src, file_type="code")
    G.add_edge("a", "b", relation="references", confidence="EXTRACTED", weight=1.0, source_file="code/model.py")
    G.add_edge("c", "d", relation="calls", confidence="EXTRACTED", weight=1.0, source_file="code/train.py")
    nc = {"a": 0, "b": 1, "c": 0, "d": 0}
    score_cross, reasons_cross = _surprise_score(G, "a", "b", G.edges["a", "b"], nc, "code/model.py", "papers/flash.pdf")
    score_same, _ = _surprise_score(G, "c", "d", G.edges["c", "d"], nc, "code/train.py", "code/data.py")
    assert score_cross > score_same
    assert any("code" in r and "paper" in r for r in reasons_cross)


def _make_cross_lang_graph():
    """Helper: Python node in backend/, TypeScript node in frontend/, different communities."""
    G = nx.Graph()
    G.add_node("py_auth", label="AuthError", source_file="backend/auth.py", file_type="code")
    G.add_node("ts_member", label="Member", source_file="frontend/types.ts", file_type="code")
    G.add_node("py_a", label="ServiceA", source_file="backend/service.py", file_type="code")
    G.add_node("py_b", label="ServiceB", source_file="backend/utils.py", file_type="code")
    return G


def test_cross_language_inferred_calls_suppressed():
    """Cross-language INFERRED calls edge should score lower than same-language EXTRACTED."""
    G = _make_cross_lang_graph()
    G.add_edge("py_auth", "ts_member", relation="calls", confidence="INFERRED",
               weight=0.8, source_file="backend/auth.py")
    G.add_edge("py_a", "py_b", relation="calls", confidence="EXTRACTED",
               weight=1.0, source_file="backend/service.py")
    nc = {"py_auth": 0, "ts_member": 1, "py_a": 0, "py_b": 0}
    score_cross, _ = _surprise_score(G, "py_auth", "ts_member",
                                      G.edges["py_auth", "ts_member"], nc,
                                      "backend/auth.py", "frontend/types.ts")
    score_same, _ = _surprise_score(G, "py_a", "py_b",
                                     G.edges["py_a", "py_b"], nc,
                                     "backend/service.py", "backend/utils.py")
    assert score_cross <= score_same


def test_cross_language_inferred_uses_suppressed():
    """Cross-language INFERRED uses edge (the exact rsl-siege-manager false positive) should be suppressed."""
    G = _make_cross_lang_graph()
    G.add_edge("py_auth", "ts_member", relation="uses", confidence="INFERRED",
               weight=0.8, source_file="backend/auth.py")
    G.add_edge("py_a", "py_b", relation="calls", confidence="EXTRACTED",
               weight=1.0, source_file="backend/service.py")
    nc = {"py_auth": 0, "ts_member": 1, "py_a": 0, "py_b": 0}
    score_cross, _ = _surprise_score(G, "py_auth", "ts_member",
                                      G.edges["py_auth", "ts_member"], nc,
                                      "backend/auth.py", "frontend/types.ts")
    score_same, _ = _surprise_score(G, "py_a", "py_b",
                                     G.edges["py_a", "py_b"], nc,
                                     "backend/service.py", "backend/utils.py")
    assert score_cross <= score_same


def test_cross_language_semantically_similar_not_suppressed():
    """`semantically_similar_to` across languages is a genuine insight — must not be suppressed."""
    G = _make_cross_lang_graph()
    G.add_edge("py_auth", "ts_member", relation="semantically_similar_to",
               confidence="INFERRED", weight=0.85, source_file="backend/auth.py")
    G.add_edge("py_a", "py_b", relation="calls", confidence="EXTRACTED",
               weight=1.0, source_file="backend/service.py")
    nc = {"py_auth": 0, "ts_member": 1, "py_a": 0, "py_b": 0}
    score_sem, _ = _surprise_score(G, "py_auth", "ts_member",
                                    G.edges["py_auth", "ts_member"], nc,
                                    "backend/auth.py", "frontend/types.ts")
    score_same, _ = _surprise_score(G, "py_a", "py_b",
                                     G.edges["py_a", "py_b"], nc,
                                     "backend/service.py", "backend/utils.py")
    assert score_sem > score_same


def test_same_language_inferred_calls_not_suppressed():
    """INFERRED calls within the same language family must not be affected."""
    G = nx.Graph()
    G.add_node("py_a", label="ModuleA", source_file="src/a.py", file_type="code")
    G.add_node("py_b", label="ModuleB", source_file="src/b.py", file_type="code")
    G.add_node("py_c", label="ModuleC", source_file="src/c.py", file_type="code")
    G.add_node("py_d", label="ModuleD", source_file="src/d.py", file_type="code")
    G.add_edge("py_a", "py_b", relation="calls", confidence="INFERRED",
               weight=0.8, source_file="src/a.py")
    G.add_edge("py_c", "py_d", relation="calls", confidence="EXTRACTED",
               weight=1.0, source_file="src/c.py")
    nc = {"py_a": 0, "py_b": 1, "py_c": 0, "py_d": 1}
    score_inf, _ = _surprise_score(G, "py_a", "py_b", G.edges["py_a", "py_b"], nc,
                                    "src/a.py", "src/b.py")
    score_ext, _ = _surprise_score(G, "py_c", "py_d", G.edges["py_c", "py_d"], nc,
                                    "src/c.py", "src/d.py")
    assert score_inf > score_ext


def test_cross_language_extracted_calls_not_suppressed():
    """EXTRACTED cross-language edges are real structural facts — must not be penalised."""
    G = _make_cross_lang_graph()
    G.add_edge("py_auth", "ts_member", relation="calls", confidence="EXTRACTED",
               weight=1.0, source_file="backend/auth.py")
    nc = {"py_auth": 0, "ts_member": 1}
    score, _ = _surprise_score(G, "py_auth", "ts_member",
                                G.edges["py_auth", "ts_member"], nc,
                                "backend/auth.py", "frontend/types.ts")
    assert score >= 1


def _make_code_doc_graph():
    """Helper: Go code + Markdown README referencing it (real artella-backend pattern)."""
    G = nx.Graph()
    G.add_node("go_proc", label="VideoProcessor",
               source_file="libs/transcoder/worker.go", file_type="code")
    G.add_node("md_ref", label="NewVideoProcessor",
               source_file="services/artella-videosplitter/Readme.md", file_type="document")
    G.add_node("go_a", label="ServiceA",
               source_file="libs/a.go", file_type="code")
    G.add_node("go_b", label="ServiceB",
               source_file="libs/b.go", file_type="code")
    return G


def test_code_doc_inferred_calls_suppressed():
    """A README mentioning a code symbol via INFERRED `calls` edge is a doc
    cross-reference, not a structural surprise — should be suppressed like
    cross-language INFERRED calls were in d14e8a7. This is the artella-backend
    pattern: libs/transcoder/worker.go -> services/.../Readme.md."""
    G = _make_code_doc_graph()
    G.add_edge("go_proc", "md_ref", relation="calls", confidence="INFERRED",
               weight=0.8, source_file="libs/transcoder/worker.go")
    G.add_edge("go_a", "go_b", relation="calls", confidence="EXTRACTED",
               weight=1.0, source_file="libs/a.go")
    nc = {"go_proc": 0, "md_ref": 1, "go_a": 0, "go_b": 0}
    score_cross, _ = _surprise_score(G, "go_proc", "md_ref",
                                      G.edges["go_proc", "md_ref"], nc,
                                      "libs/transcoder/worker.go",
                                      "services/artella-videosplitter/Readme.md")
    score_same, _ = _surprise_score(G, "go_a", "go_b",
                                     G.edges["go_a", "go_b"], nc,
                                     "libs/a.go", "libs/b.go")
    assert score_cross <= score_same, (
        f"code<->doc INFERRED calls should be suppressed, got cross={score_cross}, same={score_same}"
    )


def test_code_doc_inferred_uses_suppressed():
    """Same as above for `uses` relation — covers the resolver-pollution case
    where a README's prose creates an INFERRED `uses` edge against a code symbol."""
    G = _make_code_doc_graph()
    G.add_edge("go_proc", "md_ref", relation="uses", confidence="INFERRED",
               weight=0.8, source_file="libs/transcoder/worker.go")
    G.add_edge("go_a", "go_b", relation="calls", confidence="EXTRACTED",
               weight=1.0, source_file="libs/a.go")
    nc = {"go_proc": 0, "md_ref": 1, "go_a": 0, "go_b": 0}
    score_cross, _ = _surprise_score(G, "go_proc", "md_ref",
                                      G.edges["go_proc", "md_ref"], nc,
                                      "libs/transcoder/worker.go",
                                      "services/artella-videosplitter/Readme.md")
    score_same, _ = _surprise_score(G, "go_a", "go_b",
                                     G.edges["go_a", "go_b"], nc,
                                     "libs/a.go", "libs/b.go")
    assert score_cross <= score_same


def test_code_doc_extracted_not_suppressed():
    """EXTRACTED code<->doc edges are explicit references (e.g. doc literally
    contains a code-pattern match) — these are real structural facts and must
    not be suppressed."""
    G = _make_code_doc_graph()
    G.add_edge("go_proc", "md_ref", relation="references",
               confidence="EXTRACTED", weight=1.0,
               source_file="services/artella-videosplitter/Readme.md")
    nc = {"go_proc": 0, "md_ref": 1}
    score, _ = _surprise_score(G, "go_proc", "md_ref",
                                G.edges["go_proc", "md_ref"], nc,
                                "libs/transcoder/worker.go",
                                "services/artella-videosplitter/Readme.md")
    # Should still get conf_bonus (1) plus cross-file-type bonus (2) plus
    # other applicable bonuses — at minimum >= 3.
    assert score >= 3, f"EXTRACTED code<->doc must keep its bonuses, got {score}"


def test_code_doc_inferred_semantically_similar_not_suppressed():
    """The `semantically_similar_to` relation is preserved by d14e8a7 doctrine —
    a code↔doc INFERRED similarity edge represents an explicit LLM insight
    (the doc and the code share a concept) and must NOT be suppressed even
    though it crosses categories. Protects the relation gate."""
    G = _make_code_doc_graph()
    G.add_edge("go_proc", "md_ref", relation="semantically_similar_to",
               confidence="INFERRED", weight=0.8,
               source_file="libs/transcoder/worker.go")
    G.add_edge("go_a", "go_b", relation="calls", confidence="EXTRACTED",
               weight=1.0, source_file="libs/a.go")
    nc = {"go_proc": 0, "md_ref": 1, "go_a": 0, "go_b": 0}
    score_sem, _ = _surprise_score(G, "go_proc", "md_ref",
                                    G.edges["go_proc", "md_ref"], nc,
                                    "libs/transcoder/worker.go",
                                    "services/artella-videosplitter/Readme.md")
    score_same, _ = _surprise_score(G, "go_a", "go_b",
                                     G.edges["go_a", "go_b"], nc,
                                     "libs/a.go", "libs/b.go")
    assert score_sem > score_same, (
        f"semantically_similar_to across code<->doc must NOT be suppressed, "
        f"got sem={score_sem}, same={score_same}"
    )


def test_code_unknown_extension_inferred_calls_suppressed():
    """Document the `_file_category` fallback: any unknown file extension is
    classified as "doc" (the function returns "doc" when not code/paper/image).
    This means INFERRED calls/uses between code and an unknown-extension file
    are also suppressed by the doc-category gate. Intentional — these edges
    are almost always resolver pollution of the same shape as code↔README."""
    assert _file_category("notes/random.xyz") == "doc"  # confirms fallback
    G = nx.Graph()
    G.add_node("go_a", label="Handler", source_file="libs/a.go", file_type="code")
    G.add_node("unk", label="Handler", source_file="vendor/unknown.xyz", file_type="document")
    G.add_node("c", label="C", source_file="libs/c.go", file_type="code")
    G.add_node("d", label="D", source_file="libs/d.go", file_type="code")
    G.add_edge("go_a", "unk", relation="calls", confidence="INFERRED",
               weight=0.8, source_file="libs/a.go")
    G.add_edge("c", "d", relation="calls", confidence="EXTRACTED",
               weight=1.0, source_file="libs/c.go")
    nc = {"go_a": 0, "unk": 1, "c": 0, "d": 0}
    score_unknown, _ = _surprise_score(G, "go_a", "unk",
                                        G.edges["go_a", "unk"], nc,
                                        "libs/a.go", "vendor/unknown.xyz")
    score_same, _ = _surprise_score(G, "c", "d",
                                     G.edges["c", "d"], nc,
                                     "libs/c.go", "libs/d.go")
    assert score_unknown <= score_same, (
        f"code<->unknown-extension INFERRED calls fall under the doc-category "
        f"suppression by design, got unknown={score_unknown}, same={score_same}"
    )


def test_code_paper_inferred_calls_not_suppressed():
    """code<->paper INFERRED edges (.go <-> .pdf) are NOT the README-mention case
    and remain genuinely surprising — must not be caught by the code<->doc rule.
    Verifies the suppression is narrowly scoped to file_category=='doc'."""
    G = nx.Graph()
    G.add_node("go_attn", label="Attention", source_file="libs/ml/attention.go", file_type="code")
    G.add_node("pdf_attn", label="Attention", source_file="papers/attention-is-all-you-need.pdf", file_type="paper")
    G.add_node("go_a", label="A", source_file="libs/a.go", file_type="code")
    G.add_node("go_b", label="B", source_file="libs/b.go", file_type="code")
    G.add_edge("go_attn", "pdf_attn", relation="calls", confidence="INFERRED",
               weight=0.8, source_file="libs/ml/attention.go")
    G.add_edge("go_a", "go_b", relation="calls", confidence="EXTRACTED",
               weight=1.0, source_file="libs/a.go")
    nc = {"go_attn": 0, "pdf_attn": 1, "go_a": 0, "go_b": 0}
    score_paper, _ = _surprise_score(G, "go_attn", "pdf_attn",
                                      G.edges["go_attn", "pdf_attn"], nc,
                                      "libs/ml/attention.go",
                                      "papers/attention-is-all-you-need.pdf")
    score_same, _ = _surprise_score(G, "go_a", "go_b",
                                     G.edges["go_a", "go_b"], nc,
                                     "libs/a.go", "libs/b.go")
    assert score_paper > score_same, (
        f"code<->paper INFERRED is a real cross-format surprise, "
        f"got paper={score_paper}, same={score_same}"
    )


def test_god_nodes_filters_json_noise_keys():
    """Common JSON keys (start/end/name/properties/id/...) appearing in .json
    sources should be excluded from god_nodes — their degree is positional,
    not architectural. Real Go method abstractions must outrank them even
    when the JSON-key degree is higher."""
    G = nx.Graph()
    # Single legitimate code abstraction with modest degree.
    G.add_node("db_conn", label="DB()",
               source_file="database/connection.go", file_type="code")
    for i in range(20):
        n = f"caller_{i}"
        G.add_node(n, label=f"Caller{i}", source_file=f"libs/caller_{i}.go",
                   file_type="code")
        G.add_edge(n, "db_conn", relation="calls", confidence="EXTRACTED")
    # Massive-degree JSON-key noise that should be filtered.
    G.add_node("dates_start", label="start",
               source_file="testhelpers/dates.json", file_type="code")
    for i in range(50):
        n = f"term_{i}"
        G.add_node(n, label=f"T{i}", source_file="testhelpers/dates.json",
                   file_type="code")
        G.add_edge(n, "dates_start", relation="references",
                   confidence="EXTRACTED")
    gods = god_nodes(G, top_n=3)
    labels = [g["label"] for g in gods]
    assert "start" not in labels, (
        f"common JSON-key 'start' should be filtered out, got {labels}"
    )
    assert "DB()" in labels, (
        f"real code abstraction 'DB()' must surface, got {labels}"
    )


def test_god_nodes_keeps_noise_label_when_source_is_code():
    """`start` is only filtered when its source is .json — a real function or
    variable named `start` defined in a .go/.ts file must NOT be filtered."""
    G = nx.Graph()
    G.add_node("go_start", label="start",
               source_file="libs/scheduler/runner.go", file_type="code")
    G.add_node("low_deg", label="OtherThing",
               source_file="libs/other.go", file_type="code")
    for i in range(5):
        n = f"caller_{i}"
        G.add_node(n, label=f"C{i}", source_file=f"libs/c_{i}.go",
                   file_type="code")
        G.add_edge(n, "go_start", relation="calls", confidence="EXTRACTED")
    G.add_edge("low_deg", "caller_0", relation="calls", confidence="EXTRACTED")
    gods = god_nodes(G, top_n=2)
    labels = [g["label"] for g in gods]
    assert "start" in labels, (
        f"`start` defined in Go source must NOT be filtered, got {labels}"
    )


def test_god_nodes_keeps_real_label_in_json_source():
    """A JSON-sourced node with a non-common label (e.g. domain entity name)
    should NOT be filtered — only the small set of generic JSON keys are
    excluded."""
    G = nx.Graph()
    G.add_node("config_node", label="ProductionEsConfig",
               source_file="config/elasticsearch.json", file_type="code")
    for i in range(10):
        n = f"ref_{i}"
        G.add_node(n, label=f"R{i}", source_file=f"libs/r_{i}.go",
                   file_type="code")
        G.add_edge(n, "config_node", relation="references",
                   confidence="EXTRACTED")
    gods = god_nodes(G, top_n=1)
    labels = [g["label"] for g in gods]
    assert "ProductionEsConfig" in labels, (
        f"domain entity in JSON source must NOT be filtered, got {labels}"
    )


def test_god_nodes_filter_is_case_insensitive():
    """JSON-key filter must match regardless of label casing — `Start`, `START`,
    and `start` should all be treated as the same generic key."""
    G = nx.Graph()
    G.add_node("real", label="RealAbstraction",
               source_file="libs/real.go", file_type="code")
    G.add_edge("real", "real", relation="self")  # nominal edge so it exists
    for variant in ("Start", "START", "Name", "ID"):
        nid = f"json_{variant.lower()}"
        G.add_node(nid, label=variant,
                   source_file="testhelpers/data.json", file_type="code")
        # Give each high degree to make them outrank `real` if not filtered.
        for i in range(15):
            target = f"{nid}_ref_{i}"
            G.add_node(target, label=f"X{i}",
                       source_file="testhelpers/data.json", file_type="code")
            G.add_edge(target, nid, relation="references")
    gods = god_nodes(G, top_n=5)
    labels = [g["label"] for g in gods]
    for variant in ("Start", "START", "Name", "ID"):
        assert variant not in labels, (
            f"`{variant}` (case variant of JSON-noise key) must be filtered, got {labels}"
        )


def test_surprising_connections_have_why_field():
    G = make_graph()
    communities = cluster(G)
    for s in surprising_connections(G, communities):
        assert "why" in s
        assert isinstance(s["why"], str)
        assert len(s["why"]) > 0


def test_file_category():
    assert _file_category("model.py") == "code"
    assert _file_category("flash.pdf") == "paper"
    assert _file_category("diagram.png") == "image"
    assert _file_category("notes.md") == "doc"
    # Languages added in later releases — would misclassify as "doc" without detect.py import
    assert _file_category("app.swift") == "code"
    assert _file_category("plugin.lua") == "code"
    assert _file_category("build.zig") == "code"
    assert _file_category("deploy.ps1") == "code"
    assert _file_category("server.ex") == "code"
    assert _file_category("component.jsx") == "code"
    assert _file_category("analysis.jl") == "code"
    assert _file_category("view.m") == "code"


def test_is_concept_node_empty_source():
    G = nx.Graph()
    G.add_node("c1", source_file="")
    assert _is_concept_node(G, "c1") is True


def test_is_concept_node_real_file():
    G = nx.Graph()
    G.add_node("n1", source_file="model.py")
    assert _is_concept_node(G, "n1") is False


def test_surprising_connections_have_required_keys():
    G = make_graph()
    communities = cluster(G)
    for s in surprising_connections(G, communities):
        assert "source" in s
        assert "target" in s
        assert "source_files" in s
        assert "confidence" in s


# --- graph_diff tests ---

def _make_simple_graph(nodes, edges):
    """Helper: build a small nx.Graph from node/edge specs."""
    G = nx.Graph()
    for node_id, label in nodes:
        G.add_node(node_id, label=label, source_file="test.py")
    for src, tgt, rel, conf in edges:
        G.add_edge(src, tgt, relation=rel, confidence=conf)
    return G


def test_graph_diff_new_nodes():
    G_old = _make_simple_graph([("n1", "Alpha"), ("n2", "Beta")], [])
    G_new = _make_simple_graph([("n1", "Alpha"), ("n2", "Beta"), ("n3", "Gamma")], [])
    diff = graph_diff(G_old, G_new)
    assert len(diff["new_nodes"]) == 1
    assert diff["new_nodes"][0]["id"] == "n3"
    assert diff["new_nodes"][0]["label"] == "Gamma"
    assert diff["removed_nodes"] == []
    assert "1 new node" in diff["summary"]


def test_graph_diff_removed_nodes():
    G_old = _make_simple_graph([("n1", "Alpha"), ("n2", "Beta"), ("n3", "Gamma")], [])
    G_new = _make_simple_graph([("n1", "Alpha"), ("n2", "Beta")], [])
    diff = graph_diff(G_old, G_new)
    assert diff["new_nodes"] == []
    assert len(diff["removed_nodes"]) == 1
    assert diff["removed_nodes"][0]["id"] == "n3"
    assert "removed" in diff["summary"]


def test_graph_diff_new_edges():
    nodes = [("n1", "Alpha"), ("n2", "Beta"), ("n3", "Gamma")]
    G_old = _make_simple_graph(nodes, [("n1", "n2", "calls", "EXTRACTED")])
    G_new = _make_simple_graph(
        nodes,
        [("n1", "n2", "calls", "EXTRACTED"), ("n2", "n3", "uses", "INFERRED")],
    )
    diff = graph_diff(G_old, G_new)
    assert len(diff["new_edges"]) == 1
    new_edge = diff["new_edges"][0]
    assert new_edge["relation"] == "uses"
    assert new_edge["confidence"] == "INFERRED"
    assert diff["removed_edges"] == []
    assert "new edge" in diff["summary"]


def test_graph_diff_empty_diff():
    nodes = [("n1", "Alpha"), ("n2", "Beta")]
    edges = [("n1", "n2", "calls", "EXTRACTED")]
    G_old = _make_simple_graph(nodes, edges)
    G_new = _make_simple_graph(nodes, edges)
    diff = graph_diff(G_old, G_new)
    assert diff["new_nodes"] == []
    assert diff["removed_nodes"] == []
    assert diff["new_edges"] == []
    assert diff["removed_edges"] == []
    assert diff["summary"] == "no changes"
