from .core import *
import re
from pathlib import Path
from typing import Any


# ── Pascal / Delphi extractor ─────────────────────────────────────────────────

_pascal_unit_cache: dict[str, dict[str, str]] = {}
_pascal_class_stem_cache: dict[str, dict[str, str]] = {}  # root_key → {stem_lower: _file_stem}


def _pascal_project_root(from_path: Path) -> Path:
    """Return the highest ancestor directory that looks like a Pascal project root.

    Walks up the directory tree and tracks the topmost directory that:
      - is NOT a filesystem root (e.g. D:/, C:/, /)
      - has at least 2 .pas files OR at least 1 .dpr file as direct children

    The minimum-2 threshold avoids treating a level as the root just because a
    single stray .pas file was copied there.  The filesystem-root exclusion
    prevents overshoot on drives that have a stray file directly at D:/.

    Falls back to from_path.parent if nothing better is found.
    """
    best = from_path.parent
    current = from_path.parent
    for _ in range(12):
        if len(current.parts) <= 1:
            break  # never use a filesystem root (D:/, C:/, /)
        pas_count = sum(1 for _ in current.glob("*.pas"))
        dpr_count = sum(1 for _ in current.glob("*.dpr"))
        if pas_count >= 2 or dpr_count >= 1:
            best = current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return best


def _pascal_resolve_unit(from_path: Path, unit_name: str) -> str:
    """Resolve a Pascal unit name to the graphify node ID of its source file.

    Scans all Pascal files under the project root (the highest ancestor that
    directly contains .pas/.dpr files) and returns _make_id(str(matched_path)).
    Result is cached per project root so the rglob runs at most once per
    project.  Falls back to _make_id(unit_name) for units not found on disk
    (e.g. standard RTL units like SysUtils, Windows).
    """
    root = _pascal_project_root(from_path)
    root_key = str(root)
    if root_key not in _pascal_unit_cache:
        unit_map: dict[str, str] = {}
        for ext in (".pas", ".pp", ".dpr", ".dpk", ".inc"):
            for f in root.rglob("*" + ext):
                unit_map[f.stem.lower()] = _make_id(str(f))
        _pascal_unit_cache[root_key] = unit_map
    return _pascal_unit_cache[root_key].get(unit_name.lower(), _make_id(unit_name))


def _pascal_resolve_class(from_path: Path, class_name: str) -> str | None:
    """Resolve a Pascal class/interface name to the node ID of its defining file's class node.

    Pascal convention: TFooBar is defined in FooBar.pas, IFooBar in FooBar.pas.
    Strips the leading T/I prefix, finds the file, and returns
    _make_id(_file_stem(found_file), class_name).

    Returns None when no matching file is found on disk (RTL, stdlib, or
    unconventionally-named class — caller should create a stub node).
    """
    prefix = class_name[:1]
    unit_name = class_name[1:] if prefix in ("T", "I") else class_name

    root = _pascal_project_root(from_path)
    root_key = str(root)
    if root_key not in _pascal_class_stem_cache:
        stem_map: dict[str, str] = {}
        for ext in (".pas", ".pp", ".dpr", ".dpk"):
            for f in root.rglob("*" + ext):
                stem_map[f.stem.lower()] = _file_stem(f)
        _pascal_class_stem_cache[root_key] = stem_map

    file_stem = _pascal_class_stem_cache[root_key].get(unit_name.lower())
    if file_stem:
        return _make_id(file_stem, class_name)
    return None


