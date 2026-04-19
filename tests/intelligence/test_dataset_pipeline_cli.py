from __future__ import annotations

import json
from pathlib import Path

from depos.cli import main


def _write_ast(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_dataset_pipeline_cli_runs_with_stubbed_graphcodebert(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DEPOS_DATA", str(tmp_path / "depos-data"))
    monkeypatch.setenv("DEPOS_INTEL_PROVIDER", "stub")

    repo_root = tmp_path / "repo"
    dataset_dir = tmp_path / "dataset"
    output_dir = tmp_path / "out"
    repo_root.mkdir()
    dataset_dir.mkdir()

    source_path = repo_root / "backend" / "app" / "auth.py"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        "def verify_token():\n"
        "    return True\n",
        encoding="utf-8",
    )

    _write_ast(
        dataset_dir / "backend_app_auth.py.json",
        {
            "commit_sha": "abc123",
            "nodes": [
                {"id": "ast:abc123:backend/app/auth.py:0:32:module", "kind": "module", "label": "module", "span": {"start": {"line": 1}, "end": {"line": 2}}},
                {"id": "ast:abc123:backend/app/auth.py:0:32:function_definition", "kind": "function_definition", "label": "def verify_token():\n    return True", "span": {"start": {"line": 1}, "end": {"line": 2}}},
                {"id": "ast:abc123:backend/app/auth.py:4:16:identifier", "kind": "identifier", "label": "verify_token", "span": {"start": {"line": 1}, "end": {"line": 1}}},
            ],
            "edges": [
                {"source_id": "ast:abc123:backend/app/auth.py:0:32:module", "target_id": "ast:abc123:backend/app/auth.py:0:32:function_definition", "type": "child"},
                {"source_id": "ast:abc123:backend/app/auth.py:0:32:function_definition", "target_id": "ast:abc123:backend/app/auth.py:4:16:identifier", "type": "child"},
            ],
        },
    )

    def _fake_score_bundles(bundles, **kwargs):
        rows = []
        for idx, bundle in enumerate(bundles):
            rows.append(
                {
                    "bundle_id": bundle.get("bundle_id", f"b{idx}"),
                    "candidate_id": bundle.get("candidate_id", f"c{idx}"),
                    "scope_id": bundle.get("scope_id", ""),
                    "graphcodebert_score": 0.81 - (idx * 0.01),
                    "graphcodebert_pattern": "auth_guard_drift",
                    "top_patterns": [{"label": "auth_guard_drift", "score": 0.81 - (idx * 0.01)}],
                    "bundle_fingerprint": f"fp{idx}",
                }
            )
        return rows

    monkeypatch.setattr("depos.analysis.graphcodebert.score_bundles", _fake_score_bundles)

    rc = main(
        [
            "analyze",
            "dataset-pipeline",
            "--dataset-dir",
            str(dataset_dir),
            "--repo-root",
            str(repo_root),
            "--output-dir",
            str(output_dir),
            "--top-n",
            "5",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    payload = json.loads(captured.out)
    assert "[depos-intel]" in captured.err
    assert "Dataset pipeline: normalizing AST dataset" in captured.err
    assert "Dataset pipeline: scoring" in captured.err
    assert "Bundle pipeline:" in captured.err
    assert payload["normalized_nodes"] >= 2
    assert payload["candidates"] >= 1
    assert payload["bundles"] >= 1
    assert payload["scores"] >= 1

    assert (output_dir / "dataset-normalized-node-link.json").exists()
    assert (output_dir / "candidates.json").exists()
    assert (output_dir / "bundles.json").exists()
    assert (output_dir / "bundle-scores.json").exists()
    assert (output_dir / "gemma4-run" / "violations.json").exists()
    assert (output_dir / "gemma4-run" / "gray_zone_audit.jsonl").exists()
