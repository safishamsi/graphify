# PR 10: Multi-Repo Groups (Enterprise)

**Phase:** 13
**Stream:** B (Code Intelligence)
**Estimate:** 2-3 weeks
**Depends on:** Phase 8 (typed code schema)

## What to Build

### 1. Global Registry (`graphify/registry.py` — NEW)

```python
"""Global registry at ~/.graphify/registry.json.
Tracks indexed repos, last commit, group membership."""

import json
from pathlib import Path
from dataclasses import dataclass, field

REGISTRY_PATH = Path.home() / ".graphify" / "registry.json"

@dataclass
class RepoEntry:
    repo_id: str
    name: str
    path: str           # Absolute path
    last_commit: str    # HEAD commit at last index
    group: str | None = None
    url: str | None = None
    indexed_at: str = ""  # ISO timestamp

def load_registry() -> dict[str, RepoEntry]:
    """Load registry from ~/.graphify/registry.json. Returns {} if not found."""

def save_registry(registry: dict[str, RepoEntry]) -> None:
    """Save registry. Creates ~/.graphify/ if needed."""

def register_repo(repo_path: str, meta: dict | None = None) -> RepoEntry:
    """Register a repo. Computes repo_id from path hash.
    Detects git HEAD commit. Returns RepoEntry."""
    
def unregister_repo(repo_id: str) -> bool:
    """Remove repo from registry. Returns True if found."""
    
def list_repos() -> list[RepoEntry]:
    """List all registered repos."""
    
def get_repo(repo_id: str) -> RepoEntry | None:
    """Get repo by ID."""
    
def update_commit(repo_id: str, commit: str) -> None:
    """Update last_commit for a repo."""

def is_stale(repo_id: str) -> bool:
    """Check if repo HEAD differs from last_commit."""
```

### 2. Lazy Connection Pool (`graphify/lazy_pool.py` — NEW)

```python
"""Lazy graph connection pool.
Opens graphs on first query, evicts after inactivity timeout."""

import time
import networkx as nx

class GraphPool:
    """Lazy graph pool with eviction.
    Max 5 concurrent open graphs. 5-minute inactivity eviction."""
    
    def __init__(self, max_open: int = 5, ttl_minutes: int = 5):
        self._pool: dict[str, tuple[nx.Graph, float]] = {}  # repo_id → (G, last_access)
        self._max_open = max_open
        self._ttl_seconds = ttl_minutes * 60
    
    def get_graph(self, repo_id: str) -> nx.Graph | None:
        """Get graph for repo. Loads from graphify-out/graph.json if not cached.
        Updates last_access timestamp. Evicts stale entries.
        Returns None if graph file not found."""
        
    def evict(self, repo_id: str) -> None:
        """Explicitly evict a repo's graph."""
        
    def evict_expired(self) -> int:
        """Evict all entries past TTL. Returns count evicted."""
        
    def close(self) -> None:
        """Close all graphs, clear pool."""
```

### 3. Repository Groups (`graphify/groups.py` — NEW)

```python
"""Repository group management. Unified knowledge graph across repos."""

def create_group(name: str, repos: list[str] = None) -> dict:
    """Create a named group. Optionally add initial repos.
    Groups stored in ~/.graphify/groups/{name}.json"""

def add_to_group(name: str, repo_id: str) -> None:
    """Add repo to group."""

def remove_from_group(name: str, repo_id: str) -> None:
    """Remove repo from group."""

def list_groups() -> list[str]:
    """List all group names."""

def get_group_repos(name: str) -> list[str]:
    """Get repo IDs in a group."""

def sync_group(name: str) -> dict:
    """Extract contracts (shared interfaces, APIs, type exports)
    and build cross-repo bridge edges.
    Returns {contracts_found, bridges_created}."""

def query_group(name: str, query_text: str) -> dict:
    """Search across all repos in a group.
    Runs query on each repo's graph, merges via Reciprocal Rank Fusion.
    Returns {repo_results: {repo_id: [results]}, merged: [merged_results]}"""

def group_status(name: str) -> dict:
    """Check staleness and stats for all repos in a group.
    Returns {repos: [{repo_id, last_indexed, head_commit, stale, nodes, edges}]}"""
```

