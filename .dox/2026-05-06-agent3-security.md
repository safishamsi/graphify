# Security Review Report
# Generated: 2026-05-06
# Agent: Senior Application Security Engineer
# Target: .dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md

## (A) Security Risks in Proposed Code

### A.1 Dead-Code AST Injection in _clean_docstring()
Runbook lines 585-590. Self-identified as dead code but still in code block.
Recommend: Remove from runbook code block entirely.

### A.2 SCIP JSON Ingestion — Multiple Issues
(a) Unbounded JSON loading — no file size check before json.loads()
(b) Path traversal in source_file — untrusted relative_path from external JSON
(c) No length limits on symbols — _safe_symbol_id() has no cap
(d) No schema validation — type-checked but never validated
(e) ID collisions possible — two distinct symbols can produce same safe ID

### A.3 Unsanitized Metadata in Graph Outputs
Metadata dicts from all phases flow unsanitized into graph.json and HTML exports.
Existing sanitize_label() only handles the "label" field.

### A.4 ast.parse() Without Resource Limits
New modules don't call sys.setrecursionlimit(). Adversarial file could crash pipeline.

### A.5 Regex Patterns — Minor Concern
Simple patterns unlikely to cause catastrophic backtracking. Full file read before parsing.

### A.6 Exception Swallowing Masks Failures
Silent returns on OSError/SyntaxError are indistinguishable from empty results.

## (B) Missing Security Controls

1. VALID_FILE_TYPES not extended for doc_tag, code_index, code_index_symbol → ALL new nodes rejected by validator
2. No input size limits on new ingestion surfaces
3. No metadata sanitization pipeline
4. No file permission guidance for cache files
5. No source_file path validation in new modules
6. No trust boundary for SCIP data

## (C) Input Validation Gaps

12 gaps documented across all phases. Most critical:
- SCIP JSON: no file size check, no depth limit, no schema validation
- Metadata: raw docstring lines, import names stored verbatim
- Edge context: new context strings not validated
- Node file_type: three new values not in VALID_FILE_TYPES

## (D) Recommended Security Additions

7 specific recommendations:
1. Phase 0 security prerequisites (VALID_FILE_TYPES, metadata sanitization, file size guards, recursion limit, context validation)
2. Remove _clean_docstring() from runbook code block
3. Add input size/depth limits to SCIP ingestion
4. Validate SCIP relative_path against project root
5. Add sanitize_metadata() to security.py
6. Add VALID_CONTEXTS to validate.py
7. Document trust boundaries for external indexes

## Summary

Risk severity: 1 HIGH (VALID_FILE_TYPES incompatibility), 4 MEDIUM, 4 LOW.
Primary gaps: SCIP path missing validation, metadata unsanitized, showstopper VALID_FILE_TYPES defect.