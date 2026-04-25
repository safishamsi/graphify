"""Optional ``.depos/intent.yaml`` include/exclude globs."""
from __future__ import annotations

from pathlib import Path
from typing import Any

_DEFAULT_INCLUDES: list[str] = []


def load_intent_yaml(repo_root: Path) -> tuple[list[str], list[str]]:
    """Return ``(extra_include_globs, exclude_globs)`` from YAML if present."""
    path = repo_root / ".depos" / "intent.yaml"
    if not path.is_file():
        return [], []
    text = path.read_text(encoding="utf-8", errors="replace")
    data: dict[str, Any] = {}
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            data = loaded
    except Exception:
        return [], []
    inc = data.get("include_globs") or data.get("include") or _DEFAULT_INCLUDES
    exc = data.get("exclude_globs") or data.get("exclude") or []
    if not isinstance(inc, list):
        inc = []
    if not isinstance(exc, list):
        exc = []
    return [str(x) for x in inc if x], [str(x) for x in exc if x]
