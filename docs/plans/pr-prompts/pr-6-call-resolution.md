# PR 6: Call Resolution Engine

**Phase:** 9
**Stream:** B (Code Intelligence)
**Estimate:** 3-4 weeks
**Depends on:** Phase 8 (typed code schema must exist)

## What to Build

This is the highest-impact phase. Enables "what calls X?" answering.

### 1. Import Resolution (`graphify/imports.py` — NEW)

```python
from enum import Enum
from pathlib import Path
from dataclasses import dataclass

class ImportSemantics(Enum):
    NAMED = "named"              # import { Foo } from './foo'
    WILDCARD_LEAF = "wildcard_leaf"   # from foo import Bar
    WILDCARD_TRANSITIVE = "wildcard_transitive"  # from foo import *
    NAMESPACE = "namespace"      # import foo

@dataclass
class ImportTarget:
    module_path: str             # Resolved file path or module name
    symbol: str | None = None    # Specific symbol (for named imports)
    is_external: bool = False    # External package, not in project
    confidence: str = "EXTRACTED"

def resolve_import(target: str, from_file: Path, all_files: list[Path],
                   semantics: ImportSemantics, language: str) -> ImportTarget | None:
    """Resolve an import to a specific file/symbol.
    
    Dispatches to language-specific resolvers based on language:
    - Python: .py files, __init__.py, relative imports
    - TypeScript/JavaScript: .ts/.tsx/.js resolution, tsconfig paths
    - Go: go module resolution, internal packages
    - Java: package directory structure
    
    Returns ImportTarget or None (for external deps)."""

# Language-specific resolvers (in same file — use if/elif dispatch):
def _resolve_python_import(target, from_file, all_files, semantics) -> ImportTarget | None: ...
def _resolve_typescript_import(target, from_file, all_files, semantics) -> ImportTarget | None: ...
def _resolve_go_import(target, from_file, all_files, semantics) -> ImportTarget | None: ...
def _resolve_java_import(target, from_file, all_files, semantics) -> ImportTarget | None: ...
```

### 2. Call Extraction (`graphify/call_extractors.py` — NEW)

```python
"""Per-language call extraction from tree-sitter AST."""

@dataclass
class ExtractedCallSite:
    name: str                    # Called function/method name
    receiver: str | None = None  # self, this, or explicit receiver
    arity: int = 0               # Number of arguments passed
    line: int = 0                # Source line number
    in_class: str | None = None  # Enclosing class name
    is_dynamic: bool = False     # True if receiver type uncertain
    full_call_text: str = ""     # Raw call text for display

def extract_calls_from_ast(parsed_file, language: str, source: bytes) -> list[ExtractedCallSite]:
    """Extract all call sites from a parsed tree-sitter file.
    Dispatches to language-specific extraction based on language.
    
    Supported: python, typescript/javascript, go, java (4 languages).
    Returns list of ExtractedCallSite."""

# Language-specific extractors (in same file):
def _extract_calls_python(node, source) -> list[ExtractedCallSite]: ...
def _extract_calls_typescript(node, source) -> list[ExtractedCallSite]: ...
def _extract_calls_go(node, source) -> list[ExtractedCallSite]: ...
def _extract_calls_java(node, source) -> list[ExtractedCallSite]: ...
```

### 3. Receiver Inference (`graphify/receiver.py` — NEW)

```python
def infer_receiver(call: ExtractedCallSite, enclosing_class: str | None,
                   graph_nodes: dict[str, dict]) -> str | None:
    """Infer actual receiver type for a call.
    
    Rules:
    - self.method() → enclosing_class (look up in graph)
    - this.method() → enclosing_class  
    - cls.method() → enclosing_class (Python classmethod)
    - super().method() → parent class via extends edges
    - Constructor: MyClass() → MyClass (name matches class)
    
    Returns resolved receiver node ID or None."""

def is_constructor_call(name: str, graph_nodes: dict[str, dict]) -> str | None:
    """Check if a call is a constructor call. Returns class node ID or None."""
```

