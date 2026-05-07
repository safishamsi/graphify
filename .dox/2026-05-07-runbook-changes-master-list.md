# Runbook Changes Master List

**Date:** 2026-05-07

**Purpose:** Single source of truth for every confirmed change the runbook needs before implementation. Consolidated from: GPT-5.5 independent review, queen synthesis, verifier reports, and verification results.

**Target artifact:** `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md`

**Verified by:** `.dox/2026-05-07-unified-verification.md` (35 of 37 claims confirmed)

---

## BLOCKER — Must Fix Before Implementation

### B1. Fix Phase Numbering Mismatch in the Phase Map

**Source:** GPT-5.5 independent review §1, verified by runbook consistency check

**Target:** `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:223-264`

**Problem:** The top-level phase map omits the import-guided Phase 4, shifts test linking to Phase 4, shifts SCIP to Phase 5, and compresses later phases. The handoff checklist at line ~3018 uses a different (correct) order. An implementer following the phase map will wire or test phases out of order.

**Fix:** Make the initial phase map match the handoff checklist exactly:
```
Phase 0: Schema and security prerequisites
Phase 1: Deterministic semantic fact model
Phase 2: Deterministic Python docstring/comment tag extraction
Phase 3: Symbol index and cross-file raw call resolver extraction
Phase 4: Python import-guided call resolution
Phase 5: Deterministic Python test-to-code linking
Phase 6: Optional SCIP index ingestion skeleton
Phase 7: Cache safety and deterministic extraction metadata
Phase 8: CLI integration policy
Phase 9: Required full validation suite
```

**Rationale:** The phase map is the table of contents implementers reference. Mismatch = confusion and bugs.

---

### B2. Fix Edge Deduplication Key — Pair-Only Keys Suppress Semantically Distinct Edges

**Source:** GPT-5.5 independent review §1, queen synthesis R2 (line 157), architectural claims verification

**Target:** `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1706-1715`

**Problem:** The shared helper `existing_edge_pairs()` records only `(source, target)`, not relation or context. Phase 4 runs before Phase 5 and can emit a `calls` edge. Phase 5 then skips a `tests` edge for the same `(source, target)` pair. The required Phase 5 integration test expects the `tests` edge to exist (line ~2448).

**Fix:** Change `existing_edge_pairs()` to use `(source, target, relation)` as the dedup key. If source locations matter, use `(source, target, relation, source_location)` — matching the Phase 1 `append_unique_edge()` convention at line ~434.

Affected insertion points that reference the old pair-only key:
- `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1706-1715` (helper definition)
- `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2279-2306` (Phase 5 de-dup block)

**Rationale:** `calls` and `tests` have different semantics. Pair-only dedup treats them as duplicates. This is a cross-phase interaction bug that per-phase unit tests would miss.

---

### B3. Extend `VALID_FILE_TYPES` in Phase 0

**Source:** Queen synthesis BLOCKER1, GPT-5.5 review §1 (confirmed correct but not yet in live code)

**Target:** Phase 0 section of the runbook, `graphify/validate.py:4-7` (live code)

**Problem:** The live validator only accepts `code`, `document`, `paper`, `image`, `rationale`, and `concept`. The runbook introduces new deterministic node types (`doc_tag`, `code_index`, `code_index_symbol`) but the live validator hasn't been extended. Missing `VALID_FILE_TYPES` causes schema warnings and strict validation failures — not node loss in `build_from_json()`, but noise and broken strict-validation contexts.

**Fix:** The Phase 0 code block already includes extending `VALID_FILE_TYPES`. Ensure the implementer adds `"doc_tag"`, `"code_index"`, and `"code_index_symbol"` before any code that emits those node types.

**Rationale:** Schema warnings from unknown `file_type` values create noise and break `assert_valid()`. This is a one-line fix and must be done first (Phase 0 means Phase 0).

---

## HIGH — Should Fix, Can Be Implementation Guardrails

