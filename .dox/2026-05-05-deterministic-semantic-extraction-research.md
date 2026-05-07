# Deterministic Semantic Extraction Research Record

Date: 2026-05-05

Purpose: record the research gathered for making Graphify’s semantic extraction more deterministic, faster, and less dependent on LLMs for first-pass code understanding. This document is a research record, not an implementation plan.

## 1. Local Context Anchors

Graphify already has a pipeline that can support algorithm-first semantic extraction. The documented architecture is a staged pipeline from detection to extraction to graph building, clustering, analysis, reporting, and export: `ARCHITECTURE.md:5-11`. The extraction schema already uses node/edge dictionaries and confidence labels, including `EXTRACTED`, `INFERRED`, and `AMBIGUOUS`: `ARCHITECTURE.md:32-55`.

The current graph is large enough that deterministic extraction improvements would matter at graph scale. The current graph report records 2,454 nodes, 4,014 edges, and 250 communities: `graphify-out/GRAPH_REPORT.md:7-15`.

The current deterministic extraction module is explicitly Tree-sitter based: `graphify/extract.py:1`. It defines language configuration fields for classes, functions, imports, calls, static properties, helper functions, body/name fields, call-accessor handling, import handlers, and language-specific hooks: `graphify/extract.py:144-188`.

The main AST extraction entry point already operates as a two-pass process: per-file structural extraction, then cross-file import/call enrichment: `graphify/extract.py:4231-4253`. It uses cache lookups and only extracts uncached files: `graphify/extract.py:4276-4301`. It combines per-file node/edge results and stabilizes IDs/source paths: `graphify/extract.py:4307-4333`, `graphify/extract.py:4406-4424`.

Graphify already contains deterministic cross-file reasoning, but it is narrow and language-specific. Python cross-file import resolution builds indexes and emits class-level `uses` edges: `graphify/extract.py:3420-3562`. Java cross-file import resolution builds a class-name index and emits resolved import edges: `graphify/extract.py:3565-3647`. General cross-file call resolution builds a label index, skips ambiguous candidates, and emits inferred calls only when there is a unique candidate: `graphify/extract.py:4355-4404`.

The LLM extraction path currently provides direct semantic extraction with a strict JSON schema: `graphify/llm.py:86-99`, direct backend invocation: `graphify/llm.py:214-245`, token-budget packing: `graphify/llm.py:272-309`, adaptive retry on truncation: `graphify/llm.py:312-386`, and corpus-level parallel extraction: `graphify/llm.py:389-485`.

The CLI extraction path already separates code AST extraction from semantic extraction over documents/papers/images. The command description says it runs detection, AST extraction, semantic LLM extraction, merge, build, cluster, and output: `graphify/__main__.py:1980-1986`. Code files go through AST extraction: `graphify/__main__.py:2122-2133`. Documents, papers, and images go through semantic cache and LLM extraction: `graphify/__main__.py:2134-2190`. AST and semantic fragments are merged before graph construction: `graphify/__main__.py:2191-2201`. Graph build and incremental merge happen after extraction: `graphify/__main__.py:2245-2264`.

The build layer already validates, normalizes, assembles, and deduplicates extraction results into NetworkX graphs: `graphify/build.py:48-116`, `graphify/build.py:119-153`. Incremental merge supports existing graph loading, new extraction chunks, pruning deleted sources, deduplication, and safety checks: `graphify/build.py:162-235`.

The cache layer already supports deterministic and semantic extraction caches by hashing content and relative paths: `graphify/cache.py:37-74`, loading cached extraction entries: `graphify/cache.py:77-105`, and checking/saving semantic cache fragments by `source_file`: `graphify/cache.py:178-241`.

## 2. Core Research Finding

The main research conclusion is that Graphify should treat LLM extraction as a fallback/enrichment layer, not as the primary mechanism for obvious code facts. Static-analysis and code-indexing literature already provides deterministic algorithms for extracting many semantic facts from code:

