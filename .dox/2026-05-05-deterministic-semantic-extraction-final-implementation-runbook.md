# Final Diagnostics Implementation Runbook: Deterministic Semantic Extraction for Graphify

> Status: Planning artifact only. This document is stored under `.dox/` for private implementation planning and is not intended to be committed.
>
> Audience: Beginner implementer with Python experience who needs exact instructions, exact targets, and complete code blocks.
>
> Role perspective: Senior Principal Python Engineer converting verified research into an executable implementation plan.

---

## 0. Scope, Verification Rules, and Evidence Ledger

### 0.1 Objective

This runbook turns the deterministic semantic extraction research into a concrete implementation plan for the current Graphify codebase.

The goal is to make semantic extraction faster, more deterministic, and less dependent on LLM first-pass extraction by adding an algorithm-first layer that produces high-confidence code facts before any LLM enrichment.

The intended final extraction model is:

```text
source files
  -> current Tree-sitter structural extraction
  -> deterministic semantic fact extraction
  -> deterministic doc/comment tag extraction
  -> deterministic import/name/call resolution improvements
  -> optional external index ingestion
  -> existing build/dedup/cluster/export pipeline
  -> LLM enrichment only for unresolved or high-level semantic interpretation
```

### 0.2 Absolute Constraints For Implementers

- [ ] Do not replace the existing extraction pipeline wholesale.
- [ ] Do not remove existing `extract_python()`, `extract_js()`, or generic extraction behavior.
- [ ] Do not weaken existing tests that assert deterministic `EXTRACTED` confidence for structural edges.
- [ ] Do not make LLM calls part of deterministic code extraction.
- [ ] Do not allow ambiguous dynamic calls to become fake `EXTRACTED` edges.
- [ ] Do not let optional SCIP/LSIF/SemanticDB ingestion become a required dependency.
- [ ] Do not introduce mandatory non-stdlib dependencies unless they are already present in `pyproject.toml` or are guarded behind optional runtime imports.
- [ ] Do not change graph output schema incompatibly; emit normal Graphify node/edge dicts.
- [ ] Add tests before relying on new behavior.

### 0.3 Documents Cross-Referenced

The implementation plan is grounded in the following sources:

- Original research document: `.dox/2026-05-05-deterministic-semantic-extraction-research.md`
- Independent verification document: `.dox/2026-05-05-deterministic-semantic-extraction-verification.md`
- Live codebase files verified directly during this planning pass.

### 0.4 Live Code Evidence Ledger

The following live code anchors were re-verified and corrected against the current checkout:

- `graphify-out/GRAPH_REPORT.md:1-15` confirms graph freshness, node/edge scale, confidence distribution, and the requirement to run graph update after code changes.
- `graphify/extract.py:1-11` confirms the existing extractor is deterministic, Tree-sitter based, and imports the AST cache helpers.
- `graphify/extract.py:147` defines `LanguageConfig`, the current language-specific configuration seam.
- `graphify/extract.py:1017` begins `_extract_generic()`, including parser setup, local node/edge accumulators, and import handling.
- `graphify/extract.py:1089-1706` contains the generic extraction walker and final clean-edge return.
- `graphify/extract.py:1707` contains `_extract_python_rationale()`, the existing Python docstring/rationale post-pass.
- `graphify/extract.py:1810` contains `extract_python()`, currently calling `_extract_generic()` and `_extract_python_rationale()`.
- `graphify/extract.py:3620` contains `_resolve_cross_file_imports()`, Python-only cross-file import resolution.
- `graphify/extract.py:3765` contains `_resolve_cross_file_java_imports()`, Java cross-file import resolution.
- `graphify/extract.py:4546` contains `extract()`, the full AST extraction orchestration and cross-file call resolution.
- `graphify/build.py:48-116` contains `build_from_json()`, schema validation and graph construction.
- `graphify/build.py:119-153` contains `build()`, merge and dedup integration.
- `graphify/build.py:162-235` contains `build_merge()`, incremental graph merge and prune support.
- `graphify/cache.py:64-74` contains cache namespace creation for `ast` and `semantic` kinds.
- `graphify/cache.py:77-105` contains `load_cached()`.
- `graphify/cache.py:108-145` contains `save_cached()`.
- `graphify/cache.py:178-241` contains semantic cache helpers used by direct LLM extraction.
- `graphify/llm.py:86-99` contains the LLM semantic extraction output schema and confidence definitions.
- `graphify/llm.py:214-245` contains direct single-chunk LLM extraction.
- `graphify/llm.py:272-309` contains token-budget file chunking.
- `graphify/llm.py:312-386` contains adaptive retry on truncated LLM output.
- `graphify/llm.py:389-485` contains parallel corpus semantic extraction.
- `graphify/__main__.py:2000-2090` contains the `graphify extract` command and backend validation.
- `graphify/__main__.py:2106-2142` contains detect/incremental file classification.
- `graphify/__main__.py:2144-2160` runs AST extraction on code files.
- `graphify/__main__.py:2162-2210` runs LLM semantic extraction on docs/papers/images and semantic cache integration.
- `graphify/__main__.py:2215-2223` merges AST and semantic extraction outputs.
- `graphify/__main__.py:2267-2294` builds the final graph.
- `tests/test_extract.py:1-12` imports extractor functions and helpers for current extraction tests.
- `tests/test_extract.py:33-66` verifies Python extraction and multi-file merge behavior.
- `tests/test_extract.py:121-180` verifies current Python call edge behavior.
- `tests/test_extract.py:190-209` verifies ambiguous cross-file calls are skipped.
- `tests/test_cache.py:174-216` verifies semantic cache helpers.
- `tests/test_languages.py:44-240` verifies representative language extraction behavior and confidence/context expectations.

### 0.5 Phase 0 — Security and Schema Prerequisites (Execute Before Phase 1)

Before any implementation begins, these schema and security foundations should be in place. Skipping this phase does not make the graph builder drop the new nodes — `build_from_json()` still adds all nodes — but it does make the validator emit schema warnings for every new deterministic `file_type`, leaves new edge contexts undocumented, and leaves metadata sanitization unwired.

#### 0.5.1 Extend VALID_FILE_TYPES For New Node Categories

Target: `graphify/validate.py`, constant `VALID_FILE_TYPES` at `graphify/validate.py:4`.

The Problem: The runbook introduces three new `file_type` values — `"doc_tag"` (used by Phase 2 deterministic doc tag extraction), `"code_index"`, and `"code_index_symbol"` (used by Phase 6 SCIP ingestion). The graph validator at `validate_extraction()` in `graphify/validate.py:33-37` reports an error for any node whose `file_type` is not in `VALID_FILE_TYPES`. `build_from_json()` in `graphify/build.py:75-84` currently prints those validation errors as warnings and still adds every node to the graph, so this is not a node-loss failure. It is still a schema correctness problem: end-to-end graph assembly becomes noisy, `assert_valid()` would reject the extraction in strict validation contexts, and implementers cannot distinguish intentional deterministic node categories from genuinely invalid node types.

The Fix: In `graphify/validate.py`, replace line 4:

```python
# Before:
VALID_FILE_TYPES = {"code", "document", "paper", "image", "rationale", "concept"}

# After:
VALID_FILE_TYPES = {"code", "document", "paper", "image", "rationale", "concept",
                    "doc_tag", "code_index", "code_index_symbol"}
```

Rationale: The graph validator is a schema enforcement layer. Adding new node types to the validated set is the correct way to extend the schema. Without this, `build_from_json()` at `graphify/build.py:48-116` will still assemble the graph, but it will emit avoidable schema warnings for intentionally valid deterministic nodes and any strict use of `assert_valid()` will fail. Apply this before Phase 2 so validation output stays meaningful while new deterministic nodes are introduced.

#### 0.5.2 Add VALID_CONTEXTS For New Edge Context Strings

Target: `graphify/validate.py`, add a new documented vocabulary constant after `VALID_CONFIDENCES` at `graphify/validate.py:5`.

The Problem: The new phases introduce edge `context` strings — `"docstring_tag"` (Phase 2), `"import_guided_call"` (Phase 4), `"test_to_code_import_call"` (Phase 5), `"scip_index_occurrence"` (Phase 6) — that are not listed anywhere as a known vocabulary. The current validator does not enforce a context whitelist. Therefore, this step is a documentation and discoverability improvement, not an active validation gate. It gives later validation work one canonical set to use if context checking is added.

The Fix: Add below `VALID_CONFIDENCES`:

```python
VALID_CONTEXTS = {
    "import", "call", "reference", "field", "case",
    "import_guided_call", "docstring_tag", "test_to_code_import_call",
    "scip_index_occurrence", "scip_index_resolution",
}
```

Rationale: Edge context strings are part of the graph's semantic contract even though `validate_extraction()` does not currently validate them. Centralizing the vocabulary prevents spelling drift in new deterministic passes and makes any future context validation a small, explicit follow-up rather than a repo-wide search.

#### 0.5.3 Add Metadata Sanitization To Security Module

Target: `graphify/security.py`, new helper functions after the existing `sanitize_label()` definition.

The Problem: Every new phase stores user-controlled content in `metadata` dicts on nodes and edges — raw docstring lines, import names, SCIP symbol identifiers. The existing `sanitize_label()` only sanitizes the `label` field. Metadata values are written into `graph.json` and may later be embedded by HTML or web consumers, so metadata needs its own bounded, recursive sanitization path.

The Fix: Add to `graphify/security.py` after `sanitize_label()`:

```python
_METADATA_MAX_VALUE_LEN = 512
_METADATA_MAX_LIST_ITEMS = 50


def _sanitize_metadata_string(value: object) -> str:
    """Return a control-character-free, HTML-escaped, bounded string."""
    text = _CONTROL_CHAR_RE.sub("", str(value))
    text = html.escape(text, quote=True)
    if len(text) > _METADATA_MAX_VALUE_LEN:
        text = text[:_METADATA_MAX_VALUE_LEN]
    return text


def _sanitize_metadata_value(value: object) -> object:
    """Sanitize a metadata value while preserving simple JSON-compatible types."""
    if isinstance(value, str):
        return _sanitize_metadata_string(value)
    if isinstance(value, dict):
        return sanitize_metadata(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize_metadata_value(item) for item in value[:_METADATA_MAX_LIST_ITEMS]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _sanitize_metadata_string(value)


def sanitize_metadata(metadata: dict[object, object] | None) -> dict[str, object]:
    """Sanitize metadata keys and values before graph export.

    Metadata is less constrained than node labels: it can contain nested dicts,
    lists, source snippets, external index symbols, and docstring text. This
    helper keeps the data JSON-compatible, strips control characters, escapes
    HTML-sensitive characters in strings, caps long strings/lists, and drops
    entries whose key becomes empty after sanitization.
    """
    if metadata is None:
        return {}

    result: dict[str, object] = {}
    for key, value in metadata.items():
        clean_key = _sanitize_metadata_string(key)
        if not clean_key:
            continue
        result[clean_key] = _sanitize_metadata_value(value)
    return result
```

Call `sanitize_metadata()` inside `fact_to_edge()` (runbook Phase 1) and `make_fact_node()` (runbook Phase 1) before storing metadata on emitted dicts.

Rationale: Metadata is part of the exported graph. This helper makes metadata safer for JSON/HTML consumers without requiring every deterministic extraction phase to reimplement escaping, truncation, and recursive container handling.

#### 0.5.4 Phase 0 Validation Command

After completing Phase 0, verify with:

```bash
python -c "
from graphify.validate import VALID_FILE_TYPES, VALID_CONTEXTS
from graphify.security import sanitize_metadata
assert 'doc_tag' in VALID_FILE_TYPES
assert 'code_index' in VALID_FILE_TYPES
assert 'code_index_symbol' in VALID_FILE_TYPES
assert 'docstring_tag' in VALID_CONTEXTS
assert 'import_guided_call' in VALID_CONTEXTS
assert sanitize_metadata({'x': '<tag>\x00'}) == {'x': '&lt;tag&gt;'}
print('Phase 0: OK')
"
```

### 0.6 Correction From Research To Live Code

The research described broad architecture correctly, but live-code verification changes the implementation plan in several important ways:

- [ ] The first implementation should be modular. Do not attempt to rewrite `graphify/extract.py` wholesale because it is currently a large multi-language extractor with many regression tests.
- [ ] The safest first seam is to add new helper modules and call them from `extract_python()` and `extract()`.
- [ ] The cache already supports namespaced kinds; use a new deterministic namespace only if caching new deterministic facts separately becomes necessary.
- [ ] The CLI currently sends only documents/papers/images to direct LLM extraction; code files already go through AST extraction first. Therefore, the first win is improving AST-derived semantic facts, not changing LLM chunking immediately.
- [ ] Cross-file call resolution currently skips member calls and ambiguous duplicate labels. Preserve that conservative behavior.
- [ ] External index ingestion should remain optional and can be implemented as a separate phase after deterministic internal facts exist.

