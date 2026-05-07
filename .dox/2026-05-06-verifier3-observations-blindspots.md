# Verifier 3: Observations, Compatibility & Blind Spot Audit

> **Date**: 2026-05-06
> **Subject**: `.dox/2026-05-06-queen-synthesis.md` (535 lines)
> **Scope**: OBSERVATIONS verification, COMPATIBILITY claims, blind spot check, severity audit
> **Live code checked**: `graphify/extract.py`, `graphify/validate.py`, `graphify/llm.py`, `graphify/build.py`, `graphify/__init__.py`, `tests/test_extract.py`, `pyproject.toml`

---

## 1. OBSERVATIONS VERIFICATION (Hallucination Risk Check)

### OBS 1: Triple Parse — CONFIRMED, no hallucination

The claim that `extract_python()` triggers three parses is correct:
1. tree-sitter via `_extract_generic()` — pre-existing
2. tree-sitter via `_extract_python_rationale()` at `extract.py:1717` — pre-existing
3. stdlib `ast` via `enrich_python_doc_tags()` — new after Phase 2

The stdlib `ast` is a lightweight parse; the observation is factual, not a risk.

### OBS 2: Doc Tags Depend on Pre-Existing Owner Nodes — CONFIRMED

Verified: `enrich_python_doc_tags()` checks `if owner_nid not in existing_ids: continue`. This coupling is real but defensive (prevents dangling edges). The observation correctly identifies the dependency chain between `_extract_generic` output format and `deterministic_docs.py` ID format as a coupling point. No hallucination.

### OBS 3: `_make_id` Is Private API — CONFIRMED, nuanced

`_make_id` is indeed underscore-prefixed at `extract.py:32-36`. The runbook passes it as a dependency-injected callback. This matches the existing pattern at `extract.py:1722` where `_extract_python_rationale` already imports `_make_id`. The queen synthesis correctly notes the convention. **No hallucination.** However, the practical risk is minimal — `_make_id` is a pure string normalizer with no side effects, and the codebase already bypasses the underscore convention for internal module consumers.

### OBS 4: Docstring Extraction Is Complementary — CONFIRMED

`_extract_python_rationale()` produces `rationale` nodes (file_type `"rationale"`). `enrich_python_doc_tags()` produces `doc_tag` nodes (file_type `"doc_tag"`). Two distinct node types from the same docstring. The runbook's test `test_python_doc_tags_do_not_replace_existing_rationale_nodes` validates this. **No hallucination.**

### OBS 5: raw_calls Building Location — CONFIRMED (queen synthesis is MORE accurate)

**Runbook claim**: `extract.py:1365-1377` for raw_calls building.
**Queen synthesis correction**: Six dispersed `raw_calls.append()` locations: `:1531`, `:3071`, `:3256`, `:3431`, `:3600`, `:4227`.

**Live code verification**: All six line numbers confirmed exact via `fs_search`:
```
extract.py:1531   — _extract_generic (Python/JS/TS/other)
extract.py:3071   — extract_go()
extract.py:3256   — extract_rust()
extract.py:3431   — extract_zig()
extract.py:3600   — extract_powershell()
extract.py:4227   — extract_elixir()
```

All six sites use the identical five-key data structure (`caller_nid`, `callee`, `is_member_call`, `source_file`, `source_location`). **Queen synthesis is more precise than the runbook here.** No hallucination.

### OBS 6: `paths` vs `py_paths` Cosmetic — CONFIRMED

The runbook Phase 4 wiring guards on `if py_paths:` (line 4650) but passes `paths` to `resolve_python_import_guided_calls()`. The function internally filters by `path.suffix == ".py"`. Functionally correct, just redundant filtering. **No hallucination.** No impact.

### OBS 7: Redundant `existing_edge_pairs()` — CONFIRMED

Both Phase 3 and Phase 4 independently rebuild the dedup set. Phase 4 runs first, edges are appended, then Phase 3 sees the expanded set. Functionally correct; performance negligible. The queen synthesis correctly notes this as an architectural observation. **No hallucination.**

### OBS 8: Line Number Drift in Test Files — CONFIRMED, but **queen synthesis itself has a minor inaccuracy**

