# validate extraction JSON against the graphify schema before graph assembly
from __future__ import annotations

VALID_FILE_TYPES = {"code", "document", "paper", "image"}
VALID_CONFIDENCES = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}
REQUIRED_NODE_FIELDS = {"id", "label", "file_type", "source_file"}
REQUIRED_EDGE_FIELDS = {"source", "target", "relation", "confidence", "source_file"}

# Sentinel value for `source_file` meaning "this symbol lives outside the parsed
# corpus" (e.g. a framework base class referenced via inheritance but never
# defined locally). See graphify/extract.py module docstring for the full
# contract. The validator accepts this sentinel as a valid source_file so the
# real LLM-omission bug (empty / None) stays visible.
EXTERNAL_SENTINEL = "<external>"


def _is_valid_source_file(value: object) -> bool:
    """A valid source_file is a non-empty string (a path or the <external> sentinel)."""
    return isinstance(value, str) and value != ""


def validate_extraction(data: dict) -> list[str]:
    """
    Validate an extraction JSON dict against the graphify schema.
    Returns a list of error strings - empty list means valid.
    """
    if not isinstance(data, dict):
        return ["Extraction must be a JSON object"]

    errors: list[str] = []

    # Nodes
    if "nodes" not in data:
        errors.append("Missing required key 'nodes'")
    elif not isinstance(data["nodes"], list):
        errors.append("'nodes' must be a list")
    else:
        for i, node in enumerate(data["nodes"]):
            if not isinstance(node, dict):
                errors.append(f"Node {i} must be an object")
                continue
            for field in REQUIRED_NODE_FIELDS:
                if field not in node:
                    errors.append(f"Node {i} (id={node.get('id', '?')!r}) missing required field '{field}'")
                elif field == "source_file" and not _is_valid_source_file(node[field]):
                    # Empty string or None still counts as missing — distinguishes
                    # "outside the corpus" (use the "<external>" sentinel) from
                    # "extractor bug / LLM forgot the field".
                    errors.append(
                        f"Node {i} (id={node.get('id', '?')!r}) missing required field "
                        f"'source_file' (got {node[field]!r}; use '{EXTERNAL_SENTINEL}' "
                        f"for cross-corpus symbols)"
                    )
            if "file_type" in node and node["file_type"] not in VALID_FILE_TYPES:
                errors.append(
                    f"Node {i} (id={node.get('id', '?')!r}) has invalid file_type "
                    f"'{node['file_type']}' - must be one of {sorted(VALID_FILE_TYPES)}"
                )

    # Edges
    if "edges" not in data:
        errors.append("Missing required key 'edges'")
    elif not isinstance(data["edges"], list):
        errors.append("'edges' must be a list")
    else:
        node_ids = {n["id"] for n in data.get("nodes", []) if isinstance(n, dict) and "id" in n}
        for i, edge in enumerate(data["edges"]):
            if not isinstance(edge, dict):
                errors.append(f"Edge {i} must be an object")
                continue
            for field in REQUIRED_EDGE_FIELDS:
                if field not in edge:
                    errors.append(f"Edge {i} missing required field '{field}'")
                elif field == "source_file" and not _is_valid_source_file(edge[field]):
                    errors.append(
                        f"Edge {i} missing required field 'source_file' "
                        f"(got {edge[field]!r}; use '{EXTERNAL_SENTINEL}' "
                        f"for cross-corpus symbols)"
                    )
            if "confidence" in edge and edge["confidence"] not in VALID_CONFIDENCES:
                errors.append(
                    f"Edge {i} has invalid confidence '{edge['confidence']}' "
                    f"- must be one of {sorted(VALID_CONFIDENCES)}"
                )
            if "source" in edge and node_ids and edge["source"] not in node_ids:
                errors.append(f"Edge {i} source '{edge['source']}' does not match any node id")
            if "target" in edge and node_ids and edge["target"] not in node_ids:
                errors.append(f"Edge {i} target '{edge['target']}' does not match any node id")

    return errors


def assert_valid(data: dict) -> None:
    """Raise ValueError with all errors if extraction is invalid."""
    errors = validate_extraction(data)
    if errors:
        msg = f"Extraction JSON has {len(errors)} error(s):\n" + "\n".join(f"  • {e}" for e in errors)
        raise ValueError(msg)
