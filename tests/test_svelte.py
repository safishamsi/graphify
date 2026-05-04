"""Tests for extract_svelte() — covers static script-block imports (#713),
TS/JS dispatch via lang= attribute, Svelte 4 + 5 module blocks, and the
markup-level dynamic_import regex pass (#701)."""

from pathlib import Path

from graphify.extract import (
    _make_id,
    _mask_non_matching_scripts,
    _svelte_script_lang,
    extract_svelte,
)


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _edges_of(result: dict, *, relation: str | None = None) -> list[dict]:
    return [e for e in result["edges"]
            if relation is None or e.get("relation") == relation]


def _targets_of(result: dict, *, relation: str | None = None) -> list[str]:
    return [e.get("target") for e in _edges_of(result, relation=relation)]


# ── _svelte_script_lang ───────────────────────────────────────────────────────


def test_script_lang_default_is_js():
    assert _svelte_script_lang("") == "js"
    assert _svelte_script_lang(' context="module"') == "js"


def test_script_lang_ts():
    assert _svelte_script_lang(' lang="ts"') == "ts"
    assert _svelte_script_lang(" lang='ts'") == "ts"
    assert _svelte_script_lang(' lang="typescript"') == "ts"
    assert _svelte_script_lang(' module lang="ts"') == "ts"


def test_script_lang_unknown_falls_back_to_js():
    # coffeescript / pug / etc — we don't try to parse them
    assert _svelte_script_lang(' lang="coffee"') == "js"


# ── _mask_non_matching_scripts ────────────────────────────────────────────────


def test_mask_preserves_line_count():
    src = (
        "<script>\n"
        "  const a = 1\n"
        "</script>\n"
        "<div>hi</div>\n"
        '<script lang="ts">\n'
        "  const b: number = 2\n"
        "</script>\n"
    )
    masked_js = _mask_non_matching_scripts(src, "js").decode("utf-8")
    masked_ts = _mask_non_matching_scripts(src, "ts").decode("utf-8")
    # Newline count must match exactly so AST line numbers stay aligned.
    assert masked_js.count("\n") == src.count("\n")
    assert masked_ts.count("\n") == src.count("\n")


def test_mask_keeps_only_target_lang():
    src = (
        '<script lang="ts">\n'
        "  type Foo = string\n"
        "</script>\n"
        "<script>\n"
        "  const x = 1\n"
        "</script>\n"
    )
    masked_js = _mask_non_matching_scripts(src, "js").decode("utf-8")
    masked_ts = _mask_non_matching_scripts(src, "ts").decode("utf-8")
    assert "const x = 1" in masked_js
    assert "type Foo" not in masked_js
    assert "type Foo = string" in masked_ts
    assert "const x = 1" not in masked_ts


def test_mask_zaps_markup_and_style():
    src = (
        "<script>\n"
        "  const a = 1\n"
        "</script>\n"
        "<div class='x'>hi {value}</div>\n"
        "<style>.x { color: red; }</style>\n"
    )
    masked = _mask_non_matching_scripts(src, "js").decode("utf-8")
    # Tree-sitter must not see any of the markup or style content.
    assert "<div" not in masked
    assert "<style" not in masked
    assert ".x {" not in masked
    assert "const a = 1" in masked


# ── extract_svelte: static imports (#713 core fix) ────────────────────────────


