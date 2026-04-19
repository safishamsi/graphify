"""Smoke test for the ``depos-intel`` CLI layer.

We do not shell out to the console script (the packaging environment
may not have installed it yet); we call :func:`depos.cli.main` in-
process with synthesized argv. This catches broken dispatch / missing
lazy imports.
"""
from __future__ import annotations

import argparse
import json
import sys
from io import StringIO
from pathlib import Path

import pytest

from depos.cli import main
from depos.analysis.config import IntelligenceConfig
from depos.analysis.schemas import RunMetadata, RunResult


def _run_cli(argv, capsys) -> tuple[int, str]:
    rc = main(argv)
    captured = capsys.readouterr()
    return rc, captured.out


def test_cli_help_exits_zero(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    # --help exits with 0 via argparse.
    assert exc.value.code == 0


def test_cli_coverage_reads_real_migrations(capsys, tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "acceptance_01_http_route.json"
    assert fixture.exists()
    rc, out = _run_cli(["analyze", "coverage", "--graph-json", str(fixture)], capsys)
    assert rc == 0
    payload = json.loads(out)
    # We ship 6 migrations in supabase/migrations, so the CLI should see them.
    assert payload["migration_files_found"] >= 1
    assert "coverage_ratio" in payload


def test_cli_score_bundles_help_exits_zero(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["analyze", "score-bundles", "--help"])
    assert exc.value.code == 0


def test_cli_bundle_pipeline_help_exits_zero(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["analyze", "bundle-pipeline", "--help"])
    assert exc.value.code == 0


def test_cli_normalize_dataset_help_exits_zero(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["analyze", "normalize-dataset", "--help"])
    assert exc.value.code == 0


def test_cli_dataset_pipeline_help_exits_zero(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["analyze", "dataset-pipeline", "--help"])
    assert exc.value.code == 0


def test_cli_detectors_list_outputs_registry(capsys) -> None:
    rc, out = _run_cli(["detectors", "list", "--json"], capsys)
    assert rc == 0
    payload = json.loads(out)
    names = {row["name"] for row in payload["detectors"]}
    assert "dep-version-mismatch-across-workspaces" in names
    assert "env-var-referenced-but-undefined" in names


def test_cli_detectors_explain_outputs_spec(capsys) -> None:
    rc, out = _run_cli(["detectors", "explain", "env-var-referenced-but-undefined", "--json"], capsys)
    assert rc == 0
    payload = json.loads(out)
    assert payload["name"] == "env-var-referenced-but-undefined"


def test_run_repo_honors_provider_override(monkeypatch, tmp_path: Path, capsys) -> None:
    from depos.cli import analyze as analyze_cli

    cfg = IntelligenceConfig(data_dir=tmp_path)
    cfg.reasoner.provider = "gemma"

    class DummySource:
        def get_source_metadata(self) -> dict[str, str]:
            return {"repo_path": str(tmp_path)}

    seen: dict[str, str] = {}

    def fake_run_pipeline(source, config, run_meta, **kwargs):
        seen["provider"] = config.reasoner.provider
        return RunResult(findings=[], detector_stats=[], ingest_reports=[], run_metadata=run_meta)

    monkeypatch.setattr(analyze_cli, "load_config_from_env", lambda: cfg)
    monkeypatch.setattr(analyze_cli, "_build_graph_source", lambda args: DummySource())
    monkeypatch.setattr(analyze_cli, "_run_pipeline", fake_run_pipeline)

    args = argparse.Namespace(
        path=str(tmp_path),
        output=None,
        mode="A,B,C",
        provider="stub",
        export_training=False,
        max_seeds=None,
        detectors=[],
        no_reasoner=False,
        print_detector_stats=False,
    )

    rc = analyze_cli.run_repo(args)
    assert rc == 0
    assert seen["provider"] == "stub"


def test_run_repo_emits_progress_to_stderr(monkeypatch, tmp_path: Path, capsys) -> None:
    from depos.cli import analyze as analyze_cli

    cfg = IntelligenceConfig(data_dir=tmp_path)

    class DummySource:
        def get_source_metadata(self) -> dict[str, str]:
            return {"repo_path": str(tmp_path)}

    def fake_run_pipeline(source, config, run_meta, **kwargs):
        progress = kwargs.get("progress")
        if progress is not None:
            progress("Module 2: detectors emitted 0 candidates.")
        return RunResult(findings=[], detector_stats=[], ingest_reports=[], run_metadata=run_meta)

    monkeypatch.setattr(analyze_cli, "load_config_from_env", lambda: cfg)
    monkeypatch.setattr(analyze_cli, "_build_graph_source", lambda args: DummySource())
    monkeypatch.setattr(analyze_cli, "_run_pipeline", fake_run_pipeline)

    args = argparse.Namespace(
        path=str(tmp_path),
        output=None,
        mode="A,B,C",
        provider=None,
        export_training=False,
        max_seeds=None,
        detectors=[],
        no_reasoner=False,
        print_detector_stats=False,
    )

    rc = analyze_cli.run_repo(args)
    captured = capsys.readouterr()
    assert rc == 0
    assert "[depos-intel]" in captured.err
    assert "Module 2: detectors emitted 0 candidates." in captured.err
    payload = json.loads(captured.out)
    assert payload["findings"] == 0
