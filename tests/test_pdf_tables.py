"""Tests for PDF table extraction (basic tier)."""
from pathlib import Path

import pytest

from graphify.shared.pdf_tables import _find_aligned_blocks, _split_at, _block_to_table


class TestSplitAt:
    def test_no_splits(self):
        assert _split_at("hello world", []) == ["hello world"]

    def test_single_split(self):
        result = _split_at("Name     Value", [4])
        assert len(result) >= 2

    def test_multiple_splits(self):
        line = "Acme       1000       2024"
        result = _split_at(line, [5, 16])
        assert len(result) == 3


class TestFindAlignedBlocks:
    def test_basic_aligned_text(self):
        text = (
            "Company       Revenue     Growth\n"
            "Acme Corp     $4.2B       +35%\n"
            "Beta Inc      $1.8B       -10%\n"
            "Gamma LLC     $0.9B       +5%\n"
        )
        tables = _find_aligned_blocks(text, 0, Path("test.pdf"))
        assert len(tables) >= 1
        t = tables[0]
        assert len(t.rows) >= 3 or (len(t.headers) >= 1 and len(t.rows) >= 2)

    def test_no_table_in_prose(self):
        text = (
            "This is a paragraph of text.\n"
            "It has no tabular structure.\n"
            "Just sentences flowing naturally.\n"
        )
        tables = _find_aligned_blocks(text, 0, Path("test.pdf"))
        assert len(tables) == 0

    def test_short_block_ignored(self):
        text = "A  B\nC  D\n"  # Only 2 rows, below threshold
        tables = _find_aligned_blocks(text, 0, Path("test.pdf"))
        assert len(tables) == 0


class TestBlockToTable:
    def test_creates_table(self):
        block = [
            ("Name       Value", [4]),
            ("Alpha      100", [5]),
            ("Beta       200", [4]),
        ]
        t = _block_to_table(block, 0, Path("test.pdf"), 0)
        assert t.id == "test__p1_t1"
        assert len(t.headers) + len(t.rows) == 3


class TestExtractPdfTablesAuto:
    def test_auto_strategy_no_pdf(self, tmp_path):
        """Non-existent PDF returns empty."""
        from graphify.shared.pdf_tables import extract_pdf_tables
        result = extract_pdf_tables(tmp_path / "nonexistent.pdf")
        assert result == []
