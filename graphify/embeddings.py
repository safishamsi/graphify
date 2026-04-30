# Vector embeddings for semantic node search.
# Optional dependency: sentence-transformers (auto-detected).
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np


_DEFAULT_MODEL = "all-MiniLM-L6-v2"


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class EmbeddingIndex:
    """Lightweight embedding index for semantic graph search.

    Uses sentence-transformers if available; falls back to TF-IDF-like
    bag-of-words vectors for zero-dependency operation.
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model: Any | None = None
        self._embeddings: dict[str, np.ndarray] = {}
        self._labels: dict[str, str] = {}
        # Persisted only on the BoW fallback path so search queries can
        # be encoded against the same vocabulary as the indexed labels.
        # Without this, query vectors had a different dim than indexed
        # vectors and cosine similarity raised a shape error.
        self._bow_vocab: dict[str, int] | None = None

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            return self._model
        except ImportError:
            return None

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return text.lower().replace("_", " ").replace("-", " ").split()

    def _vectorize_corpus(self, texts: list[str]) -> np.ndarray:
        """Encode the indexed labels. On the BoW path, also build vocab."""
        model = self._load_model()
        if model is not None:
            return model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

        vocab: dict[str, int] = {}
        tokenized: list[list[str]] = []
        for text in texts:
            tokens = self._tokenize(text)
            tokenized.append(tokens)
            for t in tokens:
                if t not in vocab:
                    vocab[t] = len(vocab)
        self._bow_vocab = vocab
        return self._bow_encode(tokenized, vocab)

    def _vectorize_query(self, text: str) -> np.ndarray:
        """Encode a single query. On BoW, projects onto the build-time vocab."""
        model = self._load_model()
        if model is not None:
            return model.encode([text], convert_to_numpy=True, show_progress_bar=False)[0]

        vocab = self._bow_vocab or {}
        if not vocab:
            return np.zeros(1, dtype=np.float32)
        vec = np.zeros(len(vocab), dtype=np.float32)
        for t in self._tokenize(text):
            idx = vocab.get(t)
            if idx is not None:
                vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    @staticmethod
    def _bow_encode(tokenized: list[list[str]], vocab: dict[str, int]) -> np.ndarray:
        dim = len(vocab) or 1
        mat = np.zeros((len(tokenized), dim), dtype=np.float32)
        for i, tokens in enumerate(tokenized):
            for t in tokens:
                mat[i, vocab[t]] += 1.0
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return mat / norms

    def build(self, G: nx.Graph) -> "EmbeddingIndex":
        """Compute embeddings for all nodes in the graph."""
        self._embeddings.clear()
        self._labels.clear()
        self._bow_vocab = None
        items: list[tuple[str, str]] = []
        for nid, data in G.nodes(data=True):
            label = data.get("label", nid)
            if label:
                items.append((nid, label))

        if not items:
            return self

        nids, labels = zip(*items)
        vectors = self._vectorize_corpus(list(labels))
        for nid, vec in zip(nids, vectors):
            self._embeddings[nid] = vec
            self._labels[nid] = G.nodes[nid].get("label", nid)
        return self

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Return the top-k node IDs most semantically similar to the query.

        On the bag-of-words fallback, a query whose tokens don't appear
        in any indexed label produces a zero vector — every node would
        score 0.0 and the top-k slice would surface arbitrary nodes that
        look like matches. Return an empty list in that case rather than
        fabricated hits, and skip non-positive similarities.
        """
        if not self._embeddings:
            return []
        query_vec = self._vectorize_query(query)
        if float(np.linalg.norm(query_vec)) == 0.0:
            return []
        scores = []
        for nid, vec in self._embeddings.items():
            sim = _cosine_similarity(query_vec, vec)
            if sim <= 0.0:
                continue
            scores.append((nid, sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def save(self, path: str | Path) -> None:
        """Serialize embeddings to a JSON file."""
        on_bow = self._load_model() is None
        data = {
            "model": "fallback-bow" if on_bow else self.model_name,
            "embeddings": {
                nid: vec.tolist()
                for nid, vec in self._embeddings.items()
            },
            "labels": self._labels,
            "bow_vocab": self._bow_vocab if on_bow else None,
        }
        Path(path).write_text(json.dumps(data), encoding="utf-8")

    def load(self, path: str | Path) -> "EmbeddingIndex":
        """Load embeddings from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.model_name = data.get("model", _DEFAULT_MODEL)
        self._embeddings = {
            nid: np.array(vec, dtype=np.float32)
            for nid, vec in data["embeddings"].items()
        }
        self._labels = data.get("labels", {})
        vocab = data.get("bow_vocab")
        self._bow_vocab = dict(vocab) if vocab else None
        return self


def search_nodes(G: nx.Graph, query: str, top_k: int = 10) -> list[dict]:
    """Convenience function: build index, search, return node data."""
    idx = EmbeddingIndex().build(G)
    results = idx.search(query, top_k=top_k)
    return [
        {"id": nid, "score": round(score, 4), **G.nodes[nid]}
        for nid, score in results
    ]
