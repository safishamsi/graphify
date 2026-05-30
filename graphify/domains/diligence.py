"""Due diligence domain plugin — corporate filings, governance, conflict detection."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

from graphify.domain import DomainSpec, register
from graphify.shared.tables import Table, extract_html_tables, table_to_nodes_edges


@dataclass
class DiligenceExtractor:
    """Extract governance, legal, and risk entities from corporate documents."""

    name: str = "diligence"
    file_patterns: list[str] = field(
        default_factory=lambda: ["*.html", "*.htm", "*.pdf", "*.docx", "*.xlsx", "*.md"]
    )

    def extract(self, path: Path, content: str) -> dict:
        nodes, edges = [], []
        # Table extraction
        tables = self._get_tables(path, content)
        for t in self._filter_governance_tables(tables):
            result = table_to_nodes_edges(t, "diligence")
            nodes.extend(result["nodes"])
            edges.extend(result["edges"])
        # Text pattern extraction
        text_result = self._extract_from_text(path, content)
        nodes.extend(text_result["nodes"])
        edges.extend(text_result["edges"])
        return {"nodes": nodes, "edges": edges}

    def _extract_from_text(self, path: Path, content: str) -> dict:
        """Extract governance red flags from narrative text.

        Two-phase approach:
        - Phase 1 (deterministic): find candidate windows using regex co-occurrence
          patterns. For patterns needing entity disambiguation (officer loans, IP
          transfers), store candidates in .aag_diligence_candidates.json for agent
          resolution.
        - Phase 2 (deterministic, no disambiguation needed): compensation concentration
          (pure math), family ties (explicit "married to"), asset leasebacks (corporate
          suffix check).
        """
        import json
        import re
        from html.parser import HTMLParser

        # Strip HTML tags for text matching
        class _Stripper(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts: list[str] = []
            def handle_data(self, data):
                self.parts.append(data)
        stripper = _Stripper()
        stripper.feed(content)
        text = " ".join(stripper.parts)

        nodes, edges = [], []
        candidates = []  # for agent resolution
        stem = path.stem

        def _nid(label: str) -> str:
            cleaned = re.sub(r"[^a-z0-9]+", "_", label.lower())
            return f"{stem}_{cleaned.strip('_')[:60]}"

        # --- Shared patterns ---
        loan_kw = re.compile(r'promissory note|(?:non-?recourse |personal )?loan|note payable', re.IGNORECASE)
        related_party_kw = re.compile(
            r'related.party|officer|director|executive|insider|stockholder.loan|'
            r'principal.stockholder|chief.executive|our.(?:CEO|CFO|COO|CTO)',
            re.IGNORECASE
        )
        amounts_in_text = list(re.finditer(r'\$([\d,.]+)\s*(million|billion)', text))

        # --- Phase 1: Candidate windows (need agent disambiguation) ---

        # 1. Officer/insider loans: related-party context + loan keyword + dollar amount
        for am in amounts_in_text:
            amount = am.group(1).replace(",", "")
            unit = am.group(2).lower()
            try:
                val = float(amount)
            except ValueError:
                continue
            if val < 1.0:
                continue
            # Require related-party context within 800 chars
            ctx_start = max(0, am.start() - 800)
            ctx_end = min(len(text), am.end() + 800)
            if not related_party_kw.search(text[ctx_start:ctx_end]):
                continue
            # Require loan keyword within 200 chars
            window_start = max(0, am.start() - 200)
            window_end = min(len(text), am.end() + 200)
            window = text[window_start:window_end]
            if not loan_kw.search(window):
                continue
            candidates.append({
                "type": "officer_loan",
                "amount": f"${amount} {unit}",
                "window": text[max(0, am.start() - 300):am.end() + 300],
                "source_file": str(path),
            })

        # 2. IP/trademark transfers: transfer verb + IP term + dollar amount
        ip_terms = re.compile(r'trademark|intellectual property|brand name|patent|license\s+(?:to|from)', re.IGNORECASE)
        transfer_verbs = re.compile(r'assigned|transferred|contributed|sold|purchased from|acquired from', re.IGNORECASE)
        insider_entity = re.compile(r'[A-Z][\w\s]+?(?:Holdings|Family|Trust)\s+(?:LLC|LP)', re.IGNORECASE)

        for am in amounts_in_text:
            amount = am.group(1).replace(",", "")
            unit = am.group(2).lower()
            window_start = max(0, am.start() - 400)
            window_end = min(len(text), am.end() + 200)
            window = text[window_start:window_end]
            if not ip_terms.search(window):
                continue
            if not transfer_verbs.search(window):
                continue
            # Require related-party context OR insider entity
            ctx_start = max(0, am.start() - 800)
            ctx_end = min(len(text), am.end() + 400)
            has_rp = related_party_kw.search(text[ctx_start:ctx_end])
            has_insider = insider_entity.search(window)
            if not has_rp and not has_insider:
                continue
            candidates.append({
                "type": "ip_transfer",
                "amount": f"${amount} {unit}",
                "window": text[max(0, am.start() - 400):am.end() + 200],
                "source_file": str(path),
            })

        # Write candidates for agent resolution
        if candidates:
            out_dir = Path("graphify-out")
            out_dir.mkdir(exist_ok=True)
            cand_file = out_dir / ".aag_diligence_candidates.json"
            # Append to existing candidates (multiple files may be processed)
            existing = []
            if cand_file.exists():
                try:
                    existing = json.loads(cand_file.read_text())
                except (json.JSONDecodeError, OSError):
                    pass
            existing.extend(candidates)
            cand_file.write_text(json.dumps(existing, indent=2))

        # --- Phase 2: Patterns that don't need entity disambiguation ---

        # 3. Stock option concentration (pure math — no entity ambiguity)
        _not_name_part = {
            'Credit', 'Facility', 'Common', 'Stock', 'Preferred', 'Cash', 'Flow',
            'Capital', 'Venture', 'Bank', 'Total', 'Assets', 'Net', 'Loss', 'Lease',
            'Operating', 'Income', 'Balance', 'Sheet', 'Company', 'Companies', 'Group',
            'The', 'Each', 'These', 'Those', 'Such', 'During', 'Between', 'Through',
        }
        for m in re.finditer(
            r'(?:options?\s+(?:to purchase\s+)?(?:a\s+)?total\s+of|'
            r'(?:stock\s+)?options?.*?(?:aggregate|total).*?of|'
            r'(?:RSU|restricted\s+stock).*?total(?:ing|.*?of)|'
            r'granted\s+(?:a\s+total\s+of|.*?totaling))\s*'
            r'([\d,]+)\s*(?:shares|options?|RSUs?|units?).*?'
            r'([A-Z][a-z]{2,})\s+(?:received|was\s+(?:granted|awarded)).*?'
            r'(?:aggregate\s+of|total\s+of|totaling)\s*([\d,]+)',
            text, re.DOTALL
        ):
            total = m.group(1).replace(",", "")
            person = m.group(2)
            individual = m.group(3).replace(",", "")
            if person in _not_name_part:
                continue
            try:
                pct = round(int(individual) / int(total) * 100, 1)
            except (ValueError, ZeroDivisionError):
                continue
            if 50 < pct <= 100:
                label = f"Compensation Concentration: {person} {pct}% of options ({individual}/{total})"
                nid = _nid(f"comp_concentration_{person}")
                if not any(n["id"] == nid for n in nodes):
                    nodes.append({"id": nid, "label": label, "file_type": "document",
                                  "source_file": str(path), "type": "risk"})
                    edges.append({"source": nid, "target": _nid(person),
                                  "relation": "compensation_concentration",
                                  "confidence": "EXTRACTED", "confidence_score": 1.0})

        # 4. Family relationships / nepotism (explicit "married to" — no ambiguity)
        seen_family = set()
        for m in re.finditer(
            r'([A-Z][a-z]{2,}(?: [A-Z][a-z]{2,})?)\s+is\s+(?:married|related|the (?:spouse|sibling|brother|sister|child|parent) of)\s+(?:to\s+)?([A-Z][a-z]{2,} [A-Z][a-z]{2,})',
            text
        ):
            person1 = m.group(1)
            person2 = m.group(2)
            if any(p in _not_name_part for p in person1.split()):
                continue
            if any(p in _not_name_part for p in person2.split()):
                continue
            # Normalize single first names using nearby full name
            if ' ' not in person1:
                nearby = re.search(
                    rf'\b({re.escape(person1)} [A-Z][a-z]{{2,}})\b',
                    text[max(0, m.start()-500):m.end()+500]
                )
                if nearby:
                    person1 = nearby.group(1)
            pair = tuple(sorted([person1, person2]))
            if pair in seen_family:
                continue
            seen_family.add(pair)
            label = f"Family Tie: {person1} married to {person2}"
            nid = _nid(f"family_{pair[0]}_{pair[1]}")
            if not any(n["id"] == nid for n in nodes):
                nodes.append({"id": nid, "label": label, "file_type": "document",
                              "source_file": str(path), "type": "risk"})
                edges.append({"source": _nid(person1), "target": _nid(person2),
                              "relation": "family_tie", "confidence": "EXTRACTED",
                              "confidence_score": 1.0})

        # 5. Properties leased from insiders (corporate suffix = unambiguous)
        for m in re.finditer(
            r'(?:lease[sd]?|rent[sd]?|occupy)\s.{0,60}?(?:from|owned by|controlled by|entities? (?:owned|controlled) by)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,4})',
            text
        ):
            entity = m.group(1).strip()
            if len(entity) < 5 or len(entity) > 60:
                continue
            # Only accept entities with corporate suffix (unambiguous)
            if not re.search(r'LLC|Inc|LP|Holdings|Fund|Venture|Partners|Corp', entity):
                continue
            label = f"Asset Leaseback: leased from {entity}"
            nid = _nid(f"leaseback_{entity}")
            if not any(n["id"] == nid for n in nodes):
                nodes.append({"id": nid, "label": label, "file_type": "document",
                              "source_file": str(path), "type": "transaction"})
                edges.append({"source": _nid(entity), "target": nid,
                              "relation": "asset_leaseback", "confidence": "INFERRED",
                              "confidence_score": 0.85})

        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def resolve_candidates(resolved: list[dict], source_file: str) -> dict:
        """Convert agent-resolved candidates into graph nodes and edges.

        Called by the pyaag pipeline after agent disambiguation. Each item in
        `resolved` should have: type, amount, person_or_entity, label.
        """
        import re
        nodes, edges = [], []
        stem = Path(source_file).stem

        def _nid(label: str) -> str:
            cleaned = re.sub(r"[^a-z0-9]+", "_", label.lower())
            return f"{stem}_{cleaned.strip('_')[:60]}"

        for item in resolved:
            if not item.get("person_or_entity"):
                continue  # agent determined this was not an insider transaction
            t = item["type"]
            entity = item["person_or_entity"]
            amount = item.get("amount", "")

            if t == "officer_loan":
                label = f"Officer Loan: {amount} — {entity}"
                nid = _nid(f"loan_{amount}_{entity}")
                nodes.append({"id": nid, "label": label, "file_type": "document",
                              "source_file": source_file, "type": "transaction"})
                edges.append({"source": nid, "target": _nid(entity),
                              "relation": "loan_to_officer", "confidence": "EXTRACTED",
                              "confidence_score": 1.0})
            elif t == "ip_transfer":
                label = f"IP Transfer: {amount} ({entity})"
                nid = _nid(f"ip_transfer_{amount}")
                nodes.append({"id": nid, "label": label, "file_type": "document",
                              "source_file": source_file, "type": "transaction"})
                edges.append({"source": _nid(entity), "target": nid,
                              "relation": "ip_transfer", "confidence": "EXTRACTED",
                              "confidence_score": 1.0})

        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def _filter_governance_tables(tables: list[Table]) -> list[Table]:
        """Keep only tables relevant to governance/diligence analysis.

        Matches on first-column labels (the entity names), not incidental mentions
        of keywords in data cells.
        """
        import re
        # Match table identity: first-col labels in first few rows
        keywords = re.compile(
            r'beneficial.ownership|related.party|name.and.principal|'
            r'option.award|executive.officer|director|'
            r'shares.purchased|stock.option.grant',
            re.IGNORECASE,
        )
        result = []
        for t in tables:
            # Check first-column values of early rows (the table's "identity")
            first_cols = " ".join(row[0] for row in t.rows[:5] if row and row[0].strip())
            header_text = " ".join(cell for row in (t.headers or []) for cell in row)
            identity = header_text + " " + first_cols
            if keywords.search(identity):
                result.append(t)
        return result

    def _get_tables(self, path: Path, content: str) -> list[Table]:
        suffix = path.suffix.lower()
        if suffix in (".html", ".htm"):
            return extract_html_tables(path, content)
        elif suffix in (".xlsx", ".xls"):
            from graphify.shared.spreadsheet import extract_excel_tables
            return extract_excel_tables(path)
        elif suffix == ".pdf":
            from graphify.shared.pdf_tables import extract_pdf_tables
            return extract_pdf_tables(path)
        return []


def _diligence_prompt_fragments() -> str:
    return """## Due Diligence Domain Extraction

