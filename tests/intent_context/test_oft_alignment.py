"""OpenFastTrace alignment: oft_markdown_v0, scan guards, tag scan, trace hints."""
from __future__ import annotations

import json
from pathlib import Path

from depos.analysis.config import IntelligenceConfig
from depos.intent_context.build import run_intent_context_build
from depos.intent_context.normalize import strip_oft_scan_regions
from depos.intent_context.oft_markdown_v0 import extract_oft_markdown_v0


def test_strip_oft_scan_regions() -> None:
    raw = "a\n<!-- oft:off -->\nhidden\n<!-- oft:on -->\nvisible\n"
    assert "hidden" not in strip_oft_scan_regions(raw)
    assert "visible" in strip_oft_scan_regions(raw)


def test_extract_oft_ids_and_needs() -> None:
    text = """Intro

`req~auth-flow~1`

Authenticate every session.

Needs:
- dsn
- impl

Covers:
- feat~root~1
"""
    units = extract_oft_markdown_v0(text, chunk_id="c1", start_line=1)
    ids = {u.oft_spec_item_id for u in units}
    assert "req~auth-flow~1" in ids
    u = next(x for x in units if x.oft_spec_item_id == "req~auth-flow~1")
    assert "dsn" in u.oft_needs
    assert "feat~root~1" in u.oft_covers


def test_build_emits_oft_and_tags_and_hints(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parent / "fixtures" / "minimal_repo"
    cfg = IntelligenceConfig()
    cfg.intent_context.llm_mode = "rules"
    cfg.intent_context.tag_scan_globs = ["**/*.py"]
    out = tmp_path / "out"
    assert run_intent_context_build(repo, out, cfg) == 0

    manifest = json.loads((out / "intent_manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("units_oft", 0) >= 1
    assert manifest.get("coverage_tags_found", 0) >= 1
    assert "req" in (manifest.get("oft_artifact_type_counts") or {})

    tags = [json.loads(l) for l in (out / "intent_coverage_tags.jsonl").read_text().splitlines() if l.strip()]
    assert any(t.get("covered_spec_id") == "req~sample-auth~1" for t in tags)

    hints = json.loads((out / "intent_trace_hints.json").read_text(encoding="utf-8"))
    assert any(n.get("id") == "req~sample-auth~1" for n in hints.get("nodes", []))
    assert any(e.get("kind") == "covers" for e in hints.get("edges", []))
