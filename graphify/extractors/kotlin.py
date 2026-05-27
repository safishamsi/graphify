from .core import *
from pathlib import Path


def extract_kotlin(path: Path) -> dict:
    """Extract classes, objects, functions, and imports from a .kt/.kts file."""
    return _extract_generic(path, _KOTLIN_CONFIG)


__all__ = ['extract_kotlin']
