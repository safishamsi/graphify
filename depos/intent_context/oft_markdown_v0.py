"""Parse OpenFastTrace-style Markdown spec items (IDs, Needs, Covers, …)."""
from __future__ import annotations

import hashlib
import re
from typing import Any

from depos.intent_context.schemas import IntentEvidence, IntentUnit

# Mirrors OFT ``type~name~rev`` in backticks (see SpecificationItemId in OpenFastTrace).
_OFT_ID_BACKTICK = re.compile(
    r"`([A-Za-z][A-Za-z0-9]*)~([A-Za-z][\w.-]*(?:\.[\w.-]+)*)~(\d+)`",
)
_KEY_NEEDS = re.compile(r"^\s*Needs:\s*$", re.IGNORECASE)
_KEY_NEEDS_INLINE = re.compile(r"^\s*Needs:\s*(.+)\s*$", re.IGNORECASE)
_KEY_COVERS = re.compile(r"^\s*Covers:\s*$", re.IGNORECASE)
_KEY_DEPENDS = re.compile(r"^\s*Depends:\s*$", re.IGNORECASE)
_KEY_STATUS = re.compile(r"^\s*Status:\s*(\w+)\s*$", re.IGNORECASE)
_KEY_RATIONALE = re.compile(r"^\s*Rationale:\s*$", re.IGNORECASE)
_KEY_COMMENT = re.compile(r"^\s*Comment:\s*$", re.IGNORECASE)
_BULLET_ID = re.compile(r"^\s*[-*+]\s*`?([A-Za-z][A-Za-z0-9]*~[\w.-]+~\d+)`?\s*$")
_BULLET_WORD = re.compile(r"^\s*[-*+]\s*(\w+)\s*$")


