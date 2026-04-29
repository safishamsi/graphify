import hashlib
import json
import math
import random
from pathlib import Path

import networkx as nx
import pytest

numpy = pytest.importorskip("numpy", reason="numpy required for embedding tests")

from graphify.embed import (
    EMBEDDING_DIM,
    compute_cosine_similarity,
    generate_simple_embeddings,
    get_query_embedding,
    load_embeddings,
    save_embeddings,
    search_similar_nodes,
)


def _make_test_graph(num_nodes: int = 50, seed: int = 42) -> nx.Graph:
    rng = random.Random(seed)
    G = nx.Graph()
    for i in range(num_nodes):
        label = f"entity_{i}"
        G.add_node(i, label=label, source_file=f"src/file_{i}.py", community=i % 5)
    node_list = list(G.nodes())
    for i in range(num_nodes * 2):
        u = rng.choice(node_list)
        v = rng.choice(node_list)
        if u != v:
            G.add_edge(u, v, relation=rng.choice(["calls", "imports"]), confidence="EXTRACTED", weight=1.0)
    return G


class TestGenerateEmbeddings:
    def test_output_shape(self):
        G = _make_test_graph(50)
        embeddings = generate_simple_embeddings(G, seed=42)
        assert len(embeddings) == G.number_of_nodes()
        for node_id, vec in embeddings.items():
            assert len(vec) == EMBEDDING_DIM
            assert all(isinstance(v, float) for v in vec)

    def test_deterministic(self):
        G = _make_test_graph(30)
        e1 = generate_simple_embeddings(G, seed=42)
        e2 = generate_simple_embeddings(G, seed=42)
        for nid in e1:
            for a, b in zip(e1[nid], e2[nid]):
                assert a == pytest.approx(b)

    def test_l2_normalized(self):
        G = _make_test_graph(30)
        embeddings = generate_simple_embeddings(G, seed=42)
        for vec in embeddings.values():
            norm = math.sqrt(sum(v * v for v in vec))
            assert norm == pytest.approx(1.0, rel=1e-4)

    def test_custom_dimensions(self):
        G = _make_test_graph(20)
        dim = 64
        embeddings = generate_simple_embeddings(G, dimensions=dim, seed=42)
        for vec in embeddings.values():
            assert len(vec) == dim


class TestCosineSimilarity:
    def test_identical_vectors(self):
        vec = [1.0, 0.0, 0.0]
        sim = compute_cosine_similarity(vec, vec)
        assert sim == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        sim = compute_cosine_similarity(vec1, vec2)
        assert sim == pytest.approx(0.0)

    def test_opposite_vectors(self):
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [-1.0, 0.0, 0.0]
        sim = compute_cosine_similarity(vec1, vec2)
        assert sim == pytest.approx(-1.0)

    def test_zero_vector(self):
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        sim = compute_cosine_similarity(vec1, vec2)
        assert sim == 0.0

    def test_dimension_mismatch(self):
        with pytest.raises(ValueError):
            compute_cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])


class TestSearchSimilarNodes:
    def test_search_returns_sorted(self):
        G = _make_test_graph(20)
        embeddings = generate_simple_embeddings(G, seed=42)
        query_vec = embeddings.get("0", [0.0] * EMBEDDING_DIM)
        results = search_similar_nodes(query_vec, embeddings, top_k=5)
        assert len(results) == 5
        assert results[0][1] >= results[-1][1]

    def test_search_self_is_most_similar(self):
        G = _make_test_graph(30)
        embeddings = generate_simple_embeddings(G, seed=42)
        for node_id, vec in embeddings.items():
            results = search_similar_nodes(vec, embeddings, top_k=1)
            assert results[0][0] == node_id
            assert results[0][1] == pytest.approx(1.0)
            break

    def test_search_top_k_larger_than_nodes(self):
        G = _make_test_graph(10)
        embeddings = generate_simple_embeddings(G, seed=42)
        query_vec = embeddings.get("0", [0.0] * EMBEDDING_DIM)
        results = search_similar_nodes(query_vec, embeddings, top_k=100)
        assert len(results) == 10


class TestEmbeddingIO:
    def test_save_and_load(self, tmp_path):
        G = _make_test_graph(20)
        embeddings = generate_simple_embeddings(G, seed=42)
        out_path = tmp_path / "embeddings.json"
        save_embeddings(embeddings, out_path)
        assert out_path.exists()
        loaded = load_embeddings(out_path)
        assert len(loaded) == len(embeddings)
        for nid in embeddings:
            for a, b in zip(embeddings[nid], loaded[nid]):
                assert a == pytest.approx(b)

    def test_save_creates_directories(self, tmp_path):
        G = _make_test_graph(10)
        embeddings = generate_simple_embeddings(G, seed=42)
        out_path = tmp_path / "deep" / "nested" / "embeddings.json"
        save_embeddings(embeddings, out_path)
        assert out_path.exists()


class TestQueryEmbedding:
    def test_deterministic(self):
        vec1 = get_query_embedding("hello world")
        vec2 = get_query_embedding("hello world")
        for a, b in zip(vec1, vec2):
            assert a == pytest.approx(b)

    def test_different_yields_different(self):
        vec1 = get_query_embedding("hello")
        vec2 = get_query_embedding("world")
        assert vec1 != vec2

    def test_custom_dimensions(self):
        vec = get_query_embedding("test", dimensions=64)
        assert len(vec) == 64

    def test_l2_normalized(self):
        vec = get_query_embedding("test")
        norm = math.sqrt(sum(v * v for v in vec))
        assert norm == pytest.approx(1.0, rel=1e-4)
