"""Finance domain plugin — SEC filings, financial statements, term sheets."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from graphify.domain import DomainSpec, register
from graphify.shared.tables import Table, extract_html_tables, is_data_table_finance, table_to_nodes_edges


@dataclass
class FinanceExtractor:
    """Extract financial entities from structured documents."""

    name: str = "finance"
    file_patterns: list[str] = field(
        default_factory=lambda: ["*.html", "*.htm", "*.xhtml", "*.xlsx", "*.xls", "*.csv", "*.pdf"]
    )

    def extract(self, path: Path, content: str) -> dict:
        nodes, edges = [], []
        tables = self._get_tables(path, content)
        # For HTML sources, filter to financially relevant tables only
        if path.suffix.lower() in (".html", ".htm", ".xhtml"):
            tables = self._filter_financial_tables(tables)
        for t in tables:
            result = table_to_nodes_edges(t, "finance")
            nodes.extend(result["nodes"])
            edges.extend(result["edges"])
        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def _filter_financial_tables(tables: list) -> list:
        """Keep tables with structured financial data not captured by semantic extraction.

        Targets: obligation schedules, counterparty exposures, debt maturity tables.
        Skips: general income statements, balance sheets (semantic extraction handles those).
        """
        import re
        keywords = re.compile(
            r'lease.commitment|obligation|counterpart|exposure|'
            r'notional|maturity|covenant|credit.facilit',
            re.IGNORECASE,
        )
        result = []
        for t in tables:
            # Check row labels + headers (some tables identify in headers)
            first_cols = " ".join(row[0] for row in t.rows[:8] if row and row[0].strip())
            header_text = " ".join(cell for row in (t.headers or []) for cell in row)
            caption = t.caption or ""
            text = caption + " " + header_text + " " + first_cols
            if keywords.search(text):
                result.append(t)
        return result

    def _get_tables(self, path: Path, content: str) -> list[Table]:
        suffix = path.suffix.lower()
        if suffix in (".html", ".htm", ".xhtml"):
            return extract_html_tables(path, content)
        elif suffix in (".xlsx", ".xls"):
            from graphify.shared.spreadsheet import extract_excel_tables
            return extract_excel_tables(path)
        elif suffix == ".csv":
            from graphify.shared.spreadsheet import extract_csv_table
            return extract_csv_table(path)
        elif suffix == ".pdf":
            from graphify.shared.pdf_tables import extract_pdf_tables
            return extract_pdf_tables(path)
        return []


def _finance_prompt_fragments() -> str:
    return """## Finance Domain Extraction

Extract financial entities and relationships from the document:

**Node types**: company, security, obligation, covenant, counterparty, fund, metric, filing_section
**Edge types**: owns, guarantees, subsidiary_of, counterparty_to, benchmarked_against, revenue_from, obligated_to, reports_metric, burn_rate, dilution, valuation_inflated_by

Instructions:
- Extract named companies, funds, and counterparties as nodes
- Extract financial obligations with dollar amounts in the label
- Extract covenants and their triggering conditions
- Extract revenue dependencies (who pays whom, concentration)
- Extract non-GAAP metrics — each excluded cost as a separate edge
- For tables: each row entity should become a node with relationships to column values
- Preserve dollar amounts, percentages, and dates in labels
- Compare revenue vs. net loss across periods: if loss/revenue ratio > 1.0 or worsening, add a burn_rate edge with the ratio in the label
- Flag massive option pools or share issuances that dilute existing shareholders (edge: dilution, include percentage)
- If use-of-proceeds allocates >50% to debt repayment rather than growth, note it as an edge
- If a single investor's transactions (secondary purchases, convertible notes) set the valuation without market price discovery, add valuation_inflated_by edge

Return relationships with confidence scores. Mark inferred relationships as confidence < 1.0.
"""


def _finance_post_extract(extraction: dict) -> dict:
    """Post-extraction inference for finance domain."""
    nodes = extraction.get("nodes", [])
    edges = extraction.get("edges", [])

    # Infer concentration risk edges: if one counterparty appears in >30% of obligation edges
    _infer_concentration(nodes, edges)

    return {"nodes": nodes, "edges": edges}


def _infer_concentration(nodes: list[dict], edges: list[dict]) -> None:
    """Add concentration_risk edges for over-exposed counterparties."""
    from collections import Counter

    obligation_targets = [
        e["target"] for e in edges
        if e.get("relation") in ("counterparty_to", "revenue_from", "obligated_to")
    ]
    if not obligation_targets:
        return

    counts = Counter(obligation_targets)
    total = len(obligation_targets)
    for entity_id, count in counts.items():
        ratio = count / total
        if ratio > 0.3:
            edges.append({
                "source": entity_id,
                "target": entity_id,
                "relation": "concentration_risk",
                "confidence": min(0.6 + ratio, 0.95),
                "metadata": {"exposure_pct": round(ratio * 100, 1)},
            })


def concentration_risk_analyzer(G) -> list[dict]:
    """Report nodes with high counterparty concentration."""
    results = []
    for node, data in G.nodes(data=True):
        if data.get("domain") != "finance":
            continue
        degree = G.degree(node)
        if degree > 5:
            # Check if this node is on many obligation edges
            obligation_edges = [
                (u, v) for u, v, d in G.edges(node, data=True)
                if d.get("relation") in ("counterparty_to", "revenue_from")
            ]
            if len(obligation_edges) >= 3:
                results.append({
                    "entity": node,
                    "label": data.get("label", node),
                    "obligation_count": len(obligation_edges),
                    "total_degree": degree,
                })
    return sorted(results, key=lambda x: x["obligation_count"], reverse=True)


# --- Registration ---

_SPEC = DomainSpec(
    name="finance",
    extractors=[FinanceExtractor()],
    relations={
        "ownership": ["owns", "subsidiary_of", "controls"],
        "obligation": ["guarantees", "obligated_to", "counterparty_to"],
        "revenue": ["revenue_from", "benchmarked_against"],
        "metric": ["reports_metric", "deviates_from_gaap"],
        "risk": ["concentration_risk"],
    },
    node_types=["company", "security", "obligation", "covenant", "counterparty", "fund", "metric"],
    prompt_fragments=_finance_prompt_fragments,
    post_extract=_finance_post_extract,
    analyzers=[concentration_risk_analyzer],
)

register(_SPEC)
