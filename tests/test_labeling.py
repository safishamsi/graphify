"""Tests for LLM-backed community labeling (issue #1097).

Backend calls are mocked - no network. Covers the happy path, partial replies,
malformed replies, and the no-backend fallback.
"""
import networkx as nx
import pytest

from graphify.llm import label_communities, generate_community_labels


def _graph():
    G = nx.Graph()
    # community 0 = ordering, community 1 = payments
    G.add_node("order_place", label="place_order")
    G.add_node("order_repo", label="OrderRepository")
    G.add_node("pay_charge", label="charge_card")
    G.add_node("pay_stripe", label="StripeClient")
    communities = {0: ["order_place", "order_repo"], 1: ["pay_charge", "pay_stripe"]}
    return G, communities


def test_label_communities_happy_path(monkeypatch):
    G, communities = _graph()

    captured = {}

    def fake_call(prompt, *, backend, max_tokens=200):
        captured["prompt"] = prompt
        captured["backend"] = backend
        return '{"0": "Order Management", "1": "Payment Flow"}'

    monkeypatch.setattr("graphify.llm._call_llm", fake_call)
    labels = label_communities(G, communities, backend="gemini")

    assert labels == {0: "Order Management", 1: "Payment Flow"}
    # the prompt must carry the real node labels so the model can name them
    assert "place_order" in captured["prompt"]
    assert "StripeClient" in captured["prompt"]
    assert captured["backend"] == "gemini"


def test_label_communities_partial_reply_fills_placeholder(monkeypatch):
    G, communities = _graph()
    monkeypatch.setattr("graphify.llm._call_llm",
                        lambda p, *, backend, max_tokens=200: '{"0": "Order Management"}')
    labels = label_communities(G, communities, backend="gemini")
    assert labels[0] == "Order Management"
    assert labels[1] == "Community 1"   # missing cid falls back


def test_label_communities_strips_code_fences(monkeypatch):
    G, communities = _graph()
    monkeypatch.setattr(
        "graphify.llm._call_llm",
        lambda p, *, backend, max_tokens=200: '```json\n{"0":"Orders","1":"Pay"}\n```',
    )
    labels = label_communities(G, communities, backend="gemini")
    assert labels == {0: "Orders", 1: "Pay"}


def test_label_communities_malformed_raises(monkeypatch):
    G, communities = _graph()
    monkeypatch.setattr("graphify.llm._call_llm",
                        lambda p, *, backend, max_tokens=200: "sorry, I cannot help")
    with pytest.raises(Exception):
        label_communities(G, communities, backend="gemini")


def test_generate_community_labels_degrades_on_error(monkeypatch):
    G, communities = _graph()
    monkeypatch.setattr("graphify.llm._call_llm",
                        lambda p, *, backend, max_tokens=200: "not json")
    labels, source = generate_community_labels(G, communities, backend="gemini", quiet=True)
    assert source == "placeholder"
    assert labels == {0: "Community 0", 1: "Community 1"}


def test_generate_community_labels_no_backend(monkeypatch):
    G, communities = _graph()
    monkeypatch.setattr("graphify.llm.detect_backend", lambda: None)
    labels, source = generate_community_labels(G, communities, backend=None, quiet=True)
    assert source == "placeholder"
    assert labels == {0: "Community 0", 1: "Community 1"}


def test_generate_community_labels_success(monkeypatch):
    G, communities = _graph()
    monkeypatch.setattr("graphify.llm._call_llm",
                        lambda p, *, backend, max_tokens=200: '{"0":"Orders","1":"Payments"}')
    labels, source = generate_community_labels(G, communities, backend="gemini", quiet=True)
    assert source == "llm"
    assert labels == {0: "Orders", 1: "Payments"}


def test_gods_as_dicts_do_not_crash(monkeypatch):
    """god_nodes() returns list[dict] with an 'id' key, not bare ids."""
    G, communities = _graph()
    monkeypatch.setattr("graphify.llm._call_llm",
                        lambda p, *, backend, max_tokens=200: '{"0":"Orders","1":"Pay"}')
    gods = [{"id": "order_repo", "label": "OrderRepository"}]
    labels = label_communities(G, communities, backend="gemini", gods=gods)
    assert labels == {0: "Orders", 1: "Pay"}


def test_empty_communities_returns_placeholders(monkeypatch):
    G = nx.Graph()
    called = False

    def fake_call(p, *, backend, max_tokens=200):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr("graphify.llm._call_llm", fake_call)
    # community with no resolvable nodes -> no prompt line -> no backend call
    labels = label_communities(G, {0: []}, backend="gemini")
    assert labels == {0: "Community 0"}
    assert called is False
