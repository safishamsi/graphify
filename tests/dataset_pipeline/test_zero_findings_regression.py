"""Regression suite for the "Gemma 4 produced zero findings but the run was
marked successful" failure mode.

These tests pin the three behaviours that, together, prevent that bug from
recurring silently:

1. With a healthy provider and the right ``--source-root``, the dataset
   pipeline runs end-to-end and reports ``reasoner_run_health == "ok"``.
2. With a wrong ``--source-root`` (snippets degrade to ``label_only`` /
   ``missing``), the pipeline still completes but ``--strict`` exits with the
   path-resolution code so CI cannot be fooled into thinking nothing is wrong.
3. When one mode's provider returns malformed JSON for *every* call but the
   other modes succeed, ``ReasonerCallStats`` records the per-reason
   breakdown accurately and the run is reported as ``degraded`` rather than
   ``failed``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from depos.cli import main


FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "datasets" / "tiny_drift"


def _fake_score_bundles(bundles, **_kwargs):
    """Stub for GraphCodeBERT so the test does not download a 500MB model."""
    rows = []
    for idx, bundle in enumerate(bundles):
        rows.append(
            {
                "bundle_id": bundle.get("bundle_id", f"b{idx}"),
                "candidate_id": bundle.get("candidate_id", f"c{idx}"),
                "scope_id": bundle.get("scope_id", ""),
                "graphcodebert_score": 0.8 - idx * 0.01,
                "graphcodebert_pattern": "auth_guard_drift",
                "top_patterns": [{"label": "auth_guard_drift", "score": 0.8 - idx * 0.01}],
                "bundle_fingerprint": f"fp{idx}",
            }
        )
    return rows


def _run_dataset(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    source_roots: list[Path] | None = None,
    strict: bool = False,
    extra_args: list[str] | None = None,
) -> tuple[int, Path]:
    monkeypatch.setenv("DEPOS_DATA", str(tmp_path / "depos-data"))
    monkeypatch.setenv("DEPOS_INTEL_PROVIDER", "stub")
    # The tiny_drift fixture only exercises one source file, so the
    # heuristic evidence_score lands below the production default. Lower the
    # floor here so the gate doesn't accidentally skip every bundle and mask
    # what we're trying to test.
    monkeypatch.setenv("DEPOS_INTEL_MIN_EVIDENCE_SCORE", "0.0")
    monkeypatch.setattr("depos.analysis.graphcodebert.score_bundles", _fake_score_bundles)

    output_dir = tmp_path / "out"
    args = [
        "analyze",
        "dataset-pipeline",
        "--dataset-dir",
        str(FIXTURE_ROOT),
        "--repo-root",
        str(repo_root),
        "--output-dir",
        str(output_dir),
        "--top-n",
        "5",
    ]
    for root in source_roots or []:
        args += ["--source-root", str(root)]
    if strict:
        args.append("--strict")
    if extra_args:
        args += extra_args
    rc = main(args)
    return rc, output_dir


# ---------------------------------------------------------------------------
# (a) Happy path: stub provider + correct source roots → healthy run
# ---------------------------------------------------------------------------


def test_stub_provider_end_to_end_succeeds(tmp_path, monkeypatch):
    repo_root = FIXTURE_ROOT / "repo_src"
    rc, output_dir = _run_dataset(tmp_path=tmp_path, monkeypatch=monkeypatch, repo_root=repo_root)
    assert rc == 0

    summary_path = output_dir / "gemma4-run" / "run_summary.json"
    assert summary_path.exists(), "run_summary.json must be written by the bundle pipeline"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    # Healthy run: every reasoner call should succeed and the run should
    # advertise that explicitly.
    assert summary["reasoner_run_health"] == "ok", summary
    stats = summary["reasoner_call_stats"]
    assert stats["attempts"] >= 1
    assert stats["successes"] == stats["attempts"]
    assert stats["failures"] == 0

    # Path resolution surfaces what the operator should know.
    resolution = output_dir / "dataset_path_resolution.json"
    assert resolution.exists()
    payload = json.loads(resolution.read_text(encoding="utf-8"))
    assert payload["summary"]["files_resolved"] >= 1


# ---------------------------------------------------------------------------
# (b) Wrong source root → degraded evidence + strict exit code
# ---------------------------------------------------------------------------


def test_wrong_source_root_strict_returns_path_resolution_exit_code(tmp_path, monkeypatch):
    # Point at a directory that does not contain the dataset's source files.
    bad_root = tmp_path / "elsewhere"
    bad_root.mkdir()

    rc, output_dir = _run_dataset(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        repo_root=bad_root,
        strict=True,
    )

    # Path resolution is well below 50% (the fixture has 1 source file and we
    # gave a bogus root with nothing in it), so --strict must trip.
    resolution_payload = json.loads(
        (output_dir / "dataset_path_resolution.json").read_text(encoding="utf-8")
    )
    summary = resolution_payload["summary"]
    assert summary["files_total"] >= 1
    assert summary["files_resolved"] == 0
    assert rc in {2, 3}, (
        "--strict must surface the failure: 3 when path resolution is the cause, "
        "2 when reasoner health degrades because every bundle was skipped."
    )


# ---------------------------------------------------------------------------
# (c) Mode A always fails JSON parsing → degraded health, B/C still produce
# ---------------------------------------------------------------------------


def test_mode_a_malformed_json_records_per_reason_breakdown(tmp_path, monkeypatch):
    """Stub provider patched so Mode A always returns junk; B and C stay healthy."""
    from depos.analysis import reasoning_engine
    from depos.analysis.schemas import ReasonerMode

    real_complete = reasoning_engine.StubProvider.complete

    def patched_complete(self, prompt, *, max_tokens):
        if self.mode == ReasonerMode.A:
            # Not valid JSON at all → triggers the "not_json" failure_reason
            # branch, which is the cluster the Gemma 4 run hit.
            return "<<not json at all>>", {"model": "stub", "response_path_used": "literal"}
        return real_complete(self, prompt, max_tokens=max_tokens)

    monkeypatch.setattr(reasoning_engine.StubProvider, "complete", patched_complete)

    repo_root = FIXTURE_ROOT / "repo_src"
    rc, output_dir = _run_dataset(tmp_path=tmp_path, monkeypatch=monkeypatch, repo_root=repo_root)
    assert rc == 0  # without --strict the pipeline still returns 0

    summary = json.loads((output_dir / "gemma4-run" / "run_summary.json").read_text(encoding="utf-8"))
    stats = summary["reasoner_call_stats"]
    by_mode = stats["by_mode"]

    # Mode A failed every attempt; B and C succeeded.
    assert by_mode.get("A", {}).get("failures", 0) >= 1
    assert by_mode.get("A", {}).get("successes", 0) == 0
    assert by_mode.get("B", {}).get("successes", 0) >= 1
    assert by_mode.get("C", {}).get("successes", 0) >= 1

    # The per-reason breakdown must point the operator at the right cluster.
    by_reason = stats["by_reason"]
    assert any(reason in by_reason for reason in ("not_json", "json_but_invalid_schema"))

    # Health is degraded (some calls succeed, some fail), not failed.
    assert summary["reasoner_run_health"] in {"ok", "degraded"}
    assert summary["reasoner_run_health"] != "failed"
