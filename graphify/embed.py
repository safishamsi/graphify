from __future__ import annotations
import json
import hashlib
from pathlib import Path
import numpy as np

_model = None

def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model

def _node_text(node: dict) -> str:
    parts = [node.get("label", node.get("id", ""))]
    if node.get("docstring"):
        parts.append(node["docstring"])
    return " ".join(parts).strip()

def _cache_key(node: dict) -> str:
    return hashlib.sha256(_node_text(node).encode()).hexdigest()

def load_embedding_cache(cache_path: Path) -> dict:
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    return {}

def save_embedding_cache(cache: dict, cache_path: Path):
    cache_path.write_text(json.dumps(cache))

def embed_graph(G, cache_path: Path, threshold: float = 0.82) -> int:
    cache = load_embedding_cache(cache_path)
    model = _get_model()

    nodes = list(G.nodes(data=True))
    node_ids = [n[0] for n in nodes]
    keys = [_cache_key(n[1]) for n in nodes]
    texts = [_node_text(n[1]) for n in nodes]

    to_embed_idx = [i for i, k in enumerate(keys) if k not in cache]
    if to_embed_idx:
        new_vecs = model.encode(
            [texts[i] for i in to_embed_idx],
            normalize_embeddings=True
        )
        for i, vec in zip(to_embed_idx, new_vecs):
            cache[keys[i]] = vec.tolist()
        save_embedding_cache(cache, cache_path)

    vecs = np.array([cache[k] for k in keys], dtype=np.float32)
    sim_matrix = vecs @ vecs.T

    edges_added = 0
    for i in range(len(node_ids)):
        for j in range(i + 1, len(node_ids)):
            score = float(sim_matrix[i, j])
            if score >= threshold and not G.has_edge(node_ids[i], node_ids[j]):
                G.add_edge(
                    node_ids[i], node_ids[j],
                    relation="semantically_similar_to",
                    confidence="INFERRED",
                    confidence_score=round(score, 4),
                    provenance="embeddings"
                )
                edges_added += 1

    return edges_added