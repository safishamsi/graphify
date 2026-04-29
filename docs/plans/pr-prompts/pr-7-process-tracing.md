# PR 7: Process Tracing

**Phase:** 10
**Stream:** B (Code Intelligence)
**Estimate:** 2-3 weeks
**Depends on:** Phase 9 (call resolution must be complete — needs CALLS edges)

## What to Build

### 1. Entry Point Detection (`graphify/processes.py` — NEW)

```python
@dataclass
class EntryPoint:
    node_id: str
    label: str
    kind: str                # route_handler, cli_main, test, middleware, cron, library_export
    route: str | None = None
    method: str | None = None  # HTTP method
    score: float = 0.0
    file: str = ""

@dataclass
class ProcessStep:
    node_id: str
    step_index: int
    call_chain: list[str]
    file: str
    line: str
    is_branching: bool = False

@dataclass
class Process:
    id: str
    name: str
    entry_point: EntryPoint
    steps: list[ProcessStep]
    confidence: float
    total_calls: int
    unique_files: int

def detect_entry_points(G) -> list[EntryPoint]:
    """Framework-aware entry point detection.
    
    Scans all nodes for:
    - Route handlers: nodes with HANDLES_ROUTE edges, route path in metadata
    - CLI mains: nodes named "main" or "__main__", functions named "main()"
    - Tests: functions starting with "test_", classes ending with "Test"
    - Middleware: nodes named "*Middleware", "*middleware"
    - Cron jobs: nodes named "*cron*", "*schedule*"
    - Library exports: high-degree nodes that are exported
    
    Each gets scored: route_handler(10), cli_main(7), test(3), middleware(5), cron(6), library_export(1)"""
    
def trace_process(G, entry: EntryPoint, max_depth: int = 20) -> Process:
    """Trace execution from entry point following CALLS edges.
    
    BFS from entry node, following only CALLS edges.
    Deduplicate: visited nodes tracked, cycles detected and noted.
    Each step records its call chain (path from entry to this node).
    Mark steps as 'branching' if they call >1 different target."""
    
def build_processes(G) -> list[Process]:
    """Full process construction pipeline.
    
    1. detect_entry_points(G) → candidates
    2. score + sort candidates
    3. trace_process() for each top-N entry point
    4. Return list of Process objects"""

def cluster_processes(processes: list[Process]) -> list[list[Process]]:
    """Group overlapping processes by shared call paths.
    Deduplicate near-identical traces (>90% symbol overlap).
    Returns list of process clusters."""

def write_processes_json(processes: list[Process], output_path: str = "graphify-out/processes.json") -> None:
    """Write process traces to JSON file."""
```

### 2. Process Integration with Build + Cluster (`build.py`, `cluster.py` — EXTEND)

**In `graphify/build.py`:**
```python
def build_from_json(extraction: dict, *, directed: bool = False,
                    build_indexes: bool = True,
                    materialize: list[str] | None = None,
                    trace_processes: bool = False) -> nx.Graph:
    """If trace_processes=True, run process construction after graph built."""
    # ... existing build ...
    if trace_processes:
        from .processes import build_processes, write_processes_json
        processes = build_processes(G)
        write_processes_json(processes)
        # Add STEP_IN_PROCESS edges
        for proc in processes:
            for i in range(len(proc.steps) - 1):
                G.add_edge(proc.steps[i].node_id, proc.steps[i+1].node_id,
                          relation="step_in_process", confidence="INFERRED",
                          process_id=proc.id, step_index=i)
    return G
```

**In `graphify/cluster.py`:**
Use process membership as a signal for community detection:
```python
def cluster_with_processes(G, processes: list[Process]) -> dict[int, list[str]]:
    """Community detection that uses process membership as a cohesion signal.
    Nodes that appear together in the same process trace are more likely
    to belong to the same functional community."""
```

### 3. Detect Changes Tool (`graphify/processes.py` — EXTEND)

```python
def detect_changes(G, processes: list[Process],
                   changed_files: list[str] | None = None) -> dict:
    """Given a graph and process traces, detect impact of changes.
    
    If changed_files not provided, detects files changed since last build
    (via graph snapshot comparison).
    
    Returns:
    {
      summary: {changed_count, affected_count, changed_files, risk_level},
      changed_symbols: [{name, kind, file, changed_lines}],
      affected_processes: [{name, step_count, affected_steps}],
      recommendations: [{action, reason}]
    }"""
    
def assess_risk(affected_count: int, affected_processes: int) -> str:
    """Risk assessment: LOW (<5 affected), MEDIUM (5-20), HIGH (>20)."""
```

### 4. New MCP Tool (`graphify/serve.py` — EXTEND)

