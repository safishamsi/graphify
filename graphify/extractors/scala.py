from .core import *
from pathlib import Path


def extract_scala(path: Path) -> dict:
    """Extract classes, objects, functions, and imports from a .scala file."""
    return _extract_generic(path, _SCALA_CONFIG)


__all__ = ['extract_scala']
