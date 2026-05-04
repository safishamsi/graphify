"""Tests for #712 — extract_svelte()'s regex pass for `import('...')` must
stamp the stub node's source_file to the *imported* file's path, never to
the *importer's* path.

build_from_json does last-write-wins on node attributes when two extractors
produce nodes with the same ID. Before #712, the importer-stamped stub
could clobber the correct source_file from the target file's own extraction
depending on file-iteration order, causing downstream tools to attribute
the file to whichever component first imports it.
"""

from pathlib import Path

from graphify.extract import _make_id, extract_svelte


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _node_by_id(result: dict, node_id: str) -> dict | None:
    for n in result["nodes"]:
        if n.get("id") == node_id:
            return n
    return None


# ── Relative dynamic imports ──────────────────────────────────────────────────


def test_relative_dynamic_import_stub_points_to_target(tmp_path):
    target = _write(tmp_path / "Modal.svelte", "<div></div>")
    importer = _write(tmp_path / "page.svelte", """\
<script>
  let show = false
</script>
{#if show}
  {#await import('./Modal.svelte') then Mod}<Mod.default/>{/await}
{/if}
""")
    result = extract_svelte(importer)
    target_node = _node_by_id(result, _make_id(str(target)))
    assert target_node is not None, (
        f"Expected stub node for Modal.svelte; nodes={[n['id'] for n in result['nodes']]}"
    )
    assert target_node["source_file"] == str(target), (
        f"Stub source_file must point at the IMPORTED file (#712);\n"
        f"  expected: {target}\n"
        f"  got:      {target_node['source_file']}"
    )


def test_relative_dynamic_import_stub_does_not_carry_importer_path(tmp_path):
    """The specific bug: source_file pointed to the importer."""
    target = _write(tmp_path / "Modal.svelte", "<div></div>")
    importer = _write(tmp_path / "page.svelte", """\
<script>
  const lazy = () => import('./Modal.svelte')
</script>
""")
    result = extract_svelte(importer)
    target_node = _node_by_id(result, _make_id(str(target)))
    assert target_node is not None
    assert target_node["source_file"] != str(importer), (
        f"Stub source_file must NOT be the importer's path (#712 regression)"
    )


# ── Aliased dynamic imports ($lib/...) ───────────────────────────────────────


def test_alias_dynamic_import_stub_points_to_resolved_path(tmp_path):
    """$lib/X.svelte alias imports were the original repro for #712."""
    src_dir = tmp_path / "src"
    lib_dir = src_dir / "lib" / "components" / "library"
    lib_dir.mkdir(parents=True)
    target = _write(lib_dir / "popover.svelte", "<div></div>")

    # Minimal tsconfig.json with $lib alias
    _write(tmp_path / "tsconfig.json", """\
{
  "compilerOptions": {
    "paths": { "$lib": ["./src/lib"], "$lib/*": ["./src/lib/*"] }
  }
}
""")
    importer_dir = src_dir / "partials" / "Card"
    importer_dir.mkdir(parents=True)
    importer = _write(importer_dir / "card.svelte", """\
<script>
  const lazy = () => import('$lib/components/library/popover.svelte')
</script>
""")

    result = extract_svelte(importer)
    expected_id = _make_id(str(target))
    target_node = _node_by_id(result, expected_id)
    assert target_node is not None, (
        f"Expected resolved alias to produce node id={expected_id}; "
        f"got nodes={[n['id'] for n in result['nodes']]}"
    )
    # The stamped source_file may use a different path normalization
    # (resolve symlinks, /private prefix on macOS, etc) but it must NOT
    # be the importer's path.
    assert target_node["source_file"] != str(importer), (
        f"Stub source_file must not be importer's path; got {target_node['source_file']}"
    )
    # And it should point to something that IS the target (basename match
    # is enough — paths can differ in normalization).
    assert Path(target_node["source_file"]).name == "popover.svelte", (
        f"Stub source_file basename should be the target file's basename; "
        f"got {target_node['source_file']}"
    )


# ── Last-write-wins merge consistency ─────────────────────────────────────────


