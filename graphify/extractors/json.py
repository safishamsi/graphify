from .core import *
from pathlib import Path


def extract_json(path: Path) -> dict:
    """Extract top-level keys, nested structure, and dependency edges from a .json file."""
    _JSON_MAX_BYTES = 1_048_576  # 1 MiB — skip large fixture dumps / GeoJSON blobs

    try:
        import tree_sitter_json as tsjson
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-json not installed"}

    try:
        # Bounded read instead of stat()+read() to eliminate TOCTOU (J-1):
        # read one byte beyond the limit so we can detect oversized files even
        # if the file grows between stat and read.
        with path.open("rb") as _f:
            source = _f.read(_JSON_MAX_BYTES + 1)
        if len(source) > _JSON_MAX_BYTES:
            return {"nodes": [], "edges": [], "error": "json file too large to index"}
        language = Language(tsjson.language())
        parser = Parser(language)
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    # Keys whose string values become imports (package.json dep blocks)
    _DEP_KEYS = frozenset({
        "dependencies", "devDependencies", "peerDependencies",
        "optionalDependencies", "bundleDependencies", "bundledDependencies",
    })

    def add_node(nid: str, label: str, line: int) -> None:
        if nid and nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 context: str | None = None) -> None:
        if not src or not tgt or src == tgt:
            return
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": "EXTRACTED", "source_file": str_path,
                "source_location": f"L{line}", "weight": 1.0}
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def _key_text(pair_node) -> str | None:
        """Extract the string content of a pair's key."""
        key_node = pair_node.child_by_field_name("key")
        if key_node is None:
            return None
        if key_node.type == "string":
            content = key_node.child_by_field_name("string_content")
            if content:
                return _read_text(content, source)
            # fallback: strip surrounding quotes
            raw = _read_text(key_node, source)
            return raw.strip('"\'')
        return _read_text(key_node, source)

    def _val_node(pair_node):
        return pair_node.child_by_field_name("value")

    def walk_object(obj_node, parent_nid: str, parent_key: str | None,
                    depth: int, pair_count: list) -> None:
        if depth > 6:
            return
        for child in obj_node.children:
            if child.type != "pair":
                continue
            if pair_count[0] >= 500:  # check per-pair so the cap is honoured exactly (J-3)
                return
            pair_count[0] += 1
            key = _key_text(child)
            if not key:
                continue
            key_nid = _make_id(stem, *(([parent_key] if parent_key else []) + [key]))
            if not key_nid:
                continue
            line = child.start_point[0] + 1
            add_node(key_nid, key, line)
            add_edge(parent_nid, key_nid, "contains", line)

            val = _val_node(child)
            if val is None:
                continue

            if val.type == "object":
                walk_object(val, key_nid, key, depth + 1, pair_count)

            elif val.type == "array":
                # For "extends" arrays (tsconfig, eslint): each string element.
                # Prefix with "ref_" so external refs don't collide with real
                # code/file node IDs that share the same collapsed _make_id (J-4).
                for item in val.children:
                    if item.type == "string":
                        content = item.child_by_field_name("string_content")
                        ref = _read_text(content, source) if content else _read_text(item, source).strip('"\'')
                        if ref:
                            ref_nid = _make_id("ref", ref)
                            if ref_nid:
                                add_edge(key_nid, ref_nid, "extends", line, context="import")

            elif val.type == "string":
                content = val.child_by_field_name("string_content")
                val_text = _read_text(content, source) if content else _read_text(val, source).strip('"\'')

                if key == "extends" and val_text:
                    # Namespace external refs to avoid ID collision with file nodes (J-4)
                    ref_nid = _make_id("ref", val_text)
                    if ref_nid:
                        add_edge(file_nid, ref_nid, "extends", line, context="import")

                elif key == "$ref" and val_text:
                    # Namespace $ref values to prevent edge hijacking into code nodes (J-4)
                    ref_nid = _make_id("ref", val_text)
                    if ref_nid:
                        add_edge(parent_nid, ref_nid, "references", line)

                elif parent_key in _DEP_KEYS and val_text:
                    dep_nid = _make_id(key)
                    if dep_nid:
                        add_edge(key_nid, dep_nid, "imports", line, context="import")

    # Entry: find root document → object
    doc = root
    if doc.type == "document" and doc.child_count > 0:
        doc = doc.children[0]
    if doc.type == "object":
        walk_object(doc, file_nid, None, 0, [0])

    return {"nodes": nodes, "edges": edges}


__all__ = ['extract_json']