### 4. MRO Walk (`graphify/mro.py` — NEW)

```python
from enum import Enum

class MROStrategy(Enum):
    FIRST_WINS = "first_wins"    # Java, C#, C++, TS, Go
    C3 = "c3"                    # Python
    RUBY_MIXIN = "ruby_mixin"    # Ruby
    NONE = "none"                # Single inheritance

MRO_FOR_LANGUAGE = {
    "python": MROStrategy.C3,
    "typescript": MROStrategy.FIRST_WINS,
    "javascript": MROStrategy.FIRST_WINS,
    "go": MROStrategy.NONE,       # Go has no inheritance, only interfaces
    "java": MROStrategy.FIRST_WINS,
    "rust": MROStrategy.NONE,
    "csharp": MROStrategy.FIRST_WINS,
    "cpp": MROStrategy.FIRST_WINS,
}

def resolve_method_by_mro(target_method: str, class_node_id: str, G,
                          language: str) -> str | None:
    """Walk MRO to find which class actually provides target_method.
    Returns the class node ID that defines the method.
    
    Strategy per language:
    - first_wins: DFS on extends edges, first match wins
    - c3: Python C3 linearization (simplified: DFS + dedup)
    - none: only check the exact class"""
    
def get_parent_classes(G, class_node_id: str) -> list[str]:
    """Return parent class node IDs via extends/implements edges."""
    
def build_class_hierarchy(G) -> dict[str, list[str]]:
    """Build parent→children lookup from extends/implements edges."""
```

### 5. Cross-File Resolution (`graphify/cross_file.py` — NEW)

```python
def resolve_call_chain_across_files(
    calls: list[ExtractedCallSite],
    current_file: Path,
    all_files: list[Path],
    G,
) -> list[dict]:
    """Resolve call targets that cross file boundaries.
    
    Steps:
    1. For each call, check local file first (same-file functions)
    2. If not local, resolve import to target file
    3. Look up target function/method in target file's graph nodes
    4. If method call, walk MRO to find actual definition
    5. Return list of resolved calls with confidence scores."""
```

### 6. Call Resolution DAG (`graphify/call_dag.py` — NEW)

```python
@dataclass
class ResolvedCall:
    caller_id: str               # Node ID of the calling function
    callee_id: str               # Node ID of the called function
    call_site_line: int          # Source line number
    edge_type: str               # "calls"
    confidence: str              # EXTRACTED or INFERRED
    resolution_steps: list[str]  # Steps taken: ["extract", "infer_receiver", "resolve"]

def resolve_call_graph(files: list[Path], G) -> tuple[list[ResolvedCall], int]:
    """6-stage call resolution DAG.
    
    1. extract — extract_calls_from_ast() on each file
    2. infer-receiver — infer_receiver() for self/this/super calls
    3. select-dispatch — static dispatch by default, virtual where needed
    4. resolve-target — import resolution + cross-file lookup
    5. resolve-method — MRO walk for method calls
    6. emit-edge — create call edges with confidence scores
    
    Returns (resolved_calls, unresolved_count)."""

def emit_call_edges(resolved: list[ResolvedCall]) -> list[dict]:
    """Convert ResolvedCall list to extraction-compatible edge dicts."""
```

### 7. New MCP Tools (`graphify/serve.py` — EXTEND)

```python
"""
context({name: "validateUser"}) →
  symbol: {kind, file, line, signature, visibility}
  incoming: {calls: [...], imports: [...]}
  outgoing: {calls: [...]}
  processes: [{name, step_index, total_steps}]

impact({target: "UserService", direction: "upstream", minConfidence: 0.8}) →
  target: {kind, file}
  upstream: {
    depth_1: [{symbol, relation, confidence, file}],
    depth_2: [...], ...
  }
  downstream: { depth_1: [...], depth_2: [...], ... }
  summary: {total_affected, risk_level}
"""
```

