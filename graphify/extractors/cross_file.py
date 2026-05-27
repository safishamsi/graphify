from .core import *
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Cross-file import resolution ──────────────────────────────────────────────

def _source_key(source_file: str, root: Path) -> str:
    if not source_file:
        return ""
    source_path = Path(source_file)
    try:
        return str(source_path.resolve().relative_to(root))
    except Exception:
        return str(source_path)


def _disambiguate_colliding_node_ids(
    nodes: list[dict],
    edges: list[dict],
    raw_calls: list[dict],
    root: Path,
) -> None:
    """Rewrite only colliding node IDs, using source path as the disambiguator."""
    by_id: dict[str, list[dict]] = {}
    for node in nodes:
        nid = node.get("id")
        if isinstance(nid, str) and nid:
            by_id.setdefault(nid, []).append(node)

    remap: dict[tuple[str, str], str] = {}
    ambiguous_ids: set[str] = set()
    for old_id, group in by_id.items():
        source_keys = {_source_key(str(node.get("source_file", "")), root) for node in group}
        if len(group) < 2 or len(source_keys) < 2:
            continue
        ambiguous_ids.add(old_id)
        for node in group:
            source_key = _source_key(str(node.get("source_file", "")), root)
            if not source_key:
                continue
            new_id = _make_id(source_key, old_id)
            remap[(old_id, source_key)] = new_id
            if new_id != old_id:
                node["id"] = new_id

    if not remap:
        return

    unambiguous_remaps: dict[str, str] = {}
    for old_id, group in by_id.items():
        if old_id in ambiguous_ids:
            continue
        candidates = {
            node["id"] for node in group
            if isinstance(node.get("id"), str) and node["id"] != old_id
        }
        if len(candidates) == 1:
            unambiguous_remaps[old_id] = next(iter(candidates))

    for edge in edges:
        edge_source_key = _source_key(str(edge.get("source_file", "")), root)
        source_key = (edge.get("source", ""), edge_source_key)
        target_key = (edge.get("target", ""), edge_source_key)
        if source_key in remap:
            edge["source"] = remap[source_key]
        elif edge.get("source") in unambiguous_remaps:
            edge["source"] = unambiguous_remaps[str(edge["source"])]
        if target_key in remap:
            edge["target"] = remap[target_key]
        elif edge.get("target") in unambiguous_remaps:
            edge["target"] = unambiguous_remaps[str(edge["target"])]

    for raw_call in raw_calls:
        call_source_key = _source_key(str(raw_call.get("source_file", "")), root)
        caller_key = (raw_call.get("caller_nid", ""), call_source_key)
        if caller_key in remap:
            raw_call["caller_nid"] = remap[caller_key]
        elif raw_call.get("caller_nid") in unambiguous_remaps:
            raw_call["caller_nid"] = unambiguous_remaps[str(raw_call["caller_nid"])]


def _node_label_key(node: dict) -> str:
    label = str(node.get("label", "")).strip()
    return re.sub(r"[^a-zA-Z0-9]+", "", label).lower()


def _is_type_like_definition(node: dict) -> bool:
    label = str(node.get("label", "")).strip()
    if not label:
        return False
    if label.endswith(")") or label.startswith("."):
        return False
    if "." in label:
        return False
    return node.get("file_type") == "code"


def _rewire_unique_stub_nodes(nodes: list[dict], edges: list[dict]) -> None:
    """Map unresolved no-source stubs to a unique real definition with the same label."""
    real_by_label: dict[str, list[dict]] = {}
    stubs: list[dict] = []

    for node in nodes:
        key = _node_label_key(node)
        if not key:
            continue
        if node.get("source_file"):
            if _is_type_like_definition(node):
                real_by_label.setdefault(key, []).append(node)
            continue
        stubs.append(node)

    remap: dict[str, str] = {}
    drop_ids: set[str] = set()
    for stub in stubs:
        stub_id = str(stub.get("id", ""))
        if not stub_id:
            continue
        candidates = real_by_label.get(_node_label_key(stub), [])
        if len(candidates) != 1:
            continue
        target_id = candidates[0].get("id")
        if isinstance(target_id, str) and target_id and target_id != stub_id:
            remap[stub_id] = target_id
            drop_ids.add(stub_id)

    if not remap:
        return

    for edge in edges:
        if edge.get("source") in remap:
            edge["source"] = remap[str(edge["source"])]
        if edge.get("target") in remap:
            edge["target"] = remap[str(edge["target"])]

    nodes[:] = [node for node in nodes if node.get("id") not in drop_ids]


def _js_source_path(source_file: str, root: Path) -> Path | None:
    if not source_file:
        return None
    path = Path(source_file)
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve()
    except Exception:
        return path


@dataclass(frozen=True)
class _SymbolDeclarationFact:
    file_path: Path
    name: str
    line: int


@dataclass(frozen=True)
class _SymbolImportFact:
    file_path: Path
    local_name: str
    target_path: Path
    imported_name: str
    line: int


@dataclass(frozen=True)
class _SymbolAliasFact:
    file_path: Path
    alias: str
    target_name: str
    line: int


@dataclass(frozen=True)
class _SymbolExportFact:
    file_path: Path
    exported_name: str
    line: int
    local_name: str | None = None
    target_path: Path | None = None
    target_name: str | None = None


@dataclass(frozen=True)
class _StarExportFact:
    file_path: Path
    target_path: Path
    line: int


@dataclass(frozen=True)
class _SymbolUseFact:
    file_path: Path
    source_id: str
    local_name: str
    relation: str
    context: str
    line: int


@dataclass
class _SymbolResolutionFacts:
    declarations: list[_SymbolDeclarationFact] = field(default_factory=list)
    imports: list[_SymbolImportFact] = field(default_factory=list)
    aliases: list[_SymbolAliasFact] = field(default_factory=list)
    exports: list[_SymbolExportFact] = field(default_factory=list)
    star_exports: list[_StarExportFact] = field(default_factory=list)
    uses: list[_SymbolUseFact] = field(default_factory=list)


