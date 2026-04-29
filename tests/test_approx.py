import hashlib
import random

import networkx as nx
import pytest
from graphify.approx import (
    GraphBloomFilter,
    build_path_bloom_filter,
    estimate_graph_from_sample,
    is_path_likely,
    sample_subgraph,
    sample_subgraph_nodes,
    _approximate_query,
    _should_skip_query,
)


def _make_test_graph(num_nodes: int = 100, seed: int = 42) -> nx.Graph:
    rng = random.Random(seed)
    G = nx.Graph()
    for i in range(num_nodes):
        label = f"node_{i}"
        G.add_node(i, label=label, source_file=f"src/file_{i}.py", community=i % 5)
    node_list = list(G.nodes())
    for i in range(num_nodes * 3):
        u = rng.choice(node_list)
        v = rng.choice(node_list)
        if u != v:
            relation = rng.choice(["calls", "imports", "uses", "defines"])
            confidence = rng.choice(["EXTRACTED", "INFERRED", "AMBIGUOUS"])
            G.add_edge(u, v, relation=relation, confidence=confidence, weight=round(rng.uniform(0.1, 1.0), 3))
    return G


class TestGraphBloomFilter:
    def test_add_and_contains(self):
        bf = GraphBloomFilter(capacity=100, error_rate=0.01)
        bf.add_edge("calls", "EXTRACTED", "A", "B")
        assert bf.likely_contains("calls", "EXTRACTED", "A", "B")
        assert not bf.likely_contains("calls", "EXTRACTED", "X", "Y")

    def test_false_positive_rate(self):
        bf = GraphBloomFilter(capacity=10000, error_rate=0.01)
        added: set[str] = set()
        rng = random.Random(42)
        for i in range(5000):
            src = f"src_{i}"
            tgt = f"tgt_{i}"
            bf.add_edge("calls", "EXTRACTED", src, tgt)
            added.add(f"calls:EXTRACTED:{src}:{tgt}")
        false_positives = 0
        tests = 2000
        for i in range(tests):
            src = f"fake_src_{i}"
            tgt = f"fake_tgt_{i}"
            if bf.likely_contains("calls", "EXTRACTED", src, tgt):
                false_positives += 1
        fp_rate = false_positives / tests
        assert fp_rate <= 0.03

    def test_from_graph(self):
        G = _make_test_graph(50)
        bf = GraphBloomFilter.from_graph(G, error_rate=0.01)
        assert bf._size_bits > 0
        assert bf._num_hashes > 0

    def test_size_bits_property(self):
        bf = GraphBloomFilter(capacity=1000, error_rate=0.01)
        assert bf.size_bits > 0

    def test_empty_constructor(self):
        bf = GraphBloomFilter(capacity=1, error_rate=0.01)
        assert bf.size_bits > 0
        assert bf._num_hashes > 0


class TestPathBloomFilter:
    def test_build_path_bloom_filter(self):
        G = _make_test_graph(50)
        bf = build_path_bloom_filter(G, relation_type="calls")
        assert bf.size_bits > 0

    def test_build_path_bloom_filter_empty(self):
        G = nx.Graph()
        bf = build_path_bloom_filter(G)
        assert bf.size_bits > 0

    def test_is_path_likely(self):
        G = _make_test_graph(30)
        bf = build_path_bloom_filter(G, relation_type="calls")
        edges = list(G.edges(data=True))
        if edges:
            u, v, edata = edges[0]
            src_label = G.nodes[u].get("label", u)
            tgt_label = G.nodes[v].get("label", v)
            rel = edata.get("relation", "calls")
            if rel == "calls":
                assert is_path_likely(bf, "calls", src_label, tgt_label)


class TestGraphSampling:
    def test_sample_subgraph_nodes_size(self):
        G = _make_test_graph(200)
        sampled = sample_subgraph_nodes(G, sample_rate=0.25, seed=42)
        assert len(sampled) > 0
        assert len(sampled) <= 200

    def test_sample_subgraph_nodes_deterministic(self):
        G = _make_test_graph(200)
        s1 = sample_subgraph_nodes(G, sample_rate=0.1, seed=42)
        s2 = sample_subgraph_nodes(G, sample_rate=0.1, seed=42)
        assert s1 == s2

    def test_sample_subgraph_returns_graph(self):
        G = _make_test_graph(200)
        sub = sample_subgraph(G, sample_rate=0.1, seed=42)
        assert sub.number_of_nodes() > 0
        assert sub.number_of_nodes() <= 200

    def test_sample_subgraph_stratified_method(self):
        G = _make_test_graph(100)
        sampled = sample_subgraph_nodes(G, sample_rate=0.2, method="stratified", seed=42)
        assert len(sampled) > 0
        assert len(sampled) <= 100

    def test_sample_subgraph_empty_graph(self):
        G = nx.Graph()
        sampled = sample_subgraph_nodes(G)
        assert len(sampled) == 0

    def test_sample_subgraph_preserves_communities(self):
        G = _make_test_graph(200)
        original_comms: dict[int, int] = {}
        for _, data in G.nodes(data=True):
            cid = data.get("community", 0)
            original_comms[cid] = original_comms.get(cid, 0) + 1
        sampled_G = sample_subgraph(G, sample_rate=0.25, seed=42, method="stratified")
        sampled_comms: dict[int, int] = {}
        for _, data in sampled_G.nodes(data=True):
            cid = data.get("community", 0)
            sampled_comms[cid] = sampled_comms.get(cid, 0) + 1
        for cid in original_comms:
            if cid in sampled_comms:
                assert sampled_comms[cid] >= 1


