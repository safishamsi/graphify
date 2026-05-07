# Verifier 1: Critical Blocker Claims — Live Code Evidence

> **Date**: 2026-05-06
> **Source document**: `.dox/2026-05-06-queen-synthesis.md` (Section 2: CRITICAL BLOCKERS)
> **Live code verified**: `graphify/validate.py`, `graphify/build.py`
> **Runbook verified**: `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md`

---

## Claim 1: `VALID_FILE_TYPES` at `graphify/validate.py:4` is not extended

**Synthesis claim** (lines 34-36):
> The live code has `VALID_FILE_TYPES = {"code", "document", "paper", "image", "rationale", "concept"}` and does NOT include `"doc_tag"`, `"code_index"`, `"code_index_symbol"`.

### Verdict: **TRUE**

**Evidence** — `graphify/validate.py:4`:
```python
VALID_FILE_TYPES = {"code", "document", "paper", "image", "rationale", "concept"}
```

The set contains exactly 6 values. `"doc_tag"`, `"code_index"`, and `"code_index_symbol"` are absent. This matches the synthesis claim exactly.

---

## Claim 2: Nodes with `file_type="doc_tag"` or `"code_index"` would be rejected/dropped

**Synthesis claim** (lines 45-50):
> 1. Phase 2 emits nodes with `file_type="doc_tag"`.
> 2. Phase 6 emits nodes with `file_type="code_index"` and `file_type="code_index_symbol"`.
> 3. `build_from_json()` calls `validate_extraction()` which iterates all nodes.
> 4. Every node with an unrecognized `file_type` generates a validation error.
> 5. The graph builder filters validation errors and may drop or reject these nodes.

**Synthesis claim** (lines 52):
> "...see all doc-tag and SCIP nodes vanish during actual graph assembly."

**Runbook claim** (runbook line 99):
> "...will be silently dropped from the graph."

### Verdict: **PARTIALLY FALSE — Overstated impact**

The validation error generation is TRUE. The claim of nodes being dropped/rejected is FALSE. Here is the exact code path:

#### Step 1 — `validate_extraction()` at `graphify/validate.py:33-37`
```python
if "file_type" in node and node["file_type"] not in VALID_FILE_TYPES:
    errors.append(
        f"Node {i} (id={node.get('id', '?')!r}) has invalid file_type "
        f"'{node['file_type']}' - must be one of {sorted(VALID_FILE_TYPES)}"
    )
```
An error string is appended to the `errors` list. The node is NOT removed, filtered, or rejected. The function returns the error list — it does not raise.

#### Step 2 — `build_from_json()` at `graphify/build.py:75-84`
```python
errors = validate_extraction(extraction)
# Dangling edges (stdlib/external imports) are expected - only warn about real schema errors.
real_errors = [e for e in errors if "does not match any node id" not in e]
if real_errors:
    print(f"[graphify] Extraction warning ({len(real_errors)} issues): {real_errors[0]}", file=sys.stderr)
G: nx.Graph = nx.DiGraph() if directed else nx.Graph()
for node in extraction.get("nodes", []):
    if "source_file" in node:
        node["source_file"] = _norm_source_file(node["source_file"])
    G.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
```

**All nodes are added to the graph regardless of validation errors.** The only consequence is a `stderr` warning message. There is no code path that drops, rejects, filters, or removes nodes based on `file_type` validation errors.

#### Step 3 — `assert_valid()` at `graphify/validate.py:67-72`
```python
def assert_valid(data: dict) -> None:
    """Raise ValueError with all errors if extraction is invalid."""
    errors = validate_extraction(data)
    if errors:
        msg = f"Extraction JSON has {len(errors)} error(s):\n" + "\n".join(f"  . {e}" for e in errors)
        raise ValueError(msg)
```
This function DOES raise on errors, but it is **never called in the build pipeline**. A search across all of `graphify/` confirms `assert_valid` is only called in `tests/test_validate.py:82-87`. It is not imported or used by `build.py`, `__main__.py`, or any production code.

#### Actual impact if BLOCKER 1 is not fixed

If Phase 2+ nodes are emitted without extending `VALID_FILE_TYPES`:
- Nodes are **NOT dropped, rejected, or filtered** from the graph.
- A `stderr` warning is printed for each extraction containing unrecognized `file_type` values.
- Nodes and edges are added to the graph normally via `G.add_node()` and `G.add_edge()`.
- The graph assembles successfully and contains the new nodes.

The synthesis characterization of "silently dropped" and "vanish during actual graph assembly" is incorrect. The impact is cosmetic (stderr noise) rather than functional (data loss).

---

