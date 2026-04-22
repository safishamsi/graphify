"""Extract monorepo workspace structure from melos.yaml."""
from __future__ import annotations

import re
from pathlib import Path


def _make_id(*parts: str) -> str:
    combined = "_".join(p.strip("_.") for p in parts if p)
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", combined)
    return cleaned.strip("_").lower()


def extract_melos(path: Path) -> dict:
    """Parse melos.yaml and return nodes/edges for the workspace structure."""
    try:
        import yaml
    except ImportError:
        return {"nodes": [], "edges": [], "error": "pyyaml not installed"}

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    if not isinstance(data, dict):
        return {"nodes": [], "edges": [], "error": "invalid melos.yaml format"}

    nodes: list[dict] = []
    edges: list[dict] = []
    str_path = str(path)

    name = data.get("name", "unknown")
    ws_id = _make_id(name)

    ws_node: dict = {
        "id": ws_id,
        "label": name,
        "file_type": "config",
        "source_file": str_path,
        "dart_kind": "workspace",
    }
    nodes.append(ws_node)

    # Resolve package globs to discover actual packages
    package_globs = data.get("packages", [])
    if isinstance(package_globs, list):
        base_dir = path.parent
        for glob_pattern in package_globs:
            if not isinstance(glob_pattern, str):
                continue
            # Each glob should point to directories containing pubspec.yaml
            for pubspec_path in sorted(base_dir.glob(f"{glob_pattern}/pubspec.yaml")):
                # Security: ensure resolved path stays within the workspace
                try:
                    resolved = pubspec_path.resolve()
                    if not str(resolved).startswith(str(base_dir.resolve())):
                        continue
                except (OSError, ValueError):
                    continue
                try:
                    pkg_data = yaml.safe_load(pubspec_path.read_text(encoding="utf-8"))
                    if isinstance(pkg_data, dict) and "name" in pkg_data:
                        pkg_name = pkg_data["name"]
                        pkg_id = _make_id(pkg_name)
                        edges.append({
                            "source": ws_id,
                            "target": pkg_id,
                            "relation": "workspace_contains",
                            "confidence": "EXTRACTED",
                            "confidence_score": 1.0,
                            "source_file": str_path,
                            "weight": 1.0,
                        })
                except Exception:
                    continue

    return {"nodes": nodes, "edges": edges}