def test_two_importers_agree_on_target_source_file(tmp_path):
    """If A.svelte and B.svelte both dynamically import C.svelte, the stub
    nodes they create must agree on C.svelte's source_file. Otherwise
    build_from_json's last-write-wins merge depends on file-iteration order."""
    target = _write(tmp_path / "C.svelte", "<div></div>")
    importer_a = _write(tmp_path / "A.svelte", """\
<script>
  const lazy = () => import('./C.svelte')
</script>
""")
    importer_b = _write(tmp_path / "B.svelte", """\
<script>
  {#await import('./C.svelte') then C}<C.default/>{/await}
</script>
""")
    result_a = extract_svelte(importer_a)
    result_b = extract_svelte(importer_b)
    target_id = _make_id(str(target))
    node_a = _node_by_id(result_a, target_id)
    node_b = _node_by_id(result_b, target_id)
    assert node_a is not None and node_b is not None
    assert node_a["source_file"] == node_b["source_file"], (
        f"Two importers of the same target produced inconsistent source_file:\n"
        f"  from A: {node_a['source_file']}\n"
        f"  from B: {node_b['source_file']}\n"
        f"  Last-write-wins merge becomes order-dependent (#712)."
    )
    assert node_a["source_file"] == str(target), (
        f"Both stubs should point to the actual target file"
    )


def test_target_extraction_does_not_clobber_correct_source_file(tmp_path):
    """End-to-end: when the same .svelte file is extracted twice — once as
    a dynamic-import stub from another file, once as itself — the canonical
    source_file (its own path) must survive the merge regardless of order."""
    target = _write(tmp_path / "Modal.svelte", """\
<script>
  let open = false
</script>
""")
    importer = _write(tmp_path / "page.svelte", """\
<script>
  const lazy = () => import('./Modal.svelte')
</script>
""")
    # Stub from importer
    stub_node = _node_by_id(extract_svelte(importer), _make_id(str(target)))
    # Real node from target's own extraction
    real_node = _node_by_id(extract_svelte(target), _make_id(str(target)))
    assert stub_node is not None and real_node is not None
    # Both must report the same source_file. Otherwise either side losing
    # the merge corrupts downstream queries that read source_file.
    assert stub_node["source_file"] == real_node["source_file"], (
        f"Stub and real node must agree on source_file so the merge order "
        f"doesn't matter:\n  stub: {stub_node['source_file']}\n  "
        f"real: {real_node['source_file']}"
    )


# ── External / bare imports ──────────────────────────────────────────────────


def test_bare_module_dynamic_import_does_not_corrupt_source_file(tmp_path):
    """Dynamic imports of node_modules (e.g. `import('lodash')`) shouldn't
    be stamped with the importer's path either — better to leave empty
    than to lie."""
    importer = _write(tmp_path / "page.svelte", """\
<script>
  const load = () => import('lodash-es')
</script>
""")
    result = extract_svelte(importer)
    # Look for any node whose label is the bare module name
    bare_nodes = [n for n in result["nodes"]
                  if (n.get("label") or "") == "lodash-es"]
    if bare_nodes:
        # If a stub was created for an external, its source_file must NOT
        # claim to be the importer.
        assert bare_nodes[0]["source_file"] != str(importer), (
            f"Bare-module stub source_file must not claim to be the importer "
            f"(#712); got {bare_nodes[0]['source_file']}"
        )


# ── Edge source_file (separate concern, regression guard) ────────────────────


def test_dynamic_import_edge_source_file_is_importer(tmp_path):
    """The EDGE's source_file is the importer (correct — that's where the
    import statement lives). Only the NODE stub had the bug. Guard against
    accidentally over-correcting and changing the edge's source_file too."""
    target = _write(tmp_path / "Modal.svelte", "<div></div>")
    importer = _write(tmp_path / "page.svelte", """\
<script>
  const lazy = () => import('./Modal.svelte')
</script>
""")
    result = extract_svelte(importer)
    dyn_edges = [e for e in result["edges"]
                 if e.get("relation") == "dynamic_import"]
    assert dyn_edges
    for e in dyn_edges:
        assert e["source_file"] == str(importer), (
            f"Edge source_file should remain the importer (where the import "
            f"statement is located); got {e['source_file']}"
        )
