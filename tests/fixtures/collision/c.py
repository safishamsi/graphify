"""Fixture for cross-file call-collision tests — unique-candidate caller.

c.py calls `only_in_a()` which exists in only one other file (a.py),
so the call must resolve to a single INFERRED edge at 0.8.
"""


def caller_unique():
    return only_in_a()  # noqa: F821 — resolved via cross-file pass
