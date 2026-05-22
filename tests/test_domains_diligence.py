"""Tests for the due diligence domain plugin."""
from pathlib import Path

import networkx as nx
import pytest

from graphify.domain import active_domains, _DOMAINS


@pytest.fixture(autouse=True)
def _clear_registry():
    _DOMAINS.clear()
    yield
    _DOMAINS.clear()


def test_diligence_loads():
    domains = active_domains({"domains": ["diligence"]})
    assert len(domains) == 1
    d = domains[0]
    assert d.name == "diligence"
    assert "person" in d.node_types
    assert "governance" in d.relations
    assert "conflict" in d.relations


def test_diligence_prompt_fragments():
    domains = active_domains({"domains": ["diligence"]})
    prompt = domains[0].prompt_fragments()
    assert "officer" in prompt
    assert "related-party" in prompt
    assert "contradiction" in prompt


def test_post_extract_infer_conflicts():
    """Multi-role person triggers conflict_of_interest edge."""
    domains = active_domains({"domains": ["diligence"]})
    d = domains[0]
    extraction = {
        "nodes": [
            {"id": "adam", "label": "Adam", "type": "person"},
            {"id": "corp", "label": "Corp", "type": "entity"},
            {"id": "llc", "label": "LLC", "type": "entity"},
        ],
        "edges": [
            {"source": "adam", "target": "corp", "relation": "officer_of"},
            {"source": "adam", "target": "corp", "relation": "board_member_of"},
            {"source": "adam", "target": "llc", "relation": "asset_leaseback"},
        ],
    }
    result = d.post_extract(extraction)
    conflict_edges = [e for e in result["edges"] if e["relation"] == "conflict_of_interest"]
    assert len(conflict_edges) == 1
    assert conflict_edges[0]["source"] == "adam"
    assert conflict_edges[0]["confidence"] >= 0.7
    assert "officer_of" in conflict_edges[0]["metadata"]["roles"]
    assert "asset_leaseback" in conflict_edges[0]["metadata"]["roles"]


def test_post_extract_no_conflict_single_category():
    """Person with only internal roles does NOT trigger conflict."""
    domains = active_domains({"domains": ["diligence"]})
    d = domains[0]
    extraction = {
        "nodes": [{"id": "bob", "label": "Bob", "type": "person"}],
        "edges": [
            {"source": "bob", "target": "corp", "relation": "officer_of"},
            {"source": "bob", "target": "corp", "relation": "board_member_of"},
        ],
    }
    result = d.post_extract(extraction)
    conflict_edges = [e for e in result["edges"] if e.get("relation") == "conflict_of_interest"]
    assert len(conflict_edges) == 0


def test_post_extract_fix_mismatch():
    """asset_liability_mismatch edges with wrong endpoint types are dropped."""
    domains = active_domains({"domains": ["diligence"]})
    d = domains[0]
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "type": "person"},
            {"id": "b", "label": "B", "type": "person"},
            {"id": "c", "label": "C", "type": "obligation"},
            {"id": "d", "label": "D", "type": "asset"},
        ],
        "edges": [
            # Invalid: person→person
            {"source": "a", "target": "b", "relation": "asset_liability_mismatch"},
            # Valid: obligation→asset
            {"source": "c", "target": "d", "relation": "asset_liability_mismatch"},
        ],
    }
    result = d.post_extract(extraction)
    mismatch_edges = [e for e in result["edges"] if e["relation"] == "asset_liability_mismatch"]
    assert len(mismatch_edges) == 1
    assert mismatch_edges[0]["source"] == "c"


def test_post_build_contradictions():
    """post_build adds contradicted_by edges when claim and risk share keywords."""
    domains = active_domains({"domains": ["diligence"]})
    d = domains[0]

    G = nx.Graph()
    # Aspirational claim about profitability in community 0
    G.add_node("claim1", label="We will achieve profitability through growth",
               type="claim", domain="diligence", community=0)
    # Risk factor that negates profitability in community 1
    G.add_node("risk1", label="We may never achieve profitability due to growth costs",
               type="risk", domain="diligence", community=1)

    d.post_build(G)

    # Should have a contradicted_by edge (semantic overlap: "achieve", "profitability", "growth")
    edges = list(G.edges(data=True))
    contradiction_edges = [
        (u, v, d) for u, v, d in edges if d.get("relation") == "contradicted_by"
    ]
    assert len(contradiction_edges) == 1
    assert contradiction_edges[0][2]["inferred"] is True