---

## 1. Implementation Phase Map

### Phase 0: Security Prerequisites and Schema Extension

- [ ] Extend `VALID_FILE_TYPES` with new deterministic node types (`doc_tag`, `code_index`, `code_index_symbol`).
- [ ] Document `VALID_CONTEXTS` as the canonical edge-context vocabulary for deterministic edges.
- [ ] Integrate `sanitize_metadata()` into all places where new code writes user-derived metadata or labels.

### Phase 1: Add a deterministic semantic fact model

- [ ] Create a neutral internal fact representation.
- [ ] Convert facts into existing Graphify nodes/edges.
- [ ] Keep the emitted graph schema compatible with `build_from_json()`.

### Phase 2: Add deterministic Python doc/comment tag extraction

- [ ] Extend the existing rationale/docstring behavior with structured tags.
- [ ] Support `Args:`, `Parameters:`, `Returns:`, `Raises:`, `Yields:`, and inline `# WHY:` style comments.
- [ ] Emit deterministic `documents`, `describes_parameter`, `returns`, and `raises` relations.
- [ ] Document that Phase 2 handles module, top-level function/class, and direct-method docstrings only; nested scopes are deferred.

### Phase 3: Add deterministic import/name-resolution helpers

- [ ] Add a reusable symbol index over existing extraction results.
- [ ] Resolve imported references when the candidate is unique.
- [ ] Preserve `AMBIGUOUS` metadata for unresolved candidate sets where useful.
- [ ] Derive the source-file suffix set from extractor support rather than hard-coding a short list.

### Phase 4: Add Python import-guided call resolution

- [ ] Resolve `from X import Y` call targets where evidence is unambiguous.
- [ ] Keep the resolver conservative; skip wildcard imports and member-call cases.
- [ ] Emit `calls` edges with `EXTRACTED` confidence only when import and call evidence agree.

### Phase 5: Add test-to-code linking

- [ ] Detect Python test files deterministically.
- [ ] Link test functions/classes to imported or same-module production symbols.
- [ ] Emit `tests` edges with `EXTRACTED` confidence when import evidence exists and `INFERRED` only for explicit naming heuristics.
- [ ] Use relation-aware de-duplication so that a `tests` edge is not suppressed by a prior `calls` edge for the same (source, target) pair.

### Phase 6: Add optional external index ingestion

- [ ] Add a minimal SCIP JSON ingestion module.
- [ ] Keep this optional and dependency-free.
- [ ] Use SCIP facts as additional extraction inputs, not as a replacement for Tree-sitter.

### Phase 7: Cache safety and deterministic extraction metadata

- [ ] Extend `_KNOWN_CACHE_KINDS` to cover new deterministic extraction namespaces.
- [ ] Keep current extraction caching behavior unchanged.
- [ ] Add deterministic-semantic cache keys only where a new extraction pass produces a distinct artifact.

### Phase 8: Add CLI integration policy

- [ ] Keep the current CLI unchanged by default.
- [ ] Add opt-in flags for deterministic semantic extraction behavior if defaults are risky.
- [ ] Prefer enabling safe deterministic features by default once tests are stable.

### Phase 9: Validation and graph update

- [ ] Run targeted tests.
- [ ] Run full tests.
- [ ] Run `graphify update .` after implementation changes.
- [ ] Add a targeted end-to-end validation test that exercises Phase 2 + Phase 3 + Phase 4 + Phase 5 in the same fixture.

### Phase 10: Implementation handoff checklist

- [ ] Confirm all completed prerequisite items from Phase 0.
- [ ] Confirm no tracked documentation leaks from `.dox/` or `.AUDIT/`.
- [ ] Confirm all changes pass `uv run pytest`.
- [ ] Confirm `git diff --check` is clean.

---

## 2. Phase 1 — Deterministic Semantic Fact Model

### 2.1 Target

Target: new file `graphify/semantic_facts.py`, module-level dataclasses and conversion helpers.

Relevant existing schema anchors:

- `graphify/build.py:48-116` expects extraction dicts with `nodes`, `edges`, and optional `hyperedges`.
- `graphify/llm.py:110-118` documents accepted confidence values in the semantic extraction schema, while `graphify/validate.py:5` contains the validator’s concrete `VALID_CONFIDENCES` set.
- `graphify/extract.py:1017` shows current extractors directly append node/edge dictionaries.

### 2.2 The Problem

The current extraction code emits nodes and edges directly while walking syntax trees. That works for structural extraction, but it makes richer deterministic semantic extraction harder because every new algorithm must immediately decide exactly which graph edge to emit.

A beginner-friendly way to understand the problem:

- A parser can see many raw facts: definitions, references, imports, calls, docstrings, comments, parameters, return annotations, and test names.
- Not every raw fact should immediately become a graph edge.
- Some facts must be resolved against other facts first.
- Some facts are exact and should become `EXTRACTED` edges.
- Some facts are ambiguous and should be recorded but not guessed.

Without an intermediate fact model, the implementation tends to become a pile of one-off code paths inside `graphify/extract.py`.

### 2.3 The Fix

Create a new helper module that defines stable, dependency-free semantic fact objects and conversion helpers. This file does not change existing behavior by itself. It gives later phases a safe place to put deterministic facts before they become graph edges.

Create `graphify/semantic_facts.py` with exactly this content:

```python
"""Deterministic semantic fact helpers for Graphify extraction.

This module intentionally has no Tree-sitter dependency. Tree-sitter-specific
extractors can create these facts, but the fact model itself is plain Python so
it is easy to unit test and safe to import from any extraction path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from graphify.security import sanitize_metadata


_VALID_CONFIDENCE = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}


@dataclass(frozen=True)
class SemanticFact:
    """A neutral deterministic fact discovered before graph edge emission.

    A fact is not necessarily a final graph edge. It is evidence. For example,
    a Python docstring section may produce a ``documents`` fact, while an import
    statement may produce an ``imports`` fact that later name resolution can use.
    """

    kind: str
    source: str
    target: str | None = None
    relation: str | None = None
    label: str | None = None
    source_file: str | None = None
    source_location: str | None = None
    confidence: str = "EXTRACTED"
    confidence_score: float | None = 1.0
    weight: float = 1.0
    context: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.confidence not in _VALID_CONFIDENCE:
            raise ValueError(
                f"Invalid confidence {self.confidence!r}; "
                f"expected one of {sorted(_VALID_CONFIDENCE)}"
            )
        if not self.kind:
            raise ValueError("SemanticFact.kind must be non-empty")
        if not self.source:
            raise ValueError("SemanticFact.source must be non-empty")


def fact_to_edge(fact: SemanticFact) -> dict[str, Any] | None:
    """Convert a relation fact into a Graphify edge dictionary.

    Returns ``None`` when the fact does not have both a target and a relation.
    This lets callers keep node-only facts in the same list without branching.
    """

    if not fact.target or not fact.relation:
        return None

    edge: dict[str, Any] = {
        "source": fact.source,
        "target": fact.target,
        "relation": fact.relation,
        "confidence": fact.confidence,
        "source_file": fact.source_file or "",
        "source_location": fact.source_location,
        "weight": fact.weight,
    }
    if fact.confidence_score is not None:
        edge["confidence_score"] = fact.confidence_score
    if fact.context:
        edge["context"] = fact.context
    if fact.metadata:
        edge["metadata"] = sanitize_metadata(fact.metadata)
    return edge


def facts_to_edges(facts: list[SemanticFact]) -> list[dict[str, Any]]:
    """Convert all edge-capable facts into Graphify edge dictionaries."""

    edges: list[dict[str, Any]] = []
    for fact in facts:
        edge = fact_to_edge(fact)
        if edge is not None:
            edges.append(edge)
    return edges


def make_fact_node(
    *,
    node_id: str,
    label: str,
    file_type: str,
    source_file: str,
    source_location: str | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a Graphify-compatible node dictionary for deterministic facts."""

    node: dict[str, Any] = {
        "id": node_id,
        "label": label,
        "file_type": file_type,
        "source_file": source_file,
        "source_location": source_location,
    }
    if metadata:
        node["metadata"] = sanitize_metadata(metadata)
    return node


def append_unique_node(
    nodes: list[dict[str, Any]],
    seen_ids: set[str],
    node: dict[str, Any],
) -> bool:
    """Append ``node`` only when its id has not already been emitted.

    Returns True when a node was added and False when it was skipped.
    """

    node_id = node.get("id")
    if not node_id:
        raise ValueError("node must contain a non-empty 'id'")
    if node_id in seen_ids:
        return False
    seen_ids.add(node_id)
    nodes.append(node)
    return True


def append_unique_edge(
    edges: list[dict[str, Any]],
    seen_edges: set[tuple[str, str, str, str | None]],
    edge: dict[str, Any],
) -> bool:
    """Append ``edge`` only when the semantic edge key has not appeared.

    The key includes source, target, relation, and source_location. Keeping the
    source location in the key allows two different call sites to remain visible
    when a future relation needs that detail, while still removing accidental
    duplicate emissions from the same fact.
    """

    source = edge.get("source")
    target = edge.get("target")
    relation = edge.get("relation")
    source_location = edge.get("source_location")
    if not source or not target or not relation:
        raise ValueError("edge must contain source, target, and relation")
    key = (source, target, relation, source_location)
    if key in seen_edges:
        return False
    seen_edges.add(key)
    edges.append(edge)
    return True
```

### 2.4 Rationale

This code fixes the planning/architecture problem without disrupting existing behavior.

The important properties are:

- It is pure Python and dependency-free.
- It respects existing confidence values from `graphify/llm.py:90-99`.
- It emits ordinary dicts compatible with `graphify/build.py:48-116`.
- It gives later algorithmic passes a shared vocabulary.
- It prevents each new deterministic method from inventing a separate data structure.
- It supports beginner-friendly tests because each helper can be tested without Tree-sitter.

### 2.5 Required Tests

Target: new file `tests/test_semantic_facts.py`, module-level tests.

The Problem: New helper modules need direct unit coverage so future implementers can safely use them without relying on large integration tests.

The Fix: Create `tests/test_semantic_facts.py` with exactly this content:

```python
"""Tests for graphify.semantic_facts."""
from __future__ import annotations

import pytest

from graphify.semantic_facts import (
    SemanticFact,
    append_unique_edge,
    append_unique_node,
    fact_to_edge,
    facts_to_edges,
    make_fact_node,
)


def test_semantic_fact_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError):
        SemanticFact(kind="call", source="a", target="b", relation="calls", confidence="CERTAIN")


def test_semantic_fact_requires_kind() -> None:
    with pytest.raises(ValueError):
        SemanticFact(kind="", source="a")


def test_semantic_fact_requires_source() -> None:
    with pytest.raises(ValueError):
        SemanticFact(kind="definition", source="")


def test_fact_to_edge_returns_none_without_target() -> None:
    fact = SemanticFact(kind="definition", source="module_a")
    assert fact_to_edge(fact) is None


def test_fact_to_edge_converts_relation_fact() -> None:
    fact = SemanticFact(
        kind="call",
        source="caller",
        target="callee",
        relation="calls",
        source_file="pkg/mod.py",
        source_location="L10",
        confidence="EXTRACTED",
        confidence_score=1.0,
        context="call",
        metadata={"resolver": "unit-test"},
    )
    edge = fact_to_edge(fact)
    assert edge == {
        "source": "caller",
        "target": "callee",
        "relation": "calls",
        "confidence": "EXTRACTED",
        "source_file": "pkg/mod.py",
        "source_location": "L10",
        "weight": 1.0,
        "confidence_score": 1.0,
        "context": "call",
        "metadata": {"resolver": "unit-test"},
    }


def test_facts_to_edges_skips_node_only_facts() -> None:
    facts = [
        SemanticFact(kind="definition", source="a"),
        SemanticFact(kind="call", source="a", target="b", relation="calls"),
    ]
    assert facts_to_edges(facts) == [
        {
            "source": "a",
            "target": "b",
            "relation": "calls",
            "confidence": "EXTRACTED",
            "source_file": "",
            "source_location": None,
            "weight": 1.0,
            "confidence_score": 1.0,
        }
    ]


def test_make_fact_node_builds_graphify_node() -> None:
    node = make_fact_node(
        node_id="pkg_mod_doc_param_name",
        label="name",
        file_type="doc_tag",
        source_file="pkg/mod.py",
        source_location="L5",
        metadata={"tag": "param"},
    )
    assert node == {
        "id": "pkg_mod_doc_param_name",
        "label": "name",
        "file_type": "doc_tag",
        "source_file": "pkg/mod.py",
        "source_location": "L5",
        "metadata": {"tag": "param"},
    }


def test_append_unique_node_adds_once() -> None:
    nodes: list[dict] = []
    seen: set[str] = set()
    node = {"id": "n1", "label": "N1"}
    assert append_unique_node(nodes, seen, node) is True
    assert append_unique_node(nodes, seen, node) is False
    assert nodes == [node]


def test_append_unique_node_rejects_missing_id() -> None:
    with pytest.raises(ValueError):
        append_unique_node([], set(), {"label": "missing"})


def test_append_unique_edge_adds_once_per_location() -> None:
    edges: list[dict] = []
    seen: set[tuple[str, str, str, str | None]] = set()
    edge_l1 = {"source": "a", "target": "b", "relation": "calls", "source_location": "L1"}
    edge_l2 = {"source": "a", "target": "b", "relation": "calls", "source_location": "L2"}
    assert append_unique_edge(edges, seen, edge_l1) is True
    assert append_unique_edge(edges, seen, edge_l1) is False
    assert append_unique_edge(edges, seen, edge_l2) is True
    assert edges == [edge_l1, edge_l2]


def test_append_unique_edge_rejects_incomplete_edge() -> None:
    with pytest.raises(ValueError):
        append_unique_edge([], set(), {"source": "a", "relation": "calls"})
```

