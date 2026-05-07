# Agent2 Investigation: extract.py Phases 3-4 — Runbook vs Live Code

> Date: 2026-05-06
> Scope: Phase 3 (symbol index + raw-call resolution) and Phase 4 (import-guided call resolution)
> Runbook: `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md`
> Live code: `graphify/extract.py` (4792 lines)

---

## 1. Summary of Claims Audited

The runbook makes the following implementation claims for Phases 3 and 4:

| # | Claim | Verdict |
|---|-------|---------|
| A | `_resolve_cross_file_imports()` exists at ~line3620, with signature `(per_file, paths) -> list[dict]` | **MATCH** |
| B | `_resolve_cross_file_java_imports()` exists at ~line3765, same signature pattern | **MATCH** |
| C | `extract()` exists at ~line4546, orchestrates cross-file call resolution | **MATCH** |
| D | `py_paths`, `py_results`, `java_paths`, `java_results` are the variable names used | **MATCH** |
| E | `raw_calls` data structure uses keys `caller_nid`, `callee`, `is_member_call`, `source_file`, `source_location` | **MATCH** |
| F | The cross-file call resolution block is at lines 4670-4719 | **MATCH** |
| G | The insertion point for import-guided calls (before line 4670, after line 4668) is valid | **MATCH** |
| H | The raw_calls building logic at lines 1365-1377 works as the runbook assumes | **PARTIAL — see D1** |
| I | The runbook's `resolve_cross_file_raw_calls()` helper is a drop-in replacement for lines 4670-4719 | **FUNCTIONAL DISCREPANCY — see D2** |
| J | `paths` is the parameter name in `extract()` (needed by `resolve_python_import_guided_calls`) | **MATCH** |

---

## 2. Detailed Discrepancies

### D1: raw_calls building location is approximate (Minor)

**Runbook assumes:**
> `graphify/extract.py:1365-1377` builds `raw_calls` for unresolved calls in the generic extractor.

**Live code reality:**
Lines 1365-1377 in `_extract_generic()` contain the comment block and the `raw_calls` variable *initialization* (`raw_calls: list[dict] = []` at line 1377), plus the `label_to_nid` building. However, the actual `raw_calls.append()` calls happen much later inside the `walk_calls()` closure — at line 1531 for the main generic path, and at lines 3071, 3256, 3431, 3600, and 4227 for other language-specific extractors.

There is also a *second* `raw_calls` initialization at line 3581 inside the PowerShell extractor, which is a separate code path.

**Impact:** None. The runbook's description of the *data structure* of `raw_calls` entries is correct. Every `raw_calls.append()` site uses exactly these five keys:

```python
{
    "caller_nid": caller_nid,
    "callee": callee_name,
    "is_member_call": is_member_call,
    "source_file": str_path,
    "source_location": f"L{node.start_point[0] + 1}",
}
```

Confirmed at 6 of 6 `raw_calls.append` call sites (`graphify/extract.py:1531`, `:3071`, `:3256`, `:3431`, `:3600`, `:4227`).

---

### D2: Index filtering is stricter in runbook's `resolve_cross_file_raw_calls` than live code (SIGNIFICANT)

**Runbook assumes:**
The `resolve_cross_file_raw_calls()` helper in `graphify/symbol_resolution.py` builds its label index via `build_label_index(all_nodes)`, which calls `node_is_resolvable_symbol()`. This function excludes:

```python
_EXCLUDED_FILE_TYPES = {"rationale", "doc_tag"}

def node_is_resolvable_symbol(node):
    if node.get("file_type") in _EXCLUDED_FILE_TYPES:
        return False
    label = str(node.get("label", "")).strip()
    if not label:
        return False
    if label.endswith((".py", ".js", ".ts", ".tsx", ".java", ".go", ".rs")):
        return False
    return bool(normalise_callable_label(label))
```

**Live code reality (`extract.py:4676-4687`):**
The inline index build only excludes one thing:

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