- definitions
- references
- imports
- exports
- calls
- inheritance
- implementations
- overrides
- scopes
- symbol identities
- def-use chains
- local data flow
- local control flow
- program dependence
- doc/comment tags
- test/assertion relationships

The key practical pattern is:

```text
parse source -> extract structural facts -> resolve names/scopes -> derive semantic facts -> emit graph nodes/edges -> use LLM only for ambiguity/prose/high-level interpretation
```

## 3. Tree-sitter Query-Based Extraction

### Sources

- Tree-sitter query documentation: https://tree-sitter.github.io/tree-sitter/using-parsers/queries/

### Research Summary

Tree-sitter queries provide declarative pattern matching over parse trees. They are intended for code analysis tasks that need to find specific syntactic structures without writing complex procedural traversal logic. Queries can capture tree nodes and associate captures with semantic names.

This is directly relevant because Graphify already uses Tree-sitter and already has language configuration fields for class/function/import/call extraction: `graphify/extract.py:144-188`.

### Algorithmic Method

1. Parse file with Tree-sitter.
2. Compile language-specific query patterns.
3. Run queries over the syntax tree.
4. Collect captures such as definitions, references, imports, calls, assignments, decorators, annotations, class bases, docstrings, and comments.
5. Convert captures into structured facts with source spans.
6. Emit high-confidence graph facts directly when no resolution is needed.

### Useful Capture Categories

```text
definition.module
definition.class
definition.function
definition.method
definition.field
definition.variable
reference.identifier
reference.call
reference.member
import.module
import.symbol
export.symbol
inheritance.base
decorator.name
annotation.name
assignment.left
assignment.right
docstring.node
comment.doc
```

### Research Implication

Tree-sitter query packs can reduce language-specific procedural walking code and make semantic extraction more declarative, testable, and deterministic.

## 4. Tags and Code Navigation Patterns

### Sources

- Tree-sitter query documentation: https://tree-sitter.github.io/tree-sitter/using-parsers/queries/
- LSIF specification: https://microsoft.github.io/language-server-protocol/specifications/lsif/0.6.0/specification/

### Research Summary

Code-navigation systems generally need stable ranges, definitions, references, result sets, document symbols, implementation information, and sometimes monikers. LSIF models source-code intelligence as a graph of documents, ranges, result sets, definitions, references, implementations, type definitions, hover results, semantic tokens, and project context.

Tree-sitter can provide the low-level parse captures; LSIF-style thinking provides the semantic categories needed for navigation-grade extraction.

### Algorithmic Method

1. Extract symbol ranges.
2. Classify each range as definition, declaration, reference, unknown, or other semantic token.
3. Associate ranges with stable result sets or symbol IDs.
4. Link references to definitions when resolution is available.
5. Preserve document/range information for graph provenance.

### Research Implication

Graphify’s current node/edge schema can remain, but extraction quality improves when internal facts preserve precise range-level detail before graph edge emission.

## 5. Scope Graphs and Stack Graphs

### Sources

- GitHub Stack Graphs repository: https://github.com/github/stack-graphs
- GitHub blog: “Introducing stack graphs”: https://github.blog/2021-12-09-introducing-stack-graphs/
- Scope graph/name-resolution research family: Néron, Tolmach, Visser, Wachsmuth, “A Theory of Name Resolution” and related scope-graph work.

### Research Summary

Tree-sitter tells us what syntax exists. Scope/name-resolution algorithms tell us what a reference means.

Scope graphs model scopes, definitions, references, imports, exports, and scope-to-scope reachability. Stack graphs encode name-resolution paths as graph paths whose validity depends on push/pop symbol stack behavior. This is especially relevant for languages where imports, lexical scope, class scope, and module exports determine the meaning of identifiers.

Graphify already has a narrow version of this idea in Python and Java import resolution plus unique-candidate call resolution: `graphify/extract.py:3420-3562`, `graphify/extract.py:3565-3647`, `graphify/extract.py:4355-4404`.

### Algorithmic Method

