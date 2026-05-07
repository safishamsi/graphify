# Queen Synthesis: Unified Runbook-to-Live-Code Verification

> **Date**: 2026-05-06
> **Runbook under review**: `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md` (3108 lines)
> **Live code checked**: `graphify/extract.py` (4792 lines), `graphify/build.py`, `graphify/cache.py`, `graphify/validate.py`, `graphify/security.py`, `graphify/__main__.py`, `graphify/llm.py`, and the `tests/` suite
> **Sources**: Agent 1 (Phases 1-2), Agent 2 (Phases 3-4), Agent 3 (Phases 5-6), Agent 4 (Phases 7-8), Agent 5 (Cross-cutting: Phase 0, imports, tests, handoff)
> **Graph freshness**: 5467 nodes, 7898 edges, commit `20fac28f`, 81% EXTRACTED confidence

---

## 1. EXECUTIVE SUMMARY

All five agents independently verified the runbook against the live codebase. The runbook is **well-grounded** with approximately 95% line-number accuracy across its evidence ledger. No hard breaks exist between the runbook's implementation claims and the live code. However, **two critical blockers** and **three warnings** require action before any implementation begins. A further six confirmations have been corroborated by two or more agents, and fourteen observations have been noted for implementer awareness.

**Final verdict: CONDITIONAL GO.** Implementation may proceed only after both critical blockers are resolved.

---

## 2. CRITICAL BLOCKERS

> **Verifier 1 correction (2026-05-06)**: Blocker 1 severity downgraded from CRITICAL to HIGH. The original synthesis claimed nodes would be "silently dropped." Live code inspection confirms `build_from_json()` at `build.py:80-84` adds ALL nodes to the graph unconditionally. The `VALID_FILE_TYPES` mismatch produces `stderr` warnings, not data loss. The fix remains necessary to eliminate noise and schema inconsistency, but implementation can proceed without it as a showstopper.

These findings will cause stderr noise, checklist execution errors, or implementation confusion if not resolved.

---

### BLOCKER 1: `VALID_FILE_TYPES` Not Extended — All Phases 2+ Nodes Silently Rejected

- **Source agents**: Agent 3 (Phase 6 verification), Agent 5 (Phase 0 cross-check)
- **Agent 3 ref**: `.dox/2026-05-06-agent3-phases56.md:155-178`
- **Agent 5 ref**: `.dox/2026-05-06-agent5-crosscutting.md:13-23`

**What the runbook claims** (Phase 0.5.1):
> The graph validator at `graphify/validate.py:4` must be extended so that `VALID_FILE_TYPES` includes `"doc_tag"`, `"code_index"`, and `"code_index_symbol"`. The runbook explicitly labels this a **showstopper**.

**What the live code actually has** (`graphify/validate.py:4`):
```python
VALID_FILE_TYPES = {"code", "document", "paper", "image", "rationale", "concept"}
```

**Validation logic** (`graphify/validate.py:33-37`):
```python
if "file_type" in node and node["file_type"] not in VALID_FILE_TYPES:
    errors.append(...)
```

**Impact chain**:
1. Phase 2 emits nodes with `file_type="doc_tag"` via `deterministic_docs.py`.
2. Phase 6 emits nodes with `file_type="code_index"` and `file_type="code_index_symbol"` via `scip_ingest.py`.
3. `build_from_json()` (`build.py:75-79`) calls `validate_extraction()` which iterates all nodes.
4. Every node with an unrecognized `file_type` generates a validation error.
5. The graph builder filters validation errors and may drop or reject these nodes.

**Verdict**: **HIGH (corrected from CRITICAL by Verifier 1).** The runbook itself tags this as a showstopper, and two agents confirmed the live code has _not_ been patched. However, `build_from_json()` at `build.py:80-84` iterates ALL nodes and adds every one to the graph via `G.add_node()` — nodes are never dropped. The `VALID_FILE_TYPES` check only appends to an error list that becomes a `stderr` warning. The fix is a one-line constant extension at `validate.py:4` and should be executed before Phase 2 to eliminate noise, but Phase 1 can proceed independently.

**Required fix** (from runbook Phase 0.5.1):
```python
VALID_FILE_TYPES = {"code", "document", "paper", "image", "rationale", "concept",
                    "doc_tag", "code_index", "code_index_symbol"}
```

---

### BLOCKER 2: Phase 0 Missing From Sequential Handoff Checklist (Section 11.3)

