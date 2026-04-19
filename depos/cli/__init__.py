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

    detectors = sub.add_parser("detectors", help="Inspect the detector registry.")
    d_sub = detectors.add_subparsers(dest="detectors_command", required=True)

    repo = a_sub.add_parser("repo", help="Full-repo scan (no diff required).")
    repo.add_argument("--path", required=True)
    repo.add_argument("--output")
    repo.add_argument("--mode", default="A,B,C")
    repo.add_argument("--provider", default=None)
    repo.add_argument("--export-training", action="store_true")
    repo.add_argument("--max-seeds", type=int, default=None)
    repo.add_argument("--detectors", action="append", default=[])
    repo.add_argument("--no-reasoner", action="store_true")
    repo.add_argument("--print-detector-stats", action="store_true")

    diff = a_sub.add_parser("diff", help="Diff-aware scan using a change manifest.")
    diff.add_argument("--cpg-path")
    diff.add_argument("--graph-json")
    diff.add_argument("--diff-path")
    diff.add_argument("--output")
    diff.add_argument("--mode", default="A,B,C")
    diff.add_argument("--provider", default=None)
    diff.add_argument("--export-training", action="store_true")
    diff.add_argument("--detectors", action="append", default=[])
    diff.add_argument("--no-reasoner", action="store_true")
    diff.add_argument("--print-detector-stats", action="store_true")

    replay = a_sub.add_parser("replay", help="Replay a reasoner queue.")
    replay.add_argument("--queue", required=True)
    replay.add_argument("--output")
    replay.add_argument("--provider", default=None)

    score_bundles = a_sub.add_parser("score-bundles", help="Score context bundles with GraphCodeBERT.")
    score_bundles.add_argument("--bundles-json", required=True)
    score_bundles.add_argument("--output")
    score_bundles.add_argument("--model-name", default="microsoft/graphcodebert-base")
    score_bundles.add_argument("--cache-dir")
    score_bundles.add_argument("--device")
    score_bundles.add_argument("--local-files-only", action="store_true")

    bundle_pipeline = a_sub.add_parser("bundle-pipeline", help="Run GraphCodeBERT -> Gemma -> verifier on bundles.")
    bundle_pipeline.add_argument("--bundles-json", required=True)
    bundle_pipeline.add_argument("--scores-json")
    bundle_pipeline.add_argument("--graph-json")
    bundle_pipeline.add_argument("--output-dir")
    bundle_pipeline.add_argument("--top-n", type=int, default=20)
    bundle_pipeline.add_argument("--min-score", type=float, default=None)
    bundle_pipeline.add_argument("--provider", default=None)
    bundle_pipeline.add_argument("--model-name", default="microsoft/graphcodebert-base")
    bundle_pipeline.add_argument("--cache-dir")
    bundle_pipeline.add_argument("--device")
    bundle_pipeline.add_argument("--local-files-only", action="store_true")

    normalize_dataset = a_sub.add_parser("normalize-dataset", help="Normalize raw dataset AST JSON into a richer node-link graph.")
    normalize_dataset.add_argument("--dataset-dir", required=True)
    normalize_dataset.add_argument("--output", required=True)
    normalize_dataset.add_argument("--repo-root", default=".")
    normalize_dataset.add_argument("--extraction-output")

    dataset_pipeline = a_sub.add_parser("dataset-pipeline", help="Run raw dataset AST files through normalize -> bundles -> GraphCodeBERT -> Gemma -> verifier.")
    dataset_pipeline.add_argument("--dataset-dir", required=True)
    dataset_pipeline.add_argument("--output-dir", required=True)
    dataset_pipeline.add_argument("--repo-root", default=".")
    dataset_pipeline.add_argument("--provider", default=None)
    dataset_pipeline.add_argument("--top-n", type=int, default=20)
    dataset_pipeline.add_argument("--max-bundles", type=int, default=None)
    dataset_pipeline.add_argument("--min-score", type=float, default=None)
    dataset_pipeline.add_argument("--write-extraction", action="store_true")
    dataset_pipeline.add_argument("--model-name", default="microsoft/graphcodebert-base")
    dataset_pipeline.add_argument("--cache-dir")
    dataset_pipeline.add_argument("--device")
    dataset_pipeline.add_argument("--local-files-only", action="store_true")

    coverage = a_sub.add_parser("coverage", help="Print StitcherCoverageReport only.")
    coverage.add_argument("--path")
    coverage.add_argument("--graph-json")

    list_cmd = d_sub.add_parser("list", help="List built-in detectors.")
    list_cmd.add_argument("--json", action="store_true")

    explain_cmd = d_sub.add_parser("explain", help="Explain one detector.")
    explain_cmd.add_argument("name")
    explain_cmd.add_argument("--json", action="store_true")

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Lazy imports so a bare ``depos-intel --help`` works without the
    # [depos] / [supabase] extras installed.
    if args.command == "analyze":
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
        if args.analyze_command == "score-bundles":
            from depos.cli.analyze import run_score_bundles

            return run_score_bundles(args)
        if args.analyze_command == "bundle-pipeline":
            from depos.cli.analyze import run_bundle_pipeline

            return run_bundle_pipeline(args)
        if args.analyze_command == "normalize-dataset":
            from depos.cli.analyze import run_normalize_dataset

            return run_normalize_dataset(args)
        if args.analyze_command == "dataset-pipeline":
            from depos.cli.analyze import run_dataset_pipeline

            return run_dataset_pipeline(args)
        parser.error(f"unknown analyze subcommand: {args.analyze_command}")
        return 2
    if args.command == "detectors":
        if args.detectors_command == "list":
            from depos.cli.analyze import run_detectors_list

            return run_detectors_list(args)
        if args.detectors_command == "explain":
            from depos.cli.analyze import run_detectors_explain

            return run_detectors_explain(args)
        parser.error(f"unknown detectors subcommand: {args.detectors_command}")
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
