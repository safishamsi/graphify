import json
from pathlib import Path

import networkx as nx
import pytest

from graphify.dashboard import create_app, _load_graph


@pytest.fixture
def sample_graph(tmp_path):
    G = nx.Graph()
    G.add_node("a", label="Alpha", file_type="code", community=0)
    G.add_node("b", label="Beta", file_type="code", community=1)
    G.add_edge("a", "b", relation="uses", confidence="EXTRACTED")

    data = {
        "nodes": [{"id": n, **d} for n, d in G.nodes(data=True)],
        "links": [{"source": u, "target": v, **d} for u, v, d in G.edges(data=True)],
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_dashboard_index(sample_graph):
    app = create_app(sample_graph)
    from fastapi.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "graphify dashboard" in resp.text


def test_dashboard_api_graph(sample_graph):
    app = create_app(sample_graph)
    from fastapi.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/api/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1


def test_dashboard_api_node(sample_graph):
    app = create_app(sample_graph)
    from fastapi.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/api/node/a")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "a"
    assert data["label"] == "Alpha"


def test_dashboard_api_communities(sample_graph):
    app = create_app(sample_graph)
    from fastapi.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/api/communities")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


def test_dashboard_api_cypher(sample_graph):
    app = create_app(sample_graph)
    from fastapi.testclient import TestClient
    client = TestClient(app)
    resp = client.post("/api/cypher", json={"query": "MATCH (n) RETURN n.label"})
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert len(data["results"]) == 2


def test_dashboard_search_caches_embedding_index(sample_graph, monkeypatch):
    # /api/search must reuse a cached index across requests, not rebuild
    # it per call (rebuilding reloads the sentence-transformers model
    # every time on real graphs).
    from graphify import embeddings as embeddings_mod
    build_calls = {"n": 0}
    real_build = embeddings_mod.EmbeddingIndex.build

    def counting_build(self, G):
        build_calls["n"] += 1
        return real_build(self, G)

    monkeypatch.setattr(embeddings_mod.EmbeddingIndex, "build", counting_build)

    app = create_app(sample_graph)
    from fastapi.testclient import TestClient
    client = TestClient(app)
    for _ in range(3):
        resp = client.get("/api/search", params={"q": "Alpha"})
        assert resp.status_code == 200
    assert build_calls["n"] == 1


def test_dashboard_api_node_missing_returns_404(sample_graph):
    app = create_app(sample_graph)
    from fastapi.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/api/node/does-not-exist")
    assert resp.status_code == 404