Add two new MCP tool definitions:
- `context(name)` — 360-degree symbol view using typed schema + call edges
- `impact(target, direction, minConfidence)` — blast radius analysis

### 8. Tests

**`tests/test_imports.py` (NEW, 6+ tests):**
```python
def test_resolve_python_import_named():
def test_resolve_python_import_relative():
def test_resolve_typescript_import():
def test_resolve_java_import():
def test_resolve_external_import():
def test_import_semantics_enum():
```

**`tests/test_receiver.py` (NEW, 5+ tests):**
```python
def test_infer_self_receiver():
def test_infer_this_receiver():
def test_infer_super_receiver():
def test_is_constructor_call():
def test_infer_without_class_context():
```

**`tests/test_mro.py` (NEW, 6+ tests):**
```python
def test_mro_first_wins():
def test_mro_c3_simple():
def test_get_parent_classes():
def test_mro_no_inheritance():
def test_resolve_method_inherited():
def test_mro_for_language_map():
```

**`tests/test_call_resolution_fixtures.py` (NEW, 5+ tests):**
Uses fixture repos under `tests/fixtures/call_resolution/`:
```python
def test_resolve_python_calls():
    """Given a fixture Python project with known call graph, verify resolution."""
def test_resolve_typescript_calls():
def test_resolve_cross_file_calls():
def test_resolve_method_chains():
def test_unresolved_count():
```

## Files Changed/Created

| File | Action | Purpose |
|------|--------|---------|
| `graphify/imports.py` | **New** | Import resolution with language-specific strategies |
| `graphify/call_extractors.py` | **New** | Per-language call site extraction from AST |
| `graphify/receiver.py` | **New** | self/this/super receiver inference |
| `graphify/mro.py` | **New** | Method resolution order per language |
| `graphify/cross_file.py` | **New** | Cross-file type propagation |
| `graphify/call_dag.py` | **New** | 6-stage call resolution DAG |
| `graphify/serve.py` | **Extend** | context() and impact() MCP tools |
| `tests/test_imports.py` | **New** | |
| `tests/test_receiver.py` | **New** | |
| `tests/test_mro.py` | **New** | |
| `tests/test_call_resolution_fixtures.py` | **New** | |
| `tests/fixtures/call_resolution/` | **New** | Fixture repos |

## Compatibility
- All existing MCP tools unchanged
- New tools (context, impact) are additive
- No changes to graph.json format
- No changes to existing extraction pipeline

## Verification
```bash
pytest tests/test_imports.py tests/test_receiver.py tests/test_mro.py tests/test_call_resolution_fixtures.py -q
pytest tests/ -q  # full suite
```

### Call Resolution Benchmarks

Add to `graphify/benchmark.py`:

```python
def benchmark_call_resolution(G, num_files: int = 100, seed: int = 42) -> dict:
    """Measure call resolution throughput and coverage.
    Selects num_files random code files, runs resolve_call_graph on each.
    Returns {total_calls, resolved, unresolved, resolution_pct, avg_time_ms, p95_time_ms}."""

def benchmark_resolution_accuracy(G, fixture_dir: str = "tests/fixtures/call_resolution") -> dict:
    """Measure call resolution accuracy against known ground truth.
    Loads fixture repos with pre-annotated expected call graph.
    Compares: resolved edges vs expected edges.
    Returns {precision: |correct|/|resolved|, recall: |correct|/|expected|,
            f1, total_resolved, total_expected, correct, false_positives, false_negatives}."""

def benchmark_call_resolution_scale(G, node_counts: list[int] = [50000, 100000, 500000, 1000000]) -> list[dict]:
    """Run benchmark_call_resolution at different graph sizes (using subgraphs).
    Returns list of resolution coverage dicts, one per size."""
```

