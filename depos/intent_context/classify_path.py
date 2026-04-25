"""Classify a doc path as intent-only vs mixed (docs living next to code)."""
from __future__ import annotations

from pathlib import Path

_MIX_DIR_HINTS = frozenset(
    {
        "src",
        "lib",
        "pkg",
        "internal",
        "packages",
        "apps",
        "services",
        "cmd",
    }
)


def classify_path(rel: Path) -> str:
    """Return ``intent`` or ``mixed`` for downstream consumers."""
    parts_lower = {p.lower() for p in rel.parts}
    if parts_lower & _MIX_DIR_HINTS:
        return "mixed"
    return "intent"