### 4. Contract Bridge (`graphify/contract_bridge.py` — NEW)

```python
"""Cross-repo dependency mapping."""

def detect_shared_interfaces(graphs: dict[str, nx.Graph]) -> list[dict]:
    """Find shared interfaces across repos.
    Matches class names + method signatures.
    Returns [{interface_name, repos: [repo_ids], methods: [method_names]}]."""

def detect_shared_types(graphs: dict[str, nx.Graph]) -> list[dict]:
    """Find type definitions shared across repos.
    Matches by type name, with signature fuzzy matching."""

def map_api_consumers(api_repo_id: str, consumer_repos: list[str],
                      pool: 'GraphPool') -> list[dict]:
    """Find which functions in consumer repos call API endpoints from api_repo.
    Matches route patterns to call sites."""

def build_cross_repo_edges(repo_a: str, repo_b: str, 
                           pool: 'GraphPool') -> list[dict]:
    """Build cross-repo bridge edges between two graphs.
    Returns list of edge dicts (source in repo_a, target in repo_b)."""
```

### 5. Group-Aware MCP Tools (`graphify/serve.py` — EXTEND)

Add group-aware tools. These require lazy_pool to be initialized:

```python
# New MCP tools:

"""
group_list  → [{name, member_count, repo_paths}]
  
group_sync({name: "monorepo"})  → {contracts_found, bridges_created}

group_contracts({name: "monorepo"})  → {providers: [...], consumers: [...], cross_links: [...]}

group_query({name: "monorepo", query: "authentication"})  → 
  {repo_results: {...}, merged: [...RRF merged]}

group_status({name: "monorepo"})  → 
  {repos: [{repo, last_indexed, head_commit, stale}]}
"""
```

**Group mode for existing tools:**
- `context(name, repo="repo_id")` — scope to specific repo in group
- `impact(target, direction, repo="@groupName")` — fan out across all repos
- `query(query, repo="@groupName")` — search across all repos, merge via RRF

### 6. CLI Commands (`graphify/__main__.py` — EXTEND)

```
graphify register [path]           # Register current or specified repo
graphify unregister [repo_id]      # Unregister a repo
graphify repos                     # List registered repos
graphify group create <name>       # Create a group
graphify group add <name> <repo>   # Add repo to group
graphify group sync <name>         # Sync cross-repo contracts
graphify group status <name>       # Check group status
graphify group query <name> <q>    # Query across group
```

### 7. Tests

**`tests/test_registry.py` (NEW, 5+ tests):**
```python
def test_register_and_list_repos(tmp_path, monkeypatch):
    """Override REGISTRY_PATH to use tmp_path."""

def test_unregister_repo(tmp_path, monkeypatch):
    
def test_update_commit(tmp_path, monkeypatch):
    
def test_is_stale(tmp_path, monkeypatch):
    
def test_load_empty_registry(tmp_path, monkeypatch):
```

**`tests/test_lazy_pool.py` (NEW, 4+ tests):**
```python
def test_pool_get_graph(tmp_path):
def test_pool_eviction(tmp_path):
def test_pool_evict_expired(monkeypatch):
    """Mock time.time to test TTL eviction."""
def test_pool_max_open():
```

**`tests/test_groups.py` (NEW, 4+ tests):**
```python
def test_create_and_list_groups(tmp_path, monkeypatch):
def test_add_and_get_repos(tmp_path, monkeypatch):
def test_group_status(tmp_path, monkeypatch):
def test_group_empty_repos():
```

**`tests/test_contract_bridge.py` (NEW, 3+ tests):**
```python
def test_detect_shared_interfaces():
def test_detect_shared_types():
def test_no_shared_symbols():
```

## Files Changed/Created

| File | Action | Purpose |
|------|--------|---------|
| `graphify/registry.py` | **New** | Global repo registry |
| `graphify/lazy_pool.py` | **New** | Lazy graph connection pool |
| `graphify/groups.py` | **New** | Repository group management |
| `graphify/contract_bridge.py` | **New** | Cross-repo dependency mapping |
| `graphify/serve.py` | **Extend** | Group-aware MCP tools, repo parameter |
| `graphify/__main__.py` | **Extend** | Group/registry CLI commands |
| `tests/test_registry.py` | **New** | |
| `tests/test_lazy_pool.py` | **New** | |
| `tests/test_groups.py` | **New** | |
| `tests/test_contract_bridge.py` | **New** | |