**Queen synthesis claim**: `test_cross_file_calls_skip_ambiguous_duplicate_labels` is at line 187.
**Live code verification**: The function definition is at `tests/test_extract.py:187`. **Confirmed exact.**

**Queen synthesis claim**: "The runbook references `tests/test_extract.py:190-209`"
**Verification**: The runbook's reference to lines 190-209 would be a 3-line offset from the actual function start (line 187). The queen synthesis correctly identifies the drift.

**But note**: The queen synthesis says "The runbook identifies insertion points by test function name... eliminating risk." This is correct — the function name `test_cross_file_calls_skip_ambiguous_duplicate_labels` is unambiguous regardless of line drift. **No hallucination.**

### OBS 9: llm.py Line Reference Drift — CONFIRMED, queen synthesis is CORRECT

**Runbook claim**: `llm.py:86-99` contains confidence definitions and output schema.
**Live code verification**: `llm.py:86-90` is the `_BACKENDS` dict (`openai` backend config). The actual confidence definitions are at `llm.py:110-112` inside `_EXTRACTION_SYSTEM`.

**Verification detail**:
- `llm.py:86-90`: `"openai": {...}` (backend config)
- `llm.py:105-119`: `_EXTRACTION_SYSTEM` containing:
  - Lines 110-112: Confidence rules (`EXTRACTED`, `INFERRED`, `AMBIGUOUS`)
  - Lines 117-118: Output schema JSON

The queen synthesis is correct that the runbook's line reference is off by ~20 lines. The semantic content is correct (three confidence values). **No hallucination; queen synthesis is more precise than the runbook.**

### OBS 10: New CLI Flags — CONFIRMED

The `graphify extract` command has flags (`--model`, `--dedup-llm`, `--global`, `--as`) not listed in the runbook. These control LLM backend selection and output routing, not extraction behavior. The deterministic improvements happen inside `graphify.extract.extract()` which is called regardless of flags. **No hallucination.** No conflicts.

### OBS 11: AST + Semantic Merge Is List Concatenation — CONFIRMED

Live code at `build.py:48-116` shows `build_from_json()` accepts a single extraction dict. The merge at `__main__.py` concatenates node/edge lists. The queen synthesis correctly notes that no CLI or build changes are required. **No hallucination.**

### OBS 12: `sanitize_metadata()` Doesn't Exist — CONFIRMED

`graphify/security.py` defines `sanitize_label()` but no `sanitize_metadata()` function. The runbook proposes one in Phase 0.5.3. **No hallucination.** However, see Blind Spot 1 below — the runbook's Phase 1 code blocks don't include calls to `sanitize_metadata()`.

### OBS 13: __init__.py Relative Imports — CONFIRMED

`graphify/__init__.py` uses `__getattr__` for lazy imports with a `_map` dict. New modules would need `_map` entries only if accessed as `graphify.semantic_facts` etc. The runbook uses `from .xxx import yyy` which works regardless. **No hallucination.** Verified by reading `__init__.py`.

### OBS 14: raw_calls Preserved Through Pipeline — CONFIRMED

`extract_python()` returns `result` from `_extract_generic()` which includes `raw_calls`. Both `_extract_python_rationale` and `enrich_python_doc_tags` mutate only `nodes` and `edges`. The `raw_calls` key survives intact for later cross-file resolution. **No hallucination.**

---

## 2. COMPATIBILITY VERIFICATION

### 2.1 Edge Format Binary-Identical Check

**Live code** `resolve_cross_file_raw_calls` output (`extract.py:4709-4719`):
```python
{
    "source": caller,
    "target": tgt,
    "relation": "calls",
    "context": "call",
    "confidence": "INFERRED",
    "confidence_score": 0.8,
    "source_file": rc.get("source_file", ""),
    "source_location": rc.get("source_location"),
    "weight": 1.0,
}
```

**Runbook** `resolve_cross_file_raw_calls` (Phase 3, `symbol_resolution.py`):
Same keys, same structure, same confidence value (`0.8`), same relation (`"calls"`), same context (`"call"`).