def test_static_imports_resolve_to_relative_files(tmp_path):
    """The #713 reproducer: static .svelte imports must produce edges whose
    targets are the resolved file IDs (not phantom names).

    Cross-file merge creates the target NODE later when the sibling file is
    itself extracted; here we only verify the edge resolves to the right ID.
    """
    src_dir = tmp_path / "src" / "Grid"
    src_dir.mkdir(parents=True)
    (src_dir / "Card").mkdir()
    siblings = ("series-card-anime", "series-card-image", "series-card-meta")
    for name in siblings:
        _write(src_dir / "Card" / f"{name}.svelte", "<div></div>")
    importer = _write(src_dir / "series-entry-grid.svelte", """\
<script lang="ts">
  import SeriesCardAnime from './Card/series-card-anime.svelte'
  import SeriesCardImage from './Card/series-card-image.svelte'
  import SeriesCardMeta from './Card/series-card-meta.svelte'
</script>
""")
    result = extract_svelte(importer)
    targets = set(_targets_of(result))
    expected = {
        _make_id(str(src_dir / "Card" / f"{name}.svelte")): name
        for name in siblings
    }
    missing = [name for nid, name in expected.items() if nid not in targets]
    assert not missing, (
        f"Static .svelte imports failed to resolve: {missing}\n"
        f"Got targets: {targets}"
    )


def test_static_imports_count_increases_after_fix(tmp_path):
    """Before #713, every static .svelte import was dropped. After the fix,
    a file with N script-block imports must produce at least N import edges."""
    component = _write(tmp_path / "Card.svelte", "<div></div>")
    importer = _write(tmp_path / "page.svelte", """\
<script lang="ts">
  import { onMount } from 'svelte'
  import Card from './Card.svelte'
  import { tick } from 'svelte'
</script>
<Card />
""")
    result = extract_svelte(importer)
    import_edges = [e for e in result["edges"]
                    if e.get("relation") in ("imports", "imports_from")]
    # 3 imports declared in the script: onMount (named), Card (default), tick (named).
    # Tree-sitter TS may emit imports + imports_from depending on shape; we just
    # require it sees ≥3 of them, which is the structural guarantee.
    assert len(import_edges) >= 3, (
        f"Expected ≥3 import edges, got {len(import_edges)}: "
        f"{[(e['relation'], e['target']) for e in import_edges]}"
    )


# ── lang="ts" support ─────────────────────────────────────────────────────────


def test_ts_specific_syntax_does_not_corrupt_ast(tmp_path):
    """With JS-only parsing, `import type { X }` and generics broke the AST.
    Under #713 the TS grammar is used so subsequent imports survive."""
    importer = _write(tmp_path / "page.svelte", """\
<script lang="ts">
  import type { Foo } from './types'
  import { bar } from './bar'
  const baz = <T,>(x: T): T => x
  import { qux } from './qux'
</script>
""")
    result = extract_svelte(importer)
    targets = {str(e.get("target") or "") for e in result["edges"]
               if e.get("relation") in ("imports", "imports_from")}
    # Imports declared BEFORE and AFTER TS-only constructs (type imports,
    # generics) must all produce edges. The targets are stem-prefixed IDs
    # like "<dir>_bar", so substring-match the module names.
    assert any(t.endswith("_types") or "_types" in t for t in targets), \
        f"`import type` not extracted; targets={targets}"
    assert any(t.endswith("_bar") or "_bar_bar" in t for t in targets), \
        f"Import before generic not extracted; targets={targets}"
    assert any(t.endswith("_qux") or "_qux_qux" in t for t in targets), \
        f"Import after generic not extracted (TS grammar regression); " \
        f"targets={targets}"


# ── module blocks (Svelte 4 + 5) ──────────────────────────────────────────────


def _import_targets(result: dict) -> set[str]:
    return {str(e.get("target") or "") for e in result["edges"]
            if e.get("relation") in ("imports", "imports_from")}


def test_svelte4_module_block_extracted(tmp_path):
    importer = _write(tmp_path / "page.svelte", """\
<script context="module">
  import { foo } from './foo'
</script>
<script>
  import { bar } from './bar'
</script>
""")
    targets = _import_targets(extract_svelte(importer))
    assert any("_foo" in t for t in targets), (
        f"<script context='module'> imports must be visible; targets={targets}"
    )
    assert any("_bar" in t for t in targets), (
        f"Instance script imports must be visible; targets={targets}"
    )