### H1. NetworkX `DiGraph` Multigraph Concern

**Source:** GPT-5.5 independent review §4, architectural claims verification (qualified but valid)

**Target:** `graphify/build.py:90-112` (live code), runbook §1.3 and build integration sections

**Problem:** `networkx.DiGraph` stores one edge per `(source, target)` pair. `build_from_json()` calls `G.add_edge(src, tgt, **attrs)`, so later edges can overwrite earlier edge attributes for the same pair. Even if extraction emits both `calls` and `tests` edges, the graph representation may collapse them. However, the current code stores edge attributes in a separate dict (`build.py:100-108`) and `graphify-out/graph.html` renders multiple edges per pair — so the storage layer is multigraph-capable but the default `DiGraph` view may not be.

**Fix:** Add a note in the runbook build section: extraction emits multiple edges for the same `(source, target)` pair with different relations. The graph assembly must either:
- Use `nx.MultiDiGraph` if true multigraph semantics are needed, or
- Aggregate edge attributes when multiple relations exist for the same pair, or
- Document that the `DiGraph` edge attribute dict is the canonical representation and consumers should inspect attributes, not assume one edge per pair.

**Rationale:** This is a representation-layer concern. Extraction can be correct and graph assembly can still lose information if this isn't addressed. The current code partially handles this (separate attribute dict) but the runbook should make the policy explicit.

---

### H2. Add End-to-End Extraction Invariant Tests

**Source:** GPT-5.5 independent review §1, agent5 coverage report

**Target:** Runbook Phase 9 (validation suite), `tests/test_extract.py:106-115` (existing dangling-edge test)

**Problem:** The existing no-dangling-edge regression only checks `contains`, `method`, `inherits`, and `calls`. New relations (`tests`, `documents_parameter`, `documents_return`, `documents_exception`, `import_guided_call`, `references_definition`) have no dangling-edge coverage. The runbook's validation suite needs:

1. A test that checks every new internal relation has valid endpoints
2. A `build_from_json()` smoke test on fixtures containing `doc_tag`, `tests`, `code_index`, and `code_index_symbol` nodes
3. A schema-warning regression test ensuring no unknown `file_type` warnings

**Fix:** Add these tests to the Phase 9 validation section of the runbook.

**Rationale:** New node types and relations without dangling-edge tests = silent regressions. The existing test suite only validates old relations. This is how B2 (the dedup collision) would have been caught early — integration tests, not unit tests.

---

### H3. Add Docstring Edge-Case Tests (Quote-on-Own-Line, Nested Scopes)

**Source:** GPT-5.5 independent review §1

**Target:** Runbook Phase 2 test section (lines ~1151-1218)

**Problem:** The doc-tag parser uses `ast.get_docstring()` plus a computed starting line. Existing tests cover docstrings whose opening triple quote and summary are on the same line. They do NOT cover the common form where:

- The opening triple quote is on its own line (cleaned-docstring line offsets can drift from source line offsets)
- Module docstrings
- Class docstrings
- Async functions
- Nested methods
- Raw `# WHY:` comments

**Fix:** Add test fixtures for:
1. Quote-on-own-line docstrings
2. Module docstrings
3. Class docstrings
4. Async function docstrings
5. Nested method docstrings

If exact line provenance matters, either derive spans from AST node constants / `ast.get_source_segment()` rather than only from cleaned text, or document the known offset.

**Rationale:** Docstring line provenance is fragile. Missing edge cases = silently wrong `source_location` on doc-tag nodes. This is especially important if downstream consumers use line numbers for navigation.

---

### H4. Harden SCIP Ingestion for Production Use

**Source:** GPT-5.5 independent review §1, agent3 security report

**Target:** Runbook Phase 6, `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2524-2692`

**Problem:** The SCIP ingestion helper reads an entire JSON file into memory with:
- No size limit
- No depth limit
- No occurrence cap
- No path-root check
- No symbol-id length cap

