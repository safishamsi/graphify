from __future__ import annotations
import json
import subprocess
from datetime import datetime
from .models import PRInfo
def _gh(*args: str) -> list | dict | None:
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def _detect_default_branch(repo: str | None = None) -> str:
    """Auto-detect the repo's default branch via gh, then git, then fall back to 'main'."""
    # Try gh first — works for any repo, not just the current directory
    args = ["repo", "view", "--json", "defaultBranchRef"]
    if repo:
        args += ["--repo", repo]
    data = _gh(*args)
    if data and data.get("defaultBranchRef", {}).get("name"):
        return data["defaultBranchRef"]["name"]
    # Fall back to git symbolic-ref for the current repo
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            # refs/remotes/origin/main → main
            ref = result.stdout.strip()
            return ref.split("/")[-1] if ref else "main"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "main"


_CI_FAILURE_CONCLUSIONS = frozenset({"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"})


def _parse_ci(rollup: list) -> str:
    if not rollup:
        return "NONE"
    conclusions = {r.get("conclusion") for r in rollup if r.get("conclusion")}
    if conclusions & _CI_FAILURE_CONCLUSIONS:
        return "FAILURE"
    statuses = {r.get("status") for r in rollup}
    if "IN_PROGRESS" in statuses or "QUEUED" in statuses:
        return "PENDING"
    if "SUCCESS" in conclusions:
        return "SUCCESS"
    return "NONE"


def fetch_prs(repo: str | None = None, base: str | None = None, limit: int = 50) -> list[PRInfo]:
    resolved_base = base or _detect_default_branch(repo)
    args = [
        "pr", "list", "--state", "open", "--limit", str(limit),
        "--json", "number,title,headRefName,baseRefName,author,isDraft,"
                  "reviewDecision,statusCheckRollup,updatedAt",
    ]
    if repo:
        args += ["--repo", repo]

    raw = _gh(*args)
    if raw is None:
        raise RuntimeError("gh CLI not found or not authenticated. Run: gh auth login")

    prs = []
    for item in raw:
        updated = datetime.fromisoformat(item["updatedAt"].replace("Z", "+00:00"))
        prs.append(PRInfo(
            number=item["number"],
            title=item["title"],
            branch=item["headRefName"],
            base_branch=item["baseRefName"],
            author=item["author"]["login"] if item.get("author") else "?",
            is_draft=item.get("isDraft", False),
            review_decision=item.get("reviewDecision") or "",
            ci_status=_parse_ci(item.get("statusCheckRollup") or []),
            updated_at=updated,
            expected_base=resolved_base,
        ))
    return prs


def fetch_pr_files(number: int, repo: str | None = None) -> list[str]:
    args = ["pr", "diff", str(number), "--name-only"]
    if repo:
        args += ["--repo", repo]
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return []
        return [l.strip() for l in result.stdout.splitlines() if l.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def fetch_worktrees() -> dict[str, str]:
    """Returns {branch: worktree_path}."""
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return {}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {}

    mapping: dict[str, str] = {}
    current_path = None
    for line in result.stdout.splitlines():
        if not line:
            current_path = None  # blank line = record separator; reset to avoid leaking across detached HEADs
        elif line.startswith("worktree "):
            current_path = line[9:]
        elif line.startswith("branch refs/heads/") and current_path:
            mapping[line[18:]] = current_path
    return mapping


