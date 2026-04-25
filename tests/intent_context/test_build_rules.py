"""Intent context build (rules-only path)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from depos.analysis.config import IntelligenceConfig
from depos.intent_context.build import run_intent_context_build
from depos.intent_context.rules_v0 import extract_rules_v0


FIXTURE_REPO = Path(__file__).resolve().parent / "fixtures" / "minimal_repo"


def test_extract_rules_must_never() -> None:
    text = "The server MUST validate input.\nClients NEVER send raw SQL."
    units = extract_rules_v0(text, chunk_id="chunk1", start_line=10)
    cues = {u.natural_language.split(":")[0] for u in units}
    assert any("MUST" in c for c in cues)
    assert any("NEVER" in c for c in cues)


@pytest.mark.parametrize("repo", [FIXTURE_REPO])
def test_intent_build_rules_only(tmp_path: Path, repo: Path) -> None:
    cfg = IntelligenceConfig()
    cfg.intent_context.llm_mode = "rules"
    cfg.intent_context.chunk_max_chars = 12000
    out = tmp_path / "intent-out"
    assert run_intent_context_build(repo, out, cfg) == 0

    manifest = json.loads((out / "intent_manifest.json").read_text(encoding="utf-8"))
    assert manifest["llm_enabled"] is False
    assert manifest["units_rules"] >= 1
    rels = {f["relpath"] for f in manifest["files"]}
    assert "docs/a.md" in rels
    assert "README.md" in rels

    chunks = [json.loads(line) for line in (out / "intent_chunks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(chunks) >= 1
    assert all("chunk_id" in c for c in chunks)

    units = json.loads((out / "intent_units.json").read_text(encoding="utf-8"))
    assert isinstance(units, list)
    assert all(u.get("extractor") == "rules_v0" for u in units)
