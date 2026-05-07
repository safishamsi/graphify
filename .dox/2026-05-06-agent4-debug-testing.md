# Debug Scripts & Testing Report
# Generated: 2026-05-06
# Agent: Senior Python Developer and Testing Specialist
# Target: .dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md

## (A) Debug Scripts Needed (7 scripts for /.audit/)

1. check_doc_tag_parsing.py — validates regex parsers against curated fixtures (~80 lines)
2. check_node_id_compat.py — verifies tag node IDs match owner nodes from extractor (~100 lines)
3. check_raw_call_parity.py — diffs old vs new raw-call resolution for regressions (~120 lines)
4. check_import_guided_resolution.py — audits what import resolver resolves vs misses (~150 lines)
5. check_test_linking.py — reports test-to-code edges on repo's own tests (~130 lines)
6. check_extraction_diff.py — diffs extraction output before/after all phases (~160 lines)
7. check_confidence_rules.py — flags confidence hygiene violations (~70 lines)

## (B) Test Suite Gaps (8 gaps)

1. No full-pipeline integration test after all phases
2. No tests for interactions between new passes
3. No negative/error-path tests for parse_python_import_aliases()
4. No duplicate-prevention test between two resolvers
5. No regression tests for non-Python languages
6. No cache interaction tests for new node types
7. No edge-case tests for enrich_python_doc_tags()
8. No performance baseline test

## (C) Recommended Test Additions (5 tests)

1. test_symbol_resolution.py — 4 negative import tests
2. test_extract.py — full-pipeline integration test
3. test_extract.py — doc tag edge cases (no tags, class tags)
4. test_extract.py — cache round-trip for doc tag nodes
5. test_symbol_resolution.py — duplicate-prevention test

## (D) Existing Test Patterns to Follow (8 patterns)

File-per-module, tmp_path fixture, direct function import, integration extractor import,
structure validation, confidence assertions, helper functions, idempotence/edge coverage.

## Summary

Runbook test adequacy: Moderately specific. Per-phase tests are copy-paste-able but
don't test cross-phase interactions or downstream pipeline survival.