**Verdict**: **Binary-identical.** All field names, types, and default values match exactly.

**Runbook** `fact_to_edge()` output (Phase 1, `semantic_facts.py`):
All seven required fields (`source`, `target`, `relation`, `confidence`, `confidence_score`, `source_file`, `source_location`) plus optional `weight`, `context`, `metadata` match the live code's edge format.

**`build_from_json()` acceptance** (`build.py:90-112`):
The builder extracts `source` and `target` for graph connectivity, then passes ALL remaining keys as edge attributes via `{k: v for k, v in edge.items() if k not in ("source", "target")}`. Unknown or extra keys are silently stored as edge attributes, never rejected. **No schema enforcement beyond source/target presence.**

### 2.2 Import Guard Pattern Consistency — CONFIRMED

**Runbook pattern**:
```python
except Exception as exc:
    import logging
    logging.getLogger(__name__).warning(...)
```

**Live code instances verified**:
- `extract.py:4656-4658`: `except Exception as exc: \n import logging \n logging.getLogger(__name__).warning("Cross-file import resolution failed, skipping: %s", exc)`
- `extract.py:4666-4668`: `except Exception as exc: \n import logging \n logging.getLogger(__name__).warning("Java cross-file import resolution failed, skipping: %s", exc)`

**Verdict**: **Consistent.** The runbook's lazy-import logging pattern matches the live code exactly — same indentation, same `__name__` logger, same positional `%s` formatting. No divergence.

### 2.3 Node Format Compatibility

The runbook introduces three new `file_type` values: `doc_tag`, `code_index`, `code_index_symbol`. These are the subject of BLOCKER 1 (VALID_FILE_TYPES not extended). The node format itself (fields `id`, `label`, `file_type`, `source_file`, `source_location`) is identical to existing nodes. Once VALID_FILE_TYPES is extended, `build_from_json()` will accept these nodes without modification.

---

## 3. BLIND SPOT CHECK

### Blind Spot 3.1: `sanitize_metadata()` Call Gap

**Severity**: WARNING

The runbook Phase 0.5.3 (line 158) says:
> "Call `sanitize_metadata()` inside `fact_to_edge()` (runbook Phase 1) and `make_fact_node()` (runbook Phase 1) before storing metadata on emitted dicts."

However, the actual Phase 1 code blocks for `fact_to_edge()` and `make_fact_node()` in the runbook do **not** include calls to `sanitize_metadata()`. The code simply copies the fact's metadata dict:
```python
if fact.metadata:
    edge["metadata"] = dict(fact.metadata)
```

**Impact**: If the implementer adds `sanitize_metadata()` to `security.py` (as Phase 0.5.3 instructs) but does not add the actual invocation calls inside `fact_to_edge()` / `make_fact_node()`, the sanitization function becomes dead code. Metadata dicts would be written verbatim. This is not a blocker — unsanitized metadata doesn't cause validation errors — but it means Phase 0.5.3's security objective is not met unless the implementer explicitly remembers to wire the call.

**Recommendation**: The runbook's Phase 1 code blocks should be updated to include `from graphify.security import sanitize_metadata` and the actual call before metadata dict copying. Currently, the instructions and code blocks are inconsistent.

**This was not mentioned in the queen synthesis.** The queen synthesis notes (OBS12) that `sanitize_metadata()` doesn't exist yet, but does not flag the gap between Phase 0 instructions ("call it") and Phase 1 code blocks (which don't call it).

### Blind Spot 3.2: `VALID_CONTEXTS` Does Not Exist at All

**Severity**: CORRECTION to queen synthesis framing

The queen synthesis describes `VALID_CONTEXTS` as "not yet enforced in validator" (WARNING2, OBS summary). This framing is slightly misleading. The live `validate.py` has **no** concept of edge context validation — there is no `VALID_CONTEXTS` constant, no context-checking logic, and the `validate_extraction()` function (lines 10-64) only validates:
- `file_type` against `VALID_FILE_TYPES` (nodes)
- `confidence` against `VALID_CONFIDENCES` (edges)
- Required field presence (nodes: `id`, `label`, `file_type`, `source_file`; edges: `source`, `target`, `relation`, `confidence`, `source_file`)
- Edge source/target references to node IDs

