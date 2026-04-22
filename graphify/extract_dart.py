"""Pure Dart language extraction using tree-sitter-dart-orchard.

This module handles core Dart constructs only:
- Classes (abstract, sealed, final, base, interface), mixins, extensions, enums, typedefs
- Functions and class-scoped methods
- Imports (dart:, package:, relative), exports, part/part-of
- Inheritance (extends, implements, with, on)
- Call-graph analysis

Flutter-specific analysis (widgets, composition, navigation) lives in extract_flutter.py.
Framework detection (Riverpod, BLoC, GoRouter) lives in extract_dart_frameworks.py.
Both layers are orchestrated by the extract_dart() wrapper in extract.py.
"""
from __future__ import annotations

import re
from pathlib import Path


def _make_id(*parts: str) -> str:
    """Build a stable node ID from one or more name parts."""
    combined = "_".join(p.strip("_.") for p in parts if p)
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", combined)
    return cleaned.strip("_").lower()


def _read_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


# Class modifier keywords recognised by Dart 3
_CLASS_MODIFIERS = frozenset({"abstract", "sealed", "final", "base", "interface"})


def extract_dart(path: Path) -> dict:
    """Extract classes, mixins, extensions, enums, typedefs, functions, imports, and calls from a .dart file."""
    try:
        import tree_sitter_dart_orchard as tsdart
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-dart-orchard not installed"}

    try:
        language = Language(tsdart.language())
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
    function_bodies: list[tuple[str, object]] = []

    def add_node(nid: str, label: str, line: int, **extra) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            node_dict = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            }
            node_dict.update(extra)
            nodes.append(node_dict)

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "confidence_score": weight,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        })

    file_nid = _make_id(stem)
    add_node(file_nid, path.name, 1)

    # ── Helper: extract methods from a class/mixin/extension body ────────────
    def extract_methods(body_node, parent_nid: str) -> None:
        """Walk a class_body or extension_body and extract method_signature + function_body pairs."""
        children = list(body_node.children)
        i = 0
        while i < len(children):
            child = children[i]
            if child.type == "method_signature":
                # Look for function_signature inside
                func_sig = None
                for sc in child.children:
                    if sc.type == "function_signature":
                        func_sig = sc
                        break
                if func_sig:
                    name_node = func_sig.child_by_field_name("name")
                    if name_node:
                        method_name = _read_text(name_node, source)
                        line = child.start_point[0] + 1
                        method_nid = _make_id(parent_nid, method_name)
                        add_node(method_nid, f".{method_name}()", line)
                        add_edge(parent_nid, method_nid, "method", line)
                        # The function_body is the next sibling after method_signature
                        if i + 1 < len(children) and children[i + 1].type == "function_body":
                            function_bodies.append((method_nid, children[i + 1]))
            i += 1

    # ── First pass: walk top-level nodes ─────────────────────────────────────
    def walk(node) -> None:
        t = node.type

        # ── Classes ──────────────────────────────────────────────────────────
        if t == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                class_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                class_nid = _make_id(stem, class_name)

                # Detect class modifier
                modifier = None
                for child in node.children:
                    if child.type in _CLASS_MODIFIERS:
                        modifier = child.type
                        break

                extra = {"dart_kind": "class"}
                if modifier:
                    extra["class_modifier"] = modifier

                add_node(class_nid, class_name, line, **extra)
                add_edge(file_nid, class_nid, "contains", line)

                # Superclass (extends + mixins)
                superclass_node = node.child_by_field_name("superclass")
                if superclass_node:
                    for sc in superclass_node.children:
                        if sc.type == "type_identifier":
                            parent_name = _read_text(sc, source)
                            parent_nid = _make_id(stem, parent_name)
                            add_node(parent_nid, parent_name, sc.start_point[0] + 1, dart_kind="class")
                            add_edge(class_nid, parent_nid, "inherits", sc.start_point[0] + 1)
                            break  # Only the first type_identifier is the superclass
                    # Mixins are inside the superclass node
                    for sc in superclass_node.children:
                        if sc.type == "mixins":
                            for mc in sc.children:
                                if mc.type == "type_identifier":
                                    mixin_name = _read_text(mc, source)
                                    mixin_nid = _make_id(stem, mixin_name)
                                    add_node(mixin_nid, mixin_name, mc.start_point[0] + 1, dart_kind="mixin")
                                    add_edge(class_nid, mixin_nid, "mixes_in", mc.start_point[0] + 1)

                # Interfaces (implements)
                interfaces_node = node.child_by_field_name("interfaces")
                if interfaces_node:
                    for ic in interfaces_node.children:
                        if ic.type == "type_identifier":
                            iface_name = _read_text(ic, source)
                            iface_nid = _make_id(stem, iface_name)
                            add_node(iface_nid, iface_name, ic.start_point[0] + 1)
                            add_edge(class_nid, iface_nid, "implements", ic.start_point[0] + 1)

                # Methods
                body_node = node.child_by_field_name("body")
                if body_node:
                    extract_methods(body_node, class_nid)

            return

        # ── Mixins ───────────────────────────────────────────────────────────
        if t == "mixin_declaration":
            # The identifier child (not via field name) holds the mixin name
            mixin_name = None
            mixin_name_node = None
            for child in node.children:
                if child.type == "identifier":
                    mixin_name = _read_text(child, source)
                    mixin_name_node = child
                    break
            if mixin_name:
                line = node.start_point[0] + 1
                mixin_nid = _make_id(stem, mixin_name)
                add_node(mixin_nid, mixin_name, line, dart_kind="mixin")
                add_edge(file_nid, mixin_nid, "contains", line)

                # Check for `on` constraint: after `on` keyword, next type_identifier is the constraint
                found_on = False
                for child in node.children:
                    if child.type == "on":
                        found_on = True
                        continue
                    if found_on and child.type == "type_identifier":
                        constraint_name = _read_text(child, source)
                        constraint_nid = _make_id(stem, constraint_name)
                        add_node(constraint_nid, constraint_name, child.start_point[0] + 1, dart_kind="class")
                        add_edge(mixin_nid, constraint_nid, "constrained_to", child.start_point[0] + 1)
                        break

                # Methods in mixin body (class_body)
                for child in node.children:
                    if child.type == "class_body":
                        extract_methods(child, mixin_nid)
                        break

            return

        # ── Extensions ───────────────────────────────────────────────────────
        if t == "extension_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                ext_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                ext_nid = _make_id(stem, ext_name)

                # Find target type: after `on` keyword
                target_type = None
                found_on = False
                for child in node.children:
                    if child.type == "on":
                        found_on = True
                        continue
                    if found_on and child.type == "type_identifier":
                        target_type = _read_text(child, source)
                        break

                extra = {"dart_kind": "extension"}
                if target_type:
                    extra["extends_target"] = target_type

                add_node(ext_nid, ext_name, line, **extra)
                add_edge(file_nid, ext_nid, "contains", line)

                if target_type:
                    target_nid = _make_id(stem, target_type)
                    add_node(target_nid, target_type, line)
                    add_edge(ext_nid, target_nid, "extends_type", line)

                # Methods in extension body
                body_node = node.child_by_field_name("body")
                if body_node:
                    extract_methods(body_node, ext_nid)

            return

        # ── Enums ────────────────────────────────────────────────────────────
        if t == "enum_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                enum_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                enum_nid = _make_id(stem, enum_name)
                add_node(enum_nid, enum_name, line, dart_kind="enum")
                add_edge(file_nid, enum_nid, "contains", line)
            return

        # ── Typedefs ─────────────────────────────────────────────────────────
        if t == "type_alias":
            # The typedef name is a type_identifier child
            for child in node.children:
                if child.type == "type_identifier":
                    typedef_name = _read_text(child, source)
                    line = node.start_point[0] + 1
                    typedef_nid = _make_id(stem, typedef_name)
                    add_node(typedef_nid, typedef_name, line, dart_kind="typedef")
                    add_edge(file_nid, typedef_nid, "contains", line)
                    break
            return

        # ── Top-level functions ──────────────────────────────────────────────
        if t == "function_signature" and node.parent and node.parent.type == "program":
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                func_nid = _make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(file_nid, func_nid, "contains", line)
                # The function_body is the next sibling in the program
                parent = node.parent
                siblings = list(parent.children)
                idx = None
                for si, s in enumerate(siblings):
                    if s.id == node.id:
                        idx = si
                        break
                if idx is not None and idx + 1 < len(siblings) and siblings[idx + 1].type == "function_body":
                    function_bodies.append((func_nid, siblings[idx + 1]))
            return

        # ── Imports ──────────────────────────────────────────────────────────
        if t == "import_or_export":
            for child in node.children:
                if child.type == "library_import":
                    # Extract URI from import_specification > configurable_uri
                    for spec_child in child.children:
                        if spec_child.type == "import_specification":
                            for isc in spec_child.children:
                                if isc.type == "configurable_uri":
                                    uri_text = _read_text(isc, source).strip("'\"")
                                    tgt_nid = _make_id(uri_text)
                                    line = node.start_point[0] + 1
                                    add_edge(file_nid, tgt_nid, "imports", line)
                                    break
                elif child.type == "library_export":
                    for ec in child.children:
                        if ec.type == "configurable_uri":
                            uri_text = _read_text(ec, source).strip("'\"")
                            tgt_nid = _make_id(uri_text)
                            line = node.start_point[0] + 1
                            add_edge(file_nid, tgt_nid, "exports", line)
                            break
            return

        # ── Part directives ──────────────────────────────────────────────────
        if t == "part_directive":
            for child in node.children:
                if child.type == "uri":
                    uri_text = _read_text(child, source).strip("'\"")
                    tgt_nid = _make_id(uri_text)
                    line = node.start_point[0] + 1
                    add_edge(file_nid, tgt_nid, "has_part", line)
                    break
            return

        # Recurse into children
        for child in node.children:
            walk(child)

    walk(root)

    # ── Second pass: call-graph analysis ─────────────────────────────────────
    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()

    def _add_call(caller_nid: str, callee_name: str, line: int) -> None:
        tgt_nid = label_to_nid.get(callee_name.lower())
        if tgt_nid and tgt_nid != caller_nid:
            pair = (caller_nid, tgt_nid)
            if pair not in seen_call_pairs:
                seen_call_pairs.add(pair)
                edges.append({
                    "source": caller_nid,
                    "target": tgt_nid,
                    "relation": "calls",
                    "confidence": "INFERRED",
                    "confidence_score": 0.8,
                    "source_file": str_path,
                    "source_location": f"L{line}",
                    "weight": 0.8,
                })

    def walk_calls(node, caller_nid: str) -> None:
        # Skip nested function/method definitions
        if node.type in ("function_signature", "method_signature") and node.parent and node.parent.type != "program":
            return

        # Pattern 1: expression_statement with identifier + selector(unconditional_assignable_selector) + selector(argument_part)
        # This covers: obj.method(args) and funcName(args)
        if node.type == "expression_statement":
            children = [c for c in node.children if c.type not in (";",)]
            if len(children) >= 2:
                first = children[0]
                if first.type == "identifier":
                    first_name = _read_text(first, source)
                    selectors = [c for c in children if c.type == "selector"]

                    # Check for direct function call: identifier + selector(argument_part)
                    # e.g., print('hello')
                    if len(selectors) >= 1:
                        first_sel = selectors[0]
                        has_arg_part = any(sc.type == "argument_part" for sc in first_sel.children)
                        if has_arg_part:
                            # Direct function call
                            _add_call(caller_nid, first_name, node.start_point[0] + 1)

                    # Check for method call: identifier + selector(unconditional_assignable_selector > . + identifier) + selector(argument_part)
                    # e.g., dog.speak()
                    if len(selectors) >= 2:
                        for si in range(len(selectors) - 1):
                            sel = selectors[si]
                            next_sel = selectors[si + 1]
                            # Check if current selector has unconditional_assignable_selector with method name
                            for sc in sel.children:
                                if sc.type == "unconditional_assignable_selector":
                                    for uc in sc.children:
                                        if uc.type == "identifier":
                                            method_name = _read_text(uc, source)
                                            # And next selector has argument_part
                                            if any(nsc.type == "argument_part" for nsc in next_sel.children):
                                                _add_call(caller_nid, method_name, node.start_point[0] + 1)

        # Pattern 2: Constructor call in local_variable_declaration
        # e.g., final dog = Dog();
        if node.type == "initialized_variable_definition":
            value_node = node.child_by_field_name("value")
            if value_node and value_node.type == "identifier":
                constructor_name = _read_text(value_node, source)
                # Check if followed by a selector with argument_part (constructor call)
                children = list(node.children)
                for ci, child in enumerate(children):
                    if child.id == value_node.id:
                        # Look at next siblings for selector > argument_part
                        for j in range(ci + 1, len(children)):
                            if children[j].type == "selector":
                                if any(sc.type == "argument_part" for sc in children[j].children):
                                    _add_call(caller_nid, constructor_name, node.start_point[0] + 1)
                                    break
                        break

        # Recurse
        for child in node.children:
            walk_calls(child, caller_nid)

    for caller_nid, body_node in function_bodies:
        walk_calls(body_node, caller_nid)

    # ── Clean edges ──────────────────────────────────────────────────────────
    valid_ids = seen_ids
    clean_edges = [
        e for e in edges
        if e["source"] in valid_ids
        and (e["target"] in valid_ids or e["relation"] in ("imports", "imports_from", "exports", "has_part"))
    ]

    return {"nodes": nodes, "edges": clean_edges}
