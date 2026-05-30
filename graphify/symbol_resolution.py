"""Deterministic symbol indexing and conservative cross-file resolution helpers."""

from __future__ import annotations

import ast
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from typing import Any

from graphify.security import sanitize_metadata



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


def _bash_make_id(*parts: str) -> str:
    """Exact copy of extract._make_id — kept here to avoid an import cycle."""
    combined = "_".join(p.strip("_.") for p in parts if p)
    combined = unicodedata.normalize("NFKC", combined)
    cleaned = re.sub(r"[^\w]+", "_", combined, flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_").casefold()


def _file_node_id_for_path(path: Path, root: Path) -> str:
    # Resolve both sides so callers that pass relative or non-canonical roots
    # get the same canonical relative path that extract()'s id_remap produces.
    # _bash_make_id is an exact copy of extract._make_id, so IDs match.
    try:
        return _bash_make_id(str(path.resolve().relative_to(root.resolve())))
    except ValueError:
        return _bash_make_id(str(path))  # path outside root: hash absolute path as fallback


def resolve_bash_source_edges(
    per_file: Sequence[dict | None],
    paths: Sequence[Path],
    root: Path,
    existing_edges: list[dict] | None = None,
) -> list[dict]:
    """Resolve Bash source/import edges and source-backed function calls.

    Defensive against malformed extraction fragments: non-dict ``per_file``
    entries, missing ``bash_sources``/``raw_calls`` keys, non-dict items in
    those lists, and missing/empty ``id`` / ``target_path`` / ``caller_nid``
    fields all yield silent skips rather than ``KeyError``.

    ``bash_sources[].target_path`` contract (Graphify static-analysis policy):
        - Absolute paths: resolved as-is.
        - Relative paths: resolved against the *source file's* directory
          (i.e. ``Path(path).parent / target_path``).
          NOTE: this is a deterministic static-analysis policy chosen by
          Graphify, NOT bash runtime semantics. At runtime, ``source ./X``
          is resolved against the shell's current working directory. We
          prefer source-file-relative because static analysis cannot know
          the future CWD; resolving against the file being analyzed gives
          deterministic, reproducible edges across runs.
        - Inputs of type ``str`` and ``pathlib.Path`` are processed.
          Anything else is silently skipped.
    """
    path_by_index = [Path(p).resolve() for p in paths]
    file_nid_by_path = {p: _file_node_id_for_path(p, root) for p in path_by_index}  # resolved paths only

    functions_by_file: dict[str, dict[str, str]] = {}
    for result, path in zip(per_file, path_by_index):
        if not isinstance(result, dict):
            continue
        file_nid = file_nid_by_path[path]
        nodes = result.get("nodes", [])
        if not isinstance(nodes, list):
            continue
        for node in nodes:
            if not isinstance(node, dict):
                continue
            metadata = node.get("metadata", {})
            if not isinstance(metadata, dict):
                continue
            if metadata.get("kind") != "bash_function":
                continue
            name = str(node.get("label", "")).removesuffix("()").strip()
            node_id = node.get("id")
            if not name or not node_id:
                continue
            functions_by_file.setdefault(file_nid, {})[name] = str(node_id)

    sourced_files: dict[str, set[str]] = {}
    resolved_edges: list[dict] = []
    existing = existing_edge_pairs(existing_edges or [])

    for result, path in zip(per_file, path_by_index):
        if not isinstance(result, dict):
            continue
        src_file_nid = file_nid_by_path[path]
        bash_sources = result.get("bash_sources", [])
        if not isinstance(bash_sources, list):
            continue
        for source in bash_sources:
            if not isinstance(source, dict):
                continue
            raw_target = source.get("target_path")
            if not isinstance(raw_target, (str, Path)) or not str(raw_target).strip():
                continue
            # Relative paths resolve against the source file's directory —
            # Graphify static-analysis policy (NOT bash runtime semantics;
            # at runtime `source ./X` is CWD-relative, but static analysis
            # can't know the future CWD, so we resolve relative to the
            # file being analyzed for deterministic, reproducible edges).
            candidate = Path(raw_target)
            if not candidate.is_absolute():
                candidate = path.parent / candidate
            try:
                target_path = candidate.resolve()
            except (OSError, RuntimeError):
                continue
            target_file_nid = file_nid_by_path.get(target_path)
            if target_file_nid is None:
                continue
            sourced_files.setdefault(src_file_nid, set()).add(target_file_nid)
            key = (src_file_nid, target_file_nid, "imports_from")
            if key in existing:
                continue
            existing.add(key)
            resolved_edges.append(
                {
                    "source": src_file_nid,
                    "target": target_file_nid,
                    "relation": "imports_from",
                    "context": "import",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": source.get("source_file", str(path)),
                    "source_location": source.get("source_location", ""),
                    "weight": 1.0,
                }
            )

    for result, path in zip(per_file, path_by_index):
        if not isinstance(result, dict):
            continue
        caller_file_nid = file_nid_by_path[path]
        imported_file_ids = sourced_files.get(caller_file_nid, set())
        if not imported_file_ids:
            continue
        raw_calls = result.get("raw_calls", [])
        if not isinstance(raw_calls, list):
            continue
        for raw_call in raw_calls:
            if not isinstance(raw_call, dict):
                continue
            if raw_call.get("language") != "bash":
                continue
            callee = raw_call.get("callee")
            caller_nid = raw_call.get("caller_nid")
            # callee must be a non-empty string — anything else (list, dict,
            # int, None, …) is silently skipped to avoid TypeError on the
            # `in functions_by_file[...]` membership check below.
            if not isinstance(callee, str) or not callee or not caller_nid:
                continue
            matches = [
                functions_by_file[file_nid][callee]
                for file_nid in imported_file_ids
                if callee in functions_by_file.get(file_nid, {})
            ]
            if len(matches) != 1:
                continue
            target = matches[0]
            key = (str(caller_nid), target, "calls")
            if key in existing:
                continue
            existing.add(key)
            resolved_edges.append(
                {
                    "source": str(caller_nid),
                    "target": target,
                    "relation": "calls",
                    "context": "call",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": raw_call.get("source_file", str(path)),
                    "source_location": raw_call.get("source_location", ""),
                    "weight": 1.0,
                }
            )

    return resolved_edges
