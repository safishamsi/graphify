"""graphify - extract · build · cluster · analyze · report."""

# Lazy-import map: attribute name -> (module, attribute).
# Defined at module level so it is not rebuilt on every __getattr__ call.
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "extract": ("graphify.extract", "extract"),
    "collect_files": ("graphify.extract", "collect_files"),
    "build_from_json": ("graphify.build", "build_from_json"),
    "cluster": ("graphify.cluster", "cluster"),
    "score_all": ("graphify.cluster", "score_all"),
    "cohesion_score": ("graphify.cluster", "cohesion_score"),
    "god_nodes": ("graphify.analyze", "god_nodes"),
    "surprising_connections": ("graphify.analyze", "surprising_connections"),
    "suggest_questions": ("graphify.analyze", "suggest_questions"),
    "graph_diff": ("graphify.analyze", "graph_diff"),
    "generate": ("graphify.report", "generate"),
    "to_json": ("graphify.export", "to_json"),
    "to_html": ("graphify.export", "to_html"),
    "to_svg": ("graphify.export", "to_svg"),
    "to_canvas": ("graphify.export", "to_canvas"),
    "to_wiki": ("graphify.wiki", "to_wiki"),
}


def __getattr__(name: str):
    """Lazy imports so `graphify install` works before heavy deps are in place."""
    if name in _LAZY_IMPORTS:
        import importlib
        mod_name, attr = _LAZY_IMPORTS[name]
        mod = importlib.import_module(mod_name)
        return getattr(mod, attr)
    raise AttributeError(f"module 'graphify' has no attribute {name!r}")