_PAS_TOKEN_RE = re.compile(
    r"'(?:''|[^'])*'"
    r"|\{[^}]*\}"
    r"|\(\*.*?\*\)"
    r"|//[^\n]*",
    re.DOTALL,
)
_PAS_MODULE_RE = re.compile(
    r"\b(unit|program|library)\s+([A-Za-z_][\w.]*)\s*;",
    re.IGNORECASE,
)
_PAS_USES_RE = re.compile(
    r"\buses\b\s*([^;]+);",
    re.IGNORECASE | re.DOTALL,
)
_PAS_TYPE_HEADER_RE = re.compile(
    r"\b(?P<name>[A-Za-z_]\w*)(?:\s*<[^>]+>)?\s*=\s*(?:packed\s+)?"
    r"(?P<kind>class|interface)\b"
    r"(?:\s*\(\s*(?P<bases>[^)]*)\s*\))?",
    re.IGNORECASE,
)
_PAS_END_SEMI_RE = re.compile(r"\bend\s*;", re.IGNORECASE)
_PAS_METHOD_DECL_RE = re.compile(
    r"\b(?:procedure|function|constructor|destructor)\s+"
    r"(?P<name>[A-Za-z_]\w*)"
    r"(?:\s*\([^)]*\))?"
    r"(?:\s*:\s*[\w<>,\s.]+)?"
    r"\s*;",
    re.IGNORECASE,
)
_PAS_IMPL_HEADER_RE = re.compile(
    r"\b(?:procedure|function|constructor|destructor)\s+"
    r"(?P<qual>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)"
    r"(?:\s*<[^>]+>)?"
    r"(?:\s*\([^)]*\))?"
    r"(?:\s*:\s*[\w<>,\s.]+)?"
    r"\s*;",
    re.IGNORECASE,
)
_PAS_BEGIN_END_TOKEN_RE = re.compile(
    r"\b(begin|end|case|try|asm|record)\b", re.IGNORECASE
)
_PAS_CALL_RE = re.compile(r"\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*[(;]")
_PAS_KEYWORDS = frozenset({
    "begin", "end", "if", "then", "else", "while", "do", "for", "to",
    "downto", "repeat", "until", "case", "of", "try", "finally", "except",
    "with", "inherited", "result", "var", "const", "type", "nil", "true",
    "false", "exit", "break", "continue", "uses", "unit", "program",
    "library", "interface", "implementation", "initialization", "finalization",
    "procedure", "function", "constructor", "destructor", "class", "record",
    "object", "array", "string", "integer", "boolean", "real", "char",
    "writeln", "write", "readln", "read", "assigned", "length", "high",
    "low", "inc", "dec", "new", "dispose", "setlength", "copy", "pos",
    "trim", "format", "inttostr", "strtoint", "ord", "chr", "sizeof",
    "create", "free", "destroy",
})


def _pascal_strip_comments(text: str) -> str:
    """Strip Pascal comments ({}, (* *), //) while preserving newlines."""
    def _sub(m: re.Match) -> str:
        tok = m.group(0)
        if tok.startswith("'"):
            return tok
        return "".join(c if c == "\n" else " " for c in tok)
    return _PAS_TOKEN_RE.sub(_sub, text)


def _pascal_split_sections(text: str) -> tuple[str, int, str, int]:
    """Split into (iface_text, iface_offset, impl_text, impl_offset).
    Files without interface/implementation sections (dpr/lpr/inc) return
    the whole text as impl with offset 0.
    """
    iface_m = re.search(r"\binterface\b", text, re.IGNORECASE)
    impl_m = re.search(r"\bimplementation\b", text, re.IGNORECASE)
    if iface_m and impl_m:
        iface_off = iface_m.end()
        impl_off = impl_m.end()
        end_m = re.search(
            r"\b(initialization|finalization)\b", text[impl_off:], re.IGNORECASE
        )
        impl_end = impl_off + end_m.start() if end_m else len(text)
        return text[iface_off:impl_m.start()], iface_off, text[impl_off:impl_end], impl_off
    return "", 0, text, 0


def _pascal_split_uses(s: str) -> list[str]:
    """Split a uses list string, handling 'Foo in ''bar.pas''' syntax."""
    out = []
    for chunk in s.split(","):
        name = re.split(r"\s+in\s+", chunk.strip(), maxsplit=1, flags=re.IGNORECASE)[0]
        name = name.strip().strip(";")
        if name and re.match(r"[A-Za-z_][\w.]*$", name):
            out.append(name)
    return out


def _pascal_split_bases(s: str) -> list[str]:
    """Split inheritance list, handling generics like TList<T, U>."""
    out, depth, buf = [], 0, []
    for ch in s:
        if ch == "<":
            depth += 1
            buf.append(ch)
        elif ch == ">":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            name = re.sub(r"<.*$", "", "".join(buf).strip())
            if name:
                out.append(name)
            buf = []
        else:
            buf.append(ch)
    name = re.sub(r"<.*$", "", "".join(buf).strip())
    if name:
        out.append(name)
    return [n for n in out if re.match(r"[A-Za-z_]\w*$", n)]


