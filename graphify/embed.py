"""Node embedding generation. Requires: numpy (optional dependency)."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import networkx as nx

EMBEDDING_DIM = 128


def _import_numpy() -> Any:
    """Lazy import — embeddings are optional."""
    import numpy as np
    return np


def generate_simple_embeddings(G: nx.Graph, dimensions: int = EMBEDDING_DIM, seed: int = 42) -> dict[str, list[float]]:
    """Generate node embeddings using a deterministic random projection approach.

    No heavy ML deps needed. Each node gets a random vector seeded by its label/content hash.
    For production use, swap in node2vec/SDNE when numpy+scipy are available.
    """
    np = _import_numpy()
    embeddings: dict[str, list[float]] = {}
    for node_id, data in G.nodes(data=True):
        label = data.get("label", node_id)
        content_hash = hashlib.sha256(label.encode()).digest()
        node_seed = int.from_bytes(content_hash[:4], 'big')
        rng = np.random.RandomState(node_seed)
        vec = rng.randn(dimensions)
        vec = vec / (np.linalg.norm(vec) + 1e-8)
        embeddings[node_id] = vec.tolist()
    return embeddings


def compute_cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors (pure Python for portability)."""
    if len(vec1) != len(vec2):
        raise ValueError(f"Vector dimension mismatch: {len(vec1)} vs {len(vec2)}")
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def search_similar_nodes(query_vec: list[float], embeddings: dict[str, list[float]],
                          top_k: int = 10) -> list[tuple[str, float]]:
    """Return top-k most similar nodes by cosine similarity to query vector."""
    scored = []
    for node_id, emb in embeddings.items():
        sim = compute_cosine_similarity(query_vec, emb)
        scored.append((node_id, sim))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def save_embeddings(embeddings: dict[str, list[float]], output_path: Path) -> None:
    """Save embeddings as JSON. Keys are node IDs, values are float lists."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(embeddings, indent=2), encoding="utf-8")


def load_embeddings(input_path: Path) -> dict:
    """Load embeddings from JSON file."""
    data = json.loads(input_path.read_text(encoding="utf-8"))
    result: dict = {}
    for k, v in data.items():
        try:
            key = int(k)
        except (ValueError, TypeError):
            key = k
        result[key] = v
    return result


def get_query_embedding(query_text: str, dimensions: int = EMBEDDING_DIM) -> list[float]:
    """Generate a query embedding from text using the same deterministic approach."""
    np = _import_numpy()
    content_hash = hashlib.sha256(query_text.encode()).digest()
    seed_val = int.from_bytes(content_hash[:4], 'big')
    rng = np.random.RandomState(seed_val)
    vec = rng.randn(dimensions)
    norm = float(np.linalg.norm(vec)) + 1e-8
    return (vec / norm).tolist()
