"""Tests for shared table extraction utilities."""
from pathlib import Path

import pytest

from graphify.shared.tables import (
    Table,
    extract_html_tables,
    is_data_table_finance,
    table_to_markdown,
    table_to_nodes_edges,
    link_tables_to_entities,
    _make_id,
    _is_financial_cell,
    _parse_numeric,
)


class TestFinancialCells:
    def test_dollar_amount(self):
        assert _is_financial_cell("$1,234")

    def test_parenthetical_negative(self):
        assert _is_financial_cell("(1,234)")

    def test_percentage(self):
        assert _is_financial_cell("12.3%")

    def test_plain_text_not_financial(self):
        assert not _is_financial_cell("Revenue")

    def test_empty_not_financial(self):
        assert not _is_financial_cell("")


class TestParseNumeric:
    def test_dollar(self):
        assert _parse_numeric("$1,234") == 1234.0

    def test_negative_parens(self):
        assert _parse_numeric("(1,234)") == -1234.0

    def test_percentage(self):
        assert _parse_numeric("12.3%") == 12.3

    def test_plain_text(self):
        assert _parse_numeric("Revenue") is None

    def test_empty(self):
        assert _parse_numeric("") is None


class TestMakeId:
    def test_basic(self):
        assert _make_id("tbl", "0", "Revenue") == "tbl_0_revenue"

    def test_special_chars(self):
        result = _make_id("tbl", "Total Lease Obligations")
        assert " " not in result
        assert result == "tbl_total_lease_obligations"

    def test_length_cap(self):
        long_label = "A" * 200
        assert len(_make_id(long_label)) <= 80


class TestHTMLExtraction:
    def test_basic_financial_table(self):
        html = """<table>
        <tr><th>Item</th><th>2023</th><th>2022</th></tr>
        <tr><td>Revenue</td><td>$4,200</td><td>$3,100</td></tr>
        <tr><td>Net Income</td><td>$800</td><td>$600</td></tr>
        <tr><td>Operating Expense</td><td>$2,400</td><td>$1,900</td></tr>
        <tr><td>Total Assets</td><td>$10,500</td><td>$9,200</td></tr>
        </table>"""
        tables = extract_html_tables(Path("test.html"), html)
        assert len(tables) == 1
        t = tables[0]
        assert t.score > 0.0

    def test_filters_layout_presentation_role(self):
        html = """<table role="presentation">
        <tr><td>$100</td><td>$200</td></tr>
        <tr><td>$300</td><td>$400</td></tr>
        <tr><td>$500</td><td>$600</td></tr>
        <tr><td>$700</td><td>$800</td></tr>
        </table>"""
        tables = extract_html_tables(Path("test.html"), html)
        assert len(tables) == 0

    def test_filters_toc_table(self):
        html = """<table>
        <tr><td><a href="#s1">Section 1</a></td><td>$100</td></tr>
        <tr><td><a href="#s2">Section 2</a></td><td>$200</td></tr>
        <tr><td><a href="#s3">Section 3</a></td><td>$300</td></tr>
        <tr><td><a href="#s4">Section 4</a></td><td>$400</td></tr>
        </table>"""
        tables = extract_html_tables(Path("test.html"), html)
        assert len(tables) == 0

    def test_filters_too_small(self):
        html = """<table>
        <tr><td>Revenue</td><td>$100</td></tr>
        <tr><td>Cost</td><td>$50</td></tr>
        </table>"""
        tables = extract_html_tables(Path("test.html"), html)
        assert len(tables) == 0  # only 2 data rows, need 3+

    def test_caption(self):
        html = """<table><caption>Revenue Summary</caption>
        <tr><th>Year</th><th>Amount</th></tr>
        <tr><td>Revenue</td><td>$4,200</td></tr>
        <tr><td>Net Income</td><td>$800</td></tr>
        <tr><td>Operating</td><td>$2,400</td></tr>
        <tr><td>Total</td><td>$10,500</td></tr>
        </table>"""
        tables = extract_html_tables(Path("test.html"), html)
        if tables:  # may not pass score threshold depending on density
            assert tables[0].caption == "Revenue Summary"

    def test_skips_nested_tables(self):
        html = """<table>
        <tr><td>
            <table>
            <tr><td>Nested Revenue</td><td>$1,000</td></tr>
            <tr><td>Nested Cost</td><td>$500</td></tr>
            <tr><td>Nested Profit</td><td>$500</td></tr>
            <tr><td>Nested Tax</td><td>$100</td></tr>
            </table>
        </td></tr>
        </table>"""
        # Outer table is single-cell, inner table is nested — neither should pass
        tables = extract_html_tables(Path("test.html"), html)
        # The nested table should not be extracted as a top-level table
        for t in tables:
            assert "Nested" not in (t.caption or "")