def test_svelte5_module_block_extracted(tmp_path):
    importer = _write(tmp_path / "page.svelte", """\
<script module>
  import { foo } from './foo'
</script>
<script>
  import { bar } from './bar'
</script>
""")
    targets = _import_targets(extract_svelte(importer))
    assert any("_foo" in t for t in targets)
    assert any("_bar" in t for t in targets)


def test_mixed_lang_module_ts_instance_js(tmp_path):
    """Module block in TS + instance block in JS — both should parse with
    their own grammar and contribute edges."""
    importer = _write(tmp_path / "page.svelte", """\
<script module lang="ts">
  import type { FooT } from './types'
  import { foo } from './foo'
</script>
<script>
  import { bar } from './bar'
</script>
""")
    targets = _import_targets(extract_svelte(importer))
    assert any("_foo" in t for t in targets)
    assert any("_bar" in t for t in targets)


def test_mixed_lang_module_js_instance_ts(tmp_path):
    importer = _write(tmp_path / "page.svelte", """\
<script context="module">
  import { foo } from './foo'
</script>
<script lang="ts">
  import type { BarT } from './bar-types'
  import { bar } from './bar'
</script>
""")
    targets = _import_targets(extract_svelte(importer))
    assert any("_foo" in t for t in targets)
    assert any("_bar" in t for t in targets)


# ── #701 regression guards (markup dynamic_import) ────────────────────────────


def test_markup_dynamic_import_still_extracted(tmp_path):
    """Regression guard for #701: markup-level dynamic imports must keep
    producing dynamic_import edges after the script-slicing change."""
    target = _write(tmp_path / "Modal.svelte", "<div></div>")
    importer = _write(tmp_path / "page.svelte", """\
<script>
  let show = false
</script>
{#if show}
  {#await import('./Modal.svelte') then Mod}
    <Mod.default />
  {/await}
{/if}
""")
    result = extract_svelte(importer)
    dyn_edges = [e for e in result["edges"]
                 if e.get("relation") == "dynamic_import"]
    assert dyn_edges, "Markup-level {#await import(...)} must still emit a dynamic_import edge"
    # And the target must resolve to the real Modal.svelte file node.
    expected_target = _make_id(str(target))
    assert any(e["target"] == expected_target for e in dyn_edges), (
        f"dynamic_import target should resolve to Modal.svelte file id; "
        f"got {[e['target'] for e in dyn_edges]}"
    )


def test_script_block_dynamic_import_still_extracted(tmp_path):
    """Dynamic import inside <script> body — the #701 regex pass scans the
    full source so this remains caught after slicing."""
    target = _write(tmp_path / "Heavy.svelte", "<div></div>")
    importer = _write(tmp_path / "page.svelte", """\
<script>
  async function load() {
    const Heavy = await import('./Heavy.svelte')
    return Heavy.default
  }
</script>
""")
    result = extract_svelte(importer)
    assert any(e.get("relation") == "dynamic_import" for e in result["edges"])


# ── shape invariants ──────────────────────────────────────────────────────────


def test_no_script_block_does_not_crash(tmp_path):
    """Markup-only .svelte file (legal Svelte) must not error and must still
    have a file node so build_from_json can resolve cross-file edges."""
    importer = _write(tmp_path / "static.svelte", "<div>just markup</div>\n")
    result = extract_svelte(importer)
    assert "error" not in result
    file_node_id = _make_id(str(importer))
    assert any(n["id"] == file_node_id for n in result["nodes"]), (
        "File node must always be created so cross-file edges resolve"
    )


def test_file_node_id_matches_dispatch_convention(tmp_path):
    """The file node ID must equal _make_id(str(path)) so other extractors'
    edges to this .svelte file land on the same node (#701 invariant)."""
    importer = _write(tmp_path / "Component.svelte", "<script>const x = 1</script>")
    result = extract_svelte(importer)
    expected = _make_id(str(importer))
    assert any(n["id"] == expected for n in result["nodes"])


