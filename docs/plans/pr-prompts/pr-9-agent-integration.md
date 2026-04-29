# PR 9: Agent Integration Layer

**Phase:** 12
**Stream:** B (Code Intelligence)
**Estimate:** 1-2 weeks
**Depends on:** Phase 8 (typed schema), Phase 9 (call resolution), Phase 10 (process tracing)

## What to Build

### 1. Skill Generator (`graphify/skills/__init__.py` — NEW)

```python
"""Agent skill generation from knowledge graph."""

def generate_base_skills(output_dir: Path) -> list[str]:
    """Generate 4 base skills for agent harnesses.
    Returns list of generated file paths."""
```

### 2. Skill Templates (`graphify/skills/exploring.py`, `debugging.py`, `impact.py`, `refactoring.py` — NEW)

Each contains a function that generates a skill markdown document from the graph:

```python
# graphify/skills/exploring.py

def generate_exploring_skill(G) -> str:
    """Generate an 'Exploring' skill SKILL.md content.
    
    Includes:
    - Graph navigation instructions
    - How to use query_graph / query MCP tools
    - God nodes reference (top 10 most connected)
    - Community overview (top 5 communities by size)
    - Entry point list (top 10 entry points)
    
    Returns markdown string."""
```

```python
# graphify/skills/debugging.py

def generate_debugging_skill(G) -> str:
    """Generate a 'Debugging' skill SKILL.md content.
    
    Includes:
    - How to trace call chains with context() tool
    - How to use impact() for bug triage
    - Common error patterns from the graph
    - Test file → source file mapping
    
    Returns markdown string."""
```

```python
# graphify/skills/impact.py

def generate_impact_skill(G) -> str:
    """Generate an 'Impact Analysis' skill SKILL.md content.
    
    Includes:
    - How to use impact() tool for blast radius analysis
    - How to read detect_changes() output
    - Risk assessment guidance
    - Most-changed files (from process traces)
    
    Returns markdown string."""
```

```python
# graphify/skills/refactoring.py

def generate_refactoring_skill(G) -> str:
    """Generate a 'Refactoring' skill SKILL.md content.
    
    Includes:
    - Dependency mapping instructions
    - How to find circular dependencies
    - Low-cohesion communities that should be split
    - Isolated/loosely-connected code that needs integration
    
    Returns markdown string."""
```

### 3. Per-Community Skill Generator (`graphify/skills/repo_skills.py` — NEW)

```python
def generate_community_skills(G, communities, community_labels, output_dir: Path) -> int:
    """Generate per-community SKILL.md files.
    
    For each community:
    - SKILL.md with: key files, entry points, execution flows, 
      cross-community connections, cohesion score
    - Output to output_dir/{community_name}.md
    
    Falls back to community ID if no label.
    Returns number of skills generated."""
```

### 4. Hook Generator (`graphify/skills/hooks.py` — NEW)

```python
def generate_pre_tool_use_hook(output_dir: Path) -> None:
    """Generate PreToolUse hook script.
    
    Enriches search queries with relevant graph nodes before tool calls.
    Writes to output_dir/pre-tool-use-graphify.sh
    
    Hook logic:
    - On every search tool call (grep, find, codebase_search):
    - Check if graphify-out/graph.json exists
    - If yes, inject context: "graphify: Knowledge graph available. 
      Read GRAPH_REPORT.md first for architecture overview.""""

def generate_post_tool_use_hook(output_dir: Path) -> None:
    """Generate PostToolUse hook script.
    
    Detects stale index after file writes, prompts agent to reindex.
    Writes to output_dir/post-tool-use-graphify.sh
    
    Hook logic:
    - On file write/save tool calls:
    - Check if modified file changed since last graph build
    - If yes, prompt: "graphify: File(s) modified. Consider running 
      'graphify update' to refresh the knowledge graph.""""

def generate_hooks(output_dir: Path) -> tuple[str, str]:
    """Generate both hooks. Returns (pre_tool_path, post_tool_path)."""
```

### 5. Agent Context Injection (`graphify/skills/inject.py` — NEW)

```python
def inject_into_claude_md(project_dir: Path, G) -> bool:
    """Inject graphify context section into CLAUDE.md or AGENTS.md.
    
    Appends a section like:
    ```
    ## Graphify Knowledge Graph
    - Nodes: 1,234 | Edges: 5,678 | Communities: 42
    - Top abstractions: [god node 1], [god node 2], ...
    - Available tools: query_graph, context, impact, detect_changes
    - Run `graphify serve` to start MCP server
    ```
    
    Does NOT overwrite existing graphify section if present.
    Returns True if injected, False if skipped."""

def detect_harness_configs(project_dir: Path) -> list[Path]:
    """Detect which agent harness configs exist.
    Checks for: .claude/settings.json, .opencode/config.json, 
    .cursor/mcp.json, .github/copilot-instructions.md, etc."""
```

