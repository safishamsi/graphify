"""Deterministic normative cues (frontmatter, binding globs, OFT IDs) + tier merges."""
from __future__ import annotations

import re

from depos.intent_context.intent_policy import IntentPolicy, match_path_glob, policy_tier_for_path
from depos.intent_context.oft_markdown_v0 import OFT_ID_BACKTICK_PATTERN
from depos.intent_context.schemas import IntentChunkRecord, IntentTier, TierLineageEntry, IntentUnit

_TIER_RANK: dict[IntentTier, int] = {"P0": 0, "P1": 1, "P2": 2}


def tier_rank(tier: IntentTier) -> int:
    return _TIER_RANK[tier]


def rank_to_tier(rank: int) -> IntentTier:
    if rank <= 0:
        return "P0"
    if rank == 1:
        return "P1"
    return "P2"


def tier_weight_multiplier(tier: IntentTier) -> float:
    if tier == "P0":
        return 1.0
    if tier == "P1":
        return 0.85
    return 0.45


def effective_weight_from_extractor_confidence(confidence: float, tier: IntentTier) -> float:
    w = confidence * tier_weight_multiplier(tier)
    return round(max(0.0, min(1.0, w)), 6)


def frontmatter_normative(raw_text: str) -> bool:
    """True when YAML frontmatter contains ``normative: true`` (truthy spelling)."""
    head = raw_text[:16_384]
    if not head.lstrip().startswith("---"):
        return False
    m = re.search(r"(?ms)^---\s*$(.*?)^---\s*$", head)
    if not m:
        return False
    block = m.group(1)
    return bool(
        re.search(r"^\s*normative\s*:\s*(true|yes|1)\s*$", block, re.MULTILINE | re.IGNORECASE)
    )


def oft_id_in_chunk_text(chunk_text: str) -> bool:
    return OFT_ID_BACKTICK_PATTERN.search(chunk_text) is not None


def binding_match(relpath_posix: str, binding_globs: list[str]) -> bool:
    for g in binding_globs:
        if match_path_glob(relpath_posix, g):
            return True
    return False


def compute_file_tier_bundle(
    *,
    policy: IntentPolicy,
    relpath_posix: str,
    raw_text: str,
) -> tuple[
    IntentTier,
    IntentTier,
    list[TierLineageEntry],
    bool,
]:
    """Returns ``(policy_tier, effective_tier, tier_lineage, file_normative_surface)``.

    Merge rule (strictest wins): ranks P0 < P1 < P2 → ``effective = min(rank)``.
    Binding glob and YAML ``normative:`` floor toward **at least P1** (rank 1).
    """
    policy_tier, pol_src = policy_tier_for_path(relpath_posix, policy)
    lineage: list[TierLineageEntry] = []
    if pol_src == "policy_glob":
        lineage.append(TierLineageEntry(source="policy_glob", tier_after=policy_tier))
    else:
        lineage.append(TierLineageEntry(source="default", tier_after=policy_tier))

    eff = tier_rank(policy_tier)

    if binding_match(relpath_posix, policy.binding_globs):
        eff = min(eff, tier_rank("P1"))
        lineage.append(TierLineageEntry(source="binding_glob", tier_after=rank_to_tier(eff)))

    if frontmatter_normative(raw_text):
        eff = min(eff, tier_rank("P1"))
        lineage.append(TierLineageEntry(source="frontmatter", tier_after=rank_to_tier(eff)))

    eff_tier = rank_to_tier(eff)
    lineage.append(TierLineageEntry(source="merged", tier_after=eff_tier))

    file_ns = binding_match(relpath_posix, policy.binding_globs) or frontmatter_normative(raw_text)
    return policy_tier, eff_tier, lineage, file_ns


def enrich_chunk_tier_inplace(
    ch: IntentChunkRecord,
    *,
    file_lineage: list[TierLineageEntry],
    file_effective: IntentTier,
    file_ns: bool,
) -> None:
    """Chunk tier inherits file tiers; OFT IDs in chunk text tighten toward **at least P1**."""
    oft_hit = oft_id_in_chunk_text(ch.text)
    eff_r = tier_rank(file_effective)
    lin = list(file_lineage)
    if oft_hit:
        eff_r = min(eff_r, tier_rank("P1"))
        if lin and lin[-1].source == "merged":
            lin = lin[:-1]
        lin.append(TierLineageEntry(source="oft_markdown_pattern", tier_after=rank_to_tier(eff_r)))
        lin.append(TierLineageEntry(source="merged", tier_after=rank_to_tier(eff_r)))

    tier = rank_to_tier(eff_r)
    ch.effective_tier = tier
    ch.normative_surface = bool(file_ns or oft_hit)
    ch.tier_lineage = lin
    ch.effective_weight = tier_weight_multiplier(tier)


def enrich_units_from_chunks(units: list[IntentUnit], chunk_by_id: dict[str, IntentChunkRecord]) -> None:
    """Fill ``effective_tier`` / ``effective_weight`` on units from primary evidence chunk."""
    for u in units:
        cid = None
        if getattr(u, "evidence", None):
            cid = u.evidence[0].chunk_id  # type: ignore[index]
        ch = chunk_by_id.get(cid) if cid else None
        tier: IntentTier = ch.effective_tier if ch else "P2"
        ns_chunk = bool(ch.normative_surface) if ch else False
        u.effective_tier = tier
        u.normative_surface = ns_chunk or getattr(u, "extractor", "") == "oft_markdown_v0"
        u.tier_lineage = list(ch.tier_lineage) if ch else []
        conf = float(getattr(u, "confidence", 0.5))
        u.effective_weight = effective_weight_from_extractor_confidence(conf, tier)
