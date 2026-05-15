"""Fixture: a class that inherits from a base defined outside this corpus.

The base class `ExternalBase` is not defined in any other fixture, so the AST
extractor must emit it as a stub node so the `inherits` edge survives.
"""


class LocalClass(ExternalBase):  # noqa: F821 - intentionally undefined; this is a parse-only fixture
    def method(self):
        return 1
