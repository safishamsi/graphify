"""Flutter-specific analysis layer — only activates when package:flutter imports are detected.

This module enriches the pure Dart extraction result with Flutter-specific graph data.
Pure Dart server/CLI projects skip this entirely.

Adds:
- widget_kind metadata on widget class nodes (stateless/stateful/state/inherited/change_notifier)
- creates_state edges for StatefulWidget / State pairing
- composes edges for widget-tree composition in build() methods
- depends_on_inherited edges for X.of(context) patterns
- navigates_to edges for Navigator API calls (pushNamed, push+MaterialPageRoute, etc.)
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extract_dart import _make_id, _read_text

# ── Well-known Flutter widget names ─────────────────────────────────────────
_KNOWN_WIDGETS: set[str] = {
    "MaterialApp", "Scaffold", "AppBar", "Text", "Center", "Column", "Row",
    "Container", "Padding", "SizedBox", "Expanded", "Flexible", "Stack",
    "ListView", "GridView", "SingleChildScrollView", "Card", "ListTile",
    "IconButton", "ElevatedButton", "TextButton", "FloatingActionButton",
    "Icon", "Image", "TextField", "Form", "Drawer", "BottomNavigationBar",
    "SafeArea", "Wrap", "Align", "Positioned", "Opacity", "ClipRRect",
    "ClipOval", "DecoratedBox", "FittedBox", "InkWell", "GestureDetector",
    "Navigator", "PageView", "TabBar", "TabBarView", "Divider",
    "CircularProgressIndicator", "LinearProgressIndicator", "Chip",
    "DropdownButton", "PopupMenuButton", "SnackBar", "Dialog",
    "AlertDialog", "SimpleDialog", "BottomSheet", "Tooltip",
    "ThemeData", "MediaQuery", "LayoutBuilder", "Builder",
    "StreamBuilder", "FutureBuilder", "AnimatedContainer",
    "AnimatedOpacity", "Hero", "CustomScrollView", "SliverList",
    "SliverGrid", "SliverAppBar", "RefreshIndicator",
}

# Base classes that determine widget_kind
_WIDGET_BASE_MAP: dict[str, str] = {
    "StatelessWidget": "stateless",
    "StatefulWidget": "stateful",
    "InheritedWidget": "inherited",
    "ChangeNotifier": "change_notifier",
}


def analyze_flutter(result: dict, path: Path) -> None:
    """Mutate *result* in-place with Flutter-specific graph data.

    Only activates when ``package:flutter`` imports are detected.
    """
    # ── Check for Flutter imports ────────────────────────────────────────────
    has_flutter = any(
        e["relation"] == "imports"
        and "package_flutter" in e.get("target", "")
        for e in result["edges"]
    )
    if not has_flutter:
        return

    # ── Re-parse the file ────────────────────────────────────────────────────
    try:
        import tree_sitter_dart_orchard as tsdart
        from tree_sitter import Language, Parser
    except ImportError:
        return

    language = Language(tsdart.language())
    parser = Parser(language)
    source = path.read_bytes()
    tree = parser.parse(source)
    root = tree.root_node
    stem = path.stem
    str_path = str(path)

    # Build lookup helpers
    node_by_id: dict[str, dict] = {n["id"]: n for n in result["nodes"]}
    label_to_nid: dict[str, str] = {n["label"]: n["id"] for n in result["nodes"]}
    seen_ids: set[str] = {n["id"] for n in result["nodes"]}

    # Collect widget labels from same file (added dynamically below)
    local_widget_labels: set[str] = set()

    def _add_node_if_missing(nid: str, label: str, line: int, **extra) -> None:
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
            result["nodes"].append(node_dict)
            node_by_id[nid] = node_dict
            label_to_nid[label] = nid

    def _add_edge(src: str, tgt: str, relation: str, line: int,
                  confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        result["edges"].append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "confidence_score": weight,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        })

    # ── 1. Widget-kind annotation ────────────────────────────────────────────
    inherits_map: dict[str, str] = {}  # class_nid -> parent_label
    for e in result["edges"]:
        if e["relation"] == "inherits":
            src_node = node_by_id.get(e["source"])
            tgt_node = node_by_id.get(e["target"])
            if src_node and tgt_node:
                inherits_map[e["source"]] = tgt_node["label"]

    for nid, parent_label in inherits_map.items():
        node = node_by_id[nid]
        kind = _WIDGET_BASE_MAP.get(parent_label)
        if kind:
            node["widget_kind"] = kind
            local_widget_labels.add(node["label"])
        elif parent_label == "State":
            node["widget_kind"] = "state"
            local_widget_labels.add(node["label"])

    # ── 2. StatefulWidget / State pairing via createState() ──────────────────
    for class_node in root.children:
        if class_node.type != "class_definition":
            continue
        name_nd = class_node.child_by_field_name("name")
        if not name_nd:
            continue
        class_name = _read_text(name_nd, source)
        class_nid = _make_id(stem, class_name)
        if class_nid not in node_by_id:
            continue

        body_nd = class_node.child_by_field_name("body")
        if not body_nd:
            continue

        children = list(body_nd.children)
        for i, child in enumerate(children):
            if child.type != "method_signature":
                continue
            func_sig = None
            for sc in child.children:
                if sc.type == "function_signature":
                    func_sig = sc
                    break
            if not func_sig:
                continue
            mname_nd = func_sig.child_by_field_name("name")
            if not mname_nd or _read_text(mname_nd, source) != "createState":
                continue
            # Found createState – get the body
            if i + 1 < len(children) and children[i + 1].type == "function_body":
                body_text = _read_text(children[i + 1], source)
                m = re.search(r"(?:=>|return)\s+(\w+)\s*\(\s*\)", body_text)
                if m:
                    state_class = m.group(1)
                    state_nid = label_to_nid.get(state_class)
                    if state_nid:
                        line = child.start_point[0] + 1
                        _add_edge(class_nid, state_nid, "creates_state", line)

    # ── 3 & 4.  Walk build() methods for composition + inherited deps ────────
    all_widget_names = _KNOWN_WIDGETS | local_widget_labels

    def _is_widget_name(name: str) -> bool:
        return name in all_widget_names

    def _find_build_methods():
        """Yield (class_nid, class_label, function_body_node) for each build()."""
        for class_node in root.children:
            if class_node.type != "class_definition":
                continue
            name_nd = class_node.child_by_field_name("name")
            if not name_nd:
                continue
            class_name = _read_text(name_nd, source)
            class_nid = _make_id(stem, class_name)
            if class_nid not in node_by_id:
                continue
            body_nd = class_node.child_by_field_name("body")
            if not body_nd:
                continue
            children = list(body_nd.children)
            for i, child in enumerate(children):
                if child.type != "method_signature":
                    continue
                func_sig = None
                for sc in child.children:
                    if sc.type == "function_signature":
                        func_sig = sc
                        break
                if not func_sig:
                    continue
                mname_nd = func_sig.child_by_field_name("name")
                if not mname_nd or _read_text(mname_nd, source) != "build":
                    continue
                if i + 1 < len(children) and children[i + 1].type == "function_body":
                    yield class_nid, class_name, children[i + 1]

    def _walk_for_composition(node, parent_widget: str | None, owner_class: str,
                              in_conditional: bool, in_builder: bool):
        """Recursively find widget constructor calls and emit composes edges.

        parent_widget: label of the immediately enclosing widget constructor (or None).
        owner_class: label of the class that owns the build() method.
        in_conditional: True when inside a conditional_expression or if_element.
        in_builder: True when inside a function_expression (builder callback).

        When in_conditional or in_builder, widgets attach flat to owner_class.
        Otherwise they nest under parent_widget (or owner_class if no parent).
        """
        # Detect conditional expressions and builder callbacks
        if node.type == "conditional_expression":
            # Walk children with in_conditional=True
            for child in node.children:
                _walk_for_composition(child, parent_widget, owner_class,
                                      True, in_builder)
            return

        if node.type == "if_element":
            for child in node.children:
                _walk_for_composition(child, parent_widget, owner_class,
                                      True, in_builder)
            return

        if node.type == "function_expression":
            for child in node.children:
                _walk_for_composition(child, parent_widget, owner_class,
                                      in_conditional, True)
            return

        # Pattern A: const_object_expression -> type_identifier + arguments
        # e.g. const Text('hello'), const Icon(Icons.add), const HomeScreen()
        if node.type == "const_object_expression":
            type_id_nodes = [c for c in node.children if c.type == "type_identifier"]
            if type_id_nodes:
                widget_name = _read_text(type_id_nodes[0], source)
                if _is_widget_name(widget_name):
                    attach_to = owner_class if (in_conditional or in_builder) else (parent_widget or owner_class)
                    src_nid = label_to_nid.get(attach_to)
                    tgt_nid = label_to_nid.get(widget_name)
                    if not tgt_nid:
                        tgt_nid = _make_id(stem, widget_name)
                        _add_node_if_missing(tgt_nid, widget_name,
                                             node.start_point[0] + 1, dart_kind="class")
                    if src_nid and tgt_nid:
                        line = node.start_point[0] + 1
                        _add_edge(src_nid, tgt_nid, "composes", line, weight=0.9)
                    # Recurse into arguments with this widget as the new parent
                    new_parent = widget_name if not (in_conditional or in_builder) else parent_widget
                    for child in node.children:
                        if child.type == "arguments":
                            _walk_for_composition(child, new_parent, owner_class,
                                                  in_conditional, in_builder)
                    return

        # Pattern B: identifier + selector(argument_part)  (non-const constructor)
        # e.g. Scaffold(...), AppBar(...), Text(...)
        # These appear as siblings: identifier, selector, selector, ...
        # We need to check if the identifier is a widget name AND the next sibling is a selector with argument_part.
        #
        # This pattern appears in various contexts:
        # - return_statement children: return, identifier, selector
        # - named_argument children: label, identifier, selector
        # - argument children: identifier, selector
        # - list_literal children: [..., identifier, selector, ...]
        if node.type == "identifier":
            name = _read_text(node, source)
            if _is_widget_name(name) and node.parent is not None:
                parent_nd = node.parent
                siblings = list(parent_nd.children)
                my_idx = None
                for si, s in enumerate(siblings):
                    if s.id == node.id:
                        my_idx = si
                        break
                if my_idx is not None and my_idx + 1 < len(siblings):
                    next_sib = siblings[my_idx + 1]
                    if next_sib.type == "selector":
                        has_arg_part = any(
                            sc.type == "argument_part" for sc in next_sib.children
                        )
                        if has_arg_part:
                            attach_to = owner_class if (in_conditional or in_builder) else (parent_widget or owner_class)
                            src_nid = label_to_nid.get(attach_to)
                            tgt_nid = label_to_nid.get(name)
                            if not tgt_nid:
                                tgt_nid = _make_id(stem, name)
                                _add_node_if_missing(tgt_nid, name,
                                                     node.start_point[0] + 1, dart_kind="class")
                            if src_nid and tgt_nid:
                                line = node.start_point[0] + 1
                                _add_edge(src_nid, tgt_nid, "composes", line, weight=0.9)
                            # Recurse into the selector's arguments with this as parent
                            new_parent = name if not (in_conditional or in_builder) else parent_widget
                            for sc in next_sib.children:
                                if sc.type == "argument_part":
                                    _walk_for_composition(sc, new_parent, owner_class,
                                                          in_conditional, in_builder)
                            return  # Don't recurse further from this identifier

        # Default: recurse into children
        for child in node.children:
            _walk_for_composition(child, parent_widget, owner_class,
                                  in_conditional, in_builder)

    def _walk_for_inherited(node, class_nid: str):
        """Find X.of(context) patterns -> depends_on_inherited edges."""
        # Pattern: identifier(X) + selector(.of) + selector(args with context)
        # In the AST this shows up in various expression contexts.
        # We look for sequences: identifier, selector(.of), selector(argument_part)
        if node.type in ("local_variable_declaration", "expression_statement",
                         "return_statement", "initialized_variable_definition"):
            children = list(node.children)
            for i, child in enumerate(children):
                if child.type == "identifier":
                    name = _read_text(child, source)
                    # Check next two siblings for .of + (context)
                    if i + 2 < len(children):
                        sel1 = children[i + 1]
                        sel2 = children[i + 2]
                        if sel1.type == "selector" and sel2.type == "selector":
                            # Check sel1 has .of
                            has_of = False
                            for sc in sel1.children:
                                if sc.type == "unconditional_assignable_selector":
                                    for uc in sc.children:
                                        if uc.type == "identifier" and _read_text(uc, source) == "of":
                                            has_of = True
                            # Check sel2 has argument_part with "context"
                            has_context_arg = False
                            if has_of:
                                for sc in sel2.children:
                                    if sc.type == "argument_part":
                                        arg_text = _read_text(sc, source)
                                        if re.search(r'\bcontext\b', arg_text):
                                            has_context_arg = True
                            if has_of and has_context_arg:
                                tgt_nid = label_to_nid.get(name)
                                if not tgt_nid:
                                    tgt_nid = _make_id(stem, name)
                                    _add_node_if_missing(tgt_nid, name,
                                                         child.start_point[0] + 1,
                                                         dart_kind="class")
                                line = child.start_point[0] + 1
                                _add_edge(class_nid, tgt_nid, "depends_on_inherited",
                                          line, confidence="INFERRED", weight=0.9)

        # Recurse
        for child in node.children:
            _walk_for_inherited(child, class_nid)

    for class_nid, class_label, body_node in _find_build_methods():
        _walk_for_composition(body_node, None, class_label, False, False)
        _walk_for_inherited(body_node, class_nid)

    # ── 5.  Navigation edges (Navigator API) ────────────────────────────────
    #
    # Scans ALL method bodies (not just build()) for Navigator calls because
    # navigation can happen in onPressed callbacks, helper methods, etc.
    #
    # Patterns detected:
    #   Navigator.pushNamed(context, '/route')
    #   Navigator.of(context).pushNamed('/route')
    #   Navigator.pushReplacementNamed(context, '/route')
    #   Navigator.popAndPushNamed(context, '/route')
    #   Navigator.push(context, MaterialPageRoute(builder: (ctx) => Screen()))

    _NAV_PUSH_NAMED = re.compile(
        r"""Navigator\s*"""
        r"""(?:\.of\s*\([^)]*\)\s*)?"""
        r"""\.(?:pushNamed|pushReplacementNamed|popAndPushNamed|restorablePushNamed)"""
        r"""\s*\(\s*(?:context\s*,\s*)?['"]([^'"]+)['"]"""
    )
    _NAV_PUSH_ROUTE = re.compile(
        r"""(?:MaterialPageRoute|CupertinoPageRoute)"""
        r"""\s*\(\s*builder\s*:\s*\([^)]*\)\s*(?:=>|{\s*return)\s*(\w+)\s*\("""
    )

    for class_node in root.children:
        if class_node.type != "class_definition":
            continue
        name_nd = class_node.child_by_field_name("name")
        if not name_nd:
            continue
        class_name = _read_text(name_nd, source)
        class_nid = _make_id(stem, class_name)
        if class_nid not in node_by_id:
            continue

        body_nd = class_node.child_by_field_name("body")
        if not body_nd:
            continue
        body_text = _read_text(body_nd, source)
        line = body_nd.start_point[0] + 1

        # Named route navigation
        for m in _NAV_PUSH_NAMED.finditer(body_text):
            route_path = m.group(1)
            route_nid = _make_id("route", route_path)
            _add_node_if_missing(route_nid, route_path, line, dart_kind="route")
            _add_edge(class_nid, route_nid, "navigates_to", line,
                      confidence="INFERRED", weight=0.8)

        # Direct push with MaterialPageRoute / CupertinoPageRoute
        for m in _NAV_PUSH_ROUTE.finditer(body_text):
            screen_name = m.group(1)
            screen_nid = label_to_nid.get(screen_name)
            if not screen_nid:
                screen_nid = _make_id(stem, screen_name)
                _add_node_if_missing(screen_nid, screen_name, line,
                                     dart_kind="class")
            _add_edge(class_nid, screen_nid, "navigates_to", line,
                      confidence="INFERRED", weight=0.8)
