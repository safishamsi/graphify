# Small E2E Test for Agent

This test validates the `pyaag` skill and the core extraction pipeline using a small set of local fixtures.

## Step 1: Install the pyaag skill

Run the following command to ensure the `pyaag` skill is installed for the Gemini CLI:

```bash
uv run python -m graphify pyinstall gemini
```

## Step 2: Build the Graph

From within this agent session, run the `/pyaag` command on the small KB fixtures. 
Note: We use `--db` to ensure we test the SQLite backend.

```bash
/pyaag tests/fixtures/small_kb/raw --db
```

## Step 3: Verify Artifacts

Check that the output directory and key files exist:

```bash
ls -d graphify-out
ls graphify-out/graph.db
ls graphify-out/GRAPH_REPORT.md
ls graphify-out/.graphify_analysis.json
```

## Step 4: Verify Content (Python check)

Run a small script to verify the graph content:

```python
import sys
from pathlib import Path
from graphify.store import load

G = load(Path("graphify-out"))
nodes = [data.get("label", "").lower() for _, data in G.nodes(data=True)]

# Verify we have nodes for our fixtures
assert any("test1.c" in n or "test1_c" in n for n in nodes), f"test1.c not found in {nodes}"
assert any("test2.c" in n or "test2_c" in n for n in nodes), f"test2.c not found in {nodes}"
assert any("cwe-119" in n for n in nodes), f"cwe-119.txt not found in {nodes}"

print(f"PASS: Found {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
```

## Step 5: Cleanup

```bash
rm -rf graphify-out
```
