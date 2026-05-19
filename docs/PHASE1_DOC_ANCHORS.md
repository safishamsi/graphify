# Phase 1: Doc Anchors

## What

Adds deterministic extraction of explicit documentation anchors from markdown files, producing `file_type: "doc"` nodes and cross-linking edges to code symbols.

## Why

Graphify already extracts structural headings from markdown as `file_type: "document"`. Doc anchors provide a separate, explicit navigation layer that users or LLMs can place to create direct links between documentation sections and code symbols — without relying on semantic inference.

## Supported Patterns

| Pattern | Example | Node ID | Edge |
|---------|---------|---------|------|
| YAML frontmatter `graphify_id` | `graphify_id: auth_flow` | `doc_stem_auth_flow` | none |
| YAML frontmatter `anchors` | `anchors: [setup, teardown]` | `doc_stem_setup` | none |
| HTML comment `GRAPH` | `<!-- GRAPH: SessionManager -->` | `doc_stem_sessionmanager` | `explains` → `sessionmanager` |
| HTML comment `SEE` | `<!-- SEE: validate_token -->` | `doc_stem_validatetoken` | `references` → `validatetoken` |
| HTML comment `ANCHOR` | `<!-- ANCHOR: foo -->` | `doc_stem_foo` | `references` → `foo` |
| Fenced directive | ````graphify id=auth_flow` | `doc_stem_auth_flow` | none |
| Header with explicit ID | `## Title {#anchor}` | `doc_stem_anchor` | none |

## New Edge Relations

- `explains` — doc section explicitly describes a code symbol (from `GRAPH:` directive)
- `references` — doc section points to a code symbol (from `SEE:` or `ANCHOR:` directive)
- `documented-by` — inverse of `explains` (for future use)
- `validates` — doc section describes validation logic (for future use)
- `orchestrates` — doc section describes orchestration/flow (for future use)
- `persists-via` — doc section describes persistence mechanism (for future use)

## Integration

- **`validate.py`**: Added `"doc"` to `VALID_FILE_TYPES`
- **`extract.py`**: Added `extract_doc_anchors()` + 4 private helpers; wired into `extract()` after ID remapping, before cross-file import resolution
- **`skill.md`**: Updated `file_type` valid values (6 → 7), added new edge relations to schema, added Part A.5 extraction step, updated Part C merge

## Design Decisions

1. **Separate `doc` type from `document`** — avoids collision with `extract_markdown`'s structural heading extraction. Both can coexist for the same file.
2. **Deterministic only** — no semantic inference in v1. Only explicit, user-placed directives are extracted.
3. **Edges preserved** — `extract_doc_anchors` returns both `nodes` and `edges` (not `edges: []`), enabling cross-linking from day one.
4. **Runs after AST + semantic merge** — anchor edges are available for the global label-to-node index used by cross-file call resolution.

## Tests

- `tests/test_doc_anchors.py` — 14 tests covering all 4 patterns, dedup, validation, coexistence with document nodes, ID format matching, error handling
- `tests/test_validate.py` — added `test_doc_file_type_valid`

## Migration

No migration needed. Existing graphs are unaffected. New runs will automatically extract doc anchors from any `.md`, `.mdx`, or `.qmd` files in the corpus.
