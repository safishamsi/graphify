"""Tests for #716 — TypeScript bare-path imports, Svelte 5 rune file imports
(`from './foo.svelte'` for a `.svelte.ts` file), and directory/index.ts
imports must resolve to the actual file's node id, not a phantom.

Before #716, `_import_js` only rewrote `.js → .ts` and `.jsx → .tsx`. Every
other shape (bare path, `.svelte → .svelte.ts`, `./foo` directory imports)
produced an id like `..._foo` while the real file's node id was `..._foo_ts`,
so `build_from_json` dropped the edge as external.
"""

from pathlib import Path

from graphify.extract import (
    _make_id,
    _resolve_js_module_path,
    extract_js,
    extract_svelte,
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _import_targets(result: dict) -> set[str]:
    return {str(e.get("target") or "") for e in result["edges"]
            if e.get("relation") in ("imports", "imports_from")}


# ── _resolve_js_module_path unit tests ──────────────────────────────────────


def test_resolve_returns_existing_path_unchanged(tmp_path):
    p = _write(tmp_path / "foo.ts", "export const x = 1")
    assert _resolve_js_module_path(p) == p


def test_resolve_bare_path_to_ts(tmp_path):
    target = _write(tmp_path / "foo.ts", "export const x = 1")
    bare = tmp_path / "foo"
    assert _resolve_js_module_path(bare) == target


def test_resolve_bare_path_to_tsx(tmp_path):
    target = _write(tmp_path / "Component.tsx", "export const x = 1")
    bare = tmp_path / "Component"
    assert _resolve_js_module_path(bare) == target


def test_resolve_bare_path_to_svelte(tmp_path):
    target = _write(tmp_path / "Card.svelte", "<div></div>")
    bare = tmp_path / "Card"
    assert _resolve_js_module_path(bare) == target


def test_resolve_prefers_ts_over_svelte_when_both_exist(tmp_path):
    """Vite resolver order: .ts wins over .svelte for ambiguous bare paths."""
    ts_target = _write(tmp_path / "foo.ts", "export const x = 1")
    _write(tmp_path / "foo.svelte", "<div></div>")
    bare = tmp_path / "foo"
    assert _resolve_js_module_path(bare) == ts_target


def test_resolve_file_wins_over_sibling_directory(tmp_path):
    """Real-world repro: a project has both `auth.ts` (file) and `auth/`
    (directory of sub-modules) at the same path. Both TypeScript and Vite
    prefer the file match. If the resolver checks the directory first and
    falls back on a missing index, every `from './auth'` import silently
    drops because the directory has no index.{ts,…}."""
    file_target = _write(tmp_path / "auth.ts", "export const x = 1")
    sibling_dir = tmp_path / "auth"
    sibling_dir.mkdir()
    _write(sibling_dir / "helpers.ts", "export const y = 2")
    bare = tmp_path / "auth"
    assert _resolve_js_module_path(bare) == file_target


def test_resolve_directory_to_index_ts(tmp_path):
    pkg = tmp_path / "queue"
    target = _write(pkg / "index.ts", "export const x = 1")
    assert _resolve_js_module_path(pkg) == target


def test_resolve_directory_prefers_index_ts_over_index_js(tmp_path):
    pkg = tmp_path / "queue"
    target = _write(pkg / "index.ts", "export const x = 1")
    _write(pkg / "index.js", "module.exports = {}")
    assert _resolve_js_module_path(pkg) == target


def test_resolve_svelte_to_svelte_ts_for_rune_files(tmp_path):
    """Svelte 5: `from './foo.svelte'` may actually point at `foo.svelte.ts`
    (a rune-only TypeScript file with no .svelte file). The resolver must
    APPEND .ts to the full filename, not swap suffixes."""
    target = _write(tmp_path / "is-mobile.svelte.ts",
                    "export const isMobile = () => true")
    written_as = tmp_path / "is-mobile.svelte"
    resolved = _resolve_js_module_path(written_as)
    assert resolved == target, (
        f"Expected resolution to is-mobile.svelte.ts; got {resolved}"
    )


def test_resolve_svelte_to_svelte_js_for_javascript_rune_files(tmp_path):
    """JS variant of the rune file pattern: a `.svelte.js` file (used in
    JavaScript-only Svelte 5 projects, no TypeScript). `from './foo.svelte'`
    must resolve to `foo.svelte.js` when no `.ts` variant exists.

    Same code path as the .svelte.ts case — the generalized resolver tries
    every extension in priority order, so JS-only and TS-only projects
    both work without special-casing."""
    target = _write(tmp_path / "store.svelte.js",
                    "export const count = $state(0)")
    written_as = tmp_path / "store.svelte"
    resolved = _resolve_js_module_path(written_as)
    assert resolved == target


def test_resolve_svelte_prefers_svelte_ts_over_svelte_js(tmp_path):
    """When both `.svelte.ts` and `.svelte.js` exist (hybrid project mid-
    migration, or a build artifact alongside the source), `.ts` wins —
    matching the resolver's stated TypeScript-first priority order.

    Note: Vite's default `resolve.extensions` puts `.js` before `.ts`, but
    in practice TypeScript codebases that emit `.svelte.js` build artifacts
    expect tooling to read the `.svelte.ts` source. graphify is a source-
    code tool, not a runtime resolver, so source-first ordering is correct
    for our use case."""
    ts_target = _write(tmp_path / "store.svelte.ts",
                       "export const count = $state(0)")
    _write(tmp_path / "store.svelte.js",
           "export const count = 0  // build artifact")
    written_as = tmp_path / "store.svelte"
    resolved = _resolve_js_module_path(written_as)
    assert resolved == ts_target


def test_resolve_real_svelte_file_wins_over_svelte_ts_sibling(tmp_path):
    """If `foo.svelte` IS a real markup file, importing `./foo.svelte`
    must resolve to that — not get hijacked to a sibling `foo.svelte.ts`
    rune file. The existence-check short-circuits before any append."""
    real = _write(tmp_path / "Card.svelte", "<div>card markup</div>")
    _write(tmp_path / "Card.svelte.ts",
           "export const helpers = {}  // rune sibling, not the import target")
    resolved = _resolve_js_module_path(real)
    assert resolved == real


def test_resolve_js_to_ts_when_real_file_is_ts(tmp_path):
    """TS ESM convention: imports written as .js but the actual file is .ts."""
    target = _write(tmp_path / "foo.ts", "export const x = 1")
    written_as = tmp_path / "foo.js"
    assert _resolve_js_module_path(written_as) == target


def test_resolve_jsx_to_tsx_when_real_file_is_tsx(tmp_path):
    target = _write(tmp_path / "Component.tsx", "export const x = 1")
    written_as = tmp_path / "Component.jsx"
    assert _resolve_js_module_path(written_as) == target


def test_resolve_returns_unchanged_when_nothing_matches(tmp_path):
    """External / truly missing paths fall back to the input — preserves
    pre-#716 behavior of becoming an external phantom edge."""
    nothing = tmp_path / "does_not_exist"
    assert _resolve_js_module_path(nothing) == nothing


def test_resolve_real_js_stays_js_when_ts_does_not_exist(tmp_path):
    """If `.js` exists and `.ts` does not, keep the `.js` rewrite from
    triggering — return the existing file."""
    target = _write(tmp_path / "foo.js", "module.exports = 1")
    assert _resolve_js_module_path(target) == target


# ── End-to-end: bare-path imports in pure TS files ───────────────────────────


def test_bare_path_import_resolves_in_ts_file(tmp_path):
    """The #716 reproducer: TS file imports a sibling without an extension."""
    target = _write(tmp_path / "type-helpers.ts",
                    "export type GetNestedType<T> = T")
    importer = _write(tmp_path / "page.ts",
                      "import type { GetNestedType } from './type-helpers'\n")
    result = extract_js(importer)
    expected = _make_id(str(target))
    assert expected in _import_targets(result), (
        f"Bare-path .ts import must resolve to target node id; "
        f"expected {expected}; got {_import_targets(result)}"
    )


def test_directory_import_resolves_to_index_ts(tmp_path):
    """`from './queue'` must resolve to `./queue/index.ts`."""
    target = _write(tmp_path / "queue" / "index.ts",
                    "export const enqueue = () => {}")
    importer = _write(tmp_path / "page.ts",
                      "import { enqueue } from './queue'\n")
    result = extract_js(importer)
    expected = _make_id(str(target))
    assert expected in _import_targets(result), (
        f"Directory import must resolve to ./queue/index.ts; "
        f"expected {expected}; got {_import_targets(result)}"
    )


# ── End-to-end: .svelte → .svelte.ts (Svelte 5 rune files) ───────────────────


def test_dot_svelte_import_resolves_to_dot_svelte_ts(tmp_path):
    """Svelte 5 rune file: import written as .svelte, real file is .svelte.ts."""
    target = _write(tmp_path / "is-mobile.svelte.ts",
                    "export const isMobile = () => true")
    importer = _write(tmp_path / "page.ts",
                      "import { isMobile } from './is-mobile.svelte'\n")
    result = extract_js(importer)
    expected = _make_id(str(target))
    assert expected in _import_targets(result), (
        f".svelte → .svelte.ts resolution failed; "
        f"expected {expected}; got {_import_targets(result)}"
    )


# ── Regression guards: existing behavior preserved ───────────────────────────


def test_explicit_ts_import_still_works(tmp_path):
    """The most common case — import with explicit .ts extension — must
    continue to work after the resolver change."""
    target = _write(tmp_path / "foo.ts", "export const x = 1")
    importer = _write(tmp_path / "page.ts",
                      "import { x } from './foo.ts'\n")
    result = extract_js(importer)
    expected = _make_id(str(target))
    assert expected in _import_targets(result), (
        f"Explicit .ts imports must still resolve; "
        f"expected {expected}; got {_import_targets(result)}"
    )


def test_explicit_svelte_import_still_works(tmp_path):
    """Real .svelte file imports must still resolve when the .svelte file
    exists (i.e. don't accidentally redirect to a non-existent .svelte.ts)."""
    target = _write(tmp_path / "Card.svelte", "<div></div>")
    importer = _write(tmp_path / "page.ts",
                      "import Card from './Card.svelte'\n")
    result = extract_js(importer)
    expected = _make_id(str(target))
    assert expected in _import_targets(result), (
        f"Existing .svelte imports must resolve to the .svelte node, "
        f"not get redirected; expected {expected}; "
        f"got {_import_targets(result)}"
    )


def test_external_module_unchanged(tmp_path):
    """Bare module specifiers (no leading dot, no alias match) must still
    fall through to the external/last-segment path — don't accidentally
    treat 'lodash' as a relative path."""
    importer = _write(tmp_path / "page.ts",
                      "import _ from 'lodash-es'\n")
    result = extract_js(importer)
    targets = _import_targets(result)
    # The target should be the bare module name, not a resolved file path
    assert "lodash_es" in targets or any("lodash" in t for t in targets), (
        f"External module specifier should still produce an external "
        f"reference; got {targets}"
    )


# ── End-to-end: alias-resolved imports go through the same resolver ─────────


def test_alias_import_with_bare_path_resolves(tmp_path):
    """`$lib/foo` (alias + bare path) — both layers must work together."""
    src = tmp_path / "src"
    target = _write(src / "lib" / "type-helpers.ts",
                    "export type X = string")
    _write(tmp_path / "tsconfig.json",
           '{"compilerOptions":{"paths":{"$lib":["./src/lib"],'
           '"$lib/*":["./src/lib/*"]}}}')
    importer_dir = src / "routes"
    importer = _write(importer_dir / "page.ts",
                      "import type { X } from '$lib/type-helpers'\n")
    result = extract_js(importer)
    expected = _make_id(str(target))
    assert expected in _import_targets(result), (
        f"Alias + bare-path resolution failed; "
        f"expected {expected}; got {_import_targets(result)}"
    )


# ── Edge cases — exhaustiveness ──────────────────────────────────────────────


def test_type_only_import_with_bare_path_resolves(tmp_path):
    """`import type { X } from './foo'` — type-only imports must go through
    the same resolution path as regular imports. Common in TS codebases
    that separate types into their own module."""
    target = _write(tmp_path / "type-helpers.ts",
                    "export type GetNestedType<T> = T")
    importer = _write(tmp_path / "page.ts",
                      "import type { GetNestedType } from './type-helpers'\n")
    result = extract_js(importer)
    expected = _make_id(str(target))
    assert expected in _import_targets(result), (
        f"Type-only import with bare path failed to resolve; "
        f"expected {expected}; got {_import_targets(result)}"
    )


def test_named_imports_emit_symbol_edges_after_resolution(tmp_path):
    """`import { foo, bar } from './module'` should emit per-symbol `imports`
    edges to `module.foo` and `module.bar`, not just the file-level
    `imports_from`. The symbol-edge target_stem comes from _file_stem(resolved),
    which depends on resolution succeeding first."""
    _write(tmp_path / "utils.ts", "export const foo = 1\nexport const bar = 2")
    importer = _write(tmp_path / "page.ts",
                      "import { foo, bar } from './utils'\n")
    result = extract_js(importer)
    sym_edges = [e for e in result["edges"] if e.get("relation") == "imports"]
    targets = {str(e.get("target") or "") for e in sym_edges}
    # Target ids look like "<dir>_utils_foo" — substring-match the symbol names
    assert any("_foo" in t for t in targets), (
        f"Per-symbol `imports` edge for `foo` missing; got {targets}"
    )
    assert any("_bar" in t for t in targets), (
        f"Per-symbol `imports` edge for `bar` missing; got {targets}"
    )


def test_alias_directory_import_resolves_to_index_ts(tmp_path):
    """`from '$lib/queue'` where queue/ is a directory under src/lib/."""
    src = tmp_path / "src"
    target = _write(src / "lib" / "queue" / "index.ts",
                    "export const enqueue = () => {}")
    _write(tmp_path / "tsconfig.json",
           '{"compilerOptions":{"paths":{"$lib":["./src/lib"],'
           '"$lib/*":["./src/lib/*"]}}}')
    importer = _write(src / "routes" / "page.ts",
                      "import { enqueue } from '$lib/queue'\n")
    result = extract_js(importer)
    expected = _make_id(str(target))
    assert expected in _import_targets(result), (
        f"Alias + directory resolution failed; "
        f"expected {expected}; got {_import_targets(result)}"
    )


def test_resolve_does_not_match_partial_directory_name(tmp_path):
    """Regression guard: `from './foo'` where './foo' doesn't exist but
    './foo-extra.ts' does must NOT accidentally resolve to the latter.
    `.with_suffix(".ts")` on 'foo' produces 'foo.ts' — not 'foo-extra.ts',
    but worth pinning down."""
    _write(tmp_path / "foo-extra.ts", "export const x = 1")
    bare = tmp_path / "foo"
    resolved = _resolve_js_module_path(bare)
    # Not a real file → nothing matches → returns input unchanged
    assert resolved == bare, (
        f"Partial-name match must not happen; got {resolved}"
    )


def test_resolve_directory_without_index_returns_unchanged(tmp_path):
    """A directory with no index file should fall through to the
    \"return as-is\" path, not pick a non-index file from inside."""
    pkg = tmp_path / "pkg"
    _write(pkg / "not-index.ts", "export const x = 1")
    resolved = _resolve_js_module_path(pkg)
    assert resolved == pkg, (
        f"Directory without index.* must return unchanged; got {resolved}"
    )


def test_resolve_handles_subpath_into_directory_with_index(tmp_path):
    """`./foo/sub` where ./foo/sub/index.ts exists — nested subpath.
    Common pattern for sub-modules inside a package."""
    target = _write(tmp_path / "foo" / "sub" / "index.ts",
                    "export const x = 1")
    sub = tmp_path / "foo" / "sub"
    assert _resolve_js_module_path(sub) == target


def test_resolve_does_not_treat_dotfile_as_extension(tmp_path):
    """Edge case: `.eslintrc` and similar dotfiles. Path('.eslintrc').suffix
    returns '' on Python 3.x for files starting with `.`. Make sure we
    don't accidentally treat a real file as bare and try to append .ts."""
    target = _write(tmp_path / ".env-types.ts",
                    "export const x = 1")
    # Path('.env-types.ts').suffix is '.ts' — not a problem
    assert _resolve_js_module_path(target) == target


def test_resolve_multi_dot_helper_file(tmp_path):
    """Common patterns: foo.shared.ts, foo.config.ts, foo.compile.ts,
    foo.integration.ts, foo.triggers.ts. Imports written as
    `from './foo.shared'` (preserving the meaningful suffix) must resolve
    to foo.shared.ts.

    Before this rule, .suffix was '.shared' so neither the bare-path branch
    nor the .js/.jsx branches matched, and the import dropped to a phantom."""
    target = _write(tmp_path / "tag-action.shared.ts",
                    "export const apply = () => {}")
    written_as = tmp_path / "tag-action.shared"
    assert _resolve_js_module_path(written_as) == target


def test_resolve_multi_dot_with_explicit_extension_still_works(tmp_path):
    """Sanity: `from './foo.shared.ts'` (explicit) still wins over implicit."""
    target = _write(tmp_path / "foo.shared.ts", "export const x = 1")
    assert _resolve_js_module_path(target) == target


def test_resolve_ambient_d_ts_via_bare_path(tmp_path):
    """Ambient TS declaration files (foo.d.ts) — bare import `./foo.d`
    should resolve to `./foo.d.ts` because `name + '.ts'` gives `foo.d.ts`."""
    target = _write(tmp_path / "ambient.d.ts", "declare const X: string")
    written_as = tmp_path / "ambient.d"
    assert _resolve_js_module_path(written_as) == target


def test_end_to_end_multi_dot_import_resolves(tmp_path):
    """End-to-end sanity for the multi-dot pattern via the import handler."""
    target = _write(tmp_path / "tag-action.shared.ts",
                    "export const apply = () => {}")
    importer = _write(tmp_path / "page.ts",
                      "import { apply } from './tag-action.shared'\n")
    result = extract_js(importer)
    expected = _make_id(str(target))
    assert expected in _import_targets(result), (
        f"Multi-dot import failed end-to-end; "
        f"expected {expected}; got {_import_targets(result)}"
    )


def test_resolve_chain_alias_and_extension_compose(tmp_path):
    """Alias → bare path → .svelte.ts. Two layers of resolution must
    compose correctly: tsconfig alias maps `$lib/...` to a real dir,
    then extension resolution finds the actual file."""
    src = tmp_path / "src"
    target = _write(src / "lib" / "hooks" / "is-mobile.svelte.ts",
                    "export const isMobile = () => true")
    _write(tmp_path / "tsconfig.json",
           '{"compilerOptions":{"paths":{"$lib":["./src/lib"],'
           '"$lib/*":["./src/lib/*"]}}}')
    importer = _write(src / "routes" / "page.ts",
                      "import { isMobile } from '$lib/hooks/is-mobile.svelte'\n")
    result = extract_js(importer)
    expected = _make_id(str(target))
    assert expected in _import_targets(result), (
        f"Alias + .svelte→.svelte.ts chain failed to compose; "
        f"expected {expected}; got {_import_targets(result)}"
    )


# ── End-to-end: dynamic_import in .svelte regex pass uses resolver ──────────


def test_ts_dynamic_import_bare_path_resolves(tmp_path):
    """Real-world repro: a TS file uses `await import('./foo')` (no extension)
    to lazy-load a sibling module. The dynamic-import handler in JS/TS files
    has its own copy of the resolution logic — distinct from the static-import
    handler and from the Svelte regex pass — and was missing the bare-path
    extension append, silently dropping every such edge."""
    target = _write(tmp_path / "profanity.ts",
                    "export const hasProfanity = (s: string) => false")
    importer = _write(tmp_path / "auth-validators.ts", """\
export async function validate(name: string) {
    const { hasProfanity } = await import('./profanity')
    return hasProfanity(name)
}
""")
    result = extract_js(importer)
    expected = _make_id(str(target))
    targets = {str(e.get("target") or "") for e in result["edges"]
               if e.get("relation") in ("imports", "imports_from")}
    assert expected in targets, (
        f"Bare-path TS dynamic import failed to resolve; "
        f"expected {expected}; got {targets}"
    )


def test_ts_dynamic_import_alias_with_bare_path_resolves(tmp_path):
    """The other branch of the dynamic-import handler — alias resolution —
    also needs the same fixups. `import('$lib/foo')` should resolve to
    `$lib/foo.ts` after both alias substitution and extension append."""
    src = tmp_path / "src"
    target = _write(src / "lib" / "lazy-module.ts", "export const x = 1")
    _write(tmp_path / "tsconfig.json",
           '{"compilerOptions":{"paths":{"$lib":["./src/lib"],'
           '"$lib/*":["./src/lib/*"]}}}')
    importer = _write(src / "routes" / "page.ts", """\
export async function load() {
    const m = await import('$lib/lazy-module')
    return m.x
}
""")
    result = extract_js(importer)
    expected = _make_id(str(target))
    targets = {str(e.get("target") or "") for e in result["edges"]
               if e.get("relation") in ("imports", "imports_from")}
    assert expected in targets, (
        f"Alias + bare-path dynamic import failed to resolve; "
        f"expected {expected}; got {targets}"
    )


def test_dynamic_import_bare_path_resolves(tmp_path):
    """The regex pass for `import('...')` in .svelte files must also use
    the new resolver — otherwise dynamic imports of bare paths still
    produce phantom edges."""
    target = _write(tmp_path / "Heavy.svelte.ts",
                    "export const heavy = () => 1")
    importer = _write(tmp_path / "page.svelte", """\
<script>
  const lazy = () => import('./Heavy.svelte')
</script>
""")
    result = extract_svelte(importer)
    dyn_targets = {str(e.get("target") or "") for e in result["edges"]
                   if e.get("relation") == "dynamic_import"}
    expected = _make_id(str(target))
    assert expected in dyn_targets, (
        f"dynamic_import of .svelte that's actually .svelte.ts must "
        f"resolve through the new resolver; "
        f"expected {expected}; got {dyn_targets}"
    )