## Compatibility
- All existing single-repo workflows continue unchanged
- Group mode is additive — existing tools get optional `repo` parameter
- `register` data stored in `~/.graphify/` — doesn't touch project directories
- Lazy pool configured for local use only (no server mode needed)
- All test file I/O uses tmp_path or monkeypatch to avoid touching real filesystem

## Verification
```bash
pytest tests/test_registry.py tests/test_lazy_pool.py tests/test_groups.py tests/test_contract_bridge.py -q
pytest tests/ -q  # full suite
```

### Multi-Repo Scale Benchmarks

Add to `graphify/benchmark.py`:

```python
def benchmark_pool_eviction(pool, num_cycles: int = 100, seed: int = 42) -> dict:
    """Measure lazy pool eviction overhead.
    Returns {evict_per_cycle_ms: {avg, p95}, cache_hit_rate: float, pool_memory_mb: float}."""

def benchmark_cross_repo_query(pool, group_name: str, num_queries: int = 20, seed: int = 42) -> dict:
    """Measure cross-repo query latency.
    Returns {per_repo_ms: {avg, p95}, merge_ms: {avg, p95}, total_ms: {avg}}."""

def benchmark_contract_detection(pool, num_repos: int) -> dict:
    """Measure shared interface detection time across N repos.
    Returns {repos_scanned, interfaces_found, detection_ms, per_repo_ms}."""

def benchmark_multi_repo_scale(pool, repo_counts: list[int] = [2, 5, 10, 20]) -> list[dict]:
    """Run benchmark_cross_repo_query at increasing repo counts.
    Returns list of results dicts showing degradation curve."""
```

Run after implementation:
```bash
python -c "
from graphify.benchmark import benchmark_pool_eviction, benchmark_cross_repo_query
from graphify.lazy_pool import GraphPool
pool = GraphPool()
# Register 2-3 test repos first
print(benchmark_pool_eviction(pool))
"
```

### Commit

```bash
git add -A && git commit -m "feat(phase-13): multi-repo groups (registry + lazy pool + contract bridge)"
```

---

## Code Review Checklist

Before merging this PR, verify:
- [ ] All tests pass: `pytest tests/ -q`
- [ ] Registry I/O uses atomic writes, handles missing `~/.graphify/` dir
- [ ] Lazy pool evicts expired entries and respects max_open limit
- [ ] Group operations (create, add, remove, status) work correctly
- [ ] Cross-repo queries succeed when repo parameter is provided
- [ ] `benchmark_pool_eviction()` shows acceptable cache hit rate
- [ ] `benchmark_multi_repo_scale()` shows query latency at 2/5/10/20 repos
- [ ] No real filesystem modifications in tests (tmp_path/monkeypatch)
- [ ] Existing single-repo workflows unaffected by group-aware tool changes
- [ ] At least 1 other developer reviewed

---

## CI Verification
```bash
# Run automated verification for this PR:
bash docs/plans/verify-pr.sh 10

# Expected checks:
# - Full test suite passes
# - tests/test_registry.py + tests/test_lazy_pool.py pass
# - benchmark snapshot archived to graphify-out/benchmarks/phase-10-benchmark.json

# After passing, update PROGRESS.md:
# - Set PR 10 status to ✅ Done
# - Fill commit hash: git log -1 --format="%H"
```

---

## Prompt (paste into AI coding agent)

