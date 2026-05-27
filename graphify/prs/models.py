from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone


# ── ANSI colours ─────────────────────────────────────────────────────────────

_NO_COLOR = not sys.stdout.isatty() or os.environ.get("NO_COLOR")

def _c(code: str, text: str) -> str:
    if _NO_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

def green(t: str) -> str:   return _c("32", t)
def red(t: str) -> str:     return _c("31", t)
def yellow(t: str) -> str:  return _c("33", t)
def cyan(t: str) -> str:    return _c("36", t)
def bold(t: str) -> str:    return _c("1",  t)
def dim(t: str) -> str:     return _c("2",  t)
def magenta(t: str) -> str: return _c("35", t)

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")

def _pad(s: str, width: int) -> str:
    """Pad an ANSI-colored string to visible width (strips escape codes for length calc)."""
    visible_len = len(_ANSI_RE.sub("", s))
    return s + " " * max(0, width - visible_len)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class PRInfo:
    number: int
    title: str
    branch: str
    base_branch: str
    author: str
    is_draft: bool
    review_decision: str        # APPROVED | CHANGES_REQUESTED | ""
    ci_status: str              # SUCCESS | FAILURE | PENDING | NONE
    updated_at: datetime
    expected_base: str = "main"  # set by fetch_prs via _detect_default_branch
    worktree_path: str | None = None
    # Graph impact — populated when graph.json exists
    communities_touched: list[int] = field(default_factory=list)
    nodes_affected: int = 0
    files_changed: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return _classify(self, self.expected_base)

    @property
    def days_old(self) -> int:
        return (datetime.now(timezone.utc) - self.updated_at).days

    @property
    def blast_radius(self) -> str:
        if not self.nodes_affected:
            return ""
        n = self.nodes_affected
        c = len(self.communities_touched)
        return f"{n} node{'s' if n != 1 else ''} / {c} communit{'ies' if c != 1 else 'y'}"


# ── Classification ────────────────────────────────────────────────────────────

_STATUS_ORDER = ["WRONG-BASE", "CI-FAIL", "CHANGES-REQ", "DRAFT", "STALE", "PENDING", "APPROVED", "READY"]
_STALE_DAYS = 14


def _classify(pr: "PRInfo", base: str = "v8") -> str:
    if pr.base_branch != base:
        return "WRONG-BASE"
    if pr.ci_status == "FAILURE":
        return "CI-FAIL"
    if pr.review_decision == "CHANGES_REQUESTED":
        return "CHANGES-REQ"
    if pr.is_draft:
        return "DRAFT"
    if pr.days_old >= _STALE_DAYS:
        return "STALE"
    if pr.review_decision == "APPROVED":
        return "APPROVED"
    if pr.ci_status == "PENDING":
        return "PENDING"
    return "READY"


def _status_color(status: str) -> str:
    return {
        "READY":       green(status),
        "APPROVED":    bold(green(status)),
        "CI-FAIL":     red(status),
        "CHANGES-REQ": red(status),
        "WRONG-BASE":  dim(status),
        "STALE":       dim(status),
        "DRAFT":       yellow(status),
        "PENDING":     yellow(status),
    }.get(status, status)


def _ci_icon(status: str) -> str:
    return {"SUCCESS": green("✓"), "FAILURE": red("✗"), "PENDING": yellow("…"), "NONE": dim("–")}.get(status, "?")


