"""Deterministic structural extraction from Python code using tree-sitter. Outputs nodes+edges dicts."""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from .cache import load_cached, save_cached


def _make_id(*parts: str) -> str:
    """Build a stable node ID from one or more name parts."""
    combined = "_".join(p.strip("_.") for p in parts if p)
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", combined)
    return cleaned.strip("_").lower()


def extract_python(path: Path) -> dict:
    """Extract classes, functions, and imports from a .py file via tree-sitter AST."""
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-python not installed"}

    try:
        language = Language(tspython.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, node_type: str | None = None, modifiers: list | None = None) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            entry: dict = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            }
            if node_type is not None:
                entry["node_type"] = node_type
            if modifiers:
                entry["modifiers"] = modifiers
            nodes.append(entry)

    def add_edge(src: str, tgt: str, relation: str, line: int) -> None:
        # Only add edge if both endpoints exist or src is the file node
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        })

    # File-level node - stable ID based on stem only
    file_nid = _make_id(stem)
    add_node(file_nid, path.name, 1)

    def walk(node, parent_class_nid: str | None = None) -> None:
        t = node.type

        if t == "import_statement":
            for child in node.children:
                if child.type in ("dotted_name", "aliased_import"):
                    raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                    module_name = raw.split(" as ")[0].strip().lstrip(".")
                    tgt_nid = _make_id(module_name)
                    add_edge(file_nid, tgt_nid, "imports", node.start_point[0] + 1)
            return

        if t == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            if module_node:
                raw = source[module_node.start_byte:module_node.end_byte].decode("utf-8", errors="replace").lstrip(".")
                tgt_nid = _make_id(raw)
                add_edge(file_nid, tgt_nid, "imports_from", node.start_point[0] + 1)
            return

        if t == "class_definition":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            class_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            class_nid = _make_id(stem, class_name)
            line = node.start_point[0] + 1
            add_node(class_nid, class_name, line, node_type="class")
            add_edge(file_nid, class_nid, "contains", line)

            # Inheritance - create stub node for external bases so the edge is never dropped
            args = node.child_by_field_name("superclasses")
            if args:
                for arg in args.children:
                    if arg.type == "identifier":
                        base = source[arg.start_byte:arg.end_byte].decode("utf-8", errors="replace")
                        # Try same-file base first; fall back to a bare stub
                        base_nid = _make_id(stem, base)
                        if base_nid not in seen_ids:
                            # External or forward-declared base - add a stub so edge survives
                            base_nid = _make_id(base)
                            if base_nid not in seen_ids:
                                nodes.append({
                                    "id": base_nid,
                                    "label": base,
                                    "file_type": "code",
                                    "source_file": "",
                                    "source_location": "",
                                })
                                seen_ids.add(base_nid)
                        add_edge(class_nid, base_nid, "inherits", line)

            # Walk class body for methods
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    walk(child, parent_class_nid=class_nid)
            return

        if t == "function_definition":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            func_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            line = node.start_point[0] + 1
            if parent_class_nid:
                func_nid = _make_id(parent_class_nid, func_name)
                add_node(func_nid, f".{func_name}()", line, node_type="method")
                add_edge(parent_class_nid, func_nid, "method", line)
            else:
                func_nid = _make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line, node_type="function")
                add_edge(file_nid, func_nid, "contains", line)
            # Collect body for the call-graph pass below
            body = node.child_by_field_name("body")
            if body:
                function_bodies.append((func_nid, body))
            return

        for child in node.children:
            walk(child, parent_class_nid=None)

    function_bodies: list[tuple[str, object]] = []
    walk(root)

    # ── Call-graph pass ───────────────────────────────────────────────────────
    # Build label→nid lookup from all nodes collected above.
    # Normalise: strip "()" suffix and leading "." so "cohesion_score()" and
    # ".cohesion_score()" both map to the same entry.
    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()

    def walk_calls(node, caller_nid: str) -> None:
        # Don't recurse into nested function definitions - they have their own context.
        if node.type == "function_definition":
            return
        if node.type == "call":
            func_node = node.child_by_field_name("function")
            callee_name: str | None = None
            if func_node:
                if func_node.type == "identifier":
                    callee_name = source[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="replace")
                elif func_node.type == "attribute":
                    attr = func_node.child_by_field_name("attribute")
                    if attr:
                        callee_name = source[attr.start_byte:attr.end_byte].decode("utf-8", errors="replace")
            if callee_name:
                tgt_nid = label_to_nid.get(callee_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "confidence": "INFERRED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 0.8,
                        })
        for child in node.children:
            walk_calls(child, caller_nid)

    for caller_nid, body_node in function_bodies:
        walk_calls(body_node, caller_nid)
    # ─────────────────────────────────────────────────────────────────────────

    # Post-process: remove edges whose source or target was never added as a node
    # (dangling import edges pointing to external libraries are fine to keep,
    #  but edges between internal entities must be valid)
    valid_ids = seen_ids
    clean_edges = []
    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        # Keep if both endpoints are known, OR if it's an import edge (tgt may be external)
        if src in valid_ids and (tgt in valid_ids or edge["relation"] in ("imports", "imports_from")):
            clean_edges.append(edge)

    return {"nodes": nodes, "edges": clean_edges}