def _pascal_find_body(text: str, start: int) -> tuple[int, int]:
    """Find balanced begin..end after start. Returns (body_start, body_end).
    Returns (0, 0) if no begin found.
    """
    m = re.search(r"\bbegin\b", text[start:], re.IGNORECASE)
    if not m:
        return (0, 0)
    body_start = start + m.end()
    depth = 1
    for tok in _PAS_BEGIN_END_TOKEN_RE.finditer(text, body_start):
        kw = tok.group(1).lower()
        if kw in ("begin", "case", "try", "asm", "record"):
            depth += 1
        elif kw == "end":
            depth -= 1
            if depth == 0:
                return (body_start, tok.start())
    return (body_start, len(text))


def _extract_pascal_regex(path: Path) -> dict:
    """Regex fallback for Pascal/Delphi extraction when tree-sitter-pascal
    is unavailable. Produces the same node/edge schema as the tree-sitter pass.
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    str_path = str(path)
    stem = _file_stem(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_call_pairs: set[tuple[str, str]] = set()

    def _add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            })

    def _add_edge(src: str, tgt: str, relation: str, line: int, context: str | None = None) -> None:
        edge: dict = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    def _lineno(text: str, offset: int) -> int:
        return text.count("\n", 0, offset) + 1

    file_nid = _make_id(str_path)
    _add_node(file_nid, path.name, 1)

    stripped = _pascal_strip_comments(raw)

    # Module header
    module_nid = file_nid
    mod_m = _PAS_MODULE_RE.search(stripped)
    if mod_m:
        mod_name = mod_m.group(2)
        module_nid = _make_id(stem, mod_name)
        _add_node(module_nid, mod_name, _lineno(stripped, mod_m.start()))
        _add_edge(file_nid, module_nid, "contains", _lineno(stripped, mod_m.start()))

    iface_text, iface_off, impl_text, impl_off = _pascal_split_sections(stripped)

    # Uses clauses
    for section_text, section_off in ((iface_text, iface_off), (impl_text, impl_off)):
        for um in _PAS_USES_RE.finditer(section_text):
            line = _lineno(stripped, section_off + um.start())
            for unit_name in _pascal_split_uses(um.group(1)):
                tgt_nid = _pascal_resolve_unit(path, unit_name)
                _add_edge(module_nid, tgt_nid, "imports", line, context="import")

    # Type declarations (classes / interfaces) in interface section
    search_text = iface_text if iface_text else stripped
    search_off = iface_off if iface_text else 0
    pos = 0
    while pos < len(search_text):
        hm = _PAS_TYPE_HEADER_RE.search(search_text, pos)
        if not hm:
            break
        type_name = hm.group("name")
        bases_raw = hm.group("bases") or ""
        line = _lineno(stripped, search_off + hm.start())
        cls_nid = _make_id(stem, type_name)
        _add_node(cls_nid, type_name, line)
        _add_edge(module_nid, cls_nid, "contains", line)

        for base_name in _pascal_split_bases(bases_raw):
            resolved = _pascal_resolve_class(path, base_name)
            base_nid = resolved if resolved else _make_id(base_name)
            if base_nid not in seen_ids:
                _add_node(base_nid, base_name, line)
            _add_edge(cls_nid, base_nid, "inherits", line)

        # Find class body (up to next end;)
        end_m = _PAS_END_SEMI_RE.search(search_text, hm.end())
        body_text = search_text[hm.end():end_m.start()] if end_m else ""
        body_off = search_off + hm.end()

        # Forward method declarations inside the class body
        for mm in _PAS_METHOD_DECL_RE.finditer(body_text):
            mname = mm.group("name")
            mline = _lineno(stripped, body_off + mm.start())
            method_nid = _make_id(cls_nid, mname)
            _add_node(method_nid, f"{mname}()", mline)
            _add_edge(cls_nid, method_nid, "method", mline)

        pos = end_m.end() if end_m else len(search_text)

    # Implementation headers (procedure/function/constructor/destructor)
    impl_records: list[tuple[str, int, str]] = []
    for fm in _PAS_IMPL_HEADER_RE.finditer(impl_text):
        qualified = fm.group("qual")
        line = _lineno(stripped, impl_off + fm.start())
        if "." in qualified:
            cls_part, method_part = qualified.split(".", 1)
            cls_nid = _make_id(stem, cls_part)
            container = cls_nid if cls_nid in seen_ids else module_nid
            relation = "method" if cls_nid in seen_ids else "contains"
            label = f"{method_part}()"
        else:
            container, relation = module_nid, "contains"
            label = f"{qualified}()"
        proc_nid = _make_id(stem, qualified)
        _add_node(proc_nid, label, line)
        _add_edge(container, proc_nid, relation, line)

        body_start, body_end = _pascal_find_body(impl_text, fm.end())
        body_text = impl_text[body_start:body_end] if body_start else ""
        impl_records.append((proc_nid, line, body_text))

    # Intra-file call edges
    all_procs: dict[str, str] = {
        n["label"].removesuffix("()").lower(): n["id"]
        for n in nodes
        if n["id"] != file_nid and n["label"].endswith("()")
    }
    for caller_nid, caller_line, body_text in impl_records:
        for cm in _PAS_CALL_RE.finditer(body_text):
            callee_name = cm.group(1).split(".")[-1].lower()
            if callee_name in _PAS_KEYWORDS:
                continue
            callee_nid = all_procs.get(callee_name)
            if not callee_nid or callee_nid == caller_nid:
                continue
            pair = (caller_nid, callee_nid)
            if pair in seen_call_pairs:
                continue
            seen_call_pairs.add(pair)
            call_line = caller_line + body_text.count("\n", 0, cm.start())
            _add_edge(caller_nid, callee_nid, "calls", call_line, context="call")

    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}


def extract_pascal(path: Path) -> dict:
    """Extract units, classes, procedures, uses-imports, and calls from Pascal/Delphi files.

    Produces nodes for:
    - The file itself
    - unit / program / library declarations
    - class and interface type declarations
    - procedure / function implementations (including qualified TClass.Method names)

    Produces edges for:
    - file --contains--> module
    - module --imports--> other file node (via uses clause, resolved to path-based IDs)
    - class --inherits--> base class
    - class/module --contains--> method forward declaration
    - class/module --contains--> procedure/function implementation
    - procedure --calls--> other procedure (within the same file)

    Uses tree-sitter-pascal when available; falls back to a regex-based extractor
    (_extract_pascal_regex) when it isn't installed or fails to parse, so Pascal
    extraction works out of the box without an extra pip install.
    """
    try:
        import tree_sitter_pascal as tspascal
        from tree_sitter import Language, Parser
    except ImportError:
        return _extract_pascal_regex(path)

    try:
        language = Language(tspascal.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception:
        return _extract_pascal_regex(path)

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    proc_bodies: list[tuple[str, Any]] = []

    def _read(node) -> str:  # type: ignore[no-untyped-def]
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": label, "file_type": "code",
                "source_file": str_path, "source_location": f"L{line}",
            })

    def add_edge(
        src: str, tgt: str, relation: str, line: int,
        confidence: str = "EXTRACTED", weight: float = 1.0,
        context: str | None = None,
    ) -> None:
        edge: dict[str, Any] = {
            "source": src, "target": tgt, "relation": relation,
            "confidence": confidence, "source_file": str_path,
            "source_location": f"L{line}", "weight": weight,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)
    module_nid = file_nid

    def _proc_name(header_node) -> str | None:  # type: ignore[no-untyped-def]
        name_node = header_node.child_by_field_name("name")
        if name_node:
            return _read(name_node)
        for child in header_node.children:
            if child.type in ("identifier", "genericDot", "genericTpl"):
                return _read(child)
        return None

    def walk(node, parent_nid: str) -> None:  # type: ignore[no-untyped-def]
        nonlocal module_nid
        t = node.type
        line = node.start_point[0] + 1

        if t in ("unit", "program", "library"):
            name_node = next((c for c in node.children if c.type == "moduleName"), None)
            mod_name = _read(name_node) if name_node else path.stem
            mod_nid = _make_id(stem, mod_name)
            add_node(mod_nid, mod_name, line)
            add_edge(file_nid, mod_nid, "contains", line)
            module_nid = mod_nid
            for child in node.children:
                walk(child, mod_nid)
            return

        if t == "declUses":
            for child in node.children:
                if child.type == "moduleName":
                    mod_name = _read(child)
                    tgt_nid = _pascal_resolve_unit(path, mod_name)
                    add_edge(parent_nid, tgt_nid, "imports", line, context="import")
            return

        if t == "declType":
            type_name = None
            kind_node = None
            for child in node.children:
                if child.type == "identifier" and type_name is None:
                    type_name = _read(child)
                elif child.type in ("declClass", "declIntf", "declHelper") and kind_node is None:
                    kind_node = child
            if type_name and kind_node:
                cls_nid = _make_id(stem, type_name)
                add_node(cls_nid, type_name, line)
                add_edge(parent_nid, cls_nid, "contains", line)
                for child in kind_node.children:
                    if child.type == "typeref":
                        base_name = _read(child)
                        base_nid = _make_id(stem, base_name)
                        if base_nid not in seen_ids:
                            # Try cross-file resolution (TFooBar → FooBar.pas)
                            resolved = _pascal_resolve_class(path, base_name)
                            base_nid = resolved if resolved else _make_id(base_name)
                            if base_nid not in seen_ids:
                                # Stub for RTL/external/cross-file base classes
                                add_node(base_nid, base_name, line)
                        add_edge(cls_nid, base_nid, "inherits", line)
                for child in kind_node.children:
                    walk(child, cls_nid)
                return
            for child in node.children:
                walk(child, parent_nid)
            return

        if t == "declProcFwd":
            header = next((c for c in node.children if c.type == "declProc"), None)
            if header:
                name = _proc_name(header)
                if name and "." not in name:
                    method_nid = _make_id(parent_nid, name)
                    add_node(method_nid, f"{name}()", line)
                    add_edge(parent_nid, method_nid, "method", line)
            return

        if t == "defProc":
            header = next((c for c in node.children if c.type == "declProc"), None)
            body_node = next((c for c in node.children if c.type == "block"), None)
            if not header:
                for child in node.children:
                    walk(child, parent_nid)
                return
            name = _proc_name(header)
            if not name:
                for child in node.children:
                    walk(child, parent_nid)
                return
            container = parent_nid
            if "." in name:
                parts = name.split(".", 1)
                cls_nid = _make_id(stem, parts[0])
                if cls_nid in seen_ids:
                    container = cls_nid
                label = f"{parts[-1]}()"
            else:
                label = f"{name}()"
            proc_nid = _make_id(stem, name)
            add_node(proc_nid, label, line)
            add_edge(
                container, proc_nid,
                "method" if container != parent_nid else "contains",
                line,
            )
            if body_node:
                proc_bodies.append((proc_nid, body_node))
            return

        for child in node.children:
            walk(child, parent_nid)

    walk(root, file_nid)

    # Second pass: resolve calls inside procedure/function bodies
    all_procs: dict[str, str] = {
        n["label"].removesuffix("()").lower(): n["id"]
        for n in nodes if n["id"] != file_nid
    }
    seen_call_pairs: set[tuple[str, str]] = set()

    def walk_calls(node, caller_nid: str) -> None:  # type: ignore[no-untyped-def]
        if node.type == "exprCall":
            callee_text = None
            for child in node.children:
                if child.is_named and child.type not in ("exprArgs",):
                    callee_text = _read(child).split(".")[-1]
                    break
            if callee_text:
                callee_nid = all_procs.get(callee_text.lower())
                if callee_nid and callee_nid != caller_nid:
                    pair = (caller_nid, callee_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        add_edge(
                            caller_nid, callee_nid, "calls",
                            node.start_point[0] + 1, context="call",
                        )
        elif node.type == "statement":
            # Pascal bare procedure calls with no args: `Reset;`
            # tree-sitter represents these as statement → identifier (no exprCall wrapper)
            named = [c for c in node.children if c.is_named]
            if len(named) == 1 and named[0].type == "identifier":
                callee_text = _read(named[0])
                callee_nid = all_procs.get(callee_text.lower())
                if callee_nid and callee_nid != caller_nid:
                    pair = (caller_nid, callee_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        add_edge(
                            caller_nid, callee_nid, "calls",
                            node.start_point[0] + 1, context="call",
                        )
        for child in node.children:
            walk_calls(child, caller_nid)

    for proc_nid, body_node in proc_bodies:
        walk_calls(body_node, proc_nid)

    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}


def extract_lazarus_form(path: Path) -> dict:
    """Extract component hierarchy from Lazarus .lfm form files.

    .lfm is a text-based declarative format for UI component trees, structured as:
        object ComponentName: TClassName
          PropertyName = Value
          OnEvent = HandlerName
          object ChildName: TChildClass
            ...
          end
        end

    Produces nodes for:
    - The form file itself
    - Each component class encountered (TForm1, TButton, TPanel, ...)
    - Event handler names referenced by OnXxx properties

    Produces edges for:
    - file --contains--> root form class
    - parent component --contains--> child component class
    - component --references--> event handler (context: "event")
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    import re
    str_path = str(path)
    stem = _file_stem(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_edge_pairs: set[tuple[str, str, str]] = set()

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": label, "file_type": "code",
                "source_file": str_path, "source_location": f"L{line}",
            })

    def add_edge(
        src: str, tgt: str, relation: str, line: int,
        context: str | None = None,
    ) -> None:
        key = (src, tgt, relation)
        if key in seen_edge_pairs:
            return
        seen_edge_pairs.add(key)
        edge: dict[str, Any] = {
            "source": src, "target": tgt, "relation": relation,
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": f"L{line}", "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    obj_re = re.compile(r"^\s*object\s+\w+\s*:\s*(\w+)", re.IGNORECASE)
    event_re = re.compile(r"^\s*On\w+\s*=\s*(\w+)", re.IGNORECASE)
    end_re = re.compile(r"^\s*end\s*$", re.IGNORECASE)

    # Stack of node IDs representing the nesting of object...end blocks
    stack: list[str] = [file_nid]

    for lineno, line in enumerate(text.splitlines(), 1):
        m = obj_re.match(line)
        if m:
            class_name = m.group(1)
            nid = _make_id(stem, class_name)
            add_node(nid, class_name, lineno)
            add_edge(stack[-1], nid, "contains", lineno)
            stack.append(nid)
            continue

        m = event_re.match(line)
        if m and len(stack) > 1:
            handler = m.group(1)
            handler_nid = _make_id(stem, handler)
            add_node(handler_nid, f"{handler}()", lineno)
            add_edge(stack[-1], handler_nid, "references", lineno, context="event")
            continue

        if end_re.match(line) and len(stack) > 1:
            stack.pop()

    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}


