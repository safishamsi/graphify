from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from graphify.extractors.core import _make_id, _file_stem, _PROJECT_XML_MAX_BYTES, _project_xml_is_safe

# Add safe XML parser imported from defusedxml in upstream extract.py
try:
    from defusedxml.ElementTree import fromstring as _xml_fromstring
    from defusedxml.ElementTree import ParseError as _xml_ParseError
except ImportError:
    from xml.etree.ElementTree import fromstring as _xml_fromstring
    from xml.etree.ElementTree import ParseError as _xml_ParseError

def extract_sln(path: Path) -> dict:
    """Extract projects and inter-project dependencies from a .sln file."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    file_nid = _make_id(str(path))
    str_path = str(path)
    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_ids.add(file_nid)

    _PROJECT_RE = re.compile(
        r'Project\("[^"]*"\)\s*=\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]*)"'
    )
    _DEP_RE = re.compile(r'\{([0-9a-fA-F-]+)\}\s*=\s*\{([0-9a-fA-F-]+)\}')

    guid_to_nid: dict[str, str] = {}

    for m in _PROJECT_RE.finditer(src):
        proj_name = m.group(1)
        proj_path = m.group(2).replace("\\", "/")
        proj_guid = m.group(3).strip("{}")

        try:
            abs_proj = str((path.parent / proj_path).resolve())
        except Exception:
            abs_proj = proj_path
        proj_nid = _make_id(abs_proj)
        if proj_nid and proj_nid not in seen_ids:
            seen_ids.add(proj_nid)
            nodes.append({"id": proj_nid, "label": proj_name,
                          "file_type": "code", "source_file": abs_proj,
                          "source_location": None})
            edges.append({"source": file_nid, "target": proj_nid,
                          "relation": "contains", "confidence": "EXTRACTED",
                          "source_file": str_path, "weight": 1.0})
        if proj_guid:
            guid_to_nid[proj_guid.lower()] = proj_nid

    in_dep_section = False
    current_proj_guid: str | None = None
    _PROJECT_LINE_RE = re.compile(r'Project\("[^"]*"\)\s*=\s*"[^"]+"\s*,\s*"[^"]+"\s*,\s*"\{([^}]+)\}"')
    for line in src.splitlines():
        proj_line_m = _PROJECT_LINE_RE.search(line)
        if proj_line_m:
            current_proj_guid = proj_line_m.group(1).lower()
            continue
        if line.strip() == "EndProject":
            current_proj_guid = None
            continue
        if "ProjectSection(ProjectDependencies)" in line:
            in_dep_section = True
            continue
        if in_dep_section and "EndProjectSection" in line:
            in_dep_section = False
            continue
        if in_dep_section and current_proj_guid:
            dep_m = _DEP_RE.search(line)
            if dep_m:
                to_guid = dep_m.group(1).lower()
                from_nid = guid_to_nid.get(current_proj_guid)
                to_nid = guid_to_nid.get(to_guid)
                if from_nid and to_nid and from_nid != to_nid:
                    edges.append({"source": from_nid, "target": to_nid,
                                  "relation": "imports", "confidence": "EXTRACTED",
                                  "source_file": str_path, "weight": 1.0})

    return {"nodes": nodes, "edges": edges}


def extract_csproj(path: Path) -> dict:
    """Extract packages, project refs, and target framework from a .csproj/.fsproj/.vbproj."""
    import xml.etree.ElementTree as ET

    try:
        src = path.read_bytes()
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    if len(src) > _PROJECT_XML_MAX_BYTES:
        return {"nodes": [], "edges": [], "error": "project file too large"}
    if not _project_xml_is_safe(src):
        return {"nodes": [], "edges": [],
                "error": "refusing XML with DOCTYPE/ENTITY declaration"}

    try:
        tree = ET.fromstring(src)
    except ET.ParseError as e:
        return {"nodes": [], "edges": [], "error": f"XML parse error: {e}"}

    file_nid = _make_id(str(path))
    str_path = str(path)
    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_ids.add(file_nid)

    ns = ""
    root_tag = tree.tag
    if root_tag.startswith("{"):
        ns = root_tag.split("}")[0] + "}"

    def find_all(tag: str):
        return tree.iter(f"{ns}{tag}")

    for tf in find_all("TargetFramework"):
        if tf.text:
            fw_nid = _make_id("framework", tf.text.strip())
            if fw_nid and fw_nid not in seen_ids:
                seen_ids.add(fw_nid)
                nodes.append({"id": fw_nid, "label": tf.text.strip(),
                              "file_type": "concept", "source_file": str_path,
                              "source_location": None})
                edges.append({"source": file_nid, "target": fw_nid,
                              "relation": "references", "confidence": "EXTRACTED",
                              "source_file": str_path, "weight": 1.0})

    for tf in find_all("TargetFrameworks"):
        if tf.text:
            for fw in tf.text.strip().split(";"):
                fw = fw.strip()
                if fw:
                    fw_nid = _make_id("framework", fw)
                    if fw_nid and fw_nid not in seen_ids:
                        seen_ids.add(fw_nid)
                        nodes.append({"id": fw_nid, "label": fw,
                                      "file_type": "concept", "source_file": str_path,
                                      "source_location": None})
                        edges.append({"source": file_nid, "target": fw_nid,
                                      "relation": "references", "confidence": "EXTRACTED",
                                      "source_file": str_path, "weight": 1.0})

    for pkg in find_all("PackageReference"):
        name = pkg.get("Include") or pkg.get("include") or ""
        version = pkg.get("Version") or pkg.get("version") or ""
        if not name:
            continue
        pkg_nid = _make_id("nuget", name)
        label = f"{name} ({version})" if version else name
        if pkg_nid and pkg_nid not in seen_ids:
            seen_ids.add(pkg_nid)
            nodes.append({"id": pkg_nid, "label": label,
                          "file_type": "code", "source_file": str_path,
                          "source_location": None})
        edges.append({"source": file_nid, "target": pkg_nid,
                      "relation": "imports", "confidence": "EXTRACTED",
                      "source_file": str_path, "weight": 1.0})

    for proj in find_all("ProjectReference"):
        ref_path = proj.get("Include") or proj.get("include") or ""
        if not ref_path:
            continue
        ref_path_norm = ref_path.replace("\\", "/")
        try:
            abs_ref = str((path.parent / ref_path_norm).resolve())
        except Exception:
            abs_ref = ref_path_norm
        proj_nid = _make_id(abs_ref)
        if proj_nid and proj_nid not in seen_ids:
            seen_ids.add(proj_nid)
            proj_label = Path(ref_path_norm).name
            nodes.append({"id": proj_nid, "label": proj_label,
                          "file_type": "code", "source_file": abs_ref,
                          "source_location": None})
        edges.append({"source": file_nid, "target": proj_nid,
                      "relation": "imports", "confidence": "EXTRACTED",
                      "source_file": str_path, "weight": 1.0})

    sdk = tree.get("Sdk") or ""
    if sdk:
        sdk_nid = _make_id("sdk", sdk)
        if sdk_nid and sdk_nid not in seen_ids:
            seen_ids.add(sdk_nid)
            nodes.append({"id": sdk_nid, "label": sdk,
                          "file_type": "concept", "source_file": str_path,
                          "source_location": None})
            edges.append({"source": file_nid, "target": sdk_nid,
                          "relation": "references", "confidence": "EXTRACTED",
                          "source_file": str_path, "weight": 1.0})

    return {"nodes": nodes, "edges": edges}


def extract_razor(path: Path) -> dict:
    """Extract directives, component refs, and @code methods from .razor/.cshtml."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    file_nid = _make_id(str(path))
    str_path = str(path)
    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_ids.add(file_nid)

    def _add_ref(target_name: str, relation: str, line: int) -> None:
        tgt_nid = _make_id(target_name)
        if not tgt_nid:
            return
        if tgt_nid not in seen_ids:
            seen_ids.add(tgt_nid)
            nodes.append({"id": tgt_nid, "label": target_name,
                          "file_type": "code", "source_file": str_path,
                          "source_location": f"L{line}"})
        edges.append({"source": file_nid, "target": tgt_nid,
                      "relation": relation, "confidence": "EXTRACTED",
                      "source_file": str_path, "source_location": f"L{line}",
                      "weight": 1.0})

    for i, line in enumerate(src.splitlines(), 1):
        m = re.match(r'@using\s+([\w.]+)', line)
        if m:
            _add_ref(m.group(1), "imports", i)
            continue

        m = re.match(r'@inject\s+([\w.<>\[\]]+)\s+(\w+)', line)
        if m:
            _add_ref(m.group(1), "imports", i)
            continue

        m = re.match(r'@inherits\s+([\w.<>\[\]]+)', line)
        if m:
            _add_ref(m.group(1), "inherits", i)
            continue

        m = re.match(r'@model\s+([\w.<>\[\]]+)', line)
        if m:
            _add_ref(m.group(1), "references", i)
            continue

        m = re.match(r'@page\s+"([^"]+)"', line)
        if m:
            route = m.group(1)
            route_nid = _make_id("route", route)
            if route_nid and route_nid not in seen_ids:
                seen_ids.add(route_nid)
                nodes.append({"id": route_nid, "label": f"route:{route}",
                              "file_type": "concept", "source_file": str_path,
                              "source_location": f"L{i}"})
                edges.append({"source": file_nid, "target": route_nid,
                              "relation": "references", "confidence": "EXTRACTED",
                              "source_file": str_path, "weight": 1.0})
            continue

    _COMPONENT_RE = re.compile(r'<([A-Z][A-Za-z0-9]+)[\s/>]')
    _HTML_TAGS = frozenset({
        "DOCTYPE", "Html", "Head", "Body", "Div", "Span", "Table", "Form",
        "Input", "Button", "Select", "Option", "Label", "Textarea",
        "Script", "Style", "Link", "Meta", "Title", "Header", "Footer",
        "Nav", "Main", "Section", "Article", "Aside",
    })
    for m in _COMPONENT_RE.finditer(src):
        comp_name = m.group(1)
        if comp_name in _HTML_TAGS:
            continue
        line_num = src[:m.start()].count("\n") + 1
        _add_ref(comp_name, "calls", line_num)

    _CODE_BLOCK_RE = re.compile(r'@code\s*\{', re.MULTILINE)
    for m in _CODE_BLOCK_RE.finditer(src):
        block_start = m.end()
        depth = 1
        pos = block_start
        while pos < len(src) and depth > 0:
            if src[pos] == '{':
                depth += 1
            elif src[pos] == '}':
                depth -= 1
            pos += 1
        code_block = src[block_start:pos - 1] if depth == 0 else ""

        _METHOD_RE = re.compile(
            r'(?:public|private|protected|internal|static|async|override|virtual|abstract)\s+'
            r'[\w<>\[\],\s]+\s+(\w+)\s*\('
        )
        for mm in _METHOD_RE.finditer(code_block):
            method_name = mm.group(1)
            abs_pos = block_start + mm.start()
            method_line = src[:abs_pos].count("\n") + 1
            method_nid = _make_id(_file_stem(path), method_name)
            if method_nid and method_nid not in seen_ids:
                seen_ids.add(method_nid)
                nodes.append({"id": method_nid, "label": method_name,
                              "file_type": "code", "source_file": str_path,
                              "source_location": f"L{method_line}"})
                edges.append({"source": file_nid, "target": method_nid,
                              "relation": "contains", "confidence": "EXTRACTED",
                              "source_file": str_path, "weight": 1.0})

    return {"nodes": nodes, "edges": edges}

