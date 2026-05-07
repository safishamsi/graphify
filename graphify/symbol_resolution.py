"""Deterministic symbol indexing and conservative cross-file resolution helpers."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_EXCLUDED_FILE_TYPES = {"rationale", "doc_tag"}


@dataclass(frozen=True)
class ImportedSymbol:
    """A Python imported name that can be used as deterministic resolution evidence."""

    local_name: str
    imported_name: str
    module_stem: str
    source_file: str
    source_location: str


def normalise_callable_label(label: str) -> str:
    """Normalize a node label into the key used for call resolution."""

    return label.strip().strip("()").lstrip(".").lower()


def node_is_resolvable_symbol(node: dict[str, Any]) -> bool:
    """Return True when a node is suitable for deterministic symbol lookup."""

    if node.get("file_type") in _EXCLUDED_FILE_TYPES:
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


def existing_edge_pairs(edges: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """Return all existing source/target edge pairs."""

    pairs: set[tuple[str, str]] = set()
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source and target:
            pairs.add((str(source), str(target)))
    return pairs


def iter_raw_calls(per_file: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    """Return raw calls from all per-file extraction fragments."""

    calls: list[dict[str, Any]] = []
    for result in per_file:
        if not result:
            continue
        calls.extend(result.get("raw_calls", []))
    return calls


def _module_stem(module_name: str | None) -> str:
    """Return the final module component used to match Graphify source stems."""

    if not module_name:
        return ""
    return module_name.strip(".").split(".")[-1]


def parse_python_import_aliases(path: Path) -> dict[str, ImportedSymbol]:
    """Parse deterministic Python import aliases from one source file.

    Supported forms:
        from helper import transform
        from helper import transform as tx
        from .helper import transform

    The function deliberately does not resolve plain ``import helper`` member
    calls because current raw call records do not preserve the receiver name from
    ``helper.transform()``. That can be added later only after raw call facts are
    extended to include the receiver expression.
    """

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return {}

    aliases: dict[str, ImportedSymbol] = {}
    source_file = str(path)

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module_stem = _module_stem(node.module)
        if not module_stem:
            continue
        for alias in node.names:
            if alias.name == "*":
                continue
            local_name = alias.asname or alias.name
            aliases[local_name] = ImportedSymbol(
                local_name=local_name,
                imported_name=alias.name,
                module_stem=module_stem,
                source_file=source_file,
                source_location=f"L{getattr(node, 'lineno', 1)}",
            )

    return aliases


def _node_source_stem(node: dict[str, Any]) -> str:
    """Return the stem of a node's source file."""

    source_file = str(node.get("source_file", ""))
    if not source_file:
        return ""
    return Path(source_file).stem


def build_python_symbol_index(nodes: list[dict[str, Any]]) -> dict[tuple[str, str], list[str]]:
    """Build ``(module_stem, normalized_symbol_name) -> node_ids``.

    This index is stricter than the global label index. It uses both the module
    stem and the symbol label, which allows import evidence to resolve calls that
    global label uniqueness alone cannot safely resolve.
    """

    index: dict[tuple[str, str], list[str]] = {}
    for node in nodes:
        if not node_is_resolvable_symbol(node):
            continue
        source_stem = _node_source_stem(node)
        if not source_stem:
            continue
        label = normalise_callable_label(str(node.get("label", "")))
        if not label:
            continue
        node_id = node.get("id")
        if not node_id:
            continue
        index.setdefault((source_stem, label), []).append(str(node_id))
    return index


def find_unique_python_symbol(
    symbol_index: dict[tuple[str, str], list[str]],
    imported: ImportedSymbol,
) -> str | None:
    """Resolve one imported symbol to exactly one Graphify node id."""

    candidates = symbol_index.get((imported.module_stem, imported.imported_name.lower()), [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def resolve_python_import_guided_calls(
    per_file: list[dict[str, Any] | None],
    paths: list[Path],
    all_nodes: list[dict[str, Any]],
    all_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve raw Python calls using explicit import evidence.

    Only ``from module import symbol [as alias]`` forms are handled. Member calls
    remain skipped because the current raw call fact does not carry receiver
    information.
    """

    symbol_index = build_python_symbol_index(all_nodes)
    known_pairs = existing_edge_pairs(all_edges)
    result_by_file: dict[str, dict[str, Any]] = {
        str(path): per_file[index] or {"nodes": [], "edges": []}
        for index, path in enumerate(paths)
        if path.suffix == ".py"
    }
    resolved_edges: list[dict[str, Any]] = []

    for path in paths:
        if path.suffix != ".py":
            continue
        source_file = str(path)
        aliases = parse_python_import_aliases(path)
        if not aliases:
            continue
        file_result = result_by_file.get(source_file, {"raw_calls": []})
        for raw_call in file_result.get("raw_calls", []):
            if raw_call.get("is_member_call"):
                continue
            callee = str(raw_call.get("callee", "")).strip()
            if not callee:
                continue
            imported = aliases.get(callee)
            if imported is None:
                continue
            target = find_unique_python_symbol(symbol_index, imported)
            if target is None:
                continue
            caller = str(raw_call.get("caller_nid", ""))
            if not caller or caller == target:
                continue
            pair = (caller, target)
            if pair in known_pairs:
                continue
            known_pairs.add(pair)
            resolved_edges.append(
                {
                    "source": caller,
                    "target": target,
                    "relation": "calls",
                    "context": "import_guided_call",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": raw_call.get("source_file", source_file),
                    "source_location": raw_call.get("source_location") or imported.source_location,
                    "weight": 1.0,
                    "metadata": {
                        "resolver": "python_import_guided",
                        "local_name": imported.local_name,
                        "imported_name": imported.imported_name,
                        "module_stem": imported.module_stem,
                        "import_source_location": imported.source_location,
                    },
                }
            )

    return resolved_edges


def resolve_cross_file_raw_calls(
    per_file: list[dict[str, Any] | None],
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
        pair = (caller, target)
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
