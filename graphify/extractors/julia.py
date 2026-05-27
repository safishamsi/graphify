from .core import *
from pathlib import Path


# ── Julia extractor (custom walk) ────────────────────────────────────────────

def extract_julia(path: Path) -> dict:
    """Extract modules, structs, functions, imports, and calls from a .jl file."""
    try:
        import tree_sitter_julia as tsjulia
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-julia not installed"}

    try:
        language = Language(tsjulia.language())
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
    function_bodies: list[tuple[str, object]] = []

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

    def _func_name_from_signature(sig_node) -> str | None:
        """Extract function name from a Julia signature node (call_expression > identifier)."""
        for child in sig_node.children:
            if child.type == "call_expression":
                callee = child.children[0] if child.children else None
                if callee and callee.type == "identifier":
                    return _read_text(callee, source)
        return None

    def walk_calls(body_node, func_nid: str) -> None:
        if body_node is None:
            return
        t = body_node.type
        if t in ("function_definition", "short_function_definition"):
            return
        if t == "call_expression" and body_node.children:
            callee = body_node.children[0]
            # Direct call: foo(...)
            if callee.type == "identifier":
                callee_name = _read_text(callee, source)
                target_nid = _make_id(stem, callee_name)
                add_edge(func_nid, target_nid, "calls", body_node.start_point[0] + 1,
                         confidence="EXTRACTED", context="call")
            # Method call: obj.method(...)
            elif callee.type == "field_expression" and len(callee.children) >= 3:
                method_node = callee.children[-1]
                method_name = _read_text(method_node, source)
                target_nid = _make_id(stem, method_name)
                add_edge(func_nid, target_nid, "calls", body_node.start_point[0] + 1,
                         confidence="EXTRACTED", context="call")
        for child in body_node.children:
            walk_calls(child, func_nid)

    def walk(node, scope_nid: str) -> None:
        t = node.type

        # Module
        if t == "module_definition":
            name_node = next((c for c in node.children if c.type == "identifier"), None)
            if name_node:
                mod_name = _read_text(name_node, source)
                mod_nid = _make_id(stem, mod_name)
                line = node.start_point[0] + 1
                add_node(mod_nid, mod_name, line)
                add_edge(file_nid, mod_nid, "defines", line)
                for child in node.children:
                    walk(child, mod_nid)
            return

        # Struct (struct / mutable struct — both map to struct_definition in tree-sitter-julia)
        if t == "struct_definition":
            # type_head may contain: identifier (simple) or binary_expression (Foo <: Bar)
            type_head = next((c for c in node.children if c.type == "type_head"), None)
            if type_head:
                bin_expr = next((c for c in type_head.children if c.type == "binary_expression"), None)
                if bin_expr:
                    # First identifier is the struct name, last is the supertype
                    identifiers = [c for c in bin_expr.children if c.type == "identifier"]
                    if identifiers:
                        struct_name = _read_text(identifiers[0], source)
                        struct_nid = _make_id(stem, struct_name)
                        line = node.start_point[0] + 1
                        add_node(struct_nid, struct_name, line)
                        add_edge(scope_nid, struct_nid, "defines", line)
                        if len(identifiers) >= 2:
                            super_name = _read_text(identifiers[-1], source)
                            add_edge(struct_nid, _make_id(stem, super_name), "inherits",
                                     line, confidence="EXTRACTED")
                else:
                    name_node = next((c for c in type_head.children if c.type == "identifier"), None)
                    if name_node:
                        struct_name = _read_text(name_node, source)
                        struct_nid = _make_id(stem, struct_name)
                        line = node.start_point[0] + 1
                        add_node(struct_nid, struct_name, line)
                        add_edge(scope_nid, struct_nid, "defines", line)
            return

        # Abstract type
        if t == "abstract_definition":
            # type_head > identifier
            type_head = next((c for c in node.children if c.type == "type_head"), None)
            if type_head:
                name_node = next((c for c in type_head.children if c.type == "identifier"), None)
                if name_node:
                    abs_name = _read_text(name_node, source)
                    abs_nid = _make_id(stem, abs_name)
                    line = node.start_point[0] + 1
                    add_node(abs_nid, abs_name, line)
                    add_edge(scope_nid, abs_nid, "defines", line)
            return

        # Function: function foo(...) ... end
        if t == "function_definition":
            sig_node = next((c for c in node.children if c.type == "signature"), None)
            if sig_node:
                func_name = _func_name_from_signature(sig_node)
                if func_name:
                    func_nid = _make_id(stem, func_name)
                    line = node.start_point[0] + 1
                    add_node(func_nid, f"{func_name}()", line)
                    add_edge(scope_nid, func_nid, "defines", line)
                    function_bodies.append((func_nid, node))
            return

        # Short function: foo(x) = expr
        if t == "assignment":
            lhs = node.children[0] if node.children else None
            if lhs and lhs.type == "call_expression" and lhs.children:
                callee = lhs.children[0]
                if callee.type == "identifier":
                    func_name = _read_text(callee, source)
                    func_nid = _make_id(stem, func_name)
                    line = node.start_point[0] + 1
                    add_node(func_nid, f"{func_name}()", line)
                    add_edge(scope_nid, func_nid, "defines", line)
                    # Only walk the RHS (index 2 after lhs and operator) to avoid self-loops
                    rhs = node.children[-1] if len(node.children) >= 3 else None
                    if rhs:
                        function_bodies.append((func_nid, rhs))
            return

        # Using / Import
        if t in ("using_statement", "import_statement"):
            line = node.start_point[0] + 1
            for child in node.children:
                if child.type == "identifier":
                    mod_name = _read_text(child, source)
                    imp_nid = _make_id(mod_name)
                    add_node(imp_nid, mod_name, line)
                    add_edge(scope_nid, imp_nid, "imports", line, context="import")
                elif child.type == "selected_import":
                    identifiers = [c for c in child.children if c.type == "identifier"]
                    if identifiers:
                        pkg_name = _read_text(identifiers[0], source)
                        pkg_nid = _make_id(pkg_name)
                        add_node(pkg_nid, pkg_name, line)
                        add_edge(scope_nid, pkg_nid, "imports", line, context="import")
            return

        for child in node.children:
            walk(child, scope_nid)

    walk(root, file_nid)

    for func_nid, body_node in function_bodies:
        # For function_definition nodes, walk children directly to avoid
        # the boundary check returning early on the top-level node itself.
        # Skip the "signature" child — it contains the function's own call_expression
        # which would create a self-loop.
        if body_node.type == "function_definition":
            for child in body_node.children:
                if child.type != "signature":
                    walk_calls(child, func_nid)
        else:
            walk_calls(body_node, func_nid)

    return {"nodes": nodes, "edges": edges}