1. Build lexical scope nodes.
2. Attach definitions to scopes.
3. Attach references to scopes.
4. Add scope edges for nesting, imports, exports, module/package relationships, class inheritance, and member access.
5. Resolve references by graph search.
6. Classify results:
   - zero candidates: unresolved
   - one candidate: resolved
   - multiple candidates: ambiguous

### Useful Fact Types

```text
ScopeCreated
DefinitionInScope
ReferenceInScope
ImportIntoScope
ExportFromScope
ScopeParent
ClassScope
FunctionScope
ModuleScope
ResolvedReference
AmbiguousReference
UnresolvedReference
```

### Research Implication

Name resolution is the critical step that transforms syntactic extraction into semantic extraction. Without scope/name resolution, Graphify can identify calls and references but cannot reliably know what they point to.

## 6. SCIP: Sourcegraph Code Intelligence Protocol

### Sources

- SCIP repository: https://github.com/sourcegraph/scip

### Research Summary

SCIP is a language-agnostic protocol for indexing source code and powering code navigation features such as go-to-definition, find references, and find implementations. The repository includes a Protobuf schema and bindings. The documented ecosystem includes indexers for Java/Scala/Kotlin, TypeScript/JavaScript, Rust, C/C++, Ruby, Python, C#/.NET, Dart, and PHP.

### Algorithmic Value

SCIP itself is a format/protocol, not a single algorithm. Its practical value is that mature language indexers already perform semantic analysis and emit deterministic symbol occurrence data.

### Useful Data

```text
symbol descriptors
symbol occurrences
definition occurrences
reference occurrences
implementation links
relationships
package/language metadata
stable symbol identity
```

### Research Implication

Where SCIP indexes exist, Graphify can consume deterministic compiler/indexer-backed facts instead of asking an LLM or relying only on Tree-sitter syntax. SCIP monikers/symbols are especially valuable for deduplication and stable cross-file identity.

## 7. LSIF: Language Server Index Format

### Sources

- LSIF specification: https://microsoft.github.io/language-server-protocol/specifications/lsif/0.6.0/specification/

### Research Summary

LSIF defines a graph-shaped dump of language-server knowledge for a workspace. It models documents, ranges, result sets, definitions, declarations, references, implementations, type definitions, document symbols, semantic tokens, diagnostics, project context, events, imports/exports, monikers, and multi-project relationships.

Important LSIF ideas:

- A range captures a source span.
- A result set acts as a reusable hub for common language-server results.
- Definition/reference/implementation results are represented as graph vertices and edges.
- Monikers provide stable symbol identity across packages/projects.
- Dumps can be emitted incrementally and sharded.

### Algorithmic Value

LSIF provides a concrete graph model for code intelligence. It shows how semantic code facts can be serialized as graph data without requiring an LLM.

### Research Implication

Graphify is already a graph system, so LSIF’s model maps naturally onto Graphify’s nodes and edges. Even if Graphify does not fully adopt LSIF, LSIF validates the internal concepts Graphify should preserve: range, result set, symbol identity, definition/reference/implementation edges, and monikers.

## 8. SemanticDB

### Sources

- SemanticDB specification: https://scalameta.org/docs/semanticdb/specification.html

### Research Summary

SemanticDB is a data model for semantic information produced by compilers/tools, especially in Scala/Scalameta ecosystems. It records symbols, occurrences, ranges, signatures, synthetics, diagnostics, and semantic relationships.

### Algorithmic Value

SemanticDB is compiler-backed semantic indexing. It is useful as evidence that deterministic semantic extraction can come from language-native analyzers and not just general parsing.

### Research Implication

For JVM/Scala-style projects, Graphify can ingest SemanticDB-like outputs to obtain symbol relationships, occurrence ranges, and type/signature metadata with high confidence.

## 9. CodeQL-Style Relational Extraction and Data Flow

### Sources

- CodeQL data-flow analysis documentation: https://codeql.github.com/docs/writing-codeql-queries/about-data-flow-analysis/