### 2.6 Validation Command

Run:

```bash
uv run pytest tests/test_semantic_facts.py
```

Expected result:

```text
11 passed
```

---

## 3. Phase 2 — Deterministic Python Docstring and Comment Tag Extraction

### 3.1 Target

Target: new file `graphify/deterministic_docs.py`, module-level parsing helpers and `enrich_python_doc_tags()`.

Target: `graphify/extract.py`, function `extract_python()`.

Current verified anchors:

- `graphify/extract.py:1707` already extracts Python docstrings and rationale comments into `rationale` nodes.
- `graphify/extract.py:1810` currently calls `_extract_python_rationale()` from `extract_python()`.
- `graphify/extract.py:1314-1333` shows how top-level function and method node IDs are generated.
- `graphify/build.py:48-116` accepts additional node and edge dictionaries as long as endpoints are valid.

### 3.2 The Problem

Python docstrings often contain deterministic semantic information that does not require an LLM:

- Function parameters.
- Return values.
- Raised exceptions.
- Yielded values.
- Structured rationale.
- Sphinx/reStructuredText tags such as `:param name:` and `:returns:`.
- Google-style sections such as `Args:`, `Returns:`, and `Raises:`.

The current `_extract_python_rationale()` path extracts docstrings as broad rationale nodes, but it does not split structured docstring content into machine-readable semantic facts.

This means Graphify may send obvious documentation semantics to later LLM extraction or miss them entirely. That is slower, less deterministic, and less explainable.

### 3.3 The Fix

Add a deterministic Python doc tag module. It uses the Python standard library `ast` module, not an LLM and not a new dependency.

Create `graphify/deterministic_docs.py` with exactly this content:

```python
"""Deterministic documentation extraction helpers.

The first supported language is Python because Python's standard ``ast`` module
can recover docstrings without adding a new dependency. The helpers in this file
turn structured docstring sections into Graphify-compatible nodes and edges.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from graphify.semantic_facts import append_unique_edge, append_unique_node, make_fact_node


MakeId = Callable[..., str]
FileStem = Callable[[Path], str]


@dataclass(frozen=True)
class DocTag:
    """A structured documentation item extracted from a docstring."""

    kind: str
    name: str
    description: str
    line: int
    raw: str


def _normalise_space(text: str) -> str:
    """Collapse repeated whitespace while preserving readable text."""

    return re.sub(r"\s+", " ", text.strip())




def _docstring_start_line(node: ast.AST) -> int:
    """Return the source line where the docstring literal starts."""

    body = getattr(node, "body", [])
    if body and isinstance(body[0], ast.Expr):
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return getattr(body[0], "lineno", getattr(node, "lineno", 1))
    return getattr(node, "lineno", 1)


def _parse_restructured_tags(lines: list[str], base_line: int) -> list[DocTag]:
    """Parse Sphinx/reStructuredText-style docstring fields.

    Supported examples:
        :param path: file path to inspect
        :type path: pathlib.Path
        :returns: extracted graph fragment
        :rtype: dict
        :raises ValueError: when the input is invalid
    """

    tags: list[DocTag] = []
    pending_params: dict[str, tuple[str, int, str]] = {}
    param_types: dict[str, str] = {}
    pending_return: tuple[str, int, str] | None = None
    return_type = ""

    param_re = re.compile(r"^:param\s+(?P<name>[A-Za-z_][\w]*)\s*:\s*(?P<desc>.*)$")
    type_re = re.compile(r"^:type\s+(?P<name>[A-Za-z_][\w]*)\s*:\s*(?P<desc>.*)$")
    returns_re = re.compile(r"^:(returns?|return)\s*:\s*(?P<desc>.*)$")
    rtype_re = re.compile(r"^:rtype\s*:\s*(?P<desc>.*)$")
    raises_re = re.compile(r"^:raises?\s+(?P<name>[A-Za-z_][\w.]*)\s*:\s*(?P<desc>.*)$")

    for offset, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        type_match = type_re.match(line)
        if type_match:
            param_types[type_match.group("name")] = _normalise_space(type_match.group("desc"))
            continue
        rtype_match = rtype_re.match(line)
        if rtype_match:
            return_type = _normalise_space(rtype_match.group("desc"))
            continue
        param_match = param_re.match(line)
        if param_match:
            pending_params[param_match.group("name")] = (
                _normalise_space(param_match.group("desc")),
                base_line + offset,
                raw_line,
            )
            continue
        returns_match = returns_re.match(line)
        if returns_match:
            pending_return = (_normalise_space(returns_match.group("desc")), base_line + offset, raw_line)
            continue
        raises_match = raises_re.match(line)
        if raises_match:
            tags.append(
                DocTag(
                    "raises",
                    raises_match.group("name"),
                    _normalise_space(raises_match.group("desc")),
                    base_line + offset,
                    raw_line,
                )
            )

    for name, (description, line_number, raw_line) in pending_params.items():
        type_text = param_types.get(name)
        if type_text:
            description = f"{description} Type: {type_text}".strip()
        tags.append(DocTag("param", name, description, line_number, raw_line))

    if pending_return is not None:
        description, line_number, raw_line = pending_return
        if return_type:
            description = f"{description} Type: {return_type}".strip()
        tags.append(DocTag("returns", "return", description, line_number, raw_line))

    return tags


def _is_google_section_header(line: str) -> str | None:
    """Return a normalized section name for Google/Numpy-style headers."""

    stripped = line.strip().rstrip(":").lower()
    aliases = {
        "args": "param",
        "arguments": "param",
        "parameters": "param",
        "params": "param",
        "returns": "returns",
        "return": "returns",
        "raises": "raises",
        "raise": "raises",
        "yields": "yields",
        "yield": "yields",
    }
    return aliases.get(stripped)


def _parse_google_item(section_kind: str, text: str, line_number: int) -> DocTag | None:
    """Parse one item from a Google/Numpy-style docstring section."""

    cleaned = _normalise_space(text)
    if not cleaned:
        return None

    if section_kind == "param":
        match = re.match(
            r"^(?P<name>[A-Za-z_][\w]*)(?:\s*\((?P<type>[^)]*)\))?\s*:\s*(?P<desc>.*)$",
            cleaned,
        )
        if match:
            name = match.group("name")
            desc = match.group("desc")
            type_text = match.group("type")
            if type_text:
                desc = f"{desc} Type: {type_text}".strip()
            return DocTag("param", name, desc, line_number, text)
        simple = re.match(r"^(?P<name>[A-Za-z_][\w]*)\s+-\s+(?P<desc>.*)$", cleaned)
        if simple:
            return DocTag("param", simple.group("name"), simple.group("desc"), line_number, text)
        return None

    if section_kind in {"returns", "yields"}:
        match = re.match(r"^(?P<type>[^:]+)\s*:\s*(?P<desc>.*)$", cleaned)
        if match:
            desc = f"{match.group('desc')} Type: {match.group('type').strip()}".strip()
            return DocTag(section_kind, section_kind[:-1] if section_kind.endswith("s") else section_kind, desc, line_number, text)
        return DocTag(section_kind, section_kind[:-1] if section_kind.endswith("s") else section_kind, cleaned, line_number, text)

    if section_kind == "raises":
        match = re.match(r"^(?P<name>[A-Za-z_][\w.]*)\s*:\s*(?P<desc>.*)$", cleaned)
        if match:
            return DocTag("raises", match.group("name"), match.group("desc"), line_number, text)
        simple = re.match(r"^(?P<name>[A-Za-z_][\w.]*)\s+-\s+(?P<desc>.*)$", cleaned)
        if simple:
            return DocTag("raises", simple.group("name"), simple.group("desc"), line_number, text)
        return DocTag("raises", cleaned.split()[0], cleaned, line_number, text)

    return None


def _parse_google_sections(lines: list[str], base_line: int) -> list[DocTag]:
    """Parse Google/Numpy-style docstring sections."""

    tags: list[DocTag] = []
    active_kind: str | None = None
    active_items: list[tuple[str, int]] = []

    def flush_items() -> None:
        nonlocal active_items
        if active_kind is None:
            active_items = []
            return
        for text, line_number in active_items:
            item = _parse_google_item(active_kind, text, line_number)
            if item is not None:
                tags.append(item)
        active_items = []

    for offset, raw_line in enumerate(lines):
        current_line_number = base_line + offset
        stripped = raw_line.strip()
        section = _is_google_section_header(stripped)
        if section is not None:
            flush_items()
            active_kind = section
            continue
        if active_kind is None:
            continue
        if not stripped:
            continue
        if raw_line.startswith((" ", "\t")) or active_kind in {"returns", "yields", "raises"}:
            if active_items and raw_line.startswith(("    ", "\t")) and not re.match(r"^\s*[A-Za-z_][\w.]*\s*(\([^)]*\))?\s*[:\-]", raw_line):
                previous_text, previous_line = active_items[-1]
                active_items[-1] = (f"{previous_text} {stripped}", previous_line)
            else:
                active_items.append((stripped, current_line_number))

    flush_items()
    return tags


def parse_doc_tags(docstring: str | None, base_line: int) -> list[DocTag]:
    """Parse supported structured docstring tags.

    The parser intentionally returns only deterministic structured items. Free
    prose remains handled by the existing rationale/docstring extraction path.
    """

    cleaned = inspectable_docstring(docstring)
    if not cleaned:
        return []
    lines = cleaned.splitlines()
    tags = _parse_restructured_tags(lines, base_line)
    tags.extend(_parse_google_sections(lines, base_line))

    unique: dict[tuple[str, str, int], DocTag] = {}
    for tag in tags:
        unique[(tag.kind, tag.name, tag.line)] = tag
    return list(unique.values())


def inspectable_docstring(docstring: str | None) -> str:
    """Normalize a raw docstring into text suitable for line-based parsing."""

    if not docstring:
        return ""
    lines = docstring.expandtabs().splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""
    indentation = min((len(line) - len(line.lstrip())) for line in lines[1:] if line.strip()) if len(lines) > 1 else 0
    normalized = [lines[0].strip()]
    for line in lines[1:]:
        normalized.append(line[indentation:].rstrip() if indentation else line.rstrip())
    return "\n".join(normalized)


def _iter_documented_python_objects(
    tree: ast.Module,
    path: Path,
    make_id: MakeId,
    file_stem: FileStem,
) -> Iterable[tuple[str, str, str, int]]:
    """Yield ``(owner_node_id, owner_kind, docstring, doc_line)`` tuples.

    The node IDs mirror the existing IDs emitted by ``graphify.extract``:
    module file node, top-level functions, classes, and class methods.
    """

    stem = file_stem(path)
    file_nid = make_id(str(path))
    module_doc = ast.get_docstring(tree)
    if module_doc:
        yield file_nid, "module", module_doc, _docstring_start_line(tree)

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_nid = make_id(stem, node.name)
            class_doc = ast.get_docstring(node)
            if class_doc:
                yield class_nid, "class", class_doc, _docstring_start_line(node)
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_doc = ast.get_docstring(child)
                    if method_doc:
                        yield make_id(class_nid, child.name), "method", method_doc, _docstring_start_line(child)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_doc = ast.get_docstring(node)
            if function_doc:
                yield make_id(stem, node.name), "function", function_doc, _docstring_start_line(node)


def _tag_label(tag: DocTag) -> str:
    """Return a compact human-readable label for a doc tag node."""

    description = _normalise_space(tag.description)
    if description:
        return f"{tag.kind} {tag.name}: {description}"[:160]
    return f"{tag.kind} {tag.name}"[:160]


def _tag_relation(tag: DocTag) -> str:
    """Return the specific owner-to-tag relation for a doc tag."""

    if tag.kind == "param":
        return "documents_parameter"
    if tag.kind == "returns":
        return "documents_return"
    if tag.kind == "yields":
        return "documents_yield"
    if tag.kind == "raises":
        return "documents_exception"
    return "documents"


def enrich_python_doc_tags(
    path: Path,
    result: dict[str, Any],
    *,
    make_id: MakeId,
    file_stem: FileStem,
) -> None:
    """Append deterministic Python doc-tag nodes and edges to an extraction result.

    This function mutates ``result`` in-place, matching the existing style used by
    ``_extract_python_rationale`` in ``graphify.extract``.
    """

    try:
        source_text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return

    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return

    nodes = result.setdefault("nodes", [])
    edges = result.setdefault("edges", [])
    existing_ids = {node.get("id", "") for node in nodes}
    existing_edges: set[tuple[str, str, str, str | None]] = {
        (
            edge.get("source", ""),
            edge.get("target", ""),
            edge.get("relation", ""),
            edge.get("source_location"),
        )
        for edge in edges
    }
    source_file = str(path)

    for owner_nid, owner_kind, docstring, doc_line in _iter_documented_python_objects(tree, path, make_id, file_stem):
        if owner_nid not in existing_ids:
            continue
        tags = parse_doc_tags(docstring, doc_line)
        for index, tag in enumerate(tags, start=1):
            tag_id = make_id(owner_nid, "doc", tag.kind, tag.name, str(tag.line), str(index))
            tag_node = make_fact_node(
                node_id=tag_id,
                label=_tag_label(tag),
                file_type="doc_tag",
                source_file=source_file,
                source_location=f"L{tag.line}",
                metadata={
                    "doc_kind": tag.kind,
                    "doc_name": tag.name,
                    "doc_description": tag.description,
                    "owner_kind": owner_kind,
                    "owner_id": owner_nid,
                    "raw": tag.raw,
                },
            )
            append_unique_node(nodes, existing_ids, tag_node)

            append_unique_edge(
                edges,
                existing_edges,
                {
                    "source": tag_id,
                    "target": owner_nid,
                    "relation": "documents",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": source_file,
                    "source_location": f"L{tag.line}",
                    "weight": 1.0,
                    "context": "docstring_tag",
                },
            )
            append_unique_edge(
                edges,
                existing_edges,
                {
                    "source": owner_nid,
                    "target": tag_id,
                    "relation": _tag_relation(tag),
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": source_file,
                    "source_location": f"L{tag.line}",
                    "weight": 1.0,
                    "context": "docstring_tag",
                },
            )
```

