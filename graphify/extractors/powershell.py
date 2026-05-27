from .core import *
from pathlib import Path
from typing import Any


# ── PowerShell ────────────────────────────────────────────────────────────────

def extract_powershell(path: Path) -> dict:
    """Extract functions, classes, methods, and using statements from a .ps1 file."""
    try:
        import tree_sitter_powershell as tsps
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_powershell not installed"}

    try:
        language = Language(tsps.language())
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

    _PS_SKIP = frozenset({
        "using", "return", "if", "else", "elseif", "foreach", "for",
        "while", "do", "switch", "try", "catch", "finally", "throw",
        "break", "continue", "exit", "param", "begin", "process", "end",
    })

    def _find_script_block_body(node):
        for child in node.children:
            if child.type == "script_block":
                for sc in child.children:
                    if sc.type == "script_block_body":
                        return sc
                return child
        return None

    def walk(node, parent_class_nid: str | None = None) -> None:
        t = node.type

        if t == "function_statement":
            name_node = next((c for c in node.children if c.type == "function_name"), None)
            if name_node:
                func_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                func_nid = _make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(file_nid, func_nid, "contains", line)
                body = _find_script_block_body(node)
                if body:
                    function_bodies.append((func_nid, body))
            return

        if t == "class_statement":
            name_node = next((c for c in node.children if c.type == "simple_name"), None)
            if name_node:
                class_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                class_nid = _make_id(stem, class_name)
                add_node(class_nid, class_name, line)
                add_edge(file_nid, class_nid, "contains", line)
                for child in node.children:
                    walk(child, parent_class_nid=class_nid)
            return

        if t == "class_method_definition":
            name_node = next((c for c in node.children if c.type == "simple_name"), None)
            if name_node:
                method_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                if parent_class_nid:
                    method_nid = _make_id(parent_class_nid, method_name)
                    add_node(method_nid, f".{method_name}()", line)
                    add_edge(parent_class_nid, method_nid, "method", line)
                else:
                    method_nid = _make_id(stem, method_name)
                    add_node(method_nid, f"{method_name}()", line)
                    add_edge(file_nid, method_nid, "contains", line)
                body = _find_script_block_body(node)
                if body:
                    function_bodies.append((method_nid, body))
            return

        if t == "command":
            cmd_name_node = next((c for c in node.children if c.type == "command_name"), None)
            if cmd_name_node:
                cmd_text = _read_text(cmd_name_node, source).lower()
                if cmd_text == "using":
                    tokens = []
                    for child in node.children:
                        if child.type == "command_elements":
                            for el in child.children:
                                if el.type == "generic_token":
                                    tokens.append(_read_text(el, source))
                    module_tokens = [t for t in tokens
                                     if t.lower() not in ("namespace", "module", "assembly")]
                    if module_tokens:
                        module_name = module_tokens[-1].split(".")[-1]
                        add_edge(file_nid, _make_id(module_name), "imports_from",
                                 node.start_point[0] + 1)
            return

        for child in node.children:
            walk(child, parent_class_nid)

    walk(root)

    label_to_nid = {n["label"].strip("()").lstrip(".").lower(): n["id"] for n in nodes}
    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []

    def walk_calls(node, caller_nid: str) -> None:
        if node.type in ("function_statement", "class_statement"):
            return
        if node.type == "command":
            cmd_name_node = next((c for c in node.children if c.type == "command_name"), None)
            if cmd_name_node:
                cmd_text = _read_text(cmd_name_node, source)
                if cmd_text.lower() not in _PS_SKIP:
                    tgt_nid = label_to_nid.get(cmd_text.lower())
                    if tgt_nid and tgt_nid != caller_nid:
                        pair = (caller_nid, tgt_nid)
                        if pair not in seen_call_pairs:
                            seen_call_pairs.add(pair)
                            add_edge(caller_nid, tgt_nid, "calls",
                                     node.start_point[0] + 1,
                                     confidence="EXTRACTED", weight=1.0)
                    elif cmd_text:
                        raw_calls.append({
                            "caller_nid": caller_nid,
                            "callee": cmd_text,
                            "is_member_call": False,
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


__all__ = ['extract_powershell']
