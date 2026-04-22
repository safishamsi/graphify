"""Extract package dependency graph from pubspec.yaml."""
from __future__ import annotations

import re
from pathlib import Path


def _make_id(*parts: str) -> str:
    combined = "_".join(p.strip("_.") for p in parts if p)
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", combined)
    return cleaned.strip("_").lower()


# SDK dependencies to skip (not meaningful as edges)
_SKIP_DEPS = frozenset({"flutter"})
_SKIP_DEV_DEPS = frozenset({"flutter_test"})


def extract_pubspec(path: Path) -> dict:
    """Parse pubspec.yaml and return nodes/edges for the package dependency graph."""
    try:
        import yaml
    except ImportError:
        return {"nodes": [], "edges": [], "error": "pyyaml not installed"}

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    if not isinstance(data, dict):
        return {"nodes": [], "edges": [], "error": "invalid pubspec format"}

    nodes: list[dict] = []
    edges: list[dict] = []
    str_path = str(path)

    name = data.get("name", "unknown")
    pkg_id = _make_id(name)

    # Determine project type: flutter if 'flutter' key exists at top level
    project_type = "flutter" if "flutter" in data else "dart"

    # SDK constraint
    env = data.get("environment", {})
    sdk_constraint = env.get("sdk") if isinstance(env, dict) else None

    pkg_node: dict = {
        "id": pkg_id,
        "label": name,
        "file_type": "config",
        "source_file": str_path,
        "dart_kind": "package",
        "project_type": project_type,
    }
    if data.get("version"):
        pkg_node["version"] = data["version"]
    if data.get("description"):
        pkg_node["description"] = data["description"]
    if sdk_constraint:
        pkg_node["sdk_constraint"] = sdk_constraint

    nodes.append(pkg_node)

    # --- dependencies ---
    deps = data.get("dependencies", {})
    if isinstance(deps, dict):
        for dep_name, dep_spec in deps.items():
            if dep_name in _SKIP_DEPS:
                continue
            # Check for sdk dependency
            if isinstance(dep_spec, dict) and "sdk" in dep_spec:
                continue
            dep_id = _make_id(dep_name)
            edges.append({
                "source": pkg_id,
                "target": dep_id,
                "relation": "depends_on",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": str_path,
                "weight": 1.0,
            })

    # --- dev_dependencies ---
    dev_deps = data.get("dev_dependencies", {})
    if isinstance(dev_deps, dict):
        for dep_name, dep_spec in dev_deps.items():
            if dep_name in _SKIP_DEV_DEPS:
                continue
            # Check for sdk dependency
            if isinstance(dep_spec, dict) and "sdk" in dep_spec:
                continue
            dep_id = _make_id(dep_name)
            edges.append({
                "source": pkg_id,
                "target": dep_id,
                "relation": "dev_depends_on",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": str_path,
                "weight": 1.0,
            })

    return {"nodes": nodes, "edges": edges}
