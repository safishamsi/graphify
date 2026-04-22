"""Extract localization message keys from .arb files."""
from __future__ import annotations

import json
import re
from pathlib import Path


def _make_id(*parts: str) -> str:
    combined = "_".join(p.strip("_.") for p in parts if p)
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", combined)
    return cleaned.strip("_").lower()


def extract_arb(path: Path) -> dict:
    """Parse an .arb file and return nodes/edges for localization messages."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    if not isinstance(data, dict):
        return {"nodes": [], "edges": [], "error": "invalid .arb format"}

    nodes: list[dict] = []
    edges: list[dict] = []
    str_path = str(path)

    stem = path.stem  # e.g. "app_en"
    file_id = _make_id(stem)

    # Extract locale from @@locale key, or from filename convention (e.g. app_en -> en)
    locale = data.get("@@locale")
    if not locale:
        # Try to infer from filename: app_en.arb -> en
        parts = stem.rsplit("_", 1)
        locale = parts[-1] if len(parts) > 1 else None

    file_node: dict = {
        "id": file_id,
        "label": stem,
        "file_type": "config",
        "source_file": str_path,
        "dart_kind": "localization",
    }
    if locale:
        file_node["locale"] = locale
    nodes.append(file_node)

    # Extract message keys (skip keys starting with @ or @@)
    for key in data:
        if key.startswith("@"):
            continue
        msg_id = _make_id(stem, key)
        nodes.append({
            "id": msg_id,
            "label": key,
            "file_type": "config",
            "source_file": str_path,
            "dart_kind": "message_key",
        })
        edges.append({
            "source": file_id,
            "target": msg_id,
            "relation": "defines_message",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": str_path,
            "weight": 1.0,
        })

    return {"nodes": nodes, "edges": edges}
