"""HTML table extraction with structure preservation and layout detection.

Uses BeautifulSoup for robust parsing and a score-based filter to separate
data tables from layout/TOC noise.  Domain plugins call extract_html_tables()
then apply their own keyword filters to decide which tables are relevant.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Table:
    """Unified table representation — all sources (HTML, Excel, PDF) converge here."""

    id: str
    caption: str | None
    headers: list[list[str]]  # multi-row headers (thead rows)
    rows: list[list[str]]  # body cells, preserving column alignment
    source_file: str
    score: float = 0.0  # 0.0–1.0 data density score
    row_span_map: dict | None = None  # {(row,col): span} for merged cells


# --- Financial cell detection ---

_FINANCIAL_RE = re.compile(r'^[\$\(\)\d,\.\-\s%\u2014\u2013]+$')
_HAS_DIGIT = re.compile(r'\d')
_YEAR_RE = re.compile(r'^20\d{2}$')


def _clean_cell(text: str) -> str:
    """Strip whitespace, decode HTML entities, normalize unicode spaces."""
    return text.replace('\xa0', ' ').replace('\u200b', '').strip()


def _is_financial_cell(text: str) -> bool:
    """Check if a cell contains financial data (numbers, dollars, percentages)."""
    cleaned = _clean_cell(text).replace(' ', '')
    if not cleaned:
        return False
    return bool(_FINANCIAL_RE.match(cleaned) and _HAS_DIGIT.search(cleaned))


def _parse_numeric(text: str) -> float | None:
    """Parse financial text into a float.

    Handles: $1,234  (1,234) → negative  12.3%  1,234,567
    Returns None if not parseable.
    """
    cleaned = _clean_cell(text).replace(' ', '')
    if not cleaned or not _HAS_DIGIT.search(cleaned):
        return None

    negative = cleaned.startswith('(') and ')' in cleaned
    stripped = cleaned.replace('$', '').replace(',', '').replace('(', '').replace(')', '').replace('%', '').replace('\u2014', '').replace('\u2013', '')
    if not stripped:
        return None

    try:
        value = float(stripped)
        if negative:
            value = -abs(value)
        return value
    except ValueError:
        return None


# --- Stable ID generation ---

def _make_id(*parts: str) -> str:
    """Build a stable node ID from one or more name parts."""
    combined = "_".join(p.strip("_.") for p in parts if p)
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", combined)
    return cleaned.strip("_").lower()[:80]


# --- Table scoring ---

def _score_data(rows: list[list[str]], toc_links: int = 0, is_presentation: bool = False) -> float:
    """Score table data from 0.0 (noise) to 1.0 (dense data).

    Three hard gates that return 0.0:
      Gate 1: TOC detection (3+ internal anchor links)
      Gate 2: Size minimum (data_rows < 3 or financial_cells < 4)
      Gate 3: Numeric density (financial_ratio < 0.20)

    Then a continuous score from the remaining signals.
    """
    # Gate 1: TOC table — lots of internal anchor links
    if toc_links > 3:
        return 0.0

    # role="presentation"
    if is_presentation:
        return 0.0

    data_rows = 0
    financial_cells = 0
    total_nonempty = 0
    has_year_header = False

    for cells in rows:
        nonempty = [t for t in cells if t.strip()]
        if len(nonempty) >= 2:
            data_rows += 1

        for text in nonempty:
            total_nonempty += 1
            if _is_financial_cell(text):
                financial_cells += 1
            if _YEAR_RE.match(_clean_cell(text)):
                has_year_header = True

    # Gate 2: too small
    if data_rows < 3 or financial_cells < 4:
        return 0.0

    # Gate 3: too sparse
    ratio = financial_cells / total_nonempty if total_nonempty else 0
    if ratio < 0.20:
        return 0.0

    # Continuous score
    score = 0.0
    score += min(ratio / 0.7, 1.0) * 0.5       # density component
    score += min(data_rows / 15, 1.0) * 0.3     # size component
    score += 0.2 if has_year_header else 0.0     # year header bonus

    return round(min(score, 1.0), 2)


def _score_table(table_tag) -> float:
    """Score a BeautifulSoup table element."""
    rows = []
    for tr in table_tag.find_all('tr'):
        cells = tr.find_all(['td', 'th'])
        rows.append([c.get_text(strip=True) for c in cells])

    toc_links = len(table_tag.find_all('a', href=lambda h: h and h.startswith('#')))
    is_presentation = (table_tag.get('role') or '').lower() == 'presentation'

    return _score_data(rows, toc_links=toc_links, is_presentation=is_presentation)


# --- Header extraction ---

def _detect_table_heading(table_tag) -> str:
    """Walk backward from a table to find its preceding heading or description."""
    for prev in table_tag.find_all_previous(['b', 'p', 'div'], limit=10):
        text = prev.get_text(strip=True)
        if text and 10 < len(text) < 200 and not text.lower().startswith('table of'):
            return text[:120]
    return ""


def _extract_headers(table_tag) -> list[str]:
    """Extract column headers from the first few rows.

    Strategy:
    1. If the table has explicit <th> elements, use those first.
    2. Otherwise scan header rows for year patterns (best column identifiers
       for SEC financial tables).
    3. Fall back to descriptive text headers.
    """
    rows = table_tag.find_all('tr')

    # Strategy 1: explicit <th> elements in the first row that has them
    for row in rows[:5]:
        th_cells = row.find_all('th')
        if th_cells:
            headers = [_clean_cell(c.get_text(strip=True)) for c in th_cells]
            meaningful = [h for h in headers if h and len(h) > 1]
            if meaningful:
                return meaningful

    # Strategy 2+3: scan for years or descriptive text
    year_headers = []
    descriptive_headers = []

    for row in rows[:8]:
        cells = row.find_all(['td', 'th'])
        nonempty = [(i, _clean_cell(c.get_text(strip=True))) for i, c in enumerate(cells) if c.get_text(strip=True)]

        if not nonempty:
            continue

        # If this row has 2+ financial cells in non-first positions, it's data — stop
        non_year_financial = sum(
            1 for i, t in nonempty
            if i > 0 and _is_financial_cell(t) and not _YEAR_RE.match(_clean_cell(t))
        )
        if non_year_financial >= 2:
            break

        for _, text in nonempty:
            if _YEAR_RE.match(text):
                year_headers.append(text)

        for _, text in nonempty:
            if not _YEAR_RE.match(text) and len(text) > 3 and not _is_financial_cell(text):
                descriptive_headers.append(text)

    # Prefer year headers; disambiguate duplicates
    if year_headers:
        seen: dict[str, int] = {}
        result = []
        for h in year_headers:
            if h in seen:
                seen[h] += 1
                result.append(f"{h}_{seen[h]}")
            else:
                seen[h] = 1
                result.append(h)
        return result

    return descriptive_headers[:5]


# --- Data row extraction ---

def _extract_data_rows(table_tag, headers: list[str]) -> list[dict]:
    """Extract data rows from a table.

    Returns list of dicts with:
      - label: row label (first text column)
      - columns: {header: value} mapping
      - raw_values: list of financial cell texts
    """
    rows = table_tag.find_all('tr')
    data_rows = []

    for row in rows:
        cells = row.find_all(['td', 'th'])
        cell_texts = [_clean_cell(c.get_text(strip=True)) for c in cells]

        nonempty = [t for t in cell_texts if t]
        if not nonempty:
            continue

        # Merge standalone $ with next cell
        merged = []
        skip_next = False
        for k, text in enumerate(cell_texts):
            if skip_next:
                skip_next = False
                continue
            if text in ('$', '$(') and k + 1 < len(cell_texts) and cell_texts[k + 1]:
                merged.append(text + cell_texts[k + 1])
                skip_next = True
            else:
                merged.append(text)

        # Find label and financial values
        financial_values = []
        label = None

        for text in merged:
            if not text:
                continue
            if label is None and not _is_financial_cell(text) and len(text) > 1:
                label = text
            elif _is_financial_cell(text):
                financial_values.append(text)

        if not label or not financial_values:
            continue

        # Skip rows where all "financial" values are actually years
        if all(_YEAR_RE.match(v.replace(',', '').strip()) for v in financial_values):
            continue

        # Map values to headers
        columns = {}
        if headers and len(financial_values) <= len(headers):
            for j, val in enumerate(financial_values):
                columns[headers[j]] = val
        else:
            for j, val in enumerate(financial_values):
                columns[f"col_{j}"] = val

        data_rows.append({
            'label': label,
            'columns': columns,
            'raw_values': financial_values,
        })

    return data_rows


# --- Public API ---

def extract_html_tables(path: Path, html: str, min_score: float = 0.3) -> list[Table]:
    """Parse <table> elements, score them, return data tables above threshold.

    Args:
        path: Source file path (for IDs and metadata).
        html: Raw HTML string.
        min_score: Minimum table score (0.0-1.0). Default 0.3.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # Fallback to regex-based parsing if bs4 not available
        return _extract_html_tables_fallback(path, html, min_score=min_score)

    soup = BeautifulSoup(html, 'html.parser')
    all_tables = soup.find_all('table', recursive=True)

    tables = []
    for i, table_tag in enumerate(all_tables):
        # Skip nested tables (only process top-level)
        if table_tag.find_parent('table'):
            continue

        score = _score_table(table_tag)
        if score < min_score:
            continue

        heading = _detect_table_heading(table_tag)
        headers_list = _extract_headers(table_tag)
        data_rows = _extract_data_rows(table_tag, headers_list)

        if not data_rows:
            continue

        # Build Table with raw row data for callers that need it
        raw_rows = []
        for row_data in data_rows:
            raw_row = [row_data['label']] + row_data['raw_values']
            raw_rows.append(raw_row)

        # Caption from <caption> element or preceding heading
        cap_tag = table_tag.find('caption')
        caption = cap_tag.get_text(strip=True) if cap_tag else (heading or None)

        tables.append(Table(
            id=_make_id(path.stem, "table", str(i)),
            caption=caption,
            headers=[headers_list] if headers_list else [],
            rows=raw_rows,
            source_file=str(path),
            score=score,
        ))

    return tables