It is safe for trusted test fixtures but not for arbitrary external indexes.

**Fix:** Add language to the runbook explicitly marking the Phase 6 helper as trusted-test-fixture-only until input caps and schema checks are added. If the team wants to accept arbitrary SCIP-like JSON from users, add:
1. File size limit
2. JSON depth limit
3. Symbol occurrence cap
4. Source path normalization
5. Symbol ID length cap
6. Collision-resistant node ID generation

**Rationale:** The runbook already says Phase 6 is optional and not CLI-wired. This hardens that statement with concrete acceptance criteria so an implementer doesn't accidentally expose it to untrusted input.

---

### H5. Add Diagnostics for Silent Exception Paths

**Source:** GPT-5.5 independent review §1, agent5 coverage report

**Target:** Runbook helpers that return empty results on failure:
- `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1006-1014` (doc tag OSError/SyntaxError)
- `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1751-1755` (import alias parsing)
- `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2252-2256` (test function scanning)
- `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2683-2692` (SCIP JSON loading)

**Problem:** Several planned helpers return empty results on errors. This is acceptable for resilient extraction, but too many empty-result fallbacks will make regressions look like "no facts found." Agent 5 found only 1 of 11 proposed error-handling paths tested.

**Fix:** The runbook should:
1. Require at least one test per silent error path (OSError, SyntaxError, JSONDecodeError)
2. Recommend debug logging for post-passes (not required, but recommended for implementation debugging)

**Rationale:** Silent failure = silent regression. The implementation should be testable. Debug logging helps the implementer verify behavior during development.

---

### H6. Apply Metadata Sanitization to Labels and Manual Edge Metadata

**Source:** Verifier3 blindspot 3.1, GPT-5.5 review §1 (confirmed partially resolved)

**Target:** Runbook Phase 1 code blocks:
- `make_fact_node()` at `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:391-411`
- Phase 4 edge metadata at `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1876-1895`
- Phase 5 edge metadata at `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2307-2327`

**Problem:** Phase 1's `fact_to_edge()` and `make_fact_node()` now call `sanitize_metadata()` on metadata (resolved). But:
- `make_fact_node()` does NOT sanitize labels, even though doc-tag labels include docstring-derived descriptions
- Phase 4 manually writes edge `metadata` without passing through `sanitize_metadata()`
- Phase 5 manually writes edge `metadata` without passing through `sanitize_metadata()`

**Fix:** 
1. Add `label = sanitize_label(label)` to `make_fact_node()` or document that labels are trusted call-site inputs
2. Route Phase 4 and Phase 5 manual edge metadata through `sanitize_metadata()` or document why they're safe (Python identifiers, constrained values)
3. Live `graphify/security.py:224-239` already provides `sanitize_label()` — use it

**Rationale:** Most Phase 4/5 metadata values are Python identifiers and relatively constrained, but the runbook's stated security objective is broader than its code. Docstring-derived labels are the larger practical exposure.

---

### H7. Clarify `VALID_CONTEXTS` Is Vocabulary-Only

**Source:** Verifier2 warnings-confirmations, GPT-5.5 review §1 (confirmed correct framing)

**Target:** `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:114-130`

**Problem:** The runbook currently says `VALID_CONTEXTS` is forward-looking documentation. This is correct. But an implementer may overestimate the protection — misspelled context strings will still pass validation because current validation doesn't check context strings.

**Fix:** Ensure the runbook explicitly states:
- `VALID_CONTEXTS` is a documented vocabulary constant, not active enforcement
- Validation currently checks confidence and endpoint IDs, not edge context (`graphify/validate.py:54-62`)
- If enforcement is desired later, it requires separate validator logic and tests

**Rationale:** The runbook already says this. The fix is ensuring the wording is unambiguous enough that an implementer doesn't assume `VALID_CONTEXTS` alone provides enforcement.

---