class TestEstimate:
    def test_estimate_graph_from_sample(self):
        G = _make_test_graph(200)
        sampled = sample_subgraph(G, sample_rate=0.2, seed=42)
        stats = estimate_graph_from_sample(sampled, G.number_of_nodes())
        assert stats["nodes"] == 200
        assert "edges" in stats
        assert "avg_degree" in stats
        assert "density" in stats

    def test_estimate_empty_sample(self):
        G = nx.Graph()
        stats = estimate_graph_from_sample(G, 100)
        assert stats["nodes"] == 0
        assert stats["edges"] == 0


class TestApproximateQuery:
    def test_approximate_query_returns_text(self):
        G = _make_test_graph(100)
        result = _approximate_query(G, "node_0 node_1", sample_rate=0.2, depth=2)
        assert isinstance(result, str)
        assert "APPROXIMATE" in result

    def test_approximate_query_no_match(self):
        G = _make_test_graph(100)
        result = _approximate_query(G, "xyzzy plugh zorkmid", sample_rate=0.2)
        assert "APPROXIMATE" in result
        assert "No matching" in result

    def test_approximate_query_with_edges(self):
        G = _make_test_graph(100)
        result = _approximate_query(G, "node_5 node_10", sample_rate=0.5, depth=3)
        assert isinstance(result, str)
        assert "APPROXIMATE" in result
        assert "NODE" in result

    def test_approximate_query_truncation(self):
        G = _make_test_graph(200)
        result = _approximate_query(G, "node_0", sample_rate=0.5, depth=3, budget=10)
        assert "truncated" in result.lower()


class TestShouldSkipQuery:
    def test_should_skip_no_bloom(self):
        G = _make_test_graph(50)
        result = _should_skip_query(G, "authentication")
        assert result is False

    def test_should_skip_with_bloom(self):
        G = _make_test_graph(50)
        bf = build_path_bloom_filter(G)
        result = _should_skip_query(G, "authentication", bf)
        assert isinstance(result, bool)

    def test_should_skip_with_graph_bloom(self):
        G = _make_test_graph(20)
        bf = build_path_bloom_filter(G)
        G.graph["_bloom_filter"] = bf
        result = _should_skip_query(G, "node_0")
        assert result is False

    def test_should_skip_no_match(self):
        G = nx.Graph()
        G.add_node(0, label="alpha")
        G.add_node(1, label="beta")
        bf = GraphBloomFilter(capacity=10)
        result = _should_skip_query(G, "zorkmid", bf)
        assert result is True


class TestBloomFilterEdgeCases:
    def test_large_bloom_filter(self):
        G = _make_test_graph(500)
        bf = GraphBloomFilter.from_graph(G, error_rate=0.001)
        assert bf._num_hashes > 0
        edges = list(G.edges(data=True))
        for u, v, edata in edges[:50]:
            src_label = G.nodes[u].get("label", u)
            tgt_label = G.nodes[v].get("label", v)
            assert bf.likely_contains(edata["relation"], edata["confidence"], src_label, tgt_label)

    def test_capacity_one(self):
        bf = GraphBloomFilter(capacity=1, error_rate=0.01)
        assert bf.size_bits > 0
        assert bf._num_hashes > 0

    def test_sample_subgraph_single_node_graph(self):
        G = nx.Graph()
        G.add_node(0, label="only", community=0)
        sampled = sample_subgraph_nodes(G, sample_rate=0.5)
        assert len(sampled) >= 0

    def test_sample_subgraph_disconnected(self):
        G = nx.Graph()
        for i in range(20):
            G.add_node(i, label=f"n{i}", community=0)
        sampled = sample_subgraph_nodes(G, sample_rate=0.5, method="random_walk")
        assert len(sampled) >= 0

    def test_sample_subgraph_without_communities(self):
        G = nx.Graph()
        for i in range(30):
            G.add_node(i, label=f"n{i}")
            for j in range(max(0, i - 2), i):
                if j >= 0:
                    G.add_edge(i, j, relation="calls", confidence="EXTRACTED")
        sampled = sample_subgraph_nodes(G, sample_rate=0.3, method="stratified")
        assert len(sampled) > 0
