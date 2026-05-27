"""Tests for graphify.ingest.save_query_result"""
from __future__ import annotations
from graphify.ingest import save_query_result


def test_file_created(tmp_path):
    out = save_query_result("what is attention?", "Attention is...", tmp_path / "memory")
    assert out.exists()


def test_filename_format(tmp_path):
    mem = tmp_path / "memory"
    out = save_query_result("what connects A to B?", "They share...", mem)
    assert out.name.startswith("query_")
    assert out.suffix == ".md"


def test_frontmatter_question(tmp_path):
    mem = tmp_path / "memory"
    question = "what is attention?"
    out = save_query_result(question, "Attention is softmax.", mem)
    content = out.read_text()
    assert "question:" in content
    assert "attention" in content.lower()


def test_frontmatter_type(tmp_path):
    mem = tmp_path / "memory"
    out = save_query_result("q", "a", mem, query_type="path_query")
    content = out.read_text()
    assert 'type: "path_query"' in content


def test_source_nodes_included(tmp_path):
    mem = tmp_path / "memory"
    nodes = ["AttentionLayer", "SoftmaxFunc"]
    out = save_query_result("q", "a", mem, source_nodes=nodes)
    content = out.read_text()
    assert "AttentionLayer" in content
    assert "SoftmaxFunc" in content


def test_source_nodes_capped_at_10(tmp_path):
    mem = tmp_path / "memory"
    nodes = [f"Node{i}" for i in range(20)]
    out = save_query_result("q", "a", mem, source_nodes=nodes)
    content = out.read_text()
    # Only first 10 should appear in frontmatter source_nodes line
    fm_line = [l for l in content.splitlines() if l.startswith("source_nodes:")][0]
    assert fm_line.count('"Node') == 10


def test_memory_dir_created(tmp_path):
    mem = tmp_path / "deep" / "memory"
    assert not mem.exists()
    save_query_result("q", "a", mem)
    assert mem.exists()


def test_answer_in_body(tmp_path):
    mem = tmp_path / "memory"
    answer = "The answer is forty-two."
    out = save_query_result("what is the answer?", answer, mem)
    content = out.read_text()
    assert answer in content
