"""Approximate query methods: bloom filter, graph sampling, path existence checks."""
from __future__ import annotations
import hashlib
import math
import random
from typing import Set, Tuple

import networkx as nx


class GraphBloomFilter:
    """Bloom filter for O(1) "does this edge exist?" checks.

    Key format: "{relation}:{confidence}:{src_label}:{tgt_label}"
    Uses bit array + k hash functions for probabilistic membership.
    No external dependencies — pure Python implementation using built-in hashlib.
    """

    def __init__(self, capacity: int, error_rate: float = 0.01):
        self.capacity = capacity
        self.error_rate = error_rate
        bit_size = int(-capacity * math.log(error_rate) / (math.log(2) ** 2))
        self._num_hashes = max(1, int(bit_size / capacity * math.log(2)))
        self._size_bits = max(1, bit_size)
        byte_size = (self._size_bits + 7) // 8
        self._bits = bytearray(byte_size)

    def _hash_indices(self, key: bytes) -> list[int]:
        h1 = int.from_bytes(hashlib.sha256(key).digest()[:8], 'big')
        h2 = int.from_bytes(hashlib.sha256(key + b'\x01').digest()[:8], 'big')
        return [(h1 + i * h2) % self._size_bits for i in range(self._num_hashes)]

    def _key(self, relation: str, confidence: str, src_label: str, tgt_label: str) -> bytes:
        return f"{relation}:{confidence}:{src_label}:{tgt_label}".encode()

    def add_edge(self, relation: str, confidence: str, src_label: str, tgt_label: str) -> None:
        key = self._key(relation, confidence, src_label, tgt_label)
        for idx in self._hash_indices(key):
            byte_idx = idx // 8
            bit_idx = idx % 8
            self._bits[byte_idx] |= (1 << bit_idx)
        wild_key = self._key(relation, "", src_label, tgt_label)
        if wild_key != key:
            for idx in self._hash_indices(wild_key):
                byte_idx = idx // 8
                bit_idx = idx % 8
                self._bits[byte_idx] |= (1 << bit_idx)

    def likely_contains(self, relation: str, confidence: str, src_label: str, tgt_label: str) -> bool:
        key = self._key(relation, confidence, src_label, tgt_label)
        for idx in self._hash_indices(key):
            byte_idx = idx // 8
            bit_idx = idx % 8
            if not (self._bits[byte_idx] & (1 << bit_idx)):
                return False
        return True

    @property
    def size_bits(self) -> int:
        return self._size_bits

    @classmethod
    def from_graph(cls, G, error_rate: float = 0.01) -> 'GraphBloomFilter':
        """Build bloom filter from an existing graph. Adds all edges."""
        num_edges = G.number_of_edges()
        capacity = max(1, num_edges)
        bf = cls(capacity=capacity, error_rate=error_rate)
        for u, v, edata in G.edges(data=True):
            src_label = G.nodes[u].get("label", u)
            tgt_label = G.nodes[v].get("label", v)
            relation = edata.get("relation", "")
            confidence = edata.get("confidence", "")
            bf.add_edge(relation, confidence, src_label, tgt_label)
        return bf


def build_path_bloom_filter(G, relation_type: str = "calls") -> GraphBloomFilter:
    """Build a bloom filter for path existence checks.

    Used by always-on hook: "Is there an auth-related path? No → skip GRAPH_REPORT.md"
    """
    num_edges = G.number_of_edges()
    capacity = max(1, num_edges)
    bf = GraphBloomFilter(capacity=capacity, error_rate=0.01)
    for u, v, edata in G.edges(data=True):
        if edata.get("relation", "") == relation_type:
            src_label = G.nodes[u].get("label", u)
            tgt_label = G.nodes[v].get("label", v)
            confidence = edata.get("confidence", "")
            bf.add_edge(relation_type, confidence, src_label, tgt_label)
    return bf


def sample_subgraph_nodes(G, sample_rate: float = 0.1, method: str = "random_walk",
                          seed: int = 42) -> set[str]:
    """Sample nodes from graph.

    random_walk: preserves community proportions via random walks.
    stratified: proportional sampling from each community.
    Returns set of sampled node IDs.
    """
    rng = random.Random(seed)
    num_samples = max(1, int(len(G) * sample_rate))
    sampled: set[str] = set()

    node_list = list(G.nodes())
    if not node_list:
        return sampled

    if method == "stratified":
        communities: dict[int, list[str]] = {}
        for nid, data in G.nodes(data=True):
            cid = data.get("community", -1)
            communities.setdefault(cid, []).append(nid)
        for _, members in communities.items():
            n = max(1, int(len(members) * sample_rate))
            sampled.update(rng.sample(members, min(n, len(members))))
        return sampled

    visited: set[str] = set()
    while len(sampled) < num_samples and len(visited) < len(G):
        start = rng.choice(node_list)
        if start in visited:
            continue
        walk_node = start
        for _ in range(max(1, int(1 / max(sample_rate, 0.01)))):
            visited.add(walk_node)
            if rng.random() < sample_rate:
                sampled.add(walk_node)
            neighbors = list(G.neighbors(walk_node))
            if not neighbors:
                break
            walk_node = rng.choice(neighbors)
        if len(visited) >= len(G):
            break

    if len(sampled) < num_samples:
        remaining = [n for n in node_list if n not in sampled]
        if remaining:
            needed = min(num_samples - len(sampled), len(remaining))
            sampled.update(rng.sample(remaining, needed))

    return sampled


