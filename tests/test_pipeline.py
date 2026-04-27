"""
End-to-end pipeline test: detect → extract → build → cluster → analyze → report → export.
Uses the existing test fixtures (code + markdown). No LLM calls - AST extraction only.
Catches regressions in how modules connect, not just individual module behaviour.
"""
import json
import tempfile
from pathlib import Path

import pytest

from graphify.detect import detect
from graphify.extract import collect_files, extract
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json, to_html, to_obsidian

FIXTURES = Path(__file__).parent / "fixtures"


def run_pipeline(tmp_path: Path) -> dict:
    """Run the full pipeline on the fixtures directory. Returns a dict of outputs."""
    # Step 1: detect
    detection = detect(FIXTURES)
    assert detection["total_files"] > 0
    # fixtures corpus is intentionally small (< 5k words), so needs_graph may be False
    assert "files" in detection

    # Step 2: extract (AST only - no LLM)
    code_files = [Path(f) for f in detection["files"].get("code", [])]
    assert len(code_files) > 0
    extraction = extract(code_files)
    assert len(extraction["nodes"]) > 0
    assert len(extraction["edges"]) > 0

    # Step 3: build
    G = build_from_json(extraction)
    assert G.number_of_nodes() > 0
    assert G.number_of_edges() > 0

    # Step 4: cluster
    communities = cluster(G)
    assert len(communities) > 0
    cohesion = score_all(G, communities)
    assert len(cohesion) == len(communities)
    for score in cohesion.values():
        assert 0.0 <= score <= 1.0

    # Step 5: analyze
    gods = god_nodes(G)
    assert len(gods) > 0
    assert all("id" in g and "degree" in g for g in gods)

    surprises = surprising_connections(G, communities)
    assert isinstance(surprises, list)

    labels = {cid: f"Group {cid}" for cid in communities}
    questions = suggest_questions(G, communities, labels)
    assert isinstance(questions, list)

    # Step 6: report
    tokens = {"input": 0, "output": 0}
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, str(FIXTURES), suggested_questions=questions)
    assert "God Nodes" in report
    assert "Communities" in report
    assert len(report) > 100

    # Step 7: export - JSON
    json_path = tmp_path / "graph.json"
    to_json(G, communities, str(json_path))
    assert json_path.exists()
    data = json.loads(json_path.read_text())
    assert "nodes" in data and "links" in data
    assert all("community" in n for n in data["nodes"])

    # Step 8: export - HTML
    html_path = tmp_path / "graph.html"
    to_html(G, communities, str(html_path), community_labels=labels)
    assert html_path.exists()
    html = html_path.read_text()
    assert "vis-network" in html
    assert "RAW_NODES" in html

    # Step 9: export - Obsidian vault
    vault_path = tmp_path / "obsidian"
    n_notes = to_obsidian(G, communities, str(vault_path), community_labels=labels, cohesion=cohesion)
    assert n_notes > 0
    assert (vault_path / ".obsidian" / "graph.json").exists()
    md_files = list(vault_path.glob("*.md"))
    assert len(md_files) > 0

    return {
        "detection": detection,
        "extraction": extraction,
        "graph": G,
        "communities": communities,
        "cohesion": cohesion,
        "gods": gods,
        "surprises": surprises,
        "questions": questions,
        "report": report,
    }


def test_pipeline_runs_end_to_end(tmp_path):
    result = run_pipeline(tmp_path)
    assert result["graph"].number_of_nodes() > 0


def test_pipeline_graph_has_edges(tmp_path):
    result = run_pipeline(tmp_path)
    assert result["graph"].number_of_edges() > 0


def test_pipeline_all_nodes_have_community(tmp_path):
    result = run_pipeline(tmp_path)
    G = result["graph"]
    communities = result["communities"]
    all_community_nodes = {n for nodes in communities.values() for n in nodes}
    for node in G.nodes():
        assert node in all_community_nodes, f"Node {node!r} has no community"


def test_pipeline_report_mentions_top_god_node(tmp_path):
    result = run_pipeline(tmp_path)
    top_god = result["gods"][0]["label"]
    assert top_god in result["report"]


def test_pipeline_detection_finds_code_and_docs(tmp_path):
    result = run_pipeline(tmp_path)
    assert len(result["detection"]["files"].get("code", [])) > 0
    assert len(result["detection"]["files"].get("document", [])) > 0


def test_pipeline_incremental_update(tmp_path):
    """Second run on unchanged corpus should produce identical node/edge counts."""
    result1 = run_pipeline(tmp_path)
    result2 = run_pipeline(tmp_path)
    assert result1["graph"].number_of_nodes() == result2["graph"].number_of_nodes()
    assert result1["graph"].number_of_edges() == result2["graph"].number_of_edges()


def test_pipeline_extraction_confidence_labels(tmp_path):
    result = run_pipeline(tmp_path)
    extraction = result["extraction"]
    valid = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}
    for edge in extraction["edges"]:
        assert edge["confidence"] in valid, f"Invalid confidence: {edge['confidence']}"


def test_pipeline_no_self_loops(tmp_path):
    result = run_pipeline(tmp_path)
    G = result["graph"]
    for u, v in G.edges():
        assert u != v, f"Self-loop found on node {u!r}"
