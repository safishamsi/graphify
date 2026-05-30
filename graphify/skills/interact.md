## For --update (incremental re-extraction)

Use when you've added or modified files since the last run. Only re-extracts changed files - saves tokens and time.

```bash
$(cat graphify-out/.aag_python) -c "
import sys, json
from aag.detect import detect_incremental, save_manifest
from pathlib import Path

result = detect_incremental(Path('INPUT_PATH'))
new_total = result.get('new_total', 0)
print(json.dumps(result, indent=2))
Path('graphify-out/.aag_incremental.json').write_text(json.dumps(result))
if new_total == 0:
    print('No files changed since last run. Nothing to update.')
    raise SystemExit(0)
print(f'{new_total} new/changed file(s) to re-extract.')
"
```

If new files exist, first check whether all changed files are code files:

```bash
$(cat graphify-out/.aag_python) -c "
import json
from pathlib import Path

result = json.loads(open('graphify-out/.aag_incremental.json').read()) if Path('graphify-out/.aag_incremental.json').exists() else {}
code_exts = {'.py','.ts','.js','.go','.rs','.java','.cpp','.c','.rb','.swift','.kt','.cs','.scala','.php','.cc','.cxx','.hpp','.h','.kts','.lua','.toc','.f','.F','.f90','.F90','.f95','.F95','.f03','.F03','.f08','.F08'}
new_files = result.get('new_files', {})
all_changed = [f for files in new_files.values() for f in files]
code_only = all(Path(f).suffix.lower() in code_exts for f in all_changed)
print('code_only:', code_only)
"
```

## For --cluster-only

Skip Steps 1–3. Re-run clustering on the existing graph:

```bash
aag cluster-only .
```

## For /aag query

Two traversal modes - choose based on the question:

| Mode | Flag | Best for |
|------|------|----------|
| BFS (default) | _(none)_ | "What is X connected to?" - broad context, nearest neighbors first |
| DFS | `--dfs` | "How does X reach Y?" - trace a specific chain or dependency path |

```bash
aag query "QUESTION"
# or: aag query "QUESTION" --dfs --budget 3000
```

Replace `QUESTION` with the user's actual question. Answer using **only** what the graph output contains. Quote `source_location` when citing a specific fact. If the graph lacks enough information, say so - do not hallucinate edges.

After writing the answer, save it back into the graph so it improves future queries:

```bash
$(cat graphify-out/.aag_python) -m aag save-result --question "QUESTION" --answer "ANSWER" --type query --nodes NODE1 NODE2
```

## For /aag path

Find the shortest path between two named concepts in the graph.

```bash
aag path "NODE_A" "NODE_B"
```

Replace `NODE_A` and `NODE_B` with the actual concept names. Then explain the path in plain language - what each hop means, why it's significant.

After writing the explanation, save it back:

```bash
$(cat graphify-out/.aag_python) -m aag save-result --question "Path from NODE_A to NODE_B" --answer "ANSWER" --type path_query --nodes NODE_A NODE_B
```

## For /aag explain

Give a plain-language explanation of a single node - everything connected to it.

```bash
aag explain "NODE_NAME"
```

Replace `NODE_NAME` with the concept the user asked about. Then write a 3-5 sentence explanation of what this node is, what it connects to, and why those connections are significant. Use the source locations as citations.

After writing the explanation, save it back:

```bash
$(cat graphify-out/.aag_python) -m aag save-result --question "Explain NODE_NAME" --answer "ANSWER" --type explain --nodes NODE_NAME
```

## For /aag add

Fetch a URL and add it to the corpus, then update the graph.

```bash
$(cat graphify-out/.aag_python) -c "
import sys
from aag.ingest import ingest
from pathlib import Path

try:
    out = ingest('URL', Path('./raw'), author='AUTHOR', contributor='CONTRIBUTOR')
    print(f'Saved to {out}')
except ValueError as e:
    print(f'error: {e}', file=sys.stderr)
    sys.exit(1)
except RuntimeError as e:
    print(f'error: {e}', file=sys.stderr)
    sys.exit(1)
"
```

## For --watch

Start a background watcher that monitors a folder and auto-updates the graph when files change.

```bash
python3 -m aag.watch INPUT_PATH --debounce 3
```

## For git commit hook

Install a post-commit hook that auto-rebuilds the graph after every commit.

```bash
aag hook install    # install
aag hook uninstall  # remove
aag hook status     # check
```

## For native CLAUDE.md integration

Run once per project to make aag always-on in Claude Code sessions:

```bash
aag claude install
```