Extract governance, legal, and risk entities from the document:

**Node types**: entity, person, contract, clause, risk, liability, asset, IP, role, transaction, metric, obligation
**Edge types**: party_to, controls, encumbered_by, licensor_of, material_dependency, officer_of, board_member_of, family_tie, related_party_transaction, self_dealing, asset_leaseback, obligation_to, revenue_dependency, contradicts, risk_factor, ip_transfer, accelerating_loss, nepotism, proceeds_to_insider, excludes_from_metric, maturity_mismatch, circular_flow, insider_cashout, controlled_company_exemption, board_independence

Instructions:
- Extract all named persons with their roles (officer, director, board member, landlord, etc.)
- Flag multi-role holders (same person as both officer AND landlord/vendor/board member)
- Extract related-party transactions with dollar amounts
- Extract contractual obligations and their counterparties
- Extract IP ownership and licensing arrangements
- Extract risk factors and their potential impact
- Look for narrative contradictions (aspirational claims vs. business mechanics)
- For governance tables: each person/role pair becomes a node
- Flag IP/trademark transfers or licensing between officers and the company (edge: ip_transfer, mark self_dealing if officer is on both sides)
- Flag accelerating losses: if net loss grows >30% period-over-period, add an accelerating_loss edge between the metric node and the company
- Flag use-of-proceeds that primarily retire insider debt or repay related-party obligations (edge: proceeds_to_insider)
- Flag employment or board appointment of family members of controlling persons (edge: nepotism)
- Flag personal use of company assets (jets, properties) by officers with dollar amounts
- Flag vanity projects or subsidiaries with no revenue attribution that serve officer interests
- Flag company loans to officers/executives: extract the loan amount, recipient, and terms as a node (type: transaction) with edge "loan_to_officer"
- Flag compensation concentration: if a single person receives >50% of total equity grants/options, extract both the individual amount and total pool

