"""Scan source files for OpenFastTrace-style coverage tags in comments."""
from __future__ import annotations

import re
from pathlib import Path

from depos.intent_context.schemas import CoverageTagRecord, IntentTraceHints, TraceHintEdge, TraceHintNode

# Long form: [impl->dsn~item-name~1] with optional >>needs
_LONG_TAG = re.compile(
    r"\[\s*([A-Za-z][A-Za-z0-9]*)\s*->\s*((?:[A-Za-z][A-Za-z0-9]*)~(?:[\w.-]+)~\d+)\s*(?:>>\s*([\w,\s]+))?\s*\]",
)
_SHORT_TAG = re.compile(r"\[\[([\w.-]+):(\d+)\]\]")

_DENY = frozenset(
    {
        "node_modules",
        ".git",
        "dist",
        "build",
        "graphify-out",
        ".next",
        "__pycache__",
        ".venv",
        "venv",
        "target",
    }
)


def _denied(path: Path) -> bool:
    return any(p in _DENY for p in path.parts)


def _iter_files(repo_root: Path, globs: list[str]) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for pattern in globs:
        for p in repo_root.glob(pattern):
            if p.is_file() and p not in seen and not _denied(p):
                seen.add(p)
                out.append(p)
    return sorted(out)


def scan_coverage_tags(repo_root: Path, globs: list[str], *, max_bytes_per_file: int) -> list[CoverageTagRecord]:
    repo_root = repo_root.resolve()
    records: list[CoverageTagRecord] = []
    for path in _iter_files(repo_root, globs):
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if len(raw) > max_bytes_per_file:
            continue
        text = raw.decode("utf-8", errors="replace")
        rel = path.relative_to(repo_root).as_posix()
        for i, line in enumerate(text.splitlines(), start=1):
            if len(line) > 2000:
                continue
            for m in _LONG_TAG.finditer(line):
                cov_art = m.group(1)
                covered = m.group(2)
                excerpt = line.strip()[:500]
                records.append(
                    CoverageTagRecord(
                        source_relpath=rel,
                        line=i,
                        tag_shape="long",
                        covering_artifact=cov_art,
                        covered_spec_id=covered,
                        raw_excerpt=excerpt,
                    )
                )
            for m in _SHORT_TAG.finditer(line):
                name, rev = m.group(1), m.group(2)
                excerpt = line.strip()[:500]
                records.append(
                    CoverageTagRecord(
                        source_relpath=rel,
                        line=i,
                        tag_shape="short",
                        covering_artifact=None,
                        covered_spec_id=f"{name}:{rev}",
                        raw_excerpt=excerpt,
                    )
                )
    return records


def build_trace_hints_from_oft_units(units_oft: list, coverage_records: list[CoverageTagRecord]) -> IntentTraceHints:
    nodes: dict[str, TraceHintNode] = {}
    edges: list[TraceHintEdge] = []
    for u in units_oft:
        sid = u.oft_spec_item_id
        if not sid:
            continue
        cid = u.evidence[0].chunk_id if u.evidence else None
        nodes[sid] = TraceHintNode(id=sid, kind="spec_item", source_chunk_id=cid)
        for c in u.oft_covers:
            edges.append(TraceHintEdge(source_id=sid, target_id=c, kind="covers"))
        for d in u.oft_depends:
            edges.append(TraceHintEdge(source_id=sid, target_id=d, kind="depends"))
    tag_dicts: list[dict] = []
    for t in coverage_records:
        tag_dicts.append(
            {
                "file": t.source_relpath,
                "line": t.line,
                "covered_spec_id": t.covered_spec_id,
                "covering_artifact": t.covering_artifact,
                "shape": t.tag_shape,
            }
        )
    return IntentTraceHints(nodes=list(nodes.values()), edges=edges, coverage_tags=tag_dicts)


def oft_inventory_from_units(units_oft: list) -> tuple[dict[str, int], list[str], list[str]]:
    from collections import defaultdict

    counts: dict[str, int] = defaultdict(int)
    ids: list[str] = []
    by_key: dict[str, set[int]] = defaultdict(set)
    for u in units_oft:
        if not u.oft_spec_item_id:
            continue
        ids.append(u.oft_spec_item_id)
        if u.oft_artifact_type:
            counts[u.oft_artifact_type] += 1
        if u.oft_item_name and u.oft_artifact_type and u.oft_revision is not None:
            key = f"{u.oft_artifact_type}~{u.oft_item_name}"
            by_key[key].add(u.oft_revision)
    warnings: list[str] = []
    for key, revs in by_key.items():
        if len(revs) > 1:
            warnings.append(f"{key}: multiple revisions in scan: {sorted(revs)}")
    return dict(counts), sorted(set(ids)), warnings
