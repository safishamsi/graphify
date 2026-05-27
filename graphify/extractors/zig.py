from .core import *
from pathlib import Path
from typing import Any


# ── Zig ───────────────────────────────────────────────────────────────────────

def extract_zig(path: Path) -> dict:
    """Extract functions, structs, enums, unions, and imports from a .zig file."""
    try:
        import tree_sitter_zig as tszig
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_zig not installed"}

    try:
        language = Language(tszig.language())
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

    def _extract_import(node) -> None:
        for child in node.children:
            if child.type == "builtin_function":
                bi = None
                args = None
                for c in child.children:
                    if c.type == "builtin_identifier":
                        bi = _read_text(c, source)
                    elif c.type == "arguments":
                        args = c
                if bi in ("@import", "@cImport") and args:
                    for arg in args.children:
                        if arg.type in ("string_literal", "string"):
                            raw = _read_text(arg, source).strip('"')
                            module_name = raw.split("/")[-1].split(".")[0]
                            if module_name:
                                tgt_nid = _make_id(module_name)
                                add_edge(file_nid, tgt_nid, "imports_from",
                                         node.start_point[0] + 1)
                            return
            elif child.type == "field_expression":
                _extract_import(child)
                return

    def walk(node, parent_struct_nid: str | None = None) -> None:
        t = node.type

        if t == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                if parent_struct_nid:
                    func_nid = _make_id(parent_struct_nid, func_name)
                    add_node(func_nid, f".{func_name}()", line)
                    add_edge(parent_struct_nid, func_nid, "method", line)
                else:
                    func_nid = _make_id(stem, func_name)
                    add_node(func_nid, f"{func_name}()", line)
                    add_edge(file_nid, func_nid, "contains", line)
                body = node.child_by_field_name("body")
                if body:
                    function_bodies.append((func_nid, body))
            return

        if t == "variable_declaration":
            name_node = None
            value_node = None
            for child in node.children:
                if child.type == "identifier":
                    name_node = child
                elif child.type in ("struct_declaration", "enum_declaration",
                                    "union_declaration", "builtin_function",
                                    "field_expression"):
                    value_node = child

            if value_node and value_node.type == "struct_declaration":
                if name_node:
                    struct_name = _read_text(name_node, source)
                    line = node.start_point[0] + 1
                    struct_nid = _make_id(stem, struct_name)
                    add_node(struct_nid, struct_name, line)
                    add_edge(file_nid, struct_nid, "contains", line)
                    for child in value_node.children:
                        walk(child, parent_struct_nid=struct_nid)
                return

            if value_node and value_node.type in ("enum_declaration", "union_declaration"):
                if name_node:
                    type_name = _read_text(name_node, source)
                    line = node.start_point[0] + 1
                    type_nid = _make_id(stem, type_name)
                    add_node(type_nid, type_name, line)
                    add_edge(file_nid, type_nid, "contains", line)
                return

            if value_node and value_node.type in ("builtin_function", "field_expression"):
                _extract_import(node)
            return

        for child in node.children:
            walk(child, parent_struct_nid)

    walk(root)

    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []

    def walk_calls(node, caller_nid: str) -> None:
        if node.type == "function_declaration":
            return
        if node.type == "call_expression":
            fn = node.child_by_field_name("function")
            if fn:
                fn_text = _read_text(fn, source)
                callee = fn_text.split(".")[-1]
                is_member_call = "." in fn_text
                tgt_nid = next((n["id"] for n in nodes if n["label"] in
                                (f"{callee}()", f".{callee}()")), None)
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        add_edge(caller_nid, tgt_nid, "calls",
                                 node.start_point[0] + 1,
                                 confidence="EXTRACTED", weight=1.0)
                elif callee:
                    raw_calls.append({
                        "caller_nid": caller_nid,
                        "callee": callee,
                        "is_member_call": is_member_call,
                        "source_file": str_path,
                        "source_location": f"L{node.start_point[0] + 1}",
                    })
        for child in node.children:
            walk_calls(child, caller_nid)

    for caller_nid, body_node in function_bodies:
        walk_calls(body_node, caller_nid)

    clean_edges = [e for e in edges if e["source"] in seen_ids and
                   (e["target"] in seen_ids or e["relation"] == "imports_from")]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}


__all__ = ['extract_zig']
