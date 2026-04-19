"""Smoke test for the ``depos-intel`` CLI layer.

We do not shell out to the console script (the packaging environment
may not have installed it yet); we call :func:`depos.cli.main` in-
process with synthesized argv. This catches broken dispatch / missing
lazy imports.
"""
from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path

import pytest

from depos.cli import main


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
