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

**Node types**: company, security, obligation, covenant, counterparty, fund, metric, filing_section, cash_flow, unit_economics
**Edge types**: owns, guarantees, subsidiary_of, counterparty_to, benchmarked_against, revenue_from, obligated_to, reports_metric, burn_rate, dilution, valuation_inflated_by, revenue_quality, cash_flow_divergence, working_capital_flag, debt_maturity, total_dilution, liquidity_runway

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

REVENUE QUALITY:
- Decompose revenue by type if disclosed: recurring vs one-time, organic vs acquired, domestic vs international, related-party vs arm's-length
- Create revenue_quality edge from company to a revenue breakdown node with metadata: recurring_pct, related_party_pct, organic_growth_rate
- If related-party revenue as % of total is >5% or growing faster than organic revenue, flag with confidence_score 0.8
- If acquired revenue (from companies bought in the period) accounts for >20% of reported growth, note it

CASH FLOW vs EARNINGS:
- Extract operating cash flow and net income for each reported period
- If operating cash flow is negative while any adjusted/non-GAAP metric is positive, create a cash_flow_divergence edge
- Include in label: OCF amount, net income amount, and the adjusted metric that was positive
- This exposes when "profitability" claims depend on excluding real cash costs

WORKING CAPITAL:
- Compare accounts receivable growth rate to revenue growth rate
- If AR grows >1.5x faster than revenue, create working_capital_flag edge (possible channel stuffing or collection issues)
- Compare deferred revenue trends — shrinking deferred revenue while reporting growth = pulling forward future revenue
- Include the growth rates in edge metadata

DEBT MATURITY SCHEDULE:
- Extract the maturity timeline for all debt instruments (when does each tranche come due?)
- Create debt_maturity edges from each instrument to a time-bucket node (e.g., "2024", "2025", "2026+")
- Flag maturity walls: if >40% of total debt matures within 2 years, note concentration in label
- Include refinancing risk: what % of current cash/revenue would be needed to service near-term maturities

UNIT ECONOMICS:
- Extract per-unit metrics when disclosed: revenue per location/customer/member, cost per unit, contribution margin
- Create unit_economics node with these figures
- If unit-level contribution is negative (costs more to serve one customer than revenue from them), flag explicitly
- Compare unit economics across periods — are they improving or degrading at scale?

CAPITAL STRUCTURE / TOTAL DILUTION:
- Count all outstanding dilutive instruments: options, warrants, convertible notes, preferred conversion rights, RSUs
- Create total_dilution edge from company to a summary node with: current shares outstanding, total potential shares if everything converts/exercises, dilution percentage
- If total potential dilution exceeds 30% of current shares, flag it
- List each instrument class contributing to dilution

LIQUIDITY RUNWAY:
- Extract: cash & equivalents, quarterly/annual cash burn rate (operating cash outflow)
- Calculate implied runway in months: cash / monthly burn rate
- Create liquidity_runway edge with months_remaining in metadata
- If runway < 12 months without the IPO/fundraise proceeds, flag as critical
- If the filing mentions "going concern", "substantial doubt about ability to continue", or "need additional capital to fund operations", extract verbatim and flag

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
    seen = set()

    # 1. Detect from semantic concentration_risk edges
    for u, v, d in G.edges(data=True):
        if d.get("relation") == "concentration_risk":
            target = v
            if target in seen:
                continue
            seen.add(target)
            label = d.get("label", G.nodes[target].get("label", target))
            meta = d.get("metadata", {})
            results.append({
                "type": "concentration_risk",
                "node": target,
                "entity": target,
                "label": label,
                "exposure_pct": meta.get("exposure_pct"),
                "source": "semantic",
            })

    # 2. Detect from table-extracted nodes with high degree
    for node, data in G.nodes(data=True):
        if node in seen:
            continue
        if data.get("domain") != "finance":
            continue
        degree = G.degree(node)
        if degree > 5:
            obligation_edges = [
                (u, v) for u, v, d in G.edges(node, data=True)
                if d.get("relation") in ("counterparty_to", "revenue_from")
            ]
            if len(obligation_edges) >= 3:
                seen.add(node)
                results.append({
                    "type": "concentration_risk",
                    "node": node,
                    "entity": node,
                    "label": data.get("label", node),
                    "obligation_count": len(obligation_edges),
                    "total_degree": degree,
                    "source": "table",
                })
    # Generate finding descriptions
    for r in results:
        label = r.get("label", "")
        exposure = r.get("exposure_pct")
        if exposure:
            r["finding"] = (
                f"A single counterparty (\"{label}\") accounts for ~{exposure:.0f}% of revenue. "
                "Losing this relationship would cause an immediate, material revenue decline "
                "that the company may not be able to replace quickly."
            )
        else:
            r["finding"] = (
                f"\"{label}\" has an unusually high number of financial relationships with the company. "
                "This concentration creates dependency risk — disruption to this single counterparty "
                "would ripple across multiple business lines."
            )

    # Enrich with evidence
    for r in results:
        node = r.get("node", "")
        if node and node in G:
            ndata = G.nodes[node]
            neighbors = []
            for u, v, d in G.edges(node, data=True):
                other = v if u == node else u
                neighbors.append({
                    "node": other,
                    "label": G.nodes[other].get("label", other) if other in G else other,
                    "relation": d.get("relation", ""),
                })
            r["evidence"] = {
                "source_file": ndata.get("source_file", ""),
                "excerpt": ndata.get("label", ""),
                "data": ndata.get("data", {}),
                "neighbors": neighbors[:10],
            }
    return sorted(results, key=lambda x: x.get("obligation_count", 0), reverse=True)


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
