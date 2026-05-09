"""Vendored third-party packages.

`tree_sitter_rescript` is vendored here because there is no PyPI release of
the upstream Python binding. We expose it as the top-level `tree_sitter_rescript`
module via a sys.modules alias in graphify.__init__ so that
`importlib.import_module("tree_sitter_rescript")` continues to work in
graphify.extract without changing the per-language config pattern.

See graphify/_vendor/tree_sitter_rescript/LICENSE for upstream licensing.
"""
