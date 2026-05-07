# Coverage Assessment Report
# Generated: 2026-05-06
# Agent: Senior QA Engineer and Coverage Analyst
# Target: .dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md

## (A) Per-File Coverage Assessment

| File | Grade | Key Gap |
|------|-------|---------|
| semantic_facts.py | B+ | 2 minor gaps |
| deterministic_docs.py | D | 12 helpers, ZERO unit tests. Weakest coverage. |
| symbol_resolution.py | C+ | Multiple internal helpers untested |
| test_linking.py | C- | 4 internal helpers untested |
| scip_ingest.py | C | All private helpers untested |
| extract.py mods | B | Only 1 regression test specified |
| cache.py mods | A | Small, well-scoped |

## (B) Missing Test Coverage

8 critical gaps where functions have ZERO tests:
- _parse_restructured_tags(), _parse_google_sections(), inspectable_docstring()
- _iter_documented_python_objects(), parse_python_import_aliases() (only alias form tested)
- _iter_test_function_calls(), _safe_symbol_id(), find_unique_python_symbol() (only ambiguous path)

## (C) Edge Case Gaps

- 5/6 error-handling code paths have zero test coverage
- Empty files: 4 scenarios untested
- Malformed inputs: 6 scenarios untested
- Nested scopes: 4 scenarios untested
- Large files: zero performance tests
- Encoding: zero non-UTF-8 tests

## (D) Regression Risk Assessment

- 11 existing tests assessed for breakage risk
- 1 HIGH risk: test_no_dangling_edges_on_extract() won't catch new edge types
- 4 MEDIUM risk tests
- Downstream consumers (cluster, analyze, report, export) not addressed

## (E) Coverage Recommendations

Must-add (3): deterministic_docs unit tests, symbol_resolution import tests, extract integration edge cases
Should-add (3): test_linking error paths, scip_ingest edge cases, new-relation dangling edge test
Process (3): full suite after each phase, confidence distribution smoke test, GRAPH_REPORT.md output validation

## Summary Statistics

- Total new functions/classes: 36
- Functions with ≥1 test: 16 (44%)
- Functions with ≥2 tests: 9 (25%)
- Functions with ZERO tests: 20 (56%)
- Error-handling paths: 11 proposed, 1 tested (9%)

## Overall Grade: C+

Minimally adequate for happy paths. Critically under-tests error handling,
individual parsing functions, edge cases, and downstream consumers.