# Independent Review: Deterministic Semantic Extraction Plan

Date: 2026-05-07

Scope: `.dox/` planning/research documents plus the live Graphify codebase in the project root. No implementation was performed.

## Executive Verdict

The plan is close to implementable, but I would not start the implementation run until two runbook corrections are made:

1. Fix the phase numbering mismatch between the phase map and the detailed phase sections. The map says Phase 4 is test-to-code linking and Phase 5 is SCIP ingestion, while the detailed checklist correctly says Phase 4 is import-guided calls, Phase 5 is test-linking, Phase 6 is SCIP, Phase 7 is cache, Phase 8 is CLI policy, and Phase 9 is full validation (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:223-264`, `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:3018-3034`).

2. Change edge deduplication before Phase 5. The runbook's helper keys only on `(source, target)`, so a Phase 4 `calls` edge can suppress a semantically distinct Phase 5 `tests` edge for the same pair (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1706-1715`, `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1975-1991`, `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2279-2306`). The required Phase 5 test expects the `tests` edge to exist (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2448-2458`).

The rest of the issues below are important but can be handled as implementation guardrails or follow-up acceptance criteria.

## Evidence Boundary

- The current graph report is fresh for the checked-out commit and identifies the corpus as large enough for graph structure to matter: 174 files, 5481 nodes, 7912 edges, 484 communities (`graphify-out/GRAPH_REPORT.md:1-15`).
- `graphify-out/wiki/index.md` is not present, so I used the graph report plus direct files.
- The named file `.dox/2026-05-06-implementation-risk-assessment.md` is not present in `.dox/`. I therefore treated the available risk inputs as the agent/verifier reports, especially coverage, architecture, security, queen synthesis, and unified verification reports.
- The current runbook is newer than several verifier findings. Some earlier blockers have already been fixed in the current runbook and should not be re-opened.

## 1. Runbook Accuracy

### Claims that are correct

- The Phase 0 schema correction is accurate. The current validator only accepts the existing file types (`graphify/validate.py:4-7`), rejects unknown node `file_type` values as validation errors (`graphify/validate.py:33-37`), and `assert_valid()` would raise on those errors (`graphify/validate.py:67-72`). The runbook correctly says `build_from_json()` still adds all nodes and only prints non-dangling validation issues as warnings (`graphify/build.py:75-84`), so missing `VALID_FILE_TYPES` is schema noise and strict-validation failure, not node loss (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:91-112`).

- The `VALID_CONTEXTS` step is correctly framed as documentation/discoverability, not active validation. Current validation checks edge confidence and dangling endpoints but does not validate edge `relation` or `context` (`graphify/validate.py:54-62`). The runbook says the context vocabulary is forward-looking (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:114-130`).

- The metadata sanitization gap is correctly identified. Live `graphify/security.py` currently exposes `sanitize_label()` only (`graphify/security.py:224-239`). The runbook adds bounded recursive `sanitize_metadata()` and says to call it from both node and edge emission (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:132-190`). The current Phase 1 code block actually imports and applies it in `fact_to_edge()` and `make_fact_node()` (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:312-410`).

- The runbook no longer contains the earlier risky `ast.get_docstring(..., clean=False)` prescription. The current docstring extractor uses the default `ast.get_docstring(node)` calls (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:948-967`). Python's own docs describe `ast.get_docstring(node, clean=True)` and state that `clean=True` uses `inspect.cleandoc()`, which is consistent with the current code path.

