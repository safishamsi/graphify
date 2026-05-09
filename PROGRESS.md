# ReScript support — progress note

Branch: `feat/rescript-support`
Status: all 7 acceptance gates from the original task spec are green.

## What works

End-to-end on `tests/fixtures/rescript/{FeatureFlag,Caller}.res` and on a
real ~200-file ReScript codebase used as the smoke-test corpus:

| Surface | Behaviour |
|---|---|
| File detection | `.res` / `.resi` are classified as `FileType.CODE` and dispatched via `_DISPATCH` to `extract_rescript`. |
| Top-level `let x = 42` | Variable node, label `"x"`, edge `file --contains--> x`. |
| Top-level `let f = (a, b) => ...` | Function node, label `"f()"`. The body's calls are walked. |
| Tuple destructure `let (a, b) = pair` | One Variable node per bound name (`a`, `b`). |
| Record destructure `let {foo, bar} = record` | One Variable node per bound name (`foo`, `bar`). |
| `.resi` signature-only `let foo: type` | Function node when the annotated type is `function_type` (e.g. `let getFoo: (~x: int) => int`); Variable node otherwise (`let pi: float`). |
| `module Foo = { ... }` | Module node. Inner `let bar = ...` → method node `".bar()"` or value node with bare label. **Nested modules** recurse to arbitrary depth: `module Outer = { module Inner = { ... } }` emits `Outer --contains--> Inner --contains--> ...` with each inner member attached to its parent module. |
| `type t = ...` (alias, variant, polyvariant) | Type node, bare label. |
| `external alert: string => unit = "alert"` | Function node `alert()` when the annotation is a `function_type`; Variable node otherwise (`external pi: float = "Math.PI"` → bare `pi`). The JS-binding string on the RHS is not registered as a target — externals point at JS strings, not at any ReScript symbol that would be in the graph. |
| Function-locals (`let url = ...`, `let helper = ...` inside a function body) | **Not** registered as graph nodes. Same convention as Python and JS: `function_definition` / `arrow_function` bodies are walked for the call pass but not for entity registration. The architecture view stays at module surface. |
| `open Foo` / `include Foo` | `imports` edge file → module. The cross-file resolver in `extract()` rewrites the bare module-name target to the real file node id when both sides are in the scan, so the edge survives `build.py`'s node-existence filter. |
| Local call `f(x)` | Resolves against same-file functions; cross-file via `raw_calls` matching against `global_label_to_nids`. |
| Qualified call `Foo.bar(x)` / `Belt.Array.some(...)` | Last `value_identifier` of the `value_identifier_path` is the callee name; resolves cross-file the same way local calls do. |
| Pipe expression `arr->Belt.Array.some(...)` | `pipe_expression` wraps the inner `call_expression`; generic recursion picks it up — no special handling needed. |
| Module-qualified type references | `references_type` edge from the enclosing entity (type / let / external) to `<module>.<type>`. Covers record field types (`{x: Animal.species}`), variant and polyvariant arm payloads (`Eat(Animal.food)`, `#Walk(Animal.speed)`), function signatures (`(a: Animal.species): Animal.food`), let-binding annotations (`let helper: Animal.eventId = ...`), and `external` type annotations. Nested paths (`Animal.Habitat.species`) target the leftmost module. Bare local types (`option`, `int`) parse as `type_identifier` not `type_identifier_path`, so they emit no edges. Same-file self-references are EXTRACTED; cross-file are INFERRED at extraction and rewritten to real type-node ids by the multi-file resolver in `extract()`. ReScript is currently the only graphify language emitting type-reference edges — Java/TS/Scala could follow as separate PRs. |

Numbers from the smoke run on a ~200-file ReScript codebase:

- ~2.8k nodes total (before this branch, on the same corpus: 15 — all from `README.md`).
- ~3.2k edges.
- ~180 `.res` / `.resi` file nodes; ~2.6k ReScript symbol nodes.
- ~10 import edges between ReScript files (cross-file `open`/`include`).
- ~500 `calls` edges involving `.res` symbols.

## What's flaky

- **Imports to third-party modules drop silently.** `open Belt`,
  `include React`-style cross-language references from ReScript, etc.
  produce import edges whose target isn't in the scanned graph;
  `build.py:111-112` drops them at graph-build time. Same behaviour
  as Swift's `import UIKit` in a non-Apple-SDK scan; not regression-
  causing, but the import-edge count looks low because of it.
- **Cross-file imports rely on flat module naming.** ReScript convention
  is module = file; `Foo.res` is module `Foo`. The resolver matches on
  `module_stem.lower()`. If a project has two `Foo.res` in different
  subdirectories (rare in practice — ReScript's BS-era flat namespace
  discourages this), the resolver picks the first one seen. No
  collision-handling logic.
- **Sub-module call resolution is name-based, not path-based.** A call
  like `Foo.bar()` resolves to the *first* node labelled `bar()` in
  the global label index. If multiple files define `bar()`, the
  cross-file call resolver in `extract()` skips ambiguous matches
  (>1 candidate) rather than picking incorrectly — this is graphify's
  pre-existing behaviour and matches Swift's approach.
- **Complex / type-annotated patterns** (`let (a: int, b) = pair`,
  `let {foo: renamed} = record`) are skipped. The handler accepts
  plain `value_identifier` patterns inside `tuple_pattern` /
  `record_pattern` / direct `value_identifier`; anything else (nested
  tuple, type-annotated, `as` alias) returns no names and the binding
  is silently dropped. Rare at module scope; common-case loss is low.

## What's deferred