**Edge context is completely unvalidated.** The runbook's proposed new contexts (`"docstring_tag"`, `"import_guided_call"`, `"test_to_code_import_call"`, `"scip_index_occurrence"`, `"scip_index_resolution"`) would pass through silently regardless of whether `VALID_CONTEXTS` is added or not.

The queen synthesis at line 269 ("Also confirmed: `VALID_CONTEXTS` does not exist") is technically correct, but the repeated framing as "not yet enforced" (implying the constant exists but is unused) is slightly inaccurate. The constant was **never introduced**.

### Blind Spot 3.3: `graspologic` Python Version Constraint

**Severity**: NON-BLOCKING (no impact on runbook)

`pyproject.toml:54`:
```toml
leiden = ["graspologic; python_version < '3.13'"]
```

The leiden community detection feature cannot be installed on Python 3.13+. None of the runbook's 10 phases touch community detection or require `graspologic`. This is a **0% impact** finding — recorded here for completeness so it is definitively excluded from the blind spot list.

### Blind Spot 3.4: Module-Level Mutable Globals

**Severity**: NON-BLOCKING

`extract.py:48` — `_TSCONFIG_ALIAS_CACHE: dict[str, dict[str, str]] = {}`

This is the only module-level mutable global in the extraction pipeline. It is keyed by tsconfig path strings. Tests using `tmp_path` get unique keys. In production, the cache is populated once and persists across multiple `extract_python()` calls within the same process — this is correct and desirable.

**Risk**: If two tests reference the same tsconfig path (e.g., a shared fixture), the cache would leak state between tests. Current test fixtures don't exercise this pattern.

**Not a blind spot for the runbook.** The runbook's new modules (`deterministic_docs.py`, `symbol_resolution.py`, etc.) introduce no new module-level mutable state.

### Blind Spot 3.5: Python 3.10+ Compatibility — CONFIRMED SAFE

The runbook uses:
- `from __future__ import annotations` — available since Python 3.7
- `ast` — stdlib, `ast.Module` type hint is current (not deprecated)
- `dataclasses` — stdlib since 3.7
- `typing.Callable`, `typing.Any`, `typing.Iterable` — all available in 3.10+
- `pathlib`, `re`, `json` — stdlib

**No Python 3.11+ features** (e.g., `StrEnum`, `Self`, `ExceptionGroup`, PEP 695 type aliases, `tomllib`) are used in any runbook code.

**No deprecated AST types**: Search for `ast.Str`, `ast.Num`, `ast.Bytes`, `ast.NameConstant`, `ast.Ellipsis` across the entire codebase returned **zero** results.

**Verdict**: The runbook code is fully compatible with `requires-python = ">=3.10"` at `pyproject.toml:12`.

### Blind Spot 3.6: Test Ordering — Unit Tests Bypass the Validator

**Severity**: CORROBORATION of queen synthesis finding

The queen synthesis at line 49 correctly notes: "unit tests bypass the validator." This means that unit tests for new modules will pass (they test extraction output directly) even if `VALID_FILE_TYPES` hasn't been extended. During actual graph assembly via `build_from_json()`, `validate_extraction()` is called, and unrecognized file types generate errors.

This is a confirmed risk, not a new blind spot — the queen synthesis already flagged it. However, it's worth emphasizing: the implementer might run tests, see all green, and believe the implementation is complete, only to discover during end-to-end testing that nodes are rejected.

### Blind Spot 3.7: New Edge `relation` Values Not Validated

**Severity**: LOW

The runbook introduces new edge `relation` values: `"documents"`, `"documents_parameter"`, `"documents_return"`, `"documents_exception"`, `"test_to_code_import_call"`, `"scip_index_occurrence"`, `"scip_index_resolution"`.

The live `validate.py` does **not** validate `relation` values — there is no `VALID_RELATIONS` constant. Edge relations are stored as attributes on the NetworkX edge without any validation. These new relation values will be accepted silently. This is neither a problem nor a blind spot; it's simply how the current codebase works.