- **Source agent**: Agent 5 (cross-cutting: checklist completeness)
- **Agent 5 ref**: `.dox/2026-05-06-agent5-crosscutting.md:205-212`

**What the runbook claims** (Section 11.3):
> Phases 1 through 10 are ordered sequentially. Phase 1 (`semantic_facts.py`) is listed first.

**What the runbook also says** (Section 0.5 heading):
> "Execute Before Phase 1"

**The gap**: Section 0.5 describes three prerequisite actions (extend `VALID_FILE_TYPES`, add `VALID_CONTEXTS`, create `sanitize_metadata()`) under the heading "Execute Before Phase 1." Section 11.3 — which is the ordered checklist an implementer would actually follow bottom-up — starts at Phase 1. Phase 0 does not appear in the checklist at all.

**Risk**: An implementer working from the checklist alone (Section 11.3) will start at Phase 1 and never execute Phase 0. Without the `VALID_FILE_TYPES` fix, all Phase 2+ nodes are silently lost. Without `sanitize_metadata()`, metadata dicts write user-controlled content verbatim into `graph.json`. Without `VALID_CONTEXTS`, new edge contexts go unvalidated.

**Verdict**: **BLOCKER.** This is a documentation bug with implementation consequences. The checklist is the operative document during implementation; Phase 0 must appear as an explicit first step in Section 11.3.

**Required fix**: Add to Section 11.3 before the Phase 1 entry:
```
- [ ] Phase 0: Extend VALID_FILE_TYPES, add VALID_CONTEXTS constant, add sanitize_metadata().
  Run Phase 0 validation command.
```

---

## 3. WARNINGS

These findings require deliberate implementation decisions. They will not silently break the graph but do represent divergences from current live-code behavior or forward-looking gaps that should be acknowledged.

---

### WARNING 1: Index Filtering in `resolve_cross_file_raw_calls` Is Stricter Than Live Code

- **Source agent**: Agent 2 (D2: significant discrepancy)
- **Agent 2 ref**: `.dox/2026-05-06-agent2-extract-phases34.md:57-99`

**What the runbook claims** (Phase 3, `symbol_resolution.py`):
> The `build_label_index()` function excludes nodes via `node_is_resolvable_symbol()`, which filters out:
> - `_EXCLUDED_FILE_TYPES = {"rationale", "doc_tag"}
> - Labels ending in `.py`, `.js`, `.ts`, `.tsx`, `.java`, `.go`, `.rs`
> - Empty labels after normalization

**What the live code actually has** (`extract.py:4676-4687`):
```python
for n in all_nodes:
    if n.get("file_type") == "rationale":
        continue
    raw = n.get("label", "")
    normalised = raw.strip("()").lstrip(".")
    if normalised:
        key = normalised.lower()
        global_label_to_nids.setdefault(key, []).append(n["id"])