def extract_delphi_form(path: Path) -> dict:
    """Extract component hierarchy from Delphi .dfm form files.

    .dfm files come in two formats:
    - Text (same `object Name: TClassName ... end` syntax as .lfm)
    - Binary (starts with a TPF0/FF0A magic header — unreadable as text)

    Binary .dfm files are skipped gracefully: an empty result is returned
    so the rest of the pipeline is unaffected.  Convert binary forms to
    text in the Delphi IDE via File → Save As (Text DFM) if you want them
    indexed.

    Text .dfm files are parsed identically to .lfm: component containment
    (`contains`) and event handler references (`references`, context "event").
    """
    try:
        raw = path.read_bytes()
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    # Detect binary DFM: Delphi binary resource streams start with FF 0A
    if raw[:2] == b"\xff\x0a":
        return {
            "nodes": [], "edges": [],
            "error": f"binary DFM (convert to text in Delphi IDE to index): {path.name}",
        }

    # Text DFM — delegate to the shared form parser (same syntax as .lfm)
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    import re
    str_path = str(path)
    stem = _file_stem(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_edge_pairs: set[tuple[str, str, str]] = set()

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": label, "file_type": "code",
                "source_file": str_path, "source_location": f"L{line}",
            })

    def add_edge(
        src: str, tgt: str, relation: str, line: int,
        context: str | None = None,
    ) -> None:
        key = (src, tgt, relation)
        if key in seen_edge_pairs:
            return
        seen_edge_pairs.add(key)
        edge: dict[str, Any] = {
            "source": src, "target": tgt, "relation": relation,
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": f"L{line}", "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    obj_re   = re.compile(r"^\s*object\s+\w+\s*:\s*(\w+)", re.IGNORECASE)
    event_re = re.compile(r"^\s*On\w+\s*=\s*(\w+)", re.IGNORECASE)
    end_re   = re.compile(r"^\s*end\s*$", re.IGNORECASE)
    stack: list[str] = [file_nid]

    for lineno, line in enumerate(text.splitlines(), 1):
        m = obj_re.match(line)
        if m:
            class_name = m.group(1)
            nid = _make_id(stem, class_name)
            add_node(nid, class_name, lineno)
            add_edge(stack[-1], nid, "contains", lineno)
            stack.append(nid)
            continue
        m = event_re.match(line)
        if m and len(stack) > 1:
            handler = m.group(1)
            handler_nid = _make_id(stem, handler)
            add_node(handler_nid, f"{handler}()", lineno)
            add_edge(stack[-1], handler_nid, "references", lineno, context="event")
            continue
        if end_re.match(line) and len(stack) > 1:
            stack.pop()

    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}


