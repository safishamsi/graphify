# Architecture

graphify is a set of assistant skill templates backed by a Python library. The skills orchestrate the library in coding-agent sessions; the library can also be used standalone from the CLI.

## Pipeline

```
detect()  →  extract()  →  build() / build_merge()  →  cluster()  →  analyze()  →  report()  →  export()
```

Pipeline stages communicate through plain Python dicts and NetworkX graphs. Normal project outputs are written under `graphify-out/`; install, hook, and global-graph commands may also write the corresponding assistant config files, git hook config, or `~/.graphify/` global graph state.

## Module responsibilities

| Module | Function | Input → Output |
|--------|----------|----------------|
| `detect.py` | `detect(root)`, `detect_incremental(root)` | directory → classified file manifest |
| `extract.py` | `extract(paths)`, `collect_files(target)` | code paths → `{nodes, edges, hyperedges}` dict |
| `build.py` | `build(extractions)`, `build_from_json(extraction)`, `build_merge(...)` | extraction dicts → `nx.Graph` |
| `cluster.py` | `cluster(G)` | graph → graph with `community` attr on each node |
| `analyze.py` | `god_nodes(G)`, `surprising_connections(...)`, `suggest_questions(...)`, `graph_diff(...)` | graph → analysis lists/diffs |
| `report.py` | `generate(...)` | graph + analysis → GRAPH_REPORT.md string |
| `export.py` | `to_json(...)`, `to_html(...)`, plus optional exporters | graph → graph.json, graph.html, Obsidian/wiki/GraphML/SVG/Neo4j outputs |
| `ingest.py` | `ingest(url, ...)` | URL → file saved to corpus dir |
| `cache.py` | `check_semantic_cache / save_semantic_cache` | files → (cached, uncached) split |
| `security.py` | validation helpers | URL / path / label → validated or raises |
| `validate.py` | `validate_extraction(data)`, `assert_valid(data)` | extraction dict → error list, or raises via `assert_valid()` |
| `serve.py` | `serve(graph_path)` | graph file path → MCP stdio server |
| `watch.py` | `watch(root)`, `_rebuild_code(root)` | directory → rebuilds code graph or writes `needs_update` for semantic changes |
| `benchmark.py` | `run_benchmark(graph_path)` | graph file → corpus vs subgraph token comparison |

## Extraction output schema

Every extractor returns:

```json
{
  "nodes": [
    {"id": "unique_string", "label": "human name", "source_file": "path", "source_location": "L42"}
  ],
  "edges": [
    {"source": "id_a", "target": "id_b", "relation": "calls|imports|uses|...", "confidence": "EXTRACTED|INFERRED|AMBIGUOUS"}
  ]
}
```

`validate.py` reports schema issues before graph construction. `build_from_json()` warns on real schema errors and skips edges whose endpoints do not match graph nodes after normalization.

## Confidence labels

| Label | Meaning |
|-------|---------|
| `EXTRACTED` | Relationship is explicitly stated in the source (e.g., an import statement, a direct call) |
| `INFERRED` | Relationship is a reasonable deduction (e.g., call-graph second pass, co-occurrence in context) |
| `AMBIGUOUS` | Relationship is uncertain; flagged for human review in GRAPH_REPORT.md |

## Adding a new language extractor

1. Add an `extract_<lang>(path: Path) -> dict` function in `extract.py` following the existing pattern (tree-sitter parse → walk nodes → collect `nodes` and `edges` → call-graph second pass for `calls` edges).
2. Register the file suffix in `extract.py`'s dispatch table. `collect_files()` derives its extension set from that dispatch table.
3. Add the suffix to `CODE_EXTENSIONS` in `detect.py`; `watch.py` imports those extension sets rather than maintaining its own copy.
4. Add the tree-sitter package to `pyproject.toml` dependencies.
5. Add a fixture file to `tests/fixtures/` and tests to `tests/test_languages.py`.

## Security

All external input passes through `graphify/security.py` before use:

- URLs → `validate_url()` (http/https only) + `_NoFileRedirectHandler` (blocks file:// redirects)
- Fetched content → `safe_fetch()` / `safe_fetch_text()` (size cap, timeout)
- Graph file paths → `validate_graph_path()` (must resolve inside `graphify-out/`)
- Node labels → `sanitize_label()` (strips control chars, caps 256 chars, HTML-escapes)

See `SECURITY.md` for the full threat model.

## Testing

One test file per module under `tests/`. Run with:

```bash
pytest tests/ -q
```

All tests are pure unit tests - no network calls, no file system side effects outside `tmp_path`.