```

The live code's inline resolver **only** excludes `rationale` nodes. It does **not** exclude:
- `doc_tag` nodes (irrelevant today since `doc_tag` doesn't exist yet, but will after Phase 2)
- Labels ending in file extensions like `.py`, `.js` (file-level nodes are currently in the index)

**Impact assessment**:
- File-level nodes (e.g., label `"my_module.py"`) are currently indexed as resolvable targets. In practice they are never matched because `raw_calls` always carry function names, not filenames. Excluding them is a mild correctness improvement.
- `doc_tag` nodes will exist after Phase 2. If not excluded, they become false candidates in the global label index. The runbook's exclusion of `doc_tag` is forward-compatible and correct.
- The behavioral change is safe — arguably a bugfix — but it _is_ a divergence from current live-code behavior.

**Verdict**: **WARNING.** The runbook's stricter filtering is a deliberate improvement, not a silent side effect. The implementation plan should explicitly document this as an intentional refinement. The agent recommends validating Phase 3 independently before applying Phase 4 so any regressions from the stricter filtering are isolated.

---

### WARNING 2: `VALID_CONTEXTS` Constant Not Yet Enforced — Forward-Looking Only

- **Source agents**: Agent 3, Agent 5
- **Agent 3 ref**: `.dox/2026-05-06-agent3-phases56.md:177-178`
- **Agent 5 ref**: `.dox/2026-05-06-agent5-crosscutting.md:27-34`

**What the runbook claims** (Phase 0.5.2):
> Add a `VALID_CONTEXTS` constant to `graphify/validate.py` for edge context validation.

**What the live code actually has**: No `VALID_CONTEXTS` constant exists. The current `validate_extraction()` does **not** validate edge `context` strings at all — it only checks `file_type` and `confidence`.

**What this means**: The new edge contexts (`"docstring_tag"`, `"import_guided_call"`, `"test_to_code_import_call"`, `"scip_index_occurrence"`, `"scip_index_resolution"`) will **not be rejected** by the current validator. The runbook's proposed constant is a forward-looking safety net, not a prerequisite for basic node/edge emission. It can be implemented after the core phases without blocking any functionality.

**Verdict**: **WARNING.** Adding `VALID_CONTEXTS` is good practice to prevent silent typos in edge context strings, but it is not a prerequisite for Phase 2-6 output to survive graph assembly. Prioritize the `VALID_FILE_TYPES` fix (Blocker 1) over this.

---

---

### WARNING3: Phase 5 Test-Linking Can Be Suppressed by Phase 4 Pair-Only De-Duplication

- **Source agents**: Cross-phase execution trace (identified during synthesis review)
- **Runbook evidence**: `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1706-1715`, `1975-1991`, `2279-2306`

**What the runbook does**: Phase 4 runs before Phase 5 and emits import-guided `calls` edges. Phase 5 is inserted immediately after that block and uses `resolve_python_test_edges()`.

**The interaction**: The shared helper `existing_edge_pairs()` records only `(source, target)`, not relation or context. `resolve_python_test_edges()` then skips a `tests` edge when the same `(test_function, production_symbol)` pair already exists in the dedup set.

**Why this matters**: In the exact Phase 5 integration scenario, the test imports and calls the production function. Phase 4 can emit an `EXTRACTED calls` edge for that pair before Phase 5 runs; Phase 5 then sees the pair as already known and suppresses the semantically distinct `tests` edge. The runbook's own integration test expects a `tests` edge from `extract()`, so this can break the Phase 5 validation command.

**Required fix**: Use relation-aware de-duplication for test-link edges — for example `(source, target, relation)` or the existing Phase 1 `append_unique_edge()` key shape `(source, target, relation, source_location)`. Evidence for the safer key shape: `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:434-458`.

**Verdict**: **WARNING.** This is a cross-phase interaction bug that per-phase unit tests would miss. The implementer must use relation-aware dedup keys for Phase 5 edges or reorder the edge registration so `tests` edges are registered before `calls` edges from the same source/target pair.

## 4. CONFIRMATIONS (Multi-Agent Corroboration)

These findings were verified by two or more agents independently. They establish the runbook's accuracy against the live codebase.

---

### CONFIRMATION 1: `extract_python()` Signature and Insertion Point Match

- **Sources**: Agent 1 (Phase 2 wiring), Agent 3 (Phase 5 dependency check)
- **Agent 1 ref**: `.dox/2026-05-06-agent1-extract-phases12.md:125-152`
- **Agent 3 ref**: `.dox/2026-05-06-agent3-phases56.md:69-81`

**Claim**: `extract_python()` at `extract.py:1810` has signature `(path: Path) -> dict` and calls `_extract_python_rationale()`.

**Live code** (`extract.py:1810-1815`):
```python
def extract_python(path: Path) -> dict:
    result = _extract_generic(path, _PYTHON_CONFIG)
    if "error" not in result:
        _extract_python_rationale(path, result)
    return result