_FORTRAN_CPP_EXTS = {".F", ".F90", ".F95", ".F03", ".F08"}


def _cpp_preprocess(path: Path) -> bytes:
    """Run cpp -w -P on a capital-F Fortran file and return preprocessed bytes.

    Falls back to raw file bytes if cpp is not available. Capital-F extensions
    conventionally require C preprocessor expansion (#ifdef MPI, #define REAL8, etc.)
    before parsing.

    Security (F-007): we pass `-nostdinc` and `-I /dev/null` so a malicious
    source file containing `#include "/home/victim/.ssh/id_rsa"` (or any other
    include directive) cannot inline arbitrary host files into the output that
    we then ship to an LLM. Without these flags `cpp` happily resolves any
    relative or absolute include path it can read, which is a corpus-side
    file-exfiltration vector.
    """
    import shutil
    import subprocess
    if not shutil.which("cpp"):
        return path.read_bytes()
    try:
        result = subprocess.run(
            ["cpp", "-w", "-P", "-nostdinc", "-I", "/dev/null", str(path)],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except Exception:
        pass
    return path.read_bytes()


def extract_fortran(path: Path) -> dict:
    """Extract programs, modules, subroutines, functions, use statements, and calls from Fortran files.

    Capital-F extensions (.F, .F90, etc.) are run through the C preprocessor before
    parsing so #ifdef/#define macros are resolved.
    """
    try:
        import tree_sitter_fortran as tsfortran
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-fortran not installed"}

    try:
        language = Language(tsfortran.language())
        parser = Parser(language)
        source = _cpp_preprocess(path) if path.suffix in _FORTRAN_CPP_EXTS else path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    scope_bodies: list[tuple[str, object]] = []

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

    def _fortran_name(stmt_node) -> str | None:
        """Extract name from a *_statement node. Fortran is case-insensitive; lowercase."""
        for child in stmt_node.children:
            if child.type in ("name", "identifier"):
                return _read_text(child, source).lower()
        return None

    def walk_calls(node, scope_nid: str) -> None:
        if node is None:
            return
        t = node.type
        if t in ("subroutine", "function", "module", "program", "internal_procedures"):
            return
        # call FOO(args) — tree-sitter-fortran uses subroutine_call
        if t == "subroutine_call":
            name_node = next((c for c in node.children if c.type == "identifier"), None)
            if name_node:
                callee = _read_text(name_node, source).lower()
                target_nid = _make_id(stem, callee)
                add_edge(scope_nid, target_nid, "calls", node.start_point[0] + 1,
                         confidence="EXTRACTED", context="call")
        for child in node.children:
            walk_calls(child, scope_nid)

    def walk(node, scope_nid: str) -> None:
        t = node.type

        if t == "program":
            stmt = next((c for c in node.children if c.type == "program_statement"), None)
            name = _fortran_name(stmt) if stmt else None
            if name:
                nid = _make_id(stem, name)
                line = node.start_point[0] + 1
                add_node(nid, name, line)
                add_edge(file_nid, nid, "defines", line)
                scope_bodies.append((nid, node))
                for child in node.children:
                    walk(child, nid)
            return

        if t == "module":
            stmt = next((c for c in node.children if c.type == "module_statement"), None)
            name = _fortran_name(stmt) if stmt else None
            if name:
                nid = _make_id(stem, name)
                line = node.start_point[0] + 1
                add_node(nid, name, line)
                add_edge(file_nid, nid, "defines", line)
                for child in node.children:
                    walk(child, nid)
            return

        # subroutines/functions inside a module live under internal_procedures
        if t == "internal_procedures":
            for child in node.children:
                walk(child, scope_nid)
            return

        if t == "subroutine":
            stmt = next((c for c in node.children if c.type == "subroutine_statement"), None)
            name = _fortran_name(stmt) if stmt else None
            if name:
                nid = _make_id(stem, name)
                line = node.start_point[0] + 1
                add_node(nid, f"{name}()", line)
                add_edge(scope_nid, nid, "defines", line)
                scope_bodies.append((nid, node))
                for child in node.children:
                    walk(child, nid)
            return

        if t == "function":
            stmt = next((c for c in node.children if c.type == "function_statement"), None)
            name = _fortran_name(stmt) if stmt else None
            if name:
                nid = _make_id(stem, name)
                line = node.start_point[0] + 1
                add_node(nid, f"{name}()", line)
                add_edge(scope_nid, nid, "defines", line)
                scope_bodies.append((nid, node))
                for child in node.children:
                    walk(child, nid)
            return

        if t == "use_statement":
            line = node.start_point[0] + 1
            # tree-sitter-fortran uses module_name node for the used module
            name_node = next((c for c in node.children if c.type in ("module_name", "name", "identifier")), None)
            if name_node:
                mod_name = _read_text(name_node, source).lower()
                imp_nid = _make_id(mod_name)
                add_node(imp_nid, mod_name, line)
                add_edge(scope_nid, imp_nid, "imports", line, context="use")
            return

        for child in node.children:
            walk(child, scope_nid)

    walk(root, file_nid)

    _stmt_headers = {
        "subroutine_statement", "function_statement",
        "program_statement", "module_statement",
    }
    for scope_nid, body_node in scope_bodies:
        for child in body_node.children:
            if child.type not in _stmt_headers:
                walk_calls(child, scope_nid)

    return {"nodes": nodes, "edges": edges}


__all__ = ['extract_julia', '_FORTRAN_CPP_EXTS', '_cpp_preprocess', 'extract_fortran']
