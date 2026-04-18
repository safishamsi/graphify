"""Module 4 \u2014 reasoning engine.

Responsibilities:

- Provider abstraction: Gemma (HTTP), OpenAI (HTTP), Ollama (HTTP), plus
  an always-available :class:`StubProvider` used by tests and when no
  external service is configured.
- Three prompt modes (A/B/C) with strict JSON outputs validated against
  :class:`ModeAOutput` / :class:`ModeBOutput` / :class:`ModeCOutput`.
- Retry on JSON validation failure (``max_retries`` from config). If
  retries are exhausted, write the bundle to the replay queue and return
  an empty output so the pipeline keeps going.
- Replay queue entries are JSONL rows under
  ``<DEPOS_DATA>/intelligence/<run_id>/reasoner_queue.jsonl`` and match
  :class:`ReasonerQueueRow`.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from pydantic import ValidationError

from depos.analysis.config import IntelligenceConfig
from depos.analysis.schemas import (
    Candidate,
    ContextBundle,
    ModeAOutput,
    ModeBOutput,
    ModeCOutput,
    ReasonerMode,
    ReasonerQueueRow,
)


# ---------------------------------------------------------------------------
# Provider abstraction
# ---------------------------------------------------------------------------


class ReasoningProvider:
    """Minimal interface. Implementations must return a raw string."""

    name: str = "base"

    def complete(self, prompt: str, *, max_tokens: int) -> str:
        raise NotImplementedError


class StubProvider(ReasoningProvider):
    """Returns a minimal, valid JSON doc for each mode. Used in tests and
    when no external service is reachable. Keeps the pipeline runnable
    out of the box without network access."""

    name = "stub"

    def __init__(self, mode: ReasonerMode):
        self.mode = mode

    def complete(self, prompt: str, *, max_tokens: int) -> str:
        if self.mode == ReasonerMode.A:
            return json.dumps({"mode": "A", "findings": []})
        if self.mode == ReasonerMode.B:
            return json.dumps({"mode": "B", "findings": []})
        return json.dumps({"mode": "C", "findings": []})


class _HTTPProvider(ReasoningProvider):
    """Shared helper that POSTs JSON to a URL and parses a single string field."""

    name = "http"

    def __init__(self, url: Optional[str], *, header_key: Optional[str] = None, header_value: Optional[str] = None):
        self.url = url
        self.headers = {"Content-Type": "application/json"}
        if header_key and header_value:
            self.headers[header_key] = header_value

    def complete(self, prompt: str, *, max_tokens: int) -> str:
        if not self.url:
            raise RuntimeError(f"{self.name}: no URL configured")
        import httpx  # lazy import so tests without httpx still work

        body = self._build_body(prompt, max_tokens=max_tokens)
        with httpx.Client(timeout=30) as client:
            resp = client.post(self.url, json=body, headers=self.headers)
            resp.raise_for_status()
            return self._extract(resp.json())

    def _build_body(self, prompt: str, *, max_tokens: int) -> dict[str, Any]:
        return {"prompt": prompt, "max_tokens": max_tokens}

    def _extract(self, data: Any) -> str:
        return str(data)


class GemmaProvider(_HTTPProvider):
    name = "gemma"

    def __init__(self, url: Optional[str], *, model: str = "gemma-4"):
        super().__init__(url)
        self.model = model

    def _build_body(self, prompt: str, *, max_tokens: int) -> dict[str, Any]:
        return {"model": self.model, "prompt": prompt, "max_tokens": max_tokens, "format": "json"}

    def _extract(self, data: Any) -> str:
        if isinstance(data, dict):
            return str(data.get("response") or data.get("text") or data)
        return str(data)


class OpenAIProvider(_HTTPProvider):
    name = "openai"

    def __init__(self, api_key: Optional[str]):
        super().__init__(
            "https://api.openai.com/v1/chat/completions",
            header_key="Authorization",
            header_value=f"Bearer {api_key}" if api_key else None,
        )

    def _build_body(self, prompt: str, *, max_tokens: int) -> dict[str, Any]:
        return {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

    def _extract(self, data: Any) -> str:
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return json.dumps(data)


class OllamaProvider(_HTTPProvider):
    name = "ollama"

    def __init__(self, host: Optional[str]):
        base = host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
        super().__init__(f"{base.rstrip('/')}/api/generate")

    def _build_body(self, prompt: str, *, max_tokens: int) -> dict[str, Any]:
        return {"model": "gemma:2b", "prompt": prompt, "format": "json", "stream": False}

    def _extract(self, data: Any) -> str:
        return str(data.get("response", "")) if isinstance(data, dict) else str(data)


def get_provider(config: IntelligenceConfig, mode: ReasonerMode) -> ReasoningProvider:
    name = (config.reasoner.provider or "stub").lower()
    if name == "openai":
        return OpenAIProvider(config.reasoner.openai_api_key)
    if name == "gemma":
        if config.reasoner.gemma_api_url:
            return GemmaProvider(config.reasoner.gemma_api_url, model=config.reasoner.gemma_model)
        return StubProvider(mode)
    if name == "ollama":
        return OllamaProvider(config.reasoner.ollama_host)
    return StubProvider(mode)


# ---------------------------------------------------------------------------
# Prompts (concise; full prompt engineering lives outside this repo)
# ---------------------------------------------------------------------------

_PROMPT_HEAD = """You are a software reasoning engine. Output ONLY JSON that matches the schema for the requested mode.

