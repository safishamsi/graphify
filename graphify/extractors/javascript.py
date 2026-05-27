from .core import *
import os
from pathlib import Path


def extract_js(path: Path) -> dict:
    """Extract classes, functions, arrow functions, and imports from a .js/.ts/.tsx file."""
    if path.suffix == ".tsx":
        config = _TSX_CONFIG
    elif path.suffix == ".ts":
        config = _TS_CONFIG
    else:
        config = _JS_CONFIG
    return _extract_generic(path, config)


def extract_svelte(path: Path) -> dict:
    """Extract imports from .svelte files: script-block via JS AST + template regex fallback.

    Tree-sitter only sees the <script> block. Svelte template syntax like
    {#await import('./X.svelte')} lives in the markup layer and is invisible
    to the JS parser, so a regex pass covers those dynamic imports.
    """
    result = _extract_generic(path, _JS_CONFIG)
    try:
        import re as _re
        src = path.read_text(encoding="utf-8", errors="replace")
        existing_ids = {n["id"] for n in result.get("nodes", [])}
        # Source file node ID must match the one _extract_generic creates:
        # _make_id(str(path)) - single arg, no stem prefix. Otherwise the source
        # endpoint is a phantom node and build_from_json drops the edge (#701).
        file_node_id = _make_id(str(path))
        aliases = _load_tsconfig_aliases(path.parent)
        for m in _re.finditer(r"""import\(\s*['"]([^'"]+)['"]\s*\)""", src):
            raw = m.group(1)
            if not raw:
                continue
            if raw.startswith("."):
                # Relative import - resolve to full path so IDs match file node IDs.
                resolved = Path(os.path.normpath(path.parent / raw))
                # Apply same TS/Svelte resolver fixups as static imports so dynamic
                # imports of bare paths and .svelte.ts rune files land on real
                # file nodes instead of phantom ids (#716).
                resolved = _resolve_js_module_path(resolved)
                node_id = _make_id(str(resolved))
                stub_source_file = str(resolved)
            else:
                # Check tsconfig.json path aliases (e.g. "$lib/" -> "src/lib/", "@/" -> "src/")
                # before treating as external. Mirrors _import_js logic so SvelteKit alias
                # imports resolve to the same file node IDs the extractor creates (#701).
                resolved_alias = None
                for alias_prefix, alias_base in aliases.items():
                    if raw == alias_prefix or raw.startswith(alias_prefix + "/"):
                        rest = raw[len(alias_prefix):].lstrip("/")
                        resolved_alias = Path(os.path.normpath(Path(alias_base) / rest))
                        break
                if resolved_alias is not None:
                    resolved_alias = _resolve_js_module_path(resolved_alias)
                    node_id = _make_id(str(resolved_alias))
                    stub_source_file = str(resolved_alias)
                else:
                    # Bare/scoped import (node_modules) - use last segment;
                    # build_from_json drops as external if no matching node exists.
                    module_name = raw.split("/")[-1]
                    if not module_name:
                        continue
                    node_id = _make_id(module_name)
                    stub_source_file = raw
            if node_id in existing_ids:
                # Edge target already a real node - just add the edge, don't add a node.
                result.setdefault("edges", []).append({
                    "source": file_node_id, "target": node_id,
                    "relation": "dynamic_import", "confidence": "EXTRACTED",
                    "source_file": str(path),
                })
                continue
            result.setdefault("nodes", []).append({
                "id": node_id, "label": raw,
                "file_type": "code", "source_file": stub_source_file,
                "confidence": "EXTRACTED",
            })
            result.setdefault("edges", []).append({
                "source": file_node_id, "target": node_id,
                "relation": "dynamic_import", "confidence": "EXTRACTED",
                "source_file": str(path),
            })
            existing_ids.add(node_id)
        # Static imports inside <script> blocks. The JS tree-sitter parser fed
        # the full .svelte file produces a top-level ERROR node (HTML markup
        # is not valid JS), so import_statement nodes are never reached and
        # static imports are silently dropped (#713). Regex over each script
        # body recovers them.
        script_re = _re.compile(
            r"<script\b[^>]*>([\s\S]*?)</script\s*>", _re.IGNORECASE
        )
        static_import_re = _re.compile(
            r"""import\s+(?:[^'"`;]+?\s+from\s+)?['"]([^'"]+)['"]"""
        )
        for script_match in script_re.finditer(src):
            script_body = script_match.group(1)
            for m in static_import_re.finditer(script_body):
                raw = m.group(1)
                if not raw:
                    continue
                if raw.startswith("."):
                    resolved = Path(os.path.normpath(path.parent / raw))
                    if resolved.suffix == ".js":
                        resolved = resolved.with_suffix(".ts")
                    elif resolved.suffix == ".jsx":
                        resolved = resolved.with_suffix(".tsx")
                    node_id = _make_id(str(resolved))
                    stub_source_file = str(resolved)
                else:
                    resolved_alias = None
                    for alias_prefix, alias_base in aliases.items():
                        if raw == alias_prefix or raw.startswith(alias_prefix + "/"):
                            rest = raw[len(alias_prefix):].lstrip("/")
                            resolved_alias = Path(os.path.normpath(Path(alias_base) / rest))
                            break
                    if resolved_alias is not None:
                        node_id = _make_id(str(resolved_alias))
                        stub_source_file = str(resolved_alias)
                    else:
                        module_name = raw.split("/")[-1]
                        if not module_name:
                            continue
                        node_id = _make_id(module_name)
                        stub_source_file = raw
                if node_id in existing_ids:
                    result.setdefault("edges", []).append({
                        "source": file_node_id, "target": node_id,
                        "relation": "imports_from", "confidence": "EXTRACTED",
                        "source_file": str(path),
                    })
                    continue
                result.setdefault("nodes", []).append({
                    "id": node_id, "label": raw,
                    "file_type": "code", "source_file": stub_source_file,
                    "confidence": "EXTRACTED",
                })
                result.setdefault("edges", []).append({
                    "source": file_node_id, "target": node_id,
                    "relation": "imports_from", "confidence": "EXTRACTED",
                    "source_file": str(path),
                })
                existing_ids.add(node_id)
    except Exception:
        pass
    return result