NON-GAAP METRICS:
- Extract each non-GAAP/adjusted metric as a node (type: metric, label: the metric name)
- For each real cost excluded from the metric, create a separate edge: excludes_from_metric (source: metric node, target: excluded cost node)
- This lets downstream analysis count how many real costs are stripped to create fake profitability
- Example: "Community Adjusted EBITDA" excludes G&A, development, pre-opening costs, stock comp → 4 separate excludes_from_metric edges

MATURITY MISMATCH:
- Compare the company's longest-duration financial commitment (e.g., 15-year leases) to its shortest-duration revenue source (e.g., month-to-month memberships)
- Create a maturity_mismatch edge between the obligation node and the revenue node
- Include metadata: long_term_duration, short_term_duration, long_term_amount, short_term_amount
- Do NOT flag standard debt (credit facilities, revolvers) — flag the structural mismatch between commitment duration and customer duration

RELATED-PARTY REVENUE GROWTH:
- If related-party revenue grows faster than total revenue, extract both figures and compute what % of total revenue growth came from related parties
- Include the percentage in the edge label (e.g., "related_party_revenue_growth: 19x vs 2x organic")

INSIDER CASH-OUTS:
- Extract any pre-IPO liquidity events for insiders: secondary share sales, loan proceeds used personally, dividends, consulting fees to founders
- Create insider_cashout edge (source: person, target: company) with dollar amount in label
- This includes loans FROM the company TO officers that were used to purchase personal assets

