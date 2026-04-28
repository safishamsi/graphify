"""Git-backed freshness metadata for intent docs (best-effort, degraded modes)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from depos.intent_context.schemas import DocSignalsRecord


def git_doc_signals(repo_root: Path, file_relpath: str, *, git_timeout_s: float = 15.0) -> DocSignalsRecord:
    """Last commit touching ``file_relpath`` (POSIX, relative to ``repo_root``)."""
    try:
        r = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "log",
                "-1",
                "--format=%cI%n%h",
                "--",
                file_relpath,
            ],
            capture_output=True,
            text=True,
            timeout=git_timeout_s,
            check=False,
        )
        if r.returncode != 0:
            diag = (r.stderr or r.stdout or "").strip()
            tail = f": {diag}" if diag else ""
            return DocSignalsRecord(
                git_commit_at=None,
                git_commit_sha=None,
                git_available=True,
                degraded_warning=f"git log failed for {file_relpath}{tail}",
            )
        blob = r.stdout.strip()
        if not blob:
            return DocSignalsRecord(
                git_commit_at=None,
                git_commit_sha=None,
                git_available=True,
                degraded_warning=f"no git history for {file_relpath}",
            )
        lines = blob.split("\n")
        ts = lines[0] if lines else None
        sha = lines[1] if len(lines) > 1 else None
        return DocSignalsRecord(
            git_commit_at=ts,
            git_commit_sha=sha,
            git_available=True,
            degraded_warning=None,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass
    return DocSignalsRecord(
        git_commit_at=None,
        git_commit_sha=None,
        git_available=False,
        degraded_warning="git unavailable or not a repository — doc freshness signals degraded",
    )
