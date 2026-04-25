"""Heading-aware chunking for normalized markdown text."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from depos.analysis.config import IntentContextConfig
from depos.intent_context.schemas import IntentChunkRecord

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class _Section:
    heading_stack: list[str]
    start_line: int
    lines: list[str]


def _split_sections(text: str) -> list[_Section]:
    lines = text.split("\n")
    sections: list[_Section] = []
    stack: list[str] = []
    cur_start = 1
    cur_lines: list[str] = []
    line_no = 0
    for line in lines:
        line_no += 1
        m = _HEADING.match(line)
        if m:
            if cur_lines:
                sections.append(_Section(heading_stack=list(stack), start_line=cur_start, lines=cur_lines))
            level = len(m.group(1))
            title = m.group(2).strip()
            stack = stack[: level - 1] + [title]
            cur_start = line_no
            cur_lines = [line]
        else:
            if not cur_lines and not sections:
                cur_start = line_no
            cur_lines.append(line)
    if cur_lines:
        sections.append(_Section(heading_stack=list(stack), start_line=cur_start, lines=cur_lines))
    if not sections and lines:
        sections.append(_Section(heading_stack=[], start_line=1, lines=lines))
    return sections


def _stable_chunk_id(relpath: str, start_line: int, end_line: int, body: str) -> str:
    h = hashlib.sha256()
    h.update(relpath.encode())
    h.update(b"\0")
    h.update(f"{start_line}:{end_line}:".encode())
    h.update(body[:4000].encode())
    return h.hexdigest()[:32]


def _window_lines(
    lines: list[str],
    base_start: int,
    max_chars: int,
    overlap: int,
    relpath: str,
    heading_stack: list[str],
    path_classification: str,
) -> list[IntentChunkRecord]:
    out: list[IntentChunkRecord] = []
    text = "\n".join(lines)
    if len(text) <= max_chars:
        end_line = base_start + len(lines) - 1
        body = text.strip()
        if not body:
            return out
        cid = _stable_chunk_id(relpath, base_start, end_line, body)
        out.append(
            IntentChunkRecord(
                chunk_id=cid,
                source_relpath=relpath,
                start_line=base_start,
                end_line=max(base_start, end_line),
                heading_stack=list(heading_stack),
                text=body,
                path_classification=path_classification,  # type: ignore[arg-type]
            )
        )
        return out

    start_idx = 0
    part = 0
    while start_idx < len(lines):
        piece: list[str] = []
        char_count = 0
        end_idx = start_idx
        while end_idx < len(lines) and char_count + len(lines[end_idx]) + 1 <= max_chars:
            piece.append(lines[end_idx])
            char_count += len(lines[end_idx]) + 1
            end_idx += 1
        if not piece:
            piece = [lines[start_idx]]
            end_idx = start_idx + 1
        body = "\n".join(piece).strip()
        if not body:
            start_idx = max(start_idx + 1, end_idx)
            if start_idx >= len(lines):
                break
            continue
        sl = base_start + start_idx
        el = base_start + end_idx - 1
        cid = _stable_chunk_id(relpath, sl, el, body + f"#{part}")
        out.append(
            IntentChunkRecord(
                chunk_id=cid,
                source_relpath=relpath,
                start_line=sl,
                end_line=el,
                heading_stack=list(heading_stack),
                text=body,
                path_classification=path_classification,  # type: ignore[arg-type]
            )
        )
        part += 1
        if end_idx >= len(lines):
            break
        next_start = end_idx
        back = 0
        o_chars = 0
        while next_start - 1 > start_idx and o_chars < overlap:
            next_start -= 1
            o_chars += len(lines[next_start]) + 1
            back += 1
        start_idx = max(start_idx + 1, end_idx - max(1, back))
    return out


def chunk_normalized_text(
    relpath: str,
    normalized_text: str,
    icfg: IntentContextConfig,
    path_classification: str,
) -> list[IntentChunkRecord]:
    sections = _split_sections(normalized_text)
    chunks: list[IntentChunkRecord] = []
    for sec in sections:
        chunks.extend(
            _window_lines(
                sec.lines,
                sec.start_line,
                icfg.chunk_max_chars,
                icfg.chunk_overlap_chars,
                relpath,
                sec.heading_stack,
                path_classification,
            )
        )
    return chunks
