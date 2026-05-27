from __future__ import annotations
from .models import PRInfo, _STATUS_ORDER, bold, dim, green, red, yellow, cyan, _status_color, _ci_icon, _pad
def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


def render_dashboard(prs: list[PRInfo], base: str = "v8", show_wrong_base: bool = False) -> None:
    actionable = [p for p in prs if p.base_branch == base]
    wrong_base = [p for p in prs if p.base_branch != base]

    # Sort: READY first, then by status order, then by recency
    actionable.sort(key=lambda p: (_STATUS_ORDER.index(p.status) if p.status in _STATUS_ORDER else 99, p.days_old))

    print()
    print(bold(f"  graphify prs  ·  base: {base}  ·  {len(actionable)} PRs"))
    print()

    if not actionable:
        print(dim("  No open PRs targeting this base branch."))
    else:
        # Header
        print(f"  {'#':>4}  {'CI':2}  {'STATUS':13}  {'UPDATED':8}  {'IMPACT':22}  TITLE")
        print(f"  {'─'*4}  {'─'*2}  {'─'*13}  {'─'*8}  {'─'*22}  {'─'*40}")

        for pr in actionable:
            status_str = _pad(_status_color(pr.status), 13)
            ci_str = _ci_icon(pr.ci_status)
            age = f"{pr.days_old}d" if pr.days_old > 0 else "today"
            impact = _pad(dim(_truncate(pr.blast_radius, 22)), 22) if pr.blast_radius else _pad(dim("–"), 22)
            wt = f" {cyan('⬡')}" if pr.worktree_path else "  "
            draft = dim(" [draft]") if pr.is_draft else ""
            title = _truncate(pr.title, 52)
            num = _pad(bold(f"#{pr.number}"), 6)
            print(f"  {num}{wt}  {ci_str}  {status_str}  {age:>6}   {impact}  {title}{draft}")

    # Summary line
    by_status: dict[str, int] = {}
    for p in actionable:
        by_status[p.status] = by_status.get(p.status, 0) + 1

    parts = []
    if by_status.get("READY"):      parts.append(green(f"{by_status['READY']} ready"))
    if by_status.get("APPROVED"):   parts.append(bold(green(f"{by_status['APPROVED']} approved")))
    if by_status.get("PENDING"):    parts.append(yellow(f"{by_status['PENDING']} pending CI"))
    if by_status.get("CI-FAIL"):    parts.append(red(f"{by_status['CI-FAIL']} CI failing"))
    if by_status.get("CHANGES-REQ"):parts.append(red(f"{by_status['CHANGES-REQ']} changes requested"))
    if by_status.get("DRAFT"):      parts.append(yellow(f"{by_status['DRAFT']} draft"))
    if by_status.get("STALE"):      parts.append(dim(f"{by_status['STALE']} stale"))

    if wrong_base:
        parts.append(dim(f"{len(wrong_base)} wrong base"))

    print()
    print(f"  {' · '.join(parts)}")
    print()

    if wrong_base and show_wrong_base:
        print(dim(f"  ── {len(wrong_base)} PRs targeting wrong base ──"))
        for pr in sorted(wrong_base, key=lambda p: p.number, reverse=True):
            print(dim(f"  #{pr.number:4}  base={pr.base_branch:12}  {_truncate(pr.title, 60)}"))
        print()


def render_worktrees(prs: list[PRInfo], worktrees: dict[str, str]) -> None:
    print()
    print(bold("  Worktrees"))
    print()
    if not worktrees:
        print(dim("  No active worktrees found."))
        print()
        return

    pr_by_branch = {p.branch: p for p in prs}
    for branch, path in sorted(worktrees.items()):
        pr = pr_by_branch.get(branch)
        if pr:
            status = _status_color(pr.status)
            print(f"  {cyan(path)}")
            print(f"    {dim('branch:')} {branch}  →  PR {bold(f'#{pr.number}')}  [{status}]  {_truncate(pr.title, 50)}")
        else:
            print(f"  {cyan(path)}")
            print(f"    {dim('branch:')} {branch}  {dim('(no open PR)')}")
        print()


def render_conflicts(
    prs: list[PRInfo],
    base: str = "v8",
    community_labels: dict[int, list[str]] | None = None,
) -> None:
    actionable = [p for p in prs if p.base_branch == base and p.communities_touched]
    if not actionable:
        print(dim("\n  No graph impact data — run with a valid graph.json to detect conflicts.\n"))
        return

    # Build community → [PRs] map
    comm_to_prs: dict[int, list[PRInfo]] = {}
    for pr in actionable:
        for c in pr.communities_touched:
            comm_to_prs.setdefault(c, []).append(pr)

    conflicts = {c: ps for c, ps in comm_to_prs.items() if len(ps) > 1}
    if not conflicts:
        print(green("\n  No community overlap between open PRs — safe to merge in any order.\n"))
        return

    print()
    print(bold("  Community conflicts (PRs sharing the same graph community)"))
    print()
    labels = community_labels or {}
    for comm, ps in sorted(conflicts.items(), key=lambda x: -len(x[1])):
        comm_label_str = ""
        if comm in labels and labels[comm]:
            comm_label_str = dim("  — " + ", ".join(labels[comm]))
        print(f"  {yellow(f'Community {comm}')}{comm_label_str}  ({len(ps)} PRs overlap)")
        for pr in ps:
            print(f"    #{pr.number:4}  {_pad(_status_color(pr.status), 13)}  {_truncate(pr.title, 55)}")
        print()


def render_pr_detail(pr: PRInfo, repo: str | None = None) -> None:
    print()
    print(bold(f"  PR #{pr.number}  ·  {_status_color(pr.status)}"))
    print(f"  {pr.title}")
    print()
    print(f"  {dim('branch:')}  {pr.branch}  →  {pr.base_branch}")
    print(f"  {dim('author:')}  {pr.author}")
    print(f"  {dim('updated:')} {pr.days_old}d ago")
    print(f"  {dim('CI:')}      {_ci_icon(pr.ci_status)} {pr.ci_status}")
    if pr.review_decision:
        print(f"  {dim('review:')} {pr.review_decision}")
    if pr.worktree_path:
        print(f"  {dim('worktree:')} {cyan(pr.worktree_path)}")
    if pr.blast_radius:
        print()
        print(f"  {bold('Graph impact:')}  {pr.blast_radius}")
        print(f"  {dim('communities:')} {pr.communities_touched}")
        if pr.files_changed:
            print(f"  {dim('files changed:')} {len(pr.files_changed)}")
            for f in pr.files_changed[:10]:
                print(f"    {dim(f)}")
            if len(pr.files_changed) > 10:
                print(dim(f"    … and {len(pr.files_changed) - 10} more"))
    print()


