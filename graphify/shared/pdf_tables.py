"""PDF table extraction — 3-tier strategy (basic → plumber → vision)."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Callable

from graphify.shared.tables import Table


def extract_pdf_tables(
    path: Path,
    *,
    strategy: str = "auto",
    llm_call: Callable | None = None,
) -> list[Table]:
    """
    Unified PDF table extraction.

    strategy:
      "basic"    - whitespace heuristic (no extra deps)
      "plumber"  - pdfplumber geometry (accurate)
      "vision"   - LLM vision (scanned docs)
      "auto"     - try plumber → basic → vision for remaining
    """
    if not path.exists():
        return []

    if strategy == "plumber":
        return _extract_plumber(path)
    elif strategy == "basic":
        return _extract_basic(path)
    elif strategy == "vision":
        return _extract_vision(path, llm_call) if llm_call else []
    else:  # auto
        try:
            tables = _extract_plumber(path)
            if tables:
                return tables
        except ImportError:
            pass
        tables = _extract_basic(path)
        if tables:
            return tables
        if llm_call:
            return _extract_vision(path, llm_call)
        return []


# --- Tier 1: Basic (whitespace alignment heuristic) ---


def _extract_basic(path: Path) -> list[Table]:
    """Reconstruct tables from pypdf text using whitespace alignment."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return []

    reader = PdfReader(str(path))
    tables = []

    for page_num, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        for table in _find_aligned_blocks(text, page_num, path):
            tables.append(table)

    return tables


def _find_aligned_blocks(text: str, page_num: int, path: Path) -> list[Table]:
    """Detect runs of lines where whitespace gaps align vertically."""
    lines = text.split("\n")
    tables = []
    current_block: list[tuple[str, list[int]]] = []

    for line in lines:
        # Find column boundaries: 2+ spaces between tokens
        gaps = [m.start() for m in re.finditer(r' {2,}', line)]
        if len(gaps) >= 1 and len(line.strip()) > 5:
            current_block.append((line, gaps))
        else:
            if len(current_block) >= 3:
                tables.append(_block_to_table(current_block, page_num, path, len(tables)))
            current_block = []

    if len(current_block) >= 3:
        tables.append(_block_to_table(current_block, page_num, path, len(tables)))

    return tables


def _block_to_table(
    block: list[tuple[str, list[int]]], page_num: int, path: Path, table_idx: int
) -> Table:
    """Split aligned text block into columns using consensus gap positions."""
    all_gaps: Counter = Counter()
    for _, gaps in block:
        for g in gaps:
            # Bucket to nearest 3 chars (handles minor alignment drift)
            all_gaps[g // 3 * 3] += 1

    # Keep gaps that appear in >40% of rows
    threshold = len(block) * 0.4
    split_points = sorted(g for g, c in all_gaps.items() if c >= threshold)

    rows = []
    for line, _ in block:
        row = _split_at(line, split_points)
        rows.append(row)

    # First row as header heuristic
    headers: list[list[str]] = []
    body = rows
    if rows:
        first = rows[0]
        numeric_in_first = sum(1 for c in first if _is_numeric(c))
        if numeric_in_first == 0 and len(rows) > 1:
            headers = [first]
            body = rows[1:]

    return Table(
        id=f"{path.stem}__p{page_num + 1}_t{table_idx + 1}",
        caption=None,
        headers=headers,
        rows=body,
        source_file=str(path),
    )


def _split_at(line: str, split_points: list[int]) -> list[str]:
    """Split a line at the given character positions."""
    if not split_points:
        return [line.strip()]
    parts = []
    prev = 0
    for sp in split_points:
        if sp < len(line):
            parts.append(line[prev:sp].strip())
            prev = sp
    parts.append(line[prev:].strip())
    return [p for p in parts if p or len(parts) <= 1] or [""]


def _is_numeric(s: str) -> bool:
    s = s.replace(",", "").replace("$", "").replace("%", "").strip()
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


# --- Tier 2: pdfplumber (geometry-based) ---


def _extract_plumber(path: Path) -> list[Table]:
    """Use pdfplumber's line-intersection algorithm for accurate extraction."""
    import pdfplumber

    tables = []
    with pdfplumber.open(str(path)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            page_tables = page.find_tables()
            for i, pt in enumerate(page_tables):
                raw = pt.extract()
                if not raw or len(raw) < 2:
                    continue
                rows = [[c or "" for c in row] for row in raw]
                # First row as header
                headers = [rows[0]]
                body = rows[1:]
                tables.append(Table(
                    id=f"{path.stem}__p{page_num + 1}_t{i + 1}",
                    caption=None,
                    headers=headers,
                    rows=body,
                    source_file=str(path),
                ))
    return tables


# --- Tier 3: Vision LLM fallback ---


def _extract_vision(path: Path, llm_call: Callable) -> list[Table]:
    """Send page images to vision LLM for table extraction."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return []

    reader = PdfReader(str(path))
    tables = []

    for page_num in range(min(len(reader.pages), 20)):  # cap at 20 pages
        prompt = (
            "Extract all tables from this PDF page. Return JSON:\n"
            '{"tables": [{"caption": "...", "headers": [["col1", "col2"]], '
            '"rows": [["val1", "val2"]]}]}\n'
            "If no tables, return {\"tables\": []}."
        )
        try:
            response = llm_call(
                system=prompt,
                page_path=str(path),
                page_num=page_num,
            )
            parsed = json.loads(response)
            for i, t in enumerate(parsed.get("tables", [])):
                tables.append(Table(
                    id=f"{path.stem}__p{page_num + 1}_vision_t{i + 1}",
                    caption=t.get("caption"),
                    headers=t.get("headers", []),
                    rows=t.get("rows", []),
                    source_file=str(path),
                ))
        except (json.JSONDecodeError, Exception):
            continue

    return tables
