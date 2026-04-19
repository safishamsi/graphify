"""Structured observability helpers for the detector pipeline."""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from depos.analysis.config import IntelligenceConfig


def _path(config: IntelligenceConfig, run_id: str) -> Path:
    out_dir = config.data_dir / config.run_output_subdir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "observability.jsonl"


def emit_event(config: IntelligenceConfig, run_id: str, stage: str, **payload: Any) -> Path:
    path = _path(config, run_id)
    record = {"run_id": run_id, "stage": stage, **payload}
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, default=str) + "\n")
    return path


@contextmanager
def timed_stage(config: IntelligenceConfig, run_id: str, stage: str, **payload: Any) -> Iterator[dict[str, Any]]:
    started = time.perf_counter()
    state: dict[str, Any] = dict(payload)
    try:
        yield state
    finally:
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        emit_event(config, run_id, stage, elapsed_ms=elapsed_ms, **state)


__all__ = ["emit_event", "timed_stage"]