**The queen synthesis doesn't mention this**, but it's not a gap — edge relation validation was never part of the schema.

---

## 4. SEVERITY AUDIT

### Classification Review

| Finding | Queen Classification | Verifier Assessment | Rationale |
|---|---|---|---|
| BLOCKER 1: VALID_FILE_TYPES not extended | BLOCKER | **CORRECT** | Will cause silent node rejection. Runbook itself tags as showstopper. |
| BLOCKER 2: Phase 0 missing from checklist | BLOCKER | **CORRECT** | Implementer following checklist bottom-up would skip prerequisites. |
| WARNING 1: Stricter index filtering | WARNING | **CORRECT** | Deliberate improvement, not a bug. Should be documented. |
| WARNING 2: VALID_CONTEXTS forward-looking | WARNING | **CORRECT** | Not a blocker; edge context is unvalidated regardless. Can be added post-implementation. |
| OBS 2: EXCLUDED_FILE_TYPES divergence | OBSERVATION | **UPGRADE TO WARNING** | The runbook's ~25 entries vs live code's ~50+ entries. If the implementer uses the runbook's shorter list during Phase 3 index building, binary files, fonts, media, and cache directories would be included in the label index. This won't break the graph but will produce noise. The queen synthesis itself acknowledges `_DEFAULT_EXCLUDED_FILE_TYPES` is different from `_EXCLUDED_FILE_TYPES`, but classifies it as OBS when it should be WARNING. |
| OBS 12: VALID_CONTEXTS framing | OBSERVATION | **FRAMING CORRECTION** | The queen synthesis says "VALID_CONTEXTS not yet enforced" which implies the constant exists but is unused. In reality, `VALID_CONTEXTS` was never introduced — the concept does not exist in `validate.py`. This is a framing inaccuracy, not a misclassification of severity. |
| Blind Spot 3.1: sanitize_metadata call gap | Not mentioned in queen synthesis | **NEW WARNING** | The runbook Phase 0.5.3 says to "call sanitize_metadata() inside fact_to_edge() and make_fact_node()" but the Phase 1 code blocks do not include those calls. An implementer who adds the function to security.py but doesn't wire the calls gets dead code and unsanitized metadata. |

### No Upgrades from WARNING to BLOCKER

- WARNING 1 (stricter filtering): Intentional design choice. Does not break graph assembly.
- WARNING 2 (VALID_CONTEXTS): Edge context is completely unvalidated in the live code; adding or not adding the constant changes nothing about current behavior. Correctly stays at WARNING.

### No Upgrades from OBSERVATION to BLOCKER

All observations are informational or cosmetic. None would cause silent data loss or graph rejection.

---

## 5. SUMMARY

### Queen Synthesis Accuracy

- **14 observations**: All 14 observations verified against live code. Zero hallucinations.
- **1 framing inaccuracy**: OBS12/WARNING2 framing of `VALID_CONTEXTS` as "not yet enforced" is slightly misleading — the constant was never introduced, not merely unenforced.
- **1 severity misclassification**: OBS2 (EXCLUDED_FILE_TYPES divergence) should be WARNING, not OBSERVATION. The shorter list would include unwanted file types in the index.
- **1 new blind spot found**: The `sanitize_metadata()` call gap between Phase 0.5.3 instructions and Phase 1 code blocks was not mentioned by any agent.

### Edge Format Compatibility

**CONFIRMED.** Binary-identical between runbook and live code. All edge dicts share the same seven-field structure. `build_from_json()` uses a permissive attribute pass-through pattern that accepts unknown keys silently.

### Import Guard Pattern Consistency

**CONFIRMED.** The runbook's lazy `import logging` pattern matches `extract.py:4656-4658` and `4667-4668` exactly.

### Overall Verdict

The queen synthesis is **95%+ accurate** in its observations. The two blockers are correctly classified. One observation (OBS2) should be upgraded to WARNING. One new warning-level blind spot (sanitize_metadata call gap) was discovered. No observations contain hallucinations about the live code. The runbook is compatible with Python 3.10+, uses no deprecated AST types, and introduces no module-level mutable state that would endanger test isolation.