### 6. Skills CLI Subcommand (`graphify/__main__.py` — EXTEND)

```
graphify skills                    # Generate 4 base skills to .claude/skills/graphify/
graphify skills --repo             # Generate per-community SKILL.md to .claude/skills/generated/
graphify skills --hooks            # Generate hooks to .claude/hooks/
graphify skills --all              # All of the above
graphify skills --output <dir>     # Output to custom directory (default: .claude/)
```

### 7. Existing `graphify claude install` — EXTEND

Add to the existing install command:
- Write agent context section
- Register MCP server config where applicable

### 8. Tests

**`tests/test_skills.py` (NEW, 6+ tests):**
```python
def test_generate_exploring_skill_has_sections():
def test_generate_debugging_skill_has_sections():
def test_generate_impact_skill_has_sections():
def test_generate_refactoring_skill_has_sections():
def test_generate_community_skills_creates_files(tmp_path):
def test_generate_hooks_creates_files(tmp_path):

# Skills tests use a minimal test graph
@pytest.fixture
def test_graph():
    G = nx.Graph()
    G.add_node("n1", label="main()", file_type="code", source_file="main.py")
    G.add_node("n2", label="process()", file_type="code", source_file="lib.py")
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED")
    return G
```

## Files Changed/Created

| File | Action | Purpose |
|------|--------|---------|
| `graphify/skills/__init__.py` | **New** | Skill generation orchestrator |
| `graphify/skills/exploring.py` | **New** | Exploring skill template |
| `graphify/skills/debugging.py` | **New** | Debugging skill template |
| `graphify/skills/impact.py` | **New** | Impact analysis skill template |
| `graphify/skills/refactoring.py` | **New** | Refactoring skill template |
| `graphify/skills/repo_skills.py` | **New** | Per-community SKILL.md generator |
| `graphify/skills/hooks.py` | **New** | Pre/Post tool use hook generator |
| `graphify/skills/inject.py` | **New** | Agent context injection |
| `graphify/__main__.py` | **Extend** | `graphify skills` subcommand |
| `tests/test_skills.py` | **New** | Skill generation tests |

## Compatibility Rules
- `graphify skills` generates to `graphify/` namespace — never overwrites custom skills
- Existing `graphify claude install` behavior preserved
- Hooks are additive — don't interfere with existing hooks
- Skills are generated as markdown files — no runtime dependencies
- Output directories auto-created if they don't exist

## Verification
```bash
pytest tests/test_skills.py -q
pytest tests/ -q  # full suite
```

### Skill Completeness Validation

```bash
graphify skills --all --output /tmp/graphify-skills-test/

# Verify all 4 base skills generated
ls /tmp/graphify-skills-test/exploring.md /tmp/graphify-skills-test/debugging.md \
   /tmp/graphify-skills-test/impact-analysis.md /tmp/graphify-skills-test/refactoring.md

# Each must be >50 lines, contain no placeholder text, have section headers
for f in /tmp/graphify-skills-test/*.md; do
    lines=$(wc -l < "$f")
    sections=$(grep -c '^##' "$f" || true)
    empty=$(grep -c 'TODO\|PLACEHOLDER\|FIXME\|TBD' "$f" || true)
    echo "$f: ${lines} lines, ${sections} sections, ${empty} placeholders"
    [ "$lines" -lt 50 ] && echo "FAIL: $f too short"
    [ "$empty" -gt 0 ] && echo "FAIL: $f has placeholders"
done

# Verify hooks exist and are executable
ls -l /tmp/graphify-skills-test/pre-tool-use-graphify.sh /tmp/graphify-skills-test/post-tool-use-graphify.sh
```

### Commit

```bash
git add -A && git commit -m "feat(phase-12): agent integration (skill + hook generators)"
```

---

## Code Review Checklist

