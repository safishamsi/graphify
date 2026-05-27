from __future__ import annotations
import ast
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from typing import Any
from graphify.security import sanitize_metadata
from .core import node_is_resolvable_symbol, normalise_callable_label, existing_edge_pairs
@dataclass(frozen=True)
class ImportedSymbol:
    """A Python imported name that can be used as deterministic resolution evidence."""

    local_name: str
    imported_name: str
    module_stem: str
    source_file: str
    source_location: str


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

    # Only top-level `from ... import ...` statements count as file-wide
    # evidence. Nested/function-local imports do NOT — they're only valid
    # inside their lexical scope, and our raw-call records don't currently
    # carry enough scope info to match the import site safely. Walking
    # ast.walk(tree) would incorrectly justify calls in other scopes.
    for node in tree.body:
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
    per_file: Sequence[object],
    paths: Sequence[Path],
    all_nodes: list[dict[str, Any]],
    all_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve raw Python calls using explicit import evidence.

    Only ``from module import symbol [as alias]`` forms are handled. Member calls
    remain skipped because the current raw call fact does not carry receiver
    information.

    Parameter ``per_file`` is ``Sequence[object]`` because external extraction
    output may contain arbitrary deserialized JSON. Non-dict slots are
    treated as empty fragments, and indices past ``len(per_file)`` are also
    treated as empty (paths longer than per_file is tolerated).
    """

    symbol_index = build_python_symbol_index(all_nodes)
    known_pairs = existing_edge_pairs(all_edges)
    # Build result_by_file defensively:
    #   - skip indices past the end of per_file (paths shorter than per_file
    #     also OK; the zip-like behavior is what callers expect)
    #   - non-dict per_file slots fall back to the empty fragment so the
    #     downstream `.get("raw_calls", [])` lookup never raises
    result_by_file: dict[str, dict[str, Any]] = {}
    for index, path in enumerate(paths):
        if path.suffix != ".py":
            continue
        slot: Any = per_file[index] if index < len(per_file) else None
        result_by_file[str(path)] = slot if isinstance(slot, dict) else {"nodes": [], "edges": []}
    resolved_edges: list[dict[str, Any]] = []

    for path in paths:
        if path.suffix != ".py":
            continue
        source_file = str(path)
        aliases = parse_python_import_aliases(path)
        if not aliases:
            continue
        file_result = result_by_file.get(source_file, {"raw_calls": []})
        raw_calls = file_result.get("raw_calls", [])
        if not isinstance(raw_calls, list):
            continue
        for raw_call in raw_calls:
            if not isinstance(raw_call, dict):
                continue
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
            pair = (caller, target, "calls")
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
                    "metadata": sanitize_metadata({
                        "resolver": "python_import_guided",
                        "local_name": imported.local_name,
                        "imported_name": imported.imported_name,
                        "module_stem": imported.module_stem,
                        "import_source_location": imported.source_location,
                    }),
                }
            )

    return resolved_edges