### H8. Fix Symbol Index Filtering Divergence

**Source:** Verifier2 warnings, GPT-5.5 review (cross-language section)

**Target:** Runbook Phase 3, `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1294-1313`

**Problem:** The runbook's symbol filtering hard-codes a narrow suffix list (`.py`, `.js`, `.ts`, `.tsx`, `.java`, `.go`, `.rs`) but the live extractor supports many more source suffixes (`.cpp`, `.rb`, `.cs`, `.kt`, `.swift`, `.sql`, `.md`, and others via `graphify/extract.py:4376-4429`). This mostly causes noise, not breakage (because `raw_calls` normally carry callable names, not filenames), but the intent is "exclude non-code nodes from symbol lookup."

**Fix:** Either:
1. Derive the suffix set from live extractor support (`_DISPATCH` in `extract.py`), or
2. Use a stronger node-kind predicate instead of hard-coding seven suffixes, or
3. Document the narrow list as a first-pass noise filter and accept the known gap

**Rationale:** The runbook's intent (exclude file-level and non-code nodes from symbol lookup) is correct. The implementation detail (7 hard-coded suffixes) is narrow. An implementer should know this is a known tradeoff, not an unnoticed gap.

---

## MEDIUM — Nice to Have, Won't Block Implementation

### M1. Correct Stale Evidence-Ledger Line References

**Source:** GPT-5.5 independent review, verifier3 observations, agent5 cross-cutting

**Target:** Evidence ledger section of the runbook

**Problem:** Several line references in the evidence ledger are stale compared to the live code:
- `graphify/llm.py:86-99` — live file has backend pricing/config there; confidence/schema definitions at `graphify/llm.py:105-118`
- `graphify/extract.py:1365-1377` — describes "builds raw_calls" but that region initializes/frames the list; actual append sites are dispersed
- `tests/test_extract.py:190-209` — may have shifted

**Fix:** Update stale anchors to current live code locations. If function names are followed, none of these cause implementation errors — they're orientation-only.

**Rationale:** Cosmetic. Should be fixed for completeness but won't block implementation.

---

### M2. Add Graph Relation Vocabulary Documentation

**Source:** GPT-5.5 independent review §6

**Target:** Runbook or separate schema document

**Problem:** New relations like `documents_parameter`, `documents_return`, `documents_exception`, `tests`, `references_definition`, and `import_guided_call` contexts don't have explicit definitions. Report/export consumers may infer meanings from names alone.

**Fix:** Add a short schema note or vocabulary table describing each new deterministic relation and its semantics.

**Rationale:** Documentation is cheap. Ambiguity in relation names is expensive for downstream consumers.

---

### M3. Warn About Downstream Consumer Impact

**Source:** Agent5 coverage report, GPT-5.5 review §4

**Target:** Runbook implementation risks section

**Problem:** New node types and relations may affect community detection, god-node rankings, HTML display, JSON consumers, and export formats. The runbook doesn't explicitly flag this.

**Fix:** Add a note that implementation should include at least one graph-report smoke test after the upgrade to verify that new node types don't create unintended god-node or community artifacts.

**Rationale:** Graphify's graph structure drives downstream analysis. A blind upgrade could produce unexpected community clusters or god-node rankings.

---

### M4. Consider Splitting Implementation Into Two Pull Requests

**Source:** GPT-5.5 independent review §6

**Target:** Runbook implementation handoff checklist

**Problem:** The full plan includes core deterministic extraction (Phases 0-5, 7-9) and optional SCIP ingestion (Phase 6). These are independent concerns.

**Fix:** Recommend in the handoff checklist:
- PR 1: Core deterministic extraction (Phases 0-5, 7-9)
- PR 2: Optional SCIP ingestion (Phase 6), only after PR 1 is stable

**Rationale:** SCIP ingestion is explicitly optional and not CLI-wired. Smaller PRs are easier to review, test, and revert. The runbook already says SCIP should not be wired in the first pass — this formalizes it.

