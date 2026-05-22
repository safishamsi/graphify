"""Tests for the finance domain plugin."""
from pathlib import Path

import pytest

from graphify.domain import active_domains, _DOMAINS


@pytest.fixture(autouse=True)
def _clear_registry():
    _DOMAINS.clear()
    yield
    _DOMAINS.clear()


def test_finance_loads():
    domains = active_domains({"domains": ["finance"]})
    assert len(domains) == 1
    d = domains[0]
    assert d.name == "finance"
    assert "company" in d.node_types
    assert "obligation" in d.relations


def test_finance_extracts_html_table(tmp_path):
    html_file = tmp_path / "filing.html"
    html_file.write_text("""<table>
    <tr><th>Counterparty</th><th>Exposure</th><th>Maturity</th></tr>
    <tr><td>JPMorgan</td><td>$450,000</td><td>2025</td></tr>
    <tr><td>Goldman Sachs</td><td>$380,000</td><td>2026</td></tr>
    <tr><td>Morgan Stanley</td><td>$290,000</td><td>2027</td></tr>
    <tr><td>Citibank</td><td>$210,000</td><td>2025</td></tr>
    </table>""")

    domains = active_domains({"domains": ["finance"]})
    ext = domains[0].extractors[0]
    content = html_file.read_text()
    result = ext.extract(html_file, content)
    assert len(result["nodes"]) >= 3  # 1 table + row nodes
    assert len(result["edges"]) >= 2
    labels = [n["label"] for n in result["nodes"]]
    assert "JPMorgan" in labels
    assert "Goldman Sachs" in labels


def test_finance_extracts_csv(tmp_path):
    csv_file = tmp_path / "positions.csv"
    csv_file.write_text("Security,Notional,Maturity\nBond A,1000000,2025\nBond B,2000000,2026\n")

    domains = active_domains({"domains": ["finance"]})
    ext = domains[0].extractors[0]
    content = csv_file.read_text()
    result = ext.extract(csv_file, content)
    assert len(result["nodes"]) >= 3


def test_finance_prompt_fragments():
    domains = active_domains({"domains": ["finance"]})
    d = domains[0]
    prompt = d.prompt_fragments()
    assert "company" in prompt
    assert "covenant" in prompt
    assert "non-GAAP" in prompt


def test_finance_post_extract_concentration():
    domains = active_domains({"domains": ["finance"]})
    d = domains[0]
    extraction = {
        "nodes": [
            {"id": "jp", "label": "JPMorgan", "type": "counterparty"},
            {"id": "gs", "label": "Goldman", "type": "counterparty"},
        ],
        "edges": [
            {"source": "deal_1", "target": "jp", "relation": "counterparty_to"},
            {"source": "deal_2", "target": "jp", "relation": "counterparty_to"},
            {"source": "deal_3", "target": "jp", "relation": "counterparty_to"},
            {"source": "deal_4", "target": "jp", "relation": "counterparty_to"},
            {"source": "deal_5", "target": "gs", "relation": "counterparty_to"},
        ],
    }
    result = d.post_extract(extraction)
    conc_edges = [e for e in result["edges"] if e.get("relation") == "concentration_risk"]
    assert len(conc_edges) == 1
    assert conc_edges[0]["source"] == "jp"
    assert conc_edges[0]["metadata"]["exposure_pct"] == 80.0
