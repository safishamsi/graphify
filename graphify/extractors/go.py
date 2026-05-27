from .core import *
from pathlib import Path


# ── Go extractor (custom walk) ────────────────────────────────────────────────

def extract_go(path: Path) -> dict:
    """Extract functions, methods, type declarations, and imports from a .go file."""
    try:
        import tree_sitter_go as tsgo
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-go not installed"}

    try:
        language = Language(tsgo.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    # Use directory name as package scope so methods on the same type across
    # multiple files in a package share one canonical type node.
    pkg_scope = path.parent.name or stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    function_bodies: list[tuple[str, object]] = []
    go_imported_pkgs: set[str] = set()  # local names of imported packages

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            })

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None) -> None:
        edge = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def walk(node) -> None:
        t = node.type

        if t == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                func_nid = _make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(file_nid, func_nid, "contains", line)
                body = node.child_by_field_name("body")
                if body:
                    function_bodies.append((func_nid, body))
            return

        if t == "method_declaration":
            receiver = node.child_by_field_name("receiver")
            receiver_type: str | None = None
            if receiver:
                for param in receiver.children:
                    if param.type == "parameter_declaration":
                        type_node = param.child_by_field_name("type")
                        if type_node:
                            raw = _read_text(type_node, source).lstrip("*").strip()
                            receiver_type = raw
                        break
            name_node = node.child_by_field_name("name")
            if name_node:
                method_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                if receiver_type:
                    parent_nid = _make_id(pkg_scope, receiver_type)
                    add_node(parent_nid, receiver_type, line)
                    method_nid = _make_id(parent_nid, method_name)
                    add_node(method_nid, f".{method_name}()", line)
                    add_edge(parent_nid, method_nid, "method", line)
                else:
                    method_nid = _make_id(stem, method_name)
                    add_node(method_nid, f"{method_name}()", line)
                    add_edge(file_nid, method_nid, "contains", line)
                body = node.child_by_field_name("body")
                if body:
                    function_bodies.append((method_nid, body))
            return

        if t == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        type_name = _read_text(name_node, source)
                        line = child.start_point[0] + 1
                        type_nid = _make_id(pkg_scope, type_name)
                        add_node(type_nid, type_name, line)
                        add_edge(file_nid, type_nid, "contains", line)
            return

        if t == "import_declaration":
            for child in node.children:
                if child.type == "import_spec_list":
                    for spec in child.children:
                        if spec.type == "import_spec":
                            path_node = spec.child_by_field_name("path")
                            if path_node:
                                raw = _read_text(path_node, source).strip('"')
                                # Prefix with go_pkg_ so stdlib names (e.g. "context")
                                # don't collide with local files of the same basename.
                                tgt_nid = _make_id("go", "pkg", raw)
                                add_edge(file_nid, tgt_nid, "imports_from", spec.start_point[0] + 1, context="import")
                                # Track local name (alias or last path segment)
                                alias = spec.child_by_field_name("name")
                                local_name = _read_text(alias, source) if alias else raw.split("/")[-1]
                                if local_name and local_name != "_" and local_name != ".":
                                    go_imported_pkgs.add(local_name)
                elif child.type == "import_spec":
                    path_node = child.child_by_field_name("path")
                    if path_node:
                        raw = _read_text(path_node, source).strip('"')
                        tgt_nid = _make_id("go", "pkg", raw)
                        add_edge(file_nid, tgt_nid, "imports_from", child.start_point[0] + 1, context="import")
                        alias = child.child_by_field_name("name")
                        local_name = _read_text(alias, source) if alias else raw.split("/")[-1]
                        if local_name and local_name != "_" and local_name != ".":
                            go_imported_pkgs.add(local_name)
            return

        for child in node.children:
            walk(child)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []

    def walk_calls(node, caller_nid: str) -> None:
        if node.type in ("function_declaration", "method_declaration"):
            return
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            callee_name: str | None = None
            is_member_call: bool = False
            if func_node:
                if func_node.type == "identifier":
                    callee_name = _read_text(func_node, source)
                elif func_node.type == "selector_expression":
                    field = func_node.child_by_field_name("field")
                    operand = func_node.child_by_field_name("operand")
                    receiver_name = _read_text(operand, source) if operand else ""
                    # Package-qualified call (e.g. fmt.Println) → allow cross-file resolution.
                    # Receiver method call (e.g. s.logger.Log) → skip, no import evidence.
                    is_member_call = receiver_name not in go_imported_pkgs
                    if field:
                        callee_name = _read_text(field, source)
            if callee_name:
                tgt_nid = label_to_nid.get(callee_name)
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "context": "call",
                            "confidence": "EXTRACTED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 1.0,
                        })
                elif callee_name:
                    raw_calls.append({
                        "caller_nid": caller_nid,
                        "callee": callee_name,
                        "is_member_call": is_member_call,
                        "source_file": str_path,
                        "source_location": f"L{node.start_point[0] + 1}",
                    })
        for child in node.children:
            walk_calls(child, caller_nid)

    for caller_nid, body_node in function_bodies:
        walk_calls(body_node, caller_nid)

    valid_ids = seen_ids
    clean_edges = []
    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        if src in valid_ids and (tgt in valid_ids or edge["relation"] in ("imports", "imports_from")):
            clean_edges.append(edge)

    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}


__all__ = ['extract_go']
