**IMPORTANT: Step 9 (cleanup) deletes intermediate files (`.aag_detect.json`, `.aag_extract.json`, etc.). ALL domain analysis, narrative synthesis, and dashboard generation MUST complete BEFORE Step 9. If you need these files for domain steps, do NOT run Step 9 early.**

### Step 6 - Generate Obsidian vault (opt-in) + HTML

**Generate HTML always** (unless `--no-viz`). **Obsidian vault only if `--obsidian` was explicitly given** — skip it otherwise, it generates one file per node.

If `--obsidian` was given:

- If `--obsidian-dir <path>` was also given, pass it via `--dir`. Otherwise defaults to `graphify-out/obsidian`.

```bash
aag export obsidian
# or with custom dir: aag export obsidian --dir ~/vaults/my-project
```

Generate the HTML graph (always, unless `--no-viz`):

```bash
aag export html  # auto-aggregates to community view if graph > 5000 nodes
# or: aag export html --no-viz
```

### Step 6b - Wiki (only if --wiki flag)

**Only run this step if `--wiki` was explicitly given in the original command.**

Run this before Step 9 (cleanup) so `.aag_labels.json` is still available.

```bash
aag export wiki
```

### Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag)

**If `--neo4j`** - generate a Cypher file for manual import:

```bash
aag export neo4j
```

**If `--neo4j-push <uri>`** - push directly to a running Neo4j instance. Ask the user for credentials if not provided:

```bash
aag export neo4j --push bolt://localhost:7687 --user neo4j --password PASSWORD
```

Default URI is `bolt://localhost:7687`, default user is `neo4j`. Uses MERGE - safe to re-run without creating duplicates.

### Step 7b - SVG export (only if --svg flag)

```bash
aag export svg
```

### Step 7c - GraphML export (only if --graphml flag)

```bash
aag export graphml
```

### Step 7d - MCP server (only if --mcp flag)

```bash
python3 -m aag.serve graphify-out
```

(Pass the `graphify-out/` directory; the server auto-detects whether the KB is `graph.json` or `graph.db`.)

This starts a stdio MCP server that exposes tools: `query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`. Add to Claude Desktop or any MCP-compatible agent orchestrator so other agents can query the graph live.

To configure in Claude Desktop, add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "aag": {
      "command": "python3",
      "args": ["-m", "aag.serve", "/absolute/path/to/graphify-out"]
    }
  }
}
```

### Step 7e - Dashboard (auto-generated when `--domain` was passed)

**Generate dashboard.html whenever `domain_analysis` is present in `.aag_analysis.json`.** This is NOT optional when domains are active — always run it.

```bash
$(cat graphify-out/.aag_python) -c "
from pathlib import Path
from aag.dashboard import render_dashboard_from_file
analysis_path = Path('graphify-out/.aag_analysis.json')
graph_path = Path('graphify-out/graph.db') if Path('graphify-out/graph.db').exists() else Path('graphify-out/graph.json')
out = render_dashboard_from_file(analysis_path, graph_path)
print(f'dashboard.html written to {out}')
"
```

The dashboard provides an interactive view of domain analysis findings: red flags by severity, key person risk, concentration risk, and synthesized narratives.

### Step 8 - Token reduction benchmark (only if total_words > 5000)

If `total_words` from `graphify-out/.aag_detect.json` is greater than 5,000, run:

```bash
aag benchmark
```

Print the output directly in chat. If `total_words <= 5000`, skip silently - the graph value is structural clarity, not token compression, for small corpora.

---

### Step 9 - Save manifest, update cost tracker, clean up, and report

```bash
$(cat graphify-out/.aag_python) -c "
import json
from pathlib import Path
from datetime import datetime, timezone
from aag.detect import save_manifest

# Save manifest for --update
detect = json.loads(Path('graphify-out/.aag_detect.json').read_text())
save_manifest(detect['files'])

# Update cumulative cost tracker
extract = json.loads(Path('graphify-out/.aag_extract.json').read_text())
input_tok = extract.get('input_tokens', 0)
output_tok = extract.get('output_tokens', 0)

cost_path = Path('graphify-out/cost.json')
if cost_path.exists():
    cost = json.loads(cost_path.read_text())
else:
    cost = {'runs': [], 'total_input_tokens': 0, 'total_output_tokens': 0}

cost['runs'].append({
    'date': datetime.now(timezone.utc).isoformat(),
    'input_tokens': input_tok,
    'output_tokens': output_tok,
    'files': detect.get('total_files', 0),
})
cost['total_input_tokens'] += input_tok
cost['total_output_tokens'] += output_tok
cost_path.write_text(json.dumps(cost, indent=2))

print(f'This run: {input_tok:,} input tokens, {output_tok:,} output tokens')
print(f'All time: {cost[\"total_input_tokens\"]:,} input, {cost[\"total_output_tokens\"]:,} output ({len(cost[\"runs\"])} runs)')
"
rm -f graphify-out/.aag_detect.json graphify-out/.aag_extract.json graphify-out/.aag_ast.json graphify-out/.aag_semantic.json graphify-out/.aag_chunk_*.json
rm -f graphify-out/.needs_update 2>/dev/null || true
```