**What the live code does NOT exclude:**
- Live code does NOT exclude `doc_tag` nodes (irrelevant today — `doc_tag` doesn't exist yet, but will after Phase 2).
- Live code does NOT exclude labels ending in `.py`, `.js`, `.ts`, `.tsx`, `.java`, `.go`, `.rs`. This means file-level nodes (e.g., node label `"my_module.py"`) are currently INCLUDED in the cross-file call resolution index. In practice, these are never matched because a raw call's `callee` value is always a function name like `"log"` or `"helper"`, not a filename. But the index does contain file-level entries.

**Impact for Phase 3:** If the runbook's `resolve_cross_file_raw_calls` replaces the inline block at lines 4670-4719, the resulting behavior is:
- **Stricter**: File-level nodes will be excluded from the index (a mild improvement — they should never have been resolvable targets anyway).
- **Forward-compatible**: `doc_tag` nodes (from Phase 2) will also be excluded, preventing false matches.
- **Regression risk near zero**: The `label.endswith()` check only affects labels that look like filenames, which should never be matched as call targets. The `doc_tag` exclusion is a no-op until Phase 2 is implemented.

**Verdict:** The runbook's stricter filtering is a safe behavioral change — arguably a bugfix — but it IS a divergence from current live-code behavior. This should be explicitly acknowledged in the implementation plan.

---

### D3: Runbook's `resolve_python_import_guided_calls` uses `paths` not `py_paths` (Cosmetic)

**Runbook code:**
```python
if py_paths:
    try:
        all_edges.extend(resolve_python_import_guided_calls(per_file, paths, all_nodes, all_edges))
```

**Observation:** The guard condition checks `py_paths` (Python-only paths), but passes `paths` (ALL paths) to the function. Inside `resolve_python_import_guided_calls`, the function filters by `path.suffix == ".py"` internally, so this is functionally correct. But conceptually, passing `py_paths` would be more direct.

**Impact:** None. The function works correctly either way. This is a minor readability issue in the runbook code, not a bug.

---

### D4: `resolve_cross_file_raw_calls` and `resolve_python_import_guided_calls` each call `existing_edge_pairs()` independently (Architectural note)

**Observation:** Both helpers call `existing_edge_pairs(all_edges)` to build their deduplication set. In the runbook's planned wiring:

1. `resolve_python_import_guided_calls` runs first, reads existing edges from `all_edges`, returns new edges.
2. Caller does `all_edges.extend(...)`.
3. `resolve_cross_file_raw_calls` runs second, reads from `all_edges` (now including import-guided edges), properly skips duplicates.

This works correctly because `existing_edge_pairs` is called AFTER Phase 4 edges are appended when Phase 3 runs. However, `existing_edge_pairs` is called redundantly — Phase 4 builds it once, Phase 3 builds it again. This is a performance note, not a correctness issue, given the modest edge counts involved.

---

## 3. Confirmed Matches (No Discrepancy)

### 3.1 Function signatures

| Function | Runbook claim | Live code (`extract.py:line`) | Match? |
|----------|--------------|-------------------------------|--------|
| `_resolve_cross_file_imports()` | `(per_file, paths) -> list[dict]` | `(per_file: list[dict], paths: list[Path]) -> list[dict]` at `:3620` | YES |
| `_resolve_cross_file_java_imports()` | `(per_file, paths) -> list[dict]` | `(per_file: list[dict], paths: list[Path]) -> list[dict]` at `:3765` | YES |
| `extract()` | orchestration function | `extract(paths: list[Path], cache_root: Path \| None = None, *, parallel: bool = True, max_workers: int \| None = None) -> dict` at `:4546` | YES |

### 3.2 Variable scope at insertion point

All four local variables the runbook references are in scope at the insertion point (line 4669-4670):

| Variable | Defined at | Exists? |
|----------|-----------|---------|
| `py_paths` | `:4650` | YES |
| `py_results` | `:4652` | YES |
| `java_paths` | `:4661` | YES |
| `java_results` | `:4663` | YES |
| `paths` | `:4547` (function parameter) | YES |
| `per_file` | `:4595` | YES |
| `all_nodes` | `:4622` | YES |
| `all_edges` | `:4625` | YES |

### 3.3 Insertion point validity

The runbook says to insert the import-guided call block "immediately before the comment `# Cross-file call resolution for all languages.`"

Live code structure at the insertion region:

```
:4659  # (blank line after Python cross-file import try/except block)
:4660  # Cross-file Java import resolution
:4661  java_paths = [...]
:4662  if java_paths:
:4663      java_results = [...]
:4664      try:
:4665          all_edges.extend(...)
:4666      except Exception as exc:
:4667          ...
:4668          logging.getLogger(...)
:4669  # (blank line)
:4670  # Cross-file call resolution for all languages
```

The insertion point between line 4668 and line 4669/4670 is **valid and unambiguous**. The runbook's code block would be inserted at line 4669 (after the Java block's try/except closes, before the raw-call comment).