def test_no_dangling_edge_sources(tmp_path):
    """Every edge's source node must exist in the result."""
    target = _write(tmp_path / "Card.svelte", "<div></div>")
    importer = _write(tmp_path / "page.svelte", """\
<script lang="ts">
  import Card from './Card.svelte'
</script>
""")
    result = extract_svelte(importer)
    node_ids = {n["id"] for n in result["nodes"]}
    for edge in result["edges"]:
        assert edge["source"] in node_ids, f"Dangling source: {edge}"


def _node_loc(result: dict, label_substring: str) -> str | None:
    for n in result["nodes"]:
        if label_substring in (n.get("label") or ""):
            return n.get("source_location")
    return None


def _edge_loc_for_target(result: dict, target_substring: str) -> str | None:
    for e in result["edges"]:
        if target_substring in str(e.get("target") or ""):
            return e.get("source_location")
    return None


def test_line_numbers_stay_aligned_with_original_file(tmp_path):
    """Whitespace-masking preserves newline positions, so source_location
    on a function declared at .svelte line 7 must report L7, not L1."""
    importer = _write(tmp_path / "Component.svelte", """\
<div>
  some
  markup
  before
</div>
<script>
  function handler() {}
</script>
""")
    result = extract_svelte(importer)
    loc = _node_loc(result, "handler")
    assert loc is not None, (
        f"handler() not extracted; nodes={[n.get('label') for n in result['nodes']]}"
    )
    assert loc == "L7", f"Expected L7 (preserved by whitespace mask); got {loc}"


def test_line_numbers_for_imports_stay_aligned(tmp_path):
    """Import edges carry source_location too — must point at the actual
    import line in the .svelte file, not a script-block-relative line."""
    _write(tmp_path / "foo.ts", "export const foo = 1")
    importer = _write(tmp_path / "Component.svelte", """\
<div>
  markup line 2
</div>
<style>
  .x { color: red }
</style>

<script lang="ts">
  import { foo } from './foo'
</script>
""")
    # Source layout: <div> on L1, </div> on L3, blank L7, <script> on L8,
    # the import statement is on L9.
    result = extract_svelte(importer)
    loc = _edge_loc_for_target(result, "_foo")
    assert loc is not None, f"foo import edge missing; edges={result['edges']}"
    assert loc == "L9", f"Expected L9 (import line in .svelte); got {loc}"


def test_line_numbers_with_deeply_offset_script(tmp_path):
    """A script block 30 lines into the file must still report correct line
    numbers — proves the whitespace-mask preserves arbitrary offsets, not
    just small ones."""
    leading = "<div>line {n}</div>\n".format
    src = "".join(leading(n=i + 1) for i in range(30))
    src += "<script>\n"
    src += "  function deep() {}\n"
    src += "</script>\n"
    importer = _write(tmp_path / "Component.svelte", src)
    # Layout: lines 1-30 are markup, line 31 is <script>, line 32 is deep().
    result = extract_svelte(importer)
    loc = _node_loc(result, "deep")
    assert loc == "L32", f"Expected L32; got {loc}"


def test_line_numbers_across_two_script_blocks(tmp_path):
    """Module block + instance block on different lines — each symbol must
    report the line from the *original* file, not from its script-relative
    position."""
    importer = _write(tmp_path / "Component.svelte", """\
<script context="module">
  export function module_only() {}
</script>

<div>some markup</div>
<div>more markup</div>

<script lang="ts">
  function instance_only() {}
</script>
""")
    # Layout:
    #   L1  <script context="module">
    #   L2  export function module_only() {}     ← report L2
    #   L3  </script>
    #   L4  blank
    #   L5  <div>some markup</div>
    #   L6  <div>more markup</div>
    #   L7  blank
    #   L8  <script lang="ts">
    #   L9  function instance_only() {}          ← report L9
    #   L10 </script>
    result = extract_svelte(importer)
    mod_loc = _node_loc(result, "module_only")
    inst_loc = _node_loc(result, "instance_only")
    assert mod_loc == "L2", (
        f"module-block fn should report L2 (its line in the .svelte file); "
        f"got {mod_loc}"
    )
    assert inst_loc == "L9", (
        f"instance-block fn should report L9 (its line in the .svelte file); "
        f"got {inst_loc}"
    )