### Research Summary

CodeQL models code as queryable semantic facts. Its data-flow documentation distinguishes between AST structure and data-flow graphs. AST nodes represent syntax; data-flow nodes represent runtime value-carrying elements. Edges represent how data may flow between program elements.

Important CodeQL distinctions:

- Local data flow: within a function, usually faster and more precise.
- Global data flow: across functions/properties/program boundaries, more expensive.
- Normal data flow: value-preserving flow.
- Taint tracking: derived/influenced flow where exact value is not preserved.

The documentation notes that data-flow analysis is useful for understanding how values propagate, finding insecure uses, finding resource leaks, and analyzing behavior.

### Algorithmic Method

1. Extract relational facts from syntax and symbols.
2. Build local data-flow nodes for expressions, variables, calls, parameters, and returns.
3. Add flow edges within functions.
4. Add constrained global flow only when necessary.
5. Compute reachability from sources to sinks.
6. Distinguish exact value flow from taint-like influence flow.

### Useful Relations

```text
defines(symbol, scope)
refers(reference, name)
resolved(reference, symbol)
calls(caller, callee)
assigns(lhs, rhs)
reads(expression, variable)
writes(statement, variable)
returns(function, expression)
flows(local_source, local_sink)
taints(source, sink)
```

### Research Implication

Graphify can adopt a lightweight relational-fact layer before graph emission. Local data-flow should come before global data-flow because it is cheaper, more precise, and easier to validate.

## 10. Code Property Graphs

### Sources

- Yamaguchi et al., “Modeling and Discovering Vulnerabilities with Code Property Graphs,” IEEE Symposium on Security and Privacy, 2014.
- Joern Code Property Graph documentation: https://docs.joern.io/code-property-graph/

### Research Summary

A Code Property Graph combines multiple program representations into one graph:

```text
AST: abstract syntax and containment
CFG: control flow
PDG: program dependence
DDG: data dependence
CDG: control dependence
Call graph: call relationships
Type graph: type relationships
```

CPGs were developed for vulnerability discovery, but the core idea is broadly useful: combine syntax, control flow, data flow, and call relationships into one queryable graph.

### Algorithmic Method

1. Parse source into AST.
2. Add lexical containment and declaration relationships.
3. Build control-flow edges inside functions/methods.
4. Extract definitions and uses of variables.
5. Compute data-dependence edges.
6. Compute control-dependence edges from branch/loop/exception structure.
7. Add call graph edges.
8. Add type/inheritance/implementation relationships.

### Useful Graph Relations

```text
CONTAINS
DEFINES
DECLARES
CALLS
READS
WRITES
ASSIGNS
RETURNS
THROWS
RAISES
EXTENDS
IMPLEMENTS
OVERRIDES
DECORATED_BY
GUARDS
DEPENDS_ON
FLOWS_TO
```

### Research Implication

Graphify does not need a full Joern-equivalent system immediately. The relevant research result is that combining AST + call graph + local def-use + control/data dependence produces a much richer deterministic semantic graph than AST-only extraction.

## 11. Call Graph Construction Algorithms

### Sources

Classic static-analysis literature:

- Dean, Grove, Chambers: class hierarchy analysis for object-oriented programs.
- Bacon and Sweeney: Rapid Type Analysis / fast static analysis for C++ virtual calls.
- Andersen: inclusion-based points-to analysis.
- Steensgaard: near-linear-time points-to analysis.
- Shivers: control-flow analysis for higher-order languages.

### Research Summary

Call graph construction has several precision/cost tiers. The deterministic extractor should use the highest-confidence low-cost tiers first and avoid fabricating edges for dynamic/ambiguous calls.

### Useful Tiers

```text
Tier 1: Direct function calls with lexical/import resolution.
Tier 2: Method calls where receiver type is locally known.
Tier 3: Class Hierarchy Analysis for object-oriented dispatch.
Tier 4: Rapid Type Analysis using instantiated classes.
Tier 5: Points-to analysis for dynamic receiver resolution.
Tier 6: Ambiguous dynamic calls left unresolved or escalated to review/LLM.
```