BOARD INDEPENDENCE:
- For each board member, assess independence: are they a major investor, business partner, family member, or employee?
- Create board_independence edge (source: director, target: company) with metadata: independent=true/false, reason if not independent
- Count total independent vs non-independent directors

CIRCULAR TRANSACTIONS:
- Detect when the same person/entity appears on both sides of a financial flow
- Example: officer buys property → company leases property from officer → rent payments fund officer's loan repayment to company
- Create circular_flow edge connecting the entities involved, with description of the cycle

CONTROLLED COMPANY:
- If the company declares "controlled company" status or equivalent, extract it as a node
- Create controlled_company_exemption edge listing which governance requirements are waived (e.g., independent board majority, independent compensation committee, independent nominating committee)

Mark inferred relationships (not explicitly stated) with confidence < 1.0.
"""


def _diligence_post_extract(extraction: dict) -> dict:
    """Post-extraction inference: conflict detection, edge validation, table linking."""
    nodes = extraction.get("nodes", [])
    edges = extraction.get("edges", [])

    _infer_conflicts(nodes, edges)
    _fix_mismatch_edges(nodes, edges)
    _link_tables(nodes, edges)

    return {"nodes": nodes, "edges": edges}


def _infer_conflicts(nodes: list[dict], edges: list[dict]) -> None:
    """If a person holds 2+ governance roles, create conflict_of_interest edges."""
    # Map person → list of roles
    governance_relations = {
        "officer_of", "board_member_of", "controls", "party_to",
        "related_party_transaction", "asset_leaseback",
    }
    person_roles: dict[str, list[dict]] = defaultdict(list)

    for edge in edges:
        if edge.get("relation") in governance_relations:
            person_roles[edge["source"]].append(edge)

    for person_id, roles in person_roles.items():
        if len(roles) < 2:
            continue
        # Create conflict edge between the two role targets
        role_types = {r.get("relation") for r in roles}
        # Conflict exists if roles span different categories
        internal = role_types & {"officer_of", "board_member_of", "controls"}
        external = role_types & {"party_to", "related_party_transaction", "asset_leaseback"}
        if internal and external:
            confidence = min(0.7 + 0.1 * len(roles), 0.95)
            edges.append({
                "source": person_id,
                "target": person_id,
                "relation": "conflict_of_interest",
                "confidence": confidence,
                "metadata": {
                    "roles": list(role_types),
                    "role_count": len(roles),
                },
            })


def _link_tables(nodes: list[dict], edges: list[dict]) -> None:
    """Bridge table nodes to semantic entity nodes via label matching."""
    from graphify.shared.tables import link_tables_to_entities

    table_nodes = [n for n in nodes if n.get("type") in ("table", "table_row")]
    semantic_nodes = [n for n in nodes if n.get("type") not in ("table", "table_row", "")]

    if not table_nodes or not semantic_nodes:
        return

    cross_edges = link_tables_to_entities(table_nodes, edges, semantic_nodes)
    edges.extend(cross_edges)


def _fix_mismatch_edges(nodes: list[dict], edges: list[dict]) -> None:
    """Validate edge endpoints match expected types; drop incorrect ones."""
    node_types = {n["id"]: n.get("type", "") for n in nodes}
    to_remove = []

    for i, edge in enumerate(edges):
        rel = edge.get("relation")
        if rel == "asset_liability_mismatch":
            src_type = node_types.get(edge["source"], "")
            tgt_type = node_types.get(edge["target"], "")
            # This edge should connect obligation → revenue/asset
            if src_type not in ("obligation", "liability") and tgt_type not in ("asset", "revenue", "metric"):
                to_remove.append(i)

    for i in reversed(to_remove):
        edges.pop(i)


def _diligence_post_build(G: nx.Graph) -> None:
    """Graph-level inference: type tagging and contradiction detection."""
    _infer_node_types(G)
    _infer_claim_contradictions(G)


def _infer_node_types(G: nx.Graph) -> None:
    """Tag nodes with type='person' or type='organization' based on their edge relations.

    For person-indicating relations like X_OF (e.g., CEO_OF), the person is the
    node with *fewer* connections (the individual), not the hub (the company).
    """
    _person_rels = {
        "CEO_OF", "CEO_AND_CHAIRMAN_OF", "CHAIRMAN_OF", "DIRECTOR_OF",
        "FOUNDER_OF", "PRESIDENT_OF", "CFO_OF", "COO_OF", "CTO_OF",
        "officer_of", "CONTROLS_MAJORITY_VOTING_POWER", "SOLE_HOLDER_OF",
        "CONTROLS",
    }
    _org_rels = {
        "SUBSIDIARY_OF", "CONSOLIDATES_VIE", "JV_PARTNER_IN",
        "INVESTED_IN", "ACQUIRED", "STOCKHOLDER_OF", "ISSUER_OF",
        "BORROWER_OF",
    }

    # For "_OF" person relations, the person is typically the lower-degree end
    for u, v, ed in G.edges(data=True):
        rel = ed.get("relation", "")
        if rel in _person_rels:
            # In "X CEO_OF Y", X is the person, Y is the org
            # Heuristic: the lower-degree node is the person
            if G.degree(u) <= G.degree(v):
                person, org = u, v
            else:
                person, org = v, u
            if not G.nodes[person].get("type"):
                G.nodes[person]["type"] = "person"
            if not G.nodes[org].get("type"):
                G.nodes[org]["type"] = "organization"
        elif rel in _org_rels:
            # Both ends are likely organizations
            for endpoint in (u, v):
                if not G.nodes[endpoint].get("type"):
                    G.nodes[endpoint]["type"] = "organization"


def _infer_claim_contradictions(G: nx.Graph, max_edges: int = 5) -> None:
    """Find aspirational claims contradicted by quantitative evidence in the graph.

    Only creates 'contradicts' edges when there is structural evidence of
    contradiction (e.g., a profitability claim node coexisting with an
    accelerating_loss edge, or a growth claim vs. a risk_factor node about
    sustainability). Does NOT inject editorial opinion about whether metrics
    are misleading — that belongs in the report, not graph structure.
    """
    # Find aspirational nodes with explicit contradiction signals
    aspirational = []
    contradiction_signals = []

    for node, data in G.nodes(data=True):
        if data.get("domain") != "diligence":
            continue
        node_type = data.get("type", "")
        community = data.get("community", -1)
        label = (data.get("label") or "").lower()

        # Aspirational: claim/mission/vision nodes
        if node_type in ("claim", "mission", "vision") and G.degree(node) <= 1:
            aspirational.append((node, community, label))

        # Contradiction signals: risk nodes that explicitly name failure of a claim
        if node_type == "risk" and any(kw in label for kw in (
            "may never achieve", "history of loss", "not sustainable",
            "unable to", "no assurance",
        )):
            contradiction_signals.append((node, community, label))

    # Only connect claims to risk factors that directly negate them
    added = 0
    for claim_node, claim_comm, claim_label in aspirational:
        if added >= max_edges:
            break
        for risk_node, risk_comm, risk_label in contradiction_signals:
            if added >= max_edges:
                break
            # Must be cross-community
            if claim_comm == risk_comm:
                continue
            # Require semantic overlap: the risk must reference something the claim asserts
            claim_words = set(claim_label.split()) - {"the", "a", "an", "of", "and", "to", "we", "our", "is", "are"}
            risk_words = set(risk_label.split())
            overlap = claim_words & risk_words
            if len(overlap) >= 2 and not G.has_edge(claim_node, risk_node):
                G.add_edge(
                    claim_node, risk_node,
                    relation="contradicted_by",
                    confidence="INFERRED",
                    confidence_score=0.75,
                    inferred=True,
                    domain="diligence",
                    evidence=f"Overlap: {overlap}",
                )
                added += 1


def _enrich_evidence(flag: dict, G: nx.Graph) -> None:
    """Attach evidence metadata to a red flag by looking up the source node."""
    node = flag.get("node", "")
    if not node or node not in G:
        return
    ndata = G.nodes[node]
    neighbors = []
    for u, v, d in G.edges(node, data=True):
        other = v if u == node else u
        neighbors.append({
            "node": other,
            "label": G.nodes[other].get("label", other) if other in G else other,
            "relation": d.get("relation", ""),
            "direction": "outbound" if u == node else "inbound",
        })
    flag["evidence"] = {
        "source_file": ndata.get("source_file", ""),
        "section": ndata.get("section", ""),
        "excerpt": ndata.get("label", ""),
        "data": ndata.get("data", {}),
        "description": ndata.get("description", ""),
        "neighbors": neighbors[:10],
    }


_NOTE_RE = re.compile(r"(?:See\s+)?Note\s+(\d+)", re.IGNORECASE)
_NOTE_HEADING_RE_TEMPLATE = r"Note\s+{num}\b[.\s\u00a0]+([^<]{0,120})"


def _resolve_cross_references(flags: list[dict], G: nx.Graph) -> None:
    """Scan flag labels for 'Note N' references and resolve from raw HTML."""
    # Collect all note numbers and their source files
    refs_needed: dict[str, set[int]] = {}  # source_file -> {note_nums}
    for flag in flags:
        evidence = flag.get("evidence", {})
        src = evidence.get("source_file", "")
        if not src:
            continue
        for m in _NOTE_RE.finditer(flag.get("label", "")):
            refs_needed.setdefault(src, set()).add(int(m.group(1)))

    if not refs_needed:
        return

    # Read each source file once and extract note content
    note_cache: dict[tuple[str, int], dict] = {}
    for src_file, note_nums in refs_needed.items():
        path = Path(src_file)
        if not path.is_absolute():
            # Try relative to common parents
            candidates = list(Path(".").rglob(path.name))
            path = candidates[0] if candidates else path
        if not path.exists():
            continue
        try:
            html = path.read_text(errors="replace")
        except OSError:
            continue
        # Strip HTML tags for plain-text search
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"\s+", " ", text)

        for num in note_nums:
            # Find note definition headings: "Note 22. Title" (not "See Note 22")
            # Prefer patterns that start a sentence/section (after period or start of block)
            heading_pat = re.compile(
                rf"(?<![Ss]ee\s)Note\s+{num}\.\s*([A-Z][^\n]{{0,100}})",
            )
            all_headings = list(heading_pat.finditer(text))
            if not all_headings:
                # Fallback: any "Note N." pattern
                heading_pat2 = re.compile(rf"Note\s+{num}\.\s*(.{{0,100}})")
                all_headings = list(heading_pat2.finditer(text))
            if not all_headings:
                continue
            # Use the last match (often the actual note vs. table-of-contents reference)
            heading_match = all_headings[-1]
            heading = heading_match.group(0).strip()[:120]
            # Grab content after heading (up to 500 chars or next Note heading)
            start = heading_match.end()
            next_note = re.search(r"Note\s+\d+\.", text[start:start + 2000])
            end = start + (next_note.start() if next_note else 500)
            excerpt = text[start:end].strip()[:500]
            note_cache[(str(src_file), num)] = {
                "note_num": num,
                "heading": heading,
                "excerpt": excerpt,
            }

    # Attach cross-references to flags
    for flag in flags:
        evidence = flag.get("evidence", {})
        src = evidence.get("source_file", "")
        if not src:
            continue
        xrefs = []
        for m in _NOTE_RE.finditer(flag.get("label", "")):
            num = int(m.group(1))
            cached = note_cache.get((src, num))
            if cached:
                xrefs.append(cached)
        if xrefs:
            evidence["cross_references"] = xrefs


def _generate_finding_description(flag: dict, G: nx.Graph) -> None:
    """Generate a plain-English finding description that makes sense to a layman."""
    ftype = flag.get("type", "")
    node = flag.get("node", "")
    label = flag.get("label", "")
    ndata = G.nodes[node] if node and node in G else {}
    data = ndata.get("data", {})

    # Extract dollar amounts from label or data
    amounts = re.findall(r"\$[\d,]+(?:\.\d+)?", label)
    amount_str = amounts[0] if amounts else ""

    # Get the parent entity (who does this relate to?)
    parent = ""
    for u, v, d in G.edges(node, data=True) if node and node in G else []:
        other = u if v == node else v
        if other in G and G.nodes[other].get("type") in ("company", "entity", "person"):
            parent = G.nodes[other].get("label", "")
            break

    if ftype == "related_party_exposure":
        # Extract what kind of related-party item this is
        label_lower = label.lower()
        if "revenue" in label_lower:
            finding = f"Company earns revenue from transactions with insiders or affiliated entities"
            if amounts:
                finding += f" ({', '.join(amounts[:2])})"
            finding += ". This revenue may not reflect arm's-length pricing and could vanish if the relationship ends."
        elif "expense" in label_lower:
            finding = f"Company pays expenses to related parties"
            if amounts:
                finding += f" ({', '.join(amounts[:2])})"
            finding += ". Insiders may be extracting value through inflated costs."
        elif "loan" in label_lower or "payable" in label_lower:
            finding = f"Company has financial obligations to insiders"
            if amount_str:
                finding += f" ({amount_str})"
            finding += ". Related-party debt creates conflicts between fiduciary duty and personal interest."
        elif "convertible" in label_lower:
            finding = f"Convertible financial instruments are held by related parties"
            if amount_str:
                finding += f" ({amount_str})"
            finding += ". Insiders hold preferential claims that could dilute other shareholders."
        elif "liabilit" in label_lower:
            finding = f"Company carries liabilities owed to insiders or affiliates"
            if amount_str:
                finding += f" ({amount_str})"
            finding += ". Money flowing to related parties rather than independent creditors."
        elif "interest" in label_lower:
            finding = f"Company pays interest to related parties"
            if amounts:
                finding += f" ({', '.join(amounts[:2])})"
            finding += ". Insiders earn guaranteed returns while other investors bear risk."
        elif "gain" in label_lower or "fair value" in label_lower:
            finding = f"Company reports gains on related-party financial instruments. "
            finding += "These paper gains may not represent real economic value and can be manipulated through related-party pricing."
        else:
            finding = f"Financial relationship between the company and its insiders: {label[:80]}. "
            finding += "Related-party transactions lack the competitive pressure that ensures fair pricing."
    elif ftype == "vie_consolidation":
        entity_label = label
        detail = flag.get("detail", "")
        finding = f"\"{entity_label}\" is a variable interest entity (VIE) — a separate legal structure "
        finding += "whose debts and losses may ultimately fall on the parent company, despite appearing off the balance sheet."
        if detail:
            finding += f" Relationship: {detail}."
    elif ftype == "key_person_risk":
        degree = flag.get("degree", 0)
        finding = f"\"{label}\" is connected to {degree} other entities in the organization. "
        finding += "If this person leaves, is incapacitated, or acts against company interests, "
        finding += "it could disrupt multiple critical relationships simultaneously."
    elif ftype == "compensation_concentration":
        # Parse the label for details
        pct_match = re.search(r"([\d.]+)%", label)
        name_match = re.search(r":\s*(\w+)", label)
        person = name_match.group(1) if name_match else "one individual"
        pct = pct_match.group(1) if pct_match else "majority"
        finding = f"{person} receives {pct}% of all equity compensation (stock options/grants). "
        finding += "This extreme concentration means one person captures most of the upside while "
        finding += "other employees and shareholders are diluted."
    elif ftype == "conflict_of_interest":
        finding = f"\"{label}\" holds roles that create conflicting loyalties — "
        finding += "they may be on both sides of a financial decision, making it impossible to act "
        finding += "purely in shareholders' best interests."
    elif ftype == "risk_factor":
        finding = f"The company explicitly discloses this risk: {label[:120]}."
    elif ftype == "concentration_risk":
        exposure = flag.get("exposure_pct")
        finding = f"A single customer or counterparty (\"{label}\") "
        if exposure:
            finding += f"accounts for {exposure:.0f}% of revenue. "
        else:
            finding += "represents a material share of revenue. "
        finding += "Losing this relationship would cause an immediate, significant revenue drop."
    else:
        finding = label

    flag["finding"] = finding


def red_flag_analyzer(G) -> list[dict]:
    """Detect red flags from graph structure: risk factors, related-party exposure, VIEs, key-person concentration."""
    flags = []

    # 1. Explicit risk factor edges (HAS_RISK_FACTOR)
    for u, v, data in G.edges(data=True):
        rel = data.get("relation", "")
        if rel == "HAS_RISK_FACTOR":
            label = G.nodes[v].get("label", str(v))
            # Classify severity by content
            label_lower = label.lower()
            if any(kw in label_lower for kw in ("related party", "dependence", "conflict", "loss")):
                severity = "high"
            elif any(kw in label_lower for kw in ("lease", "growth", "retention")):
                severity = "medium"
            else:
                severity = "low"
            flags.append({
                "type": "risk_factor",
                "node": v,
                "label": label,
                "severity": severity,
            })

    # 2. Related-party exposure: nodes with "related party" or "loan" in labels
    _rp_kw = re.compile(r"related.party|loan.*(officer|partie|employee)|self.deal", re.IGNORECASE)
    for node, data in G.nodes(data=True):
        label = data.get("label", "")
        if _rp_kw.search(label):
            # Check if it's a financial item (has dollar amounts or is in financial tables)
            has_amount = bool(re.search(r"\$[\d,]+|[\d,]+\.\d", label))
            # If it's a table row, also check the data values for dollar amounts
            if not has_amount and data.get("type") == "table_row":
                row_data = data.get("data", {})
                if any(re.search(r"\$[\d,]+|[\d,]+\.\d", str(v)) for v in row_data.values()):
                    has_amount = True
            
            flags.append({
                "type": "related_party_exposure",
                "node": node,
                "label": label,
                "severity": "high" if has_amount else "medium",
                "domain": data.get("domain", ""),
            })

    # 3. VIE consolidation (off-balance-sheet risk)
    for u, v, data in G.edges(data=True):
        rel = (data.get("relation") or "").lower()
        if "vie" in rel or "consolidat" in rel:
            flags.append({
                "type": "vie_consolidation",
                "node": v,
                "label": G.nodes[v].get("label", str(v)),
                "severity": "medium",
                "detail": f"{G.nodes[u].get('label', u)} → {G.nodes[v].get('label', v)}",
            })

    # 4. Key-person concentration: persons with high degree
    # Exclude the subject entity (highest-degree node) — it's the company being analyzed
    _top_node = max(G.nodes(), key=lambda n: G.degree(n)) if G.number_of_nodes() else None
    _kp_prefixes = ("director_of", "officer_of", "controls", "ceo_of", "founder_of")
    for node, data in G.nodes(data=True):
        if node == _top_node:
            continue
        ntype = data.get("type", "")
        # Skip nodes explicitly typed as company/entity/organization
        if ntype in ("company", "entity", "organization", "fund"):
            continue
        label = data.get("label", "")
        if ntype == "person" or (not ntype and any(
            any((d.get("relation") or "").lower().startswith(p) for p in _kp_prefixes)
            for _, _, d in G.edges(node, data=True)
        )):
            degree = G.degree(node)
            if degree >= 4:
                flags.append({
                    "type": "key_person_risk",
                    "node": node,
                    "label": label,
                    "degree": degree,
                    "severity": "high" if degree >= 8 else "medium",
                })

    # 5. Compensation concentration (from _extract_from_text or post_extract)
    _detect_compensation_concentration(G, flags)

    # 6. Conflict of interest edges
    for u, v, data in G.edges(data=True):
        if data.get("relation") == "conflict_of_interest":
            flags.append({
                "type": "conflict_of_interest",
                "node": u,
                "label": G.nodes[u].get("label", u),
                "severity": "high",
            })

    # Deduplicate by node
    seen = set()
    deduped = []
    for f in flags:
        key = (f["type"], f.get("node", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    # Generate human-readable finding descriptions
    for f in deduped:
        _generate_finding_description(f, G)

    # Enrich with evidence
    for f in deduped:
        _enrich_evidence(f, G)
    _resolve_cross_references(deduped, G)

    return sorted(deduped, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["severity"], 3))




def _detect_compensation_concentration(G, flags: list[dict]) -> None:
    """Flag when >50% of equity compensation goes to a single person."""
    # Strategy 1: Look for nodes created by _extract_from_text with "Compensation Concentration" label
    for node, data in G.nodes(data=True):
        label = data.get("label") or ""
        if "Compensation Concentration" in label:
            flags.append({
                "type": "compensation_concentration",
                "node": node,
                "label": label,
                "severity": "high",
                "detail": label,
            })
            return  # Already detected deterministically

    # Strategy 2: Look for compensation_concentration edges from post_extract
    for u, v, data in G.edges(data=True):
        if data.get("relation") == "compensation_concentration":
            flags.append({
                "type": "compensation_concentration",
                "node": u,
                "label": G.nodes[u].get("label", u),
                "severity": "high",
                "detail": f"Concentrated equity grants: {G.nodes[u].get('label', u)}",
            })
            return

    # Strategy 3: Heuristic — check node labels for concentration patterns
    for node, data in G.nodes(data=True):
        label = (data.get("label") or "").lower()
        if not ("option" in label or "grant" in label or "compensation" in label):
            continue
        # Look for percentage or ratio indicating concentration
        numbers = re.findall(r"[\d,]+\.?\d*", label.replace(",", ""))
        numbers = [float(n) for n in numbers if float(n) > 1000]
        if len(numbers) >= 2:
            total = max(numbers)
            individual = sorted(numbers)[-2] if len(numbers) > 2 else min(numbers)
            if individual > total:
                total, individual = individual, total
            if total > 0 and individual / total > 0.5:
                flags.append({
                    "type": "compensation_concentration",
                    "node": node,
                    "label": data.get("label", node),
                    "severity": "high",
                    "detail": f"~{individual/total:.0%} of equity grants to single person",
                })
                return


def key_person_risk_analyzer(G) -> list[dict]:
    """Identify high-degree persons or entities whose removal would fragment the graph."""
    results = []

    # Find person-like nodes: explicit type=person, nodes with officer/director edges,
    # or nodes named in "Dependence on X" risk factors
    _officer_prefixes = ("director_of", "officer_of", "controls", "ceo_of", "founder_of", "board_member_of")
    person_set: set = set()

    # Nodes with officer/director edges (either direction)
    for u, v, ed in G.edges(data=True):
        rel = (ed.get("relation") or "").lower()
        if any(rel.startswith(prefix) or rel == prefix for prefix in _officer_prefixes):
            person_set.add(u)
            # Also add v if it's the source of an inbound officer_of edge
            # (e.g., "The We Company -> Adam Neumann: officer_of")
            if rel.startswith("officer_of") or rel.startswith("director_of") or rel.startswith("ceo_of") or rel.startswith("founder_of"):
                person_set.add(v)

    # Explicit type=person
    for n, d in G.nodes(data=True):
        if d.get("type") == "person":
            person_set.add(n)

    # Nodes whose name appears in a "Dependence on X" risk factor label
    risk_labels = [
        G.nodes[n].get("label", "") for n in G.nodes()
        if "Dependence on" in G.nodes[n].get("label", "")
    ]
    for n, d in G.nodes(data=True):
        label = d.get("label", "")
        if label and any(label in rl for rl in risk_labels):
            person_set.add(n)

    # Exclude the highest-degree node — it's the subject entity of the corpus
    # (e.g., "The We Company" in a WeWork S-1) and trivially fragments the graph.
    top_node = max(G.nodes(), key=lambda n: G.degree(n)) if G.number_of_nodes() else None
    person_nodes = [n for n in person_set if n != top_node]

    for person in person_nodes:
        neighbors = set(G.neighbors(person))
        if len(neighbors) < 3:
            continue
        # Check if removing this node disconnects neighbors
        subgraph = G.subgraph([n for n in G.nodes() if n != person])
        neighbor_components = set()
        for n in neighbors:
            if n in subgraph:
                for i, comp in enumerate(nx.connected_components(subgraph)):
                    if n in comp:
                        neighbor_components.add(i)
                        break
        if len(neighbor_components) > 1:
            results.append({
                "person": person,
                "label": G.nodes[person].get("label", person),
                "fragments_into": len(neighbor_components),
                "connections": len(neighbors),
            })
        elif len(neighbors) >= 5:
            # Even if not fragmenting, high-degree persons are a concentration risk
            results.append({
                "person": person,
                "label": G.nodes[person].get("label", person),
                "fragments_into": 0,
                "connections": len(neighbors),
            })

    return sorted(results, key=lambda x: (x["fragments_into"], x["connections"]), reverse=True)


# --- Registration ---

_SPEC = DomainSpec(
    name="diligence",
    extractors=[DiligenceExtractor()],
    relations={
        "governance": ["officer_of", "board_member_of", "controls", "family_tie"],
        "conflict": ["related_party_transaction", "self_dealing", "asset_leaseback", "conflict_of_interest", "ip_transfer"],
        "financial": ["obligation_to", "revenue_dependency", "asset_liability_mismatch", "loan_to_officer"],
        "disclosure": ["deviates_from_gaap", "contradicted_by"],
        "risk": ["risk_factor", "concentration_risk", "material_dependency", "key_person", "compensation_concentration"],
    },
    node_types=["entity", "person", "contract", "clause", "risk", "liability", "asset", "IP", "role", "transaction"],
    prompt_fragments=_diligence_prompt_fragments,
    post_extract=_diligence_post_extract,
    post_build=_diligence_post_build,
    analyzers=[red_flag_analyzer, key_person_risk_analyzer],
)

register(_SPEC)
