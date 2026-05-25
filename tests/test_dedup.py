"""Tests for graphify/dedup.py entity deduplication pipeline."""
from __future__ import annotations
import pytest
from graphify.dedup import deduplicate_entities, _entropy, _shingles


# ── entropy gate ─────────────────────────────────────────────────────────────

def test_entropy_short_label_low():
    assert _entropy("AI") < 2.5

def test_entropy_normal_label_high():
    assert _entropy("AuthenticationManager") >= 2.5

def test_entropy_empty_string():
    assert _entropy("") == 0.0


# ── shingles ─────────────────────────────────────────────────────────────────

def test_shingles_produces_trigrams():
    s = _shingles("hello")
    assert "hel" in s
    assert "ell" in s
    assert "llo" in s

def test_shingles_short_string():
    # strings shorter than 3 chars return single shingle of the string itself
    assert _shingles("ab") == {"ab"}


# ── full pipeline ─────────────────────────────────────────────────────────────

def _make_nodes(*labels):
    return [{"id": label.lower().replace(" ", "_"), "label": label, "source_file": "test.md"} for label in labels]

def _make_edges(src, tgt, relation="relates_to"):
    return [{"source": src, "target": tgt, "relation": relation}]


def test_exact_duplicates_merged():
    nodes = _make_nodes("UserService", "userservice", "User Service")
    edges = []
    result_nodes, result_edges = deduplicate_entities(nodes, edges, communities={})
    # All three are the same concept — only one survives
    assert len(result_nodes) == 1


def test_typo_merged():
    # "GraphExtractor" vs "Graph Extractor" — Jaro-Winkler >= 0.92
    nodes = _make_nodes("GraphExtractor", "Graph Extractor")
    edges = []
    result_nodes, _ = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 1


def test_unrelated_not_merged():
    nodes = _make_nodes("UserService", "OrderService")
    edges = []
    result_nodes, _ = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 2


def test_short_low_entropy_not_merged():
    # "AI" and "ML" are low-entropy — entropy gate skips them
    nodes = _make_nodes("AI", "ML")
    edges = []
    result_nodes, _ = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 2


def test_edges_rewired_after_merge():
    nodes = _make_nodes("GraphExtractor", "Graph Extractor", "Parser")
    # edge from loser to Parser should be rewired to winner
    edges = [{"source": "graph_extractor", "target": "parser", "relation": "uses"}]
    result_nodes, result_edges = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 2  # merged + Parser
    # edge should still exist (rewired to winner)
    assert len(result_edges) == 1


def test_self_loops_dropped_after_merge():
    # If both endpoints of an edge get merged into same node, drop the edge
    nodes = _make_nodes("GraphExtractor", "Graph Extractor")
    edges = [{"source": "graphextractor", "target": "graph_extractor", "relation": "same"}]
    _, result_edges = deduplicate_entities(nodes, edges, communities={})
    assert result_edges == []


def test_community_boost_aids_merge():
    # Two nodes in same community with score in 0.75-0.85 zone get boosted
    nodes = _make_nodes("AuthManager", "Auth Manager")
    edges = []
    # Same community → boost → merge
    communities = {"authmanager": 1, "auth_manager": 1}
    result_with, _ = deduplicate_entities(nodes, edges, communities=communities)
    # Different community → no boost
    communities_diff = {"authmanager": 1, "auth_manager": 2}
    result_without, _ = deduplicate_entities(nodes, edges, communities=communities_diff)
    assert len(result_with) <= len(result_without)


def test_empty_inputs():
    result_nodes, result_edges = deduplicate_entities([], [], communities={})
    assert result_nodes == []
    assert result_edges == []


def test_single_node_no_crash():
    nodes = _make_nodes("UserService")
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 1


def test_dedup_llm_flag_accepted():
    """deduplicate_entities accepts dedup_llm_backend without crashing when no ambiguous pairs exist."""
    nodes = _make_nodes("UserService", "OrderService")
    edges = []
    result_nodes, _ = deduplicate_entities(nodes, edges, communities={}, dedup_llm_backend=None)
    assert len(result_nodes) == 2


# ── build integration ─────────────────────────────────────────────────────────

def test_build_calls_dedup():
    """build() should deduplicate near-identical nodes across extractions."""
    from graphify.build import build
    chunk1 = {
        "nodes": [{"id": "graphextractor", "label": "GraphExtractor", "source_file": "a.py"}],
        "edges": [],
    }
    chunk2 = {
        "nodes": [{"id": "graph_extractor", "label": "Graph Extractor", "source_file": "b.py"}],
        "edges": [],
    }
    G = build([chunk1, chunk2])
    assert G.number_of_nodes() == 1


# --- #878: fuzzy dedup false merges on short/variant labels ---

def test_dedup_does_not_merge_numeric_variants(tmp_path):
    """Chip SKU variants (ASR1603 vs ASR1605) must not be merged (#878)."""
    nodes = _make_nodes("ASR1603", "ASR1605")
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2, "ASR1603 and ASR1605 are distinct chip models, not duplicates"


def test_dedup_does_not_merge_short_insertion_variants(tmp_path):
    """Short labels differing by an insertion (cranel vs cranelr) must not merge (#878)."""
    nodes = _make_nodes("cranel", "cranelr")
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2, "cranel and cranelr are distinct, not a typo"


def test_dedup_does_not_merge_model_with_suffix(tmp_path):
    """M1 vs M1 Pro must not merge (#878)."""
    nodes = _make_nodes("M1", "M1 Pro")
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2, "M1 and M1 Pro are distinct Apple chip variants"


def test_dedup_still_merges_real_typos():
    """Genuine same-length single-char typos should still merge (#878 non-regression)."""
    from graphify.dedup import _is_variant_pair, _short_label_blocked
    from rapidfuzz.distance import JaroWinkler
    a, b = "graphextractor", "graphextractar"
    score = JaroWinkler.normalized_similarity(a, b) * 100
    assert not _is_variant_pair(a, b), "not a variant pair"
    assert not _short_label_blocked(a, b, score), "long-enough label, should not be blocked"


def test_variant_pair_helper():
    """_is_variant_pair correctly identifies chip-model variant pairs (#878)."""
    from graphify.dedup import _is_variant_pair
    assert _is_variant_pair("asr1603", "asr1605")
    assert _is_variant_pair("cortex a55", "cortex a55x")
    assert not _is_variant_pair("graphextractor", "graphextracter")
    assert not _is_variant_pair("foo", "foo")