### 3.4 Correction Already Applied To The Code Above

Target: `graphify/deterministic_docs.py`, function `_parse_restructured_tags()`.

The Problem: reStructuredText commonly writes `:param name:` before `:type name:`. The copy-paste code above now stores parameter descriptions until the full docstring has been scanned, so later `:type name:` lines are still merged into the final doc tag.

The Fix: No additional implementation step is needed; the `_parse_restructured_tags()` code block in this runbook already includes the corrected pending-parameter merge behavior.

Rationale: This keeps the runbook copy-paste block internally consistent with the required test `test_python_doc_tags_extract_restructured_text_sections()`.

### 3.5 Pre-Removed Dead Code

Target: `graphify/deterministic_docs.py`, function `_clean_docstring()` (pre-removed from the code block above).

The Problem: The helper `_clean_docstring()` originally appeared in an earlier draft of this runbook. It called `ast.parse()` on arbitrary docstring content wrapped in triple-quotes, creating an unnecessary AST injection surface. It was never called by the rest of the module — the active parser path uses `inspectable_docstring()`, which is safer for line-based parsing. As of this revision, the function has been deleted from the code block above. No action is needed.

Rationale: Removing unused code with `ast.parse()` eliminates dead attack surface and reduces module size.

### 3.6 Wire The Doc Tag Extractor Into Python Extraction

Target: `graphify/extract.py`, imports near `graphify/extract.py:1-11`.

The Problem: The new module does nothing until `extract_python()` calls it.

The Fix: Add this import below the existing cache import at `graphify/extract.py:11`:

```python
from .deterministic_docs import enrich_python_doc_tags
```

Target: `graphify/extract.py`, function `extract_python()` at `graphify/extract.py:1810`.

The Problem: `extract_python()` currently calls `_extract_python_rationale()` only. It must also call the deterministic doc tag enrichment pass after base extraction succeeds.

The Fix: Replace the entire `extract_python()` function with this exact function:

```python
def extract_python(path: Path) -> dict:
    """Extract classes, functions, imports, rationale, and doc tags from a Python file."""
    result = _extract_generic(path, _PYTHON_CONFIG)
    if "error" not in result:
        _extract_python_rationale(path, result)
        enrich_python_doc_tags(path, result, make_id=_make_id, file_stem=_file_stem)
    return result
```

### 3.7 Rationale

This phase is a direct implementation of the algorithm-first principle:

- Python docstrings are parsed locally with `ast`.
- Structured doc tags become deterministic `EXTRACTED` facts.
- The existing broad rationale extraction remains intact.
- No LLM is required for obvious `param`, `return`, and `raise` semantics.
- Node IDs are generated using the same `_make_id()` and `_file_stem()` logic as the current extractor.
- The implementation mutates the extraction result in the same style as `_extract_python_rationale()` at `graphify/extract.py:1707`.

### 3.8 Required Tests

Target: `tests/test_extract.py`, append new tests after the Python extraction tests around `tests/test_extract.py:33-66` or near the existing call-edge tests at `tests/test_extract.py:121-180`.

The Problem: Without tests, doc tag extraction could silently drift, create dangling edges, or emit non-deterministic labels.

The Fix: Add these test functions exactly:

```python
def test_python_doc_tags_extract_google_style_sections(tmp_path):
    src = tmp_path / "docsample.py"
    src.write_text(
        'def transform(value, strict=False):\n'
        '    """Transform a value.\n'
        '\n'
        '    Args:\n'
        '        value (str): Input value to transform.\n'
        '        strict (bool): Whether invalid input should raise.\n'
        '\n'
        '    Returns:\n'
        '        str: The transformed value.\n'
        '\n'
        '    Raises:\n'
        '        ValueError: If strict mode rejects the input.\n'
        '    """\n'
        '    if strict and not value:\n'
        '        raise ValueError("empty")\n'
        '    return value.upper()\n',
        encoding="utf-8",
    )

    result = extract_python(src)
    doc_nodes = [node for node in result["nodes"] if node.get("file_type") == "doc_tag"]
    doc_edges = [edge for edge in result["edges"] if edge.get("context") == "docstring_tag"]

    labels = {node["label"] for node in doc_nodes}
    relations = {edge["relation"] for edge in doc_edges}
    node_ids = {node["id"] for node in result["nodes"]}

    assert any("param value" in label for label in labels)
    assert any("param strict" in label for label in labels)
    assert any("returns return" in label for label in labels)
    assert any("raises ValueError" in label for label in labels)
    assert "documents" in relations
    assert "documents_parameter" in relations
    assert "documents_return" in relations
    assert "documents_exception" in relations
    for edge in doc_edges:
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids
        assert edge["confidence"] == "EXTRACTED"
        assert edge["confidence_score"] == 1.0


def test_python_doc_tags_extract_restructured_text_sections(tmp_path):
    src = tmp_path / "redoc.py"
    src.write_text(
        'def load(path):\n'
        '    """Load a file.\n'
        '\n'
        '    :param path: File path to read.\n'
        '    :type path: pathlib.Path\n'
        '    :returns: Parsed content.\n'
        '    :rtype: dict\n'
        '    :raises OSError: If the file cannot be read.\n'
        '    """\n'
        '    return {}\n',
        encoding="utf-8",
    )

    result = extract_python(src)
    doc_nodes = [node for node in result["nodes"] if node.get("file_type") == "doc_tag"]
    labels = {node["label"] for node in doc_nodes}

    assert any("param path" in label and "pathlib.Path" in label for label in labels)
    assert any("returns return" in label and "dict" in label for label in labels)
    assert any("raises OSError" in label for label in labels)


def test_python_doc_tags_do_not_replace_existing_rationale_nodes(tmp_path):
    src = tmp_path / "both.py"
    src.write_text(
        'def explain(name):\n'
        '    """Explain the name.\n'
        '\n'
        '    Args:\n'
        '        name: Name to explain.\n'
        '    """\n'
        '    return name\n',
        encoding="utf-8",
    )

    result = extract_python(src)
    file_types = {node.get("file_type") for node in result["nodes"]}
    assert "rationale" in file_types
    assert "doc_tag" in file_types
```

### 3.9 Validation Command

Run:

```bash
uv run pytest tests/test_semantic_facts.py tests/test_extract.py
```

Expected result:

```text
all selected tests pass
```

---

## 4. Phase 3 — Symbol Index and Cross-File Raw Call Resolver Extraction

### 4.1 Target

Target: new file `graphify/symbol_resolution.py`, module-level helper functions.

Target: `graphify/extract.py`, function `extract()` at the cross-file call block `graphify/extract.py:4670-4719`.

Current verified anchors:

- `graphify/extract.py:1365-1377` builds `raw_calls` for unresolved calls in the generic extractor.
- `graphify/extract.py:4670-4719` resolves raw calls after all files are extracted.
- `tests/test_extract.py:190-209` verifies ambiguous duplicate cross-file call labels are skipped.

### 4.2 The Problem

The current cross-file raw call resolver is embedded inside `extract()`. That makes it harder to test in isolation and harder to extend with future algorithmic name-resolution features.

The current behavior is important and must be preserved:

- Skip member calls such as `obj.log()` when receiver type is unknown.
- Skip ambiguous names where multiple nodes have the same label.
- Emit only when there is exactly one candidate.
- Mark these edges as `INFERRED`, not `EXTRACTED`, because a raw unqualified call across files lacks direct import evidence.

The implementation should first extract this logic into a reusable module without changing behavior. Later phases can improve the resolver with import evidence and scope facts.

### 4.3 The Fix

Create `graphify/symbol_resolution.py` with exactly this content:

```python
"""Deterministic symbol indexing and conservative cross-file resolution helpers."""
from __future__ import annotations

from typing import Any


_EXCLUDED_FILE_TYPES = {"rationale", "doc_tag"}


def normalise_callable_label(label: str) -> str:
    """Normalize a node label into the key used for call resolution."""

    return label.strip().strip("()").lstrip(".").lower()


def node_is_resolvable_symbol(node: dict[str, Any]) -> bool:
    """Return True when a node is suitable for deterministic symbol lookup."""

    if node.get("file_type") in _EXCLUDED_FILE_TYPES:
        return False
    label = str(node.get("label", "")).strip()
    if not label:
        return False
    if label.endswith((".py", ".js", ".ts", ".tsx", ".java", ".go", ".rs")):
        return False
    return bool(normalise_callable_label(label))


def build_label_index(nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Build label -> node id list for conservative cross-file resolution."""

    index: dict[str, list[str]] = {}
    for node in nodes:
        if not node_is_resolvable_symbol(node):
            continue
        node_id = node.get("id")
        if not node_id:
            continue
        key = normalise_callable_label(str(node.get("label", "")))
        if not key:
            continue
        index.setdefault(key, []).append(str(node_id))
    return index


def existing_edge_pairs(edges: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """Return all existing source/target edge pairs."""

    pairs: set[tuple[str, str]] = set()
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source and target:
            pairs.add((str(source), str(target)))
    return pairs


def iter_raw_calls(per_file: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    """Return raw calls from all per-file extraction fragments."""

    calls: list[dict[str, Any]] = []
    for result in per_file:
        if not result:
            continue
        calls.extend(result.get("raw_calls", []))
    return calls


def resolve_cross_file_raw_calls(
    per_file: list[dict[str, Any] | None],
    all_nodes: list[dict[str, Any]],
    all_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve unqualified raw calls conservatively after all files are known.

    This intentionally preserves Graphify's existing behavior:
    - member calls are skipped;
    - ambiguous labels are skipped;
    - only a single unique candidate is emitted;
    - emitted edges are INFERRED because the raw call alone is not import proof.
    """

    label_index = build_label_index(all_nodes)
    known_pairs = existing_edge_pairs(all_edges)
    resolved: list[dict[str, Any]] = []

    for raw_call in iter_raw_calls(per_file):
        callee = str(raw_call.get("callee", "")).strip()
        if not callee:
            continue
        if raw_call.get("is_member_call"):
            continue
        candidates = label_index.get(callee.lower(), [])
        if len(candidates) != 1:
            continue
        target = candidates[0]
        caller = str(raw_call.get("caller_nid", ""))
        if not caller:
            continue
        if target == caller:
            continue
        pair = (caller, target)
        if pair in known_pairs:
            continue
        known_pairs.add(pair)
        resolved.append(
            {
                "source": caller,
                "target": target,
                "relation": "calls",
                "context": "call",
                "confidence": "INFERRED",
                "confidence_score": 0.8,
                "source_file": raw_call.get("source_file", ""),
                "source_location": raw_call.get("source_location"),
                "weight": 1.0,
            }
        )

    return resolved
```

### 4.4 Wire The Helper Into `extract()`

Target: `graphify/extract.py`, imports near `graphify/extract.py:1-11`.

The Fix: Add this import below the deterministic docs import after Phase 2:

