"""graphify - extract · build · cluster · analyze · report."""

# Expose the vendored tree-sitter-rescript binding under its conventional
# top-level name so `importlib.import_module("tree_sitter_rescript")` in
# graphify.extract resolves without a per-language detour. The vendored
# source lives under graphify/_vendor/tree_sitter_rescript/ and matches
# the upstream PyPI binding's surface (`.language()`).
import sys as _sys

if "tree_sitter_rescript" not in _sys.modules:
    try:
        from graphify._vendor import tree_sitter_rescript as _vendored_tsr
        _sys.modules["tree_sitter_rescript"] = _vendored_tsr
    except ImportError:
        # _binding.so not built yet (e.g. during `pip install` before the
        # extension compiles, or in a partial sdist). Leave the import error
        # to surface naturally when extract.py tries to load the module.
        pass


def __getattr__(name):
    # Lazy imports so `graphify install` works before heavy deps are in place.
    _map = {
        "extract": ("graphify.extract", "extract"),
        "collect_files": ("graphify.extract", "collect_files"),
        "build_from_json": ("graphify.build", "build_from_json"),
        "cluster": ("graphify.cluster", "cluster"),
        "score_all": ("graphify.cluster", "score_all"),
        "cohesion_score": ("graphify.cluster", "cohesion_score"),
        "god_nodes": ("graphify.analyze", "god_nodes"),
        "surprising_connections": ("graphify.analyze", "surprising_connections"),
        "suggest_questions": ("graphify.analyze", "suggest_questions"),
        "generate": ("graphify.report", "generate"),
        "to_json": ("graphify.export", "to_json"),
        "to_html": ("graphify.export", "to_html"),
        "to_svg": ("graphify.export", "to_svg"),
        "to_canvas": ("graphify.export", "to_canvas"),
        "to_wiki": ("graphify.wiki", "to_wiki"),
    }
    if name in _map:
        import importlib
        mod_name, attr = _map[name]
        mod = importlib.import_module(mod_name)
        return getattr(mod, attr)
    raise AttributeError(f"module 'graphify' has no attribute {name!r}")
