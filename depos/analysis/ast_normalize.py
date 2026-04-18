"""Normalize raw per-file AST JSON into graphify-valid extractions.

The dataset under ``dataset/`` carries low-level AST nodes with useful
spans and labels, but it does not match graphify's extraction contract
and it is too leaf-heavy for the depOS intelligence pipeline.

This module promotes that raw structure into a smaller, richer entity
graph:

- file entities
- function / class entities
- import entities
- semantic-ish edges such as ``CONTAINS``, ``IMPORTS``, and ``CALLS``

The resulting extraction dict can be passed to
``graphify.build.build_from_json`` directly.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


_FUNCTION_KINDS = {
    "function_definition",
    "function_declaration",
    "method_definition",
    "arrow_function",
    "generator_function_definition",
}
_CLASS_KINDS = {"class_definition", "class_declaration"}
_IMPORT_KINDS = {"import_statement", "import_from_statement"}
_CALL_KINDS = {"call", "call_expression"}
_IDENTIFIER_KINDS = {"identifier", "property_identifier", "type_identifier"}
_ENTITY_KINDS = _FUNCTION_KINDS | _CLASS_KINDS | _IMPORT_KINDS | _CALL_KINDS


@dataclass(frozen=True)
class ParsedAstId:
    commit_sha: str
    source_file: str
    start_byte: int
    end_byte: int
    kind: str


@dataclass
class RawAstFile:
    source_file: str
    commit_sha: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    dataset_path: Path


@dataclass
class EntityNode:
    node_id: str
    raw_id: str
    name: str
    entity_kind: str
    source_file: str
    start_line: int
    end_line: int
    label: str
    embedded_text: str


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower() or "anon"


def _parse_ast_id(node_id: str) -> Optional[ParsedAstId]:
    match = re.match(r"^ast:(?P<sha>[^:]+):(?P<path>.+):(?P<start>\d+):(?P<end>\d+):(?P<kind>[^:]+)$", node_id)
    if not match:
        return None
    return ParsedAstId(
        commit_sha=match.group("sha"),
        source_file=match.group("path"),
        start_byte=int(match.group("start")),
        end_byte=int(match.group("end")),
        kind=match.group("kind"),
    )


def _span_start_line(node: dict[str, Any]) -> int:
    return int((((node.get("span") or {}).get("start") or {}).get("line")) or 0)


def _span_end_line(node: dict[str, Any]) -> int:
    return int((((node.get("span") or {}).get("end") or {}).get("line")) or 0)


def _source_excerpt(source_text: str, start_line: int, end_line: int, *, max_lines: int = 80) -> str:
    if not source_text:
        return ""
    lines = source_text.splitlines()
    if start_line > 0 and end_line >= start_line:
        chunk = lines[max(0, start_line - 1) : min(len(lines), end_line)]
    else:
        chunk = lines[:max_lines]
    if len(chunk) > max_lines:
        chunk = chunk[:max_lines]
    return "\n".join(chunk).strip()


def _load_raw_ast_file(path: Path) -> RawAstFile:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data.get("parts"), list) and data.get("relative_path"):
        merged_nodes: list[dict[str, Any]] = []
        merged_edges: list[dict[str, Any]] = []
        commit_sha = str(data.get("commit_sha") or "")
        for part_name in data.get("parts", []):
            part_path = path.parent / str(part_name)
            part = json.loads(part_path.read_text(encoding="utf-8"))
            merged_nodes.extend(list(part.get("nodes", [])))
            merged_edges.extend(list(part.get("edges", [])))
            commit_sha = commit_sha or str(part.get("commit_sha") or "")
        data = {
            "commit_sha": commit_sha,
            "nodes": merged_nodes,
            "edges": merged_edges,
            "relative_path": data.get("relative_path"),
        }
    commit_sha = str(data.get("commit_sha") or "")
    source_file = str(data.get("relative_path") or "")
    for node in data.get("nodes", []):
        parsed = _parse_ast_id(str(node.get("id") or ""))
        if parsed is not None:
            commit_sha = commit_sha or parsed.commit_sha
            source_file = parsed.source_file
            break
    if not source_file:
        raise ValueError(f"Could not infer source file from AST ids in {path}")
    return RawAstFile(
        source_file=source_file,
        commit_sha=commit_sha,
        nodes=list(data.get("nodes", [])),
        edges=list(data.get("edges", [])),
        dataset_path=path,
    )


def _descendants_of(root_id: str, child_map: dict[str, list[str]]) -> list[str]:
    out: list[str] = []
    stack = list(child_map.get(root_id, []))
    seen: set[str] = set()
    while stack:
        nid = stack.pop()
        if nid in seen:
            continue
        seen.add(nid)
        out.append(nid)
        stack.extend(child_map.get(nid, []))
    return out


def _first_named_descendant(
    root_id: str,
    node_by_id: dict[str, dict[str, Any]],
    child_map: dict[str, list[str]],
) -> str:
    for nid in _descendants_of(root_id, child_map):
        child = node_by_id.get(nid) or {}
        if child.get("kind") in _IDENTIFIER_KINDS:
            label = str(child.get("label") or "").strip()
            if label:
                return label
    return ""


def _fallback_name_from_label(label: str, kind: str, line: int) -> str:
    text = " ".join(str(label or "").split())
    patterns = [
        r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\bconst\s+([A-Za-z_][A-Za-z0-9_]*)\s*=",
        r"\blet\s+([A-Za-z_][A-Za-z0-9_]*)\s*=",
        r"\bvar\s+([A-Za-z_][A-Za-z0-9_]*)\s*=",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    if "(" in text:
        head = text.split("(", 1)[0].strip()
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", head)
        if tokens:
            return tokens[-1]
    return f"{kind}_l{line or 0}"


def _entity_name_for(
    raw_id: str,
    node: dict[str, Any],
    *,
    node_by_id: dict[str, dict[str, Any]],
    child_map: dict[str, list[str]],
    parent_map: dict[str, list[str]],
) -> str:
    direct_name = _first_named_descendant(raw_id, node_by_id, {raw_id: child_map.get(raw_id, [])})
    if direct_name:
        return direct_name
    for parent_id in parent_map.get(raw_id, []):
        parent = node_by_id.get(parent_id) or {}
        if str(parent.get("kind") or "") in {"variable_declarator", "assignment", "assignment_expression"}:
            parent_name = _first_named_descendant(parent_id, node_by_id, child_map)
            if parent_name:
                return parent_name
    return _fallback_name_from_label(str(node.get("label") or ""), str(node.get("kind") or "entity"), _span_start_line(node))


def _import_target_from_label(label: str) -> str:
    text = " ".join(str(label or "").split())
    py_from = re.search(r"^from\s+([A-Za-z0-9_\.]+)\s+import\b", text)
    if py_from:
        return py_from.group(1)
    py_import = re.search(r"^import\s+([A-Za-z0-9_\.]+)", text)
    if py_import:
        return py_import.group(1)
    js_import = re.search(r"""from\s+["']([^"']+)["']""", text)
    if js_import:
        return js_import.group(1)
    return text[:120]


def _call_target_from_label(label: str) -> str:
    text = " ".join(str(label or "").split())
    head = text.split("(", 1)[0].strip()
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", head)
    if not tokens:
        return ""
    return tokens[-1]


def _candidate_suffixes(module_path: str, *, source_file: str) -> list[str]:
    module = module_path.strip()
    out: list[str] = []
    if not module:
        return out
    if module.startswith("."):
        base = Path(source_file).parent
        rel = module
        while rel.startswith("../"):
            base = base.parent
            rel = rel[3:]
        rel = rel.removeprefix("./").removeprefix(".")
        parts = [p for p in rel.split("/") if p]
        base_path = base.joinpath(*parts) if parts else base
        for ext in (".ts", ".tsx", ".js", ".jsx", ".py"):
            out.append(base_path.with_suffix(ext).as_posix())
            out.append(base_path.joinpath(f"index{ext}").as_posix())
    elif module.startswith("@/"):
        rel = module[2:]
        for prefix in ("frontend/src", "src", ""):
            stem = f"{prefix}/{rel}".strip("/")
            for ext in (".ts", ".tsx", ".js", ".jsx"):
                out.append(f"{stem}{ext}")
                out.append(f"{stem}/index{ext}")
    elif "." in module and "/" not in module:
        stem = module.replace(".", "/")
        for ext in (".py", ".pyi"):
            out.append(f"{stem}{ext}")
    else:
        for ext in (".ts", ".tsx", ".js", ".jsx", ".py"):
            out.append(f"{module}{ext}")
            out.append(f"{module}/index{ext}")
    deduped: list[str] = []
    seen: set[str] = set()
    for item in out:
        norm = Path(item).as_posix()
        if norm not in seen:
            seen.add(norm)
            deduped.append(norm)
    return deduped


def _resolve_import_target(module_path: str, *, source_file: str, known_files: set[str]) -> str:
    suffixes = _candidate_suffixes(module_path, source_file=source_file)
    if not suffixes:
        return ""
    exact = [cand for cand in suffixes if cand in known_files]
    if exact:
        return sorted(exact, key=len)[0]
    matches: list[str] = []
    for suffix in suffixes:
        suffix_norm = suffix if suffix.startswith("/") else f"/{suffix}"
        for known in known_files:
            if known.endswith(suffix_norm):
                matches.append(known)
    if not matches:
        return ""
    return sorted(set(matches), key=len)[0]


def _edge_key(source: str, target: str, relation: str) -> str:
    return f"{source}|{target}|{relation}"


def _read_source_text(repo_root: Optional[Path], source_file: str) -> str:
    if repo_root is None:
        return ""
    path = repo_root / source_file
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def normalize_raw_ast_files(
    files: list[RawAstFile],
    *,
    repo_root: Optional[Path] = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve() if repo_root is not None else None
    known_files = {Path(f.source_file).as_posix() for f in files}
    extraction_nodes: list[dict[str, Any]] = []
    extraction_edges: list[dict[str, Any]] = []
    added_nodes: set[str] = set()
    added_edges: set[str] = set()
    entities_by_file: dict[str, list[EntityNode]] = defaultdict(list)

    def add_node(payload: dict[str, Any]) -> None:
        node_id = str(payload["id"])
        if node_id in added_nodes:
            return
        added_nodes.add(node_id)
        extraction_nodes.append(payload)

    def add_edge(payload: dict[str, Any]) -> None:
        key = _edge_key(str(payload["source"]), str(payload["target"]), str(payload["relation"]))
        if key in added_edges:
            return
        added_edges.add(key)
        extraction_edges.append(payload)

    file_entity_ids: dict[str, str] = {}
    entity_by_raw_id: dict[str, EntityNode] = {}
    source_cache: dict[str, str] = {}

    for raw in files:
        node_by_id = {str(node.get("id")): node for node in raw.nodes if node.get("id")}
        child_map: dict[str, list[str]] = defaultdict(list)
        parent_map: dict[str, list[str]] = defaultdict(list)
        for edge in raw.edges:
            if str(edge.get("type") or edge.get("role") or "") != "child":
                continue
            source_id = str(edge.get("source_id") or "")
            target_id = str(edge.get("target_id") or "")
            if source_id and target_id:
                child_map[source_id].append(target_id)
                parent_map[target_id].append(source_id)

        source_text = _read_source_text(repo_root, raw.source_file)
        source_cache[raw.source_file] = source_text
        max_line = max((_span_end_line(node) for node in raw.nodes), default=1)
        file_entity_id = f"entity:file:{raw.source_file}"
        file_entity_ids[raw.source_file] = file_entity_id
        add_node(
            {
                "id": file_entity_id,
                "label": Path(raw.source_file).name,
                "file_type": "code",
                "source_file": raw.source_file,
                "source_location": "L1",
                "start_line": 1,
                "end_line": max_line,
                "synthetic_entity": True,
                "entity_kind": "file",
                "kind": "file",
                "embedded_text": _source_excerpt(source_text, 1, max_line),
            }
        )

        import_targets: dict[str, str] = {}

        for node in raw.nodes:
            raw_id = str(node.get("id") or "")
            kind = str(node.get("kind") or "")
            if kind not in _ENTITY_KINDS:
                continue
            start_line = _span_start_line(node)
            end_line = _span_end_line(node)
            label = " ".join(str(node.get("label") or "").split())
            embedded_text = _source_excerpt(source_text, start_line, end_line) or label

            if kind in _FUNCTION_KINDS | _CLASS_KINDS:
                name = _entity_name_for(
                    raw_id,
                    node,
                    node_by_id=node_by_id,
                    child_map=child_map,
                    parent_map=parent_map,
                )
                entity_kind = "class" if kind in _CLASS_KINDS else "function"
                entity_id = f"entity:{entity_kind}:{raw.source_file}:{_slug(name)}:{start_line or 0}"
                entity = EntityNode(
                    node_id=entity_id,
                    raw_id=raw_id,
                    name=name,
                    entity_kind=entity_kind,
                    source_file=raw.source_file,
                    start_line=start_line,
                    end_line=end_line,
                    label=f"{name}{'()' if entity_kind == 'function' else ''}",
                    embedded_text=embedded_text,
                )
                entity_by_raw_id[raw_id] = entity
                entities_by_file[raw.source_file].append(entity)
                add_node(
                    {
                        "id": entity.node_id,
                        "label": entity.label,
                        "file_type": "code",
                        "source_file": raw.source_file,
                        "source_location": f"L{start_line or 1}",
                        "start_line": start_line,
                        "end_line": end_line,
                        "synthetic_entity": True,
                        "entity_kind": entity.entity_kind,
                        "kind": entity.entity_kind,
                        "ast_kind": kind,
                        "ast_node_id": raw_id,
                        "embedded_text": entity.embedded_text,
                    }
                )
                add_edge(
                    {
                        "source": file_entity_id,
                        "target": entity.node_id,
                        "relation": "CONTAINS",
                        "confidence": "EXTRACTED",
                        "source_file": raw.source_file,
                        "weight": 1.0,
                    }
                )
            elif kind in _IMPORT_KINDS:
                import_target = _import_target_from_label(label)
                entity_id = f"entity:import:{raw.source_file}:{_slug(import_target)}:{start_line or 0}"
                add_node(
                    {
                        "id": entity_id,
                        "label": f"import {import_target}",
                        "file_type": "code",
                        "source_file": raw.source_file,
                        "source_location": f"L{start_line or 1}",
                        "start_line": start_line,
                        "end_line": end_line,
                        "synthetic_entity": True,
                        "entity_kind": "import",
                        "kind": "import",
                        "ast_kind": kind,
                        "ast_node_id": raw_id,
                        "import_target": import_target,
                        "embedded_text": embedded_text,
                    }
                )
                add_edge(
                    {
                        "source": file_entity_id,
                        "target": entity_id,
                        "relation": "CONTAINS",
                        "confidence": "EXTRACTED",
                        "source_file": raw.source_file,
                        "weight": 1.0,
                    }
                )
                import_targets[entity_id] = import_target
            elif kind in _CALL_KINDS:
                callee_name = _call_target_from_label(label)
                if not callee_name:
                    continue
                continue

        for import_entity_id, import_target in import_targets.items():
            resolved_target = _resolve_import_target(import_target, source_file=raw.source_file, known_files=known_files)
            if not resolved_target:
                continue
            target_file_id = file_entity_ids.get(resolved_target) or f"entity:file:{resolved_target}"
            add_node(
                {
                    "id": target_file_id,
                    "label": Path(resolved_target).name,
                    "file_type": "code",
                    "source_file": resolved_target,
                    "source_location": "L1",
                    "start_line": 1,
                    "end_line": 0,
                    "synthetic_entity": True,
                    "entity_kind": "file",
                    "kind": "file",
                    "embedded_text": _source_excerpt(source_cache.get(resolved_target, ""), 1, 80),
                }
            )
            file_entity_ids.setdefault(resolved_target, target_file_id)
            add_edge(
                {
                    "source": file_entity_id,
                    "target": target_file_id,
                    "relation": "IMPORTS",
                    "confidence": "EXTRACTED",
                    "source_file": raw.source_file,
                    "weight": 1.0,
                }
            )

    symbols_by_name: dict[str, list[EntityNode]] = defaultdict(list)
    symbols_by_file_and_name: dict[tuple[str, str], list[EntityNode]] = defaultdict(list)
    for entities in entities_by_file.values():
        for entity in entities:
            if entity.entity_kind not in {"function", "class"}:
                continue
            name_key = _slug(entity.name)
            symbols_by_name[name_key].append(entity)
            symbols_by_file_and_name[(entity.source_file, name_key)].append(entity)

    for raw in files:
        node_by_id = {str(node.get("id")): node for node in raw.nodes if node.get("id")}
        child_map: dict[str, list[str]] = defaultdict(list)
        parent_map: dict[str, list[str]] = defaultdict(list)
        for edge in raw.edges:
            if str(edge.get("type") or edge.get("role") or "") != "child":
                continue
            source_id = str(edge.get("source_id") or "")
            target_id = str(edge.get("target_id") or "")
            if source_id and target_id:
                child_map[source_id].append(target_id)
                parent_map[target_id].append(source_id)

        source_text = source_cache.get(raw.source_file, "")
        entity_by_raw_local = {
            entity.raw_id: entity
            for entity in entities_by_file.get(raw.source_file, [])
        }
        for node in raw.nodes:
            raw_id = str(node.get("id") or "")
            if str(node.get("kind") or "") not in _CALL_KINDS:
                continue
            callee_name = _call_target_from_label(str(node.get("label") or ""))
            if not callee_name:
                continue
            parent_entity: Optional[EntityNode] = None
            for parent_id in parent_map.get(raw_id, []):
                current = parent_id
                while current:
                    if current in entity_by_raw_local:
                        parent_entity = entity_by_raw_local[current]
                        break
                    next_parents = parent_map.get(current, [])
                    current = next_parents[0] if next_parents else ""
                if parent_entity is not None:
                    break
            if parent_entity is None:
                continue
            name_key = _slug(callee_name)
            candidates = symbols_by_file_and_name.get((raw.source_file, name_key), [])
            if len(candidates) != 1:
                candidates = symbols_by_name.get(name_key, [])
            if len(candidates) != 1:
                continue
            target = candidates[0]
            if target.node_id == parent_entity.node_id:
                continue
            add_edge(
                {
                    "source": parent_entity.node_id,
                    "target": target.node_id,
                    "relation": "CALLS",
                    "confidence": "INFERRED",
                    "source_file": raw.source_file,
                    "weight": 0.75,
                }
            )

    return {
        "nodes": extraction_nodes,
        "edges": extraction_edges,
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }


def normalize_dataset_dir(
    dataset_dir: Path,
    *,
    repo_root: Optional[Path] = None,
) -> dict[str, Any]:
    paths = sorted(dataset_dir.glob("*.json"))
    referenced_parts: set[str] = set()
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for part_name in data.get("parts", []) or []:
            referenced_parts.add(str(part_name))
    filtered_paths = [path for path in paths if path.name not in referenced_parts]
    raw_files = [_load_raw_ast_file(path) for path in filtered_paths]
    if not raw_files:
        raise ValueError(f"No AST JSON files found under {dataset_dir}")
    return normalize_raw_ast_files(raw_files, repo_root=repo_root)


__all__ = ["normalize_dataset_dir", "normalize_raw_ast_files"]
