# Plugin architecture for language extractors and custom extensions.
# Plugins are arbitrary Python imported via importlib, so auto-discovery
# is OFF by default — set GRAPHIFY_ENABLE_PLUGINS=1 to opt in. Tests and
# in-process callers can still register extractors directly via
# register_extractor() without flipping the env var.
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Callable

# Registry: file_suffix → extractor_function
_EXTRACTOR_REGISTRY: dict[str, Callable[[Path], dict]] = {}

_DEFAULT_PLUGIN_DIRS = [
    Path.home() / ".graphify" / "plugins",
    Path(".").resolve() / "graphify-plugins",
]


def _auto_discover_enabled() -> bool:
    """Return True if file-based plugin discovery is opted in."""
    return os.environ.get("GRAPHIFY_ENABLE_PLUGINS", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _discover_plugins() -> list[Path]:
    """Find all .py files in plugin directories."""
    plugins: list[Path] = []
    for directory in _DEFAULT_PLUGIN_DIRS:
        if directory.is_dir():
            for f in directory.glob("*.py"):
                if f.name.startswith("_"):
                    continue
                plugins.append(f)
    return plugins


def _load_plugin(path: Path) -> dict | None:
    """Load a single plugin file and return its register() dict."""
    try:
        spec = importlib.util.spec_from_file_location(
            f"graphify_plugin_{path.stem}", str(path)
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        # Avoid polluting sys.modules with transient plugin names
        sys.modules[module.__name__] = module
        spec.loader.exec_module(module)
        register = getattr(module, "register", None)
        if callable(register):
            return register()
    except Exception as exc:
        print(f"[graphify] Plugin error in {path}: {exc}", file=sys.stderr)
    return None


def load_plugins() -> dict[str, Callable[[Path], dict]]:
    """Discover and load all plugins, returning the merged extractor registry.

    File-based discovery runs only when GRAPHIFY_ENABLE_PLUGINS is set —
    auto-importing arbitrary Python from ~/.graphify/plugins/ on every
    invocation is a code-execution sink, so opting in is required.
    register_extractor() still works without the flag.

    Each plugin must expose a `register()` function that returns a dict mapping
    file suffixes (e.g. '.hs') to extractor functions:

        def register():
            return {".hs": extract_haskell}

    Extractor functions receive a Path and return a dict with "nodes" and "edges".
    """
    global _EXTRACTOR_REGISTRY
    if _EXTRACTOR_REGISTRY:
        return dict(_EXTRACTOR_REGISTRY)

    if not _auto_discover_enabled():
        return dict(_EXTRACTOR_REGISTRY)

    for plugin_path in _discover_plugins():
        mapping = _load_plugin(plugin_path)
        if mapping and isinstance(mapping, dict):
            for suffix, fn in mapping.items():
                if callable(fn):
                    _EXTRACTOR_REGISTRY[suffix] = fn
                else:
                    print(
                        f"[graphify] Plugin {plugin_path}: value for {suffix} is not callable",
                        file=sys.stderr,
                    )

    return dict(_EXTRACTOR_REGISTRY)


def get_extractor(suffix: str) -> Callable[[Path], dict] | None:
    """Return the extractor function for a file suffix, or None."""
    registry = load_plugins()
    return registry.get(suffix)


def list_plugins() -> list[str]:
    """Return a list of discovered plugin file paths."""
    return [str(p) for p in _discover_plugins()]


def reset_registry() -> None:
    """Clear the plugin registry (useful for testing)."""
    global _EXTRACTOR_REGISTRY
    _EXTRACTOR_REGISTRY = {}


def register_extractor(suffix: str, fn: Callable[[Path], dict]) -> None:
    """Programmatically register an extractor (useful for tests and built-ins)."""
    _EXTRACTOR_REGISTRY[suffix] = fn