Run after implementation:
```bash
# Throughput benchmark
python -c "
from graphify.benchmark import benchmark_call_resolution
from graphify.build import build
G = build('.')
print(benchmark_call_resolution(G, num_files=50))
"

# Accuracy benchmark (requires test fixtures)
python -c "
from graphify.benchmark import benchmark_resolution_accuracy
from graphify.build import build
G = build('.')
print(benchmark_resolution_accuracy(G))
"
```
---

### Commit

```bash
git add -A && git commit -m "feat(phase-9): call resolution engine (6-stage DAG + MRO walk)"
```

---

## Code Review Checklist

Before merging this PR, verify:
- [ ] All tests pass: `pytest tests/ -q`
- [ ] `benchmark_resolution_accuracy()` shows precision ≥ 0.85, recall ≥ 0.80 on test fixtures
- [ ] `benchmark_call_resolution()` runs on real codebase and reports resolution_pct
- [ ] Import resolution handles all 4 languages (Python, TS/JS, Go, Java)
- [ ] MRO walk correctly resolves inherited methods (test fixture proves it)
- [ ] New MCP tools `context()` and `impact()` return valid responses
- [ ] No breaking changes to existing MCP tools
- [ ] Test fixtures under `tests/fixtures/call_resolution/` are small and self-contained
- [ ] At least 1 other developer reviewed

---

## CI Verification
```bash
# Run automated verification for this PR:
bash docs/plans/verify-pr.sh 6

# Expected checks:
# - Full test suite passes
# - tests/test_imports.py + tests/test_receiver.py pass
# - Resolution accuracy: precision >= 0.85, recall >= 0.80
# - benchmark snapshot archived to graphify-out/benchmarks/phase-6-benchmark.json

# After passing, update PROGRESS.md:
# - Set PR 6 status to ✅ Done
# - Fill commit hash: git log -1 --format="%H"
# - Fill accuracy benchmark results in Accuracy Benchmarks table
```

---

## Prompt (paste into AI coding agent)