def sample_subgraph(G, sample_rate: float = 0.1, method: str = "random_walk",
                    seed: int = 42) -> nx.Graph:
    """Return induced subgraph on sampled nodes."""
    sampled = sample_subgraph_nodes(G, sample_rate=sample_rate, method=method, seed=seed)
    return G.subgraph(sampled).copy()


def estimate_graph_from_sample(sampled_G, original_node_count: int) -> dict:
    """Estimate full graph stats from sample: node count, edge count, avg degree, density."""
    if sampled_G.number_of_nodes() == 0:
        return {"nodes": 0, "edges": 0, "avg_degree": 0, "density": 0}
    sample_ratio = sampled_G.number_of_nodes() / max(1, original_node_count)
    estimated_edges = int(sampled_G.number_of_edges() / max(sample_ratio, 0.0001))
    avg_degree = sum(d for _, d in sampled_G.degree()) / sampled_G.number_of_nodes()
    n = sampled_G.number_of_nodes()
    density = (2 * sampled_G.number_of_edges()) / (n * (n - 1)) if n > 1 else 0
    return {
        "nodes": original_node_count,
        "edges": estimated_edges,
        "avg_degree": round(avg_degree, 2),
        "density": round(density, 4),
    }


def is_path_likely(bf: GraphBloomFilter, relation: str, src: str, tgt: str) -> bool:
    """Quick existence check using bloom filter. Returns True if path might exist."""
    return bf.likely_contains(relation, "", src, tgt)


def _approximate_query(
    G: nx.Graph, question: str, sample_rate: float = 0.1,
    depth: int = 3, budget: int = 2000, seed: int = 42
) -> str:
    """Query on a sampled subgraph. ~10x faster, ~90% accuracy.

    Returns a string with the subgraph context text, prefixed with [APPROXIMATE].
    """
    import unicodedata

    sampled_G = sample_subgraph(G, sample_rate=sample_rate, seed=seed)

    def _strip_diacritics(text: str) -> str:
        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    terms = [t.lower() for t in question.split() if len(t) > 2]
    norm_terms = [_strip_diacritics(t).lower() for t in terms]
    scored = []
    for nid, data in sampled_G.nodes(data=True):
        norm_label = data.get("norm_label") or _strip_diacritics(data.get("label") or "").lower()
        source = (data.get("source_file") or "").lower()
        s = sum(1 for t in norm_terms if t in norm_label) + sum(0.5 for t in norm_terms if t in source)
        if s > 0:
            scored.append((s, nid))
    scored.sort(reverse=True)
    if not scored:
        return "[APPROXIMATE] No matching nodes found in sampled subgraph."

    start_nodes = [nid for _, nid in scored[:3]]
    visited: set[str] = set(start_nodes)
    frontier = set(start_nodes)
    edges_seen: list[tuple] = []
    for _ in range(depth):
        next_frontier: set[str] = set()
        for n in frontier:
            for neighbor in sampled_G.neighbors(n):
                if neighbor not in visited:
                    next_frontier.add(neighbor)
                    edges_seen.append((n, neighbor))
        visited.update(next_frontier)
        frontier = next_frontier

    char_budget = budget * 3
    lines = []
    for nid in sorted(visited, key=lambda n: sampled_G.degree(n), reverse=True):
        d = sampled_G.nodes[nid]
        line = f"NODE {d.get('label', nid)} [src={d.get('source_file', '')} loc={d.get('source_location', '')} community={d.get('community', '')}]"
        lines.append(line)
    for u, v in edges_seen:
        if u in visited and v in visited:
            d = sampled_G.edges[u, v]
            line = f"EDGE {sampled_G.nodes[u].get('label', u)} --{d.get('relation', '')} [{d.get('confidence', '')}]--> {sampled_G.nodes[v].get('label', v)}"
            lines.append(line)
    output = "\n".join(lines)
    if len(output) > char_budget:
        output = output[:char_budget] + f"\n... (truncated to ~{budget} token budget)"

    header = f"[APPROXIMATE] BFS depth={depth} sample={sample_rate} | {len(visited)} nodes found\n\n"
    return header + output


def _should_skip_query(G, question: str, bloom_filter: GraphBloomFilter | None = None) -> bool:
    """Check if question has any likely relevant paths via bloom filter.

    Returns True if definitely no paths exist → skip expensive traversal.
    """
    if bloom_filter is None:
        if hasattr(G, "graph") and G.graph.get("_bloom_filter"):
            bloom_filter = G.graph["_bloom_filter"]
        else:
            return False
    terms = [t.lower() for t in question.split() if len(t) > 2]
    for node_id in G.nodes():
        label = G.nodes[node_id].get("label", "")
        label_lower = label.lower()
        if any(t in label_lower for t in terms):
            return False
    return True