- The earlier dead `_clean_docstring()` concern is resolved in the current runbook. The runbook explicitly says that helper was removed before implementation (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1095-1101`).

- The existing Graphify extraction architecture supports adding deterministic post-passes after base extraction. `extract()` collects per-file results, merges AST outputs, then performs cross-file import/call resolution (`graphify/extract.py:4546-4719`). The runbook's decision to add doc tags, stronger call resolution, and test linking as post-passes fits that architecture.

### Claims that need correction or stronger wording

#### Phase map mismatch

The top-level phase map is stale. It omits the import-guided Phase 4, shifts test linking to Phase 4, shifts SCIP to Phase 5, and compresses later cache/CLI/full-validation phases (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:223-264`). The handoff checklist later uses a different and more accurate order (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:3018-3034`). This should be corrected before implementation because implementers will otherwise wire or test phases out of order.

Recommended correction: make the initial phase map match the handoff checklist exactly.

#### Pair-only edge deduplication will erase semantic edge types

The plan uses `existing_edge_pairs()` keyed only by `(source, target)` (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1706-1715`). Phase 4 is inserted before raw-call fallback and can emit a `calls` edge (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1975-1991`). Phase 5 then builds the same pair set and skips any edge whose pair already exists (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2279-2306`). That can suppress the desired `tests` edge, even though `calls` and `tests` have different semantics. The proposed Phase 5 test expects a `tests` relation to exist (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2448-2458`).

Recommended correction: deduplicate on at least `(source, target, relation)`. If source locations matter, use `(source, target, relation, source_location)` or reuse the Phase 1 `append_unique_edge()` keying convention.

#### End-to-end validation is under-specified

The runbook adds new node types and relations, but the existing no-dangling-edge regression only checks `contains`, `method`, `inherits`, and `calls` (`tests/test_extract.py:106-115`). Agent 5 independently flagged that as a high-risk gap and called for new-relation dangling-edge tests and downstream smoke tests (`.dox/2026-05-06-agent5-coverage.md:34-45`).

Recommended correction: add an extraction invariant test that checks every new internal relation has valid endpoints, then run `build_from_json()` on fixtures that include `doc_tag`, `tests`, `code_index`, and `code_index_symbol` nodes. This catches both dangling-edge regressions and schema warning regressions.

#### SCIP ingestion is a useful seam, not a safe ingestion boundary yet

The SCIP phase is correctly optional and dependency-free, but it reads an entire JSON file into memory with no size limit, depth limit, occurrence cap, path-root check, or symbol-id length cap (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2524-2536`, `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2602-2613`, `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2683-2692`). Agent 3 already identified SCIP input/resource risks and recommended path, size, and schema hardening (`.dox/2026-05-06-agent3-security.md:12-31`, `.dox/2026-05-06-agent3-security.md:49-63`).

Recommended correction: explicitly mark the Phase 6 helper as trusted-test-fixture-only until input caps and schema checks are added. If the team wants to accept arbitrary SCIP-like JSON from users, add those protections in Phase 0 or Phase 6.

#### Docstring source-location provenance needs edge-case tests

The doc-tag parser uses `ast.get_docstring()` plus a computed starting line (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:948-967`). That gives cleaned text, not exact source text. The required tests cover docstrings whose opening triple quote and summary are on the same line (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1151-1218`). They do not cover the common form where the opening triple quote is on its own line. In that case, cleaned-docstring line offsets can drift from source line offsets.

Recommended correction: add tests for quote-on-own-line, module docstrings, class docstrings, async functions, nested methods, and raw `# WHY:` comments. If exact line provenance matters, derive spans from AST node constants or `ast.get_source_segment()` rather than only from cleaned text.

#### Silent exception paths need diagnostics

