from __future__ import annotations

from pathlib import Path

from depos.analysis.graphcodebert import load_bundles, persist_scores


def test_load_bundles_roundtrip_shape(tmp_path: Path) -> None:
    path = tmp_path / "bundles.json"
    path.write_text(
        '[{"bundle_id":"b1","candidate_id":"c1","scope_id":"s1","code_snippets":[]}]',
        encoding="utf-8",
    )
    rows = load_bundles(path)
    assert len(rows) == 1
    assert rows[0]["bundle_id"] == "b1"


def test_persist_scores_writes_json(tmp_path: Path) -> None:
    out = tmp_path / "scores.json"
    persist_scores(
        [{"bundle_id": "b1", "candidate_id": "c1", "graphcodebert_score": 0.8, "graphcodebert_pattern": "auth_guard_drift"}],
        out,
    )
    text = out.read_text(encoding="utf-8")
    assert '"graphcodebert_score": 0.8' in text
