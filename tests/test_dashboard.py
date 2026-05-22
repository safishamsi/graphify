"""Tests for graphify.dashboard module."""
import json
from pathlib import Path

import pytest

from graphify.dashboard import render_dashboard, render_dashboard_from_file


@pytest.fixture
def sample_analysis():
    return {
        "communities": {"0": ["a", "b", "c"], "1": ["d", "e"]},
        "cohesion": {"0": 0.72, "1": 0.85},
        "gods": ["node_x", "node_y"],
        "surprises": [
            {"from": "a", "to": "d", "relation": "imports", "why": "cross-community"}
        ],
        "tokens": {"input": 1000, "output": 500},
        "domain_analysis": {
            "finance.concentration_risk_analyzer": [
                {"entity": "finance__jpmorgan", "label": "JPMorgan", "obligation_count": 7, "total_degree": 12}
            ],
            "diligence.red_flag_analyzer": [
                {"type": "orphan_liability", "node": "diligence__lease_4", "label": "Lease", "severity": "high"}
            ],
            "diligence.key_person_risk_analyzer": [
                {"person": "diligence__john", "label": "John", "degree": 10, "components_if_removed": 3, "risk": "high"}
            ],
        },
    }


@pytest.fixture
def sample_meta():
    return {"nodes": 50, "edges": 120}


def test_render_dashboard_creates_file(tmp_path, sample_analysis, sample_meta):
    out = tmp_path / "dashboard.html"
    result = render_dashboard(sample_analysis, sample_meta, out)
    assert result == out
    assert out.exists()
    content = out.read_text()
    assert "Knowledge Graph Dashboard" in content
    assert "JPMorgan" in content
    assert "orphan_liability" in content


def test_render_dashboard_embeds_data(tmp_path, sample_analysis, sample_meta):
    out = tmp_path / "dashboard.html"
    render_dashboard(sample_analysis, sample_meta, out)
    content = out.read_text()
    # Data should be embedded as JSON in the script
    assert '"nodes": 50' in content or '"nodes":50' in content
    assert '"edges": 120' in content or '"edges":120' in content


def test_render_dashboard_no_domain_analysis(tmp_path, sample_meta):
    analysis = {
        "communities": {"0": ["a", "b"]},
        "cohesion": {"0": 0.5},
        "gods": [],
        "surprises": [],
        "tokens": {"input": 100, "output": 50},
    }
    out = tmp_path / "dashboard.html"
    render_dashboard(analysis, sample_meta, out)
    assert out.exists()
    content = out.read_text()
    assert "Knowledge Graph Dashboard" in content


def test_render_dashboard_from_file(tmp_path, sample_analysis):
    analysis_path = tmp_path / ".graphify_analysis.json"
    analysis_path.write_text(json.dumps(sample_analysis))
    result = render_dashboard_from_file(analysis_path)
    assert result == tmp_path / "dashboard.html"
    assert result.exists()
    content = result.read_text()
    assert "JPMorgan" in content


def test_dashboard_html_is_valid_structure(tmp_path, sample_analysis, sample_meta):
    out = tmp_path / "dashboard.html"
    render_dashboard(sample_analysis, sample_meta, out)
    content = out.read_text()
    assert content.startswith("<!DOCTYPE html>")
    assert "</html>" in content
    assert "<script>" in content
    assert "const DATA =" in content