## Claim 3: Phase 0 is missing from the runbook's sequential checklist (Section 11.3)

**Synthesis claim** (lines 67-77):
> Section 11.3 — which is the ordered checklist an implementer would actually follow bottom-up — starts at Phase 1. Phase 0 does not appear in the checklist at all.

### Verdict: **TRUE**

**Evidence** — Runbook Section 11.3, lines 2982-2999:
```
- [ ] Phase 1: Add `graphify/semantic_facts.py` and `tests/test_semantic_facts.py`.
- [ ] Run `uv run pytest tests/test_semantic_facts.py`.
- [ ] Phase 2: Add `graphify/deterministic_docs.py`, wire `extract_python()`, add doc-tag tests.
...
- [ ] Phase 9: Run full validation.
- [ ] Run `graphify update .` after code changes.
```

The sequential checklist begins at Phase 1. Phase 0 is absent despite the runbook's own Section 0.5 heading "Execute Before Phase 1" and the Phase 0 contents at runbook lines 91-176.

The synthesis is correct: an implementer working bottom-up from the checklist would start at Phase 1 and skip Phase 0 entirely.

---

## Claim 4: Are there other validation checks that would block new `file_type` values?

**Synthesis implication**: The `VALID_FILE_TYPES` set at `validate.py:4` is the sole gate blocking new file_type values.

### Verdict: **NO — no other validation blocks exist**

Full audit of validation checks in the `file_type` code path:

#### In `validate_extraction()` (`validate.py:10-64`):

| Check | Lines | Blocks new file_type? |
|---|---|---|
| `REQUIRED_NODE_FIELDS` — checks `id`, `label`, `file_type`, `source_file` exist | 30-32 | No — new nodes would carry all required fields |
| `VALID_FILE_TYPES` membership check | 33-37 | Yes — generates error (but does not reject node; see Claim 2) |
| Edge `VALID_CONFIDENCES` check | 54-58 | No — only applies to edges |
| Edge dangling reference check | 59-62 | No — only applies to edges |

#### In `build_from_json()` (`build.py:48-116`):

| Behavior | Lines | Blocks new file_type? |
|---|---|---|
| Legacy schema canonicalization (`source` → `source_file`) | 59-73 | No |
| Calls `validate_extraction()`, prints warnings | 75-79 | No — only prints stderr warning |
| Adds ALL nodes to graph unconditionally | 81-84 | No |
| Adds edges (skipping dangling refs) | 90-116 | No |

#### In `assert_valid()` (`validate.py:67-72`):

Raises `ValueError` on validation errors — **never called in production code**. Only used in `tests/test_validate.py`. Confirmed by `rg "assert_valid" graphify/` returning only the definition at `validate.py:67` (no callers inside `graphify/`).

#### In other production files:

- `graphify/build.py:119-153` (`build()`): Calls `build_from_json()` — same path, no additional filtering.
- `graphify/build.py:162-235` (`build_merge()`): Calls `build()` → `build_from_json()` — same path.
- `graphify/__main__.py`: No direct validation calls; extraction results flow to `build_merge()`.
- `graphify/watch.py:68-70`: Comment explicitly says they do NOT filter by `file_type`.

### Conclusion on Claim 4

The `VALID_FILE_TYPES` set membership check at `validate.py:33-37` is the **only** validation that interacts with `file_type` values. There are no secondary gates, no downstream filters, and no rejection logic anywhere in the build pipeline.

---

## Summary

| Claim | Verdict | Key Evidence |
|---|---|---|
| 1. `VALID_FILE_TYPES` at `validate.py:4` lacks new values | **TRUE** | `validate.py:4` confirmed — 6 values, no `doc_tag`/`code_index`/`code_index_symbol` |
| 2. New file_type values cause nodes to be dropped/rejected | **FALSE (overstated)** | `build.py:81-84` adds ALL nodes unconditionally. `assert_valid` never called in production. Only stderr warning is emitted. |
| 3. Phase 0 missing from Section 11.3 checklist | **TRUE** | Checklist at runbook:2982-2999 starts at Phase 1, omits Phase 0 |
| 4. Other validation checks block new file_type values | **FALSE** | `validate.py:33-37` is the only file_type gate; no secondary blocking exists |

### Recommendation

**Blocker 1 remains a necessary fix**, but its severity should be downgraded from "CRITICAL — data loss" to **"HIGH — stderr noise and schema inconsistency"**. The fix should still be applied before Phase 2, but an implementer who skips it will see warnings, not lost data.

**Blocker 2 is a valid documentation gap** — Phase 0 should be added to the Section 11.3 checklist as a prerequisite step. This is a genuine implementation risk if the implementer works exclusively from the checklist.
