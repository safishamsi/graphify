from __future__ import annotations
import re
import unicodedata
from pathlib import Path
from collections.abc import Sequence
from .core import existing_edge_pairs
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