def _hash_unit(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()[:24]


def _parse_list_section(lines: list[str], start: int) -> tuple[list[str], int]:
    out: list[str] = []
    j = start
    while j < len(lines):
        raw = lines[j]
        if not raw.strip():
            break
        if _BULLET_ID.match(raw):
            out.append(_BULLET_ID.match(raw).group(1))
            j += 1
            continue
        if _BULLET_WORD.match(raw):
            out.append(_BULLET_WORD.match(raw).group(1))
            j += 1
            continue
        break
    return out, j


def _parse_multiline_value(lines: list[str], start: int) -> tuple[str, int]:
    parts: list[str] = []
    j = start
    while j < len(lines):
        line = lines[j]
        if not line.strip():
            j += 1
            break
        if re.match(
            r"^\s*(Needs|Covers|Depends|Status|Rationale|Comment|Description):\s*",
            line,
            re.IGNORECASE,
        ):
            break
        if _OFT_ID_BACKTICK.search(line):
            break
        parts.append(line.rstrip())
        j += 1
    return "\n".join(parts).strip(), j


def _parse_block_after_id(block_lines: list[str]) -> dict[str, Any]:
    needs: list[str] = []
    covers: list[str] = []
    depends: list[str] = []
    status: str | None = None
    rationale = ""
    comment = ""
    i = 0
    while i < len(block_lines):
        line = block_lines[i]
        m_needs_inline = _KEY_NEEDS_INLINE.match(line)
        if m_needs_inline and not _KEY_NEEDS.match(line):
            raw = m_needs_inline.group(1).strip()
            for part in re.split(r"[,;]\s*", raw):
                p = part.strip()
                if p and "~" not in p:
                    needs.append(p)
            i += 1
            continue
        if _KEY_NEEDS.match(line):
            got, j = _parse_list_section(block_lines, i + 1)
            needs.extend(got)
            i = max(j, i + 1)
            continue
        if _KEY_COVERS.match(line):
            got, j = _parse_list_section(block_lines, i + 1)
            covers.extend(got)
            i = max(j, i + 1)
            continue
        if _KEY_DEPENDS.match(line):
            got, j = _parse_list_section(block_lines, i + 1)
            depends.extend(got)
            i = max(j, i + 1)
            continue
        m_stat = _KEY_STATUS.match(line)
        if m_stat:
            status = m_stat.group(1).lower()
            i += 1
            continue
        if _KEY_RATIONALE.match(line):
            rationale, i = _parse_multiline_value(block_lines, i + 1)
            continue
        if _KEY_COMMENT.match(line):
            comment, i = _parse_multiline_value(block_lines, i + 1)
            continue
        i += 1
    return {
        "needs": needs,
        "covers": covers,
        "depends": depends,
        "status": status,
        "rationale": rationale[:2000],
        "comment": comment[:2000],
    }


def extract_oft_markdown_v0(
    chunk_text: str,
    *,
    chunk_id: str,
    start_line: int,
) -> list[IntentUnit]:
    """Extract OFT-style spec items from a chunk; emit ``IntentUnit`` with ``extractor=oft_markdown_v0``."""
    lines = chunk_text.split("\n")
    units: list[IntentUnit] = []
    seen_spans: set[tuple[int, int, str]] = set()

    for m in _OFT_ID_BACKTICK.finditer(chunk_text):
        art, name, rev = m.group(1), m.group(2), m.group(3)
        full_id = f"{art}~{name}~{rev}"
        pos_line = start_line + chunk_text[: m.start()].count("\n")
        line_idx = pos_line - start_line
        if line_idx < 0 or line_idx >= len(lines):
            continue
        # Block: from ID line through following content until next backtick-ID or double blank
        block_start = line_idx
        block_end = min(len(lines), line_idx + 80)
        block_lines = lines[block_start:block_end]
        # Trim block at next OFT id line (different item)
        trimmed: list[str] = []
        for k, bl in enumerate(block_lines):
            if k > 0 and _OFT_ID_BACKTICK.search(bl) and "`" + full_id + "`" not in bl:
                break
            trimmed.append(bl)
        meta = _parse_block_after_id(trimmed[1:] if len(trimmed) > 1 else [])

        desc_lines: list[str] = []
        for bl in trimmed[1:]:
            if re.match(r"^\s*(Needs|Covers|Depends|Status|Rationale|Comment|Description):\s*", bl, re.I):
                break
            if _OFT_ID_BACKTICK.search(bl):
                break
            if bl.strip():
                desc_lines.append(bl.strip())
        description = " ".join(desc_lines)[:1500] or f"Specification item {full_id}"

        span_key = (pos_line, pos_line, full_id)
        if span_key in seen_spans:
            continue
        seen_spans.add(span_key)

        uid = _hash_unit(f"oft:{chunk_id}:{full_id}:{pos_line}")
        nl = f"{full_id}: {description}"
        units.append(
            IntentUnit(
                unit_id=uid,
                kind="api_contract_narrative",
                natural_language=nl,
                scope_hints=[art, *meta["needs"][:16]],
                evidence=[IntentEvidence(chunk_id=chunk_id, start_line=pos_line, end_line=pos_line)],
                extractor="oft_markdown_v0",
                confidence=0.95,
                oft_spec_item_id=full_id,
                oft_artifact_type=art,
                oft_item_name=name,
                oft_revision=int(rev),
                oft_needs=list(meta["needs"])[:32],
                oft_covers=list(meta["covers"])[:64],
                oft_depends=list(meta["depends"])[:64],
                oft_status=meta["status"],
                oft_rationale_excerpt=(meta["rationale"] or None)[:800] if meta["rationale"] else None,
                oft_comment_excerpt=(meta["comment"] or None)[:800] if meta["comment"] else None,
            )
        )
    return units


def oft_prompt_context_snippet(chunk_text: str, max_chars: int = 700) -> str:
    """Structured OFT-ish context for LLM prompts (Rationale / Comment / first IDs)."""
    parts: list[str] = []
    if "Rationale:" in chunk_text:
        m = re.search(r"Rationale:\s*([\s\S]{0,400}?)(?=^\s*(?:Needs|Covers|Comment|Status|$))", chunk_text, re.MULTILINE | re.IGNORECASE)
        if m:
            parts.append("Rationale excerpt: " + m.group(1).strip()[:400])
    if "Depends:" in chunk_text:
        m = re.search(r"Depends:\s*([\s\S]{0,300}?)(?=^\s*(?:Needs|Covers|Rationale|$))", chunk_text, re.MULTILINE | re.IGNORECASE)
        if m:
            parts.append("Depends excerpt: " + m.group(1).strip()[:300])
    ids = _OFT_ID_BACKTICK.findall(chunk_text)
    if ids:
        parts.append("OFT IDs in chunk: " + ", ".join(f"{a}~{n}~{r}" for a, n, r in ids[:12]))
    out = "\n".join(parts).strip()
    return out[:max_chars] if out else ""