```python
# Add detect_changes tool
"""
detect_changes({scope: "all"}) →
  summary: {changed_count, affected_count, changed_files, risk_level}
  changed_symbols: [{name, kind, file, changed_lines}]
  affected_processes: [{name, step_count, affected_steps}]
  recommendations: [{action, reason}]
"""
```

### 5. Update existing MCP tools

**context tool (Phase 9):** Add process membership data:
```
processes: [{name, step_index, total_steps}]
```

**impact tool (Phase 9):** Add process-level impact summary:
```
summary: {total_affected, risk_level, affected_processes: [...]}
```

### 6. Tests

**`tests/test_processes.py` (NEW, 8+ tests):**
```python
from graphify.processes import (
    EntryPoint, Process, ProcessStep,
    detect_entry_points, trace_process, build_processes,
    cluster_processes, detect_changes, assess_risk,
)

def test_detect_entry_points_finds_routes():
    """Graph with route handler nodes → detected as route_handler kind."""
    
def test_detect_entry_points_finds_cli_main():
    """Graph with main() function → detected as cli_main kind."""
    
def test_detect_entry_points_finds_tests():
    """Graph with test_ functions → detected as test kind."""
    
def test_trace_process_follows_calls():
    """Trace from entry follows CALLS edges to build process."""
    
def test_trace_process_handles_cycles():
    """Cycle in call graph → detected and noted, doesn't infinite loop."""
    
def test_trace_process_respects_max_depth():
    """Process trace stops at max_depth."""
    
def test_build_processes_returns_processes():
    """Integration: build_processes returns non-empty list."""
    
def test_cluster_processes_deduplicates():
    """Near-identical traces (>90% overlap) → grouped."""
    
def test_assess_risk_levels():
    """Risk assessment returns correct levels."""
```

**`tests/test_serve.py` (EXTEND):**
```python
def test_detect_changes_tool_response():
    """detect_changes tool returns correct format."""
```

## Files Changed/Created

| File | Action | Purpose |
|------|--------|---------|
| `graphify/processes.py` | **New** | Entry point detection, process tracing, change impact |
| `graphify/build.py` | **Extend** | trace_processes parameter, write processes.json |
| `graphify/cluster.py` | **Extend** | Process-informed community detection |
| `graphify/serve.py` | **Extend** | detect_changes MCP tool, update context/impact tools |
| `tests/test_processes.py` | **New** | Process tracing tests |

## Compatibility
- All existing MCP tools unchanged
- trace_processes=False by default (no change to existing pipeline)
- processes.json is new output file, doesn't change graph.json
- STEP_IN_PROCESS edges are additive (new relation type)

## Verification
```bash
pytest tests/test_processes.py -q
pytest tests/test_serve.py -q
pytest tests/ -q  # full suite
```

### Process Tracing Benchmarks

Add to `graphify/benchmark.py`:

```python
def benchmark_process_tracing(G, max_processes: int = 50) -> dict:
    """Measure process tracing throughput.
    Returns {entry_points_found, processes_traced, avg_depth, max_depth,
            avg_trace_ms, p95_trace_ms, total_steps, unique_files_covered}."""

def benchmark_change_impact(G, num_changes: int = 10, seed: int = 42) -> dict:
    """Measure change impact analysis speed.
    Randomly selects num_changes files, runs detect_changes().
    Returns {avg_response_ms, avg_affected_nodes, avg_affected_processes}."""
```

Run after implementation:
```bash
python -c "
from graphify.processes import build_processes, detect_changes
from graphify.benchmark import benchmark_process_tracing
print(benchmark_process_tracing(G))
"
```

### Commit

```bash
git add -A && git commit -m "feat(phase-10): process tracing + change impact analysis"
```

---

## Code Review Checklist

Before merging this PR, verify:
- [ ] All tests pass: `pytest tests/ -q`
- [ ] Process tracing follows CALLS edges only (not other relation types)
- [ ] Entry point detection finds all known handler types (route, CLI, test, middleware, cron)
- [ ] Change impact analysis correctly identifies affected processes
- [ ] `benchmark_process_tracing()` returns valid throughput numbers
- [ ] Processes JSON written to `graphify-out/processes.json`
- [ ] No breaking changes to existing MCP tools
- [ ] Cluster integration falls back gracefully when no processes provided
- [ ] At least 1 other developer reviewed

---

## CI Verification
```bash
# Run automated verification for this PR:
bash docs/plans/verify-pr.sh 7

# Expected checks:
# - Full test suite passes
# - tests/test_processes.py + tests/test_serve.py pass
# - benchmark snapshot archived to graphify-out/benchmarks/phase-7-benchmark.json

# After passing, update PROGRESS.md:
# - Set PR 7 status to ✅ Done
# - Fill commit hash: git log -1 --format="%H"
```