### Algorithmic Details

Direct calls:

```text
reference name -> resolve in lexical/import scope -> unique function symbol -> calls edge
```

Receiver-type method calls:

```text
x = Foo()
x.bar()
=> x has type Foo
=> resolve Foo.bar
```

Class Hierarchy Analysis:

```text
receiver static type T
candidate methods = implementations in T and subclasses
```

Rapid Type Analysis:

```text
candidate methods = CHA candidates restricted to instantiated classes
```

Points-to analysis:

```text
compute possible allocation targets for variables/fields
resolve calls from possible receiver objects
```

### Research Implication

Graphify’s existing ambiguity guard in cross-file call resolution is correct in spirit: emit deterministic calls only when resolution is unique or strongly evidenced. Call graph improvements should add better evidence rather than relaxing ambiguity checks.

## 12. Program Dependence Graphs and Program Slicing

### Sources

Classic static-analysis literature:

- Weiser, “Program Slicing,” 1981.
- Ferrante, Ottenstein, Warren, “The Program Dependence Graph and Its Use in Optimization,” 1987.
- Horwitz, Reps, Binkley: interprocedural slicing and dependence analysis.

### Research Summary

Program slicing extracts the subset of code relevant to a variable, statement, return value, call, or sink. Program dependence graphs support slicing by representing data dependence and control dependence.

### Algorithmic Method

1. Build local control-flow graph.
2. Identify variable definitions and uses.
3. Compute reaching definitions.
4. Add data-dependence edges from definitions to uses.
5. Compute control-dependence edges from branches, loops, exception handlers, and post-dominance relationships.
6. Slice backward or forward from selected points.

### Useful Graph Relations

```text
DEFINES_VALUE
USES_VALUE
VALUE_FLOWS_TO
CONTROL_DEPENDS_ON
GUARDED_BY
AFFECTS_RETURN
AFFECTS_CALL_ARGUMENT
AFFECTS_EXCEPTION_PATH
```

### Research Implication

Program slicing is valuable twice:

1. It can emit deterministic local semantic edges.
2. It can reduce LLM prompt size by sending only relevant slices around ambiguous questions instead of whole files.

## 13. Def-Use and Local Data Flow

### Sources

- CodeQL data-flow analysis documentation: https://codeql.github.com/docs/writing-codeql-queries/about-data-flow-analysis/
- Program dependence graph literature listed above.

### Research Summary

Local def-use analysis is one of the best early deterministic semantic upgrades because it is much cheaper than whole-program analysis and useful across many languages.

### Algorithmic Method

1. For each function/method, collect parameters, assignments, variable reads, variable writes, call arguments, returns, and raises/throws.
2. Track last definitions reaching each use in simple statement order.
3. Add conservative flow edges inside the function.
4. Avoid global alias-heavy reasoning initially.

### Useful Edge Examples

```text
parameter -> call argument
assignment rhs -> assigned variable
assigned variable -> return value
config variable -> constructor argument
condition variable -> guarded call
exception object -> raise statement
```

### Research Implication

Local data-flow gives Graphify valuable semantic edges with manageable complexity and good determinism.

## 14. Control Flow and Control Dependence

### Sources

- Code Property Graph literature.
- Program dependence graph literature.

### Research Summary

Control-flow analysis models possible execution order. Control-dependence analysis models which statements are guarded by conditions, loops, exception handlers, or other control constructs.

### Algorithmic Method

1. Identify basic blocks or statement-level execution units.
2. Add sequential flow edges.
3. Add branch edges from condition nodes to then/else bodies.
4. Add loop edges and back-edges.
5. Add exception edges for try/except/raise or try/catch/throw constructs.
6. Add control-dependence edges from guard conditions to controlled statements.

### Useful Relations

```text
NEXT_STATEMENT
BRANCH_TRUE
BRANCH_FALSE
LOOP_BODY
EXCEPTION_HANDLER
CONTROL_DEPENDS_ON
GUARDED_BY
```