```python
from .symbol_resolution import resolve_cross_file_raw_calls
```

Target: `graphify/extract.py`, function `extract()`, replace the cross-file call resolution block at `graphify/extract.py:4670-4719`.

The Problem: The block is currently inline and should be delegated to the isolated helper.

The Fix: Replace the full block from the comment beginning `# Cross-file call resolution for all languages` through the emitted edge dictionary append call with this exact block:

```python
    # Cross-file call resolution for all languages.
    # Each extractor saved unresolved calls in raw_calls. Now that we have all
    # nodes from all files, resolve any callee that exists uniquely in the corpus.
    # The helper intentionally skips member calls and ambiguous duplicate labels.
    all_edges.extend(resolve_cross_file_raw_calls(per_file, all_nodes, all_edges))
```

### 4.5 Rationale

This is a safe refactor that makes future deterministic algorithms practical.

It does not claim to implement full name resolution yet. Instead, it creates a tested module that preserves behavior and creates a seam for future import-guided and scope-graph-lite logic.

This matters because static resolution should be built in layers:

1. Preserve current conservative raw-call resolution.
2. Add symbol indexing tests.
3. Add import evidence.
4. Add scope facts.
5. Only then consider richer dynamic dispatch heuristics.

### 4.6 Required Tests

Target: new file `tests/test_symbol_resolution.py`, module-level tests.

The Fix: Create `tests/test_symbol_resolution.py` with exactly this content:

```python
"""Tests for graphify.symbol_resolution."""
from __future__ import annotations

from graphify.symbol_resolution import (
    build_label_index,
    node_is_resolvable_symbol,
    normalise_callable_label,
    resolve_cross_file_raw_calls,
)


def test_normalise_callable_label_strips_function_punctuation() -> None:
    assert normalise_callable_label("run()") == "run"
    assert normalise_callable_label(".process()") == "process"
    assert normalise_callable_label("  Execute  ") == "execute"


def test_node_is_resolvable_symbol_skips_rationale_and_doc_tags() -> None:
    assert node_is_resolvable_symbol({"id": "a", "label": "run()", "file_type": "code"}) is True
    assert node_is_resolvable_symbol({"id": "r", "label": "why", "file_type": "rationale"}) is False
    assert node_is_resolvable_symbol({"id": "d", "label": "param x", "file_type": "doc_tag"}) is False


def test_build_label_index_collects_unique_symbols() -> None:
    nodes = [
        {"id": "a_run", "label": "run()", "file_type": "code"},
        {"id": "b_run", "label": "run()", "file_type": "code"},
        {"id": "doc", "label": "run docs", "file_type": "doc_tag"},
    ]
    assert build_label_index(nodes) == {"run": ["a_run", "b_run"]}


def test_resolve_cross_file_raw_calls_emits_unique_unqualified_call() -> None:
    per_file = [
        {
            "raw_calls": [
                {
                    "caller_nid": "caller_run",
                    "callee": "helper",
                    "is_member_call": False,
                    "source_file": "caller.py",
                    "source_location": "L2",
                }
            ]
        }
    ]
    nodes = [
        {"id": "caller_run", "label": "run()", "file_type": "code"},
        {"id": "helper_helper", "label": "helper()", "file_type": "code"},
    ]
    edges = []

    resolved = resolve_cross_file_raw_calls(per_file, nodes, edges)

    assert resolved == [
        {
            "source": "caller_run",
            "target": "helper_helper",
            "relation": "calls",
            "context": "call",
            "confidence": "INFERRED",
            "confidence_score": 0.8,
            "source_file": "caller.py",
            "source_location": "L2",
            "weight": 1.0,
        }
    ]


def test_resolve_cross_file_raw_calls_skips_member_calls() -> None:
    per_file = [
        {
            "raw_calls": [
                {
                    "caller_nid": "caller_run",
                    "callee": "helper",
                    "is_member_call": True,
                    "source_file": "caller.py",
                    "source_location": "L2",
                }
            ]
        }
    ]
    nodes = [
        {"id": "caller_run", "label": "run()", "file_type": "code"},
        {"id": "helper_helper", "label": "helper()", "file_type": "code"},
    ]
    assert resolve_cross_file_raw_calls(per_file, nodes, []) == []


def test_resolve_cross_file_raw_calls_skips_ambiguous_duplicate_labels() -> None:
    per_file = [
        {
            "raw_calls": [
                {
                    "caller_nid": "caller_run",
                    "callee": "log",
                    "is_member_call": False,
                    "source_file": "caller.py",
                    "source_location": "L2",
                }
            ]
        }
    ]
    nodes = [
        {"id": "caller_run", "label": "run()", "file_type": "code"},
        {"id": "a_log", "label": "log()", "file_type": "code"},
        {"id": "b_log", "label": "log()", "file_type": "code"},
    ]
    assert resolve_cross_file_raw_calls(per_file, nodes, []) == []


def test_resolve_cross_file_raw_calls_skips_existing_pair() -> None:
    per_file = [
        {
            "raw_calls": [
                {
                    "caller_nid": "caller_run",
                    "callee": "helper",
                    "is_member_call": False,
                    "source_file": "caller.py",
                    "source_location": "L2",
                }
            ]
        }
    ]
    nodes = [
        {"id": "caller_run", "label": "run()", "file_type": "code"},
        {"id": "helper_helper", "label": "helper()", "file_type": "code"},
    ]
    edges = [{"source": "caller_run", "target": "helper_helper", "relation": "calls"}]
    assert resolve_cross_file_raw_calls(per_file, nodes, edges) == []
```

### 4.7 Regression Validation

Run:

```bash
uv run pytest tests/test_symbol_resolution.py tests/test_extract.py::test_cross_file_calls_skip_ambiguous_duplicate_labels
```

Expected result:

```text
all selected tests pass
```

---


## 5. Phase 4 — Python Import-Guided Call Resolution

### 5.1 Target

Target: `graphify/symbol_resolution.py`, module-level symbol resolution helpers.

Target: `graphify/extract.py`, function `extract()`.

Verified local anchors:

- `graphify/extract.py:3620` already resolves Python `from ... import ...` statements into class-level `uses` edges.
- `graphify/extract.py:4670-4719` currently resolves raw unqualified calls only by global label uniqueness.
- `tests/test_extract.py:190-209` verifies Graphify must not guess when duplicate labels make a call ambiguous.

### 5.2 The Problem

The current raw-call resolver intentionally skips ambiguous names. That is correct. However, there is a common case where the call is not ambiguous to a human or to the Python parser:

```python
from helper import transform as tx

def run(value):
    return tx(value)
```

The raw call sees only `tx`. The current global label resolver cannot know that `tx` means `helper.transform`, so it either misses the call or might become tempted to guess later.

The deterministic solution is to use import evidence:

- Parse the importing Python file with the standard library `ast` module.
- Build an alias map from imported names to original module/name pairs.
- Compare each raw call callee against the alias map.
- Resolve only when the imported target exists exactly once in the indexed internal nodes.
- Emit the call as `EXTRACTED` because the edge is backed by an import statement and a call expression.
- Still skip member calls such as `obj.method()` because current raw call records do not preserve the receiver object.

### 5.3 The Fix

Replace the entire `graphify/symbol_resolution.py` file created in Phase 3 with this expanded version. This is safer for a beginner than asking them to manually merge partial additions.

```python
"""Deterministic symbol indexing and conservative cross-file resolution helpers."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_EXCLUDED_FILE_TYPES = {"rationale", "doc_tag"}


@dataclass(frozen=True)
class ImportedSymbol:
    """A Python imported name that can be used as deterministic resolution evidence."""

    local_name: str
    imported_name: str
    module_stem: str
    source_file: str
    source_location: str


def normalise_callable_label(label: str) -> str:
    """Normalize a node label into the key used for call resolution."""

    return label.strip().strip("()").lstrip(".").lower()


def node_is_resolvable_symbol(node: dict[str, Any]) -> bool:
    """Return True when a node is suitable for deterministic symbol lookup."""

    if node.get("file_type") in _EXCLUDED_FILE_TYPES:
        return False
    label = str(node.get("label", "")).strip()
    if not label:
        return False
    if label.endswith((".py", ".js", ".ts", ".tsx", ".java", ".go", ".rs")):
        return False
    return bool(normalise_callable_label(label))


def build_label_index(nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Build label -> node id list for conservative cross-file resolution."""

    index: dict[str, list[str]] = {}
    for node in nodes:
        if not node_is_resolvable_symbol(node):
            continue
        node_id = node.get("id")
        if not node_id:
            continue
        key = normalise_callable_label(str(node.get("label", "")))
        if not key:
            continue
        index.setdefault(key, []).append(str(node_id))
    return index


def existing_edge_pairs(edges: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """Return all existing source/target edge pairs."""

    pairs: set[tuple[str, str]] = set()
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source and target:
            pairs.add((str(source), str(target)))
    return pairs


def iter_raw_calls(per_file: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    """Return raw calls from all per-file extraction fragments."""

    calls: list[dict[str, Any]] = []
    for result in per_file:
        if not result:
            continue
        calls.extend(result.get("raw_calls", []))
    return calls


def _module_stem(module_name: str | None) -> str:
    """Return the final module component used to match Graphify source stems."""

    if not module_name:
        return ""
    return module_name.strip(".").split(".")[-1]


def parse_python_import_aliases(path: Path) -> dict[str, ImportedSymbol]:
    """Parse deterministic Python import aliases from one source file.

    Supported forms:
        from helper import transform
        from helper import transform as tx
        from .helper import transform

    The function deliberately does not resolve plain ``import helper`` member
    calls because current raw call records do not preserve the receiver name from
    ``helper.transform()``. That can be added later only after raw call facts are
    extended to include the receiver expression.
    """

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return {}

    aliases: dict[str, ImportedSymbol] = {}
    source_file = str(path)

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module_stem = _module_stem(node.module)
        if not module_stem:
            continue
        for alias in node.names:
            if alias.name == "*":
                continue
            local_name = alias.asname or alias.name
            aliases[local_name] = ImportedSymbol(
                local_name=local_name,
                imported_name=alias.name,
                module_stem=module_stem,
                source_file=source_file,
                source_location=f"L{getattr(node, 'lineno', 1)}",
            )

    return aliases


def _node_source_stem(node: dict[str, Any]) -> str:
    """Return the stem of a node's source file."""

    source_file = str(node.get("source_file", ""))
    if not source_file:
        return ""
    return Path(source_file).stem


def build_python_symbol_index(nodes: list[dict[str, Any]]) -> dict[tuple[str, str], list[str]]:
    """Build ``(module_stem, normalized_symbol_name) -> node_ids``.

    This index is stricter than the global label index. It uses both the module
    stem and the symbol label, which allows import evidence to resolve calls that
    global label uniqueness alone cannot safely resolve.
    """

    index: dict[tuple[str, str], list[str]] = {}
    for node in nodes:
        if not node_is_resolvable_symbol(node):
            continue
        source_stem = _node_source_stem(node)
        if not source_stem:
            continue
        label = normalise_callable_label(str(node.get("label", "")))
        if not label:
            continue
        node_id = node.get("id")
        if not node_id:
            continue
        index.setdefault((source_stem, label), []).append(str(node_id))
    return index


def find_unique_python_symbol(
    symbol_index: dict[tuple[str, str], list[str]],
    imported: ImportedSymbol,
) -> str | None:
    """Resolve one imported symbol to exactly one Graphify node id."""

    candidates = symbol_index.get((imported.module_stem, imported.imported_name.lower()), [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def resolve_python_import_guided_calls(
    per_file: list[dict[str, Any] | None],
    paths: list[Path],
    all_nodes: list[dict[str, Any]],
    all_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve raw Python calls using explicit import evidence.

    Only ``from module import symbol [as alias]`` forms are handled. Member calls
    remain skipped because the current raw call fact does not carry receiver
    information.
    """

    symbol_index = build_python_symbol_index(all_nodes)
    known_pairs = existing_edge_pairs(all_edges)
    result_by_file: dict[str, dict[str, Any]] = {
        str(path): per_file[index] or {"nodes": [], "edges": []}
        for index, path in enumerate(paths)
        if path.suffix == ".py"
    }
    resolved_edges: list[dict[str, Any]] = []

    for path in paths:
        if path.suffix != ".py":
            continue
        source_file = str(path)
        aliases = parse_python_import_aliases(path)
        if not aliases:
            continue
        file_result = result_by_file.get(source_file, {"raw_calls": []})
        for raw_call in file_result.get("raw_calls", []):
            if raw_call.get("is_member_call"):
                continue
            callee = str(raw_call.get("callee", "")).strip()
            if not callee:
                continue
            imported = aliases.get(callee)
            if imported is None:
                continue
            target = find_unique_python_symbol(symbol_index, imported)
            if target is None:
                continue
            caller = str(raw_call.get("caller_nid", ""))
            if not caller or caller == target:
                continue
            pair = (caller, target)
            if pair in known_pairs:
                continue
            known_pairs.add(pair)
            resolved_edges.append(
                {
                    "source": caller,
                    "target": target,
                    "relation": "calls",
                    "context": "import_guided_call",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": raw_call.get("source_file", source_file),
                    "source_location": raw_call.get("source_location") or imported.source_location,
                    "weight": 1.0,
                    "metadata": {
                        "resolver": "python_import_guided",
                        "local_name": imported.local_name,
                        "imported_name": imported.imported_name,
                        "module_stem": imported.module_stem,
                        "import_source_location": imported.source_location,
                    },
                }
            )

    return resolved_edges


def resolve_cross_file_raw_calls(
    per_file: list[dict[str, Any] | None],
    all_nodes: list[dict[str, Any]],
    all_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve unqualified raw calls conservatively after all files are known.

    This intentionally preserves Graphify's existing behavior:
    - member calls are skipped;
    - ambiguous labels are skipped;
    - only a single unique candidate is emitted;
    - emitted edges are INFERRED because the raw call alone is not import proof.
    """

    label_index = build_label_index(all_nodes)
    known_pairs = existing_edge_pairs(all_edges)
    resolved: list[dict[str, Any]] = []

    for raw_call in iter_raw_calls(per_file):
        callee = str(raw_call.get("callee", "")).strip()
        if not callee:
            continue
        if raw_call.get("is_member_call"):
            continue
        candidates = label_index.get(callee.lower(), [])
        if len(candidates) != 1:
            continue
        target = candidates[0]
        caller = str(raw_call.get("caller_nid", ""))
        if not caller:
            continue
        if target == caller:
            continue
        pair = (caller, target)
        if pair in known_pairs:
            continue
        known_pairs.add(pair)
        resolved.append(
            {
                "source": caller,
                "target": target,
                "relation": "calls",
                "context": "call",
                "confidence": "INFERRED",
                "confidence_score": 0.8,
                "source_file": raw_call.get("source_file", ""),
                "source_location": raw_call.get("source_location"),
                "weight": 1.0,
            }
        )

    return resolved
```