def test_post_build_no_contradictions_same_community():
    """No contradicted_by edges within the same community."""
    domains = active_domains({"domains": ["diligence"]})
    d = domains[0]

    G = nx.Graph()
    G.add_node("claim1", label="We will achieve profitability", type="claim", domain="diligence", community=0)
    G.add_node("risk1", label="We may never achieve profitability", type="risk", domain="diligence", community=0)

    d.post_build(G)
    edges = [(u, v, d) for u, v, d in G.edges(data=True) if d.get("relation") == "contradicted_by"]
    assert len(edges) == 0


def test_red_flag_analyzer():
    """Red flag analyzer detects risk factors, related-party exposure, and key-person risk."""
    domains = active_domains({"domains": ["diligence"]})
    d = domains[0]
    analyzer = d.analyzers[0]  # red_flag_analyzer

    G = nx.Graph()
    # Risk factor edge
    G.add_node("company", label="ACME Corp", domain="diligence")
    G.add_node("risk1", label="Risk: Related Party Transactions", domain="diligence")
    G.add_edge("company", "risk1", relation="HAS_RISK_FACTOR")
    # Related party node
    G.add_node("rp1", label="Loans to Related Parties ($50M)", domain="diligence")
    # Key person (high degree with officer edge)
    G.add_node("ceo", label="CEO", type="person", domain="diligence")
    for i in range(6):
        G.add_node(f"entity_{i}", label=f"Entity {i}", type="entity", domain="diligence")
        G.add_edge("ceo", f"entity_{i}", relation="controls")

    flags = analyzer(G)
    types = [f["type"] for f in flags]
    assert "risk_factor" in types
    assert "related_party_exposure" in types
    assert "key_person_risk" in types


def test_extract_from_text_officer_loan_candidate(tmp_path, monkeypatch):
    """Officer loan in related-party context produces a candidate for agent resolution."""
    import json
    from graphify.domains.diligence import DiligenceExtractor
    monkeypatch.chdir(tmp_path)
    (tmp_path / "graphify-out").mkdir()
    ext = DiligenceExtractor()
    html = """<p>Related Party Transactions. In 2019, the Company made a
    promissory note to John Smith for $362.1 million secured by shares.</p>"""
    ext._extract_from_text(Path("test.htm"), html)
    cands = json.loads((tmp_path / "graphify-out/.aag_diligence_candidates.json").read_text())
    assert any(c["type"] == "officer_loan" and "362.1" in c["amount"] for c in cands)


def test_extract_from_text_ip_transfer_candidate(tmp_path, monkeypatch):
    """IP transfer from insider entity produces a candidate for agent resolution."""
    import json
    from graphify.domains.diligence import DiligenceExtractor
    monkeypatch.chdir(tmp_path)
    (tmp_path / "graphify-out").mkdir()
    ext = DiligenceExtractor()
    html = """<p>In July 2019, ABC Holdings LLC assigned residual rights related
    to trademarks to the Company for $5.9 million in partnership interests.</p>"""
    ext._extract_from_text(Path("test.htm"), html)
    cands = json.loads((tmp_path / "graphify-out/.aag_diligence_candidates.json").read_text())
    assert any(c["type"] == "ip_transfer" and "5.9" in c["amount"] for c in cands)


def test_resolve_candidates():
    """resolve_candidates converts agent output into graph nodes/edges."""
    from graphify.domains.diligence import DiligenceExtractor
    resolved = [
        {"type": "officer_loan", "amount": "$362.1 million", "person_or_entity": "Adam Neumann"},
        {"type": "ip_transfer", "amount": "$5.9 million", "person_or_entity": "WE Holdings LLC"},
        {"type": "officer_loan", "amount": "$100 million", "person_or_entity": None},  # not insider
    ]
    result = DiligenceExtractor.resolve_candidates(resolved, "filing.htm")
    assert len(result["nodes"]) == 2
    labels = [n["label"] for n in result["nodes"]]
    assert any("362.1" in l and "Adam Neumann" in l for l in labels)
    assert any("5.9" in l and "WE Holdings" in l for l in labels)


def test_extract_from_text_family_tie():
    """Text extraction finds family relationships."""
    from graphify.domains.diligence import DiligenceExtractor
    ext = DiligenceExtractor()
    html = """<p>John Smith is married to Jane Doe, who serves as Chief Brand Officer.</p>"""
    result = ext._extract_from_text(Path("test.htm"), html)
    labels = [n["label"] for n in result["nodes"]]
    assert any("Family Tie" in l for l in labels)


def test_extract_from_text_no_false_positives():
    """Regular business loans should not trigger officer loan detection."""
    from graphify.domains.diligence import DiligenceExtractor
    ext = DiligenceExtractor()
    html = """<p>The Company entered into a $6.0 billion credit facility
    with JPMorgan Chase Bank. The term loan has a maturity of 5 years.</p>"""
    result = ext._extract_from_text(Path("test.htm"), html)
    assert len(result["nodes"]) == 0
