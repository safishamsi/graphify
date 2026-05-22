"""Domain extension layer. Core pipeline handles code by default; domains add extra extraction."""
from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

import networkx as nx


class DomainExtractor(Protocol):
    """Protocol for domain-specific extractors."""

    name: str
    file_patterns: list[str]

    def extract(self, path: Path, content: str) -> dict:
        """Return {"nodes": [...], "edges": [...]}."""
        ...


@dataclass
class DomainSpec:
    """Declaration of a domain plugin."""

    name: str
    extractors: list = field(default_factory=list)
    relations: dict[str, list[str]] = field(default_factory=dict)  # category → relation names
    node_types: list[str] = field(default_factory=list)

    # Hooks (all optional)
    prompt_fragments: Callable[[], str] | None = None
    post_extract: Callable[[dict], dict] | None = None
    post_build: Callable[[nx.Graph], None] | None = None
    analyzers: list[Callable] = field(default_factory=list)


_DOMAINS: dict[str, DomainSpec] = {}


def register(spec: DomainSpec) -> None:
    """Register a domain plugin."""
    _DOMAINS[spec.name] = spec


def active_domains(config: dict | None = None) -> list[DomainSpec]:
    """Return domains listed in config. Empty list if none configured."""
    if not config or "domains" not in config:
        return []
    # Auto-discover entry-points on first call
    if not _DOMAINS:
        try:
            eps = importlib.metadata.entry_points(group="graphify.plugins")
        except TypeError:
            # Python 3.9 compat
            eps = importlib.metadata.entry_points().get("graphify.plugins", [])
        for ep in eps:
            try:
                factory = ep.load()
                spec = factory() if callable(factory) else factory
                if isinstance(spec, DomainSpec):
                    _DOMAINS[spec.name] = spec
            except Exception:
                pass
    # Also try importing built-in domains
    _load_builtin_domains()
    requested = config["domains"]
    return [_DOMAINS[k] for k in requested if k in _DOMAINS]


def _load_builtin_domains() -> None:
    """Import built-in domains from graphify.domains package."""
    import importlib
    import pkgutil

    try:
        import graphify.domains as pkg
    except ImportError:
        return
    for importer, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
        try:
            mod = importlib.import_module(f"graphify.domains.{modname}")
            # If the module has a _SPEC attribute, register it (handles re-import)
            spec = getattr(mod, "_SPEC", None)
            if spec is not None and isinstance(spec, DomainSpec) and spec.name not in _DOMAINS:
                _DOMAINS[spec.name] = spec
        except Exception:
            pass


def run_hooks(
    config: dict,
    extraction: dict,
    G: nx.Graph | None = None,
    *,
    hooks: list[str] | None = None,
    all_files: list[str] | None = None,
) -> tuple[dict, dict[str, list]]:
    """Execute domain hooks in order. Returns (modified_extraction, analysis_results).

    Parameters
    ----------
    config : dict with "domains" key listing active domain names
    extraction : merged extraction dict (nodes, edges, hyperedges)
    G : built graph (required for post_build and analyzers hooks)
    hooks : which hooks to run; None = all applicable. Options:
            "prompt_fragments", "extractors", "post_extract", "post_build", "analyzers"
    all_files : file paths for extractor hook (Hook 2)

    Returns
    -------
    (extraction, analysis) where analysis is {"{domain}.{analyzer_name}": [findings]}
    """
    import fnmatch

    domains = active_domains(config)
    if not domains:
        return extraction, {}

    run_all = hooks is None
    hook_set = set(hooks) if hooks else set()

    # Hook 2: extractors
    if run_all or "extractors" in hook_set:
        if all_files:
            nodes = extraction.get("nodes", [])
            edges = extraction.get("edges", [])
            for dom in domains:
                for extractor in dom.extractors:
                    for fpath in all_files:
                        p = Path(fpath)
                        for pattern in extractor.file_patterns:
                            if fnmatch.fnmatch(p.name, pattern):
                                try:
                                    content = p.read_text(errors="replace")
                                    result = extractor.extract(p, content)
                                    nodes.extend(result.get("nodes", []))
                                    edges.extend(result.get("edges", []))
                                except Exception:
                                    pass
                                break
            extraction = {**extraction, "nodes": nodes, "edges": edges}

    # Hook 3: post_extract
    if run_all or "post_extract" in hook_set:
        for dom in domains:
            if dom.post_extract:
                extraction = dom.post_extract(extraction)

    # Hook 4: post_build (requires G)
    if G is not None and (run_all or "post_build" in hook_set):
        for dom in domains:
            if dom.post_build:
                dom.post_build(G)

    # Hook 5: analyzers (requires G)
    analysis: dict[str, list] = {}
    if G is not None and (run_all or "analyzers" in hook_set):
        for dom in domains:
            for analyzer in dom.analyzers or []:
                key = f"{dom.name}.{analyzer.__name__}"
                analysis[key] = analyzer(G)

    return extraction, analysis