Several planned helpers return empty results on `OSError`, `SyntaxError`, or `JSONDecodeError` (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1006-1014`, `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2683-2692`). Returning empty results is acceptable for resilient extraction, but the runbook should require at least one test for each silent path and should consider debug logging for post-passes. Agent 5 found only 1 of 11 proposed error-handling paths tested (`.dox/2026-05-06-agent5-coverage.md:47-58`).

#### The missing named risk assessment should be resolved

The user prompt references `.dox/2026-05-06-implementation-risk-assessment.md`, but that file is absent. The available risk material is distributed across other files: coverage gaps (`.dox/2026-05-06-agent5-coverage.md:6-58`), architecture risks (`.dox/2026-05-06-agent2-architecture.md:33-53`), security risks (`.dox/2026-05-06-agent3-security.md:12-63`), and synthesis items (`.dox/2026-05-06-queen-synthesis.md:150-164`). The implementation team should either restore the missing file or update references to the actual risk documents.

## 2. Algorithm Assessment

### Tree-sitter queries and tags

Assessment: Good foundational approach for cross-language deterministic extraction. Graphify already depends on many Tree-sitter grammars (`pyproject.toml:13-41`), and Tree-sitter's query system is explicitly designed for finding syntactic patterns without custom parser logic. Tree-sitter also defines a code-navigation tagging convention with `@definition.*`, `@reference.*`, `@name`, and optional `@doc` captures.

Better strategy than a full rewrite: add language-specific `tags.scm`-style query packs incrementally for high-value languages, then normalize captures into Graphify's existing node/edge schema. Keep the current procedural extractor for logic that queries cannot express cleanly.

Tradeoffs: Tree-sitter queries are portable and fast, but mostly syntax-level. They do not by themselves resolve imports, types, build-system semantics, monkey-patching, or dynamic dispatch. The verification report reached the same conclusion: queries are a better syntax layer, not a complete static-analysis replacement (`.dox/2026-05-05-deterministic-semantic-extraction-verification.md:602-612`).

Recommendation: Use query packs for definitions, doc adjacency, and simple references. Keep import-guided resolution and SCIP/LSP ingestion as separate semantic layers.

### Import-guided call resolution

Assessment: The proposed Python import-guided resolution is a pragmatic improvement over Graphify's current raw label matching. Current live code indexes labels, skips rationale nodes, and emits inferred call edges only when a callee label has exactly one candidate (`graphify/extract.py:4670-4719`). The runbook's import-aware Phase 4 is a sound step because it uses stronger evidence before global fallback (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1975-1991`).

Better algorithms/libraries:

- For Python, LibCST can preserve concrete syntax and provide metadata for positions, scopes, qualified names, parents, and type inference. This is more robust than a hand-written `ast` import alias parser when comments, aliases, nested scopes, relative imports, and formatting all matter.
- Jedi or Pyright-based analysis could provide richer Python resolution, but they introduce larger dependency and environment sensitivity.
- `scip-python` can externalize the problem into a standard index format if the team is willing to depend on an external indexer.

Tradeoffs: The hand-rolled resolver is cheap, deterministic, and fits the current codebase. LibCST/Pyright/Jedi produce better Python semantics but add dependencies, configuration, and version drift. External indexers produce the highest-quality references when configured correctly, but they shift complexity into tool orchestration.

Recommendation: Implement the runbook's conservative import-guided resolver first, but add an explicit "future Python resolver" note for LibCST or SCIP-Python rather than expanding hand parsing indefinitely.

### Docstring and comment tag extraction

Assessment: The proposed parser is appropriate for a first pass because it avoids new runtime dependencies and targets common Google/reST forms (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1142-1238`). It also preserves the existing `_extract_python_rationale()` behavior by enriching rather than replacing it (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:1103-1128`).

Better libraries:

- `docstring-parser` supports reST, Google, Numpydoc, and Epydoc style docstrings.
- Griffe supports Google, Numpy, Sphinx, and auto-detected docstring styles, and can integrate docstring parsing with Python object loading.
- Sphinx Napoleon is the ecosystem reference for Google/Numpy docstring conventions if the project ever wants docs-compatible interpretation.

Tradeoffs: Hand parsing keeps the dependency graph small and deterministic, but it will miss style variants quickly. Libraries increase correctness for Python docs but are Python-specific and add dependency maintenance.

Recommendation: Keep hand parsing for the initial implementation, but design `deterministic_docs.py` so a future optional parser backend can be swapped in. Add tests for unsupported styles to ensure the parser ignores them safely instead of emitting wrong facts.

### Test-to-code linking

