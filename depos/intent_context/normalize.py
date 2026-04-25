"""Normalize file text and optionally extract fenced code blocks."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from depos.intent_context.schemas import FencedBlockMeta

FencedPolicy = Literal["strip", "annotate"]


@dataclass
class NormalizedDoc:
    text: str
    fenced_blocks: list[FencedBlockMeta]


def read_normalized_bytes(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def normalize_markdown_text(full: str, policy: FencedPolicy) -> NormalizedDoc:
    """Remove or annotate fenced ``` blocks; record metadata with 1-based line numbers in ``full``."""
    lines = full.split("\n")
    out: list[str] = []
    fenced: list[FencedBlockMeta] = []
    in_fence = False
    fence_lang = ""
    fence_open_line = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```") and not in_fence:
            in_fence = True
            fence_lang = stripped[3:].strip()
            fence_open_line = i + 1
            i += 1
            continue
        if stripped.startswith("```") and in_fence:
            fenced.append(
                FencedBlockMeta(
                    language=fence_lang,
                    start_line=fence_open_line,
                    end_line=i + 1,
                )
            )
            in_fence = False
            if policy == "annotate":
                out.append(
                    f"<!-- intent_context:fenced {fence_lang or 'text'} "
                    f"lines {fence_open_line}-{i + 1} omitted -->"
                )
            elif policy == "strip":
                out.append("")
            i += 1
            continue
        if in_fence:
            i += 1
            continue
        out.append(line)
        i += 1
    return NormalizedDoc(text="\n".join(out), fenced_blocks=fenced)


def normalize_markdown(path: Path, policy: FencedPolicy) -> NormalizedDoc:
    raw = path.read_bytes()
    full = read_normalized_bytes(raw)
    return normalize_markdown_text(full, policy)
