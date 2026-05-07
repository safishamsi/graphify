# Verification Report: GPT-5.5 Independent Review — Cross-Cutting & Architectural Claims

**Date:** 2026-05-07
**Scope:** All architectural and cross-cutting claims from `.dox/2026-05-07-independent-review.md` verified against the live codebase.

## Summary

ALL FIVE claims are **VERIFIED** — the review's claims are substantiated by the live codebase. No claims were found to be overstated or inaccurate.

## Detailed Findings

### Claim 1: NetworkX Multigraph Risk — VERIFIED

`graphify/build.py:80` creates a `DiGraph`, not a `MultiDiGraph`. `DiGraph.add_edge()` at `graphify/build.py:112` stores at most one edge per `(source, target)` directed pair. Calling it twice with the same pair and different `attrs` **overwrites** the first edge's attributes with the second call's. The file-level docstring documents three layers of node deduplication but says nothing about edge multigraph semantics or the overwrite behavior. Edge attributes like `relation`, `confidence`, and `context` are silently lost if two edges share the same `(source, target)` but differ semantically.

The review's warning that "even if extraction emits both `calls` and `tests`, `networkx.DiGraph` stores one edge per source-target pair" is technically accurate.

Note: The live `dedup.py:134-142` edge-dedup function `_edge_key()` already includes `relation` in its tuple, but the NetworkX DiGraph layer itself provides no multigraph semantics.

### Claim 2: Dedup Collision Between Import-Guided Calls and Test Edges — VERIFIED

The review's target is the runbook's planned code at `symbol_resolution.py:1706-1715`:

```python
def existing_edge_pairs(edges):  # keys on (source, target) only
    pairs = set()
    for edge in edges:
        pairs.add((str(edge.get("source")), str(edge.get("target"))))
    return pairs
```

This function is reused by both Phase 4 (import-guided calls) and Phase 5 (test linking). Since Phase 4 runs before Phase 5 and the key is only `(source, target)`, a `calls` edge for pair `(test_func, production_func)` will prevent Phase 5 from emitting a `tests` edge for the same pair. The runbook's own Phase 5 test **expects** the `tests` edge to exist, creating a self-contradiction.

The live `graphify/dedup.py:134-142` does NOT have this flaw — its `_edge_key()` includes `relation`. The issue is confined to the runbook's new helper.

### Claim 3: Phase 9 Validation Suite Under-Specified — VERIFIED

The runbook's Phase 9 section (lines 2947-3001) consists of `uv run pytest` commands, `git diff --check`, and `graphify update .` — but no specific end-to-end test content. No assertions about:

- Verifying new relations survive the full pipeline
- Checking node/edge counts on multi-file fixtures
- Running `build_from_json()` on fixtures containing `doc_tag`, `code_index`, and `code_index_symbol` nodes
- Catch-all dangling-edge checks for the new relation types

The existing `test_no_dangling_edges_on_extract` at `tests/test_extract.py:106-115` only checks `contains`, `method`, `inherits`, and `calls`.

### Claim 4: SCIP Ingestion Needs Hardening — VERIFIED

`graphify/security.py` provides URL validation, safe fetch with size caps, path validation (for graph-out paths), and label sanitization. It provides **no** protections relevant to JSON ingestion:

- No file-size limit for JSON files
- No JSON depth limit
- No occurrence count cap
- No path-traversal / path-root check for user-supplied JSON paths
- No symbol-ID length cap

The runbook's SCIP ingestion code at line 2683-2692 reads the entire file with `json.loads(path.read_text(encoding="utf-8"))` — no size check, no file-type validation, no path sanitization beyond what `Path` provides. The review's characterization of SCIP as "a useful seam, not a safe ingestion boundary yet" is accurate.

### Claim 5: Docstring Extraction with `clean=True` Behavior — VERIFIED

The runbook's `_iter_documented_python_objects()` at lines 935-967 calls `ast.get_docstring()` without an explicit `clean` parameter. In Python 3.12+, this defaults to `clean=True`, which calls `inspect.cleandoc()` — stripping leading/trailing blank lines and normalizing indentation.

The runbook code accounts for this in two ways:
1. `parse_doc_tags()` works on the cleaned output and additionally calls `inspectable_docstring()` (lines 916-932) which performs its own normalization — somewhat redundant but not harmful.
2. Line provenance is derived from AST node `lineno` attributes, not from text offsets.

The caveat (as the review notes) is for the quote-on-own-line form — `_docstring_start_line()` returns the `"""` line, but the first content line is one line later after cleaning, creating a one-line offset in source-location annotation. The runbook's tests cover only the same-line triple-quote form and do not test this edge case.