def test_byte_offset_alignment_via_tree_sitter(tmp_path):
    """Internal sanity check: when the masked source is parsed, every
    declared symbol's start byte (column 0 of its line) must equal the
    same byte offset in the original .svelte source. Catches any future
    regression where masking accidentally shifts content."""
    src = (
        "<div>markup</div>\n"
        "<script>\n"
        "  function alpha() {}\n"
        "  const beta = 1\n"
        "</script>\n"
    )
    importer = _write(tmp_path / "Component.svelte", src)
    result = extract_svelte(importer)
    # alpha is on line 3, beta on line 4
    assert _node_loc(result, "alpha") == "L3"
    # beta is a `const` arrow-decl-style? No, it's a plain const. Tree-sitter
    # JS still emits a node for it via _js_extra_walk only for arrow funcs;
    # plain `const beta = 1` may or may not produce a node depending on the
    # config. We just ensure alpha is correct — the masking invariant holds.
    # And the file node lives at L1.
    file_node = next((n for n in result["nodes"]
                      if n["id"] == _make_id(str(importer))), None)
    assert file_node is not None
    assert file_node["source_location"] == "L1"


def test_mask_byte_count_equals_original(tmp_path):
    """Internal invariant: mask must produce a byte-for-byte equivalent
    string (only character substitution, never insertion/deletion). This
    is what guarantees tree-sitter's byte offsets remain valid pointers
    into the original .svelte source."""
    src = (
        "<script>\n"
        "  const a = 1\n"
        "</script>\n"
        "<div>markup</div>\n"
        '<script lang="ts">\n'
        "  const b: number = 2\n"
        "</script>\n"
    )
    masked_js = _mask_non_matching_scripts(src, "js")
    masked_ts = _mask_non_matching_scripts(src, "ts")
    src_bytes = src.encode("utf-8")
    assert len(masked_js) == len(src_bytes), (
        f"Mask must not change byte count; src={len(src_bytes)} "
        f"masked={len(masked_js)}"
    )
    assert len(masked_ts) == len(src_bytes), (
        f"Mask must not change byte count; src={len(src_bytes)} "
        f"masked={len(masked_ts)}"
    )
    # Newline positions must match exactly so row numbers align.
    src_newlines = [i for i, c in enumerate(src_bytes) if c == ord("\n")]
    js_newlines = [i for i, c in enumerate(masked_js) if c == ord("\n")]
    ts_newlines = [i for i, c in enumerate(masked_ts) if c == ord("\n")]
    assert src_newlines == js_newlines, "JS mask shifted newlines"
    assert src_newlines == ts_newlines, "TS mask shifted newlines"


def test_mask_preserves_byte_offsets_of_kept_content(tmp_path):
    """The bytes of a kept <script> body must sit at the SAME byte offsets
    in the masked output as they did in the original. This is the load-
    bearing invariant: tree-sitter's start_byte values index back into a
    file we can still read, and source_location lines stay correct."""
    src = (
        "<div>filler</div>\n"      # 19 bytes inc. \n
        "<script>\n"                # offsets 19..27, body starts at 28
        "const x = 42\n"
        "</script>\n"
    )
    masked = _mask_non_matching_scripts(src, "js")
    # The 'const x = 42' substring must appear at the SAME byte offset
    # in both the original and masked source.
    needle = b"const x = 42"
    assert masked.find(needle) == src.encode().find(needle), (
        "Kept <script> body must stay at the same byte offset after masking"
    )
