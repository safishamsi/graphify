from .core import *
from pathlib import Path


def extract_lua(path: Path) -> dict:
    """Extract functions, methods, require() imports, and calls from a .lua file."""
    return _extract_generic(path, _LUA_CONFIG)


__all__ = ['extract_lua']
