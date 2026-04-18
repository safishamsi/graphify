"""Post-CI: correlate failed jobs / files with predicted blast files."""
from __future__ import annotations

import json
from typing import Any


def correlate_ci_failure(
    predicted_impacted_files: list[str],
    failed_paths: list[str] | None,
    *,
    check_conclusion: str,
) -> dict[str, Any]:
    """Return overlap score and narrative."""
    failed_paths = failed_paths or []
    pred = {p.replace("\\", "/") for p in predicted_impacted_files}
    fail = {p.replace("\\", "/") for p in failed_paths}
    inter = pred & fail
    union = pred | fail
    score = len(inter) / len(union) if union else (1.0 if not pred and not fail else 0.0)
    return {
        "check_conclusion": check_conclusion,
        "overlap_score": round(score, 4),
        "intersecting_paths": sorted(inter),
        "unexpected_failure": check_conclusion == "failure" and not inter,
        "summary": (
            f"CI {check_conclusion}; {len(inter)} path(s) overlap predicted blast of {len(pred)} file(s)."
        ),
    }


def store_signal(session: Any, repo_slug: str, head_sha: str, payload: dict) -> None:
    from depos.db import CISignal

    row = CISignal(
        repo_slug=repo_slug,
        head_sha=head_sha,
        check_conclusion=payload.get("check_conclusion", ""),
        predicted_files=json.dumps(payload.get("predicted_files", [])),
        overlap_score=float(payload.get("overlap_score", 0.0)),
    )
    session.add(row)
    session.commit()
