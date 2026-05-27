from .core import *
import re
from pathlib import Path


def extract_dart(path: Path) -> dict:
    """Extract classes, mixins, functions, imports, and calls from a .dart file using regex."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"error": f"cannot read {path}"}

    # Use stem (not str(path)) for child IDs to keep them machine-independent.
    stem = _file_stem(path)
    file_nid = _make_id(str(path))
    nodes = [{"id": file_nid, "label": path.name, "file_type": "code",
              "source_file": str(path), "source_location": None}]
    edges = []
    defined: set[str] = set()

    # Classes and mixins
    for m in re.finditer(r"^\s*(?:abstract\s+)?(?:class|mixin)\s+(\w+)", src, re.MULTILINE):
        nid = _make_id(stem, m.group(1))
        if nid not in defined:
            nodes.append({"id": nid, "label": m.group(1), "file_type": "code",
                          "source_file": str(path), "source_location": None})
            edges.append({"source": file_nid, "target": nid, "relation": "defines",
                          "confidence": "EXTRACTED", "confidence_score": 1.0,
                          "source_file": str(path), "source_location": None, "weight": 1.0})
            defined.add(nid)

    # Top-level and member functions/methods
    for m in re.finditer(r"^\s*(?:static\s+|async\s+)?(?:\w+\s+)+(\w+)\s*\(", src, re.MULTILINE):
        name = m.group(1)
        if name in {"if", "for", "while", "switch", "catch", "return"}:
            continue
        nid = _make_id(stem, name)
        if nid not in defined:
            nodes.append({"id": nid, "label": name, "file_type": "code",
                          "source_file": str(path), "source_location": None})
            edges.append({"source": file_nid, "target": nid, "relation": "defines",
                          "confidence": "EXTRACTED", "confidence_score": 1.0,
                          "source_file": str(path), "source_location": None, "weight": 1.0})
            defined.add(nid)

    # import 'package:...' or import '...'
    for m in re.finditer(r"""^import\s+['"]([^'"]+)['"]""", src, re.MULTILINE):
        pkg = m.group(1)
        tgt_nid = _make_id(pkg)
        if tgt_nid not in defined:
            nodes.append({"id": tgt_nid, "label": pkg, "file_type": "code",
                          "source_file": str(path), "source_location": None})
            defined.add(tgt_nid)
        edges.append({"source": file_nid, "target": tgt_nid, "relation": "imports",
                      "confidence": "EXTRACTED", "confidence_score": 1.0,
                      "source_file": str(path), "source_location": None, "weight": 1.0})

    return {"nodes": nodes, "edges": edges}


__all__ = ['extract_dart']
