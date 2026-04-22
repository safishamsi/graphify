"""Framework detection layer — only activates when known framework imports are detected.

This module enriches the Dart extraction result with framework-specific graph data.
It scans already-extracted import edges, matches against known package patterns, and
performs targeted AST analysis for key frameworks.

Adds:
- frameworks metadata on class nodes (e.g. ['riverpod'], ['bloc'], ['go_router'])
- watches_provider / reads_provider edges for Riverpod
- handles_event / emits_state edges for BLoC
- navigates_to edges for GoRouter (route definitions + context.go/push)
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extract_dart import _make_id, _read_text

# ── Pre-compiled regexes ────────────────────────────────────────────────────
_REF_WATCH = re.compile(r'\bref\s*\.\s*watch\s*\(\s*([a-zA-Z_]\w*)')
_REF_READ = re.compile(r'\bref\s*\.\s*read\s*\(\s*([a-zA-Z_]\w*)')
_ON_EVENT = re.compile(r'\bon\s*<\s*([a-zA-Z_]\w*)\s*>')
_EMIT_CALL = re.compile(r'\bemit\s*\(')
_EMIT_STATE = re.compile(r'\bemit\s*\(\s*([A-Z][a-zA-Z_]\w*)\s*\(')

# ── Framework detection table ────────────────────────────────────────────────
# Maps import substrings (after _make_id normalisation) to framework tags.
_FRAMEWORK_IMPORT_PATTERNS: dict[str, str] = {
    "flutter_riverpod": "riverpod",
    "hooks_riverpod": "riverpod",
    "riverpod": "riverpod",
    "flutter_bloc": "bloc",
    "bloc": "bloc",
    "provider": "provider",
    "get_it": "get_it",
    "freezed": "freezed",
    "retrofit": "retrofit",
    "dio": "dio",
    "go_router": "go_router",
    "auto_route": "auto_route",
    "hive": "hive",
    "drift": "drift",
    "floor": "floor",
    "sqflite": "sqflite",
}

# Order matters: more specific patterns must come first so
# "flutter_riverpod" matches before bare "riverpod".
_ORDERED_PATTERNS = sorted(_FRAMEWORK_IMPORT_PATTERNS.keys(), key=len, reverse=True)


def _detect_import_frameworks(result: dict) -> set[str]:
    """Scan import edges and return the set of detected framework tags."""
    detected: set[str] = set()
    for edge in result["edges"]:
        if edge["relation"] != "imports":
            continue
        target = edge.get("target", "")
        # target is a _make_id'd version of the URI, e.g.
        # "package_flutter_riverpod_flutter_riverpod_dart"
        for pattern in _ORDERED_PATTERNS:
            # Normalise the pattern the same way _make_id would
            normalised = re.sub(r"[^a-zA-Z0-9]+", "_", pattern).strip("_").lower()
            # Use word-boundary matching on underscore delimiters to avoid
            # false positives (e.g. "dio" matching "studio", "hive" matching "archive")
            if re.search(rf'(?:^|_){re.escape(normalised)}(?:_|$)', target):
                detected.add(_FRAMEWORK_IMPORT_PATTERNS[pattern])
                break
    return detected


def detect_frameworks(result: dict, path: Path) -> None:
    """Mutate *result* in-place with framework-specific graph data.

    1.  Detect which frameworks are in use via import edges.
    2.  Tag every class node with ``frameworks: [...]``.
    3.  For Riverpod: add ``watches_provider`` / ``reads_provider`` edges.
    4.  For BLoC: add ``handles_event`` / ``emits_state`` edges.
    """

    detected = _detect_import_frameworks(result)
    if not detected:
        return

    # ── Tag class nodes with detected frameworks ────────────────────────────
    for node in result["nodes"]:
        if node.get("dart_kind") == "class":
            node.setdefault("frameworks", [])
            for fw in sorted(detected):
                if fw not in node["frameworks"]:
                    node["frameworks"].append(fw)

    # Bail out early if no advanced analysis needed
    if not (detected & {"riverpod", "bloc", "go_router"}):
        return

    # ── Re-parse the file for AST analysis ──────────────────────────────────
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

    node_by_id: dict[str, dict] = {n["id"]: n for n in result["nodes"]}
    label_to_nid: dict[str, str] = {n["label"]: n["id"] for n in result["nodes"]}
    seen_ids: set[str] = {n["id"] for n in result["nodes"]}

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
                  confidence: str = "INFERRED", weight: float = 0.9) -> None:
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

    # ── Riverpod analysis ───────────────────────────────────────────────────
    if "riverpod" in detected:
        _analyze_riverpod(root, source, stem, str_path, result,
                          node_by_id, label_to_nid, seen_ids,
                          _add_node_if_missing, _add_edge)

    # ── BLoC analysis ───────────────────────────────────────────────────────
    if "bloc" in detected:
        _analyze_bloc(root, source, stem, str_path, result,
                      node_by_id, label_to_nid, seen_ids,
                      _add_node_if_missing, _add_edge)

    # ── GoRouter analysis ──────────────────────────────────────────────────
    if "go_router" in detected:
        _analyze_gorouter(root, source, stem, str_path, result,
                          node_by_id, label_to_nid, seen_ids,
                          _add_node_if_missing, _add_edge)


def _analyze_riverpod(root, source, stem, str_path, result,
                      node_by_id, label_to_nid, seen_ids,
                      _add_node_if_missing, _add_edge) -> None:
    """Find ref.watch(X) and ref.read(X) calls via regex on class method bodies."""
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

        # Walk method signatures + bodies
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

            # Get the function body
            if i + 1 < len(children) and children[i + 1].type == "function_body":
                body_text = _read_text(children[i + 1], source)
                line = children[i + 1].start_point[0] + 1

                # Find ref.watch(provider) calls
                for m in _REF_WATCH.finditer(body_text):
                    provider_name = m.group(1)
                    provider_nid = label_to_nid.get(provider_name)
                    if not provider_nid:
                        provider_nid = _make_id(stem, provider_name)
                        _add_node_if_missing(provider_nid, provider_name,
                                             line, dart_kind="provider")
                    _add_edge(class_nid, provider_nid, "watches_provider", line)

                # Find ref.read(provider) calls
                for m in _REF_READ.finditer(body_text):
                    provider_name = m.group(1)
                    provider_nid = label_to_nid.get(provider_name)
                    if not provider_nid:
                        provider_nid = _make_id(stem, provider_name)
                        _add_node_if_missing(provider_nid, provider_name,
                                             line, dart_kind="provider")
                    _add_edge(class_nid, provider_nid, "reads_provider", line)

    # Also scan top-level provider definitions for ref.watch / ref.read
    # (e.g. greetingProvider that watches counterProvider)

    # Find top-level variable declarations that are providers
    for node in root.children:
        if node.type == "top_level_definition":
            node_text = _read_text(node, source)
            # Check if this looks like a provider definition
            # Pattern: final/const <name> = SomeProvider(...)
            for child in node.children:
                if child.type == "initialized_variable_definition":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        var_name = _read_text(name_node, source)
                        var_nid = label_to_nid.get(var_name)
                        if not var_nid:
                            continue
                        val_text = _read_text(child, source)
                        line = child.start_point[0] + 1
                        for m in _REF_WATCH.finditer(val_text):
                            provider_name = m.group(1)
                            provider_nid = label_to_nid.get(provider_name)
                            if not provider_nid:
                                provider_nid = _make_id(stem, provider_name)
                                _add_node_if_missing(provider_nid, provider_name,
                                                     line, dart_kind="provider")
                            _add_edge(var_nid, provider_nid, "watches_provider", line)
                        for m in _REF_READ.finditer(val_text):
                            provider_name = m.group(1)
                            provider_nid = label_to_nid.get(provider_name)
                            if not provider_nid:
                                provider_nid = _make_id(stem, provider_name)
                                _add_node_if_missing(provider_nid, provider_name,
                                                     line, dart_kind="provider")
                            _add_edge(var_nid, provider_nid, "reads_provider", line)


def _analyze_gorouter(root, source, stem, str_path, result,
                      node_by_id, label_to_nid, seen_ids,
                      _add_node_if_missing, _add_edge) -> None:
    """Find GoRoute(path: ..., builder: ... => Screen()) definitions and
    context.go/push/goNamed/pushNamed navigation calls."""
    source_text = source.decode("utf-8", errors="replace")

    # ── GoRoute definitions ────────────────────────────────────────────────
    # Find each GoRoute( block and extract path + builder target within a
    # reasonable window to avoid spanning across sibling GoRoute entries.
    for m in re.finditer(r"GoRoute\s*\(", source_text):
        start = m.end()
        window = source_text[start:start + 500]
        path_m = re.search(r"""path\s*:\s*['"]([^'"]+)['"]""", window)
        builder_m = re.search(
            r"""(?:builder|pageBuilder)\s*:\s*\([^)]*\)\s*(?:=>|{\s*return)\s*(\w+)\s*\(""",
            window,
        )
        if path_m and builder_m:
            route_path = path_m.group(1)
            screen_name = builder_m.group(1)
            # Estimate source line from character offset
            line = source_text[:m.start()].count("\n") + 1
            route_nid = _make_id("route", route_path)
            _add_node_if_missing(route_nid, route_path, line, dart_kind="route")
            screen_nid = label_to_nid.get(screen_name)
            if not screen_nid:
                screen_nid = _make_id(stem, screen_name)
                _add_node_if_missing(screen_nid, screen_name, line,
                                     dart_kind="class")
            _add_edge(route_nid, screen_nid, "navigates_to", line)

    # ── context.go / context.push / context.goNamed / etc. ─────────────────
    _CONTEXT_NAV = re.compile(
        r"""context\s*\.\s*"""
        r"""(?:go|push|pushReplacement|goNamed|pushNamed|pushReplacementNamed)"""
        r"""\s*\(\s*['"]([^'"]+)['"]"""
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

        for nav_m in _CONTEXT_NAV.finditer(body_text):
            route_or_name = nav_m.group(1)
            route_nid = _make_id("route", route_or_name)
            _add_node_if_missing(route_nid, route_or_name, line,
                                 dart_kind="route")
            _add_edge(class_nid, route_nid, "navigates_to", line)


def _analyze_bloc(root, source, stem, str_path, result,
                  node_by_id, label_to_nid, seen_ids,
                  _add_node_if_missing, _add_edge) -> None:
    """Find on<EventType>() and emit() patterns via regex on class bodies."""
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

        # Find on<EventType>() calls
        for m in _ON_EVENT.finditer(body_text):
            event_name = m.group(1)
            event_nid = label_to_nid.get(event_name)
            if not event_nid:
                event_nid = _make_id(stem, event_name)
                _add_node_if_missing(event_nid, event_name, line, dart_kind="class")
            _add_edge(class_nid, event_nid, "handles_event", line)

        # Find emit(SomeState(...)) calls
        for m in _EMIT_STATE.finditer(body_text):
            state_name = m.group(1)
            state_nid = label_to_nid.get(state_name)
            if not state_nid:
                state_nid = _make_id(stem, state_name)
                _add_node_if_missing(state_nid, state_name, line, dart_kind="class")
            _add_edge(class_nid, state_nid, "emits_state", line)