---

## Prompt (paste into AI coding agent)

```
You are implementing Phase 10 of the Graphify fork enhancement plan — Process Tracing.

Repository: ~/graphify
Branch: feat/phase-10-process-tracing

TASK: Build entry point detection, process tracing, change impact analysis, and the detect_changes MCP tool.

## Module 1: Process Tracing Engine (graphify/processes.py)

Create graphify/processes.py:

1. Define dataclasses: EntryPoint (node_id, label, kind, route, method, score, file), ProcessStep (node_id, step_index, call_chain, file, line, is_branching), Process (id, name, entry_point, steps, confidence, total_calls, unique_files).

2. detect_entry_points(G) → list[EntryPoint]:
   Scan all graph nodes. Heuristic classification:
   - HANDLES_ROUTE edges → route_handler (score 10)
   - label is "main()" or contains "__main__" → cli_main (score 7)
   - label starts with "test_" or ends with "Test" → test (score 3)
   - label contains "middleware" (case insensitive) → middleware (score 5)
   - label contains "cron"/"schedule"/"job" → cron (score 6)
   - High-degree nodes (>5 edges) that are exported → library_export (score 1)
   - Extract route and HTTP method from node metadata if available.
   - Sort by score descending. Return all candidates.

3. trace_process(G, entry, max_depth=20) → Process:
   BFS from entry.node_id following CALLS edges only. Use type-safe edge lookups — check edge_type from code_schema or relation field.
   Track visited set to handle cycles. Record call chain for each step.
   Mark steps as branching if they have >1 outgoing CALLS edge.
   Stop at max_depth or when no unvisited CALLS edges remain.
   Compute confidence as average of all edge confidence_scores in the trace.
   Count unique files from node source_file attributes.

4. build_processes(G) → list[Process]:
   Orchestrate: detect → sort by score → trace top N (limit: min(50, len(entries))). Return list of Process.

5. cluster_processes(processes) → list[list[Process]]:
   Compute Jaccard similarity on step node_id sets. Processes with >90% overlap → same cluster.
   Each process belongs to exactly one cluster.

6. detect_changes(G, processes, changed_files=None) → dict:
   If changed_files is None, return stub (tests should not need real git integration).
   Otherwise: find nodes whose source_file is in changed_files. Find which processes those nodes belong to.
   Return summary, changed_symbols, affected_processes, recommendations.

7. assess_risk(affected_count, affected_processes) → str: LOW, MEDIUM, HIGH.

8. write_processes_json(processes, output_path) → None:
   Write to JSON. Format spec in docs/plans/spec.md Section 8.

## Module 2: Build + Cluster Integration

9. In graphify/build.py, extend build_from_json():
   - Add trace_processes=False parameter at end of signature.
   - If True, after graph construction, call build_processes(G), write_processes_json(cache_dir), add STEP_IN_PROCESS edges.
   - Also push through build() and build_merge().

10. In graphify/cluster.py, add cluster_with_processes(G, processes):
    - Use process co-occurrence as additional signal for community detection.
    - Nodes in the same process trace get a cohesion bonus during partition.
    - Fall back to regular cluster() if no processes provided.

## Module 3: MCP Tools (extend serve.py)

11. Add detect_changes MCP tool definition and handler.
    Input: scope (string, default "all"). Output format in spec Section 8.

12. Update context(name) tool (from Phase 9) to include processes field in output.

13. Update impact(target, direction, minConfidence) tool to include affected_processes in summary.

## Module 4: Tests

14. Create tests/test_processes.py with 8+ tests:
    - Build a test graph with known CALLS edges and entry points.
    - Test entry point detection (routes, CLI, tests).
    - Test process tracing (follows CALLS, handles cycles, respects max depth).
    - Test cluster_processes (deduplication).
    - Test assess_risk (all levels).
    - Test detect_changes with explicit changed_files.
    Use same _make_graph pattern from test_serve.py.

15. Add 1 test to tests/test_serve.py for detect_changes tool response format.

MATCH EXISTING CODE STYLE. All new code additive. Zero breaking changes.

The CALLS edge relation comes from Phase 9's call_dag.py. If calls edges don't exist on the test graph, manually add them as edges with relation="calls" + confidence.

RUN `pytest tests/ -q` after implementation.

ADD benchmark_process_tracing(G) and benchmark_change_impact(G) to graphify/benchmark.py. Measure trace throughput and change impact analysis speed.

RUN `git add -A && git commit -m "feat(phase-10): process tracing + change impact analysis"`
```