### Research Implication

Graphify probably does not need full CFG export in user-facing graphs at first, but internal CFG/control-dependence facts can support better `GUARDS`, `VALIDATES`, `RAISES`, and `AFFECTS` semantic edges.

## 15. Type and Inheritance Analysis

### Sources

- Call graph algorithm literature.
- LSIF/SCIP/SemanticDB symbol-indexing formats.
- Code Property Graph literature.

### Research Summary

Many semantic relationships come from declared or inferred type information:

```text
class extends base
class implements interface/protocol
method overrides base method
call dispatches through receiver type
constructor assignment gives variable type
annotation gives parameter/return type
```

### Algorithmic Method

1. Extract class/interface/protocol definitions.
2. Extract inheritance/implementation clauses.
3. Extract method definitions and signatures.
4. Extract type annotations where available.
5. Extract constructor assignments.
6. Resolve base classes/interfaces via name resolution.
7. Derive `extends`, `implements`, `overrides`, and receiver-type call candidates.

### Research Implication

Type and inheritance extraction creates high-value semantic edges and improves call graph precision.

## 16. Documentation, Comments, and Structured Prose

### Sources

Practical documentation systems and conventions:

- Python docstrings
- JSDoc/TSDoc
- JavaDoc
- Rust doc comments
- Go doc comments
- Sphinx/reStructuredText
- Markdown headings, links, anchors, and code fences

### Research Summary

A large amount of semantic intent is explicit in structured comments and docs. LLMs are useful for free prose, but deterministic extraction should first capture obvious structured semantics.

### Algorithmic Method

1. Attach doc comments/docstrings to nearby definitions using syntax-tree positions.
2. Parse structured tags:
   - params
   - returns
   - throws/raises
   - deprecated
   - see/reference links
   - examples
3. Extract Markdown headings and anchors.
4. Extract Markdown links and code fences.
5. Link exact symbol mentions to known symbols after name resolution.
6. Link tests and docs to APIs by exact references before fuzzy/LLM methods.

### Useful Relations

```text
DOCUMENTS
PARAMETER_DOCUMENTED_BY
RETURNS
RAISES
DEPRECATED_BY
SEE_ALSO
EXAMPLE_OF
REFERENCES
MENTIONS_SYMBOL
```

### Research Implication

LLM work on documentation should start after deterministic parsing has extracted structure, links, and exact symbol mentions.

## 17. Test Semantics

### Sources

Practical static-analysis/testing conventions rather than a single paper:

- pytest naming conventions
- unittest/xUnit naming conventions
- Jest/Mocha test blocks
- JUnit annotations
- assertion-call recognition
- fixture/decorator/annotation extraction

### Research Summary

Tests encode executable semantic claims about behavior. Deterministic extraction can identify test definitions, assertions, fixtures, mocks, parametrization, and APIs under test.

### Algorithmic Method

1. Identify test files by path/name conventions.
2. Identify test functions/classes/blocks.
3. Extract assertions and expected exceptions.
4. Extract imports and symbols under test.
5. Link tests to target code through imports, exact symbol references, call edges, and naming conventions.
6. Mark exact links as deterministic and naming-only links as inferred/ambiguous.

### Useful Relations

```text
TESTS
ASSERTS
EXPECTS_EXCEPTION
USES_FIXTURE
MOCKS
PARAMETRIZES
COVERS_BEHAVIOR
```

### Research Implication

Test extraction can create strong semantic graph edges without LLMs and can help LLMs summarize behavior from smaller evidence sets.

## 18. Clone, Deduplication, and Similarity Algorithms

### Sources

Classic and practical algorithms:

- exact hashing
- normalized token hashing
- AST subtree hashing
- Merkle tree hashing
- SimHash
- MinHash
- winnowing fingerprints
- Jaro-Winkler / edit distance
- locality-sensitive hashing

### Research Summary