def extract_lazarus_package(path: Path) -> dict:
    """Extract package metadata from Lazarus .lpk package files (XML format).

    .lpk is an XML file listing the package name, required dependencies,
    and the Pascal units that belong to the package.

    Produces nodes for:
    - The package file itself
    - The package (by name)
    - Each required package (dependency)
    - Each listed unit file (resolved to path-based IDs where possible)

    Produces edges for:
    - file --contains--> package
    - package --imports--> required dependency (context: "import")
    - package --contains--> listed unit
    """
    try:
        import xml.etree.ElementTree as ET
        text = path.read_text(encoding="utf-8", errors="replace")
        xml_root = ET.fromstring(text)
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    str_path = str(path)
    stem = _file_stem(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": label, "file_type": "code",
                "source_file": str_path, "source_location": "L1",
            })

    def add_edge(src: str, tgt: str, relation: str, context: str | None = None) -> None:
        edge: dict[str, Any] = {
            "source": src, "target": tgt, "relation": relation,
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": "L1", "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name)

    name_elem = xml_root.find(".//Package/Name")
    pkg_name = name_elem.get("Value") if name_elem is not None else path.stem
    pkg_nid = _make_id(stem, pkg_name)
    add_node(pkg_nid, pkg_name)
    add_edge(file_nid, pkg_nid, "contains")

    # Required packages → imports edges
    for item in xml_root.findall(".//RequiredPkgs/"):
        dep_elem = item.find("PackageName")
        if dep_elem is not None:
            dep_name = dep_elem.get("Value", "")
            if dep_name:
                dep_nid = _make_id(dep_name)
                add_node(dep_nid, dep_name)
                add_edge(pkg_nid, dep_nid, "imports", context="import")

    # Listed units → contains edges, resolved to path-based IDs where possible
    for item in xml_root.findall(".//Files/"):
        unit_elem = item.find("UnitName")
        if unit_elem is not None:
            unit_name = unit_elem.get("Value", "")
            if unit_name:
                unit_nid = _pascal_resolve_unit(path, unit_name)
                add_node(unit_nid, unit_name)
                add_edge(pkg_nid, unit_nid, "contains")

    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}


__all__ = ['_pascal_project_root', '_pascal_resolve_unit', '_pascal_resolve_class', '_PAS_TOKEN_RE', '_PAS_MODULE_RE', '_PAS_USES_RE', '_PAS_TYPE_HEADER_RE', '_PAS_END_SEMI_RE', '_PAS_METHOD_DECL_RE', '_PAS_IMPL_HEADER_RE', '_PAS_BEGIN_END_TOKEN_RE', '_PAS_CALL_RE', '_PAS_KEYWORDS', '_pascal_strip_comments', '_pascal_split_sections', '_pascal_split_uses', '_pascal_split_bases', '_pascal_find_body', '_extract_pascal_regex', 'extract_pascal', 'extract_lazarus_form', 'extract_delphi_form', 'extract_lazarus_package']