---

### M5. Avoid Cache Namespace Changes Without Demonstrated Need

**Source:** GPT-5.5 independent review §4

**Target:** Runbook Phase 7

**Problem:** The runbook proposes `_KNOWN_CACHE_KINDS` future-proofing. Current cache helper methods iterate only `ast` and `semantic` namespaces (`graphify/cache.py:148-175`). If deterministic semantic passes are embedded into AST extraction results, cache changes may be unnecessary for the first implementation.

**Fix:** Defer cache namespace changes until there is a demonstrated stale-cache bug. Implement Phase 7 only if Phase 2 or Phase 3 extraction results are stored separately from AST results.

**Rationale:** Unnecessary cache changes introduce risk for no benefit. The runbook already says Phase 7 is optional and small — this clarifies the trigger condition.

---

### M6. Add "Must Not Regress" Graph-Quality Budget

**Source:** GPT-5.5 independent review §6

**Target:** Runbook Phase 9 validation section

**Problem:** The implementation adds new node types and edges. Without a regression budget, it's hard to distinguish "expected new facts" from "unexpected noise."

**Fix:** Add a checklist item for the validation phase:
- No large increase in inferred raw `calls` edges
- No doc-tag nodes becoming god nodes
- No avoidable `VALID_FILE_TYPES` or `VALID_CONTEXTS` validator warnings
- No drop in extracted/validated node counts on the fixture corpus
- `graphify update .` shows expected graph delta, not unexpected community restructuring

**Rationale:** This gives the implementer concrete pass/fail criteria beyond "tests pass."

---

## Security Findings Already Addressed

The following security findings from the agent/verifier pipeline are already addressed in the current runbook or covered by items above:

| Finding | Status | Covered By |
|---|---|---|
| `ast.get_docstring(clean=False)` | Resolved — removed from runbook | N/A |
| `_clean_docstring()` dead code | Resolved — removed from runbook | N/A |
| Phase 0 missing from checklist | Resolved — added to current runbook | N/A |
| `sanitize_metadata()` call gap in Phase 1 | Partially resolved — wired in `fact_to_edge()` and `make_fact_node()` | H6 (labels and manual edge metadata still need sanitization) |
| SCIP unbounded input | Not resolved | H4 |
| Silent exception swallowing | Not resolved | H5 |
| `VALID_FILE_TYPES` not extended in live code | Not resolved — needs implementation | B3 |

---

## Verification Status

The GPT-5.5 independent review was independently verified by 3 verification agents (`.dox/2026-05-07-unified-verification.md`):

| Category | Verified | Qualified | Wrong |
|---|---|---|---|
| External references (10 claims) | 10 | 0 | 0 |
| Live code anchors (12 claims) | 11 | 1 | 0 |
| Runbook internal consistency (8 claims) | 7 | 1 | 0 |
| Architectural risks (7 claims) | 7 | 0 | 0 |
| **Total** | **35** | **2** | **0** |

The 2 qualified claims are:
1. NetworkX multigraph concern — valid but more nuanced than stated (handled in H1)
2. Phase numbering mismatch — real, confirmed by runbook consistency check (handled in B1)

---

## Implementation Order Recommendation

1. **B3** — Extend `VALID_FILE_TYPES` (Phase 0, one-line fix)
2. **B1** — Fix phase numbering mismatch (runbook edit only)
3. **B2** — Fix edge deduplication key (affects Phase 4 and Phase 5 code)
4. **H1** — Document NetworkX multigraph policy (informs build integration)
5. **H2–H8** — Handle as implementation guardrails (can be done during/after coding)
6. **M1–M6** — Nice-to-have, do not block implementation

---

## Bottom Line

The runbook is implementation-ready with these changes. The 3 blockers (B1–B3) are the only mandatory pre-implementation fixes. Everything else can be handled as implementation guardrails or follow-up tasks.
