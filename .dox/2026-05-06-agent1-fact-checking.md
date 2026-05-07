# Fact-Checking Verification Report
# Generated: 2026-05-06
# Agent: Senior Fact-Checking Research Analyst
# Target: .dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md

## (A) Verified Claims

All 13 external references in the runbook are real, correctly named, accurately described, and correctly applied:
- Tree-sitter: existing extraction engine, query packs deferred to future
- SCIP: active format, JSON-compatible subset explicitly labeled
- LSIF: legacy/deprecated, correctly noted
- SemanticDB: JVM-specific, deferred to future work
- Scope Graphs: real algorithm, correctly deferred
- Stack Graphs: real algorithm, archived Sep 2025, correctly deferred
- Code Property Graphs: real, correctly deferred
- Program Slicing (Weiser, Ferrante, Horwitz): real papers, deferred
- Python ast module: stdlib, correctly used
- Sphinx/reStructuredText: real format, correctly parsed
- Google/Numpy-style docstrings: real convention
- pytest tmp_path: real fixture
- Confidence model schema: correct values

## (B) Qualified Claims

1. SCIP naming slightly optimistic (file named scip_ingest.py but accepts JSON subset) — correctly qualified in text
2. _clean_docstring() dead code — self-identified by runbook at §3.5
3. Stack Graphs archival status not explicitly noted in §12.2 — minor omission
4. Scope Graph complexity correctly acknowledged

## (C) Unverifiable Claims

3 items (internal code anchors, graph statistics, predicted test outcomes) — none are external algorithm claims

## (D) Likely Fabricated Claims

**NONE FOUND.** Zero fabricated algorithms, papers, tools, or methods.

## Summary

The runbook is honest, conservative, and well-sourced. All simplifications are explicitly labeled.