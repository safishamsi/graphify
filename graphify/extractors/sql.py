from .core import *
import re
from pathlib import Path


def extract_sql(path: Path) -> dict:
    """Extract tables, views, functions, and relationships from .sql files via tree-sitter."""
    try:
        import tree_sitter_sql as tssql
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_sql not installed. Run: pip install tree-sitter-sql"}

    try:
        language = Language(tssql.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    file_nid = _make_id(str_path)
    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                           "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = {file_nid}
    table_nids: dict[str, str] = {}  # name → nid for reference resolution

    def _read(n) -> str:
        return source[n.start_byte:n.end_byte].decode("utf-8", errors="replace")

    def _obj_name(n) -> str | None:
        for c in n.children:
            if c.type == "object_reference":
                return _read(c)
        return None

    def _add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                           "source_file": str_path, "source_location": f"L{line}"})
            edges.append({"source": file_nid, "target": nid, "relation": "contains",
                           "confidence": "EXTRACTED", "source_file": str_path,
                           "source_location": f"L{line}", "weight": 1.0})

    def _add_edge(src: str, tgt: str, relation: str, line: int) -> None:
        edges.append({"source": src, "target": tgt, "relation": relation,
                       "confidence": "EXTRACTED", "source_file": str_path,
                       "source_location": f"L{line}", "weight": 1.0})

    def walk(node) -> None:
        t = node.type
        line = node.start_point[0] + 1

        if t == "create_table":
            name = _obj_name(node)
            if name:
                nid = _make_id(stem, name)
                _add_node(nid, name, line)
                table_nids[name.lower()] = nid
                # Foreign key REFERENCES
                for col in node.children:
                    if col.type == "column_definitions":
                        has_error = any(cd.type == "ERROR" for cd in col.children)
                        seen_refs: set[str] = set()
                        for cd in col.children:
                            if cd.type == "column_definition":
                                # Inline column-level REFERENCES
                                ref_name: str | None = None
                                found_ref = False
                                for cc in cd.children:
                                    if cc.type == "keyword_references":
                                        found_ref = True
                                    elif found_ref and cc.type == "object_reference":
                                        ref_name = _read(cc)
                                        break
                                if ref_name:
                                    ref_nid = table_nids.get(ref_name.lower()) or _make_id(stem, ref_name)
                                    _add_edge(nid, ref_nid, "references", line)
                                    seen_refs.add(ref_name.lower())
                            elif cd.type == "constraints":
                                # Table-level FOREIGN KEY ... REFERENCES ... constraints
                                for constraint in cd.children:
                                    if constraint.type != "constraint":
                                        continue
                                    ref_name = None
                                    found_ref = False
                                    for cc in constraint.children:
                                        if cc.type == "keyword_references":
                                            found_ref = True
                                        elif found_ref and cc.type == "object_reference":
                                            ref_name = _read(cc)
                                            break
                                    if ref_name:
                                        ref_nid = table_nids.get(ref_name.lower()) or _make_id(stem, ref_name)
                                        _add_edge(nid, ref_nid, "references", line)
                                        seen_refs.add(ref_name.lower())
                        if has_error:
                            # Dialect-specific syntax (e.g. Firebird COMPUTED BY) causes ERROR
                            # nodes that make the parser drop the trailing constraints block.
                            # Regex-scan the raw column_definitions text as fallback.
                            col_text = _read(col)
                            for rm in re.finditer(r"\bREFERENCES\s+([\w$]+)", col_text, re.IGNORECASE):
                                ref_name = rm.group(1)
                                if ref_name.lower() not in seen_refs:
                                    ref_nid = table_nids.get(ref_name.lower()) or _make_id(stem, ref_name)
                                    _add_edge(nid, ref_nid, "references", line)
                                    seen_refs.add(ref_name.lower())

        elif t == "create_view":
            name = _obj_name(node)
            if name:
                nid = _make_id(stem, name)
                _add_node(nid, name, line)
                table_nids[name.lower()] = nid
                # FROM/JOIN table references inside view body
                _walk_from_refs(node, nid, line)

        elif t == "create_function":
            name = _obj_name(node)
            if name:
                nid = _make_id(stem, name)
                _add_node(nid, f"{name}()", line)
                _walk_from_refs(node, nid, line)

        elif t == "create_procedure":
            name = _obj_name(node)
            if name:
                nid = _make_id(stem, name)
                _add_node(nid, f"{name}()", line)
                _walk_from_refs(node, nid, line)

        elif t == "alter_table":
            name = _obj_name(node)
            if name:
                src_nid = table_nids.get(name.lower())
                if not src_nid:
                    src_nid = _make_id(stem, name)
                    _add_node(src_nid, name, line)
                    table_nids[name.lower()] = src_nid
                for child in node.children:
                    if child.type == "add_constraint":
                        for cc in child.children:
                            if cc.type != "constraint":
                                continue
                            found_ref = False
                            ref_name: str | None = None
                            for ccc in cc.children:
                                if ccc.type == "keyword_references":
                                    found_ref = True
                                elif found_ref and ccc.type == "object_reference":
                                    ref_name = _read(ccc)
                                    break
                            if ref_name:
                                ref_nid = table_nids.get(ref_name.lower())
                                if not ref_nid:
                                    ref_nid = _make_id(stem, ref_name)
                                _add_edge(src_nid, ref_nid, "references", line)

        elif t == "create_trigger":
            trig_name: str | None = None
            tbl_name: str | None = None
            after_trigger = False
            after_for = False
            for c in node.children:
                if c.type == "keyword_trigger":
                    after_trigger = True
                elif after_trigger and not trig_name and c.type == "object_reference":
                    trig_name = _read(c)
                elif c.type == "keyword_for":
                    after_for = True
                elif after_for and not tbl_name and c.type == "object_reference":
                    tbl_name = _read(c)
            if trig_name:
                trig_nid = _make_id(stem, trig_name)
                _add_node(trig_nid, trig_name, line)
                if tbl_name:
                    tbl_nid = table_nids.get(tbl_name.lower()) or _make_id(stem, tbl_name)
                    _add_edge(trig_nid, tbl_nid, "triggers", line)

        elif t == "fb_proc_or_trigger":
            text = _read(node)
            m = re.match(
                r"CREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?"
                r"(PROCEDURE|TRIGGER|FUNCTION)\s+([\w$]+)",
                text, re.IGNORECASE,
            )
            if m:
                obj_type = m.group(1).upper()
                obj_name = m.group(2)
                obj_nid = _make_id(stem, obj_name)
                label = obj_name if obj_type == "TRIGGER" else f"{obj_name}()"
                _add_node(obj_nid, label, line)
                if obj_type == "TRIGGER":
                    fm = re.search(r"\bFOR\s+([\w$]+)", text, re.IGNORECASE)
                    if fm:
                        tbl = fm.group(1)
                        tbl_nid = table_nids.get(tbl.lower()) or _make_id(stem, tbl)
                        _add_edge(obj_nid, tbl_nid, "triggers", line)
                _NON_TABLES = {
                    "select", "where", "set", "dual", "null", "true", "false",
                    "first", "skip", "rows", "next", "only", "lateral",
                }
                seen_tbls: set[str] = set()
                for rm in re.finditer(r"\b(?:FROM|JOIN|INTO)\s+([\w$]+)", text, re.IGNORECASE):
                    tbl = rm.group(1)
                    if tbl.lower() not in _NON_TABLES and tbl.lower() not in seen_tbls:
                        seen_tbls.add(tbl.lower())
                        tbl_nid = table_nids.get(tbl.lower()) or _make_id(stem, tbl)
                        _add_edge(obj_nid, tbl_nid, "reads_from", line)
                for rm in re.finditer(r"\bUPDATE\s+([\w$]+)", text, re.IGNORECASE):
                    tbl = rm.group(1)
                    if tbl.lower() not in _NON_TABLES and tbl.lower() not in seen_tbls:
                        seen_tbls.add(tbl.lower())
                        tbl_nid = table_nids.get(tbl.lower()) or _make_id(stem, tbl)
                        _add_edge(obj_nid, tbl_nid, "reads_from", line)

        for child in node.children:
            walk(child)

    def _walk_from_refs(node, caller_nid: str, line: int) -> None:
        """Recursively find FROM/JOIN table references inside a node."""
        if node.type in ("from", "join"):
            for c in node.children:
                if c.type == "relation":
                    for cc in c.children:
                        if cc.type == "object_reference":
                            tbl = _read(cc)
                            tbl_nid = _make_id(stem, tbl)
                            _add_edge(caller_nid, tbl_nid, "reads_from",
                                      c.start_point[0] + 1)
        for child in node.children:
            _walk_from_refs(child, caller_nid, line)

    for stmt in root.children:
        if stmt.type == "statement":
            for child in stmt.children:
                walk(child)
        elif stmt.type in ("fb_proc_or_trigger", "set_term", "declare_external_function"):
            walk(stmt)

    # Global regex fallback: catch any REFERENCES missed due to ERROR nodes in the parse tree
    # (e.g. Firebird COMPUTED BY columns push constraints out of the tree entirely).
    # Snapshot after tree walk so we don't re-emit edges already captured above.
    emitted = {(e["source"], e["target"]) for e in edges if e["relation"] == "references"}
    src_text = source.decode("utf-8", errors="replace")
    for m in re.finditer(r"CREATE\s+TABLE\s+([\w$]+)\s*\(", src_text, re.IGNORECASE):
        tbl_name = m.group(1)
        tbl_nid = table_nids.get(tbl_name.lower())
        if tbl_nid is None:
            continue
        tbl_line = src_text[: m.start()].count("\n") + 1
        tail = src_text[m.start():]
        end = re.search(r"(?:^|\n)(?:CREATE|SET\s+TERM|ALTER)\s", tail[1:], re.IGNORECASE)
        block = tail[: end.start() + 1] if end else tail
        for rm in re.finditer(r"\bREFERENCES\s+([\w$]+)", block, re.IGNORECASE):
            ref_name = rm.group(1)
            ref_nid = table_nids.get(ref_name.lower()) or _make_id(stem, ref_name)
            if (tbl_nid, ref_nid) not in emitted:
                _add_edge(tbl_nid, ref_nid, "references", tbl_line)
                emitted.add((tbl_nid, ref_nid))

    return {"nodes": nodes, "edges": edges}


__all__ = ['extract_sql']