```
You are implementing Phase 9 of the Graphify fork enhancement plan — the Call Resolution Engine.

Repository: ~/graphify
Branch: feat/phase-9-call-resolution

This is the single highest-impact phase. It enables answering "what calls X?" by resolving call targets across files using tree-sitter AST analysis and MRO walks.

TASK: Build the call resolution pipeline — 6 modules + 2 new MCP tools.

## Module 1: Import Resolution (graphify/imports.py)

Create graphify/imports.py. Define ImportSemantics enum, ImportTarget dataclass.

1. resolve_import(target, from_file, all_files, semantics, language) → ImportTarget | None:
   - Dispatch to _resolve_python_import, _resolve_typescript_import, _resolve_go_import, _resolve_java_import based on language parameter.
   - Python: handle relative imports (.foo, ..bar), absolute imports, __init__.py.
   - TypeScript/JS: handle relative paths, tsconfig paths, .ts/.js resolution.
   - Go: handle module imports, internal package paths.
   - Java: dotted package names.
   - Return None for external dependencies (stdlib, node_modules, etc.).

Each language resolver is a private function in the same file.

## Module 2: Call Extraction (graphify/call_extractors.py)

2. ExtractedCallSite dataclass: name, receiver, arity, line, in_class, is_dynamic, full_call_text.

3. extract_calls_from_ast(parsed_file, language, source: bytes) → list[ExtractedCallSite]:
   - Dispatch to language-specific extractors for python, typescript/javascript, go, java.
   - Use existing tree-sitter LanguageConfig from extract.py to understand tree structure.
   - For each call node: extract name, arity (argument count), receiver if member call.
   - Track enclosing class context while walking the tree.
   - Each language extractor is a private _extract_calls_{lang} function.

## Module 3: Receiver Inference (graphify/receiver.py)

4. infer_receiver(call, enclosing_class, graph_nodes) → str | None:
   - If call has explicit receiver "self" or "this" → enclosing_class.
   - If "cls" → enclosing_class (Python classmethod).
   - If "super()" → parent class via extends edges in G.
   - For method calls without receiver (bare function calls) → no inference needed.

5. is_constructor_call(name, graph_nodes) → str | None:
   - Check if name matches a known class name. Return class node ID if found.

## Module 4: MRO Walk (graphify/mro.py)

6. MROStrategy enum: FIRST_WINS, C3, RUBY_MIXIN, NONE.

7. MRO_FOR_LANGUAGE dict: language → MROStrategy.

8. get_parent_classes(G, class_node_id) → list[str]: Return parent class node IDs via extends/implements edges. Use RELATION_MAP from code_schema.py.

9. resolve_method_by_mro(target_method, class_node_id, G, language) → str | None:
   - first_wins: DFS on extends edges. First class that has a method node with matching label wins.
   - c3: Simplified C3 — DFS with dedup, merge order.
   - none: Only check the exact class.
   - Look for method nodes with label = f".{target_method}()" in each class.

## Module 5: Cross-File Resolution (graphify/cross_file.py)

10. resolve_call_chain_across_files(calls, current_file, all_files, G) → list[dict]:
    - For each extracted call site:
      a. Check if the called symbol exists in the current file's graph nodes. If yes → resolved (EXTRACTED confidence).
      b. If not, find which import brings in this symbol, resolve to target file.
      c. Look up the symbol in target file's nodes.
      d. If method call with MRO, walk MRO to find correct definition.
      e. Return resolved call with confidence (EXTRACTED for direct, INFERRED for MRO-resolved).

## Module 6: Call Resolution DAG (graphify/call_dag.py)

11. ResolvedCall dataclass: caller_id, callee_id, call_site_line, edge_type="calls", confidence, resolution_steps.

12. resolve_call_graph(files, G) → tuple[list[ResolvedCall], int]:
    - Orchestrate the 6 stages: extract → infer-receiver → select-dispatch → resolve-target → resolve-method → emit-edge.
    - For each file in files: parse with tree-sitter, extract calls, infer receivers, resolve across files.
    - Return resolved calls and count of unresolved ones.

13. emit_call_edges(resolved) → list[dict]: Convert to extraction-compatible edge dicts for build.py.

## Module 7: New MCP Tools (extend graphify/serve.py)

14. Add context(name) MCP tool:
    - Input: name (string). Output: symbol {kind, file, line, signature}, incoming calls, outgoing calls, process membership.
    - Implementation: use _find_node to locate node, then query CALLS edges (incoming and outgoing) using edge relation index.

15. Add impact(target, direction, minConfidence) MCP tool:
    - Input: target, direction ("upstream"/"downstream"/"both"), minConfidence (float 0-1).
    - Implementation: BFS along CALLS edges in specified direction, grouping by depth. Filter by confidence_score.
    - Risk level: HIGH if >20 affected, MEDIUM if >5, LOW otherwise.

## Module 8: Tests

16. tests/test_imports.py: 6 tests
17. tests/test_receiver.py: 5 tests  
18. tests/test_mro.py: 6 tests
19. tests/test_call_resolution_fixtures.py: Need test fixture repos. Create a minimal test fixture at tests/fixtures/call_resolution/ with a few files (1 Python, 1 TS) that have known call relations. Test that the resolution engine correctly identifies call chains.

MATCH EXISTING CODE STYLE. Use existing patterns. All new things are additive — zero breaking changes to existing code.

For the call extraction, you can REUSE tree-sitter parsing logic from extract.py (LanguageConfig, etc.) rather than reimplementing it.

RUN `pytest tests/ -q` after implementation.

ADD benchmark_call_resolution(G) and benchmark_call_resolution_scale(G) to graphify/benchmark.py. Measure resolution throughput and coverage at 50K-1M node scales.

ADD benchmark_resolution_accuracy(G, fixture_dir) to graphify/benchmark.py. Compare resolved call edges against known ground truth from test fixtures. Report precision/recall/f1.

RUN `git add -A && git commit -m "feat(phase-9): call resolution engine (6-stage DAG + MRO walk)"`
```