### 5.4 Wire The Import-Guided Resolver Into Extraction

Target: `graphify/extract.py`, imports near `graphify/extract.py:1-11`.

The Problem: `extract()` cannot use the new import-guided resolver until it imports it.

The Fix: Replace the Phase 3 import:

```python
from .symbol_resolution import resolve_cross_file_raw_calls
```

with this exact import block:

```python
from .symbol_resolution import (
    resolve_cross_file_raw_calls,
    resolve_python_import_guided_calls,
)
```

Target: `graphify/extract.py`, function `extract()`, after the Java cross-file import block at `graphify/extract.py:4660-4668` and before the raw-call block beginning at `graphify/extract.py:4670`.

The Problem: Import-guided calls must run before global raw-call fallback. If the fallback runs first, it might emit weaker `INFERRED` edges before the import-guided pass has a chance to emit stronger `EXTRACTED` edges.

The Fix: Insert this exact block immediately before the comment `# Cross-file call resolution for all languages.`:

```python
    # Python import-guided call resolution.
    # This runs before global raw-call fallback so import-backed calls can be
    # emitted as EXTRACTED instead of weaker INFERRED edges.
    if py_paths:
        try:
            all_edges.extend(resolve_python_import_guided_calls(per_file, paths, all_nodes, all_edges))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Python import-guided call resolution failed, skipping: %s", exc)
```

### 5.5 Rationale

This implements the deterministic algorithm described in the research without overreaching into full dynamic Python analysis.

It is intentionally conservative:

- It handles only `from module import symbol` and alias forms.
- It requires exactly one matching internal target symbol.
- It does not resolve wildcard imports.
- It does not resolve `import module; module.symbol()` because current raw call records do not carry receiver text.
- It emits `EXTRACTED` only when import evidence and call evidence agree.

This improves graph precision without repeating the old mistake of guessing ambiguous edges.

### 5.6 Required Tests

Target: `tests/test_symbol_resolution.py`, append these tests after the Phase 3 tests.

```python
from pathlib import Path

from graphify.symbol_resolution import (
    build_python_symbol_index,
    find_unique_python_symbol,
    parse_python_import_aliases,
    resolve_python_import_guided_calls,
)


def test_parse_python_import_aliases_supports_from_import_alias(tmp_path: Path) -> None:
    src = tmp_path / "caller.py"
    src.write_text("from helper import transform as tx\n", encoding="utf-8")

    aliases = parse_python_import_aliases(src)

    assert set(aliases) == {"tx"}
    imported = aliases["tx"]
    assert imported.local_name == "tx"
    assert imported.imported_name == "transform"
    assert imported.module_stem == "helper"
    assert imported.source_location == "L1"


def test_build_python_symbol_index_uses_module_stem_and_label() -> None:
    nodes = [
        {"id": "helper_transform", "label": "transform()", "file_type": "code", "source_file": "/repo/helper.py"},
        {"id": "other_transform", "label": "transform()", "file_type": "code", "source_file": "/repo/other.py"},
    ]
    index = build_python_symbol_index(nodes)
    assert index[("helper", "transform")] == ["helper_transform"]
    assert index[("other", "transform")] == ["other_transform"]


def test_find_unique_python_symbol_returns_none_when_ambiguous(tmp_path: Path) -> None:
    src = tmp_path / "caller.py"
    src.write_text("from helper import transform\n", encoding="utf-8")
    imported = parse_python_import_aliases(src)["transform"]
    index = {("helper", "transform"): ["a", "b"]}
    assert find_unique_python_symbol(index, imported) is None


def test_resolve_python_import_guided_calls_emits_extracted_edge(tmp_path: Path) -> None:
    caller = tmp_path / "caller.py"
    helper = tmp_path / "helper.py"
    caller.write_text("from helper import transform as tx\n\ndef run(value):\n    return tx(value)\n", encoding="utf-8")
    helper.write_text("def transform(value):\n    return value\n", encoding="utf-8")

    per_file = [
        {
            "raw_calls": [
                {
                    "caller_nid": "caller_run",
                    "callee": "tx",
                    "is_member_call": False,
                    "source_file": str(caller),
                    "source_location": "L4",
                }
            ]
        },
        {"raw_calls": []},
    ]
    nodes = [
        {"id": "caller_run", "label": "run()", "file_type": "code", "source_file": str(caller)},
        {"id": "helper_transform", "label": "transform()", "file_type": "code", "source_file": str(helper)},
    ]

    edges = resolve_python_import_guided_calls(per_file, [caller, helper], nodes, [])

    assert edges == [
        {
            "source": "caller_run",
            "target": "helper_transform",
            "relation": "calls",
            "context": "import_guided_call",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": str(caller),
            "source_location": "L4",
            "weight": 1.0,
            "metadata": {
                "resolver": "python_import_guided",
                "local_name": "tx",
                "imported_name": "transform",
                "module_stem": "helper",
                "import_source_location": "L1",
            },
        }
    ]
```

Target: `tests/test_extract.py`, append this integration test near `tests/test_extract.py:190-209`.

```python
def test_python_import_guided_cross_file_call_is_extracted(tmp_path):
    caller = tmp_path / "caller.py"
    helper = tmp_path / "helper.py"
    caller.write_text(
        "from helper import transform as tx\n\n"
        "def run(value):\n"
        "    return tx(value)\n",
        encoding="utf-8",
    )
    helper.write_text(
        "def transform(value):\n"
        "    return value\n",
        encoding="utf-8",
    )

    result = extract([caller, helper], cache_root=tmp_path)
    nodes = {node["id"]: node for node in result["nodes"]}
    calls = [edge for edge in result["edges"] if edge["relation"] == "calls"]

    assert any(
        nodes[edge["source"]]["label"] == "run()"
        and nodes[edge["target"]]["label"] == "transform()"
        and edge["confidence"] == "EXTRACTED"
        and edge.get("context") == "import_guided_call"
        for edge in calls
    )
```

### 5.7 Validation Command

Run:

```bash
uv run pytest tests/test_symbol_resolution.py tests/test_extract.py::test_python_import_guided_cross_file_call_is_extracted tests/test_extract.py::test_cross_file_calls_skip_ambiguous_duplicate_labels
```

Expected result:

```text
all selected tests pass
```

---

## 6. Phase 5 — Deterministic Python Test-to-Code Linking

### 6.1 Target

Target: new file `graphify/test_linking.py`, module-level test-linking helpers.

Target: `graphify/extract.py`, function `extract()`.

Verified local anchors:

- `graphify/extract.py:4546` gathers all per-file extraction results and is the correct post-pass insertion point.
- `tests/test_extract.py:33-66` already validates multi-file extraction.
- The research verification found test-to-code linking feasible when import evidence exists; naming-only heuristics should be treated cautiously.

### 6.2 The Problem

Tests encode important semantic relationships. A test function that imports and calls a production function is deterministic evidence that the test covers that production symbol.

Example:

```python
from service import transform

def test_transform_uppercases():
    assert transform("a") == "A"
```

The current extractor may emit a `calls` edge, but it does not emit a semantic `tests` edge that downstream analysis can use to understand behavioral coverage.

A safe first implementation should only emit `tests` edges when there is direct import-and-call evidence. It should not rely only on fuzzy name matching.

### 6.3 The Fix

Create `graphify/test_linking.py` with exactly this content:

```python
"""Deterministic test-to-code linking helpers."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from graphify.symbol_resolution import (
    build_python_symbol_index,
    existing_edge_pairs,
    find_unique_python_symbol,
    parse_python_import_aliases,
)


def is_python_test_file(path: Path) -> bool:
    """Return True when a path looks like a Python test file."""

    name = path.name
    parts = {part.lower() for part in path.parts}
    return path.suffix == ".py" and (
        name.startswith("test_")
        or name.endswith("_test.py")
        or "tests" in parts
    )


def _normalise_function_label(label: str) -> str:
    """Normalize a Graphify function label into a Python function name."""

    return label.strip().strip("()").lstrip(".")


def _test_function_nodes_for_file(path: Path, nodes: list[dict[str, Any]]) -> dict[str, str]:
    """Return test function name -> node id for one test file."""

    source_file = str(path)
    result: dict[str, str] = {}
    for node in nodes:
        if str(node.get("source_file", "")) != source_file:
            continue
        if node.get("file_type") == "rationale":
            continue
        label = str(node.get("label", ""))
        function_name = _normalise_function_label(label)
        if function_name.startswith("test_") and node.get("id"):
            result[function_name] = str(node["id"])
    return result


def _called_names_in_function(function_node: ast.AST) -> set[str]:
    """Return simple function names called inside a Python function body."""

    called: set[str] = set()
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            called.add(func.id)
    return called


def _iter_test_function_calls(path: Path) -> list[tuple[str, set[str], str]]:
    """Return ``(test_function_name, called_names, line)`` tuples."""

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return []

    results: list[tuple[str, set[str], str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            results.append((node.name, _called_names_in_function(node), f"L{getattr(node, 'lineno', 1)}"))
    return results


def resolve_python_test_edges(
    paths: list[Path],
    all_nodes: list[dict[str, Any]],
    all_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Emit deterministic ``tests`` edges from Python test functions to code symbols.

    A ``tests`` edge is emitted only when all of the following are true:
    - the file is a Python test file;
    - the test function exists as a Graphify node;
    - the test function calls a simple imported alias/name;
    - the import resolves to exactly one internal symbol.
    """

    symbol_index = build_python_symbol_index(all_nodes)
    known_pairs: set[tuple[str, str]] = set()  # independent dedup, not inherited from Phase4
    edges: list[dict[str, Any]] = []

    for path in paths:
        if not is_python_test_file(path):
            continue
        aliases = parse_python_import_aliases(path)
        if not aliases:
            continue
        test_nodes = _test_function_nodes_for_file(path, all_nodes)
        if not test_nodes:
            continue
        for test_name, called_names, function_line in _iter_test_function_calls(path):
            test_node_id = test_nodes.get(test_name)
            if not test_node_id:
                continue
            for called_name in sorted(called_names):
                imported = aliases.get(called_name)
                if imported is None:
                    continue
                target = find_unique_python_symbol(symbol_index, imported)
                if target is None or target == test_node_id:
                    continue
                pair = (test_node_id, target)
                if pair in known_pairs:
                    continue
                known_pairs.add(pair)
                edges.append(
                    {
                        "source": test_node_id,
                        "target": target,
                        "relation": "tests",
                        "context": "test_to_code_import_call",
                        "confidence": "EXTRACTED",
                        "confidence_score": 1.0,
                        "source_file": str(path),
                        "source_location": function_line,
                        "weight": 1.0,
                        "metadata": {
                            "resolver": "python_test_import_call",
                            "test_function": test_name,
                            "called_name": called_name,
                            "imported_name": imported.imported_name,
                            "module_stem": imported.module_stem,
                        },
                    }
                )

    return edges
```