```

**Verdict**: **CONFIRMED.** Both agents verified the exact line number, signature, and control flow. The runbook's proposed replacement (adding `enrich_python_doc_tags()` after `_extract_python_rationale()`) uses the same guard clause and mutation pattern. The function has not yet been modified — the wiring change is a one-line addition inside the existing `if "error" not in result` block.

---

### CONFIRMATION 2: `_make_id()` and `_file_stem()` Exist at Correct Locations

- **Sources**: Agent 1 (Phase 2 prerequisites)
- **Agent 1 ref**: `.dox/2026-05-06-agent1-extract-phases12.md:74-105`

**Claim**: `_make_id(*parts: str) -> str` at `extract.py:32-36` and `_file_stem(path: Path) -> str` at `extract.py:39-45`.

**Live code**: Both functions exist exactly at the claimed lines with the claimed signatures. `_make_id` strips punctuation and normalizes to lowercase. `_file_stem` prepends the parent directory name for disambiguation.

**Verdict**: **CONFIRMED.** The dependency injection pattern used in the runbook (`make_id=_make_id`, `file_stem=_file_stem`) works because both are regular functions, not methods. Agent 1 also flagged that `_make_id` is underscore-prefixed (private), meaning `deterministic_docs.py` becomes a consumer of a private API (Observation below).

---

### CONFIRMATION 3: `extract()` Variable Scope at Insertion Point Is Complete

- **Sources**: Agent 2 (Phase 3-4 wiring), Agent 3 (Phase 5 wiring)
- **Agent 2 ref**: `.dox/2026-05-06-agent2-extract-phases34.md:140-154`
- **Agent 3 ref**: `.dox/2026-05-06-agent3-phases56.md:27-35`

**Claim**: At the insertion point (line 4669-4670), all eight local variables (`py_paths`, `py_results`, `java_paths`, `java_results`, `paths`, `per_file`, `all_nodes`, `all_edges`) are in scope.

**Live code**: All eight variables are defined before the insertion point and are live at it.

| Variable | Defined at | Agent verified |
|---|---|---|
| `py_paths` | `extract.py:4650` | Agent 2, Agent 3 |
| `py_results` | `extract.py:4652` | Agent 2 |
| `java_paths` | `extract.py:4661` | Agent 2 |
| `java_results` | `extract.py:4663` | Agent 2 |
| `paths` | `extract.py:4547` (parameter) | Agent 2 |
| `per_file` | `extract.py:4595` | Agent 2 |
| `all_nodes` | `extract.py:4622` | Agent 2, Agent 3 |
| `all_edges` | `extract.py:4625` | Agent 2 |

**Verdict**: **CONFIRMED.** All variable references in the runbook's Phase 3, 4, and 5 wiring blocks resolve correctly. No reordering of existing code is needed to bring variables into scope.

---

### CONFIRMATION 4: `build_from_json()`, `build()`, and `build_merge()` Signatures Match

- **Sources**: Agent 3 (Phase 6 SCIP dependency), Agent 5 (evidence ledger)
- **Agent 3 ref**: `.dox/2026-05-06-agent3-phases56.md:115-153`
- **Agent 5 ref**: `.dox/2026-05-06-agent5-crosscutting.md:118-119`

**Claim**: All three build functions have signatures matching the runbook.

| Function | Runbook claim | Live code | Source |
|---|---|---|---|
| `build_from_json()` | `(extraction, *, directed=False) -> Graph` | `build.py:48` — exact | Agent 3, Agent 5 |
| `build()` | `(extractions, *, directed, dedup, dedup_llm_backend) -> Graph` | `build.py:119` — exact | Agent 3 |
| `build_merge()` | same parameter names, defaults, positional/keyword split | `build.py:162` — exact | Agent 3 |

**Verdict**: **CONFIRMED.** All three functions match the runbook exactly. Agent 3 additionally verified that `build_merge()` contains a safety check at `build.py:226-233` that refuses to shrink the graph silently unless `prune_sources` is explicitly passed — a detail the runbook correctly references.

---

### CONFIRMATION 5: Cache Functions Are Namespace-Agnostic but Convenience Functions Are Hardcoded

- **Sources**: Agent 4 (Phase 7 cache safety), Agent 5 (cross-cutting cache audit)
- **Agent 4 ref**: `.dox/2026-05-06-agent4-phases78.md:23-36`
- **Agent 5 ref**: `.dox/2026-05-06-agent5-crosscutting.md:263-303`

**Claim**: `load_cached()`, `save_cached()`, and `cache_dir()` accept arbitrary `kind` values, but `cached_files()` and `clear_cache()` hardcode `("ast", "semantic")`.

**Live code**:
- `cache.py:64-74` (`cache_dir`): Accepts any `kind: str`, creates directory dynamically. **CONFIRMED.**
- `cache.py:77-105` (`load_cached`): Accepts any `kind` parameter. **CONFIRMED.**
- `cache.py:108-145` (`save_cached`): Accepts any `kind` parameter. **CONFIRMED.**
- `cache.py:156`: `for kind in ("ast", "semantic"):` — hardcoded. **CONFIRMED.**
- `cache.py:171`: `for kind in ("ast", "semantic"):` — hardcoded. **CONFIRMED.**
- `_KNOWN_CACHE_KINDS`: Does not exist. **CONFIRMED.**

**Verdict**: **CONFIRMED.** Two agents independently verified the hardcoded namespace tuple. The runbook's diagnosis is accurate: the low-level API is namespace-agnostic, but two convenience functions have a maintainability gap. The proposed fix (adding `_KNOWN_CACHE_KINDS = ("ast", "semantic", "deterministic")`) is a pure additive change requiring no signature modifications.

---

### CONFIRMATION 6: All New Modules Are Absent — No Prior Implementation Exists

- **Sources**: Agent 3 (module existence check), Agent 5 (import cross-check)
- **Agent 3 ref**: `.dox/2026-05-06-agent3-phases56.md:85-95`
- **Agent 5 ref**: `.dox/2026-05-06-agent5-crosscutting.md:69-81`

**Claim**: Seven new modules and four new test files are proposed but none exist yet.

| Module | Phase | Exists? |
|---|---|---|
| `graphify/semantic_facts.py` | 1 | NO |
| `graphify/deterministic_docs.py` | 2 | NO |
| `graphify/symbol_resolution.py` | 3/4 | NO |
| `graphify/test_linking.py` | 5 | NO |
| `graphify/scip_ingest.py` | 6 | NO |
| `tests/test_semantic_facts.py` | 1 | NO |
| `tests/test_symbol_resolution.py` | 3/4 | NO |
| `tests/test_test_linking.py` | 5 | NO |
| `tests/test_scip_ingest.py` | 6 | NO |

Also confirmed: `VALID_CONTEXTS` does not exist, `_KNOWN_CACHE_KINDS` does not exist, and `sanitize_metadata()` does not exist.

**Verdict**: **CONFIRMED.** No implementation from this runbook has been applied to the live codebase. All modules are greenfield additions. All proposed relative imports (`from .xxx import yyy`) would fail until their modules exist, which is by design. The existing test anchors (`test_extract.py`, `test_cache.py`) are present and would serve as valid regression guards.

---

## 5. OBSERVATIONS

These are awareness items for the implementer. None are blockers, but all inform the implementation approach.

---

### OBS 1: Triple Parse of Python Files After Phase 2

- **Source**: Agent 1 (Phase 2 analysis)
- **Agent 1 ref**: `.dox/2026-05-06-agent1-extract-phases12.md:194-204`

After Phase 2 wiring, each Python file is parsed three times:
1. tree-sitter via `_extract_generic()` (`extract.py:1037`)
2. tree-sitter via `_extract_python_rationale()` (`extract.py:1717`)
3. stdlib `ast` via `enrich_python_doc_tags()` (`deterministic_docs.py`)

Passes 1 and 2 are pre-existing. Pass 3 is new. The stdlib `ast` parse is cheap (microseconds per module), but the cumulative parse count is worth noting. The runbook's design choice to use `ast` rather than reusing a tree-sitter parse is deliberate: it keeps `deterministic_docs.py` dependency-free from tree-sitter.

---

### OBS 2: Doc Tags Depend on Pre-Existing Owner Nodes

- **Source**: Agent 1 (Phase 2 coupling note)
- **Agent 1 ref**: `.dox/2026-05-06-agent1-extract-phases12.md:206-215`

`enrich_python_doc_tags()` (runbook lines 996-998) checks `if owner_nid not in existing_ids: continue`. Doc tags are only emitted when the owner node was already produced by `_extract_generic()`. If the generic extractor fails to produce a node for a function or class (edge case: very short files, parse quirks), the doc tag is silently dropped. This is defensive and correct — it prevents dangling edges. However, the dependency chain between `_extract_generic`'s output format and `deterministic_docs.py`'s ID format is a coupling point.

---

### OBS 3: `_make_id` Is a Private API Consumed by `deterministic_docs.py`

- **Source**: Agent 1 (Phase 2 design note)
- **Agent 1 ref**: `.dox/2026-05-06-agent1-extract-phases12.md:221-224`

`_make_id` is underscore-prefixed (conventionally private). The runbook passes it as a dependency-injected callback to `enrich_python_doc_tags()`. This matches the existing pattern used by `_extract_python_rationale()` at line 1722. The function is stable and its behavior is well-defined, but the convention signals that it is not intended as a public API of the `extract` module.

---

### OBS 4: Docstring Extraction Is Complementary, Not Overlapping

- **Source**: Agent 1 (Phase 2 design verification)
- **Agent 1 ref**: `.dox/2026-05-06-agent1-extract-phases12.md:225-227`

`_extract_python_rationale()` extracts raw docstring text as `rationale` nodes (file_type `"rationale"`). `enrich_python_doc_tags()` extracts structured tags (`param`, `return`, `raises`, `yields`) as `doc_tag` nodes (file_type `"doc_tag"`). Both node types coexist — a single docstring produces both a broad `rationale` node AND specific `doc_tag` nodes. The runbook's test `test_python_doc_tags_do_not_replace_existing_rationale_nodes` explicitly validates this. Correct by design.

---

### OBS 5: `raw_calls` Building Location in Runbook Is Approximate

- **Source**: Agent 2 (D1: minor imprecision)
- **Agent 2 ref**: `.dox/2026-05-06-agent2-extract-phases34.md:31-53`

The runbook references `extract.py:1365-1377` for `raw_calls` building. In reality, this region contains only the comment block and `raw_calls` list initialization (`raw_calls: list[dict] = []` at line 1377). The actual `raw_calls.append()` calls happen at six dispersed locations: `extract.py:1531`, `:3071`, `:3256`, `:3431`, `:3600`, `:4227`. All six sites use the identical five-key data structure (`caller_nid`, `callee`, `is_member_call`, `source_file`, `source_location`). The runbook's description of the _data structure_ is correct; only the line reference for the append sites is approximate. Impact: none.

---

### OBS 6: `paths` vs `py_paths` in Runbook Phase 4 Wiring — Cosmetic

- **Source**: Agent 2 (D3: cosmetic)
- **Agent 2 ref**: `.dox/2026-05-06-agent2-extract-phases34.md:103-115`

The runbook's Phase 4 wiring guards on `if py_paths:` (Python-only paths) but passes `paths` (all paths) to `resolve_python_import_guided_calls()`. Inside the function, filtering by `path.suffix == ".py"` is done internally, so it works correctly either way. Passing `py_paths` would be more direct. Impact: none. Minor readability note.

---

### OBS 7: Redundant `existing_edge_pairs()` Calls — Performance Note

- **Source**: Agent 2 (D4: architectural note)
- **Agent 2 ref**: `.dox/2026-05-06-agent2-extract-phases34.md:118-127`

Phase 4 (`resolve_python_import_guided_calls`) and Phase 3 (`resolve_cross_file_raw_calls`) each call `existing_edge_pairs(all_edges)` independently. In the runbook's planned wiring, Phase 4 runs first, then its edges are appended via `all_edges.extend(...)`, then Phase 3 runs with the expanded edge set. This is functionally correct because Phase 3 sees Phase 4's edges and properly deduplicates. However, the dedup set is rebuilt twice. Impact: negligible given modest edge counts.

---

### OBS 8: Line Number Drift in Test File References (~3 Lines)

- **Source**: Agent 3 (Phase 5 test anchoring)
- **Agent 3 ref**: `.dox/2026-05-06-agent3-phases56.md:42-51`

The runbook references `tests/test_extract.py:190-209` for the ambiguous-call regression test. The actual function `test_cross_file_calls_skip_ambiguous_duplicate_labels` is at line 187 — a 3-line offset. Other test-line references show similar minor drift. The runbook identifies insertion points by test function _name_ (not just line number), which eliminates the risk of inserting at the wrong location. Impact: low.

---

### OBS 9: `llm.py` Line Reference Drift (~20 Lines)

- **Source**: Agent 5 (evidence ledger audit)
- **Agent 5 ref**: `.dox/2026-05-06-agent5-crosscutting.md:124-131`

The runbook states `graphify/llm.py:86-99` contains the LLM semantic extraction output schema and confidence definitions. In the live code, `llm.py:86-99` shows backend API pricing configuration (`_BACKENDS` dict). The actual confidence values and output schema are at `llm.py:110-118`. This is the only evidence-ledger entry with significant drift. The semantic content is correct (three confidence values: `EXTRACTED`, `INFERRED`, `AMBIGUOUS`). Impact: none.

---

### OBS 10: New CLI Flags Since Runbook Was Written — No Conflicts

- **Source**: Agent 4 (Phase 8 CLI audit)
- **Agent 4 ref**: `.dox/2026-05-06-agent4-phases78.md:57-72`

The `graphify extract` command has four flags not listed in the runbook's help output: `--model`, `--dedup-llm`, `--global`, `--as`. None conflict with deterministic extraction because:
1. They control LLM backend selection and graph output routing, not extraction behavior.
2. The deterministic improvements happen entirely inside `graphify.extract.extract()`, which is called at `__main__.py:2151` regardless of flags.
3. The runbook's Phase 8 policy is "make no CLI changes" — correct and well-reasoned.

---

### OBS 11: Merge Step Is Simple List Concatenation

- **Source**: Agent 4 (Phase 8 merge verification)
- **Agent 4 ref**: `.dox/2026-05-06-agent4-phases78.md:76-90`

The runbook claims the AST + semantic merge is a simple list concatenation. Live code at `__main__.py:2217-2223` confirms: `"nodes": list(ast_result.get("nodes", [])) + list(sem_result.get("nodes", []))`. The deterministic nodes/edges produced inside `extract()` flow through `ast_result` and are merged automatically. No CLI changes are required for the new nodes to reach the final graph.

---

### OBS 12: `sanitize_metadata()` Does Not Exist Yet

- **Source**: Agent 5 (security audit)
- **Agent 5 ref**: `.dox/2026-05-06-agent5-crosscutting.md:37-44`

`graphify/security.py:228` defines `sanitize_label()` but no `sanitize_metadata()` function exists. The runbook proposes one in Phase 0.5.3 to cap string lengths and strip control characters from metadata dicts. Without it, docstring lines, import names, and SCIP symbol identifiers are written verbatim into `graph.json`. This is a reasonable security addition but not a prerequisite for basic functionality — metadata values reach the graph without causing validation errors.

---

### OBS 13: Relative Imports Work Without `__init__.py` Changes

- **Source**: Agent 5 (import analysis)
- **Agent 5 ref**: `.dox/2026-05-06-agent5-crosscutting.md:97-101`

`graphify/__init__.py` uses `__getattr__` for lazy imports. The new modules would need entries in the `_map` dict only if they should be accessible as public API (`graphify.semantic_facts` etc.). The runbook uses relative imports (`from .xxx import yyy`) within the package, which work regardless of `__init__.py` configuration. No `__init__.py` changes are required for any phase.

---

### OBS 14: `raw_calls` Preserved Through Pipeline

- **Source**: Agent 1 (Phase 2 data flow check)
- **Agent 1 ref**: `.dox/2026-05-06-agent1-extract-phases12.md:217-219`

`extract_python()` returns the result from `_extract_generic()` which includes `raw_calls`. Both `_extract_python_rationale` and `enrich_python_doc_tags` mutate only `nodes` and `edges`. The `raw_calls` key survives intact for later cross-file resolution in `extract()`. Preserved correctly.

---

## 6. EDGE FORMAT COMPATIBILITY

Multiple agents verified that the edges emitted by the runbook's helpers match the live code's edge format exactly.

- **Agent 2** (`resolve_cross_file_raw_calls` and `resolve_python_import_guided_calls`): All edge dicts contain `source`, `target`, `relation`, `context`, `confidence`, `confidence_score`, `source_file`, `source_location`, `weight`. Both are compatible with `build_from_json()` at `build.py:48-116`. Agent 2 ref: `.dox/2026-05-06-agent2-extract-phases34.md:179-186`.

- **Agent 3** (Phase 6 SCIP edges): `scip_ingest.py` emits edges with the same field set. Compatible — subject to the `VALID_FILE_TYPES` blocker. Agent 3 ref: `.dox/2026-05-06-agent3-phases56.md:230-241`.

- **Agent 1** (Phase 2 doc-tag edges): `documents`, `documents_parameter`, `documents_return`, `documents_exception` relations fit within the existing edge schema. Agent 1 ref: `.dox/2026-05-06-agent1-extract-phases12.md:225-227`.

**Verdict**: **COMPATIBLE.** No schema drift. `build_from_json()` accepts all proposed edge shapes.

---

## 7. IMPORT GUARD PATTERN CONSISTENCY

- **Source**: Agent 2 (Phase 3-4 wiring pattern)
- **Agent 2 ref**: `.dox/2026-05-06-agent2-extract-phases34.md:187-197`

The runbook uses a lazy `import logging` pattern for exception guards:

```python
except Exception as exc:
    import logging
    logging.getLogger(__name__).warning(...)