def table_to_nodes_edges(table: Table, domain: str) -> dict:
    """Convert a Table into graph nodes+edges.

    Creates a table node + one row node per data row.
    Stores parsed numeric values on row nodes for quantitative queries.
    """
    if not table.rows:
        return {"nodes": [], "edges": []}

    # Column names from headers, or generate from position
    col_names = table.headers[-1] if table.headers and table.headers[-1] else []

    table_label = table.caption or _infer_table_label(table)
    if not table_label:
        return {"nodes": [], "edges": []}

    nodes = [{"id": table.id, "label": table_label, "type": "table",
              "headers": table.headers, "source_file": table.source_file,
              "score": table.score}]
    edges = []
    seen_ids: set[str] = set()
    seen_ids.add(table.id)

    prev_row_id = None
    for i, row in enumerate(table.rows):
        if not row or not row[0].strip():
            continue
        label = row[0].strip()

        # Skip rows whose label is purely numeric (not a named entity)
        if re.match(r'^[\d,$%.()\-\u2013\u2014\s]+$', label):
            continue

        # Skip separator rows (all other cells empty/dashes)
        if len(row) > 1 and all(not cell.strip() or cell.strip() in ("\u2014", "-", "\u2013") for cell in row[1:]):
            continue

        # Stable ID based on content
        row_id = _make_id(table.id, label)
        if row_id in seen_ids:
            row_id = _make_id(table.id, label, str(i))
        seen_ids.add(row_id)

        # Map cells to column names
        row_data = {}
        numeric_values = {}
        for j, val in enumerate(row):
            col_name = col_names[j] if j < len(col_names) else f"col_{j}"
            row_data[col_name] = val
            if j > 0:  # skip label column
                parsed = _parse_numeric(val)
                if parsed is not None:
                    numeric_values[col_name] = parsed

        node = {"id": row_id, "label": label, "type": "table_row",
                "data": row_data, "source_file": table.source_file}
        if numeric_values:
            node["numeric_values"] = numeric_values
        nodes.append(node)

        edges.append({"source": table.id, "target": row_id,
                      "relation": "contains_row", "confidence": "EXTRACTED",
                      "confidence_score": 1.0})

        # Preserve row ordering
        if prev_row_id:
            edges.append({"source": prev_row_id, "target": row_id,
                          "relation": "followed_by", "confidence": "EXTRACTED",
                          "confidence_score": 1.0})
        prev_row_id = row_id

    # If no valid rows, discard
    if len(nodes) == 1:
        return {"nodes": [], "edges": []}

    return {"nodes": nodes, "edges": edges}