Before merging this PR, verify:
- [ ] All tests pass: `pytest tests/ -q`
- [ ] All 4 base skills generate: exploring, debugging, impact-analysis, refactoring
- [ ] Each skill is >50 lines, has section headers (##), zero TODO/PLACEHOLDER text
- [ ] Pre/post tool use hooks are generated and shellcheck-clean
- [ ] `inject_into_claude_md()` inserts a "Graphify Knowledge Graph" section if absent
- [ ] `graphify skills --all` CLI completes without errors
- [ ] Generated skills don't overwrite existing custom skills in output directory
- [ ] Skills contain real data from G (not hardcoded stubs)
- [ ] At least 1 other developer reviewed

---

## CI Verification
```bash
# Run automated verification for this PR:
bash docs/plans/verify-pr.sh 9

# Expected checks:
# - Full test suite passes
# - tests/test_skills.py passes
# - Skills completeness: >= 4 valid skill files
# - benchmark snapshot archived to graphify-out/benchmarks/phase-9-benchmark.json

# After passing, update PROGRESS.md:
# - Set PR 9 status to ✅ Done
# - Fill commit hash: git log -1 --format="%H"
```

---

## Prompt (paste into AI coding agent)

```
You are implementing Phase 12 of the Graphify fork enhancement plan — Agent Integration Layer.

Repository: ~/graphify
Branch: feat/phase-12-agent-integration

TASK: Build skill generators, hook generators, and agent context injection. Add `graphify skills` CLI subcommand.

## PART A: Skill Templates

Create graphify/skills/ package with __init__.py and four skill templates:

1. graphify/skills/exploring.py: generate_exploring_skill(G) → str
   Returns SKILL.md markdown content. Sections: graph navigation instructions, how to use query_graph/query tools, top-10 god nodes, top-5 communities, top-10 entry points.

2. graphify/skills/debugging.py: generate_debugging_skill(G) → str
   Sections: call chain tracing with context() tool, bug triage with impact() tool, test file→source file mapping, common error patterns from ambiguous edges.

3. graphify/skills/impact.py: generate_impact_skill(G) → str
   Sections: blast radius analysis with impact() tool, reading detect_changes() output, risk assessment guidance, most-changed files from process traces.

4. graphify/skills/refactoring.py: generate_refactoring_skill(G) → str
   Sections: dependency mapping, finding circular dependencies, low-cohesion communities, isolated code needing integration.

Each skill file should be self-contained markdown. Use triple backtick code blocks for examples. Reference actual graph data (god nodes, community names, etc.) pulled from G.

## PART B: Repo Skills (graphify/skills/repo_skills.py)

5. generate_community_skills(G, communities, community_labels, output_dir) → int:
   - For each community in communities dict, generate a SKILL.md.
   - Content: key files, entry points, execution flows, cross-community connections, cohesion score.
   - Name files after community label (sanitized for filesystem).
   - Return count of files generated.

## PART C: Hook Generator (graphify/skills/hooks.py)

6. generate_pre_tool_use_hook(output_dir) → str:
   - Write shell script to output_dir/pre-tool-use-graphify.sh
   - Logic: on search tool calls, if graph exists, inject context suggesting GRAPH_REPORT.md first.
   - Return file path.

7. generate_post_tool_use_hook(output_dir) → str:
   - Write shell script to output_dir/post-tool-use-graphify.sh
   - Logic: on file write, detect staleness, prompt reindex.
   - Return file path.

8. generate_hooks(output_dir) → tuple[str, str]:
   - Generate both, return (pre_path, post_path).

## PART D: Context Injection (graphify/skills/inject.py)

9. inject_into_claude_md(project_dir, G) → bool:
   - Find CLAUDE.md or AGENTS.md in project_dir.
   - If found and no existing "Graphify Knowledge Graph" section, append a context section with graph stats, top abstractions, available tools.
   - Return True if injected.

10. detect_harness_configs(project_dir) → list[Path]:
    - Find agent config files: .claude/settings.json, .opencode/config.json, .cursor/mcp.json, etc.
    - Return list of Paths found.

## PART E: Skills Orchestrator (graphify/skills/__init__.py)

11. generate_base_skills(output_dir) → list[str]:
    - Call all 4 skill generators. Write to output_dir/exploring.md, debugging.md, impact-analysis.md, refactoring.md.
    - Create output_dir if needed.
    - Return list of file paths.

## PART F: CLI (extend graphify/__main__.py)

12. Add "skills" subcommand:
    - `graphify skills`: Generate 4 base skills to .claude/skills/graphify/
    - `graphify skills --repo`: Generate per-community skills
    - `graphify skills --hooks`: Generate hooks
    - `graphify skills --all`: All three
    - `graphify skills --output <dir>`: Custom output directory
    - Load graph from graphify-out/graph.json (default or --graph flag).

## PART G: Tests

13. Create tests/test_skills.py with 6+ tests:
    - Use a fixture that creates a minimal test graph (same pattern as test_serve._make_graph).
    - Test each skill generator produces non-empty markdown with expected sections.
    - Test generate_community_skills creates correct number of files (use tmp_path).
    - Test generate_hooks creates both hook files.
    - Test generate_base_skills returns list of file paths.

SKILLS ARE PURE TEXT GENERATION. No runtime deps. Each skill function takes G and returns a string. The __main__.py subcommand handles file I/O.

MATCH EXISTING CODE STYLE. Use existing test patterns. Output directories are auto-created.

RUN `pytest tests/ -q` after implementation.

RUN `graphify skills --all --output /tmp/graphify-skills-test/` and validate all 4 skills are >50 lines, have section headers, and contain zero TODO/PLACEHOLDER text.

RUN `git add -A && git commit -m "feat(phase-12): agent integration (skill + hook generators)"`
```
