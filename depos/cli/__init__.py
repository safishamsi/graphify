"""depos-intel console script entrypoint.

``main()`` is the setup.py entry target. Dispatches to subcommands:

- ``repo``      full-repo scan
- ``diff``      diff-aware analysis
- ``replay``    replay a persisted ``reasoner_queue.jsonl``
- ``coverage``  print the StitcherCoverageReport only (no reasoning)
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="depos-intel", description="depOS AI intelligence CLI.")
    sub = p.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Run or inspect intelligence analyses.")
    a_sub = analyze.add_subparsers(dest="analyze_command", required=True)

    repo = a_sub.add_parser("repo", help="Full-repo scan (no diff required).")
    repo.add_argument("--path", required=True)
    repo.add_argument("--output")
    repo.add_argument("--mode", default="A,B,C")
    repo.add_argument("--provider", default=None)
    repo.add_argument("--export-training", action="store_true")
    repo.add_argument("--max-seeds", type=int, default=None)

    diff = a_sub.add_parser("diff", help="Diff-aware scan using a change manifest.")
    diff.add_argument("--cpg-path")
    diff.add_argument("--graph-json")
    diff.add_argument("--diff-path")
    diff.add_argument("--output")
    diff.add_argument("--mode", default="A,B,C")
    diff.add_argument("--provider", default=None)
    diff.add_argument("--export-training", action="store_true")

    replay = a_sub.add_parser("replay", help="Replay a reasoner queue.")
    replay.add_argument("--queue", required=True)
    replay.add_argument("--output")
    replay.add_argument("--provider", default=None)

    coverage = a_sub.add_parser("coverage", help="Print StitcherCoverageReport only.")
    coverage.add_argument("--path")
    coverage.add_argument("--graph-json")

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command != "analyze":
        parser.error(f"unknown command: {args.command}")
        return 2

    # Lazy imports so a bare ``depos-intel --help`` works without the
    # [depos] / [supabase] extras installed.
    if args.analyze_command == "coverage":
        from depos.cli.analyze import run_coverage

        return run_coverage(args)
    if args.analyze_command == "repo":
        from depos.cli.analyze import run_repo

        return run_repo(args)
    if args.analyze_command == "diff":
        from depos.cli.analyze import run_diff

        return run_diff(args)
    if args.analyze_command == "replay":
        from depos.cli.analyze import run_replay

        return run_replay(args)
    parser.error(f"unknown analyze subcommand: {args.analyze_command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
