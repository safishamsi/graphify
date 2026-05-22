"""Tests for grounding validation pass."""
import tempfile
from pathlib import Path

from graphify.grounding import validate_grounding, _label_appears_in_source


def test_label_appears_exact_match():
    assert _label_appears_in_source("Adam Neumann", "CEO Adam Neumann founded the company")


def test_label_appears_partial_words():
    # 3 of 4 significant words present (75% > 60% threshold)
    assert _label_appears_in_source(
        "Non-cancelable operating lease commitments",
        "The company has operating lease commitments that are non-cancelable"
    )


def test_label_not_in_source():
    assert not _label_appears_in_source(
        "Community Adjusted EBITDA",
        "We use contribution margin to assess profitability of our locations"
    )


def test_grounding_downgrades_ungrounded_extracted_edges():
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "doc.md"
        source.write_text("Adam Neumann is the CEO. Revenue was $1.82B.")

        extraction = {
            "nodes": [
                {"id": "adam", "label": "Adam Neumann", "file_type": "document", "source_file": "doc.md"},
                {"id": "hallucinated", "label": "Community Adjusted EBITDA", "file_type": "document", "source_file": "doc.md"},
            ],
            "edges": [
                {"source": "adam", "target": "hallucinated", "relation": "reports_metric",
                 "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": "doc.md"},
            ],
        }

        result = validate_grounding(extraction, source_root=Path(tmp))

        # The edge touching "hallucinated" should be downgraded
        edge = result["edges"][0]
        assert edge["confidence"] == "INFERRED"
        assert edge["confidence_score"] == 0.75
        assert "grounding_note" in edge


def test_grounding_leaves_grounded_edges_alone():
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "doc.md"
        source.write_text("Adam Neumann is CEO. Total revenue was 1.82 billion dollars.")

        extraction = {
            "nodes": [
                {"id": "adam", "label": "Adam Neumann", "file_type": "document", "source_file": "doc.md"},
                {"id": "revenue", "label": "Total revenue 1.82 billion", "file_type": "document", "source_file": "doc.md"},
            ],
            "edges": [
                {"source": "adam", "target": "revenue", "relation": "reports_metric",
                 "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": "doc.md"},
            ],
        }

        result = validate_grounding(extraction, source_root=Path(tmp))

        edge = result["edges"][0]
        assert edge["confidence"] == "EXTRACTED"
        assert edge["confidence_score"] == 1.0


def test_grounding_skips_inferred_edges():
    """Grounding only checks EXTRACTED edges, leaves INFERRED alone."""
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "doc.md"
        source.write_text("Some unrelated text here.")

        extraction = {
            "nodes": [
                {"id": "fake", "label": "Nonexistent Entity", "file_type": "document", "source_file": "doc.md"},
            ],
            "edges": [
                {"source": "fake", "target": "fake", "relation": "self_ref",
                 "confidence": "INFERRED", "confidence_score": 0.85, "source_file": "doc.md"},
            ],
        }

        result = validate_grounding(extraction, source_root=Path(tmp))

        # INFERRED edges are not touched by grounding
        edge = result["edges"][0]
        assert edge["confidence"] == "INFERRED"
        assert edge["confidence_score"] == 0.85