def extract_js(path: Path) -> dict:
    """Extract classes, functions, arrow functions, and imports from a .js/.ts/.tsx file."""
    try:
        if path.suffix in (".ts", ".tsx"):
            import tree_sitter_typescript as tslang
            from tree_sitter import Language, Parser
            language = Language(tslang.language_typescript())
        else:
            import tree_sitter_javascript as tslang
            from tree_sitter import Language, Parser
            language = Language(tslang.language())
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-javascript/typescript not installed"}

    try:
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, node_type: str | None = None, modifiers: list | None = None) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            entry: dict = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            }
            if node_type is not None:
                entry["node_type"] = node_type
            if modifiers:
                entry["modifiers"] = modifiers
            nodes.append(entry)

    def add_edge(src: str, tgt: str, relation: str, line: int, confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        })

    file_nid = _make_id(stem)
    add_node(file_nid, path.name, 1)

    function_bodies: list[tuple[str, object]] = []

    def walk(node, parent_class_nid: str | None = None) -> None:
        t = node.type

        if t == "import_statement":
            for child in node.children:
                if child.type == "string":
                    raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace").strip("'\"` ")
                    module_name = raw.lstrip("./").split("/")[-1]
                    if module_name:
                        tgt_nid = _make_id(module_name)
                        add_edge(file_nid, tgt_nid, "imports_from", node.start_point[0] + 1)
            return

        if t == "class_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            class_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            class_nid = _make_id(stem, class_name)
            line = node.start_point[0] + 1
            _js_mods: list[str] = ["export"] if node.parent and node.parent.type == "export_statement" else []
            for _c in node.children:
                if _c.type == "abstract":
                    _js_mods.append("abstract")
            add_node(class_nid, class_name, line, node_type="class", modifiers=_js_mods or None)
            add_edge(file_nid, class_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    walk(child, parent_class_nid=class_nid)
            return

        if t == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            iface_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            iface_nid = _make_id(stem, iface_name)
            line = node.start_point[0] + 1
            _js_mods = ["export"] if node.parent and node.parent.type == "export_statement" else []
            add_node(iface_nid, iface_name, line, node_type="interface", modifiers=_js_mods or None)
            add_edge(file_nid, iface_nid, "contains", line)
            return

        if t == "function_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            func_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            line = node.start_point[0] + 1
            func_nid = _make_id(stem, func_name)
            _js_mods = ["export"] if node.parent and node.parent.type == "export_statement" else []
            for _c in node.children:
                if _c.type == "async":
                    _js_mods.append("async")
            add_node(func_nid, f"{func_name}()", line, node_type="function", modifiers=_js_mods or None)
            add_edge(file_nid, func_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body:
                function_bodies.append((func_nid, body))
            return

        if t == "method_definition" and parent_class_nid:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            method_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            line = node.start_point[0] + 1
            method_nid = _make_id(parent_class_nid, method_name)
            _js_mods = []
            for _c in node.children:
                if _c.type in ("static", "async", "abstract"):
                    _js_mods.append(_c.type)
                elif _c.type == "accessibility_modifier":
                    _js_mods.append(source[_c.start_byte:_c.end_byte].decode("utf-8", errors="replace"))
            add_node(method_nid, f".{method_name}()", line, node_type="method", modifiers=_js_mods or None)
            add_edge(parent_class_nid, method_nid, "method", line)
            body = node.child_by_field_name("body")
            if body:
                function_bodies.append((method_nid, body))
            return

        if t == "lexical_declaration":
            # Arrow functions: const foo = (...) => { ... }
            for child in node.children:
                if child.type == "variable_declarator":
                    value = child.child_by_field_name("value")
                    if value and value.type == "arrow_function":
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            func_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                            line = child.start_point[0] + 1
                            func_nid = _make_id(stem, func_name)
                            _js_arrow_mods = ["export"] if node.parent and node.parent.type == "export_statement" else []
                            add_node(func_nid, f"{func_name}()", line, node_type="function", modifiers=_js_arrow_mods or None)
                            add_edge(file_nid, func_nid, "contains", line)
                            body = value.child_by_field_name("body")
                            if body:
                                function_bodies.append((func_nid, body))
            return

        for child in node.children:
            walk(child, parent_class_nid=None)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()

    def walk_calls(node, caller_nid: str) -> None:
        if node.type in ("function_declaration", "arrow_function", "method_definition"):
            return
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            callee_name: str | None = None
            if func_node:
                if func_node.type == "identifier":
                    callee_name = source[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="replace")
                elif func_node.type == "member_expression":
                    prop = func_node.child_by_field_name("property")
                    if prop:
                        callee_name = source[prop.start_byte:prop.end_byte].decode("utf-8", errors="replace")
            if callee_name:
                tgt_nid = label_to_nid.get(callee_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "confidence": "INFERRED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 0.8,
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

    return {"nodes": nodes, "edges": clean_edges}


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

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, node_type: str | None = None, modifiers: list | None = None) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            entry: dict = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            }
            if node_type is not None:
                entry["node_type"] = node_type
            if modifiers:
                entry["modifiers"] = modifiers
            nodes.append(entry)

    def add_edge_raw(src: str, tgt: str, relation: str, line: int, confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        })

    file_nid = _make_id(stem)
    add_node(file_nid, path.name, 1)

    function_bodies: list[tuple[str, object]] = []

    def walk(node) -> None:
        t = node.type

        if t == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                line = node.start_point[0] + 1
                func_nid = _make_id(stem, func_name)
                _go_mods = ["export"] if func_name and func_name[0].isupper() else []
                add_node(func_nid, f"{func_name}()", line, node_type="function", modifiers=_go_mods or None)
                add_edge_raw(file_nid, func_nid, "contains", line)
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
                            raw = source[type_node.start_byte:type_node.end_byte].decode("utf-8", errors="replace").lstrip("*").strip()
                            receiver_type = raw
                        break
            name_node = node.child_by_field_name("name")
            if name_node:
                method_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                line = node.start_point[0] + 1
                _go_method_mods = ["export"] if method_name and method_name[0].isupper() else []
                if receiver_type:
                    parent_nid = _make_id(stem, receiver_type)
                    _go_recv_mods = ["export"] if receiver_type and receiver_type[0].isupper() else []
                    add_node(parent_nid, receiver_type, line, node_type="class", modifiers=_go_recv_mods or None)
                    method_nid = _make_id(parent_nid, method_name)
                    add_node(method_nid, f".{method_name}()", line, node_type="method", modifiers=_go_method_mods or None)
                    add_edge_raw(parent_nid, method_nid, "method", line)
                else:
                    method_nid = _make_id(stem, method_name)
                    add_node(method_nid, f"{method_name}()", line, node_type="method", modifiers=_go_method_mods or None)
                    add_edge_raw(file_nid, method_nid, "contains", line)
                body = node.child_by_field_name("body")
                if body:
                    function_bodies.append((method_nid, body))
            return

        if t == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        type_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                        line = child.start_point[0] + 1
                        type_nid = _make_id(stem, type_name)
                        _go_type_mods = ["export"] if type_name and type_name[0].isupper() else []
                        _go_body = child.child_by_field_name("type")
                        if _go_body and _go_body.type == "interface_type":
                            _go_node_type = "interface"
                        elif _go_body and _go_body.type == "struct_type":
                            _go_node_type = "class"
                        else:
                            _go_node_type = "type"
                        add_node(type_nid, type_name, line, node_type=_go_node_type, modifiers=_go_type_mods or None)
                        add_edge_raw(file_nid, type_nid, "contains", line)
            return

        if t == "import_declaration":
            for child in node.children:
                if child.type == "import_spec_list":
                    for spec in child.children:
                        if spec.type == "import_spec":
                            path_node = spec.child_by_field_name("path")
                            if path_node:
                                raw = source[path_node.start_byte:path_node.end_byte].decode("utf-8", errors="replace").strip('"')
                                module_name = raw.split("/")[-1]
                                tgt_nid = _make_id(module_name)
                                add_edge_raw(file_nid, tgt_nid, "imports_from", spec.start_point[0] + 1)
                elif child.type == "import_spec":
                    path_node = child.child_by_field_name("path")
                    if path_node:
                        raw = source[path_node.start_byte:path_node.end_byte].decode("utf-8", errors="replace").strip('"')
                        module_name = raw.split("/")[-1]
                        tgt_nid = _make_id(module_name)
                        add_edge_raw(file_nid, tgt_nid, "imports_from", child.start_point[0] + 1)
            return

        for child in node.children:
            walk(child)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()

    def walk_calls(node, caller_nid: str) -> None:
        if node.type in ("function_declaration", "method_declaration"):
            return
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            callee_name: str | None = None
            if func_node:
                if func_node.type == "identifier":
                    callee_name = source[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="replace")
                elif func_node.type == "selector_expression":
                    field = func_node.child_by_field_name("field")
                    if field:
                        callee_name = source[field.start_byte:field.end_byte].decode("utf-8", errors="replace")
            if callee_name:
                tgt_nid = label_to_nid.get(callee_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "confidence": "INFERRED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 0.8,
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

    return {"nodes": nodes, "edges": clean_edges}


def extract_rust(path: Path) -> dict:
    """Extract functions, structs, enums, traits, impl methods, and use declarations from a .rs file."""
    try:
        import tree_sitter_rust as tsrust
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-rust not installed"}

    try:
        language = Language(tsrust.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, node_type: str | None = None, modifiers: list | None = None) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            entry: dict = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            }
            if node_type is not None:
                entry["node_type"] = node_type
            if modifiers:
                entry["modifiers"] = modifiers
            nodes.append(entry)

    def add_edge(src: str, tgt: str, relation: str, line: int, confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        })

    file_nid = _make_id(stem)
    add_node(file_nid, path.name, 1)

    function_bodies: list[tuple[str, object]] = []

    def walk(node, parent_impl_nid: str | None = None) -> None:
        t = node.type

        if t == "function_item":
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                line = node.start_point[0] + 1
                _rs_mods: list[str] = []
                for _c in node.children:
                    if _c.type == "visibility_modifier":
                        _rs_mods.append("export")
                    elif _c.type == "async":
                        _rs_mods.append("async")
                if parent_impl_nid:
                    func_nid = _make_id(parent_impl_nid, func_name)
                    add_node(func_nid, f".{func_name}()", line, node_type="method", modifiers=_rs_mods or None)
                    add_edge(parent_impl_nid, func_nid, "method", line)
                else:
                    func_nid = _make_id(stem, func_name)
                    add_node(func_nid, f"{func_name}()", line, node_type="function", modifiers=_rs_mods or None)
                    add_edge(file_nid, func_nid, "contains", line)
                body = node.child_by_field_name("body")
                if body:
                    function_bodies.append((func_nid, body))
            return

        if t in ("struct_item", "enum_item", "trait_item"):
            name_node = node.child_by_field_name("name")
            if name_node:
                item_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                line = node.start_point[0] + 1
                item_nid = _make_id(stem, item_name)
                _rs_mods: list[str] = []
                for _c in node.children:
                    if _c.type == "visibility_modifier":
                        _rs_mods.append("export")
                _rs_node_type = "enum" if t == "enum_item" else ("interface" if t == "trait_item" else "class")
                add_node(item_nid, item_name, line, node_type=_rs_node_type, modifiers=_rs_mods or None)
                add_edge(file_nid, item_nid, "contains", line)
            return

        if t == "impl_item":
            type_node = node.child_by_field_name("type")
            impl_nid: str | None = None
            if type_node:
                type_name = source[type_node.start_byte:type_node.end_byte].decode("utf-8", errors="replace").strip()
                impl_nid = _make_id(stem, type_name)
                add_node(impl_nid, type_name, node.start_point[0] + 1)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    walk(child, parent_impl_nid=impl_nid)
            return

        if t == "use_declaration":
            arg = node.child_by_field_name("argument")
            if arg:
                raw = source[arg.start_byte:arg.end_byte].decode("utf-8", errors="replace")
                clean = raw.split("{")[0].rstrip(":").rstrip("*").rstrip(":")
                module_name = clean.split("::")[-1].strip()
                if module_name:
                    tgt_nid = _make_id(module_name)
                    add_edge(file_nid, tgt_nid, "imports_from", node.start_point[0] + 1)
            return

        for child in node.children:
            walk(child, parent_impl_nid=None)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()

    def walk_calls(node, caller_nid: str) -> None:
        if node.type == "function_item":
            return
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            callee_name: str | None = None
            if func_node:
                if func_node.type == "identifier":
                    callee_name = source[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="replace")
                elif func_node.type == "field_expression":
                    field = func_node.child_by_field_name("field")
                    if field:
                        callee_name = source[field.start_byte:field.end_byte].decode("utf-8", errors="replace")
                elif func_node.type == "scoped_identifier":
                    name = func_node.child_by_field_name("name")
                    if name:
                        callee_name = source[name.start_byte:name.end_byte].decode("utf-8", errors="replace")
            if callee_name:
                tgt_nid = label_to_nid.get(callee_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "confidence": "INFERRED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 0.8,
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

    return {"nodes": nodes, "edges": clean_edges}


def extract_java(path: Path) -> dict:
    """Extract classes, interfaces, methods, constructors, and imports from a .java file."""
    try:
        import tree_sitter_java as tsjava
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-java not installed"}

    try:
        language = Language(tsjava.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, node_type: str | None = None, modifiers: list | None = None) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            entry: dict = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            }
            if node_type is not None:
                entry["node_type"] = node_type
            if modifiers:
                entry["modifiers"] = modifiers
            nodes.append(entry)

    def add_edge_raw(src: str, tgt: str, relation: str, line: int, confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        })

    file_nid = _make_id(stem)
    add_node(file_nid, path.name, 1)

    function_bodies: list[tuple[str, object]] = []

    def _walk_scoped_identifier(node) -> str:
        """Reconstruct a dotted import path from nested scoped_identifier nodes."""
        parts: list[str] = []
        cur = node
        while cur:
            if cur.type == "scoped_identifier":
                name_node = cur.child_by_field_name("name")
                if name_node:
                    parts.append(source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace"))
                cur = cur.child_by_field_name("scope")
            elif cur.type == "identifier":
                parts.append(source[cur.start_byte:cur.end_byte].decode("utf-8", errors="replace"))
                break
            else:
                break
        parts.reverse()
        return ".".join(parts)

    def walk(node, parent_class_nid: str | None = None) -> None:
        t = node.type

        if t == "import_declaration":
            # Find scoped_identifier or identifier child
            for child in node.children:
                if child.type in ("scoped_identifier", "identifier"):
                    path_str = _walk_scoped_identifier(child)
                    module_name = path_str.split(".")[-1].strip("*").strip(".") or path_str.split(".")[-2]
                    if module_name:
                        tgt_nid = _make_id(module_name)
                        add_edge_raw(file_nid, tgt_nid, "imports", node.start_point[0] + 1)
                    break
            return

        if t in ("class_declaration", "interface_declaration"):
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            class_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            class_nid = _make_id(stem, class_name)
            line = node.start_point[0] + 1
            _java_mods: list[str] = []
            for _c in node.children:
                if _c.type == "modifiers":
                    for _m in _c.children:
                        if _m.type in ("public", "private", "protected", "abstract", "static", "final"):
                            _java_mods.append(_m.type)
            _java_node_type = "interface" if t == "interface_declaration" else "class"
            add_node(class_nid, class_name, line, node_type=_java_node_type, modifiers=_java_mods or None)
            add_edge_raw(file_nid, class_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    walk(child, parent_class_nid=class_nid)
            return

        if t in ("method_declaration", "constructor_declaration"):
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            method_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            line = node.start_point[0] + 1
            _java_mods: list[str] = []
            for _c in node.children:
                if _c.type == "modifiers":
                    for _m in _c.children:
                        if _m.type in ("public", "private", "protected", "abstract", "static", "final"):
                            _java_mods.append(_m.type)
            if parent_class_nid:
                method_nid = _make_id(parent_class_nid, method_name)
                add_node(method_nid, f".{method_name}()", line, node_type="method", modifiers=_java_mods or None)
                add_edge_raw(parent_class_nid, method_nid, "method", line)
            else:
                method_nid = _make_id(stem, method_name)
                add_node(method_nid, f"{method_name}()", line, node_type="method", modifiers=_java_mods or None)
                add_edge_raw(file_nid, method_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body:
                function_bodies.append((method_nid, body))
            return

        for child in node.children:
            walk(child, parent_class_nid=None)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()

    def walk_calls(node, caller_nid: str) -> None:
        if node.type in ("method_declaration", "constructor_declaration"):
            return
        if node.type == "method_invocation":
            name_node = node.child_by_field_name("name")
            callee_name: str | None = None
            if name_node:
                callee_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            if callee_name:
                tgt_nid = label_to_nid.get(callee_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "confidence": "INFERRED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 0.8,
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

    return {"nodes": nodes, "edges": clean_edges}


def extract_c(path: Path) -> dict:
    """Extract functions and includes from a .c/.h file."""
    try:
        import tree_sitter_c as tsc
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-c not installed"}

    try:
        language = Language(tsc.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, node_type: str | None = None, modifiers: list | None = None) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            entry: dict = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            }
            if node_type is not None:
                entry["node_type"] = node_type
            if modifiers:
                entry["modifiers"] = modifiers
            nodes.append(entry)

    def add_edge_raw(src: str, tgt: str, relation: str, line: int, confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        })

    file_nid = _make_id(stem)
    add_node(file_nid, path.name, 1)

    function_bodies: list[tuple[str, object]] = []

    def _get_func_name_from_declarator(node) -> str | None:
        """Recursively unwrap declarator to find the innermost identifier."""
        if node.type == "identifier":
            return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
        decl = node.child_by_field_name("declarator")
        if decl:
            return _get_func_name_from_declarator(decl)
        # fallback: search children for identifier
        for child in node.children:
            if child.type == "identifier":
                return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
        return None

    def walk(node) -> None:
        t = node.type

        if t == "preproc_include":
            # path child or string child
            for child in node.children:
                if child.type in ("string_literal", "system_lib_string", "string"):
                    raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace").strip('"<> ')
                    module_name = raw.split("/")[-1].split(".")[0]
                    if module_name:
                        tgt_nid = _make_id(module_name)
                        add_edge_raw(file_nid, tgt_nid, "imports", node.start_point[0] + 1)
                    break
            return

        if t == "function_definition":
            declarator = node.child_by_field_name("declarator")
            func_name: str | None = None
            if declarator:
                func_name = _get_func_name_from_declarator(declarator)
            if func_name:
                line = node.start_point[0] + 1
                func_nid = _make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge_raw(file_nid, func_nid, "contains", line)
                body = node.child_by_field_name("body")
                if body:
                    function_bodies.append((func_nid, body))
            return

        for child in node.children:
            walk(child)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()

    def walk_calls(node, caller_nid: str) -> None:
        if node.type == "function_definition":
            return
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            callee_name: str | None = None
            if func_node:
                if func_node.type == "identifier":
                    callee_name = source[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="replace")
                elif func_node.type == "field_expression":
                    field = func_node.child_by_field_name("field")
                    if field:
                        callee_name = source[field.start_byte:field.end_byte].decode("utf-8", errors="replace")
            if callee_name:
                tgt_nid = label_to_nid.get(callee_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "confidence": "INFERRED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 0.8,
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

    return {"nodes": nodes, "edges": clean_edges}


def extract_cpp(path: Path) -> dict:
    """Extract functions, classes, and includes from a .cpp/.cc/.cxx/.hpp file."""
    try:
        import tree_sitter_cpp as tscpp
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-cpp not installed"}

    try:
        language = Language(tscpp.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, node_type: str | None = None, modifiers: list | None = None) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            entry: dict = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            }
            if node_type is not None:
                entry["node_type"] = node_type
            if modifiers:
                entry["modifiers"] = modifiers
            nodes.append(entry)

    def add_edge_raw(src: str, tgt: str, relation: str, line: int, confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        })

    file_nid = _make_id(stem)
    add_node(file_nid, path.name, 1)

    function_bodies: list[tuple[str, object]] = []

    def _get_func_name_from_declarator(node) -> str | None:
        """Recursively unwrap declarator to find the innermost identifier."""
        if node.type == "identifier":
            return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
        if node.type == "qualified_identifier":
            name_node = node.child_by_field_name("name")
            if name_node:
                return source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
        decl = node.child_by_field_name("declarator")
        if decl:
            return _get_func_name_from_declarator(decl)
        for child in node.children:
            if child.type == "identifier":
                return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
        return None

    def walk(node, parent_class_nid: str | None = None) -> None:
        t = node.type

        if t == "preproc_include":
            for child in node.children:
                if child.type in ("string_literal", "system_lib_string", "string"):
                    raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace").strip('"<> ')
                    module_name = raw.split("/")[-1].split(".")[0]
                    if module_name:
                        tgt_nid = _make_id(module_name)
                        add_edge_raw(file_nid, tgt_nid, "imports", node.start_point[0] + 1)
                    break
            return

        if t == "class_specifier":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            class_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            class_nid = _make_id(stem, class_name)
            line = node.start_point[0] + 1
            add_node(class_nid, class_name, line)
            add_edge_raw(file_nid, class_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    walk(child, parent_class_nid=class_nid)
            return

        if t == "function_definition":
            declarator = node.child_by_field_name("declarator")
            func_name: str | None = None
            if declarator:
                func_name = _get_func_name_from_declarator(declarator)
            if func_name:
                line = node.start_point[0] + 1
                if parent_class_nid:
                    func_nid = _make_id(parent_class_nid, func_name)
                    add_node(func_nid, f".{func_name}()", line)
                    add_edge_raw(parent_class_nid, func_nid, "method", line)
                else:
                    func_nid = _make_id(stem, func_name)
                    add_node(func_nid, f"{func_name}()", line)
                    add_edge_raw(file_nid, func_nid, "contains", line)
                body = node.child_by_field_name("body")
                if body:
                    function_bodies.append((func_nid, body))
            return

        for child in node.children:
            walk(child, parent_class_nid=None)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()

    def walk_calls(node, caller_nid: str) -> None:
        if node.type == "function_definition":
            return
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            callee_name: str | None = None
            if func_node:
                if func_node.type == "identifier":
                    callee_name = source[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="replace")
                elif func_node.type in ("field_expression", "qualified_identifier"):
                    name = func_node.child_by_field_name("field") or func_node.child_by_field_name("name")
                    if name:
                        callee_name = source[name.start_byte:name.end_byte].decode("utf-8", errors="replace")
            if callee_name:
                tgt_nid = label_to_nid.get(callee_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "confidence": "INFERRED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 0.8,
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

    return {"nodes": nodes, "edges": clean_edges}


def extract_ruby(path: Path) -> dict:
    """Extract classes, methods, singleton methods, and calls from a .rb file."""
    try:
        import tree_sitter_ruby as tsruby
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-ruby not installed"}

    try:
        language = Language(tsruby.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, node_type: str | None = None, modifiers: list | None = None) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            entry: dict = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            }
            if node_type is not None:
                entry["node_type"] = node_type
            if modifiers:
                entry["modifiers"] = modifiers
            nodes.append(entry)

    def add_edge_raw(src: str, tgt: str, relation: str, line: int, confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        })

    file_nid = _make_id(stem)
    add_node(file_nid, path.name, 1)

    function_bodies: list[tuple[str, object]] = []

    def walk(node, parent_class_nid: str | None = None) -> None:
        t = node.type

        if t == "class":
            # name is a child node (not a field in all versions)
            name_node = node.child_by_field_name("name")
            if name_node is None:
                for child in node.children:
                    if child.type in ("constant", "scope_resolution"):
                        name_node = child
                        break
            if not name_node:
                return
            class_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            class_nid = _make_id(stem, class_name)
            line = node.start_point[0] + 1
            add_node(class_nid, class_name, line)
            add_edge_raw(file_nid, class_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body is None:
                # body may not be a named field - walk all children except first/last
                for child in node.children:
                    if child.type == "body_statement":
                        body = child
                        break
            if body:
                for child in body.children:
                    walk(child, parent_class_nid=class_nid)
            return

        if t in ("method", "singleton_method"):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                for child in node.children:
                    if child.type == "identifier":
                        name_node = child
                        break
            if not name_node:
                return
            method_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            line = node.start_point[0] + 1
            if parent_class_nid:
                method_nid = _make_id(parent_class_nid, method_name)
                add_node(method_nid, f".{method_name}()", line)
                add_edge_raw(parent_class_nid, method_nid, "method", line)
            else:
                method_nid = _make_id(stem, method_name)
                add_node(method_nid, f"{method_name}()", line)
                add_edge_raw(file_nid, method_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body is None:
                for child in node.children:
                    if child.type == "body_statement":
                        body = child
                        break
            if body:
                function_bodies.append((method_nid, body))
            return

        for child in node.children:
            walk(child, parent_class_nid=None)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()

    def walk_calls(node, caller_nid: str) -> None:
        if node.type in ("method", "singleton_method"):
            return
        if node.type == "call":
            method_node = node.child_by_field_name("method")
            callee_name: str | None = None
            if method_node:
                callee_name = source[method_node.start_byte:method_node.end_byte].decode("utf-8", errors="replace")
            if callee_name:
                tgt_nid = label_to_nid.get(callee_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "confidence": "INFERRED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 0.8,
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

    return {"nodes": nodes, "edges": clean_edges}


def extract_csharp(path: Path) -> dict:
    """Extract classes, interfaces, methods, namespaces, and usings from a .cs file."""
    try:
        import tree_sitter_c_sharp as tscsharp
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-c-sharp not installed"}

    try:
        language = Language(tscsharp.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, node_type: str | None = None, modifiers: list | None = None) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            entry: dict = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            }
            if node_type is not None:
                entry["node_type"] = node_type
            if modifiers:
                entry["modifiers"] = modifiers
            nodes.append(entry)

    def add_edge_raw(src: str, tgt: str, relation: str, line: int, confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        })

    file_nid = _make_id(stem)
    add_node(file_nid, path.name, 1)

    function_bodies: list[tuple[str, object]] = []

    def walk(node, parent_class_nid: str | None = None) -> None:
        t = node.type

        if t == "using_directive":
            # Extract the namespace name from the using directive
            for child in node.children:
                if child.type in ("qualified_name", "identifier", "name_equals"):
                    raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                    module_name = raw.split(".")[-1].strip()
                    if module_name:
                        tgt_nid = _make_id(module_name)
                        add_edge_raw(file_nid, tgt_nid, "imports", node.start_point[0] + 1)
                    break
            return

        if t == "namespace_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                ns_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                ns_nid = _make_id(stem, ns_name)
                line = node.start_point[0] + 1
                add_node(ns_nid, ns_name, line)
                add_edge_raw(file_nid, ns_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    walk(child, parent_class_nid=parent_class_nid)
            return

        if t in ("class_declaration", "interface_declaration"):
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            class_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            class_nid = _make_id(stem, class_name)
            line = node.start_point[0] + 1
            add_node(class_nid, class_name, line)
            add_edge_raw(file_nid, class_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    walk(child, parent_class_nid=class_nid)
            return

        if t == "method_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            method_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            line = node.start_point[0] + 1
            if parent_class_nid:
                method_nid = _make_id(parent_class_nid, method_name)
                add_node(method_nid, f".{method_name}()", line)
                add_edge_raw(parent_class_nid, method_nid, "method", line)
            else:
                method_nid = _make_id(stem, method_name)
                add_node(method_nid, f"{method_name}()", line)
                add_edge_raw(file_nid, method_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body:
                function_bodies.append((method_nid, body))
            return

        for child in node.children:
            walk(child, parent_class_nid=None)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()

    def walk_calls(node, caller_nid: str) -> None:
        if node.type == "method_declaration":
            return
        if node.type == "invocation_expression":
            callee_name: str | None = None
            name_node = node.child_by_field_name("name")
            if name_node:
                callee_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            else:
                # Try first named child
                for child in node.children:
                    if child.is_named:
                        raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                        # member_access_expression: strip the object prefix
                        if "." in raw:
                            callee_name = raw.split(".")[-1]
                        else:
                            callee_name = raw
                        break
            if callee_name:
                tgt_nid = label_to_nid.get(callee_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "confidence": "INFERRED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 0.8,
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

    return {"nodes": nodes, "edges": clean_edges}


def extract_kotlin(path: Path) -> dict:
    """Extract classes, objects, functions, and imports from a .kt/.kts file."""
    try:
        import tree_sitter_kotlin as tskotlin
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-kotlin not installed"}

    try:
        language = Language(tskotlin.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, node_type: str | None = None, modifiers: list | None = None) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            entry: dict = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            }
            if node_type is not None:
                entry["node_type"] = node_type
            if modifiers:
                entry["modifiers"] = modifiers
            nodes.append(entry)

    def add_edge_raw(src: str, tgt: str, relation: str, line: int, confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        })

    file_nid = _make_id(stem)
    add_node(file_nid, path.name, 1)

    function_bodies: list[tuple[str, object]] = []

    def walk(node, parent_class_nid: str | None = None) -> None:
        t = node.type

        if t == "import_header":
            for child in node.children:
                if child.type == "identifier":
                    raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                    tgt_nid = _make_id(raw)
                    add_edge_raw(file_nid, tgt_nid, "imports", node.start_point[0] + 1)
                    break
            return

        if t in ("class_declaration", "object_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                for child in node.children:
                    if child.type == "simple_identifier":
                        name_node = child
                        break
            if not name_node:
                return
            class_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            class_nid = _make_id(stem, class_name)
            line = node.start_point[0] + 1
            add_node(class_nid, class_name, line)
            add_edge_raw(file_nid, class_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body is None:
                for child in node.children:
                    if child.type == "class_body":
                        body = child
                        break
            if body:
                for child in body.children:
                    walk(child, parent_class_nid=class_nid)
            return

        if t == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                for child in node.children:
                    if child.type == "simple_identifier":
                        name_node = child
                        break
            if not name_node:
                return
            func_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            line = node.start_point[0] + 1
            if parent_class_nid:
                func_nid = _make_id(parent_class_nid, func_name)
                add_node(func_nid, f".{func_name}()", line)
                add_edge_raw(parent_class_nid, func_nid, "method", line)
            else:
                func_nid = _make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge_raw(file_nid, func_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body is None:
                for child in node.children:
                    if child.type == "function_body":
                        body = child
                        break
            if body:
                function_bodies.append((func_nid, body))
            return

        for child in node.children:
            walk(child, parent_class_nid=None)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()

    def walk_calls(node, caller_nid: str) -> None:
        if node.type == "function_declaration":
            return
        if node.type == "call_expression":
            callee_name: str | None = None
            # Try first child (the callable) then look for simple_identifier
            first = node.children[0] if node.children else None
            if first:
                if first.type == "simple_identifier":
                    callee_name = source[first.start_byte:first.end_byte].decode("utf-8", errors="replace")
                elif first.type == "navigation_expression":
                    # obj.method - get the suffix
                    for child in reversed(first.children):
                        if child.type == "simple_identifier":
                            callee_name = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                            break
            if callee_name:
                tgt_nid = label_to_nid.get(callee_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "confidence": "INFERRED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 0.8,
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

    return {"nodes": nodes, "edges": clean_edges}


def extract_scala(path: Path) -> dict:
    """Extract classes, objects, functions, and imports from a .scala file."""
    try:
        import tree_sitter_scala as tsscala
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-scala not installed"}

    try:
        language = Language(tsscala.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, node_type: str | None = None, modifiers: list | None = None) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            entry: dict = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            }
            if node_type is not None:
                entry["node_type"] = node_type
            if modifiers:
                entry["modifiers"] = modifiers
            nodes.append(entry)

    def add_edge_raw(src: str, tgt: str, relation: str, line: int, confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        })

    file_nid = _make_id(stem)
    add_node(file_nid, path.name, 1)

    function_bodies: list[tuple[str, object]] = []

    def walk(node, parent_class_nid: str | None = None) -> None:
        t = node.type

        if t == "import_declaration":
            for child in node.children:
                if child.type in ("stable_id", "identifier"):
                    raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                    module_name = raw.split(".")[-1].strip("{} ")
                    if module_name and module_name != "_":
                        tgt_nid = _make_id(module_name)
                        add_edge_raw(file_nid, tgt_nid, "imports", node.start_point[0] + 1)
                    break
            return

        if t in ("class_definition", "object_definition"):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                for child in node.children:
                    if child.type == "identifier":
                        name_node = child
                        break
            if not name_node:
                return
            class_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            class_nid = _make_id(stem, class_name)
            line = node.start_point[0] + 1
            add_node(class_nid, class_name, line)
            add_edge_raw(file_nid, class_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body is None:
                for child in node.children:
                    if child.type == "template_body":
                        body = child
                        break
            if body:
                for child in body.children:
                    walk(child, parent_class_nid=class_nid)
            return

        if t == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                for child in node.children:
                    if child.type == "identifier":
                        name_node = child
                        break
            if not name_node:
                return
            func_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            line = node.start_point[0] + 1
            if parent_class_nid:
                func_nid = _make_id(parent_class_nid, func_name)
                add_node(func_nid, f".{func_name}()", line)
                add_edge_raw(parent_class_nid, func_nid, "method", line)
            else:
                func_nid = _make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge_raw(file_nid, func_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body:
                function_bodies.append((func_nid, body))
            return

        for child in node.children:
            walk(child, parent_class_nid=None)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()

    def walk_calls(node, caller_nid: str) -> None:
        if node.type == "function_definition":
            return
        if node.type == "call_expression":
            callee_name: str | None = None
            # First child is the function being called
            first = node.children[0] if node.children else None
            if first:
                if first.type == "identifier":
                    callee_name = source[first.start_byte:first.end_byte].decode("utf-8", errors="replace")
                elif first.type == "field_expression":
                    field = first.child_by_field_name("field")
                    if field:
                        callee_name = source[field.start_byte:field.end_byte].decode("utf-8", errors="replace")
                    else:
                        for child in reversed(first.children):
                            if child.type == "identifier":
                                callee_name = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                                break
            if callee_name:
                tgt_nid = label_to_nid.get(callee_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "confidence": "INFERRED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 0.8,
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

    return {"nodes": nodes, "edges": clean_edges}


def extract_php(path: Path) -> dict:
    """Extract classes, functions, methods, namespace uses, and calls from a .php file."""
    try:
        import tree_sitter_php as tsphp
        from tree_sitter import Language, Parser
        try:
            from tree_sitter_php import language_php
            language = Language(language_php())
        except (ImportError, AttributeError):
            language = Language(tsphp.language())
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-php not installed"}

    try:
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, node_type: str | None = None, modifiers: list | None = None) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            entry: dict = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            }
            if node_type is not None:
                entry["node_type"] = node_type
            if modifiers:
                entry["modifiers"] = modifiers
            nodes.append(entry)

    def add_edge_raw(src: str, tgt: str, relation: str, line: int, confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        })

    file_nid = _make_id(stem)
    add_node(file_nid, path.name, 1)

    function_bodies: list[tuple[str, object]] = []

    def walk(node, parent_class_nid: str | None = None) -> None:
        t = node.type

        if t == "namespace_use_clause":
            for child in node.children:
                if child.type in ("qualified_name", "name", "identifier"):
                    raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                    module_name = raw.split("\\")[-1].strip()
                    if module_name:
                        tgt_nid = _make_id(module_name)
                        add_edge_raw(file_nid, tgt_nid, "imports", node.start_point[0] + 1)
                    break
            return

        if t == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                for child in node.children:
                    if child.type == "name":
                        name_node = child
                        break
            if not name_node:
                return
            class_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            class_nid = _make_id(stem, class_name)
            line = node.start_point[0] + 1
            add_node(class_nid, class_name, line)
            add_edge_raw(file_nid, class_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body is None:
                for child in node.children:
                    if child.type == "declaration_list":
                        body = child
                        break
            if body:
                for child in body.children:
                    walk(child, parent_class_nid=class_nid)
            return

        if t in ("function_definition", "method_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                for child in node.children:
                    if child.type == "name":
                        name_node = child
                        break
            if not name_node:
                return
            func_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            line = node.start_point[0] + 1
            if parent_class_nid:
                func_nid = _make_id(parent_class_nid, func_name)
                add_node(func_nid, f".{func_name}()", line)
                add_edge_raw(parent_class_nid, func_nid, "method", line)
            else:
                func_nid = _make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge_raw(file_nid, func_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body is None:
                for child in node.children:
                    if child.type == "compound_statement":
                        body = child
                        break
            if body:
                function_bodies.append((func_nid, body))
            return

        for child in node.children:
            walk(child, parent_class_nid=None)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()

    def walk_calls(node, caller_nid: str) -> None:
        if node.type in ("function_definition", "method_declaration"):
            return
        if node.type in ("function_call_expression", "member_call_expression"):
            callee_name: str | None = None
            if node.type == "function_call_expression":
                func_node = node.child_by_field_name("function")
                if func_node:
                    callee_name = source[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="replace")
            else:
                # member_call_expression: obj->method(args)
                name_node = node.child_by_field_name("name")
                if name_node:
                    callee_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            if callee_name:
                tgt_nid = label_to_nid.get(callee_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "confidence": "INFERRED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 0.8,
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

    return {"nodes": nodes, "edges": clean_edges}


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

    # Pass 1: name → node_id across all files
    # Map: stem → {ClassName: node_id}
    stem_to_entities: dict[str, dict[str, str]] = {}
    for file_result in per_file:
        for node in file_result.get("nodes", []):
            src = node.get("source_file", "")
            if not src:
                continue
            stem = Path(src).stem
            label = node.get("label", "")
            nid = node.get("id", "")
            # Only index real classes/functions (not file nodes, not method stubs)
            if label and not label.endswith((")", ".py")) and "_" not in label[:1]:
                stem_to_entities.setdefault(stem, {})[label] = nid

    # Pass 2: for each file, find `from .X import A, B, C` and resolve
    new_edges: list[dict] = []
    stem_to_path: dict[str, Path] = {p.stem: p for p in paths}

    for file_result, path in zip(per_file, paths):
        stem = path.stem
        str_path = str(path)

        # Find all classes defined in this file (the importers)
        local_classes = [
            n["id"] for n in file_result.get("nodes", [])
            if n.get("source_file") == str_path
            and not n["label"].endswith((")", ".py"))
            and n["id"] != _make_id(stem)  # exclude file-level node
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
                target_stem: str | None = None
                for child in node.children:
                    if child.type == "relative_import":
                        # Dig into relative_import → dotted_name → identifier
                        for sub in child.children:
                            if sub.type == "dotted_name":
                                raw = source[sub.start_byte:sub.end_byte].decode("utf-8", errors="replace")
                                target_stem = raw.split(".")[-1]
                                break
                        break
                    if child.type == "dotted_name" and target_stem is None:
                        raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                        target_stem = raw.split(".")[-1]

                if not target_stem or target_stem not in stem_to_entities:
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
                    tgt_nid = stem_to_entities[target_stem].get(name)
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


def extract(paths: list[Path]) -> dict:
    """Extract AST nodes and edges from a list of code files.

    Two-pass process:
    1. Per-file structural extraction (classes, functions, imports)
    2. Cross-file import resolution: turns file-level imports into
       class-level INFERRED edges (DigestAuth --uses--> Response)
    """
    per_file: list[dict] = []

    # Infer a common root for cache keys
    try:
        if not paths:
            root = Path(".")
        elif len(paths) == 1:
            root = paths[0].parent
        else:
            common_len = sum(
                1 for i in range(min(len(p.parts) for p in paths))
                if len({p.parts[i] for p in paths}) == 1
            )
            root = Path(*paths[0].parts[:common_len]) if common_len else Path(".")
    except Exception:
        root = Path(".")

    _JS_SUFFIXES = {".js", ".ts", ".tsx"}

    for path in paths:
        if path.suffix == ".py":
            cached = load_cached(path, root)
            if cached is not None:
                per_file.append(cached)
                continue
            result = extract_python(path)
            if "error" not in result:
                save_cached(path, result, root)
            per_file.append(result)
        elif path.suffix in _JS_SUFFIXES:
            cached = load_cached(path, root)
            if cached is not None:
                per_file.append(cached)
                continue
            result = extract_js(path)
            if "error" not in result:
                save_cached(path, result, root)
            per_file.append(result)
        elif path.suffix == ".go":
            cached = load_cached(path, root)
            if cached is not None:
                per_file.append(cached)
                continue
            result = extract_go(path)
            if "error" not in result:
                save_cached(path, result, root)
            per_file.append(result)
        elif path.suffix == ".rs":
            cached = load_cached(path, root)
            if cached is not None:
                per_file.append(cached)
                continue
            result = extract_rust(path)
            if "error" not in result:
                save_cached(path, result, root)
            per_file.append(result)
        elif path.suffix == ".java":
            cached = load_cached(path, root)
            if cached is not None:
                per_file.append(cached)
                continue
            result = extract_java(path)
            if "error" not in result:
                save_cached(path, result, root)
            per_file.append(result)
        elif path.suffix in {".c", ".h"}:
            cached = load_cached(path, root)
            if cached is not None:
                per_file.append(cached)
                continue
            result = extract_c(path)
            if "error" not in result:
                save_cached(path, result, root)
            per_file.append(result)
        elif path.suffix in {".cpp", ".cc", ".cxx", ".hpp"}:
            cached = load_cached(path, root)
            if cached is not None:
                per_file.append(cached)
                continue
            result = extract_cpp(path)
            if "error" not in result:
                save_cached(path, result, root)
            per_file.append(result)
        elif path.suffix == ".rb":
            cached = load_cached(path, root)
            if cached is not None:
                per_file.append(cached)
                continue
            result = extract_ruby(path)
            if "error" not in result:
                save_cached(path, result, root)
            per_file.append(result)
        elif path.suffix == ".cs":
            cached = load_cached(path, root)
            if cached is not None:
                per_file.append(cached)
                continue
            result = extract_csharp(path)
            if "error" not in result:
                save_cached(path, result, root)
            per_file.append(result)
        elif path.suffix in {".kt", ".kts"}:
            cached = load_cached(path, root)
            if cached is not None:
                per_file.append(cached)
                continue
            result = extract_kotlin(path)
            if "error" not in result:
                save_cached(path, result, root)
            per_file.append(result)
        elif path.suffix == ".scala":
            cached = load_cached(path, root)
            if cached is not None:
                per_file.append(cached)
                continue
            result = extract_scala(path)
            if "error" not in result:
                save_cached(path, result, root)
            per_file.append(result)
        elif path.suffix == ".php":
            cached = load_cached(path, root)
            if cached is not None:
                per_file.append(cached)
                continue
            result = extract_php(path)
            if "error" not in result:
                save_cached(path, result, root)
            per_file.append(result)

    all_nodes: list[dict] = []
    all_edges: list[dict] = []
    for result in per_file:
        all_nodes.extend(result.get("nodes", []))
        all_edges.extend(result.get("edges", []))

    # Add cross-file class-level edges (Python only - uses Python parser internally)
    py_paths = [p for p in paths if p.suffix == ".py"]
    py_results = [r for r, p in zip(per_file, paths) if p.suffix == ".py"]
    cross_file_edges = _resolve_cross_file_imports(py_results, py_paths)
    all_edges.extend(cross_file_edges)

    return {
        "nodes": all_nodes,
        "edges": all_edges,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def collect_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    _EXTENSIONS = (
        "*.py", "*.js", "*.ts", "*.tsx", "*.go", "*.rs",
        "*.java", "*.c", "*.h", "*.cpp", "*.cc", "*.cxx", "*.hpp",
        "*.rb", "*.cs", "*.kt", "*.kts", "*.scala", "*.php",
    )
    results: list[Path] = []
    for pattern in _EXTENSIONS:
        results.extend(
            p for p in target.rglob(pattern)
            if not any(part.startswith(".") for part in p.parts)
        )
    return sorted(results)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m graphify.extract <file_or_dir> ...", file=sys.stderr)
        sys.exit(1)

    paths: list[Path] = []
    for arg in sys.argv[1:]:
        paths.extend(collect_files(Path(arg)))

    result = extract(paths)
    print(json.dumps(result, indent=2))
