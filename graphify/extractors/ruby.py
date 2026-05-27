from .core import *
from pathlib import Path


def extract_ruby(path: Path) -> dict:
    """Extract classes, methods, singleton methods, and calls from a .rb file."""
    return _extract_generic(path, _RUBY_CONFIG)


__all__ = ['extract_ruby']