Richer extraction produces more nodes and edges. Deterministic deduplication and similarity detection are needed to prevent graph pollution.

### Algorithmic Method

1. Use exact stable IDs and monikers first.
2. Use source location and source file keys for exact identity.
3. Use normalized symbol names for near matches.
4. Use AST subtree fingerprints for duplicate definitions.
5. Use token shingling and MinHash/SimHash for clone candidates.
6. Use edit-distance/Jaro-Winkler only after stronger identity signals.
7. Use LLM only for ambiguous semantic-equivalence decisions.

### Research Implication

Dedup should remain deterministic wherever source identity, monikers, or structural hashes are available.

## 19. Probabilistic/Approximate Retrieval for Candidate Generation

### Sources

Practical information-retrieval algorithms:

- inverted indexes
- trigram indexes
- BM25
- MinHash
- SimHash
- locality-sensitive hashing
- embedding search as candidate generation only

### Research Summary

Approximate algorithms are useful for candidate generation but should not directly assert graph truth. They can find possible matches for unresolved symbols, docs, tests, or duplicate nodes.

### Algorithmic Method

1. Generate candidate pairs with cheap indexes.
2. Filter with deterministic constraints.
3. Mark unresolved pairs as ambiguous.
4. Send only hard cases to LLM/human review.

### Research Implication

Approximate similarity belongs before expensive review, but after exact deterministic matching.

## 20. Incremental Extraction and Caching

### Sources

Local Graphify cache/pipeline behavior: `graphify/cache.py:37-74`, `graphify/cache.py:77-105`, `graphify/cache.py:178-241`, `graphify/extract.py:4276-4301`.

### Research Summary

Algorithmic extraction should be incremental. Graphify already hashes file contents and relative paths and separates AST and semantic cache namespaces.

### Algorithmic Method

1. Hash file content and relative path.
2. Cache per-file parse/extraction/fact results.
3. Recompute only changed files.
4. Re-run global resolution only over changed facts plus affected dependency neighborhoods.
5. Keep deterministic facts separate from LLM enrichment cache.

### Research Implication

Deterministic semantic extraction can be fast if per-file fact extraction is cached and global resolution is incremental.

## 21. Confidence Model Research Implications

### Local Anchor

Graphify’s schema already supports confidence labels: `ARCHITECTURE.md:49-55`.

### Research Summary

Static-analysis outputs should not all be treated equally. Confidence should distinguish source evidence and derivation method.

### Proposed Evidence Categories

```text
EXTRACTED_PARSE: directly captured from syntax
EXTRACTED_INDEX: emitted by SCIP/LSIF/SemanticDB/language indexer
EXTRACTED_RESOLVED: deterministically resolved from scope/name graph
INFERRED_LOCAL_FLOW: derived by local data-flow/control-flow analysis
INFERRED_GLOBAL_FLOW: derived by constrained global analysis
AMBIGUOUS_CANDIDATES: multiple unresolved candidates
LLM_INFERRED: LLM-derived relationship
LLM_ENRICHED: label/summary added by LLM to deterministic fact
```

### Research Implication

Graphify can preserve the current public confidence labels while recording richer internal provenance. This improves debugging and prevents LLM output from being confused with deterministic facts.

## 22. LLM Role After Algorithmic Extraction

### Local Anchor

The current LLM extraction prompt asks the model to emit graph fragments directly: `graphify/llm.py:86-99`.

### Research Summary

The research direction is not “remove LLMs.” It is “reserve LLMs for what deterministic algorithms cannot do cheaply or reliably.”

### LLMs Should Handle

```text
architectural role labeling
concept extraction from free prose
cluster/community naming
ambiguous relationship adjudication
summarization of deterministic facts
high-level rationale extraction
surprising connection explanation
semantic labeling of docs/papers/images
```

### LLMs Should Not Be Primary For

```text
imports
definitions
references
direct calls
source locations
class inheritance
structured doc tags
symbol identity
simple local data flow
test assertions
```

### Research Implication