```
You are implementing Phase 13 of the Graphify fork enhancement plan — Multi-Repo Groups.

Repository: ~/graphify
Branch: feat/phase-13-multi-repo

TASK: Build global registry, lazy graph pool, repository groups, contract bridge, and group-aware MCP tools.

## PART A: Global Registry (graphify/registry.py)

1. RepoEntry dataclass: repo_id, name, path, last_commit, group, url, indexed_at.
2. REGISTRY_PATH = Path.home() / ".graphify" / "registry.json"
3. load_registry() → dict[str, RepoEntry]: Load from JSON. Return {} if not found.
4. save_registry(registry): Save to JSON. Create dir if needed. Atomic write.
5. register_repo(repo_path, meta=None) → RepoEntry:
   - Detect git HEAD: run `git -C {path} rev-parse HEAD` (handle non-git dirs gracefully — set last_commit="").
   - Generate repo_id from path stem + hash (short, readable).
   - Add to registry, save, return entry.
6. unregister_repo(repo_id) → bool.
7. list_repos() → list[RepoEntry].
8. get_repo(repo_id) → RepoEntry | None.
9. update_commit(repo_id, commit): Update last_commit, save.
10. is_stale(repo_id) → bool: Compare registry commit vs git HEAD.

## PART B: Lazy Pool (graphify/lazy_pool.py)

11. class GraphPool(max_open=5, ttl_minutes=5):
    - _pool: dict[str, tuple[G, last_access_timestamp]]
    - get_graph(repo_id): Load from registry→graphify-out/graph.json. Cache in pool. Evict expired. Update timestamp.
    - evict(repo_id): Remove from pool.
    - evict_expired() → int: Remove entries past TTL.
    - close(): Clear pool.
    - Use nx.readwrite.json_graph for loading.

## PART C: Repository Groups (graphify/groups.py)

12. create_group(name, repos=None) → dict: Create group file at ~/.graphify/groups/{name}.json.
13. add_to_group(name, repo_id): Add repo to group.
14. remove_from_group(name, repo_id): Remove from group.
15. list_groups() → list[str]: Scan ~/.graphify/groups/ directory.
16. get_group_repos(name) → list[str]: Load group file, return repo list.
17. sync_group(name) → dict: Placeholder — detect shared interfaces across repos in group. Return {contracts_found: N, bridges_created: M}.
18. query_group(name, query) → dict: Placeholder — search across repos, RRF merge. Return {repo_results: {}, merged: []}.
19. group_status(name) → dict: Check staleness of each repo in group.

## PART D: Contract Bridge (graphify/contract_bridge.py)

20. detect_shared_interfaces(graphs) → list[dict]:
    - Given {repo_id: G}, find class/interface nodes with same name appearing in ≥2 repos.
    - Match by label (case insensitive). Return [{interface_name, repos, methods}].

21. detect_shared_types(graphs) → list[dict]: Same logic for type aliases.

22. map_api_consumers(api_repo_id, consumer_repos, pool) → list[dict]: Placeholder.

23. build_cross_repo_edges(repo_a, repo_b, pool) → list[dict]: Placeholder.

## PART E: MCP Tools (extend serve.py)

24. Add group-aware MCP tools: group_list, group_sync, group_contracts, group_query, group_status.
    Each loads group data and responds with formatted text.

25. Add optional `repo` parameter to existing tools (context, impact, query):
    - If not provided, defaults to current single-repo graph.
    - If provided, pools the graph for that repo and runs the query.
    - If repo="@groupName", fans out across all repos in the group.

## PART F: CLI (extend __main__.py)

26. Add subcommands: register, unregister, repos, group create/add/sync/status/query.

## PART G: Tests

27. tests/test_registry.py: 5 tests. Use monkeypatch to set REGISTRY_PATH to tmp_path.
28. tests/test_lazy_pool.py: 4 tests. Use tmp_path with test graph.json files.
29. tests/test_groups.py: 4 tests. Use monkeypatch for group file paths.
30. tests/test_contract_bridge.py: 3 tests.

All test file I/O must use tmp_path or monkeypatch. No real filesystem modifications.

MATCH EXISTING CODE STYLE. All additive. Zero breaking changes to existing single-repo workflows.

RUN `pytest tests/ -q` after implementation.

ADD benchmark_pool_eviction(pool), benchmark_cross_repo_query(pool, group), benchmark_contract_detection(pool, N), and benchmark_multi_repo_scale(pool) to graphify/benchmark.py. Measure pool overhead, cross-repo query latency, and scaling degradation at 2/5/10/20 repos.

RUN `git add -A && git commit -m "feat(phase-13): multi-repo groups (registry + lazy pool + contract bridge)"`
```