Mode A: pattern-based bugs (null ref, off-by-one, missing error handling).
Mode B: semantic mismatches (client contract vs server behavior).
Mode C: control/data flow bugs (missing guards, payload drift).

NEVER include natural language outside the JSON document.
"""


def _render_prompt(
    mode: ReasonerMode,
    bundle: ContextBundle,
    *,
    graphcodebert_hint: Optional[dict[str, Any]] = None,
) -> str:
    header = _PROMPT_HEAD
    body = {
        "candidate_id": bundle.candidate_id,
        "scope_id": bundle.scope_id,
        "mode": mode.value,
        "data_reads": bundle.data_reads,
        "data_writes": bundle.data_writes,
        "rls_coverage": {k: v.value for k, v in bundle.rls_coverage.items()},
        "migration_state": {k: v.value for k, v in bundle.migration_state.items()},
        "cross_language_seams": [e.model_dump(mode="json") for e in bundle.cross_language_seams],
        "code_snippets": [
            {"node_id": s.node_id, "file": s.source_file, "text": s.text[:4000]}
            for s in bundle.code_snippets
        ],
    }
    if graphcodebert_hint:
        body["graphcodebert_hint"] = graphcodebert_hint
    return f"{header}\n```json\n{json.dumps(body, indent=2)}\n```"


# ---------------------------------------------------------------------------
# Reasoner runners
# ---------------------------------------------------------------------------


_MODE_SCHEMA = {
    ReasonerMode.A: ModeAOutput,
    ReasonerMode.B: ModeBOutput,
    ReasonerMode.C: ModeCOutput,
}


def _parse(mode: ReasonerMode, raw: str):
    schema = _MODE_SCHEMA[mode]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract a JSON object if the model added noise.
        first = raw.find("{")
        last = raw.rfind("}")
        if first == -1 or last == -1 or last <= first:
            raise
        data = json.loads(raw[first : last + 1])
    return schema.model_validate(data)


def _queue_path(config: IntelligenceConfig, run_id: str) -> Path:
    out = config.data_dir / config.run_output_subdir / run_id
    out.mkdir(parents=True, exist_ok=True)
    return out / "reasoner_queue.jsonl"


def _enqueue(
    config: IntelligenceConfig,
    run_id: str,
    bundle: ContextBundle,
    mode: ReasonerMode,
    ranking_phase: int,
    *,
    graphcodebert_score: float = 0.0,
    graphcodebert_pattern: str = "",
) -> None:
    row = ReasonerQueueRow(
        bundle_id=bundle.bundle_id,
        candidate_id=bundle.candidate_id,
        mode=mode,
        evidence_pack={"data_reads": bundle.data_reads, "data_writes": bundle.data_writes},
        pack_manifest=bundle.pack_manifest,
        graphcodebert_score=graphcodebert_score,
        graphcodebert_pattern=graphcodebert_pattern,
        ranking_phase=ranking_phase,
        queued_at=datetime.now(tz=timezone.utc),
    )
    with _queue_path(config, run_id).open("a", encoding="utf-8") as fp:
        fp.write(row.model_dump_json() + "\n")


def run_reasoner(
    bundle: ContextBundle,
    *,
    mode: ReasonerMode,
    config: IntelligenceConfig,
    run_id: str,
    ranking_phase: int = 0,
    graphcodebert_hint: Optional[dict[str, Any]] = None,
) -> Optional[ModeAOutput | ModeBOutput | ModeCOutput]:
    provider = get_provider(config, mode)
    prompt = _render_prompt(mode, bundle, graphcodebert_hint=graphcodebert_hint)
    attempts = max(1, config.reasoner.max_retries + 1)
    last_error: Optional[Exception] = None
    for _ in range(attempts):
        try:
            raw = provider.complete(prompt, max_tokens=config.reasoner.default_max_tokens)
            return _parse(mode, raw)
        except (json.JSONDecodeError, ValidationError, RuntimeError) as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.1)
    # Exhausted: enqueue for later replay.
    _enqueue(
        config,
        run_id,
        bundle,
        mode,
        ranking_phase,
        graphcodebert_score=float((graphcodebert_hint or {}).get("score", 0.0)),
        graphcodebert_pattern=str((graphcodebert_hint or {}).get("pattern", "")),
    )
    return None


def run_all_modes(
    bundle: ContextBundle,
    *,
    config: IntelligenceConfig,
    run_id: str,
    ranking_phase: int = 0,
    graphcodebert_hint: Optional[dict[str, Any]] = None,
) -> dict[ReasonerMode, Any]:
    out: dict[ReasonerMode, Any] = {}
    for mode in (ReasonerMode.A, ReasonerMode.B, ReasonerMode.C):
        result = run_reasoner(
            bundle,
            mode=mode,
            config=config,
            run_id=run_id,
            ranking_phase=ranking_phase,
            graphcodebert_hint=graphcodebert_hint,
        )
        if result is not None:
            out[mode] = result
    return out


def replay_one(row: dict, *, config: IntelligenceConfig) -> Iterable[Any]:
    """Consumer of the replay queue rows \u2014 called from
    :func:`depos.cli.analyze.run_replay`. For MVP we return an empty list;
    individual deployments can extend this to re-render prompts and re-query
    providers after backoffs.
    """
    return []


__all__ = [
    "ReasoningProvider",
    "StubProvider",
    "GemmaProvider",
    "OpenAIProvider",
    "OllamaProvider",
    "get_provider",
    "run_reasoner",
    "run_all_modes",
    "replay_one",
]