def link_tables_to_entities(
    table_nodes: list[dict],
    table_edges: list[dict],
    semantic_nodes: list[dict],
) -> list[dict]:
    """Create cross-edges linking table row nodes to matching semantic entity nodes.

    Matches table row labels to semantic node labels via normalized string matching.
    Requires labels to be at least 5 characters to avoid spurious short matches.
    """
    # Build lookup of normalized semantic labels → node ids
    semantic_lookup: dict[str, str] = {}
    for node in semantic_nodes:
        label = (node.get("label") or "").strip().lower()
        if label and len(label) > 4:
            semantic_lookup[label] = node["id"]
            # Also index first N significant words for partial matching
            words = [w for w in re.sub(r"[^a-z0-9\s]", "", label).split() if len(w) > 2]
            if len(words) >= 3:
                key = " ".join(words[:4])
                semantic_lookup[key] = node["id"]

    cross_edges = []
    for node in table_nodes:
        if node.get("type") != "table_row":
            continue
        label = (node.get("label") or "").strip().lower()
        if not label or len(label) < 5:
            continue

        # Exact match
        if label in semantic_lookup:
            cross_edges.append({
                "source": node["id"],
                "target": semantic_lookup[label],
                "relation": "table_reference",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
            })
            continue

        # Best prefix match — score all candidates, pick longest overlap
        best_target = None
        best_overlap = 0
        for sem_label, sem_id in semantic_lookup.items():
            if sem_label.startswith(label) or label.startswith(sem_label):
                overlap = min(len(label), len(sem_label))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_target = sem_id

        if best_target and best_overlap >= 5:
            cross_edges.append({
                "source": node["id"],
                "target": best_target,
                "relation": "table_reference",
                "confidence": "INFERRED",
                "confidence_score": 0.85,
            })

    return cross_edges