The LLM prompt should receive compact deterministic context and unresolved ambiguity sets rather than raw source files whenever possible.

## 23. External Research Bibliography

### Tree-sitter

- Tree-sitter Queries Documentation. Tree-sitter. https://tree-sitter.github.io/tree-sitter/using-parsers/queries/

### Stack/Scope Graphs

- GitHub Stack Graphs repository. https://github.com/github/stack-graphs
- GitHub Blog, “Introducing stack graphs.” https://github.blog/2021-12-09-introducing-stack-graphs/
- Néron, Tolmach, Visser, Wachsmuth. “A Theory of Name Resolution.” Scope graph research family.

### Code Indexing Formats

- SCIP Code Intelligence Protocol. Sourcegraph / scip-code. https://github.com/sourcegraph/scip
- LSIF Specification 0.6.0. Microsoft Language Server Protocol. https://microsoft.github.io/language-server-protocol/specifications/lsif/0.6.0/specification/
- SemanticDB Specification. Scalameta. https://scalameta.org/docs/semanticdb/specification.html

### CodeQL / Relational Static Analysis

- CodeQL Documentation, “About data flow analysis.” https://codeql.github.com/docs/writing-codeql-queries/about-data-flow-analysis/

### Code Property Graphs

- Yamaguchi et al. “Modeling and Discovering Vulnerabilities with Code Property Graphs.” IEEE Symposium on Security and Privacy, 2014.
- Joern Code Property Graph Documentation. https://docs.joern.io/code-property-graph/

### Program Slicing and Dependence

- Weiser, Mark. “Program Slicing.” 1981.
- Ferrante, Ottenstein, Warren. “The Program Dependence Graph and Its Use in Optimization.” 1987.
- Horwitz, Reps, Binkley. Interprocedural slicing and dependence-analysis literature.

### Call Graph and Points-To Analysis

- Dean, Grove, Chambers. Class Hierarchy Analysis.
- Bacon and Sweeney. Rapid Type Analysis.
- Andersen. Inclusion-based points-to analysis.
- Steensgaard. Near-linear-time points-to analysis.
- Shivers. Control-flow analysis for higher-order languages.

### Similarity / Clone Detection

- SimHash.
- MinHash.
- Winnowing fingerprints.
- AST subtree hashing / Merkle hashing.
- Token shingling and locality-sensitive hashing.
- Jaro-Winkler / edit-distance similarity.

## 24. Research-Only Synthesis

The strongest research-backed conclusion is that Graphify should not rely on LLMs to discover routine code facts. The mature algorithmic ecosystem already covers most of the first-pass semantic extraction problem:

```text
Tree-sitter queries -> syntax-level captures
Scope/stack graphs -> name resolution
SCIP/LSIF/SemanticDB -> external compiler/indexer-backed facts
CodeQL-style facts -> relational derivation and data flow
CPG -> combined syntax/call/control/data graph model
Call-graph algorithms -> deterministic call resolution tiers
PDG/slicing -> dependency and prompt-reduction context
Doc/test extraction -> explicit semantic claims from comments and tests
Similarity algorithms -> deterministic dedup/candidate generation
```

For Graphify specifically, this research aligns with the existing extraction architecture because the project already has:

- Tree-sitter-based deterministic extraction: `graphify/extract.py:1`
- Language configuration hooks: `graphify/extract.py:144-188`
- Per-file cache and extraction orchestration: `graphify/extract.py:4231-4301`
- Cross-file deterministic enrichment: `graphify/extract.py:3420-3562`, `graphify/extract.py:3565-3647`, `graphify/extract.py:4355-4404`
- Schema-compatible graph building: `graphify/build.py:48-153`
- Separate LLM semantic extraction path: `graphify/llm.py:86-99`, `graphify/llm.py:389-485`
- CLI seams separating AST extraction, semantic extraction, merging, and graph build: `graphify/__main__.py:2122-2264`

The research record supports an algorithm-first extraction strategy, but this document intentionally stops at research capture rather than implementation design.
