"""Tests for the domain plugin system."""
import networkx as nx
import pytest

from graphify.domain import DomainSpec, active_domains, register, _DOMAINS


@pytest.fixture(autouse=True)
def _clear_registry():
    """Reset global registry between tests."""
    _DOMAINS.clear()
    yield
    _DOMAINS.clear()


def test_register_and_discover():
    spec = DomainSpec(name="test_domain", node_types=["widget"])
    register(spec)
    result = active_domains({"domains": ["test_domain"]})
    assert len(result) == 1
    assert result[0].name == "test_domain"


def test_active_domains_no_config():
    register(DomainSpec(name="foo"))
    assert active_domains(None) == []
    assert active_domains({}) == []


def test_active_domains_missing_domain():
    register(DomainSpec(name="foo"))
    result = active_domains({"domains": ["bar"]})
    assert result == []


def test_active_domains_subset():
    register(DomainSpec(name="a"))
    register(DomainSpec(name="b"))
    register(DomainSpec(name="c"))
    result = active_domains({"domains": ["a", "c"]})
    assert [d.name for d in result] == ["a", "c"]


def test_builtin_domains_load():
    """Built-in finance and diligence domains auto-register."""
    result = active_domains({"domains": ["finance", "diligence"]})
    assert len(result) == 2
    assert result[0].name == "finance"
    assert result[1].name == "diligence"


def test_domain_spec_hooks():
    """DomainSpec with all hooks populated."""
    spec = DomainSpec(
        name="full",
        prompt_fragments=lambda: "extra prompt",
        post_extract=lambda d: d,
        post_build=lambda g: None,
        analyzers=[lambda g: []],
    )
    register(spec)
    d = active_domains({"domains": ["full"]})[0]
    assert d.prompt_fragments() == "extra prompt"
    assert d.post_extract({"nodes": [], "edges": []}) == {"nodes": [], "edges": []}
    assert d.post_build(nx.Graph()) is None
    assert d.analyzers[0](nx.Graph()) == []