def table_to_markdown(table: Table) -> str:
    """Render as aligned markdown for LLM consumption."""
    lines = []
    if table.headers:
        for hrow in table.headers:
            lines.append("| " + " | ".join(hrow) + " |")
        lines.append("|" + "|".join("---" for _ in table.headers[-1]) + "|")
    for row in table.rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def is_data_table_finance(rows: list[list[str]]) -> bool:
    """Finance-specific: tables with $ amounts, %, dates are almost always data."""
    flat = " ".join(cell for row in rows for cell in row)
    has_currency = bool(re.search(r'[\$\u20ac\u00a3\u00a5]\s*[\d,]+', flat))
    has_pct = bool(re.search(r'\d+\.?\d*\s*%', flat))
    has_dates = bool(re.search(r'(FY|Q[1-4]|20\d{2}|19\d{2})', flat))
    return has_currency or has_pct or has_dates


# --- Fallback parser (no bs4) ---

def _extract_html_tables_fallback(path: Path, html: str, min_score: float = 0.3) -> list[Table]:
    """Regex+HTMLParser fallback when BeautifulSoup is not installed."""
    tables = []
    segments = _find_table_segments(html)

    for i, (table_html, caption) in enumerate(segments):
        rows, has_th, metadata = _parse_table_html(table_html)
        if not rows:
            continue

        score = _score_data(rows, toc_links=metadata['toc_links'], is_presentation=metadata['is_presentation'])
        if score < min_score:
            continue

        headers, body = _split_header(rows, has_th)
        tables.append(Table(
            id=_make_id(path.stem, "table", str(i)),
            caption=caption,
            headers=headers,
            rows=body,
            source_file=str(path),
            score=score,
        ))

    return tables


