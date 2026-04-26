# Configurable path resolution for graphify outputs (set via GRAPHIFY_HOME).
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HOME_NAME = ".graphify"
LEGACY_HOME_NAME = "graphify-out"
ENV_HOME = "GRAPHIFY_HOME"


def home_name() -> str:
    """Configured home dir name (env GRAPHIFY_HOME or DEFAULT_HOME_NAME). Read each call."""
    val = os.environ.get(ENV_HOME, "").strip()
    return val or DEFAULT_HOME_NAME


def home(root: Path | str = Path(".")) -> Path:
    return Path(root).resolve() / home_name()


def cache_dir(root: Path | str = Path("."), *, create: bool = True) -> Path:
    d = home(root) / "cache"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def manifest_path(root: Path | str = Path(".")) -> Path:
    return home(root) / "manifest.json"


def memory_dir(root: Path | str = Path(".")) -> Path:
    return home(root) / "memory"


def converted_dir(root: Path | str = Path(".")) -> Path:
    return home(root) / "converted"


def graph_path(root: Path | str = Path(".")) -> Path:
    return home(root) / "graph.json"


def report_path(root: Path | str = Path(".")) -> Path:
    return home(root) / "GRAPH_REPORT.md"


def cost_path(root: Path | str = Path(".")) -> Path:
    return home(root) / "cost.json"


def needs_update_path(root: Path | str = Path(".")) -> Path:
    return home(root) / "needs_update"


def has_legacy_layout(root: Path | str = Path(".")) -> bool:
    """True iff GRAPHIFY_HOME unset, ``graphify-out/`` exists, and the default home does not."""
    if os.environ.get(ENV_HOME, "").strip():
        return False
    r = Path(root).resolve()
    return (r / LEGACY_HOME_NAME).is_dir() and not (r / DEFAULT_HOME_NAME).exists()


def auto_migrate(root: Path | str = Path(".")) -> bool:
    """Rename ``graphify-out/`` to the configured home on legacy layouts. Returns True if migrated.

    Conservative: never overwrites or merges. Use ``graphify migrate-home --force``
    to resolve a side-by-side layout manually.
    """
    if not has_legacy_layout(root):
        return False
    r = Path(root).resolve()
    (r / LEGACY_HOME_NAME).rename(r / home_name())
    return True
