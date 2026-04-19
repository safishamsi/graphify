"""Module 4 — reasoning engine.

Responsibilities:

- Provider abstraction: Gemma (HTTP), OpenAI (HTTP), Ollama (HTTP), plus
  an always-available :class:`StubProvider` used by tests and when no
  external service is configured.
- Three prompt modes (A/B/C) with strict JSON outputs validated against
  :class:`ModeAOutput` / :class:`ModeBOutput` / :class:`ModeCOutput`.
- Typed exception dispatch so every failure mode (transport, empty
  response, not JSON, JSON-but-invalid-schema) is recorded in
  :class:`ReasonerCallStats` and on the corresponding
  :class:`ReasonerQueueRow`.
- JSON repair pass before strict validation that strips ```` ```json ````
  fences/trailing commas and lifts a single-finding dict into the
  expected ``{"findings": [<dict>]}`` envelope. Each repair attempt is
  recorded in ``validation_errors`` so the change is auditable.
- Replay queue entries are JSONL rows under
  ``<DEPOS_DATA>/intelligence/<run_id>/reasoner_queue.jsonl`` matching
  :class:`ReasonerQueueRow`. The full prompt body is cached once per
  unique hash under ``<run_dir>/prompts/<sha>.json`` so
  :func:`replay_one` can re-issue without re-running upstream stages.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Tuple

from pydantic import ValidationError

from depos.analysis.config import IntelligenceConfig
from depos.analysis.schemas import (
    Candidate,
    ContextBundle,
    ModeAOutput,
    ModeBOutput,
    ModeCOutput,
    ReasonerCallStats,
    ReasonerMode,
    ReasonerQueueRow,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider abstraction
# ---------------------------------------------------------------------------


class ProviderError(Exception):
    """Wrap provider transport/decoding failures with a typed reason."""

    def __init__(
        self,
        reason: str,
        message: str,
        *,
        http_status: Optional[int] = None,
        raw_excerpt: str = "",
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.http_status = http_status
        self.raw_excerpt = raw_excerpt


class ReasoningProvider:
    """Minimal interface. Implementations must return a raw string.

    Implementations should raise :class:`ProviderError` so the caller can
    record a typed ``failure_reason``.
    """

    name: str = "base"

    def complete(self, prompt: str, *, max_tokens: int) -> Tuple[str, dict[str, Any]]:
        """Return ``(text, meta)``.

        ``meta`` must include ``model`` and may include
        ``response_path_used`` to help operators tune
        ``ReasonerProviderConfig`` after the fact.
        """
        raise NotImplementedError


class StubProvider(ReasoningProvider):
    """Returns a minimal, valid JSON doc for each mode. Used in tests and
    when no external service is reachable. Keeps the pipeline runnable
    out of the box without network access."""

    name = "stub"

    def __init__(self, mode: ReasonerMode):
        self.mode = mode

    def complete(self, prompt: str, *, max_tokens: int) -> Tuple[str, dict[str, Any]]:
        if self.mode == ReasonerMode.A:
            text = json.dumps({"mode": "A", "findings": []})
        elif self.mode == ReasonerMode.B:
            text = json.dumps({"mode": "B", "findings": []})
        else:
            text = json.dumps({"mode": "C", "findings": []})
        return text, {"model": "stub", "response_path_used": "literal"}


# ---------------------------------------------------------------------------
# Response path extraction
# ---------------------------------------------------------------------------


_PATH_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def _extract_by_path(data: Any, path: str) -> Any:
    """Walk a dotted/bracketed path. Returns ``None`` on miss.

    Accepts ``"choices[0].message.content"``-style expressions. We do not
    eval, only walk dict keys and list indices.
    """
    if not path:
        return None
    cursor: Any = data
    for raw_key, raw_idx in _PATH_TOKEN.findall(path):
        try:
            if raw_idx:
                cursor = cursor[int(raw_idx)]
            elif isinstance(cursor, dict):
                cursor = cursor.get(raw_key)
            else:
                return None
        except (KeyError, IndexError, TypeError):
            return None
        if cursor is None:
            return None
    return cursor


def _extract_text(data: Any, paths: list[str]) -> Tuple[str, Optional[str]]:
    """Try each path in order; return ``(text, path_used)``.

    Returns ``("", None)`` if every path misses or yields a non-string.
    """
    for path in paths:
        if not path:
            continue
        value = _extract_by_path(data, path)
        if isinstance(value, str) and value.strip():
            return value, path
        if isinstance(value, (dict, list)):
            # Some providers nest the JSON object directly.
            return json.dumps(value), path
    return "", None


class _HTTPProvider(ReasoningProvider):
    """Shared helper that POSTs JSON to a URL and parses a single string field."""

    name = "http"

    def __init__(
        self,
        url: Optional[str],
        *,
        header_key: Optional[str] = None,
        header_value: Optional[str] = None,
        response_paths: list[str],
        model: str,
    ):
        self.url = url
        self.headers = {"Content-Type": "application/json"}
        if header_key and header_value:
            self.headers[header_key] = header_value
        self.response_paths = response_paths
        self.model = model

    def complete(self, prompt: str, *, max_tokens: int) -> Tuple[str, dict[str, Any]]:
        if not self.url:
            raise ProviderError("transport", f"{self.name}: no URL configured")
        try:
            import httpx  # lazy import so tests without httpx still work
        except ImportError as exc:  # pragma: no cover - dev safety
            raise ProviderError("transport", f"httpx unavailable: {exc}") from exc

        body = self._build_body(prompt, max_tokens=max_tokens)
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(self.url, json=body, headers=self.headers)
        except httpx.RequestError as exc:
            raise ProviderError("transport", f"{self.name} request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise ProviderError(
                "transport",
                f"{self.name} HTTP {resp.status_code}",
                http_status=resp.status_code,
                raw_excerpt=_clip(resp.text, 2048),
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError(
                "not_json",
                f"{self.name} returned non-JSON body: {exc}",
                http_status=resp.status_code,
                raw_excerpt=_clip(resp.text, 2048),
            ) from exc

        text, path_used = _extract_text(data, self.response_paths)
        if not text:
            raise ProviderError(
                "empty_response",
                f"{self.name} produced no extractable text",
                http_status=resp.status_code,
                raw_excerpt=_clip(json.dumps(data), 2048),
            )
        return text, {"model": self.model, "response_path_used": path_used or ""}

    def _build_body(self, prompt: str, *, max_tokens: int) -> dict[str, Any]:
        return {"prompt": prompt, "max_tokens": max_tokens}


def _clip(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


# Common Gemma response shapes — tried in order if the configured path
# misses. Keeps deployments without code changes for known servers.
_GEMMA_FALLBACK_PATHS: list[str] = [
    "response",
    "text",
    "candidates[0].content.parts[0].text",
    "candidates[0].text",
    "output[0].generated_text",
    "outputs[0].text",
]

_OPENAI_FALLBACK_PATHS: list[str] = [
    "choices[0].message.content",
    "choices[0].text",
]

_OLLAMA_FALLBACK_PATHS: list[str] = ["response", "message.content"]


class GemmaProvider(_HTTPProvider):
    name = "gemma"

    def __init__(
        self,
        url: Optional[str],
        *,
        model: str = "gemma-4",
        response_path: str = "response",
    ):
        paths = [response_path] + [p for p in _GEMMA_FALLBACK_PATHS if p != response_path]
        super().__init__(url, response_paths=paths, model=model)

    def _build_body(self, prompt: str, *, max_tokens: int) -> dict[str, Any]:
        return {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "format": "json",
        }


class OpenAIProvider(_HTTPProvider):
    name = "openai"

    def __init__(
        self,
        api_key: Optional[str],
        *,
        model: str = "gpt-4o-mini",
        response_path: str = "choices[0].message.content",
    ):
        paths = [response_path] + [p for p in _OPENAI_FALLBACK_PATHS if p != response_path]
        super().__init__(
            "https://api.openai.com/v1/chat/completions",
            header_key="Authorization",
            header_value=f"Bearer {api_key}" if api_key else None,
            response_paths=paths,
            model=model,
        )

    def _build_body(self, prompt: str, *, max_tokens: int) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }


class OllamaProvider(_HTTPProvider):
    name = "ollama"

    def __init__(
        self,
        host: Optional[str],
        *,
        model: str = "gemma:2b",
        response_path: str = "response",
    ):
        import os as _os

        base = host or _os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
        paths = [response_path] + [p for p in _OLLAMA_FALLBACK_PATHS if p != response_path]
        super().__init__(
            f"{base.rstrip('/')}/api/generate",
            response_paths=paths,
            model=model,
        )

    def _build_body(self, prompt: str, *, max_tokens: int) -> dict[str, Any]:
        return {
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"num_predict": max_tokens},
        }


def get_provider(config: IntelligenceConfig, mode: ReasonerMode) -> ReasoningProvider:
    name = (config.reasoner.provider or "stub").lower()
    if name == "openai":
        return OpenAIProvider(
            config.reasoner.openai_api_key,
            model=config.reasoner.openai_model,
            response_path=config.reasoner.openai_response_path,
        )
    if name == "gemma":
        if config.reasoner.gemma_api_url:
            return GemmaProvider(
                config.reasoner.gemma_api_url,
                model=config.reasoner.gemma_model,
                response_path=config.reasoner.gemma_response_path,
            )
        return StubProvider(mode)
    if name == "ollama":
        return OllamaProvider(
            config.reasoner.ollama_host,
            model=config.reasoner.ollama_model,
            response_path=config.reasoner.ollama_response_path,
        )
    return StubProvider(mode)


# ---------------------------------------------------------------------------
# Prompts
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
            {
                "node_id": s.node_id,
                "file": s.source_file,
                "text": s.text[:4000],
                "evidence_quality": s.evidence_quality,
            }
            for s in bundle.code_snippets
        ],
    }
    if graphcodebert_hint:
        body["graphcodebert_hint"] = graphcodebert_hint
    return f"{header}\n```json\n{json.dumps(body, indent=2)}\n```"


# ---------------------------------------------------------------------------
# Parsing + JSON repair
# ---------------------------------------------------------------------------

_MODE_SCHEMA = {
    ReasonerMode.A: ModeAOutput,
    ReasonerMode.B: ModeBOutput,
    ReasonerMode.C: ModeCOutput,
}

_FENCE_OPEN = re.compile(r"^\s*```(?:json|JSON)?\s*", re.MULTILINE)
_FENCE_CLOSE = re.compile(r"\s*```\s*$", re.MULTILINE)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _strip_fences_and_trailing_commas(raw: str) -> str:
    no_open = _FENCE_OPEN.sub("", raw)
    no_close = _FENCE_CLOSE.sub("", no_open)
    return _TRAILING_COMMA.sub(r"\1", no_close).strip()


def _coerce_envelope(mode: ReasonerMode, data: Any) -> tuple[dict[str, Any], list[str]]:
    """Try to coerce arbitrary JSON into the expected mode envelope.

    Returns the (possibly rewritten) dict plus a list of repair tags.
    """
    repairs: list[str] = []
    if isinstance(data, list):
        repairs.append("wrap_list_into_findings")
        data = {"mode": mode.value, "findings": data}
    if not isinstance(data, dict):
        return {"mode": mode.value, "findings": []}, repairs + ["non_object_replaced_with_empty"]
    if "findings" not in data:
        # If it looks like a single finding, lift it.
        if any(key in data for key in ("bug_type", "violation_type", "flow_bug_type")):
            repairs.append("lift_single_finding")
            data = {"mode": mode.value, "findings": [data]}
        else:
            repairs.append("inject_empty_findings")
            data = {**data, "findings": data.get("findings", [])}
    if "mode" not in data:
        repairs.append("inject_mode")
        data = {**data, "mode": mode.value}
    return data, repairs


def _parse(mode: ReasonerMode, raw: str) -> tuple[Any, list[str]]:
    """Strict-validate ``raw`` into the mode schema.

    Returns ``(parsed_obj, repair_tags)``. Raises ``json.JSONDecodeError``
    if no JSON can be recovered, or ``pydantic.ValidationError`` if the
    JSON does not match the mode schema.
    """
    schema = _MODE_SCHEMA[mode]
    cleaned = _strip_fences_and_trailing_commas(raw)
    repairs: list[str] = []
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first == -1 or last == -1 or last <= first:
            # Try a list outermost as a last resort.
            list_first = cleaned.find("[")
            list_last = cleaned.rfind("]")
            if list_first == -1 or list_last == -1 or list_last <= list_first:
                raise
            repairs.append("substring_recover_list")
            data = json.loads(cleaned[list_first : list_last + 1])
        else:
            repairs.append("substring_recover_object")
            data = json.loads(cleaned[first : last + 1])

    coerced, coercion_repairs = _coerce_envelope(mode, data)
    repairs.extend(coercion_repairs)
    return schema.model_validate(coerced), repairs


# ---------------------------------------------------------------------------
# Queue + prompt cache
# ---------------------------------------------------------------------------


def _queue_path(config: IntelligenceConfig, run_id: str) -> Path:
    out = config.data_dir / config.run_output_subdir / run_id
    out.mkdir(parents=True, exist_ok=True)
    return out / "reasoner_queue.jsonl"


def _prompts_dir(config: IntelligenceConfig, run_id: str) -> Path:
    out = config.data_dir / config.run_output_subdir / run_id / "prompts"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _cache_prompt(config: IntelligenceConfig, run_id: str, prompt: str, mode: ReasonerMode) -> str:
    sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    target = _prompts_dir(config, run_id) / f"{sha}.json"
    if not target.exists():
        target.write_text(
            json.dumps({"mode": mode.value, "prompt": prompt}, indent=2),
            encoding="utf-8",
        )
    return sha


def _enqueue(
    config: IntelligenceConfig,
    run_id: str,
    bundle: ContextBundle,
    mode: ReasonerMode,
    ranking_phase: int,
    *,
    failure_reason: str,
    http_status: Optional[int],
    attempt_count: int,
    validation_errors: list[dict[str, Any]],
    raw_response_excerpt: str,
    provider_name: str,
    model: str,
    prompt_hash: str,
    prompt_token_estimate: int,
    response_path_used: Optional[str],
    graphcodebert_score: float = 0.0,
    graphcodebert_pattern: str = "",
    extra: Optional[dict[str, Any]] = None,
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
        failure_reason=failure_reason,  # type: ignore[arg-type]
        http_status=http_status,
        attempt_count=attempt_count,
        validation_errors=validation_errors,
        raw_response_excerpt=raw_response_excerpt,
        provider_name=provider_name,
        model=model,
        request_payload_sha256=prompt_hash,
        prompt_token_estimate=prompt_token_estimate,
        response_path_used=response_path_used,
        extra=extra or {},
    )
    with _queue_path(config, run_id).open("a", encoding="utf-8") as fp:
        fp.write(row.model_dump_json() + "\n")


# ---------------------------------------------------------------------------
# Reasoner runners
# ---------------------------------------------------------------------------


def run_reasoner(
    bundle: ContextBundle,
    *,
    mode: ReasonerMode,
    config: IntelligenceConfig,
    run_id: str,
    ranking_phase: int = 0,
    graphcodebert_hint: Optional[dict[str, Any]] = None,
    stats: Optional[ReasonerCallStats] = None,
) -> Optional[ModeAOutput | ModeBOutput | ModeCOutput]:
    provider = get_provider(config, mode)
    prompt = _render_prompt(mode, bundle, graphcodebert_hint=graphcodebert_hint)
    prompt_hash = _cache_prompt(config, run_id, prompt, mode)
    prompt_token_estimate = max(1, len(prompt) // 4)
    attempts = max(1, config.reasoner.max_retries + 1)

    last_failure_reason = "other"
    last_http_status: Optional[int] = None
    last_validation_errors: list[dict[str, Any]] = []
    last_raw_excerpt = ""
    last_response_path: Optional[str] = None
    last_attempt = 0
    last_repairs: list[str] = []
    provider_model = ""
    provider_name = getattr(provider, "name", provider.__class__.__name__)

    for attempt_idx in range(1, attempts + 1):
        last_attempt = attempt_idx
        try:
            raw, meta = provider.complete(prompt, max_tokens=config.reasoner.default_max_tokens)
            provider_model = str(meta.get("model", ""))
            last_response_path = meta.get("response_path_used") or last_response_path
            parsed, repairs = _parse(mode, raw)
            last_repairs = repairs
            if stats is not None:
                stats.record_success(mode.value)
            if repairs:
                logger.info(
                    "reasoner_call_repaired",
                    extra={
                        "mode": mode.value,
                        "provider": provider_name,
                        "repairs": repairs,
                        "candidate_id": bundle.candidate_id,
                    },
                )
            return parsed
        except ProviderError as exc:
            last_failure_reason = exc.reason
            last_http_status = exc.http_status
            last_raw_excerpt = exc.raw_excerpt or str(exc)
            logger.warning(
                "reasoner_call_failed",
                extra={
                    "mode": mode.value,
                    "provider": provider_name,
                    "reason": exc.reason,
                    "http_status": exc.http_status,
                    "attempt": attempt_idx,
                    "candidate_id": bundle.candidate_id,
                },
            )
        except json.JSONDecodeError as exc:
            last_failure_reason = "not_json"
            last_raw_excerpt = _clip(getattr(exc, "doc", "") or str(exc), 2048)
            logger.warning(
                "reasoner_call_failed",
                extra={
                    "mode": mode.value,
                    "provider": provider_name,
                    "reason": "not_json",
                    "attempt": attempt_idx,
                    "candidate_id": bundle.candidate_id,
                },
            )
        except ValidationError as exc:
            last_failure_reason = "json_but_invalid_schema"
            last_validation_errors = [
                {k: _stringify(v) for k, v in err.items()} for err in exc.errors()
            ]
            logger.warning(
                "reasoner_call_failed",
                extra={
                    "mode": mode.value,
                    "provider": provider_name,
                    "reason": "json_but_invalid_schema",
                    "errors": len(last_validation_errors),
                    "attempt": attempt_idx,
                    "candidate_id": bundle.candidate_id,
                },
            )
        except Exception as exc:  # noqa: BLE001
            last_failure_reason = "other"
            last_raw_excerpt = _clip(str(exc), 2048)
            logger.warning(
                "reasoner_call_failed",
                extra={
                    "mode": mode.value,
                    "provider": provider_name,
                    "reason": "other",
                    "attempt": attempt_idx,
                    "candidate_id": bundle.candidate_id,
                },
            )
        time.sleep(0.1)

    if stats is not None:
        stats.record_failure(mode.value, last_failure_reason)
    extra_meta: dict[str, Any] = {}
    if last_repairs:
        extra_meta["repairs"] = last_repairs
    _enqueue(
        config,
        run_id,
        bundle,
        mode,
        ranking_phase,
        failure_reason=last_failure_reason,
        http_status=last_http_status,
        attempt_count=last_attempt,
        validation_errors=last_validation_errors,
        raw_response_excerpt=last_raw_excerpt,
        provider_name=provider_name,
        model=provider_model,
        prompt_hash=prompt_hash,
        prompt_token_estimate=prompt_token_estimate,
        response_path_used=last_response_path,
        graphcodebert_score=float((graphcodebert_hint or {}).get("score", 0.0)),
        graphcodebert_pattern=str((graphcodebert_hint or {}).get("pattern", "")),
        extra=extra_meta,
    )
    return None


def _stringify(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_stringify(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _stringify(v) for k, v in value.items()}
    return str(value)


def run_all_modes(
    bundle: ContextBundle,
    *,
    config: IntelligenceConfig,
    run_id: str,
    ranking_phase: int = 0,
    graphcodebert_hint: Optional[dict[str, Any]] = None,
    stats: Optional[ReasonerCallStats] = None,
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
            stats=stats,
        )
        if result is not None:
            out[mode] = result
    return out


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


def replay_one(
    row: dict[str, Any],
    *,
    config: IntelligenceConfig,
    run_id: str | None = None,
) -> Iterable[Any]:
    """Re-issue a single queued reasoner call.

    Reads the prompt body from ``<DEPOS_DATA>/intelligence/<run_id>/prompts/<sha>.json``
    if available; otherwise yields nothing. On success returns the parsed
    mode output. On failure, appends a fresh queue row with
    ``attempt_count`` incremented.

    ``run_id`` may be provided explicitly when the caller knows it (e.g., from
    the queue-file path). Otherwise it falls back to the row's own ``run_id``.
    """
    sha = str(row.get("request_payload_sha256") or "")
    mode_raw = str(row.get("mode") or "")
    try:
        mode = ReasonerMode(mode_raw)
    except ValueError:
        return []

    resolved_run_id = run_id or _infer_run_id(row)
    if not resolved_run_id or not sha:
        return []
    run_id = resolved_run_id

    prompt_path = config.data_dir / config.run_output_subdir / run_id / "prompts" / f"{sha}.json"
    if not prompt_path.exists():
        return []
    try:
        cached = json.loads(prompt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    prompt = str(cached.get("prompt") or "")
    if not prompt:
        return []

    provider = get_provider(config, mode)
    prior_attempts = int(row.get("attempt_count") or 0)
    try:
        raw, meta = provider.complete(prompt, max_tokens=config.reasoner.default_max_tokens)
        parsed, _ = _parse(mode, raw)
        return [parsed]
    except (ProviderError, json.JSONDecodeError, ValidationError) as exc:
        failure_reason = (
            exc.reason if isinstance(exc, ProviderError)
            else "not_json" if isinstance(exc, json.JSONDecodeError)
            else "json_but_invalid_schema"
        )
        # Append a fresh queue row reflecting the replay attempt.
        queue_path = (
            config.data_dir / config.run_output_subdir / run_id / "reasoner_queue.jsonl"
        )
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        new_row = {
            **row,
            "failure_reason": failure_reason,
            "attempt_count": prior_attempts + 1,
            "queued_at": datetime.now(tz=timezone.utc).isoformat(),
            "raw_response_excerpt": _clip(
                getattr(exc, "raw_excerpt", "") or str(exc), 2048
            ),
        }
        with queue_path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(new_row) + "\n")
        return []


def _infer_run_id(row: dict[str, Any]) -> str:
    # Best-effort: the row itself may not include run_id; the canonical
    # location is the parent directory of the queue file. If the caller
    # passes a row with explicit ``run_id``, honor it.
    if row.get("run_id"):
        return str(row["run_id"])
    queued_at = row.get("queued_at")
    if not queued_at:
        return ""
    return ""


__all__ = [
    "ReasoningProvider",
    "StubProvider",
    "GemmaProvider",
    "OpenAIProvider",
    "OllamaProvider",
    "ProviderError",
    "get_provider",
    "run_reasoner",
    "run_all_modes",
    "replay_one",
]
