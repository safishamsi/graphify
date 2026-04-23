"""Fixture for cross-file call-collision tests — ambiguous caller.

d.py calls `shared()` which exists in both a.py and b.py, so the cross-file
resolution pass must emit two AMBIGUOUS edges (score 0.2, ambiguity_degree=2)
instead of silently picking one winner.
"""


def caller_ambiguous():
    return shared()  # noqa: F821 — resolved via cross-file pass
