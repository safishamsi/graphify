"""Deterministic structural extraction from prose documents. Outputs nodes+edges dicts.

Unlike extract.py (which uses tree-sitter AST parsing for code files), this module
handles non-code corpora: markdown, plain text, reStructuredText, Jupyter notebooks,
PDF, and DOCX files. It parses document structure (headings, sections, paragraphs)
deterministically and builds a structural graph without any LLM calls.

The LLM-based semantic extraction for prose mode happens in skill.md subagent prompts,
not here. This module provides the structural backbone that semantic extraction builds on.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# ── ID normalization ─────────────────────────────────────────────────────────

def _make_id(*parts: str) -> str:
    """Build a stable node ID from one or more name parts.

    Normalizes to snake_case for cross-file deduplication: "Gradient Descent"
    in file A and "gradient descent" in file B both map to "gradient_descent".
    """
    combined = "_".join(p.strip("_.") for p in parts if p)
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", combined)
    return cleaned.strip("_").lower()


# ── File type detection ──────────────────────────────────────────────────────

_PROSE_EXTENSIONS = {".md", ".txt", ".rst", ".ipynb", ".pdf", ".docx"}


def _classify_file_type(path: Path) -> str:
    """Return the file_type string for a prose file."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "paper"
    return "document"


# ── Document readers ─────────────────────────────────────────────────────────

def _read_markdown(path: Path) -> str:
    """Read a markdown file, stripping YAML frontmatter."""
    text = path.read_text(encoding="utf-8", errors="replace")
    # Strip YAML frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:]
    return text


def _read_plain_text(path: Path) -> str:
    """Read a plain text or rst file."""
    return path.read_text(encoding="utf-8", errors="replace")


def _read_ipynb(path: Path) -> str:
    """Read a Jupyter notebook, extracting markdown and code cell sources."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        nb = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw

    parts: list[str] = []
    for cell in nb.get("cells", []):
        cell_type = cell.get("cell_type", "")
        source = "".join(cell.get("source", []))
        if cell_type == "markdown":
            parts.append(source)
        elif cell_type == "code":
            parts.append(f"```\n{source}\n```")
    return "\n\n".join(parts)


def _read_file(path: Path) -> str:
    """Read a prose file and return its text content.

    Supports: .md, .txt, .rst, .ipynb
    For .pdf and .docx, returns empty string (these require external libraries
    and are handled by the LLM subagent via vision or tool use).
    """
    suffix = path.suffix.lower()
    if suffix == ".md":
        return _read_markdown(path)
    if suffix == ".ipynb":
        return _read_ipynb(path)
    if suffix in (".txt", ".rst"):
        return _read_plain_text(path)
    # PDF and DOCX: structural parsing not possible without external deps.
    # The LLM subagent handles these via vision/tool use.
    return ""


# ── Structural parsing ───────────────────────────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_RST_HEADING_RE = re.compile(
    r"^(.+)\n([=\-~^\"\'`]+)$", re.MULTILINE
)

# RST underline chars ordered by conventional nesting depth
_RST_LEVELS = {"=": 1, "-": 2, "~": 3, "^": 4, '"': 5, "'": 5, "`": 5}


def _extract_headings_md(text: str) -> list[tuple[int, str]]:
    """Extract (level, title) pairs from markdown headings."""
    results: list[tuple[int, str]] = []
    for match in _HEADING_RE.finditer(text):
        level = len(match.group(1))
        title = match.group(2).strip()
        if title:
            results.append((level, title))
    return results


def _extract_headings_rst(text: str) -> list[tuple[int, str]]:
    """Extract (level, title) pairs from reStructuredText headings."""
    results: list[tuple[int, str]] = []
    for match in _RST_HEADING_RE.finditer(text):
        title = match.group(1).strip()
        underline_char = match.group(2)[0]
        level = _RST_LEVELS.get(underline_char, 3)
        if title and len(match.group(2)) >= len(title):
            results.append((level, title))
    return results


def _extract_headings(text: str, suffix: str) -> list[tuple[int, str]]:
    """Extract headings from document text based on file type."""
    if suffix == ".rst":
        return _extract_headings_rst(text)
    # Default to markdown-style headings (works for .md, .txt, .ipynb)
    return _extract_headings_md(text)


# ── Structural graph builder ─────────────────────────────────────────────────

def _build_file_node(path: Path, file_type: str) -> dict[str, Any]:
    """Create a node representing the file itself."""
    stem = path.stem
    return {
        "id": _make_id(stem),
        "label": stem,
        "file_type": file_type,
        "source_file": str(path),
    }


def _build_section_nodes(
    headings: list[tuple[int, str]],
    path: Path,
    file_type: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build nodes for each heading/section and 'contains' edges from parent sections.

    Returns (nodes, edges).
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    str_path = str(path)
    file_id = _make_id(path.stem)

    # Stack tracks (level, node_id) for parent resolution
    stack: list[tuple[int, str]] = [(0, file_id)]

    for level, title in headings:
        node_id = _make_id(title)
        node = {
            "id": node_id,
            "label": title,
            "file_type": file_type,
            "source_file": str_path,
        }
        nodes.append(node)

        # Pop stack until we find a parent at a higher level
        while len(stack) > 1 and stack[-1][0] >= level:
            stack.pop()

        parent_id = stack[-1][1]
        # Skip self-referencing edges (e.g., file "ARCHITECTURE" contains heading "Architecture")
        if parent_id != node_id:
            edges.append({
                "source": parent_id,
                "target": node_id,
                "relation": "contains",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": str_path,
            })

        stack.append((level, node_id))

    return nodes, edges


# ── Main extraction function ─────────────────────────────────────────────────

def extract_prose(paths: list[Path]) -> dict[str, Any]:
    """Extract structural nodes and edges from a list of prose files.

    Parses document structure (headings, sections) deterministically and builds
    a structural graph. Does NOT use tree-sitter or LLM calls.

    Each node has: id (snake_case), label, source_file, file_type.
    Each edge has: source, target, relation, confidence, confidence_score, source_file.

    Cross-file deduplication: concept names are normalized to snake_case, so
    "Gradient Descent" in file A and "gradient descent" in file B both map to
    node id "gradient_descent".

    Args:
        paths: List of file paths to extract from. Supported extensions:
               .md, .txt, .rst, .ipynb, .pdf, .docx

    Returns:
        Dict matching the graphify extraction schema:
        {nodes: [...], edges: [...], input_tokens: 0, output_tokens: 0}
    """
    all_nodes: list[dict[str, Any]] = []
    all_edges: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for path in paths:
        if not path.exists():
            continue

        suffix = path.suffix.lower()
        if suffix not in _PROSE_EXTENSIONS:
            continue

        file_type = _classify_file_type(path)

        # File-level node
        file_node = _build_file_node(path, file_type)
        if file_node["id"] not in seen_ids:
            all_nodes.append(file_node)
            seen_ids.add(file_node["id"])

        # Read content and extract structure
        text = _read_file(path)
        if not text:
            continue

        headings = _extract_headings(text, suffix)
        section_nodes, section_edges = _build_section_nodes(
            headings, path, file_type,
        )

        for node in section_nodes:
            if node["id"] not in seen_ids:
                all_nodes.append(node)
                seen_ids.add(node["id"])

        all_edges.extend(section_edges)

    return {
        "nodes": all_nodes,
        "edges": all_edges,
        "input_tokens": 0,
        "output_tokens": 0,
    }
