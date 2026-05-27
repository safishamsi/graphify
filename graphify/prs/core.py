from __future__ import annotations
import sys
from pathlib import Path
from .models import red
from .github import fetch_prs, fetch_worktrees, _detect_default_branch
from .impact import attach_graph_impact
from .render import render_dashboard, render_worktrees, render_conflicts, render_pr_detail
from .ai import triage_with_opus
def cmd_prs(argv: list[str]) -> None:
    base: str | None = None  # auto-detected from repo if not given
    repo: str | None = None
    do_triage = False
    do_worktrees = False
    do_conflicts = False
    show_wrong_base = False
    pr_number: int | None = None
    graph_path = Path("graphify-out/graph.json")

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--triage":
            do_triage = True
        elif arg == "--worktrees":
            do_worktrees = True
        elif arg == "--conflicts":
            do_conflicts = True
        elif arg == "--wrong-base":
            show_wrong_base = True
        elif arg in ("--base", "-b") and i + 1 < len(argv):
            base = argv[i + 1]; i += 1
        elif arg.startswith("--base="):
            base = arg.split("=", 1)[1]
        elif arg in ("--repo", "-R") and i + 1 < len(argv):
            repo = argv[i + 1]; i += 1
        elif arg.startswith("--graph="):
            graph_path = Path(arg.split("=", 1)[1])
        elif arg == "--graph" and i + 1 < len(argv):
            graph_path = Path(argv[i + 1]); i += 1
        elif arg.lstrip("#").isdigit():
            pr_number = int(arg.lstrip("#"))
        elif arg in ("-h", "--help"):
            print(__doc__)
            return
        i += 1

    if base is None:
        base = _detect_default_branch(repo)

    try:
        prs = fetch_prs(repo=repo, base=base)
    except RuntimeError as e:
        print(red(f"  Error: {e}"), file=sys.stderr)
        sys.exit(1)

    worktrees = fetch_worktrees()
    for pr in prs:
        pr.worktree_path = worktrees.get(pr.branch)

    # Graph impact is expensive (concurrent gh pr diff calls) — only fetch when
    # the user actually needs it: deep dive, triage, and conflict detection.
    community_labels: dict[int, list[str]] = {}
    needs_impact = graph_path.exists() and (pr_number is not None or do_triage or do_conflicts)
    if needs_impact:
        community_labels = attach_graph_impact(prs, graph_path, repo)

    if pr_number is not None:
        match = next((p for p in prs if p.number == pr_number), None)
        if not match:
            print(red(f"  PR #{pr_number} not found in open PRs."), file=sys.stderr)
            sys.exit(1)
        render_pr_detail(match, repo)
        return

    if do_triage:
        render_dashboard(prs, base, show_wrong_base)
        triage_with_opus(prs, base)
        return

    if do_worktrees:
        render_worktrees(prs, worktrees)
        return

    if do_conflicts:
        render_dashboard(prs, base, show_wrong_base)
        render_conflicts(prs, base, community_labels)
        return

    render_dashboard(prs, base, show_wrong_base)