def _apply_symbol_resolution_facts(
    paths: list[Path],
    nodes: list[dict],
    edges: list[dict],
    root: Path,
    facts: _SymbolResolutionFacts,
) -> None:
    """Apply language-provided import/export/use facts to graph edges."""
    if not (
        facts.declarations
        or facts.imports
        or facts.aliases
        or facts.exports
        or facts.star_exports
        or facts.uses
    ):
        return

    path_by_resolved = {path.resolve(): path for path in paths}
    source_file_id = {path.resolve(): _make_id(str(path)) for path in paths}
    symbol_nodes: dict[tuple[Path, str], str] = {}
    for node in nodes:
        source_path = _js_source_path(str(node.get("source_file", "")), root)
        if source_path is None:
            continue
        label = str(node.get("label", "")).strip().strip("()").lstrip(".")
        if label and node.get("id"):
            symbol_nodes[(source_path, label)] = str(node["id"])

    def ensure_symbol_node(path: Path, name: str, line: int) -> str:
        resolved_path = path.resolve()
        existing = symbol_nodes.get((resolved_path, name))
        if existing is not None:
            return existing
        node_id = _make_id(_file_stem(path), name)
        symbol_nodes[(resolved_path, name)] = node_id
        nodes.append({
            "id": node_id,
            "label": name,
            "file_type": "code",
            "source_file": str(path),
            "source_location": f"L{line}",
        })
        return node_id

    existing_edges = {
        (
            str(edge.get("source")),
            str(edge.get("target")),
            str(edge.get("relation")),
            str(edge.get("context") or ""),
        )
        for edge in edges
    }

    def add_edge(source: str, target: str, relation: str, context: str, line: int, source_path: Path) -> None:
        key = (source, target, relation, context or "")
        if key in existing_edges:
            return
        existing_edges.add(key)
        edges.append({
            "source": source,
            "target": target,
            "relation": relation,
            "context": context,
            "confidence": "EXTRACTED",
            "source_file": str(source_path),
            "source_location": f"L{line}",
            "weight": 1.0,
        })

    for declaration in facts.declarations:
        ensure_symbol_node(declaration.file_path, declaration.name, declaration.line)

    local_aliases_by_file: dict[Path, dict[str, tuple[Path, str]]] = {}
    for import_fact in facts.imports:
        file_path = import_fact.file_path.resolve()
        local_aliases_by_file.setdefault(file_path, {})[import_fact.local_name] = (
            import_fact.target_path.resolve(),
            import_fact.imported_name,
        )

    pending_aliases_by_file: dict[Path, list[_SymbolAliasFact]] = {}
    for alias_fact in facts.aliases:
        pending_aliases_by_file.setdefault(alias_fact.file_path.resolve(), []).append(alias_fact)

    for file_path, aliases in pending_aliases_by_file.items():
        local_aliases = local_aliases_by_file.setdefault(file_path, {})
        changed = True
        while changed:
            changed = False
            for alias_fact in aliases:
                if alias_fact.alias in local_aliases:
                    continue
                origin = local_aliases.get(alias_fact.target_name)
                if origin is not None:
                    local_aliases[alias_fact.alias] = origin
                    changed = True

    named_exports_by_file: dict[Path, dict[str, tuple[Path, str]]] = {}
    star_exports_by_file: dict[Path, list[Path]] = {}

    for star_fact in facts.star_exports:
        source_path = star_fact.file_path.resolve()
        target_path = star_fact.target_path.resolve()
        star_exports_by_file.setdefault(source_path, []).append(target_path)
        source_id = source_file_id.get(source_path)
        if source_id is not None:
            add_edge(
                source_id,
                _make_id(str(path_by_resolved.get(target_path, target_path))),
                "re_exports",
                "export",
                star_fact.line,
                star_fact.file_path,
            )

    for export_fact in facts.exports:
        file_path = export_fact.file_path.resolve()
        origin: tuple[Path, str] | None = None
        if export_fact.target_path is not None and export_fact.target_name is not None:
            origin = (export_fact.target_path.resolve(), export_fact.target_name)
        elif export_fact.local_name is not None:
            origin = local_aliases_by_file.get(file_path, {}).get(export_fact.local_name)
            if origin is None and (file_path, export_fact.local_name) in symbol_nodes:
                origin = (file_path, export_fact.local_name)
        if origin is None:
            continue
        named_exports_by_file.setdefault(file_path, {})[export_fact.exported_name] = origin
        if origin[0] != file_path:
            source_id = source_file_id.get(file_path)
            if source_id is not None:
                add_edge(
                    source_id,
                    _make_id(str(path_by_resolved.get(origin[0], origin[0]))),
                    "re_exports",
                    "export",
                    export_fact.line,
                    export_fact.file_path,
                )

    def resolve_exported_origin(target_path: Path, imported_name: str, seen: set[tuple[Path, str]] | None = None) -> tuple[Path, str]:
        target_path = target_path.resolve()
        key = (target_path, imported_name)
        if seen is None:
            seen = set()
        if key in seen:
            return key
        seen.add(key)
        origin = named_exports_by_file.get(target_path, {}).get(imported_name)
        if origin is not None:
            return resolve_exported_origin(origin[0], origin[1], seen)
        for star_target in star_exports_by_file.get(target_path, []):
            star_key = (star_target, imported_name)
            if star_key in symbol_nodes:
                return star_key
            resolved = resolve_exported_origin(star_target, imported_name, seen)
            if resolved in symbol_nodes:
                return resolved
        return key

    for import_fact in facts.imports:
        source_id = source_file_id.get(import_fact.file_path.resolve())
        if source_id is None:
            continue
        origin_path, origin_symbol = resolve_exported_origin(
            import_fact.target_path,
            import_fact.imported_name,
        )
        target_id = symbol_nodes.get((origin_path, origin_symbol))
        if target_id is None:
            continue
        add_edge(
            source_id,
            target_id,
            "imports",
            "import",
            import_fact.line,
            import_fact.file_path,
        )

    for use_fact in facts.uses:
        file_path = use_fact.file_path.resolve()
        unresolved_origin = local_aliases_by_file.get(file_path, {}).get(use_fact.local_name)
        if unresolved_origin is None:
            continue
        origin_path, origin_symbol = resolve_exported_origin(*unresolved_origin)
        target_id = symbol_nodes.get((origin_path, origin_symbol))
        if target_id is None:
            continue
        add_edge(
            use_fact.source_id,
            target_id,
            use_fact.relation,
            use_fact.context,
            use_fact.line,
            use_fact.file_path,
        )


def _parse_js_tree(path: Path):
    try:
        from tree_sitter import Language, Parser
        if path.suffix in (".ts", ".tsx"):
            import tree_sitter_typescript as tstypescript
            language = Language(tstypescript.language_typescript())
        else:
            import tree_sitter_javascript as tsjavascript
            language = Language(tsjavascript.language())
        source = path.read_bytes()
        parser = Parser(language)
        return source, parser.parse(source).root_node
    except Exception:
        return None


def _walk_js_tree(node):
    yield node
    for child in node.children:
        yield from _walk_js_tree(child)


def _js_module_specifier(node, source: bytes) -> str | None:
    source_node = node.child_by_field_name("source")
    if source_node is None:
        for child in node.children:
            if child.type == "string":
                source_node = child
                break
    if source_node is None:
        return None
    raw = _read_text(source_node, source).strip()
    return raw.strip("'\"`") or None