- **Function-locals as graph nodes.** Decision: don't register them.
  Same as Python / JS — `let helper = ...` defined inside another
  function is invisible to the architecture view. If a `--mode deep`
  flag is added later that opts back into per-function-body recursion,
  reinstate the recursion at the let_declaration handler. Without
  that flag, the noise floor was 1,400+ spurious nodes per ~200-file
  ReScript corpus — `let url = ...`, `let now = Date.now()` etc.
- **Cross-language `open` resolution.** When a ReScript file does
  `open Belt`, point the import edge at a synthetic `belt` node tagged
  as a third-party module rather than dropping it at build time. Would
  need a registry of well-known ReScript stdlibs (Belt, Js, React, etc).
- **`module type` signatures.** ReScript supports `module type FOO = {
  ... }` with `module M: FOO`; today these parse without crashing but
  the relationship between the signature and the implementing module
  isn't surfaced as an edge.
- **Pipe-style first-arg calls.** `arr->Belt.Array.some(f)` is captured
  as a call to `some`, but not as `some(arr, f)` semantically; the
  pipe operand becomes invisible to call-context analyses. graphify's
  cross-file resolver doesn't use argument lists today, so this only
  matters if/when richer call analysis is added.
- **JSX.** `<Component prop=...>` blocks parse fine but don't yet
  emit references to the Component module. JSX nodes are
  `jsx_element` / `jsx_self_closing_element`; same shape as TypeScript's
  JSX handling could be ported.

## Sub-task 1 choice (vendor vs PyPI)

Picked **Option A (vendor)**. Reasons:

1. `tree-sitter-rescript` is not on PyPI as of 2026-05-09 (`pip index
   versions tree-sitter-rescript` returns 404).
2. `tree-sitter-language-pack` does ship a ReScript grammar but bundles
   its own `Language`/`Parser` C types under the `builtins` module
   that don't interop with the stock `tree-sitter` Python package
   graphify already depends on
   (`tree_sitter.Language(language_pack_lang)` raises
   `TypeError: an integer is required`). Drop-in replacement not
   viable without rewriting `_extract_generic`.
3. A `git+https://github.com/...` dependency would require git +
   network + C toolchain on every user's machine and is not allowed
   for packages published to PyPI.
4. Upstream already ships a complete `binding.c` / `setup.py` shape
   that exposes the modern `Language(language_capsule)` API, so
   vendoring is a copy of `bindings/python/...` and `src/...`, not
   a binding port.

The `pyproject.toml` build now requires a C toolchain on systems
without a pre-built wheel. graphify is small enough today that a
single sdist build from `pip install -e .` works on macOS / Linux
out of the box. For PyPI distribution the maintainer should add
cibuildwheel CI to cover Linux/macOS/Windows × Python 3.10–3.13.

## Test layout deviation

The original task spec asked for `tests/test_extract_rescript.py`. Every
other language extractor's tests live as a `# ── Language ──` section
in `tests/test_languages.py`. Followed the existing convention; the
ReScript section sits at the end of `test_languages.py`, modeled on
the Scala block. 19 tests, all passing.

## Files changed

- `pyproject.toml` — added `wheel` to build-system, registered
  `graphify._vendor` packages, package-data for the vendored binding.
- `setup.py` (new) — declares the `setuptools.Extension` for the
  vendored `_binding.so`. Mirrors upstream's compile flags.
- `graphify/__init__.py` — sys.modules alias so
  `importlib.import_module("tree_sitter_rescript")` resolves to
  `graphify._vendor.tree_sitter_rescript`.
- `graphify/_vendor/__init__.py` (new) — vendor package marker.
- `graphify/_vendor/tree_sitter_rescript/` (new) — vendored binding
  + grammar + license, copied from
  rescript-lang/tree-sitter-rescript@v6.0.0.
- `graphify/extract.py` —
  `_rescript_pattern_names` (helper),
  `_rescript_type_annotation_is_function` (helper),
  `_import_rescript`,
  `_rescript_extra_walk` (handles let / module / type / external),
  `_RESCRIPT_CONFIG`,
  `extract_rescript`,
  walker dispatch branch,
  call-graph dispatch branch,
  `_DISPATCH` entries,
  and the cross-file imports resolver in `extract()`.
- `graphify/detect.py` — `.res` / `.resi` added to `CODE_EXTENSIONS`.
- `tests/fixtures/rescript/{FeatureFlag,Caller}.res` (new) — fictional
  feature-flag-style fixture pair exercising polyvariant types, value
  lets, function lets, nested modules, cross-file `open`, and
  qualified calls.
- `tests/test_languages.py` — ReScript section (19 tests).
- `README.md` — supported-languages row updated (28 → 29 languages).
- `CHANGELOG.md` — `## Unreleased` entry above 0.7.11.

## Acceptance gates — final state

| Gate | Ask | Status | Evidence |
|---|---|---|---|
| 1 | per-language extractor tests pass | ✓ | `pytest tests/test_languages.py -k rescript` → 19/19 pass |
| 2 | `graphify update tests/fixtures/rescript` ≥ 9 nodes / ≥ 4 edges | ✓ | 11 nodes, 13 edges, all expected entities and edges emitted |
| 3 | nonzero `.res` symbols on real corpus | ✓ | ~2.8k nodes / ~3.2k edges on ~200-file corpus (vs 15 baseline) |
| 4 | `graphify path` / `graphify query` returns the cross-file callers | ✓ | `graphify query "who calls isEnabled"` returns `darkModeOn()` and `isEnabledForUser()` |
| 5 | existing tests still pass | ✓ | full suite passes (one unrelated pre-existing fixture mod) |
| 6 | README updated | ✓ | row count 28 → 29, `.res .resi` listed |
| 7 | CHANGELOG entry | ✓ | `## Unreleased` block above 0.7.11 |

## Upstream PR

Not yet submitted. Draft description prepared for review before push.
