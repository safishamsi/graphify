from .core import *
from pathlib import Path


def extract_verilog(path: Path) -> dict:
    """Extract modules, functions, tasks, package imports, and instantiations from .v/.sv files."""
    try:
        import tree_sitter_verilog as tsverilog
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_verilog not installed"}

    try:
        language = Language(tsverilog.language())
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

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}",
                          "confidence_score": 1.0})

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", score: float = 1.0) -> None:
        edges.append({"source": src, "target": tgt, "relation": relation,
                      "confidence": confidence, "confidence_score": score,
                      "source_file": str_path, "source_location": f"L{line}", "weight": 1.0})

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def walk(node, module_nid: str | None = None) -> None:
        t = node.type

        if t == "module_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                mod_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                nid = _make_id(stem, mod_name)
                add_node(nid, mod_name, line)
                add_edge(file_nid, nid, "defines", line)
                for child in node.children:
                    walk(child, nid)
                return

        elif t in ("function_declaration", "function_prototype"):
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                parent = module_nid or file_nid
                nid = _make_id(parent, func_name)
                add_node(nid, f"{func_name}()", line)
                add_edge(parent, nid, "contains", line)

        elif t == "task_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                task_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                parent = module_nid or file_nid
                nid = _make_id(parent, task_name)
                add_node(nid, task_name, line)
                add_edge(parent, nid, "contains", line)

        elif t == "package_import_declaration":
            for child in node.children:
                if child.type == "package_import_item":
                    pkg_text = _read_text(child, source)
                    pkg_name = pkg_text.split("::")[0].strip()
                    if pkg_name:
                        line = node.start_point[0] + 1
                        tgt_nid = _make_id(pkg_name)
                        add_node(tgt_nid, pkg_name, line)
                        src = module_nid or file_nid
                        add_edge(src, tgt_nid, "imports_from", line)

        elif t == "module_instantiation":
            # module_type instantiates another module
            type_node = node.child_by_field_name("module_type")
            if type_node and module_nid:
                inst_type = _read_text(type_node, source).strip()
                if inst_type:
                    line = node.start_point[0] + 1
                    tgt_nid = _make_id(inst_type)
                    add_node(tgt_nid, inst_type, line)
                    add_edge(module_nid, tgt_nid, "instantiates", line)

        for child in node.children:
            walk(child, module_nid)

    walk(root)
    return {"nodes": nodes, "edges": edges}


__all__ = ['extract_verilog']
