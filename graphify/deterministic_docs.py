"""Deterministic documentation extraction helpers.

The first supported language is Python because Python's standard ``ast`` module
can recover docstrings without adding a new dependency. The helpers in this file
turn structured docstring sections into Graphify-compatible nodes and edges.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from graphify.semantic_facts import append_unique_edge, append_unique_node, make_fact_node


MakeId = Callable[..., str]
FileStem = Callable[[Path], str]


@dataclass(frozen=True)
class DocTag:
    """A structured documentation item extracted from a docstring."""

    kind: str
    name: str
    description: str
    line: int
    raw: str


def _normalise_space(text: str) -> str:
    """Collapse repeated whitespace while preserving readable text."""

    return re.sub(r"\s+", " ", text.strip())


def _docstring_start_line(node: ast.AST) -> int:
    """Return the source line where the docstring literal starts."""

    body = getattr(node, "body", [])
    if body and isinstance(body[0], ast.Expr):
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return getattr(body[0], "lineno", getattr(node, "lineno", 1))
    return getattr(node, "lineno", 1)


def _parse_restructured_tags(lines: list[str], base_line: int) -> list[DocTag]:
    """Parse Sphinx/reStructuredText-style docstring fields.

    Supported examples:
        :param path: file path to inspect
        :type path: pathlib.Path
        :returns: extracted graph fragment
        :rtype: dict
        :raises ValueError: when the input is invalid
    """

    tags: list[DocTag] = []
    pending_params: dict[str, tuple[str, int, str]] = {}
    param_types: dict[str, str] = {}
    pending_return: tuple[str, int, str] | None = None
    return_type = ""

    param_re = re.compile(r"^:param\s+(?P<name>[A-Za-z_][\w]*)\s*:\s*(?P<desc>.*)$")
    type_re = re.compile(r"^:type\s+(?P<name>[A-Za-z_][\w]*)\s*:\s*(?P<desc>.*)$")
    returns_re = re.compile(r"^:(returns?|return)\s*:\s*(?P<desc>.*)$")
    rtype_re = re.compile(r"^:rtype\s*:\s*(?P<desc>.*)$")
    raises_re = re.compile(r"^:raises?\s+(?P<name>[A-Za-z_][\w.]*)\s*:\s*(?P<desc>.*)$")

    for offset, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        type_match = type_re.match(line)
        if type_match:
            param_types[type_match.group("name")] = _normalise_space(type_match.group("desc"))
            continue
        rtype_match = rtype_re.match(line)
        if rtype_match:
            return_type = _normalise_space(rtype_match.group("desc"))
            continue
        param_match = param_re.match(line)
        if param_match:
            pending_params[param_match.group("name")] = (
                _normalise_space(param_match.group("desc")),
                base_line + offset,
                raw_line,
            )
            continue
        returns_match = returns_re.match(line)
        if returns_match:
            pending_return = (_normalise_space(returns_match.group("desc")), base_line + offset, raw_line)
            continue
        raises_match = raises_re.match(line)
        if raises_match:
            tags.append(
                DocTag(
                    "raises",
                    raises_match.group("name"),
                    _normalise_space(raises_match.group("desc")),
                    base_line + offset,
                    raw_line,
                )
            )

    for name, (description, line_number, raw_line) in pending_params.items():
        type_text = param_types.get(name)
        if type_text:
            description = f"{description} Type: {type_text}".strip()
        tags.append(DocTag("param", name, description, line_number, raw_line))

    if pending_return is not None:
        description, line_number, raw_line = pending_return
        if return_type:
            description = f"{description} Type: {return_type}".strip()
        tags.append(DocTag("returns", "return", description, line_number, raw_line))

    return tags


def _is_google_section_header(line: str) -> str | None:
    """Return a normalized section name for Google/Numpy-style headers."""

    stripped = line.strip().rstrip(":").lower()
    aliases = {
        "args": "param",
        "arguments": "param",
        "parameters": "param",
        "params": "param",
        "returns": "returns",
        "return": "returns",
        "raises": "raises",
        "raise": "raises",
        "yields": "yields",
        "yield": "yields",
    }
    return aliases.get(stripped)


def _parse_google_item(section_kind: str, text: str, line_number: int) -> DocTag | None:
    """Parse one item from a Google/Numpy-style docstring section."""

    cleaned = _normalise_space(text)
    if not cleaned:
        return None

    if section_kind == "param":
        match = re.match(
            r"^(?P<name>[A-Za-z_][\w]*)(?:\s*\((?P<type>[^)]*)\))?\s*:\s*(?P<desc>.*)$",
            cleaned,
        )
        if match:
            name = match.group("name")
            desc = match.group("desc")
            type_text = match.group("type")
            if type_text:
                desc = f"{desc} Type: {type_text}".strip()
            return DocTag("param", name, desc, line_number, text)
        simple = re.match(r"^(?P<name>[A-Za-z_][\w]*)\s+-\s+(?P<desc>.*)$", cleaned)
        if simple:
            return DocTag("param", simple.group("name"), simple.group("desc"), line_number, text)
        return None

    if section_kind in {"returns", "yields"}:
        match = re.match(r"^(?P<type>[^:]+)\s*:\s*(?P<desc>.*)$", cleaned)
        if match:
            desc = f"{match.group('desc')} Type: {match.group('type').strip()}".strip()
            return DocTag(section_kind, section_kind[:-1] if section_kind.endswith("s") else section_kind, desc, line_number, text)
        return DocTag(section_kind, section_kind[:-1] if section_kind.endswith("s") else section_kind, cleaned, line_number, text)

    if section_kind == "raises":
        match = re.match(r"^(?P<name>[A-Za-z_][\w.]*)\s*:\s*(?P<desc>.*)$", cleaned)
        if match:
            return DocTag("raises", match.group("name"), match.group("desc"), line_number, text)
        simple = re.match(r"^(?P<name>[A-Za-z_][\w.]*)\s+-\s+(?P<desc>.*)$", cleaned)
        if simple:
            return DocTag("raises", simple.group("name"), simple.group("desc"), line_number, text)
        return DocTag("raises", cleaned.split()[0], cleaned, line_number, text)

    return None


def _parse_google_sections(lines: list[str], base_line: int) -> list[DocTag]:
    """Parse Google/Numpy-style docstring sections."""

    tags: list[DocTag] = []
    active_kind: str | None = None
    active_items: list[tuple[str, int]] = []

    def flush_items() -> None:
        nonlocal active_items
        if active_kind is None:
            active_items = []
            return
        for text, line_number in active_items:
            item = _parse_google_item(active_kind, text, line_number)
            if item is not None:
                tags.append(item)
        active_items = []

    for offset, raw_line in enumerate(lines):
        current_line_number = base_line + offset
        stripped = raw_line.strip()
        section = _is_google_section_header(stripped)
        if section is not None:
            flush_items()
            active_kind = section
            continue
        if active_kind is None:
            continue
        if not stripped:
            continue
        if raw_line.startswith((" ", "\t")) or active_kind in {"returns", "yields", "raises"}:
            if active_items and raw_line.startswith(("    ", "\t")) and not re.match(r"^\s*[A-Za-z_][\w.]*\s*(\([^)]*\))?\s*[:\-]", raw_line):
                previous_text, previous_line = active_items[-1]
                active_items[-1] = (f"{previous_text} {stripped}", previous_line)
            else:
                active_items.append((stripped, current_line_number))

    flush_items()
    return tags


def inspectable_docstring(docstring: str | None) -> str:
    """Normalize a raw docstring into text suitable for line-based parsing."""

    if not docstring:
        return ""
    lines = docstring.expandtabs().splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""
    indentation = min((len(line) - len(line.lstrip())) for line in lines[1:] if line.strip()) if len(lines) > 1 else 0
    normalized = [lines[0].strip()]
    for line in lines[1:]:
        normalized.append(line[indentation:].rstrip() if indentation else line.rstrip())
    return "\n".join(normalized)


def parse_doc_tags(docstring: str | None, base_line: int) -> list[DocTag]:
    """Parse supported structured docstring tags.

    The parser intentionally returns only deterministic structured items. Free
    prose remains handled by the existing rationale/docstring extraction path.
    """

    cleaned = inspectable_docstring(docstring)
    if not cleaned:
        return []
    lines = cleaned.splitlines()
    tags = _parse_restructured_tags(lines, base_line)
    tags.extend(_parse_google_sections(lines, base_line))

    unique: dict[tuple[str, str, int], DocTag] = {}
    for tag in tags:
        unique[(tag.kind, tag.name, tag.line)] = tag
    return list(unique.values())


def _iter_documented_python_objects(
    tree: ast.Module,
    path: Path,
    make_id: MakeId,
    file_stem: FileStem,
) -> Iterable[tuple[str, str, str, int]]:
    """Yield ``(owner_node_id, owner_kind, docstring, doc_line)`` tuples.

    The node IDs mirror the existing IDs emitted by ``graphify.extract``:
    module file node, top-level functions, classes, and class methods.
    """

    stem = file_stem(path)
    file_nid = make_id(str(path))
    module_doc = ast.get_docstring(tree)
    if module_doc:
        yield file_nid, "module", module_doc, _docstring_start_line(tree)

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_nid = make_id(stem, node.name)
            class_doc = ast.get_docstring(node)
            if class_doc:
                yield class_nid, "class", class_doc, _docstring_start_line(node)
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_doc = ast.get_docstring(child)
                    if method_doc:
                        yield make_id(class_nid, child.name), "method", method_doc, _docstring_start_line(child)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_doc = ast.get_docstring(node)
            if function_doc:
                yield make_id(stem, node.name), "function", function_doc, _docstring_start_line(node)


def _tag_label(tag: DocTag) -> str:
    """Return a compact human-readable label for a doc tag node."""

    description = _normalise_space(tag.description)
    if description:
        return f"{tag.kind} {tag.name}: {description}"[:160]
    return f"{tag.kind} {tag.name}"[:160]


def _tag_relation(tag: DocTag) -> str:
    """Return the specific owner-to-tag relation for a doc tag."""

    if tag.kind == "param":
        return "documents_parameter"
    if tag.kind == "returns":
        return "documents_return"
    if tag.kind == "yields":
        return "documents_yield"
    if tag.kind == "raises":
        return "documents_exception"
    return "documents"


def enrich_python_doc_tags(
    path: Path,
    result: dict[str, Any],
    *,
    make_id: MakeId,
    file_stem: FileStem,
) -> None:
    """Append deterministic Python doc-tag nodes and edges to an extraction result.

    This function mutates ``result`` in-place, matching the existing style used by
    ``_extract_python_rationale`` in ``graphify.extract``.
    """

    try:
        source_text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return

    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return

    nodes = result.setdefault("nodes", [])
    edges = result.setdefault("edges", [])
    existing_ids = {node.get("id", "") for node in nodes}
    existing_edges: set[tuple[str, str, str, str | None]] = {
        (
            edge.get("source", ""),
            edge.get("target", ""),
            edge.get("relation", ""),
            edge.get("source_location"),
        )
        for edge in edges
    }
    source_file = str(path)

    for owner_nid, owner_kind, docstring, doc_line in _iter_documented_python_objects(tree, path, make_id, file_stem):
        if owner_nid not in existing_ids:
            continue
        tags = parse_doc_tags(docstring, doc_line)
        for index, tag in enumerate(tags, start=1):
            tag_id = make_id(owner_nid, "doc", tag.kind, tag.name, str(tag.line), str(index))
            tag_node = make_fact_node(
                node_id=tag_id,
                label=_tag_label(tag),
                file_type="doc_tag",
                source_file=source_file,
                source_location=f"L{tag.line}",
                metadata={
                    "doc_kind": tag.kind,
                    "doc_name": tag.name,
                    "doc_description": tag.description,
                    "owner_kind": owner_kind,
                    "owner_id": owner_nid,
                    "raw": tag.raw,
                },
            )
            append_unique_node(nodes, existing_ids, tag_node)

            append_unique_edge(
                edges,
                existing_edges,
                {
                    "source": tag_id,
                    "target": owner_nid,
                    "relation": "documents",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": source_file,
                    "source_location": f"L{tag.line}",
                    "weight": 1.0,
                    "context": "docstring_tag",
                },
            )
            append_unique_edge(
                edges,
                existing_edges,
                {
                    "source": owner_nid,
                    "target": tag_id,
                    "relation": _tag_relation(tag),
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": source_file,
                    "source_location": f"L{tag.line}",
                    "weight": 1.0,
                    "context": "docstring_tag",
                },
            )
