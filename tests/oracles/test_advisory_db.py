from __future__ import annotations

from pathlib import Path

from depos.analysis.oracles.advisory_db import lookup


def test_advisory_db_uses_fixture_snapshot(tmp_path: Path) -> None:
    snapshot = tmp_path / "advisories.jsonl"
    snapshot.write_text(
        '{"id":"GHSA-1","ecosystem":"npm","name":"left-pad","affected_versions":["1.0.0"]}\n',
        encoding="utf-8",
    )

    hit = lookup({"snapshot_path": str(snapshot), "ecosystem": "npm", "name": "left-pad", "version": "1.0.0"})
    miss = lookup({"snapshot_path": str(snapshot), "ecosystem": "npm", "name": "left-pad", "version": "2.0.0"})

    assert hit.conclusion == "fail"
    assert miss.conclusion == "pass"