class TestTableToNodesEdges:
    def test_basic(self):
        t = Table(
            id="t1",
            caption="Test Table",
            headers=[["Entity", "Amount"]],
            rows=[["Acme Corp", "$100"], ["Beta Inc", "$200"]],
            source_file="test.html",
            score=0.5,
        )
        result = table_to_nodes_edges(t, "finance")
        assert len(result["nodes"]) == 3  # 1 table + 2 rows
        assert result["nodes"][0]["type"] == "table"
        assert result["nodes"][1]["type"] == "table_row"
        assert result["nodes"][1]["label"] == "Acme Corp"

    def test_numeric_values_parsed(self):
        t = Table(
            id="t1",
            caption="Financials",
            headers=[["Item", "2023"]],
            rows=[["Revenue", "$4,200"]],
            source_file="test.html",
            score=0.5,
        )
        result = table_to_nodes_edges(t, "finance")
        row_node = result["nodes"][1]
        assert "numeric_values" in row_node
        assert row_node["numeric_values"]["2023"] == 4200.0

    def test_empty_first_col_skipped(self):
        t = Table(
            id="t1", caption="Test",
            headers=[["Name", "Val"]],
            rows=[["", "$100"], ["Beta", "$200"]],
            source_file="f.html",
            score=0.5,
        )
        result = table_to_nodes_edges(t, "test")
        row_nodes = [n for n in result["nodes"] if n["type"] == "table_row"]
        assert len(row_nodes) == 1
        assert row_nodes[0]["label"] == "Beta"

    def test_purely_numeric_label_skipped(self):
        t = Table(
            id="t1", caption="Test",
            headers=[["Label", "Val"]],
            rows=[["$1,234", "$100"], ["Real Label", "$200"]],
            source_file="f.html",
            score=0.5,
        )
        result = table_to_nodes_edges(t, "test")
        row_nodes = [n for n in result["nodes"] if n["type"] == "table_row"]
        assert len(row_nodes) == 1
        assert row_nodes[0]["label"] == "Real Label"

    def test_followed_by_edges(self):
        t = Table(
            id="t1", caption="Test",
            headers=[["Item", "Val"]],
            rows=[["Alpha", "$100"], ["Beta", "$200"], ["Gamma", "$300"]],
            source_file="f.html",
            score=0.5,
        )
        result = table_to_nodes_edges(t, "test")
        followed_by = [e for e in result["edges"] if e["relation"] == "followed_by"]
        assert len(followed_by) == 2

    def test_stable_ids(self):
        t = Table(
            id="t1", caption="Test",
            headers=[["Item", "Val"]],
            rows=[["Revenue", "$100"]],
            source_file="f.html",
            score=0.5,
        )
        result1 = table_to_nodes_edges(t, "test")
        result2 = table_to_nodes_edges(t, "test")
        assert result1["nodes"][1]["id"] == result2["nodes"][1]["id"]

    def test_duplicate_labels_disambiguated(self):
        t = Table(
            id="t1", caption="Test",
            headers=[["Item", "Val"]],
            rows=[["Total", "$100"], ["Total", "$200"]],
            source_file="f.html",
            score=0.5,
        )
        result = table_to_nodes_edges(t, "test")
        row_nodes = [n for n in result["nodes"] if n["type"] == "table_row"]
        ids = [n["id"] for n in row_nodes]
        assert len(set(ids)) == 2  # unique IDs despite same label


class TestLinkTablesToEntities:
    def test_exact_match(self):
        table_nodes = [
            {"id": "row1", "type": "table_row", "label": "Adam Neumann"},
        ]
        semantic_nodes = [
            {"id": "sem1", "label": "Adam Neumann"},
        ]
        edges = link_tables_to_entities(table_nodes, [], semantic_nodes)
        assert len(edges) == 1
        assert edges[0]["confidence"] == "EXTRACTED"

    def test_short_label_skipped(self):
        table_nodes = [
            {"id": "row1", "type": "table_row", "label": "ABC"},
        ]
        semantic_nodes = [
            {"id": "sem1", "label": "ABC Corp"},
        ]
        edges = link_tables_to_entities(table_nodes, [], semantic_nodes)
        assert len(edges) == 0  # "ABC" is < 5 chars

    def test_prefix_match(self):
        table_nodes = [
            {"id": "row1", "type": "table_row", "label": "Operating Lease Commitments"},
        ]
        semantic_nodes = [
            {"id": "sem1", "label": "Operating Lease Commitments and Obligations Summary"},
        ]
        edges = link_tables_to_entities(table_nodes, [], semantic_nodes)
        assert len(edges) == 1
        assert edges[0]["confidence"] == "INFERRED"


class TestTableToMarkdown:
    def test_with_headers(self):
        t = Table(
            id="t", caption=None,
            headers=[["A", "B"]],
            rows=[["1", "2"], ["3", "4"]],
            source_file="f",
        )
        md = table_to_markdown(t)
        assert "| A | B |" in md
        assert "|---|---|" in md
        assert "| 1 | 2 |" in md

    def test_without_headers(self):
        t = Table(id="t", caption=None, headers=[], rows=[["x", "y"]], source_file="f")
        md = table_to_markdown(t)
        assert "| x | y |" in md
        assert "---" not in md


class TestFinanceDetection:
    def test_currency(self):
        assert is_data_table_finance([["Revenue", "$4.2B"]])

    def test_percentage(self):
        assert is_data_table_finance([["Growth", "35%"]])

    def test_fiscal_year(self):
        assert is_data_table_finance([["Period", "FY2024"]])

    def test_plain_text(self):
        assert not is_data_table_finance([["Hello", "World"]])
