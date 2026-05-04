# Embedding support for semantic similarity queries (v3 roadmap)
#
# This module provides the interface and base implementation for
# embedding-based node similarity. The default implementation is a
# no-op stub; install an embedding backend to enable it.
#
# Planned backends:
#   - Local: quantized Gemma 4 via llama.cpp (v0.4.0)
#   - API: Claude embeddings, OpenAI embeddings
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Protocol
import networkx as nx


class EmbeddingBackend(ABC):
    """Abstract base class for embedding backends."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of float vectors."""
        ...

    @abstractmethod
    def dimension(self) -> int:
        """Return the dimensionality of the embedding vectors."""
        ...


class NoOpBackend(EmbeddingBackend):
    """Stub backend when no embedding library is installed."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return []

    def dimension(self) -> int:
        return 0


def get_backend(name: str = "auto") -> EmbeddingBackend:
    """Get an embedding backend by name.

    Args:
        name: Backend name. "auto" tries to find an installed backend.
              Currently returns NoOpBackend since no backends are implemented yet.

    Returns:
        An EmbeddingBackend instance.
    """
    # Future: detect installed backends and return the best available
    return NoOpBackend()


def embed_graph_nodes(G: nx.Graph | nx.DiGraph, backend: EmbeddingBackend | None = None) -> dict[str, list[float]]:
    """Compute embeddings for all node labels in the graph.

    Args:
        G: The knowledge graph.
        backend: Embedding backend to use. If None, uses auto-detection.

    Returns:
        Dict mapping node IDs to their embedding vectors.
        Empty dict if no backend is available.
    """
    if backend is None:
        backend = get_backend()

    if isinstance(backend, NoOpBackend):
        return {}

    node_ids = list(G.nodes())
    texts = [G.nodes[n].get("label", n) for n in node_ids]
    vectors = backend.embed(texts)

    if not vectors:
        return {}

    return dict(zip(node_ids, vectors))


def find_similar(
    embeddings: dict[str, list[float]],
    query_id: str,
    top_k: int = 5,
) -> list[tuple[str, float]]:
    """Find the most similar nodes to a given node by cosine similarity.

    Args:
        embeddings: Dict mapping node IDs to embedding vectors.
        query_id: The node ID to find similar nodes for.
        top_k: Number of results to return.

    Returns:
        List of (node_id, similarity_score) tuples, sorted by similarity descending.
    """
    if query_id not in embeddings or not embeddings:
        return []

    query_vec = embeddings[query_id]

    def _cosine_sim(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    scores = []
    for nid, vec in embeddings.items():
        if nid == query_id:
            continue
        scores.append((nid, _cosine_sim(query_vec, vec)))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_k]