### 6.4 Wire Test Linking Into Extraction

Target: `graphify/extract.py`, imports near `graphify/extract.py:1-11`.

The Fix: Add this import below the symbol-resolution import block:

```python
from .test_linking import resolve_python_test_edges
```

Target: `graphify/extract.py`, function `extract()`, immediately after the Phase 4 import-guided call resolver block and before raw-call fallback.

The Fix: Insert this exact block:

```python
    # Deterministic Python test-to-code linking.
    # Only import-backed test calls are emitted as EXTRACTED tests edges.
    if py_paths:
        try:
            all_edges.extend(resolve_python_test_edges(paths, all_nodes, all_edges))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Python test-to-code linking failed, skipping: %s", exc)
```

### 6.5 Rationale

This adds a semantic relationship that the existing extraction pipeline does not currently represent. It remains deterministic because it requires:

- a test file;
- a test function node;
- a direct call inside the test function;
- an explicit import alias/name;
- exactly one matching internal target symbol.

It avoids fuzzy naming-only guesses. Those can be added later as `INFERRED` edges if desired, but they should not be part of the first implementation.

### 6.6 Required Tests

Target: new file `tests/test_test_linking.py`, module-level tests.

```python
"""Tests for deterministic test-to-code linking."""
from __future__ import annotations

from pathlib import Path

from graphify.test_linking import is_python_test_file, resolve_python_test_edges


def test_is_python_test_file_detects_common_patterns(tmp_path: Path) -> None:
    assert is_python_test_file(tmp_path / "test_service.py") is True
    assert is_python_test_file(tmp_path / "service_test.py") is True
    nested = tmp_path / "tests" / "service.py"
    assert is_python_test_file(nested) is True
    assert is_python_test_file(tmp_path / "service.py") is False
    assert is_python_test_file(tmp_path / "test_service.txt") is False


def test_resolve_python_test_edges_emits_import_backed_tests_edge(tmp_path: Path) -> None:
    prod = tmp_path / "service.py"
    test = tmp_path / "test_service.py"
    prod.write_text("def transform(value):\n    return value.upper()\n", encoding="utf-8")
    test.write_text(
        "from service import transform\n\n"
        "def test_transform_uppercases():\n"
        "    assert transform('a') == 'A'\n",
        encoding="utf-8",
    )

    nodes = [
        {"id": "service_transform", "label": "transform()", "file_type": "code", "source_file": str(prod)},
        {"id": "test_service_test_transform_uppercases", "label": "test_transform_uppercases()", "file_type": "code", "source_file": str(test)},
    ]

    edges = resolve_python_test_edges([prod, test], nodes, [])

    assert edges == [
        {
            "source": "test_service_test_transform_uppercases",
            "target": "service_transform",
            "relation": "tests",
            "context": "test_to_code_import_call",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": str(test),
            "source_location": "L3",
            "weight": 1.0,
            "metadata": {
                "resolver": "python_test_import_call",
                "test_function": "test_transform_uppercases",
                "called_name": "transform",
                "imported_name": "transform",
                "module_stem": "service",
            },
        }
    ]
```

Target: `tests/test_extract.py`, append this integration test near the multi-file extraction tests at `tests/test_extract.py:62-66`.

```python
def test_extract_emits_python_tests_edges_for_import_backed_calls(tmp_path):
    prod = tmp_path / "service.py"
    test = tmp_path / "test_service.py"
    prod.write_text(
        "def transform(value):\n"
        "    return value.upper()\n",
        encoding="utf-8",
    )
    test.write_text(
        "from service import transform\n\n"
        "def test_transform_uppercases():\n"
        "    assert transform('a') == 'A'\n",
        encoding="utf-8",
    )

    result = extract([prod, test], cache_root=tmp_path)
    nodes = {node["id"]: node for node in result["nodes"]}
    test_edges = [edge for edge in result["edges"] if edge["relation"] == "tests"]

    assert any(
        nodes[edge["source"]]["label"] == "test_transform_uppercases()"
        and nodes[edge["target"]]["label"] == "transform()"
        and edge["confidence"] == "EXTRACTED"
        and edge.get("context") == "test_to_code_import_call"
        for edge in test_edges
    )
```

### 6.7 Validation Command

Run:

```bash
uv run pytest tests/test_test_linking.py tests/test_extract.py::test_extract_emits_python_tests_edges_for_import_backed_calls
```

Expected result:

```text
all selected tests pass
```

---

## 7. Phase 6 — Optional SCIP Index Ingestion Skeleton

### 7.1 Target

Target: new file `graphify/scip_ingest.py`, module-level optional ingestion helpers.

Target: no core extractor wiring in the first implementation pass.

Verified local anchors:

- `graphify/build.py:48-116` can build from normal node/edge dicts regardless of where the extraction came from.
- `graphify/__main__.py:2215-2223` merges AST and semantic extraction outputs as plain dicts.
- The verification research qualified SCIP as active and LSIF as legacy/deprecated. Therefore, SCIP is the correct first optional index format.

### 7.2 The Problem

External compiler/language-server indexes can provide high-quality symbol occurrence data, but Graphify must not require those tools for normal extraction.

The safe first implementation is a standalone ingestion module that can convert a simplified SCIP-like JSON export into Graphify-compatible extraction dicts. This gives implementers a tested seam before adding CLI flags or binary protobuf parsing.

A beginner-friendly explanation:

- SCIP is an index format, not a Python AST parser.
- Real `.scip` files are protobuf-based.
- This phase intentionally starts with JSON dictionaries because it avoids adding mandatory protobuf dependencies.
- A later implementation can add true protobuf decoding behind an optional dependency.

### 7.3 The Fix

Create `graphify/scip_ingest.py` with exactly this content:

```python
"""Optional SCIP-like index ingestion helpers.

This module intentionally accepts a JSON-compatible subset rather than requiring
SCIP protobuf dependencies. It creates Graphify-compatible nodes and edges from
symbol occurrence records when a caller has already converted an index to JSON.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graphify.semantic_facts import append_unique_edge, append_unique_node, make_fact_node


def _safe_symbol_id(symbol: str) -> str:
    """Return a stable Graphify-safe id fragment for an index symbol."""

    cleaned = []
    for char in symbol:
        if char.isalnum():
            cleaned.append(char.lower())
        else:
            cleaned.append("_")
    value = "".join(cleaned).strip("_")
    while "__" in value:
        value = value.replace("__", "_")
    return value or "symbol"


def _range_to_location(range_value: Any) -> str | None:
    """Convert a SCIP-like zero-based range into Graphify's line location."""

    if isinstance(range_value, list) and range_value:
        first = range_value[0]
        if isinstance(first, int):
            return f"L{first + 1}"
    return None


def _occurrence_role(occurrence: dict[str, Any]) -> str:
    """Return normalized occurrence role from common SCIP JSON shapes."""

    symbol_roles = occurrence.get("symbol_roles")
    if isinstance(symbol_roles, list):
        lowered = {str(role).lower() for role in symbol_roles}
        if "definition" in lowered:
            return "definition"
        if "reference" in lowered:
            return "reference"
    if occurrence.get("definition") is True:
        return "definition"
    raw = str(occurrence.get("role", "")).lower()
    if "definition" in raw:
        return "definition"
    if "reference" in raw:
        return "reference"
    return "reference"


def ingest_scip_json(data: dict[str, Any], *, source_name: str = "scip") -> dict[str, list[dict[str, Any]]]:
    """Convert a JSON-compatible SCIP-like index into Graphify extraction data.

    Expected minimal shape:
        {
            "documents": [
                {
                    "relative_path": "pkg/mod.py",
                    "occurrences": [
                        {"symbol": "pkg/mod.py::foo().", "range": [0, 0, 0, 3], "role": "definition"}
                    ]
                }
            ]
        }

    The function is intentionally permissive because different tools expose SCIP
    JSON with slightly different key spellings.
    """

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    seen_edges: set[tuple[str, str, str, str | None]] = set()
    definition_by_symbol: dict[str, str] = {}
    references: list[tuple[str, str, str | None]] = []

    documents = data.get("documents", [])
    if not isinstance(documents, list):
        return {"nodes": [], "edges": []}

    for doc in documents:
        if not isinstance(doc, dict):
            continue
        source_file = str(doc.get("relative_path") or doc.get("path") or doc.get("uri") or source_name)
        file_node_id = f"scip_file_{_safe_symbol_id(source_file)}"
        append_unique_node(
            nodes,
            seen_nodes,
            make_fact_node(
                node_id=file_node_id,
                label=Path(source_file).name,
                file_type="code_index",
                source_file=source_file,
                source_location="L1",
                metadata={"index_format": "scip_json_subset"},
            ),
        )
        occurrences = doc.get("occurrences", [])
        if not isinstance(occurrences, list):
            continue
        for occurrence in occurrences:
            if not isinstance(occurrence, dict):
                continue
            symbol = str(occurrence.get("symbol", "")).strip()
            if not symbol:
                continue
            symbol_id = f"scip_symbol_{_safe_symbol_id(symbol)}"
            location = _range_to_location(occurrence.get("range"))
            role = _occurrence_role(occurrence)
            append_unique_node(
                nodes,
                seen_nodes,
                make_fact_node(
                    node_id=symbol_id,
                    label=symbol,
                    file_type="code_index_symbol",
                    source_file=source_file,
                    source_location=location,
                    metadata={"index_format": "scip_json_subset", "role": role},
                ),
            )
            append_unique_edge(
                edges,
                seen_edges,
                {
                    "source": file_node_id,
                    "target": symbol_id,
                    "relation": "defines" if role == "definition" else "references",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": source_file,
                    "source_location": location,
                    "weight": 1.0,
                    "context": "scip_index_occurrence",
                },
            )
            if role == "definition":
                definition_by_symbol.setdefault(symbol, symbol_id)
            else:
                references.append((file_node_id, symbol, location))

    for file_node_id, symbol, location in references:
        definition_id = definition_by_symbol.get(symbol)
        if definition_id is None:
            continue
        append_unique_edge(
            edges,
            seen_edges,
            {
                "source": file_node_id,
                "target": definition_id,
                "relation": "references_definition",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": source_name,
                "source_location": location,
                "weight": 1.0,
                "context": "scip_index_resolution",
            },
        )

    return {"nodes": nodes, "edges": edges}


def ingest_scip_json_file(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Load and ingest a JSON SCIP-like index file."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"nodes": [], "edges": []}
    if not isinstance(data, dict):
        return {"nodes": [], "edges": []}
    return ingest_scip_json(data, source_name=str(path))
```

### 7.4 Rationale

This phase prevents overcommitment. It records the verified direction — SCIP first, LSIF legacy, SemanticDB JVM-specific — but only implements a safe JSON-compatible ingestion skeleton.

It is useful because:

- It can be tested without installing SCIP tools.
- It emits ordinary Graphify dicts.
- It keeps external indexes optional.
- It provides a clear future seam for protobuf decoding.

### 7.5 Required Tests

Target: new file `tests/test_scip_ingest.py`, module-level tests.

```python
"""Tests for optional SCIP-like index ingestion."""
from __future__ import annotations

import json
from pathlib import Path

from graphify.scip_ingest import ingest_scip_json, ingest_scip_json_file


def test_ingest_scip_json_creates_symbol_nodes_and_edges() -> None:
    data = {
        "documents": [
            {
                "relative_path": "pkg/mod.py",
                "occurrences": [
                    {"symbol": "pkg/mod.py::foo().", "range": [0, 0, 0, 3], "role": "definition"},
                    {"symbol": "pkg/mod.py::foo().", "range": [3, 4, 3, 7], "role": "reference"},
                ],
            }
        ]
    }

    result = ingest_scip_json(data)

    labels = {node["label"] for node in result["nodes"]}
    relations = {edge["relation"] for edge in result["edges"]}
    assert "mod.py" in labels
    assert "pkg/mod.py::foo()." in labels
    assert "defines" in relations
    assert "references" in relations
    assert "references_definition" in relations


def test_ingest_scip_json_file_returns_empty_for_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not-json", encoding="utf-8")
    assert ingest_scip_json_file(path) == {"nodes": [], "edges": []}


def test_ingest_scip_json_file_loads_valid_json(tmp_path: Path) -> None:
    path = tmp_path / "index.json"
    path.write_text(json.dumps({"documents": []}), encoding="utf-8")
    assert ingest_scip_json_file(path) == {"nodes": [], "edges": []}
```

### 7.6 Validation Command

Run:

```bash
uv run pytest tests/test_scip_ingest.py
```

Expected result:

```text
all selected tests pass
```

---

## 8. Phase 7 — Cache Safety and Deterministic Extraction Metadata

### 8.1 Target

Target: `graphify/cache.py`, functions `cached_files()` and `clear_cache()`.

Verified local anchors:

