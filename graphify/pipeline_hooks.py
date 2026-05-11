"""External hook chain execution.

Graphify runs hook entries as separate processes. Hook code is never imported
into the graphify process; data is exchanged through JSON files and environment
variables.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


ENRICHMENT_DIR = "enrichment"
_TRUTHY = {"1", "true", "yes", "on"}


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _hooks_enabled_from_env() -> bool:
    if _env_truthy("GRAPHIFY_NO_HOOKS"):
        return False
    return _env_truthy("GRAPHIFY_ENABLE_HOOKS") or _env_truthy("GRAPHIFY_ALLOW_HOOKS")


@dataclass(frozen=True)
class HookState:
    """Loaded hook config plus the user-controlled execution gate."""

    config: dict
    enabled: bool
    lsp_entries: tuple[dict, ...]

    @property
    def has_lsp_hooks(self) -> bool:
        return bool(self.lsp_entries)

    @property
    def lsp_enabled(self) -> bool:
        return self.enabled and self.has_lsp_hooks

    @property
    def disabled_lsp_hooks(self) -> bool:
        return self.has_lsp_hooks and not self.enabled


def _graphify_python(root: Path) -> str:
    for version_file in (root / ".graphify_python", root / "graphify-out" / ".graphify_python"):
        if not version_file.exists():
            continue
        try:
            for line in version_file.read_text(encoding="utf-8").splitlines():
                candidate = line.strip()
                if not candidate or candidate.startswith("File:"):
                    continue
                return candidate
        except OSError:
            pass
    return sys.executable


def load_hook_config(root: Path) -> dict:
    """Load repo hook config. Missing config means no hooks."""
    env_path = os.environ.get("GRAPHIFY_CONFIG", "").strip()
    if env_path:
        path = Path(env_path).expanduser()
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    path = root / ".graphify" / "config.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def hooks_enabled() -> bool:
    """Return true when the user explicitly allows repo-configured hooks.

    Hook config lives in the target repository and can execute arbitrary
    commands, so command execution must be opted into from the user's
    environment rather than enabled by the repo itself.
    """
    return _hooks_enabled_from_env()


def _as_hook_list(value: object) -> list[dict]:
    if isinstance(value, dict):
        return [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _stage_hooks(config: dict, stage: str) -> list[dict]:
    hooks = config.get("hooks", {})
    if not isinstance(hooks, dict):
        return []
    return _as_hook_list(hooks.get(stage, []))


def _with_chain_defaults(chain: dict, hook: dict, index: int) -> dict:
    merged = dict(hook)
    if "languages" not in merged and "languages" in chain:
        merged["languages"] = chain["languages"]
    if "timeout_seconds" not in merged and "timeout_seconds" in chain:
        merged["timeout_seconds"] = chain["timeout_seconds"]
    if "required" not in merged and "required" in chain:
        merged["required"] = chain["required"]
    chain_name = chain.get("name")
    if chain_name and "name" in merged:
        merged["name"] = f"{chain_name}:{merged['name']}"
    elif chain_name:
        merged["name"] = f"{chain_name}[{index}]"
    return merged


def lsp_hooks(config: dict) -> list[dict]:
    """Return configured LSP hook chain entries.

    Supported config shapes:

    - ``{"lsp": {"hooks": [...]}}`` or ``{"lsp": {"servers": [...]}}``
    - ``{"lsp": {"chains": [{"languages": [...], "hooks": [...]}]}}``

    Chains let one language run several external resolvers, e.g. Ruby LSP,
    Solargraph, and Steep/RBS.
    """
    lsp = config.get("lsp")
    if isinstance(lsp, list):
        return _as_hook_list(lsp)
    if not isinstance(lsp, dict):
        return []

    hooks: list[dict] = []
    hooks.extend(_as_hook_list(lsp.get("hooks", [])))
    hooks.extend(_as_hook_list(lsp.get("servers", [])))
    for chain in _as_hook_list(lsp.get("chains", [])):
        entries = _as_hook_list(chain.get("hooks", []))
        entries.extend(_as_hook_list(chain.get("servers", [])))
        for idx, hook in enumerate(entries):
            hooks.append(_with_chain_defaults(chain, hook, idx))
    return hooks


def has_lsp_hooks(config: dict) -> bool:
    return bool(lsp_hooks(config))


def load_hook_state(root: Path, config: dict | None = None) -> HookState:
    """Load repo hook config and compute hook execution state once."""
    resolved_config = config if config is not None else load_hook_config(root)
    return HookState(
        config=resolved_config,
        enabled=hooks_enabled(),
        lsp_entries=tuple(lsp_hooks(resolved_config)),
    )


def has_disabled_lsp_hooks(root: Path) -> bool:
    """Return true when a repo configures LSP hooks but execution is not enabled."""
    try:
        return load_hook_state(root).disabled_lsp_hooks
    except Exception:
        return False


def _hook_matches_languages(hook: dict, languages: set[str]) -> bool:
    raw = hook.get("languages")
    if raw in (None, [], "*"):
        return True
    if isinstance(raw, str):
        hook_languages = {raw}
    elif isinstance(raw, list):
        hook_languages = {str(v) for v in raw}
    else:
        return False
    return "*" in hook_languages or bool(hook_languages & languages)


def _command_args(command: str | list, placeholders: dict[str, str]) -> list[str]:
    if isinstance(command, str):
        parts = shlex.split(command)
    elif isinstance(command, list):
        parts = [str(p) for p in command]
    else:
        raise ValueError("hook command must be a string or list")
    return [part.format(**placeholders) for part in parts]


def _run_hooks(
    hooks: list[dict],
    stage: str,
    *,
    root: Path,
    graphify_out: Path,
    languages: set[str],
    unresolved_calls_path: Path,
    enrichment_dir: Path | None = None,
    parallel: bool = False,
    max_parallel: int | None = None,
    enabled: bool,
) -> list[str]:
    if not enabled:
        return []
    if not hooks:
        return []

    enrichment_dir = enrichment_dir or (graphify_out / ENRICHMENT_DIR)
    enrichment_dir.mkdir(parents=True, exist_ok=True)
    placeholders = {
        "root": str(root),
        "graphify_out": str(graphify_out),
        "unresolved_calls": str(unresolved_calls_path),
        "enrichment_dir": str(enrichment_dir),
        "languages": ",".join(sorted(languages)),
        "stage": stage,
        "python": _graphify_python(root),
    }
    env = os.environ.copy()
    env.update({
        "GRAPHIFY_ROOT": str(root),
        "GRAPHIFY_OUT": str(graphify_out),
        "GRAPHIFY_UNRESOLVED_CALLS": str(unresolved_calls_path),
        "GRAPHIFY_ENRICHMENT_DIR": str(enrichment_dir),
        "GRAPHIFY_STAGE": stage,
        "GRAPHIFY_LANGUAGES": placeholders["languages"],
    })

    jobs: list[dict] = []
    for idx, hook in enumerate(hooks):
        if hook.get("enabled", True) is False:
            continue
        if not _hook_matches_languages(hook, languages):
            continue
        name = str(hook.get("name") or f"{stage}[{idx}]")
        command = hook.get("command")
        if not command:
            raise ValueError(f"hook {name!r} is missing 'command'")
        args = _command_args(command, placeholders)
        timeout = hook.get("timeout_seconds")
        timeout_arg = float(timeout) if timeout not in (None, "") else None
        if timeout_arg is not None and timeout_arg <= 0:
            timeout_arg = None
        required = hook.get("required", True) is not False
        hook_env = env.copy()
        hook_env["GRAPHIFY_HOOK_NAME"] = name
        hook_env["GRAPHIFY_HOOK_INDEX"] = str(idx)
        jobs.append({
            "idx": idx,
            "name": name,
            "args": args,
            "timeout": timeout_arg,
            "required": required,
            "env": hook_env,
        })

    def run_one(job: dict) -> tuple[int, str, bool, str | None]:
        name = job["name"]
        print(f"[graphify hooks] running {stage}:{name}", flush=True)
        try:
            result = subprocess.run(
                job["args"],
                cwd=root,
                env=job["env"],
                text=True,
                timeout=job["timeout"],
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            timeout = job["timeout"]
            msg = f"hook {name!r} timed out after {timeout:.1f} seconds" if timeout else f"hook {name!r} timed out"
            return job["idx"], name, False, msg
        except Exception as exc:
            return job["idx"], name, False, f"hook {name!r} failed to start: {exc}"
        if result.returncode != 0:
            return job["idx"], name, False, f"hook {name!r} exited with status {result.returncode}"
        return job["idx"], name, True, None

    if not jobs:
        return []

    results: list[tuple[int, str, bool, str | None]] = []
    if parallel and len(jobs) > 1:
        default_workers = os.cpu_count() or 1
        workers = max_parallel or min(default_workers, len(jobs))
        workers = max(1, min(workers, len(jobs)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run_one, job) for job in jobs]
            for future in as_completed(futures):
                results.append(future.result())
    else:
        results = [run_one(job) for job in jobs]

    required_by_name = {job["name"]: job["required"] for job in jobs}
    failures = []
    ran = []
    for _idx, name, ok, error in sorted(results, key=lambda item: item[0]):
        if ok:
            ran.append(name)
        elif required_by_name.get(name, True):
            failures.append(error or f"hook {name!r} failed")
        else:
            print(f"[graphify hooks] warning: {error}", file=sys.stderr)
    if failures:
        raise RuntimeError(failures[0])
    return ran


def run_lsp_hooks(
    *,
    root: Path,
    graphify_out: Path,
    languages: set[str],
    unresolved_calls_path: Path,
    enrichment_dir: Path | None = None,
    config: dict | None = None,
    state: HookState | None = None,
) -> list[str]:
    """Run configured LSP hook chain entries."""
    state = state or load_hook_state(root, config)
    config = state.config
    enrichment_dir = enrichment_dir or (graphify_out / ENRICHMENT_DIR / "lsp")
    lsp_config = config.get("lsp", {}) if isinstance(config.get("lsp"), dict) else {}
    parallel = lsp_config.get("parallel_hooks", True) is not False
    max_parallel = lsp_config.get("max_parallel_hooks")
    try:
        max_parallel_arg = int(max_parallel) if max_parallel not in (None, "") else None
    except (TypeError, ValueError):
        max_parallel_arg = None
    return _run_hooks(
        list(state.lsp_entries),
        "lsp_enrichment",
        root=root,
        graphify_out=graphify_out,
        languages=languages,
        unresolved_calls_path=unresolved_calls_path,
        enrichment_dir=enrichment_dir,
        parallel=parallel,
        max_parallel=max_parallel_arg,
        enabled=state.enabled,
    )


def run_external_hooks(
    stage: str,
    *,
    root: Path,
    graphify_out: Path,
    languages: set[str],
    unresolved_calls_path: Path,
    config: dict | None = None,
    state: HookState | None = None,
) -> list[str]:
    """Run configured generic external commands for one pipeline stage."""
    state = state or load_hook_state(root, config)
    return _run_hooks(
        _stage_hooks(state.config, stage),
        stage,
        root=root,
        graphify_out=graphify_out,
        languages=languages,
        unresolved_calls_path=unresolved_calls_path,
        enabled=state.enabled,
    )
