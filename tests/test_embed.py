import networkx as nx
from pathlib import Path
from graphify.embed import embed_graph

def test_similar_nodes_get_connected(tmp_path):
    G = nx.Graph()
    G.add_node("a", label="authentication login user session")
    G.add_node("b", label="user login auth session token")
    G.add_node("c", label="database query sql table schema")

    cache_path = tmp_path / "embeddings.json"
    added = embed_graph(G, cache_path, threshold=0.75)

    assert added >= 1
    assert G.has_edge("a", "b")
    assert not G.has_edge("a", "c")

def test_cache_is_created(tmp_path):
    G = nx.Graph()
    G.add_node("x", label="neural network deep learning")
    G.add_node("y", label="machine learning model training")

    cache_path = tmp_path / "embeddings.json"
    embed_graph(G, cache_path, threshold=0.99)

    assert cache_path.exists()

def test_no_duplicate_edges(tmp_path):
    G = nx.Graph()
    G.add_node("a", label="authentication login user")
    G.add_node("b", label="user login auth session")

    cache_path = tmp_path / "embeddings.json"
    embed_graph(G, cache_path, threshold=0.75)
    embed_graph(G, cache_path, threshold=0.75)  # run twice

    assert G.number_of_edges("a", "b") <= 1