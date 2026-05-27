from __future__ import annotations
from collections.abc import Sequence
from typing import Any
def normalise_callable_label(label: str) -> str:
    """Normalize a node label into the key used for call resolution."""

    return label.strip().strip("()").lstrip(".").lower()


def node_is_resolvable_symbol(node: dict[str, Any]) -> bool:
    """Return True when a node is suitable for deterministic symbol lookup.

    Requires ``file_type == "code"`` as the positive gate — only code-class
    nodes participate as call targets. ``_EXCLUDED_FILE_TYPES`` is kept as
    defensive-in-depth against legacy data, but the primary guard is the
    positive code check. Document/paper/image/concept nodes (e.g. a Markdown
    heading whose label happens to match a code identifier) MUST NOT become
    callees for a raw code call.
    """

    if node.get("file_type") != "code":
        return False
    label = str(node.get("label", "")).strip()
    if not label:
        return False
    if label.endswith((".py", ".js", ".ts", ".tsx", ".java", ".go", ".rs")):
        return False
    return bool(normalise_callable_label(label))


def build_label_index(nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Build label -> node id list for conservative cross-file resolution."""

    index: dict[str, list[str]] = {}
    for node in nodes:
        if not node_is_resolvable_symbol(node):
            continue
        node_id = node.get("id")
        if not node_id:
            continue
        key = normalise_callable_label(str(node.get("label", "")))
        if not key:
            continue
        index.setdefault(key, []).append(str(node_id))
    return index


def existing_edge_pairs(edges: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    """Return all existing source/target/relation edge triples.

    Includes relation so that a prior "contains" or "method" edge does not
    suppress a semantically distinct "calls" edge between the same endpoints (#F5).
    """

    triples: set[tuple[str, str, str]] = set()
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        relation = edge.get("relation", "")
        if source and target:
            triples.add((str(source), str(target), str(relation)))
    return triples


def iter_raw_calls(per_file: Sequence[object]) -> list[dict[str, Any]]:
    """Return raw calls from all per-file extraction fragments.

    Parameter is ``Sequence[object]`` (not ``Sequence[dict[str, Any] | None]``)
    because external extraction output may contain arbitrary deserialized
    JSON. Defensive against malformed fragments: non-dict per-file entries
    are skipped, non-list ``raw_calls`` are treated as empty, and non-dict
    items inside the list are silently dropped. The downstream resolvers
    assume every returned item is a dict and they expect this guarantee.
    """

    calls: list[dict[str, Any]] = []
    for result in per_file:
        if not isinstance(result, dict):
            continue
        raw_calls = result.get("raw_calls", [])
        if not isinstance(raw_calls, list):
            continue
        for raw_call in raw_calls:
            if isinstance(raw_call, dict):
                calls.append(raw_call)
    return calls

def resolve_cross_file_raw_calls(
    per_file: Sequence[dict[str, Any] | None],
    all_nodes: list[dict[str, Any]],
    all_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve unqualified raw calls conservatively after all files are known.

    This intentionally preserves Graphify's existing behavior:
    - member calls are skipped;
    - ambiguous labels are skipped;
    - only a single unique candidate is emitted;
    - emitted edges are INFERRED because the raw call alone is not import proof.
    """

    label_index = build_label_index(all_nodes)
    known_pairs = existing_edge_pairs(all_edges)
    resolved: list[dict[str, Any]] = []

    for raw_call in iter_raw_calls(per_file):
        callee = str(raw_call.get("callee", "")).strip()
        if not callee:
            continue
        if raw_call.get("is_member_call"):
            continue
        candidates = label_index.get(callee.lower(), [])
        if len(candidates) != 1:
            continue
        target = candidates[0]
        caller = str(raw_call.get("caller_nid", ""))
        if not caller:
            continue
        if target == caller:
            continue
        pair = (caller, target, "calls")
        if pair in known_pairs:
            continue
        known_pairs.add(pair)
        resolved.append(
            {
                "source": caller,
                "target": target,
                "relation": "calls",
                "context": "call",
                "confidence": "INFERRED",
                "confidence_score": 0.8,
                "source_file": raw_call.get("source_file", ""),
                "source_location": raw_call.get("source_location"),
                "weight": 1.0,
            }
        )

    return resolved

