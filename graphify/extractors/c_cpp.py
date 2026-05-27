from .core import *
from pathlib import Path


def extract_c(path: Path) -> dict:
    """Extract functions and includes from a .c/.h file."""
    return _extract_generic(path, _C_CONFIG)


def extract_cpp(path: Path) -> dict:
    """Extract functions, classes, and includes from a .cpp/.cc/.cxx/.hpp file."""
    return _extract_generic(path, _CPP_CONFIG)


__all__ = ['extract_c', 'extract_cpp']
