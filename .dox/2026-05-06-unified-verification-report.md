# Unified Verification Report: Deterministic Semantic Extraction Runbook

**Date:** 2026-05-06
**Target:** `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md`
**Source Reports:** Fact-Checking (Agent 1), Architecture Review (Agent 2), Security Review (Agent 3), Debug & Testing (Agent 4), Coverage Assessment (Agent 5)

## 1. Executive Summary

The runbook under review is a planning artifact of unusual quality. Across five independent verification passes — fact-checking, architecture, security, testing, and coverage — the document emerges as honest, conservative, well-sourced, and structurally sound. Not a single fabricated claim was detected: all 13 external references are real, correctly named, accurately described, and correctly applied.

**However, the runbook is not implementation-ready.** Five independent reviews converge on a consistent picture: the plan is architecturally correct, but the code blocks contain defects that would cause silent failures, security gaps, and significant test coverage holes if implemented verbatim.

### What MUST Be Fixed (Critical — Block Implementation)

1. **`ast.get_docstring(node, clean=False)` is incompatible with Python 3.10–3.12.** The `clean` parameter was added in Python 3.13. The project requires `>=3.10`. Four call sites in `_iter_documented_python_objects()` at runbook lines 834, 841, 846, and 850 would cause `enrich_python_doc_tags()` to fail silently on all supported Python versions below 3.13. **Severity: CRITICAL.**

2. **`VALID_FILE_TYPES` not extended for `doc_tag`, `code_index`, `code_index_symbol`.** Every new node type emitted by Phases 2–5 will be rejected by the graph validator. Showstopper schema incompatibility. **Severity: HIGH.**

3. **`_clean_docstring()` contains dead code with AST injection risk.** Self-identified by the runbook at §3.5, the function remains in the code block. Remove it entirely before implementation. **Severity: MEDIUM.**

### What SHOULD Be Fixed (Significant — Impact Correctness or Robustness)

- SCIP JSON ingestion has five distinct security gaps
- Metadata dicts from all phases flow unsanitized into graph.json and HTML exports
- No integration test exists for the combined Phase 2+3+4+5 pipeline
- `deterministic_docs.py` receives a grade of D — 12 helper functions with ZERO unit tests
- 56% of new functions (20 of 36) have zero tests. Error-handling path coverage is 9%.
- `ast.parse()` is called without `sys.setrecursionlimit()` in new modules
- Exception swallowing masks genuine failures
- Nested class docstrings are not extracted

### Overall Verdict

The runbook requires **three mandatory corrections** before any implementation work begins. After those corrections, the runbook is implementation-ready for Phase 1 and Phase 6. Phases 2–5 require substantial test scaffolding before they can be considered production-grade.

## 2. Cross-Cutting Findings (Multi-Agent Consensus)

1. **`_clean_docstring()` Dead Code** — flagged by Agents 1, 2, and 3
2. **No Full-Pipeline Integration Test** — flagged by Agents 2, 4, and 5
3. **SCIP Ingestion Is JSON-Only** — noted by Agents 1, 2, and 3
4. **`deterministic_docs.py` Is the Weakest Module** — flagged by Agents 2 and 5

## 3. Critical Defects (Must Fix Before Implementation)

### 3.1 CRITICAL: `ast.get_docstring(node, clean=False)` — Python Version Incompatibility
- Location: `_iter_documented_python_objects()`, four call sites at runbook lines 834, 841, 846, 850
- Fix: Remove `clean=False` — it is the default behavior. Use `ast.get_docstring(tree)` etc.

### 3.2 HIGH: `VALID_FILE_TYPES` Not Extended
- Location: `graphify/validate.py`
- Fix: Add `"doc_tag"`, `"code_index"`, `"code_index_symbol"` to `VALID_FILE_TYPES`

### 3.3 MEDIUM: `_clean_docstring()` Dead Code
- Location: Runbook lines 585–590
- Fix: Delete the function from the runbook code block

## 4. Significant Gaps (Should Fix — 8 items)

See full report for details.

## 5. Minor Issues (Could Fix — 5 items)

See full report for details.

## 6. Debug Script Recommendations (7 scripts for /.audit/)

1. `check_doc_tag_parsing.py`
2. `check_node_id_compat.py`
3. `check_raw_call_parity.py`
4. `check_import_guided_resolution.py`
5. `check_test_linking.py`
6. `check_extraction_diff.py`
7. `check_confidence_rules.py`

## 7. Test Coverage Recommendations

Overall grade C+. Must-add 3 tests, should-add 6 tests. Full details in report.

## 8. Security Hardening Recommendations (7 items)

See full report for details.

## 9. Items Requiring Further Investigation (5 items)

See full report for details.

## 10. Final Verdict

**Not ready for verbatim implementation.** Three mandatory corrections required first. Once corrected, implementation-ready for Phase 1 and Phase 6. Phases 2–5 need test scaffolding.

---

*Synthesis completed 2026-05-06 from five independent verification reports.*