def extract_astro(path: Path) -> dict:
    """Extract imports from .astro files: frontmatter (TS) + template regex fallback.

    Astro files start with a ``---\\n...\\n---`` frontmatter block of TypeScript
    setup code (where almost all imports live), followed by an HTML-with-expressions
    template body, and optionally ``<script>`` blocks for client-side JS. Tree-sitter
    only sees the file usefully through the frontmatter — feeding the whole file to
    the JS parser produces a top-level ERROR node because the template is not valid
    JS, so ``import_statement`` nodes are never reached and static imports are
    silently dropped (#850). Mirrors :func:`extract_svelte` — same regex-rescue
    approach, scanning the frontmatter block and any client-side ``<script>`` blocks
    for static and dynamic imports.
    """
    result = _extract_generic(path, _JS_CONFIG)
    try:
        import re as _re
        src = path.read_text(encoding="utf-8", errors="replace")
        existing_ids = {n["id"] for n in result.get("nodes", [])}
        file_node_id = _make_id(str(path))
        aliases = _load_tsconfig_aliases(path.parent)
        # Dynamic imports anywhere in the file: `import('./X.astro')` is legal in
        # frontmatter setup code and inside expression slots.
        for m in _re.finditer(r"""import\(\s*['"]([^'"]+)['"]\s*\)""", src):
            raw = m.group(1)
            if not raw:
                continue
            if raw.startswith("."):
                resolved = Path(os.path.normpath(path.parent / raw))
                resolved = _resolve_js_module_path(resolved)
                node_id = _make_id(str(resolved))
                stub_source_file = str(resolved)
            else:
                resolved_alias = None
                for alias_prefix, alias_base in aliases.items():
                    if raw == alias_prefix or raw.startswith(alias_prefix + "/"):
                        rest = raw[len(alias_prefix):].lstrip("/")
                        resolved_alias = Path(os.path.normpath(Path(alias_base) / rest))
                        break
                if resolved_alias is not None:
                    resolved_alias = _resolve_js_module_path(resolved_alias)
                    node_id = _make_id(str(resolved_alias))
                    stub_source_file = str(resolved_alias)
                else:
                    module_name = raw.split("/")[-1]
                    if not module_name:
                        continue
                    node_id = _make_id(module_name)
                    stub_source_file = raw
            if node_id in existing_ids:
                result.setdefault("edges", []).append({
                    "source": file_node_id, "target": node_id,
                    "relation": "dynamic_import", "confidence": "EXTRACTED",
                    "source_file": str(path),
                })
                continue
            result.setdefault("nodes", []).append({
                "id": node_id, "label": raw,
                "file_type": "code", "source_file": stub_source_file,
                "confidence": "EXTRACTED",
            })
            result.setdefault("edges", []).append({
                "source": file_node_id, "target": node_id,
                "relation": "dynamic_import", "confidence": "EXTRACTED",
                "source_file": str(path),
            })
            existing_ids.add(node_id)
        # Static imports: scan the `---...---` frontmatter at the file head plus any
        # client-side <script> blocks. Both are TS/JS regions but live inside a file
        # the JS tree-sitter parser cannot validate as a whole.
        frontmatter_re = _re.compile(
            r"\A\s*---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|\Z)"
        )
        script_re = _re.compile(
            r"<script\b[^>]*>([\s\S]*?)</script\s*>", _re.IGNORECASE
        )
        static_import_re = _re.compile(
            r"""import\s+(?:[^'"`;]+?\s+from\s+)?['"]([^'"]+)['"]"""
        )
        regions: list[str] = []
        fm = frontmatter_re.search(src)
        if fm:
            regions.append(fm.group(1))
        for script_match in script_re.finditer(src):
            regions.append(script_match.group(1))
        for region in regions:
            for m in static_import_re.finditer(region):
                raw = m.group(1)
                if not raw:
                    continue
                if raw.startswith("."):
                    resolved = Path(os.path.normpath(path.parent / raw))
                    if resolved.suffix == ".js":
                        resolved = resolved.with_suffix(".ts")
                    elif resolved.suffix == ".jsx":
                        resolved = resolved.with_suffix(".tsx")
                    node_id = _make_id(str(resolved))
                    stub_source_file = str(resolved)
                else:
                    resolved_alias = None
                    for alias_prefix, alias_base in aliases.items():
                        if raw == alias_prefix or raw.startswith(alias_prefix + "/"):
                            rest = raw[len(alias_prefix):].lstrip("/")
                            resolved_alias = Path(os.path.normpath(Path(alias_base) / rest))
                            break
                    if resolved_alias is not None:
                        node_id = _make_id(str(resolved_alias))
                        stub_source_file = str(resolved_alias)
                    else:
                        module_name = raw.split("/")[-1]
                        if not module_name:
                            continue
                        node_id = _make_id(module_name)
                        stub_source_file = raw
                if node_id in existing_ids:
                    result.setdefault("edges", []).append({
                        "source": file_node_id, "target": node_id,
                        "relation": "imports_from", "confidence": "EXTRACTED",
                        "source_file": str(path),
                    })
                    continue
                result.setdefault("nodes", []).append({
                    "id": node_id, "label": raw,
                    "file_type": "code", "source_file": stub_source_file,
                    "confidence": "EXTRACTED",
                })
                result.setdefault("edges", []).append({
                    "source": file_node_id, "target": node_id,
                    "relation": "imports_from", "confidence": "EXTRACTED",
                    "source_file": str(path),
                })
                existing_ids.add(node_id)
    except Exception:
        pass
    return result


__all__ = ['extract_js', 'extract_svelte', 'extract_astro']
