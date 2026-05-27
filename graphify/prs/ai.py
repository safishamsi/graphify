from __future__ import annotations
import os
import sys
import json
from .models import PRInfo, bold, dim, red
# Best model per backend for reasoning tasks (different from extraction defaults)
_TRIAGE_MODEL_DEFAULTS: dict[str, str] = {
    "claude": "claude-opus-4-7",
    "kimi":   "kimi-k2.6",
    "openai": "gpt-4.1-mini",
    "gemini": "gemini-3-flash-preview",
}


def _resolve_triage_backend() -> tuple[str, str]:
    """Return (backend, model) using GRAPHIFY_TRIAGE_BACKEND or first available key."""
    from graphify.llm.core import BACKENDS, _get_backend_api_key, _default_model_for_backend

    explicit = os.environ.get("GRAPHIFY_TRIAGE_BACKEND", "").strip()
    if explicit in BACKENDS:
        model = (os.environ.get("GRAPHIFY_TRIAGE_MODEL")
                 or _TRIAGE_MODEL_DEFAULTS.get(explicit)
                 or _default_model_for_backend(explicit))
        return explicit, model

    for b in ("claude", "kimi", "openai", "gemini"):
        if _get_backend_api_key(b):
            model = (os.environ.get("GRAPHIFY_TRIAGE_MODEL")
                     or _TRIAGE_MODEL_DEFAULTS.get(b)
                     or _default_model_for_backend(b))
            return b, model

    import shutil
    if shutil.which("claude"):
        return "claude-cli", "claude-code-plan"

    return "ollama", _default_model_for_backend("ollama")


def triage_with_opus(prs: list[PRInfo], base: str) -> None:
    try:
        from graphify.llm.core import BACKENDS, _get_backend_api_key
    except ImportError:
        print(red("  graphify.llm not available — cannot run triage."), file=sys.stderr)
        sys.exit(1)

    candidates = [p for p in prs if p.base_branch == base and p.status not in ("WRONG-BASE", "STALE")]
    if not candidates:
        print(dim("  No actionable PRs to triage."))
        return

    lines = []
    for pr in candidates:
        impact = f", blast_radius={pr.blast_radius}" if pr.blast_radius else ""
        lines.append(
            f"PR #{pr.number} [{pr.status}] CI={pr.ci_status} review={pr.review_decision or 'none'} "
            f"age={pr.days_old}d author={pr.author}{impact}\n  title: {pr.title}"
        )

    prompt = (
        "You are a senior engineer helping triage a PR review queue. "
        "Given these open PRs, rank them by review priority for the repo maintainer. "
        "For each PR give: priority number, one sentence on what action to take and why. "
        "Be direct and specific. Format each as: #<number> — <action>.\n\n"
        + "\n\n".join(lines)
    )

    try:
        backend, model = _resolve_triage_backend()
    except Exception as e:
        print(red(f"  Could not resolve triage backend: {e}"), file=sys.stderr)
        sys.exit(1)

    print()
    print(bold("  Triage") + dim(f" ({backend} / {model})"))
    print()

    try:
        if backend == "claude":
            import anthropic
            client = anthropic.Anthropic(api_key=_get_backend_api_key("claude"))
            with client.messages.stream(
                model=model, max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                print("  ", end="", flush=True)
                for text in stream.text_stream:
                    print(text.replace("\n", "\n  "), end="", flush=True)
            print("\n")

        elif backend in ("kimi", "openai", "gemini", "ollama"):
            from openai import OpenAI
            cfg = BACKENDS[backend]
            api_key = _get_backend_api_key(backend) or "ollama"
            client = OpenAI(api_key=api_key, base_url=cfg.get("base_url", ""))
            with client.chat.completions.create(
                model=model, max_tokens=1024, stream=True,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                print("  ", end="", flush=True)
                for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        print(delta.replace("\n", "\n  "), end="", flush=True)
            print("\n")

        elif backend == "claude-cli":
            import subprocess as _sp
            proc = _sp.run(
                ["claude", "-p", "--no-session-persistence"],
                input=prompt, capture_output=True, text=True, timeout=120,
            )
            if proc.returncode != 0:
                print(red(f"  claude -p failed: {proc.stderr.strip()[:300]}"), file=sys.stderr)
            else:
                try:
                    result = json.loads(proc.stdout).get("result") or proc.stdout
                except json.JSONDecodeError:
                    result = proc.stdout
                for line in result.splitlines():
                    print(f"  {line}")
                print()

    except Exception as e:
        print(f"\n\n  {red(f'Triage failed: {e}')}", file=sys.stderr)


# ── Entry point ───────────────────────────────────────────────────────────────