def _find_table_segments(html: str) -> list[tuple[str, str | None]]:
    """Find top-level <table>...</table> segments with optional captions."""
    segments = []
    pattern = re.compile(r'<table[^>]*>(.*?)</table>', re.DOTALL | re.IGNORECASE)
    for m in pattern.finditer(html):
        table_html = m.group(0)
        cap_match = re.search(r'<caption[^>]*>(.*?)</caption>', table_html, re.DOTALL | re.IGNORECASE)
        caption = cap_match.group(1).strip() if cap_match else None
        segments.append((table_html, caption))
    return segments


from html.parser import HTMLParser


class _TableHTMLParser(HTMLParser):
    """Parse a single <table> element into rows of cells."""

    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self.current_row: list[str] = []
        self.cell_buf: str = ""
        self.in_cell: bool = False
        self.has_th: bool = False
        self.nested_depth: int = 0
        self.toc_links: int = 0
        self.is_presentation: bool = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "table":
            self.nested_depth += 1
            if self.nested_depth == 1:
                if attrs_dict.get('role') == 'presentation':
                    self.is_presentation = True
            return

        if self.nested_depth > 1:
            return

        if tag == "a":
            href = attrs_dict.get('href', '')
            if href.startswith('#'):
                self.toc_links += 1

        if tag in ("td", "th"):
            self.in_cell = True
            self.cell_buf = ""
            if tag == "th":
                self.has_th = True
        elif tag == "tr":
            self.current_row = []

    def handle_endtag(self, tag):
        if tag == "table":
            self.nested_depth -= 1
            return
        if self.nested_depth > 1:
            return
        if tag in ("td", "th"):
            self.current_row.append(self.cell_buf.strip())
            self.in_cell = False
        elif tag == "tr":
            if self.current_row:
                self.rows.append(self.current_row)

    def handle_data(self, data):
        if self.in_cell and self.nested_depth <= 1:
            self.cell_buf += data


def _parse_table_html(html: str) -> tuple[list[list[str]], bool, dict]:
    """Parse table HTML into rows + whether <th> was present + metadata."""
    parser = _TableHTMLParser()
    parser.feed(html)
    metadata = {
        'toc_links': parser.toc_links,
        'is_presentation': parser.is_presentation,
    }
    return parser.rows, parser.has_th, metadata


def _is_layout_table(html: str, rows: list[list[str]], has_th: bool) -> bool:
    """Return True if this table is used for page layout, not data."""
    if len(rows) <= 1 and all(len(r) <= 1 for r in rows):
        return True
    if html.lower().count("<table") > 1:
        return True
    if 'role="presentation"' in html.lower() or "role='presentation'" in html.lower():
        return True
    col_counts = [len(r) for r in rows if r]
    if re.search(r'width\s*[=:]\s*["\']?100%', html, re.IGNORECASE):
        if col_counts and max(col_counts) <= 2:
            return True
    if col_counts and max(col_counts) <= 1:
        return True
    return False


def _split_header(rows: list[list[str]], has_th: bool) -> tuple[list[list[str]], list[list[str]]]:
    """Split rows into headers and body."""
    if not rows:
        return [], []
    if has_th:
        return [rows[0]], rows[1:]
    first = rows[0]
    numeric_in_first = sum(1 for c in first if _is_numeric(c))
    if numeric_in_first == 0 and len(rows) > 1:
        rest_flat = " ".join(c for r in rows[1:] for c in r)
        if re.search(r'\d', rest_flat):
            return [first], rows[1:]
    return [], rows


def _is_numeric(s: str) -> bool:
    s = s.replace(",", "").replace("$", "").replace("%", "").strip()
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def _infer_table_label(table: Table) -> str:
    """Infer a readable label from table content when no caption exists."""
    if table.headers and table.headers[0]:
        meaningful = [h for h in table.headers[0] if h.strip()]
        if meaningful:
            return " | ".join(meaningful)[:80]
    for row in table.rows:
        for cell in row:
            if cell.strip() and len(cell.strip()) >= 5:
                return cell.strip()[:80]
    return ""
