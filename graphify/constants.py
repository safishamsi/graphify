# Shared constants and enums for graphify
from __future__ import annotations
from enum import Enum


class Confidence(str, Enum):
    """Edge confidence levels. str mixin ensures JSON serialization works."""
    EXTRACTED = "EXTRACTED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"


# ── Extraction defaults ─────────────────────────────────────────────────────
INFERRED_WEIGHT = 0.8          # weight for call-graph (pass 2) edges
EXTRACTED_WEIGHT = 1.0         # weight for AST-derived (pass 1) edges

# ── Clustering thresholds ────────────────────────────────────────────────────
MAX_COMMUNITY_FRACTION = 0.25  # communities larger than this fraction get split
MIN_SPLIT_SIZE = 10            # only split if community has >= this many nodes

# ── Surprise scoring weights ────────────────────────────────────────────────
CONFIDENCE_BONUS = {
    Confidence.AMBIGUOUS: 3,
    Confidence.INFERRED: 2,
    Confidence.EXTRACTED: 1,
}
CROSS_FILE_TYPE_BONUS = 2      # code <-> paper, code <-> image
CROSS_REPO_BONUS = 2           # different top-level directory
CROSS_COMMUNITY_BONUS = 1      # Leiden says structurally distant
SEMANTIC_SIMILARITY_MULTIPLIER = 1.5
PERIPHERAL_HUB_BONUS = 1       # low-degree node reaching a god node
PERIPHERAL_MAX_DEGREE = 2      # threshold for "peripheral" node
HUB_MIN_DEGREE = 5             # threshold for "hub" node

# ── Size limits ──────────────────────────────────────────────────────────────
MAX_FETCH_BYTES = 52_428_800   # 50 MB hard cap for binary downloads
MAX_TEXT_BYTES = 10_485_760    # 10 MB hard cap for HTML / text

# ── Visualization ────────────────────────────────────────────────────────────
MAX_NODES_FOR_VIZ = 5_000
MAX_LABEL_LEN = 256

# ── Traversal defaults ───────────────────────────────────────────────────────
DEFAULT_TRAVERSAL_DEPTH = 3
MAX_TRAVERSAL_DEPTH = 6
DEFAULT_TOKEN_BUDGET = 2000
CHARS_PER_TOKEN = 3            # approx chars-per-token for budget calc