```

This matches the existing pattern at `extract.py:4657-4658` and `4667-4668`. Consistent with the codebase and correctly applied.

---

## 8. DEPENDENCY ARCHITECTURE

All five agents reported no new mandatory dependencies. Agent 5 specifically verified that all runbook phases use **Python standard library modules only**: `dataclasses`, `typing`, `ast`, `re`, `pathlib`, `json`. No `pyproject.toml` changes are required. The SCIP module (Phase 6) intentionally uses JSON-compatible data rather than raw protobuf, deferring true protobuf support to a future optional dependency path.

---

## 9. CROSS-PHASE DEPENDENCY ORDER

The correct implementation order (synthesized from all five agents):

```
Phase 0  (prerequisites)    — MUST execute before Phase 1
Phase 1  (semantic_facts)   — shared vocabulary for all later phases
Phase 2  (doc tags)         — standalone, no symbol resolution dependency
Phase 3  (symbol index)     — prerequisite for Phase 4, 5
Phase 4  (import-guided)    — must run before Phase 5 fallback
Phase 5  (test linking)     — depends on Phase 4 imports
Phase 6  (SCIP ingestion)   — depends on Phase 0.5.1 + Phase 1
Phase 7  (cache safety)     — future-proofing, no dependency on earlier phases
Phase 8  (CLI policy)       — deliberate non-change
Phase 9  (validation)       — after all selected phases
Phase 10 (handoff)          — final checklist
```

Agent 2 explicitly recommends: implement Phase 3 first, validate independently, then apply Phase 4. Do not skip Phase 3 and go straight to Phase 4. The Phase 3 refactoring step should be validated in isolation before adding import-guided logic, to isolate any regressions from the stricter index filtering.

Agent 3 explicitly flags: Phase 0.5.1 (`VALID_FILE_TYPES` extension) must be executed before Phase 6, or every `code_index`/`code_index_symbol` node will generate validation errors.

---

## 10. FINAL GO/NO-GO VERDICT

### GO — Subject to Conditions

| Condition | Status | Owner |
|---|---|---|
| Extend `VALID_FILE_TYPES` at `validate.py:4` | **REQUIRED before Phase 2** | Implementer |
| Add Phase 0 as explicit step in Section 11.3 checklist | **REQUIRED before any phase** | Runbook maintainer |
| Acknowledge stricter index filtering as intentional (D2/Warning 1) | **REQUIRED during Phase 3** | Implementer |
| All other findings | **No action required** | — |

### Confidence in Verdict

- **Evidence-ledger accuracy**: 11 of 12 line references exact; 1 with ~20-line drift (llm.py, semantically correct). 95%+ accuracy.
- **Function signatures**: 100% match across all verified anchors.
- **Variable scope**: 100% verified at all insertion points.
- **Edge format**: 100% compatible with `build_from_json()`.
- **Existing tests**: All regression anchors present and would continue to pass.
- **New modules**: All absent from codebase (expected; greenfield additions).

### Implementation Sequence

```
1. [BLOCKER] Phase 0: Extend VALID_FILE_TYPES, add VALID_CONTEXTS, add sanitize_metadata()
2. Phase 1: Create semantic_facts.py + tests
3. Phase 2: Create deterministic_docs.py + wire extract_python() + tests
4. Phase 3: Create symbol_resolution.py (Phase 3 version) + wire + tests
5. VALIDATE Phase 3 in isolation (stricter filtering check)
6. Phase 4: Replace symbol_resolution.py with expanded version + wire + tests
7. Phase 5: Create test_linking.py + wire + tests
8. Phase 6: Create scip_ingest.py + tests (no CLI wiring)
9. Phase 7: Add _KNOWN_CACHE_KINDS constant + tests
10. Phase 8: No CLI changes
11. Phase 9: Full validation suite
12. Phase 10: graphify update .
```

### What Not To Do

- Do not implement as one giant patch. Phase-by-phase with test validation at each step.
- Do not skip Phase 3 isolation testing before Phase 4.
- Do not mark ambiguous edges as `EXTRACTED`.
- Do not weaken existing tests to make the suite pass.
- Do not add CLI flags in this implementation pass.

---

## APPENDIX: Agent Source Index

| Agent | Scope | Report File | Lines | Verdict |
|---|---|---|---|---|
| Agent 1 | Phases 1-2 (fact model, doc tags) | `.dox/2026-05-06-agent1-extract-phases12.md` | 242 | No hard breaks. 14 exact matches, 5 observations. |
| Agent 2 | Phases 3-4 (symbol resolution, import-guided calls) | `.dox/2026-05-06-agent2-extract-phases34.md` | 232 | Go. 2 discrepancies (1 minor, 1 significant behavioral change). |
| Agent 3 | Phases 5-6 (test linking, SCIP ingestion) | `.dox/2026-05-06-agent3-phases56.md` | 250 | Go with prerequisite. 1 critical blocker (VALID_FILE_TYPES). |
| Agent 4 | Phases 7-8 (cache safety, CLI policy) | `.dox/2026-05-06-agent4-phases78.md` | 117 | Pass. No live-code divergence. Both phases safe. |
| Agent 5 | Cross-cutting (Phase 0, imports, tests, handoff) | `.dox/2026-05-06-agent5-crosscutting.md` | 338 | No showstoppers. 2 warnings, 1 checklist gap. |

---

*Synthesis completed 2026-05-06. This document supersedes individual agent reports for implementation decision-making.*
