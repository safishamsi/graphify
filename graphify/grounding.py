"""Grounding validation — verify extracted nodes are anchored in source text.

After semantic extraction, this pass checks that EXTRACTED nodes actually have
their label (or a close variant) present in the source file. Nodes that fail
grounding are downgraded from EXTRACTED to INFERRED/AMBIGUOUS, preventing
hallucinated entities from polluting the graph with false confidence.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def _normalize_for_match(text: str) -> str:
    """Lowercase and collapse whitespace/punctuation for fuzzy matching."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _label_appears_in_source(label: str, source_text: str) -> bool:
    """Check if the node label (or meaningful substring) appears in the source."""
    norm_label = _normalize_for_match(label)
    norm_source = _normalize_for_match(source_text)

    # Direct match
    if norm_label in norm_source:
        return True

    # Try significant words (3+ chars) — if >=60% appear in source, it's grounded
    words = [w for w in norm_label.split() if len(w) >= 3]
    if not words:
        return True  # very short labels (e.g., "IP") — skip validation
    hits = sum(1 for w in words if w in norm_source)
    return hits / len(words) >= 0.6


def validate_grounding(
    extraction: dict,
    *,
    source_root: Path | None = None,
    strict: bool = False,
) -> dict:
    """Validate that EXTRACTED-confidence nodes are grounded in their source files.

    For each node marked with edges having confidence=EXTRACTED, check that the
    node's label appears in the source_file. If not:
    - Downgrade edges FROM/TO that node from EXTRACTED→INFERRED (score 0.75)
    - If strict=True, also mark the node with grounding_failed=True

    Returns the (possibly modified) extraction dict and prints warnings.
    """
    nodes = extraction.get("nodes", [])
    edges = extraction.get("edges", [])

    # Build source file cache (read each file at most once)
    source_cache: dict[str, str] = {}
    failed_nodes: set[str] = set()
    checked = 0
    failed = 0

    for node in nodes:
        source_file = node.get("source_file")
        if not source_file:
            continue

        label = node.get("label", "")
        if not label:
            continue

        # Resolve source file path
        if source_root and not Path(source_file).is_absolute():
            full_path = source_root / source_file
        else:
            full_path = Path(source_file)

        if not full_path.exists():
            continue

        # Load and cache source text
        if source_file not in source_cache:
            try:
                source_cache[source_file] = full_path.read_text(
                    encoding="utf-8", errors="replace"
                )
            except (OSError, PermissionError):
                continue

        checked += 1
        source_text = source_cache[source_file]

        if not _label_appears_in_source(label, source_text):
            failed_nodes.add(node["id"])
            failed += 1
            if strict:
                node["grounding_failed"] = True

    # Downgrade edges connected to ungrounded nodes
    downgraded = 0
    for edge in edges:
        if edge.get("confidence") != "EXTRACTED":
            continue
        src, tgt = edge.get("source", ""), edge.get("target", "")
        if src in failed_nodes or tgt in failed_nodes:
            edge["confidence"] = "INFERRED"
            edge["confidence_score"] = 0.75
            edge["grounding_note"] = "downgraded: node label not found in source"
            downgraded += 1

    if failed > 0:
        print(
            f"[graphify] Grounding: {checked} nodes checked, {failed} ungrounded "
            f"({downgraded} edges downgraded from EXTRACTED→INFERRED)",
            file=sys.stderr,
        )

    return extraction