def _js_named_specifiers(node, source: bytes, specifier_type: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for child in _walk_js_tree(node):
        if child.type != specifier_type:
            continue
        name_node = child.child_by_field_name("name")
        if name_node is None:
            continue
        alias_node = child.child_by_field_name("alias")
        name = _read_text(name_node, source)
        exposed = _read_text(alias_node, source) if alias_node is not None else name
        if name and exposed:
            pairs.append((name, exposed))
    return pairs


def _js_export_clause(node):
    for child in node.children:
        if child.type == "export_clause":
            return child
    return None


def _js_export_statement_is_star(node) -> bool:
    return any(child.type == "*" for child in node.children)


def _js_lexical_aliases(node, source: bytes) -> list[tuple[str, str]]:
    aliases: list[tuple[str, str]] = []
    if node.type != "lexical_declaration":
        return aliases
    for child in node.children:
        if child.type != "variable_declarator":
            continue
        name_node = child.child_by_field_name("name")
        value_node = child.child_by_field_name("value")
        if (
            name_node is not None
            and value_node is not None
            and value_node.type in ("identifier", "type_identifier")
        ):
            aliases.append((_read_text(name_node, source), _read_text(value_node, source)))
    return aliases


def _js_exported_declaration_names(node, source: bytes) -> list[str]:
    names: list[str] = []
    declaration = node.child_by_field_name("declaration")
    if declaration is None:
        return names

    if declaration.type == "lexical_declaration":
        names.extend(alias for alias, _target in _js_lexical_aliases(declaration, source))
        return names

    if declaration.type in (
        "class_declaration",
        "abstract_class_declaration",
        "interface_declaration",
        "type_alias_declaration",
        "function_declaration",
    ):
        name_node = declaration.child_by_field_name("name")
        if name_node is not None:
            names.append(_read_text(name_node, source))
    return names


def _js_top_level_function_bodies(path: Path, root_node, source: bytes) -> list[tuple[str, object]]:
    bodies: list[tuple[str, object]] = []
    stem = _file_stem(path)
    for node in root_node.children:
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            body = node.child_by_field_name("body")
            if name_node is not None and body is not None:
                bodies.append((_make_id(stem, _read_text(name_node, source)), body))
            continue
        if node.type != "lexical_declaration":
            continue
        for child in node.children:
            if child.type != "variable_declarator":
                continue
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if (
                name_node is not None
                and value_node is not None
                and value_node.type == "arrow_function"
            ):
                bodies.append((_make_id(stem, _read_text(name_node, source)), value_node))
    return bodies


def _js_call_identifier(node, source: bytes) -> str | None:
    if node.type != "call_expression":
        return None
    function_node = node.child_by_field_name("function")
    if function_node is None:
        for child in node.children:
            if child.is_named:
                function_node = child
                break
    if function_node is not None and function_node.type in ("identifier", "type_identifier"):
        return _read_text(function_node, source)
    return None


_JS_PRIMITIVE_TYPES = frozenset({
    "string", "number", "boolean", "any", "unknown", "void", "never",
    "object", "null", "undefined", "bigint", "symbol", "this",
})


def _ts_heritage_clause_entries(clause_node, source: bytes) -> list[str]:
    """Return base/interface type names from an extends_clause or implements_clause."""
    out: list[str] = []
    for child in clause_node.children:
        if not child.is_named:
            continue
        if child.type in ("identifier", "type_identifier"):
            name = _read_text(child, source)
            if name:
                out.append(name)
        elif child.type == "generic_type":
            name_node = child.child_by_field_name("name")
            if name_node is None:
                for sub in child.children:
                    if sub.type in ("type_identifier", "nested_type_identifier", "identifier"):
                        name_node = sub
                        break
            if name_node is not None:
                text = _read_text(name_node, source).rsplit(".", 1)[-1]
                if text:
                    out.append(text)
        elif child.type == "nested_type_identifier":
            text = _read_text(child, source).rsplit(".", 1)[-1]
            if text:
                out.append(text)
    return out


def _ts_collect_type_refs(node, source: bytes, generic: bool, out: list[tuple[str, str]]) -> None:
    """Walk a TS type annotation tree; append (name, role) tuples.

    role is 'type' for the outermost type position and 'generic_arg' for entries
    that appear inside `type_arguments`.
    """
    if node is None:
        return
    t = node.type
    if t == "type_annotation":
        for c in node.children:
            if c.is_named:
                _ts_collect_type_refs(c, source, generic, out)
        return
    if t in ("type_identifier", "identifier"):
        name = _read_text(node, source)
        if name and name not in _JS_PRIMITIVE_TYPES:
            out.append((name, "generic_arg" if generic else "type"))
        return
    if t == "nested_type_identifier":
        tail = _read_text(node, source).rsplit(".", 1)[-1]
        if tail and tail not in _JS_PRIMITIVE_TYPES:
            out.append((tail, "generic_arg" if generic else "type"))
        return
    if t == "generic_type":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            text = _read_text(name_node, source).rsplit(".", 1)[-1]
            if text and text not in _JS_PRIMITIVE_TYPES:
                out.append((text, "generic_arg" if generic else "type"))
        else:
            for c in node.children:
                if c.type in ("type_identifier", "nested_type_identifier"):
                    text = _read_text(c, source).rsplit(".", 1)[-1]
                    if text and text not in _JS_PRIMITIVE_TYPES:
                        out.append((text, "generic_arg" if generic else "type"))
                    break
        for c in node.children:
            if c.type == "type_arguments":
                for sub in c.children:
                    if sub.is_named:
                        _ts_collect_type_refs(sub, source, True, out)
        return
    if node.is_named:
        for c in node.children:
            if c.is_named:
                _ts_collect_type_refs(c, source, generic, out)


def _ts_walk_class_members(class_node, source: bytes, path: Path, class_nid: str,
                            facts: _SymbolResolutionFacts) -> None:
    """Emit type-relation and type-reference use facts for a class declaration node."""
    class_node.start_point[0] + 1
    for child in class_node.children:
        if child.type == "class_heritage":
            for clause in child.children:
                if clause.type == "extends_clause":
                    for name in _ts_heritage_clause_entries(clause, source):
                        facts.uses.append(
                            _SymbolUseFact(path, class_nid, name, "inherits", "type",
                                           clause.start_point[0] + 1)
                        )
                elif clause.type == "implements_clause":
                    for name in _ts_heritage_clause_entries(clause, source):
                        facts.uses.append(
                            _SymbolUseFact(path, class_nid, name, "implements", "type",
                                           clause.start_point[0] + 1)
                        )

    body = class_node.child_by_field_name("body")
    if body is None:
        return

    for member in body.children:
        m_line = member.start_point[0] + 1
        if member.type in ("method_definition", "method_signature", "abstract_method_signature"):
            name_node = member.child_by_field_name("name")
            if name_node is None:
                continue
            method_name = _read_text(name_node, source)
            method_nid = _make_id(class_nid, method_name)
            params = member.child_by_field_name("parameters")
            if params is not None:
                for p in params.children:
                    if p.type not in ("required_parameter", "optional_parameter"):
                        continue
                    type_anno = p.child_by_field_name("type")
                    if type_anno is None:
                        continue
                    refs: list[tuple[str, str]] = []
                    _ts_collect_type_refs(type_anno, source, False, refs)
                    for name, role in refs:
                        ctx = "generic_arg" if role == "generic_arg" else "parameter_type"
                        facts.uses.append(
                            _SymbolUseFact(path, method_nid, name, "references", ctx, m_line)
                        )
            return_type = member.child_by_field_name("return_type")
            if return_type is not None:
                refs = []
                _ts_collect_type_refs(return_type, source, False, refs)
                for name, role in refs:
                    ctx = "generic_arg" if role == "generic_arg" else "return_type"
                    facts.uses.append(
                        _SymbolUseFact(path, method_nid, name, "references", ctx, m_line)
                    )
        elif member.type in ("public_field_definition", "property_signature"):
            type_anno = None
            for c in member.children:
                if c.type == "type_annotation":
                    type_anno = c
                    break
            if type_anno is None:
                continue
            refs = []
            _ts_collect_type_refs(type_anno, source, False, refs)
            for name, role in refs:
                ctx = "generic_arg" if role == "generic_arg" else "field"
                facts.uses.append(
                    _SymbolUseFact(path, class_nid, name, "references", ctx, m_line)
                )


def _collect_js_symbol_resolution_facts(paths: list[Path], facts: _SymbolResolutionFacts) -> None:
    js_paths = [
        path for path in paths
        if path.suffix in _JS_CACHE_BYPASS_SUFFIXES and path.suffix != ".vue"
    ]
    if not js_paths:
        return

    trees: dict[Path, tuple[bytes, object]] = {}

    for path in js_paths:
        resolved_path = path.resolve()
        parsed = _parse_js_tree(path)
        if parsed is None:
            continue
        source, root_node = parsed
        trees[resolved_path] = parsed

        for node in _walk_js_tree(root_node):
            if node.type == "export_statement":
                for name in _js_exported_declaration_names(node, source):
                    facts.declarations.append(
                        _SymbolDeclarationFact(path, name, node.start_point[0] + 1)
                    )

            if node.type != "import_statement":
                continue
            raw_module = _js_module_specifier(node, source)
            if raw_module is None:
                continue
            target_path = _resolve_js_module_path(raw_module, path.parent)
            if target_path is None:
                continue
            target_path = target_path.resolve()
            for imported_name, local_name in _js_named_specifiers(node, source, "import_specifier"):
                facts.imports.append(
                    _SymbolImportFact(
                        path,
                        local_name,
                        target_path,
                        imported_name,
                        node.start_point[0] + 1,
                    )
                )

        for node in _walk_js_tree(root_node):
            for alias, target in _js_lexical_aliases(node, source):
                facts.aliases.append(
                    _SymbolAliasFact(path, alias, target, node.start_point[0] + 1)
                )

    for path in js_paths:
        resolved_path = path.resolve()
        parsed = trees.get(resolved_path)
        if parsed is None:
            continue
        source, root_node = parsed

        for node in _walk_js_tree(root_node):
            if node.type != "export_statement":
                continue

            raw_module = _js_module_specifier(node, source)
            export_clause = _js_export_clause(node)
            if raw_module is not None:
                target_path = _resolve_js_module_path(raw_module, path.parent)
                if target_path is None:
                    continue
                target_path = target_path.resolve()
                if _js_export_statement_is_star(node):
                    facts.star_exports.append(
                        _StarExportFact(path, target_path, node.start_point[0] + 1)
                    )
                if export_clause is not None:
                    for original_name, exported_name in _js_named_specifiers(
                        export_clause, source, "export_specifier"
                    ):
                        facts.exports.append(
                            _SymbolExportFact(
                                path,
                                exported_name,
                                node.start_point[0] + 1,
                                target_path=target_path,
                                target_name=original_name,
                            )
                        )
                continue

            if export_clause is not None:
                for local_name, exported_name in _js_named_specifiers(
                    export_clause, source, "export_specifier"
                ):
                    facts.exports.append(
                        _SymbolExportFact(
                            path,
                            exported_name,
                            node.start_point[0] + 1,
                            local_name=local_name,
                        )
                    )
                continue

            for exported_name in _js_exported_declaration_names(node, source):
                facts.exports.append(
                    _SymbolExportFact(
                        path,
                        exported_name,
                        node.start_point[0] + 1,
                        local_name=exported_name,
                    )
                )

    for path in js_paths:
        resolved_path = path.resolve()
        parsed = trees.get(resolved_path)
        if parsed is None:
            continue
        source, root_node = parsed
        for source_id, body in _js_top_level_function_bodies(path, root_node, source):
            for node in _walk_js_tree(body):
                imported_name = _js_call_identifier(node, source)
                if imported_name is None:
                    continue
                facts.uses.append(
                    _SymbolUseFact(
                        path,
                        source_id,
                        imported_name,
                        "calls",
                        "call",
                        node.start_point[0] + 1,
                    )
                )

    for path in js_paths:
        resolved_path = path.resolve()
        parsed = trees.get(resolved_path)
        if parsed is None:
            continue
        source, root_node = parsed
        stem = _file_stem(path)
        for node in _walk_js_tree(root_node):
            if node.type not in (
                "class_declaration",
                "abstract_class_declaration",
                "interface_declaration",
            ):
                continue
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            class_name = _read_text(name_node, source)
            if not class_name:
                continue
            class_nid = _make_id(stem, class_name)
            _ts_walk_class_members(node, source, path, class_nid, facts)


def _parse_python_tree(path: Path):
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_python as tspython
        source = path.read_bytes()
        parser = Parser(Language(tspython.language()))
        return source, parser.parse(source).root_node
    except Exception:
        return None


def _walk_python_tree(node):
    yield node
    for child in node.children:
        yield from _walk_python_tree(child)


def _python_import_from_module(node, source: bytes) -> tuple[int, str] | None:
    level = 0
    module_name = ""
    for child in node.children:
        if child.type == "import":
            break
        if child.type == "relative_import":
            raw = _read_text(child, source)
            level = len(raw) - len(raw.lstrip("."))
            remainder = raw.lstrip(".")
            if remainder:
                module_name = remainder
            for sub in child.children:
                if sub.type == "dotted_name":
                    module_name = _read_text(sub, source)
        elif child.type == "dotted_name":
            module_name = _read_text(child, source)
    if level == 0 and not module_name:
        return None
    return level, module_name


def _python_imported_names(node, source: bytes) -> list[tuple[str, str]]:
    names: list[tuple[str, str]] = []
    past_import = False
    for child in node.children:
        if child.type == "import":
            past_import = True
            continue
        if not past_import:
            continue
        if child.type == "dotted_name":
            name = _read_text(child, source)
            names.append((name, name.split(".")[-1]))
        elif child.type == "aliased_import":
            name_node = child.child_by_field_name("name")
            alias_node = child.child_by_field_name("alias")
            if name_node is None:
                continue
            name = _read_text(name_node, source)
            local = _read_text(alias_node, source) if alias_node is not None else name.split(".")[-1]
            names.append((name, local))
    return names


def _resolve_python_module_path(module_name: str, current_path: Path, root: Path, level: int) -> Path | None:
    if level > 0:
        base = current_path.parent
        for _ in range(level - 1):
            base = base.parent
        candidate = base / module_name.replace(".", "/") if module_name else base
    else:
        candidate = root / module_name.replace(".", "/")

    if candidate.is_dir():
        init_path = candidate / "__init__.py"
        if init_path.is_file():
            return init_path
    if candidate.is_file():
        return candidate
    py_candidate = candidate.with_suffix(".py")
    if py_candidate.is_file():
        return py_candidate
    return None


def _python_top_level_function_bodies(path: Path, root_node, source: bytes) -> list[tuple[str, object]]:
    bodies: list[tuple[str, object]] = []
    stem = _file_stem(path)
    for node in root_node.children:
        if node.type != "function_definition":
            continue
        name_node = node.child_by_field_name("name")
        body = node.child_by_field_name("body")
        if name_node is not None and body is not None:
            bodies.append((_make_id(stem, _read_text(name_node, source)), body))
    return bodies


def _python_call_identifier(node, source: bytes) -> str | None:
    if node.type != "call":
        return None
    function_node = node.child_by_field_name("function")
    if function_node is not None and function_node.type == "identifier":
        return _read_text(function_node, source)
    return None


def _collect_python_symbol_resolution_facts(
    paths: list[Path],
    root: Path,
    facts: _SymbolResolutionFacts,
) -> None:
    py_paths = [path for path in paths if path.suffix == ".py"]
    if not py_paths:
        return

    trees: dict[Path, tuple[bytes, object]] = {}
    for path in py_paths:
        parsed = _parse_python_tree(path)
        if parsed is None:
            continue
        source, root_node = parsed
        trees[path.resolve()] = parsed

        for node in _walk_python_tree(root_node):
            if node.type != "import_from_statement":
                continue
            module = _python_import_from_module(node, source)
            if module is None:
                continue
            level, module_name = module
            target_path = _resolve_python_module_path(module_name, path, root, level)
            if target_path is None:
                continue
            for imported_name, local_name in _python_imported_names(node, source):
                line = node.start_point[0] + 1
                facts.imports.append(
                    _SymbolImportFact(path, local_name, target_path, imported_name, line)
                )
                if path.name == "__init__.py":
                    facts.exports.append(
                        _SymbolExportFact(
                            path,
                            local_name,
                            line,
                            target_path=target_path,
                            target_name=imported_name,
                        )
                    )

    for path in py_paths:
        parsed = trees.get(path.resolve())
        if parsed is None:
            continue
        source, root_node = parsed
        for source_id, body in _python_top_level_function_bodies(path, root_node, source):
            for node in _walk_python_tree(body):
                imported_name = _python_call_identifier(node, source)
                if imported_name is None:
                    continue
                facts.uses.append(
                    _SymbolUseFact(
                        path,
                        source_id,
                        imported_name,
                        "calls",
                        "call",
                        node.start_point[0] + 1,
                    )
                )


def _augment_symbol_resolution_edges(
    paths: list[Path],
    nodes: list[dict],
    edges: list[dict],
    root: Path,
) -> None:
    facts = _SymbolResolutionFacts()
    _collect_js_symbol_resolution_facts(paths, facts)
    _collect_python_symbol_resolution_facts(paths, root, facts)
    _apply_symbol_resolution_facts(paths, nodes, edges, root, facts)


def _augment_js_reexport_edges(
    paths: list[Path],
    nodes: list[dict],
    edges: list[dict],
    root: Path,
) -> None:
    """Compatibility wrapper for the JS/TS symbol-resolution post-pass."""
    facts = _SymbolResolutionFacts()
    _collect_js_symbol_resolution_facts(paths, facts)
    _apply_symbol_resolution_facts(paths, nodes, edges, root, facts)


def _resolve_cross_file_imports(
    per_file: list[dict],
    paths: list[Path],
) -> list[dict]:
    """
    Two-pass import resolution: turn file-level imports into class-level edges.

    Pass 1 - build a global map: class/function name → node_id, per stem.
    Pass 2 - for each `from .module import Name`, look up Name in the global
              map and add a direct INFERRED edge from each class in the
              importing file to the imported entity.

    This turns:
        auth.py --imports_from--> models.py          (obvious, filtered out)
    Into:
        DigestAuth --uses--> Response  [INFERRED]    (cross-file, interesting!)
        BasicAuth  --uses--> Request   [INFERRED]
    """
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
    except ImportError:
        return []

    language = Language(tspython.language())
    parser = Parser(language)

    # Pass 1: _file_stem(path) → {ClassName: node_id}
    # Keyed by directory-qualified stem (e.g. "auth_models") to avoid collisions
    # when multiple files share the same filename in different directories.
    # A secondary bare-stem index handles absolute imports where only the module
    # name is known — first writer wins when names collide (inherently ambiguous).
    stem_to_entities: dict[str, dict[str, str]] = {}
    bare_to_qualified: dict[str, str] = {}
    for file_result in per_file:
        for node in file_result.get("nodes", []):
            src = node.get("source_file", "")
            if not src:
                continue
            src_path = Path(src)
            fq_stem = _file_stem(src_path)
            label = node.get("label", "")
            nid = node.get("id", "")
            # Index class-level entities only. Function/method labels end in "()"
            # so are excluded by the `endswith(")")` filter; file nodes end in ".py";
            # private/internal labels start with "_"; rationale nodes carry
            # file_type=="rationale" and must never participate in cross-file
            # import resolution (#563).
            if (
                label
                and not label.endswith((")", ".py"))
                and "_" not in label[:1]
                and node.get("file_type") != "rationale"
            ):
                stem_to_entities.setdefault(fq_stem, {})[label] = nid
                if src_path.stem not in bare_to_qualified:
                    bare_to_qualified[src_path.stem] = fq_stem

    # Pass 2: for each file, find `from .X import A, B, C` and resolve
    new_edges: list[dict] = []
    stem_to_path: dict[str, Path] = {_file_stem(p): p for p in paths}

    for file_result, path in zip(per_file, paths):
        stem = _file_stem(path)
        str_path = str(path)

        # Find all classes defined in this file (the importers).
        # Excludes rationale nodes whose labels happen not to end in ")" or ".py"
        # but which must never be treated as importing entities (#563).
        local_classes = [
            n["id"] for n in file_result.get("nodes", [])
            if n.get("source_file") == str_path
            and not n["label"].endswith((")", ".py"))
            and n["id"] != _make_id(stem)  # exclude file-level node
            and n.get("file_type") != "rationale"
        ]
        if not local_classes:
            continue

        # Parse imports from this file
        try:
            source = path.read_bytes()
            tree = parser.parse(source)
        except Exception:
            continue

        def walk_imports(node) -> None:
            if node.type == "import_from_statement":
                # Find the module name - handles both absolute and relative imports.
                # Relative: `from .models import X` → relative_import → dotted_name
                # Absolute: `from models import X`  → module_name field
                # target_fq is the directory-qualified stem used as the key in
                # stem_to_entities. Relative imports are resolved exactly via the
                # importing file's directory; absolute imports fall back to the
                # bare-stem secondary index (first-writer-wins when names collide).
                target_fq: str | None = None
                for child in node.children:
                    if child.type == "relative_import":
                        for sub in child.children:
                            if sub.type == "dotted_name":
                                raw = source[sub.start_byte:sub.end_byte].decode("utf-8", errors="replace")
                                bare = raw.split(".")[-1]
                                # Resolve relative import to exact qualified stem.
                                candidate = path.parent / f"{bare}.py"
                                target_fq = _file_stem(candidate)
                                break
                        break
                    if child.type == "dotted_name" and target_fq is None:
                        raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                        bare = raw.split(".")[-1]
                        target_fq = bare_to_qualified.get(bare)

                if not target_fq or target_fq not in stem_to_entities:
                    return

                # Collect imported names: dotted_name children of import_from_statement
                # that come AFTER the 'import' keyword token.
                imported_names: list[str] = []
                past_import_kw = False
                for child in node.children:
                    if child.type == "import":
                        past_import_kw = True
                        continue
                    if not past_import_kw:
                        continue
                    if child.type == "dotted_name":
                        imported_names.append(
                            source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                        )
                    elif child.type == "aliased_import":
                        # `import X as Y` - take the original name
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            imported_names.append(
                                source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                            )

                line = node.start_point[0] + 1
                for name in imported_names:
                    tgt_nid = stem_to_entities[target_fq].get(name)
                    if tgt_nid:
                        for src_class_nid in local_classes:
                            new_edges.append({
                                "source": src_class_nid,
                                "target": tgt_nid,
                                "relation": "uses",
                                "confidence": "INFERRED",
                                "source_file": str_path,
                                "source_location": f"L{line}",
                                "weight": 0.8,
                            })
            for child in node.children:
                walk_imports(child)

        walk_imports(tree.root_node)

    return new_edges


def _merge_swift_extensions(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Collapse cross-file Swift `extension Foo` nodes into the canonical `Foo`.

    tree-sitter-swift reuses `class_declaration` for both `class Foo` and
    `extension Foo`, and node ids carry the file stem, so each file that
    extends `Foo` produces its own `Foo` node. The match is done by label:
    when exactly one non-extension declaration shares the label, extension
    nodes redirect onto it. Extensions of types outside the corpus (no match)
    and ambiguous labels (more than one match) are left untouched — picking
    arbitrarily would invent edges.
    """
    extension_nids: set[str] = set()
    extension_labels: dict[str, str] = {}
    for result in per_file:
        for ext in result.get("swift_extensions", []) or []:
            extension_nids.add(ext["nid"])
            extension_labels[ext["nid"]] = ext["label"]

    if not extension_nids:
        return

    label_to_canonical: dict[str, list[str]] = {}
    for n in all_nodes:
        if n.get("id") in extension_nids:
            continue
        label = n.get("label")
        if not label:
            continue
        label_to_canonical.setdefault(label, []).append(n["id"])

    remap: dict[str, str] = {}
    for ext_nid in extension_nids:
        candidates = label_to_canonical.get(extension_labels[ext_nid], [])
        if len(candidates) != 1:
            continue
        canonical_nid = candidates[0]
        if canonical_nid != ext_nid:
            remap[ext_nid] = canonical_nid

    if not remap:
        return

    all_nodes[:] = [n for n in all_nodes if n.get("id") not in remap]

    # Each extension file's `contains` edge ends up pointing at the canonical
    # type — multiple files containing the same node is the intended shape:
    # the type owns the methods, the files own their slice. Self-loops are
    # dropped (e.g. an in-file extension method whose call already pointed at
    # the canonical type).
    rewritten: list[dict] = []
    seen_keys: set[tuple] = set()
    for e in all_edges:
        src = remap.get(e.get("source"), e.get("source"))
        tgt = remap.get(e.get("target"), e.get("target"))
        if src == tgt:
            continue
        e["source"] = src
        e["target"] = tgt
        key = (src, tgt, e.get("relation"), e.get("source_file"), e.get("source_location"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        rewritten.append(e)
    all_edges[:] = rewritten


def _resolve_cross_file_java_imports(
    per_file: list[dict],
    paths: list[Path],
) -> list[dict]:
    """Two-pass Java import resolution.

    Pass 1: build a global index {ClassName: [node_id, ...]} across all Java nodes.
    Pass 2: re-parse each Java file; for every `import a.b.C;`, resolve C against
    the index. Wildcard and stdlib imports produce no edge.
    """
    try:
        import tree_sitter_java as tsjava
        from tree_sitter import Language, Parser
    except ImportError:
        return []

    language = Language(tsjava.language())
    parser = Parser(language)

    # Pass 1: class-name → node_id index (only internal, uppercase-starting names)
    name_to_ids: dict[str, list[str]] = {}
    for file_result in per_file:
        for node in file_result.get("nodes", []):
            label = node.get("label", "")
            nid = node.get("id", "")
            src = node.get("source_file", "")
            if not label or not nid or not src:
                continue
            if label.endswith(")") or label.endswith(".java"):
                continue
            if not label[0].isalpha() or not label[0].isupper():
                continue
            name_to_ids.setdefault(label, []).append(nid)

    # Pass 2: resolve imports to real node IDs
    new_edges: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for path in paths:
        file_nid = _make_id(str(path))
        try:
            source = path.read_bytes()
            tree = parser.parse(source)
        except Exception:
            continue

        def walk(n) -> None:
            if n.type == "import_declaration":
                raw = _read_text(n, source).strip()
                body = raw[len("import"):].strip().rstrip(";").strip()
                if body.startswith("static "):
                    body = body[len("static "):].strip()
                if body.endswith(".*"):
                    return
                parts = body.split(".")
                if not parts:
                    return
                last = parts[-1]
                if last and last[0].islower() and len(parts) >= 2:
                    last = parts[-2]
                at_line = n.start_point[0] + 1
                for tgt_nid in name_to_ids.get(last, []):
                    if tgt_nid == file_nid:
                        continue
                    key = (file_nid, tgt_nid)
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)
                    new_edges.append({
                        "source": file_nid,
                        "target": tgt_nid,
                        "relation": "imports",
                        "confidence": "EXTRACTED",
                        "confidence_score": 1.0,
                        "source_file": str(path),
                        "source_location": f"L{at_line}",
                        "weight": 1.0,
                    })
            for child in n.children:
                walk(child)

        walk(tree.root_node)

    return new_edges


def extract_objc(path: Path) -> dict:
    """Extract interfaces, implementations, protocols, methods, and imports from .m/.mm/.h files."""
    try:
        import tree_sitter_objc as tsobjc
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_objc not installed"}

    try:
        language = Language(tsobjc.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    method_bodies: list[tuple[str, Any]] = []

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None) -> None:
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": confidence, "source_file": str_path,
                "source_location": f"L{line}", "weight": weight}
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def _read(node) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _get_name(node, field: str) -> str | None:
        n = node.child_by_field_name(field)
        return _read(n) if n else None

    def walk(node, parent_nid: str | None = None) -> None:
        t = node.type
        line = node.start_point[0] + 1

        if t == "preproc_include":
            # #import <Foundation/Foundation.h> or #import "MyClass.h"
            for child in node.children:
                if child.type == "system_lib_string":
                    raw = _read(child).strip("<>")
                    module = raw.split("/")[-1].replace(".h", "")
                    if module:
                        tgt_nid = _make_id(module)
                        add_edge(file_nid, tgt_nid, "imports", line, context="import")
                elif child.type == "string_literal":
                    # recurse into string_literal to find string_content
                    for sub in child.children:
                        if sub.type == "string_content":
                            raw = _read(sub)
                            module = raw.split("/")[-1].replace(".h", "")
                            if module:
                                tgt_nid = _make_id(module)
                                add_edge(file_nid, tgt_nid, "imports", line, context="import")
            return

        if t == "class_interface":
            # @interface ClassName : SuperClass <Protocols>
            # children: @interface, identifier(name), ':', identifier(super), parameterized_arguments, ...
            identifiers = [c for c in node.children if c.type == "identifier"]
            if not identifiers:
                for child in node.children:
                    walk(child, parent_nid)
                return
            name = _read(identifiers[0])
            cls_nid = _make_id(stem, name)
            add_node(cls_nid, name, line)
            add_edge(file_nid, cls_nid, "contains", line)
            # superclass is second identifier after ':'
            colon_seen = False
            for child in node.children:
                if child.type == ":":
                    colon_seen = True
                elif colon_seen and child.type == "identifier":
                    super_nid = _make_id(_read(child))
                    add_edge(cls_nid, super_nid, "inherits", line)
                    colon_seen = False
                elif child.type == "parameterized_arguments":
                    # protocols adopted
                    for sub in child.children:
                        if sub.type == "type_name":
                            for s in sub.children:
                                if s.type == "type_identifier":
                                    proto_nid = _make_id(_read(s))
                                    add_edge(cls_nid, proto_nid, "imports", line, context="import")
                elif child.type == "method_declaration":
                    walk(child, cls_nid)
            return

        if t == "class_implementation":
            # @implementation ClassName
            name = None
            for child in node.children:
                if child.type == "identifier":
                    name = _read(child)
                    break
            if not name:
                for child in node.children:
                    walk(child, parent_nid)
                return
            impl_nid = _make_id(stem, name)
            if impl_nid not in seen_ids:
                add_node(impl_nid, name, line)
                add_edge(file_nid, impl_nid, "contains", line)
            for child in node.children:
                if child.type == "implementation_definition":
                    for sub in child.children:
                        walk(sub, impl_nid)
            return

        if t == "protocol_declaration":
            name = None
            for child in node.children:
                if child.type == "identifier":
                    name = _read(child)
                    break
            if name:
                proto_nid = _make_id(stem, name)
                add_node(proto_nid, f"<{name}>", line)
                add_edge(file_nid, proto_nid, "contains", line)
                for child in node.children:
                    walk(child, proto_nid)
            return

        if t in ("method_declaration", "method_definition"):
            container = parent_nid or file_nid
            # method name is the first identifier child (simple selector)
            # for compound selectors: identifier + method_parameter pairs
            parts = []
            for child in node.children:
                if child.type == "identifier":
                    parts.append(_read(child))
                elif child.type == "method_parameter":
                    for sub in child.children:
                        if sub.type == "identifier":
                            # selector keyword before ':'
                            pass
            method_name = "".join(parts) if parts else None
            if method_name:
                method_nid = _make_id(container, method_name)
                add_node(method_nid, f"-{method_name}", line)
                add_edge(container, method_nid, "method", line)
                if t == "method_definition":
                    method_bodies.append((method_nid, node))
            return

        for child in node.children:
            walk(child, parent_nid)

    walk(root)

    # Second pass: resolve calls inside method bodies
    all_method_nids = {n["id"] for n in nodes if n["id"] != file_nid}
    seen_calls: set[tuple[str, str]] = set()
    for caller_nid, body_node in method_bodies:
        def walk_calls(n) -> None:
            if n.type == "message_expression":
                # [receiver selector]
                for child in n.children:
                    if child.type in ("selector", "keyword_argument_list"):
                        sel = []
                        if child.type == "selector":
                            sel.append(_read(child))
                        else:
                            for sub in child.children:
                                if sub.type == "keyword_argument":
                                    for s in sub.children:
                                        if s.type == "selector":
                                            sel.append(_read(s))
                        method_name = "".join(sel)
                        for candidate in all_method_nids:
                            if candidate.endswith(_make_id("", method_name).lstrip("_")):
                                pair = (caller_nid, candidate)
                                if pair not in seen_calls and caller_nid != candidate:
                                    seen_calls.add(pair)
                                    add_edge(caller_nid, candidate, "calls", body_node.start_point[0] + 1,
                                             confidence="EXTRACTED", weight=1.0, context="call")
            for child in n.children:
                walk_calls(child)
        walk_calls(body_node)

    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}


def extract_elixir(path: Path) -> dict:
    """Extract modules, functions, imports, and calls from a .ex/.exs file."""
    try:
        import tree_sitter_elixir as tselixir
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_elixir not installed"}

    try:
        language = Language(tselixir.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    function_bodies: list[tuple[str, Any]] = []

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None) -> None:
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": confidence, "source_file": str_path,
                "source_location": f"L{line}", "weight": weight}
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    _IMPORT_KEYWORDS = frozenset({"alias", "import", "require", "use"})

    def _get_alias_text(node) -> str | None:
        for child in node.children:
            if child.type == "alias":
                return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
        return None

    def walk(node, parent_module_nid: str | None = None) -> None:
        if node.type != "call":
            for child in node.children:
                walk(child, parent_module_nid)
            return

        identifier_node = None
        arguments_node = None
        do_block_node = None
        for child in node.children:
            if child.type == "identifier":
                identifier_node = child
            elif child.type == "arguments":
                arguments_node = child
            elif child.type == "do_block":
                do_block_node = child

        if identifier_node is None:
            for child in node.children:
                walk(child, parent_module_nid)
            return

        keyword = source[identifier_node.start_byte:identifier_node.end_byte].decode("utf-8", errors="replace")
        line = node.start_point[0] + 1

        if keyword == "defmodule":
            module_name = _get_alias_text(arguments_node) if arguments_node else None
            if not module_name:
                return
            module_nid = _make_id(stem, module_name)
            add_node(module_nid, module_name, line)
            add_edge(file_nid, module_nid, "contains", line)
            if do_block_node:
                for child in do_block_node.children:
                    walk(child, parent_module_nid=module_nid)
            return

        if keyword in ("def", "defp"):
            func_name = None
            if arguments_node:
                for child in arguments_node.children:
                    if child.type == "call":
                        for sub in child.children:
                            if sub.type == "identifier":
                                func_name = source[sub.start_byte:sub.end_byte].decode("utf-8", errors="replace")
                                break
                    elif child.type == "identifier":
                        func_name = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                        break
            if not func_name:
                return
            container = parent_module_nid or file_nid
            func_nid = _make_id(container, func_name)
            add_node(func_nid, f"{func_name}()", line)
            if parent_module_nid:
                add_edge(parent_module_nid, func_nid, "method", line)
            else:
                add_edge(file_nid, func_nid, "contains", line)
            if do_block_node:
                function_bodies.append((func_nid, do_block_node))
            return

        if keyword in _IMPORT_KEYWORDS and arguments_node:
            module_name = _get_alias_text(arguments_node)
            if module_name:
                tgt_nid = _make_id(module_name)
                add_edge(file_nid, tgt_nid, "imports", line, context="import")
            return

        for child in node.children:
            walk(child, parent_module_nid)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        normalised = n["label"].strip("()").lstrip(".")
        label_to_nid[normalised] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []
    _SKIP_KEYWORDS = frozenset({
        "def", "defp", "defmodule", "defmacro", "defmacrop",
        "defstruct", "defprotocol", "defimpl", "defguard",
        "alias", "import", "require", "use",
        "if", "unless", "case", "cond", "with", "for",
    })

    def walk_calls(node, caller_nid: str) -> None:
        if node.type != "call":
            for child in node.children:
                walk_calls(child, caller_nid)
            return
        for child in node.children:
            if child.type == "identifier":
                kw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                if kw in _SKIP_KEYWORDS:
                    for c in node.children:
                        walk_calls(c, caller_nid)
                    return
                break
        callee_name: str | None = None
        is_member_call: bool = False
        for child in node.children:
            if child.type == "dot":
                is_member_call = True
                dot_text = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                parts = dot_text.rstrip(".").split(".")
                if parts:
                    callee_name = parts[-1]
                break
            if child.type == "identifier":
                callee_name = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                break
        if callee_name:
            tgt_nid = label_to_nid.get(callee_name)
            if tgt_nid and tgt_nid != caller_nid:
                pair = (caller_nid, tgt_nid)
                if pair not in seen_call_pairs:
                    seen_call_pairs.add(pair)
                    add_edge(caller_nid, tgt_nid, "calls",
                             node.start_point[0] + 1, confidence="EXTRACTED", weight=1.0,
                             context="call")
            else:
                raw_calls.append({
                    "caller_nid": caller_nid,
                    "callee": callee_name,
                    "is_member_call": is_member_call,
                    "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}",
                })
        for child in node.children:
            walk_calls(child, caller_nid)

    for caller_nid, body in function_bodies:
        walk_calls(body, caller_nid)

    clean_edges = [e for e in edges if e["source"] in seen_ids and
                   (e["target"] in seen_ids or e["relation"] == "imports")]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls, "input_tokens": 0, "output_tokens": 0}


def extract_markdown(path: Path) -> dict:
    """Extract structural nodes and edges from a Markdown file.

    Produces nodes for:
    - The file itself
    - Each heading (# / ## / ### etc.)
    - Each fenced code block (``` ... ```)

    Produces edges for:
    - file --contains--> heading
    - parent heading --contains--> child heading (nesting by level)
    - heading --contains--> code block
    - heading --references--> other node (when backtick `Name` matches a known pattern)

    No tree-sitter dependency — pure line-by-line parsing.
    """
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, file_type: str = "document") -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": file_type,
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({"source": src, "target": tgt, "relation": relation,
                      "confidence": confidence, "source_file": str_path,
                      "source_location": f"L{line}", "weight": weight})

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    # Track heading stack for nesting: [(level, nid), ...]
    heading_stack: list[tuple[int, str]] = []
    in_code_block = False
    code_block_lang: str | None = None
    code_block_start: int = 0
    code_block_lines: list[str] = []
    code_block_count = 0

    lines = source.splitlines()
    for line_num_0, line_text in enumerate(lines):
        line_num = line_num_0 + 1

        # Toggle fenced code blocks
        stripped = line_text.strip()
        if stripped.startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_block_lang = stripped[3:].strip().split()[0] if len(stripped) > 3 else None
                code_block_start = line_num
                code_block_lines = []
                continue
            else:
                # End of code block — create a node
                in_code_block = False
                code_block_count += 1
                snippet = "\n".join(code_block_lines[:3])  # first 3 lines as preview
                label = f"code:{code_block_lang}" if code_block_lang else f"code:block{code_block_count}"
                if snippet:
                    # Use first meaningful line as label hint
                    first_line = code_block_lines[0].strip()[:60] if code_block_lines else ""
                    if first_line:
                        label = f"{label} ({first_line})"
                cb_nid = _make_id(stem, f"codeblock_{code_block_count}")
                add_node(cb_nid, label, code_block_start)
                # Attach to nearest heading or file
                parent = heading_stack[-1][1] if heading_stack else file_nid
                add_edge(parent, cb_nid, "contains", code_block_start)
                continue

        if in_code_block:
            code_block_lines.append(line_text)
            continue

        # Detect headings: # Heading, ## Heading, etc.
        heading_match = re.match(r'^(#{1,6})\s+(.+)', line_text)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            h_nid = _make_id(stem, title)
            # Avoid duplicate heading IDs by appending line number
            if h_nid in seen_ids:
                h_nid = _make_id(stem, title, str(line_num))
            add_node(h_nid, title, line_num)

            # Pop headings at same or deeper level
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()

            # Connect to parent heading or file
            parent = heading_stack[-1][1] if heading_stack else file_nid
            add_edge(parent, h_nid, "contains", line_num)

            heading_stack.append((level, h_nid))
            continue

    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}


__all__ = ['_source_key', '_disambiguate_colliding_node_ids', '_node_label_key', '_is_type_like_definition', '_rewire_unique_stub_nodes', '_js_source_path', '_SymbolDeclarationFact', '_SymbolImportFact', '_SymbolAliasFact', '_SymbolExportFact', '_StarExportFact', '_SymbolUseFact', '_SymbolResolutionFacts', '_apply_symbol_resolution_facts', '_parse_js_tree', '_walk_js_tree', '_js_module_specifier', '_js_named_specifiers', '_js_export_clause', '_js_export_statement_is_star', '_js_lexical_aliases', '_js_exported_declaration_names', '_js_top_level_function_bodies', '_js_call_identifier', '_JS_PRIMITIVE_TYPES', '_ts_heritage_clause_entries', '_ts_collect_type_refs', '_ts_walk_class_members', '_collect_js_symbol_resolution_facts', '_parse_python_tree', '_walk_python_tree', '_python_import_from_module', '_python_imported_names', '_resolve_python_module_path', '_python_top_level_function_bodies', '_python_call_identifier', '_collect_python_symbol_resolution_facts', '_augment_symbol_resolution_edges', '_augment_js_reexport_edges', '_resolve_cross_file_imports', '_merge_swift_extensions', '_resolve_cross_file_java_imports', 'extract_objc', 'extract_elixir', 'extract_markdown']