### 3.4 Edge format consistency

The edges emitted by the runbook's helpers match the live code's edge format exactly:

- `resolve_cross_file_raw_calls` edges: 5 fields identical to live code (`source`, `target`, `relation`, `context`, `confidence`, `confidence_score`, `source_file`, `source_location`, `weight`)
- `resolve_python_import_guided_calls` edges: Same fields plus a `metadata` dict with resolver evidence

Both are compatible with `build_from_json()` at `graphify/build.py:48-116`.

### 3.5 Import guard pattern consistency

The runbook uses a lazy `import logging` pattern for exception guards:

```python
except Exception as exc:
    import logging
    logging.getLogger(__name__).warning(...)
```

This matches the existing pattern already used in the live code at lines 4657-4658 and 4667-4668.

---

## 4. Test Anchors

The existing test `test_cross_file_calls_skip_ambiguous_duplicate_labels` at `tests/test_extract.py:187-206` verifies that ambiguous duplicate labels are NOT resolved. This test must continue to pass after Phase 3/4 implementation.

The runbook's Phase 3 replacement preserves this behavior exactly (see `resolve_cross_file_raw_calls` lines 1346-1348: `if len(candidates) != 1: continue`).

---

## 5. Go/No-Go Assessment for Implementation

| Check | Status |
|-------|--------|
| All function signatures match runbook claims | GO |
| All variable names in scope at insertion point | GO |
| raw_calls data structure matches runbook assumptions | GO |
| Insertion point unambiguous | GO |
| Edge format compatible with `build_from_json()` | GO |
| Existing regression test covers ambiguous-call behavior | GO |
| `_EXCLUDED_FILE_TYPES` filtering is a safe behavioral change | GO (document as intentional) |
| Phase 4 ordering (import-guided before raw-call fallback) is correct | GO |

**Overall verdict: GO for implementation.** The two discrepancies found (D1: line-number imprecision, D2: stricter index filtering) are both non-blocking. D2 should be explicitly noted in the implementation as a deliberate improvement, not a silent side effect.

---

## 6. Recommended Implementation Order Within Phases 3-4

1. **Phase 3 first**: Extract `resolve_cross_file_raw_calls` into `graphify/symbol_resolution.py`. Wire into `extract()` by replacing lines 4670-4719. Run the regression test (`test_cross_file_calls_skip_ambiguous_duplicate_labels`). This validates the refactor without changing behavior (modulo the stricter filtering noted in D2).

2. **Phase 4 second**: Replace `graphify/symbol_resolution.py` with the expanded version containing `resolve_python_import_guided_calls`. Wire into `extract()` at the insertion point (line 4669). This adds new functionality on top of the validated refactor.

3. **Do NOT skip Phase 3 and go straight to Phase 4.** The runbook itself says Phase 4 replaces the entire Phase 3 file. But the Phase 3 refactoring step should be validated independently before adding import-guided logic, to isolate any regressions.
