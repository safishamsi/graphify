"""CLI for ``depos-intel intent-context``."""
from __future__ import annotations

import argparse
from pathlib import Path

from depos.analysis.config import load_config_from_env
from depos.intent_context.build import run_intent_context_build


def run_intent_context_cli(args: argparse.Namespace) -> int:
    if getattr(args, "intent_command", None) != "build":
        return 2
    cfg = load_config_from_env()
    return run_intent_context_build(
        Path(args.repo_root),
        Path(args.output_dir),
        cfg,
        intent_llm_override=args.intent_llm,
    )