Assessment: Static import-plus-call linking is useful, deterministic, and cheap. It is also incomplete: it misses fixtures, parametrization, monkeypatching, indirect calls, class-based tests, and test helpers. The runbook correctly uses `EXTRACTED` only when import evidence exists (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:223-247`, `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2448-2458`).

Better complementary approach: dynamic coverage contexts. Coverage.py can record dynamic contexts, commonly to answer which test ran a line. That would provide empirical test-to-code edges for Python test runs. This should not replace static linking because it requires executing tests, but it is an excellent validation or optional enrichment path.

Tradeoffs: Static linking is available without executing code and generalizes conceptually across languages. Dynamic coverage is more accurate for executed paths, but it depends on test runtime, environment, and coverage tooling.

Recommendation: Implement static linking first, then consider an optional `coverage.py` context importer later.

### SCIP, LSIF, LSP, and SemanticDB

Assessment: SCIP is the right first external-index target. The research and verification documents identify SCIP/SemanticDB/LSIF as external code-intelligence formats (`.dox/2026-05-05-deterministic-semantic-extraction-research.md:177-232`, `.dox/2026-05-05-deterministic-semantic-extraction-verification.md:246-278`). Sourcegraph's current SCIP documentation describes protobuf-schema-based indexes with documents, occurrences, symbols, and semantic roles, and lists Python among supported/recommended indexers.

Better strategy: treat SCIP as an optional import format, not a Graphify core requirement. When moving beyond the JSON skeleton, consume real SCIP protobuf or a documented CLI JSON/snapshot export. Add golden fixtures and deterministic snapshot tests.

Tradeoffs: SCIP gives strong cross-language semantics when indexers exist. It requires build/tool setup, can create large indexes, and can fail if project dependencies are missing. LSIF is older and less attractive for new work. SemanticDB is strong in Scala/JVM ecosystems but not a broad first target for Graphify.

Recommendation: Keep Phase 6 optional and unwired for the first implementation. A production SCIP importer should be a separate phase with explicit input limits and schema/version checks.

### Scope graphs and stack graphs

Assessment: Scope graphs are a strong theoretical fit for name resolution. Stack graphs in particular are designed for efficient, incremental language-specific name resolution without invoking full build tools. The research covers scope/stack graph ideas (`.dox/2026-05-05-deterministic-semantic-extraction-research.md:128-176`).

Tradeoffs: This is a deeper investment than the current runbook. GitHub's `stack-graphs` repository is archived as of 2025, so adopting it directly has maintenance risk. The concept remains useful, but it should not block the current incremental import-guided resolver.

Recommendation: Keep as research/future direction. Do not implement stack graphs in the first deterministic extraction upgrade.

### CodeQL, Joern, and code property graphs

Assessment: These tools are powerful but oversized for the current Graphify goal. The verification report correctly says full compiler/static analysis would be disproportionate for Graphify's extraction scope (`.dox/2026-05-05-deterministic-semantic-extraction-verification.md:315-339`, `.dox/2026-05-05-deterministic-semantic-extraction-verification.md:417-437`). CodeQL supports local/global data-flow and taint analysis; Joern uses code property graphs for cross-language querying. Those are analysis platforms, not lightweight extraction helpers.

Tradeoffs: They can produce high-value security/dataflow facts, but at much higher setup, runtime, and schema-mapping cost. They also risk moving Graphify from a knowledge-graph extractor into a static-analysis platform.

Recommendation: Do not implement in this runbook. Consider optional importers later for findings, call/dataflow overlays, or security-specific graph enrichments.

## 3. Research Gaps

The research is broad and mostly sound, but I would add these deterministic approaches to the backlog:

- LSP server-driven extraction. Language servers expose document symbols, definitions, references, implementations, call hierarchy, type hierarchy, semantic tokens, and diagnostics through a standardized protocol. This is a practical alternative to LSIF/SCIP dumps when a language has a mature server but no easy standalone indexer.

- Python concrete-syntax and metadata tooling. LibCST, Jedi, Pyright, and SCIP-Python deserve explicit comparison before the team expands hand-rolled Python resolution. LibCST is especially relevant because it preserves formatting/comments and exposes metadata providers for position, scope, and qualified-name information.

- Runtime-assisted test evidence. Coverage.py dynamic contexts can record which test ran which line. The research discusses test-to-code linking feasibility (`.dox/2026-05-05-deterministic-semantic-extraction-verification.md:495-536`), but should explicitly identify coverage contexts as a deterministic validation/enrichment route.

- Docstring parser ecosystem. The research covers doc comment conventions and the current Python rationale path (`.dox/2026-05-05-deterministic-semantic-extraction-verification.md:445-482`), but it should explicitly evaluate `docstring-parser`, Griffe, and Sphinx Napoleon as alternatives to maintaining a growing custom parser.

- Dependency and package graph extraction. The current plan focuses on source semantics. Manifest/lockfile facts can deterministically add package, dependency, and importability context across languages without executing code.

- Multigraph semantics and provenance. The pair-only dedup issue shows that the schema needs an explicit policy for multiple relations between the same nodes. The graph model already supports edge attributes (`graphify/build.py:90-112`), but the runbook should define whether Graphify is a semantic multigraph at the extraction dict level even though NetworkX `DiGraph` will collapse duplicate source-target edges unless modeled carefully.

- Golden graph delta tests. Because the graph report shows many inferred edges and thin communities (`graphify-out/GRAPH_REPORT.md:7-15`), implementation should include expected node/edge/relation deltas on small fixtures and at least one real-corpus smoke report.

## 4. Implementation Risks

These build on the available risk documents because the named risk-assessment file is missing.

- Relation loss through graph representation. Even if extraction emits both `calls` and `tests`, `networkx.DiGraph` stores one edge per source-target pair. `build_from_json()` calls `G.add_edge(src, tgt, **attrs)` (`graphify/build.py:90-112`), so later edges can overwrite earlier edge attributes for the same pair. The implementation must decide whether distinct semantic relations need distinct intermediate nodes, relation-specific targets, a `MultiDiGraph`, or an edge aggregation structure.

- Validator/schema drift. New file types are covered by Phase 0, but new relation names and contexts are not validated today (`graphify/validate.py:54-62`). Without tests, typoed relation names can silently ship.

- Downstream consumer drift. Agent 5 called out cluster, analyze, report, and export as unaddressed downstream consumers (`.dox/2026-05-06-agent5-coverage.md:34-45`). New node types and relations may affect community detection, god-node rankings, HTML display, and JSON consumers.

- Security and resource handling. Metadata sanitization is necessary but not sufficient for external index ingestion. Large or malicious SCIP-like JSON can create memory pressure, huge node IDs, path traversal-looking source names, and enormous metadata.

- Silent extraction failures. Resilience is useful, but too many empty-result fallbacks will make regressions look like "no facts found." Add diagnostics and tests for each intended silent path.

- Python-specific tests may create false confidence. The implementation mostly upgrades Python extraction while Graphify supports many languages through Tree-sitter grammars (`pyproject.toml:13-41`). Keep the release notes explicit about which relations are Python-only in this run.

- Cache namespace changes may not be worth first-pass risk. Current cache helper methods iterate only `ast` and `semantic` namespaces (`graphify/cache.py:148-175`, cited by the runbook at `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2772-2883`). If deterministic semantic passes are embedded into AST extraction results, avoid cache changes until there is a demonstrated stale-cache bug.

- Test coverage is too happy-path-heavy. Agent 5 rates `deterministic_docs.py` as D, `test_linking.py` as C-, and finds 20 of 36 proposed functions/classes with zero tests (`.dox/2026-05-06-agent5-coverage.md:6-58`). Add focused unit tests before full-suite confidence.

- Graph freshness must remain explicit. The graph report itself instructs `graphify update .` after code changes (`graphify-out/GRAPH_REPORT.md:12-15`). Since this review only writes `.dox/` documentation, no graph update is needed now; implementation sessions that modify code should run it.

## 5. Cross-Language Considerations

| Approach | Generalizes across languages? | Python-specific parts | Notes |
| --- | --- | --- | --- |
| Tree-sitter definitions/references/tags | Yes, where grammars and queries exist | Query files and capture mapping per grammar | Best first cross-language layer. Syntax-level only. |
| Hand-written Python doc tags | No | `ast.get_docstring()`, Google/reST parser, Python node IDs | Keep scoped to Python and do not imply coverage for other languages. |
| Doc comments via Tree-sitter `@doc` captures | Yes, with per-language queries | None conceptually | Better route for non-Python comments such as JSDoc, Rustdoc, Go comments, JavaDoc. |
| Import-guided Python calls | Mostly no | Python import syntax, aliases, relative imports, module paths | General concept applies, but each language needs its own resolver. |
| Static test-to-code linking | Conceptually yes | pytest naming/import conventions | Other languages need their own test framework and coverage conventions. |
| Coverage contexts | Conceptually yes | coverage.py/pytest contexts | Equivalent ecosystems exist elsewhere, but implementation is language/tool-specific. |
| SCIP ingestion | Yes, when indexers exist | None in Graphify except setup docs | Good cross-language optional seam, but index generation is language/build-specific. |
| LSP extraction | Yes, when servers expose capabilities | Server selection/configuration | Useful bridge where SCIP indexers are absent. |
| LibCST/Jedi/Pyright | No | Python parser/resolver ecosystem | Strong candidates for future Python-only resolver quality. |
| CodeQL/Joern/CPG | Yes at platform level | Query packs per language | Too heavy for the first extraction upgrade. |

## 6. Additional Beneficial Recommendations

- Split the implementation into two pull requests if possible: core deterministic internal extraction first, optional SCIP ingestion second. The runbook already says SCIP should not be wired into the CLI in the first pass (`.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2477-2503`, `.dox/2026-05-05-deterministic-semantic-extraction-final-implementation-runbook.md:2887-2943`).

- Add one mini-corpus integration fixture that exercises doc tags, import-guided calls, test links, validation, `build_from_json()`, export/report smoke, and no unexpected schema warnings. Unit tests are not enough for this change.

- Make the graph relation vocabulary explicit in docs. New relations like `documents_parameter`, `documents_return`, `documents_exception`, `tests`, `references_definition`, and `import_guided_call` contexts should have a short schema note so report/export consumers do not infer meanings from names alone.

- Add a "must not regress" graph-quality budget: no large increase in inferred raw `calls` edges, no doc-tag nodes becoming god nodes, no avoidable validator warnings, and no drop in extracted/validated node counts on the fixture corpus.

- Preserve the plan's conservative confidence model. The research conclusion correctly frames deterministic extraction as primary and LLMs as fallback/enrichment (`.dox/2026-05-05-deterministic-semantic-extraction-research.md:27-52`, `.dox/2026-05-05-deterministic-semantic-extraction-research.md:873-897`). Do not blur `EXTRACTED`, `INFERRED`, and `AMBIGUOUS` just to maximize edge counts.

## Primary External References Checked

- Tree-sitter query and code-navigation docs: <https://tree-sitter.github.io/tree-sitter/using-parsers/queries/index.html>, <https://tree-sitter.github.io/tree-sitter/4-code-navigation.html>
- Sourcegraph SCIP indexer docs: <https://sourcegraph.com/docs/code-navigation/writing-an-indexer>
- Python `ast.get_docstring()` docs: <https://docs.python.org/3/library/ast.html#ast.get_docstring>
- LibCST metadata docs: <https://libcst.readthedocs.io/en/latest/metadata.html>
- Coverage.py measurement contexts: <https://coverage.readthedocs.io/en/7.10.7/contexts.html>
- Language Server Protocol 3.17 specification: <https://ntaylormullen.github.io/language-server-protocol/specifications/specification-3-17/>
- CodeQL Python data-flow docs: <https://codeql.github.com/docs/codeql-language-guides/analyzing-data-flow-in-python/>
- Joern code property graph docs: <https://docs.joern.io/code-property-graph/>
- Griffe docstring parser docs: <https://mkdocstrings.github.io/griffe/reference/docstrings/>
- `docstring-parser` package page: <https://pypi.org/project/docstring-parser/>