- `graphify/cache.py:64-74` already supports arbitrary cache namespace names via `kind`.
- `graphify/cache.py:77-145` already works for arbitrary `kind` values.
- `graphify/cache.py:148-160` only scans `ast` and `semantic` namespaces in `cached_files()`.
- `graphify/cache.py:163-175` only clears `ast` and `semantic` namespaces in `clear_cache()`.

### 8.2 The Problem

The runbook phases above do not require a separate deterministic cache namespace immediately because the AST cache stores each full per-file extraction result. However, if later implementers add a separate `kind="deterministic"` cache, the current helper functions will not list or clear it.

This is a small maintenance defect: the cache API accepts arbitrary namespaces, but two convenience functions hard-code only two names.

### 8.3 The Fix

Target: `graphify/cache.py`, add this helper after `_GRAPHIFY_OUT` at `graphify/cache.py:13`:

```python
_KNOWN_CACHE_KINDS = ("ast", "semantic", "deterministic")
```

Target: `graphify/cache.py`, function `cached_files()` at `graphify/cache.py:148-160`.

Replace the entire function with this exact function:

```python
def cached_files(root: Path = Path(".")) -> set[str]:
    """Return set of file hashes that have a valid cache entry in any known namespace."""
    base = Path(root).resolve() / _GRAPHIFY_OUT / "cache"
    hashes: set[str] = set()
    # Legacy flat entries
    if base.is_dir():
        hashes.update(p.stem for p in base.glob("*.json"))
    # Namespaced entries
    for kind in _KNOWN_CACHE_KINDS:
        d = base / kind
        if d.is_dir():
            hashes.update(p.stem for p in d.glob("*.json"))
    return hashes
```

Target: `graphify/cache.py`, function `clear_cache()` at `graphify/cache.py:163-175`.

Replace the entire function with this exact function:

```python
def clear_cache(root: Path = Path(".")) -> None:
    """Delete all cache entries in legacy and known namespaced cache directories."""
    base = Path(root).resolve() / _GRAPHIFY_OUT / "cache"
    # Legacy flat entries
    if base.is_dir():
        for f in base.glob("*.json"):
            f.unlink()
    # Namespaced entries
    for kind in _KNOWN_CACHE_KINDS:
        d = base / kind
        if d.is_dir():
            for f in d.glob("*.json"):
                f.unlink()
```

### 8.4 Rationale

This is deliberately small. The extraction changes above continue using the existing AST cache path, so this phase is future-proofing rather than a prerequisite.

It keeps current behavior for `ast` and `semantic`, and extends helper awareness to a deterministic namespace if later phases split deterministic fact caching from AST caching.

### 8.5 Required Tests

Target: `tests/test_cache.py`, append these tests near the existing cache namespace tests around `tests/test_cache.py:174-216`.

```python
def test_cached_files_includes_deterministic_namespace(tmp_path):
    src = tmp_path / "sample.py"
    src.write_text("print('x')", encoding="utf-8")
    save_cached(src, {"nodes": [], "edges": []}, root=tmp_path, kind="deterministic")

    hashes = cached_files(root=tmp_path)

    assert file_hash(src, tmp_path) in hashes


def test_clear_cache_clears_deterministic_namespace(tmp_path):
    src = tmp_path / "sample.py"
    src.write_text("print('x')", encoding="utf-8")
    save_cached(src, {"nodes": [], "edges": []}, root=tmp_path, kind="deterministic")

    clear_cache(root=tmp_path)

    deterministic_dir = tmp_path / "graphify-out" / "cache" / "deterministic"
    assert not list(deterministic_dir.glob("*.json"))
```

### 8.6 Validation Command

Run:

```bash
uv run pytest tests/test_cache.py::test_cached_files_includes_deterministic_namespace tests/test_cache.py::test_clear_cache_clears_deterministic_namespace
```

Expected result:

```text
all selected tests pass
```

---

## 9. Phase 8 — CLI Integration Policy

### 9.1 Target

Target: `graphify/__main__.py`, `graphify extract` command flow.

Verified local anchors:

- `graphify/__main__.py:2144-2160` runs AST extraction on code files.
- `graphify/__main__.py:2162-2210` runs LLM semantic extraction only on docs, papers, and images.
- `graphify/__main__.py:2215-2223` merges AST and semantic results.
- `graphify/__main__.py:2267-2294` builds the graph.

### 9.2 The Problem

The research discussed reducing LLM work for code. Live code verification shows Graphify already sends code files through AST extraction and sends documents/papers/images through direct semantic extraction. Therefore, the first implementation should not add CLI flags for code LLM avoidance.

Adding CLI flags too early would create a surface area before the internal APIs are stable.

### 9.3 The Fix

Do not change `graphify/__main__.py` in the first implementation pass.

Use this explicit policy in the implementation ticket:

```text
No CLI change is required for Phases 1 through 8.
The new deterministic extraction helpers are internal AST-extraction improvements.
The existing graphify extract command automatically receives them because it calls graphify.extract.extract() for code files.
```

### 9.4 Rationale

This is a deliberate non-change. It prevents unnecessary CLI churn and keeps the feature behind the same path users already exercise:

```text
graphify extract <target>
  -> code_files
  -> graphify.extract.extract()
  -> new deterministic post-passes
```

A CLI flag can be considered later if one of the deterministic post-passes becomes expensive or controversial. The current proposed passes are local, stdlib-based, and conservative.

### 9.5 Validation Command

Run the existing CLI-related tests if present, and always run the full extraction test subset:

```bash
uv run pytest tests/test_extract.py tests/test_cache.py
```

Expected result:

```text
all selected tests pass
```

---

## 10. Phase 9 — Required Full Validation Suite

### 10.1 Target

Target: whole repository validation after implementation.

Verified local anchors:

- `pyproject.toml` configures the project for `uv`-based test execution.
- The previous rebase recovery validated the full suite with `uv run pytest`.
- `graphify-out/GRAPH_REPORT.md:12-15` requires `graphify update .` after code changes.

### 10.2 The Problem

This implementation affects extraction, caching, and tests. A targeted test pass is not enough. The new edges can affect graph structure, dedup behavior, report output, and global graph update behavior.

### 10.3 The Fix

After implementing all selected phases, run these commands in order:

```bash
uv run pytest tests/test_semantic_facts.py
uv run pytest tests/test_symbol_resolution.py
uv run pytest tests/test_test_linking.py
uv run pytest tests/test_scip_ingest.py
uv run pytest tests/test_extract.py tests/test_cache.py tests/test_languages.py
uv run pytest
git diff --check
graphify update .
git status --short --branch --untracked-files=all
```

### 10.4 Expected Outcomes

The expected final outcomes are:

```text
all targeted tests pass
full test suite passes
git diff --check reports no whitespace errors
graphify update . completes successfully
tracked code changes are visible and intentional
.dox artifacts remain ignored/private
```

### 10.5 Rationale

This validation order catches failures progressively:

- Unit tests catch helper logic mistakes.
- Extraction tests catch integration mistakes.
- Full tests catch downstream graph/report/dedup regressions.
- Whitespace checks catch patch hygiene issues.
- Graph update satisfies the project rule in `graphify-out/GRAPH_REPORT.md:12-15`.

---

## 11. Phase 10 — Implementation Handoff Checklist

### 11.1 Target

Target: implementation agent or engineer applying this runbook.

### 11.2 The Problem

This runbook is exhaustive by design. The risk is not lack of detail; the risk is applying phases out of order or mixing optional external-index work into the core extraction changes before the deterministic internal pieces are tested.

### 11.3 The Fix

Apply phases in this order:

- [ ] Phase 0: Extend `VALID_FILE_TYPES`, add the documented `VALID_CONTEXTS` vocabulary, add `sanitize_metadata()`, and run the Phase 0 validation command.
- [ ] Phase 1: Add `graphify/semantic_facts.py` and `tests/test_semantic_facts.py`.
- [ ] Run `uv run pytest tests/test_semantic_facts.py`.
- [ ] Phase 2: Add `graphify/deterministic_docs.py`, wire `extract_python()`, add doc-tag tests.
- [ ] Run `uv run pytest tests/test_semantic_facts.py tests/test_extract.py`.
- [ ] Phase 3: Add initial `graphify/symbol_resolution.py`, wire raw-call helper, add tests.
- [ ] Run `uv run pytest tests/test_symbol_resolution.py tests/test_extract.py::test_cross_file_calls_skip_ambiguous_duplicate_labels`.
- [ ] Phase 4: Replace `graphify/symbol_resolution.py` with the import-guided version, wire import-guided calls, add tests.
- [ ] Run the Phase 4 validation command.
- [ ] Phase 5: Add `graphify/test_linking.py`, wire test-linking post-pass, add tests.
- [ ] Run the Phase 5 validation command.
- [ ] Phase 6: Add optional `graphify/scip_ingest.py` and tests, but do not wire it into CLI yet.
- [ ] Run the Phase 6 validation command.
- [ ] Phase 7: Update cache namespace helpers only if deterministic cache namespace support is desired now.
- [ ] Phase 8: Make no CLI changes in the first implementation pass.
- [ ] Phase 9: Run full validation.
- [ ] Run `graphify update .` after code changes.

### 11.4 Rationale

This order prevents broad breakage. Each phase adds a small, testable piece:

- facts first;
- doc tags second;
- resolver extraction third;
- stronger import-guided resolution fourth;
- test linking fifth;
- optional external ingestion sixth;
- cache/CLI policy last.

---

## 12. Items Requiring Further Investigation

### 12.1 Tree-sitter Query Packs

Target: future files under a new `graphify/queries/` package.

The Problem: The research strongly supports Tree-sitter query packs, but the current extractor already contains a large procedural multi-language walker. Replacing it with query packs is too broad for the first implementation pass.

The Fix: Treat query packs as a separate design/implementation project after Phases 1 through 5 land and stabilize.

Rationale: Query packs are a long-term maintainability improvement, but helper modules and post-passes produce immediate value without destabilizing every language extractor.

### 12.2 Full Scope Graphs / Stack Graphs

Target: future name-resolution subsystem.

The Problem: Scope graphs and stack graphs are verified real algorithms, but implementing them properly requires a larger language-specific scope model.

The Fix: Use the Phase 4 import-guided resolver as a conservative stepping stone. Do not claim full scope graph support until the implementation actually models lexical scopes, imports, exports, aliases, and candidate paths.

Rationale: This avoids hallucinating capabilities. The first implementation is import-guided resolution, not full stack graphs.

### 12.3 Real SCIP Protobuf Parsing

Target: future optional dependency path.

The Problem: Phase 6 handles JSON-compatible SCIP-like data, not raw `.scip` protobuf files.

The Fix: Add protobuf parsing later behind an optional dependency and explicit tests with real fixture data.

Rationale: The verification document confirmed SCIP as actionable, but production-grade ingestion requires real fixture validation rather than an invented parser.

### 12.4 Global Data Flow / Program Slicing

Target: future CPG-lite phase.

The Problem: Program slicing and data-flow algorithms are verified, but implementing them correctly is substantially larger than the safe first pass.

The Fix: Start with local facts, import-guided calls, and test links. Add local def-use only after those are stable.

Rationale: This keeps the plan executable and avoids mixing several complex static-analysis projects into one patch.

---

## 13. Final Diagnostic Summary

### 13.1 What This Runbook Implements Immediately

- [ ] A neutral deterministic semantic fact helper module.
- [ ] Deterministic Python docstring tag extraction.
- [ ] A reusable conservative symbol-resolution module.
- [ ] Import-guided Python cross-file call resolution.
- [ ] Deterministic Python test-to-code linking.
- [ ] Optional SCIP-like JSON ingestion skeleton.
- [ ] Cache namespace future-proofing.
- [ ] A validation sequence tied to the current repository.

### 13.2 What This Runbook Explicitly Does Not Pretend To Implement Yet

- [ ] Full Tree-sitter query-pack replacement.
- [ ] Full stack graph or scope graph name resolution.
- [ ] Full Code Property Graph construction.
- [ ] Global data-flow analysis.
- [ ] Program slicing.
- [ ] Raw `.scip` protobuf decoding.
- [ ] LSIF or SemanticDB ingestion.
- [ ] LLM prompt redesign.

### 13.3 Why This Is The Correct First Implementation Slice

The first slice is intentionally conservative because the live codebase already has a working multi-language extractor. The best engineering move is not to replace that extractor. The best move is to add deterministic semantic post-passes that:

- preserve existing behavior;
- add high-confidence facts;
- are easy to test;
- do not add mandatory dependencies;
- reduce future LLM reliance;
- establish clean modules for later static-analysis algorithms.

### 13.4 Final Instruction To Implementer

Do not implement this as one giant patch. Implement and validate phase-by-phase.

If any phase fails tests, stop and fix that phase before continuing. Do not skip ahead. Do not weaken tests to make the suite pass. Do not mark ambiguous edges as `EXTRACTED` unless the algorithm has deterministic evidence.

The core principle is:

```text
Emit deterministic facts when evidence is exact.
Mark uncertainty explicitly.
Leave high-level interpretation to later enrichment.
```

---
