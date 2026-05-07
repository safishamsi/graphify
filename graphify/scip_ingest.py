"""scip_ingest.py — Phase 6 SCIP index ingestion (JSON-based subset).

Reads a simplified SCIP JSON structure and converts it into Graphify
nodes and edges.  This is a skeleton implementation — it handles the
core SCIP document/symbol/relationship model but does NOT implement
the full SCIP protobuf specification.

NOT wired to the CLI in this phase.

Entry point:
  ingest_scip_json(doc: dict[str, Any], source_file: str = "",
      language: str = "python") → dict[str, Any]

  Returns {"nodes": [...], "edges": [...]}.

Supported SCIP document fields:
  documents[]: { relative_path, language, symbols[], occurrences[] }
  symbols[]:   { symbol, kind, display_name, documentation[], relationships[] }
  relationships[]: { symbol, is_reference, is_implementation, is_type_definition, is_definition }
  occurrences[]: { range[], symbol, symbol_roles }
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


def ingest_scip_json(
    doc: dict[str, Any],
    source_file: str = "",
    language: str = "python",
) -> dict[str, Any]:
    """Convert a SCIP JSON document into Graphify nodes and edges.

    Returns {"nodes": [...], "edges": [...]} compatible with Graphify's
    extraction result format.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str, str | None]] = set()

    if not isinstance(doc, dict):
        return {"nodes": nodes, "edges": edges}

    documents = doc.get("documents", [])
    if not isinstance(documents, list):
        return {"nodes": nodes, "edges": edges}

    for document in documents:
        if not isinstance(document, dict):
            continue

        doc_path = document.get("relative_path", source_file)
        doc_language = document.get("language", language)

        symbols = document.get("symbols", [])
        if not isinstance(symbols, list):
            continue

        for symbol in symbols:
            if not isinstance(symbol, dict):
                continue
            _ingest_symbol(
                symbol,
                doc_path,
                doc_language,
                nodes,
                edges,
                seen_ids,
                seen_edges,
            )

    return {"nodes": nodes, "edges": edges}


def _ingest_symbol(
    symbol: dict[str, Any],
    doc_path: str,
    language: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    seen_ids: set[str],
    seen_edges: set[tuple[str, str, str, str | None]],
) -> None:
    """Process a single SCIP symbol entry into Graphify nodes and edges."""

    symbol_id = symbol.get("symbol", "")
    kind = symbol.get("kind", "unknown")
    display_name = symbol.get("display_name", "")
    documentation = symbol.get("documentation", [])
    relationships = symbol.get("relationships", [])

    if not symbol_id:
        return

    # Derive a Graphify node id from the SCIP symbol
    node_id = _make_scip_node_id(symbol_id, doc_path)

    # Parse line info from the first occurrence
    sourceline = 0
    occurrences = symbol.get("occurrences", [])
    if isinstance(occurrences, list) and occurrences:
        first_occ = occurrences[0]
        if isinstance(first_occ, dict):
            rng = first_occ.get("range", [])
            if isinstance(rng, list) and len(rng) >= 2:
                sourceline = rng[0]

    # Map SCIP kind to Graphify file_type
    file_type = _scip_kind_to_file_type(kind)

    # Description from documentation
    description = ""
    if isinstance(documentation, list) and documentation:
        description = documentation[0] if documentation[0] else ""

    node_label = display_name or (symbol_id.split("#")[-1] if "#" in symbol_id else symbol_id)

    # Add node if not already seen
    if node_id not in seen_ids:
        seen_ids.add(node_id)
        nodes.append({
            "id": node_id,
            "label": node_label,
            "file_type": file_type,
            "source_file": doc_path,
            "source_location": f"L{sourceline}" if sourceline else "",
            "metadata": _build_scip_metadata(symbol_id, kind, description),
        })

    # Process relationships
    for rel in relationships:
        if not isinstance(rel, dict):
            continue
        _ingest_relationship(
            rel,
            node_id,
            doc_path,
            sourceline,
            edges,
            seen_edges,
        )


def _ingest_relationship(
    rel: dict[str, Any],
    source_node_id: str,
    source_file: str,
    sourceline: int,
    edges: list[dict[str, Any]],
    seen_edges: set[tuple[str, str, str, str | None]],
) -> None:
    """Process a single SCIP relationship entry into a Graphify edge."""

    target_symbol = rel.get("symbol", "")
    if not target_symbol:
        return

    # Derive target node id
    target_node_id = _make_scip_node_id(target_symbol, source_file)

    # Determine relation type
    if rel.get("is_implementation"):
        relation = "scip_impl"
    elif rel.get("is_type_definition"):
        relation = "scip_typed"
    elif rel.get("is_definition"):
        relation = "scip_def"
    elif rel.get("is_reference"):
        relation = "scip_ref"
    else:
        relation = "scip_ref"

    source_location = f"L{sourceline}" if sourceline else ""

    key = (source_node_id, target_node_id, relation, source_location)
    if key in seen_edges:
        return
    seen_edges.add(key)

    edges.append({
        "source": source_node_id,
        "target": target_node_id,
        "relation": relation,
        "confidence": "EXTRACTED",
        "confidence_score": 1.0,
        "source_file": source_file,
        "source_location": source_location,
        "weight": 1.0,
        "context": "scip",
        "metadata": {
            "scip_relationship": rel,
        },
    })


def _make_scip_node_id(symbol: str, source_file: str) -> str:
    """Derive a stable Graphify node ID from a SCIP symbol identifier."""
    raw = f"{source_file}:{symbol}"
    h = hashlib.sha1(raw.encode()).hexdigest()[:12]
    parts = symbol.split("#")
    suffix = parts[-1] if parts else symbol
    suffix = re.sub(r"[^a-zA-Z0-9_]", "_", suffix).strip("_").lower()
    if suffix:
        return f"scip_{suffix}_{h}"
    return f"scip_{h}"


def _scip_kind_to_file_type(kind: str) -> str:
    """Map SCIP symbol kind to a Graphify file_type."""
    return "code"


def _build_scip_metadata(symbol_id: str, kind: str, description: str) -> dict[str, str]:
    """Build metadata for a SCIP node."""
    meta: dict[str, str] = {
        "scip_symbol": symbol_id,
        "scip_kind": kind,
    }
    if description:
        meta["scip_description"] = description
    return meta
