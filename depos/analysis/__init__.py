"""depOS intelligence analysis package.

All Pydantic models for JSON contracts live in :mod:`depos.analysis.schemas`.
Runtime config lives in :mod:`depos.analysis.config`. Modules 2\u20137 (candidate
identification, context bundles, reasoning, ranker, verifier, gray zone) all
import types from ``schemas`` \u2014 there is NO ``depos/intelligence_types.py``.
"""
