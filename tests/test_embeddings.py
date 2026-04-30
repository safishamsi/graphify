import networkx as nx
import numpy as np
import pytest

from graphify.embeddings import EmbeddingIndex, search_nodes


def test_embedding_index_builds():
    G = nx.Graph()
    G.add_node("a", label="HTTP client")
    G.add_node("b", label="Database connection")
    G.add_node("c", label="File parser")

    idx = EmbeddingIndex().build(G)
    assert len(idx._embeddings) == 3


def test_embedding_search():
    G = nx.Graph()
    G.add_node("a", label="HTTP client")
    G.add_node("b", label="Database connection")
    G.add_node("c", label="File parser")

    idx = EmbeddingIndex().build(G)
    results = idx.search("network request", top_k=2)
    assert len(results) == 2
    # HTTP client should be most relevant
    ids = [r[0] for r in results]
    assert "a" in ids


def test_embedding_save_load(tmp_path):
    G = nx.Graph()
    G.add_node("a", label="HTTP client")

    idx = EmbeddingIndex().build(G)
    path = tmp_path / "embeddings.json"
    idx.save(path)

    idx2 = EmbeddingIndex().load(path)
    assert len(idx2._embeddings) == 1
    assert np.allclose(idx._embeddings["a"], idx2._embeddings["a"])


def test_search_nodes_convenience():
    G = nx.Graph()
    G.add_node("a", label="HTTP client")
    G.add_node("b", label="Database connection")

    results = search_nodes(G, "web request", top_k=1)
    assert len(results) == 1
    assert results[0]["id"] == "a"


def test_search_returns_empty_when_query_has_no_token_overlap():
    # BoW fallback builds vocab from indexed labels only. A query with
    # zero overlap must not surface arbitrary top-k nodes with score=0.
    G = nx.Graph()
    G.add_node("a", label="HTTP client")
    G.add_node("b", label="Database connection")

    idx = EmbeddingIndex()
    # Force the BoW path regardless of whether sentence-transformers is
    # installed in this environment.
    idx._model = None
    idx._load_model = lambda: None  # type: ignore[method-assign]
    idx.build(G)

    results = idx.search("xyzzy_unknown_token", top_k=5)
    assert results == []
