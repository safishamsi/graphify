# Architecture

graphify is a Claude Code skill backed by a Python library. The skill orchestrates the library; the library can be used standalone.

## Pipeline

```
detect  →  extract  →  build  →  cluster  →  analyze  →  report  →  export
```

Each stage is implemented as a dedicated sub-package or module. They communicate through plain Python dicts and NetworkX graphs - no shared state, no side effects outside `graphify-out/`.

## Package structure

Following a major modularization effort, the codebase is structured into feature-specific packages rather than flat files:

| Package / Module | Responsibility | Input → Output |
|------------------|----------------|----------------|
| `cli/` | Entry point & argument parsing (`main.py`) | argv → CLI commands |
| `detect/` | File discovery and filtering (`collect_files`) | directory → `[Path]` filtered list |
| `extract/` | Orchestration of the AST/semantic extraction | file path → `{nodes, edges}` dict |
| `extractors/` | Language-specific AST parsers (Python, TS, .NET, MCP, etc.) | source code/JSON → extraction dict |
| `build/` | Graph construction from extraction dicts | list of extraction dicts → `nx.Graph` |
| `cluster.py` | Community detection and clustering | graph → graph with `community` attr on each node |
| `analyze/` | Graph metrics, god nodes, and surprise analysis | graph → analysis dict (god nodes, surprises, questions) |
| `report.py` | Generation of `GRAPH_REPORT.md` | graph + analysis → markdown string |
| `export/` | Format conversion (HTML, JSON, SVG, Obsidian) | graph → graphify-out files |
| `llm/` | Parallel semantic chunk extraction and backend integration | uncached files → semantic nodes/edges |
| `serve/` | MCP stdio server and graph query endpoints | graph file path → MCP stdio server |
| `watch/` | Filesystem watcher for automatic graph rebuilding | directory → writes flag file on change |
| `installers/` | Integrations for Claude Code, Cursor, Windsurf, etc. | setup commands → modified tool configs |
| `skills/` | Markdown files for AI assistant prompt injection | none → static files |
| `ingest.py` | Fetching remote URLs or markdown | URL → file saved to corpus dir |
| `cache.py` | Semantic chunk caching logic | files → (cached, uncached) split |
| `security.py` | Input validation and SSRF protections | URL / path / label → validated or raises |
| `validate.py` | Schema enforcement for extraction output | extraction dict → raises on schema errors |
| `benchmark.py` | Benchmarking subgraph vs corpus extraction | graph file → corpus vs subgraph token comparison |

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

`validate.py` enforces this schema before graph construction consumes it.

## Confidence labels

| Label | Meaning |
|-------|---------|
| `EXTRACTED` | Relationship is explicitly stated in the source (e.g., an import statement, a direct call) |
| `INFERRED` | Relationship is a reasonable deduction (e.g., call-graph second pass, co-occurrence in context) |
| `AMBIGUOUS` | Relationship is uncertain; flagged for human review in GRAPH_REPORT.md |

## Adding a new language extractor

1. Add a new `<lang>_extractor.py` module in `graphify/extractors/` following the existing pattern (tree-sitter parse → walk nodes → collect `nodes` and `edges` → call-graph second pass for INFERRED `calls` edges).
2. Register the file suffix in `graphify/extract/core.py` dispatch.
3. Add the suffix to `CODE_EXTENSIONS` in `graphify/detect/core.py` and `_WATCHED_EXTENSIONS` in `graphify/watch/core.py`.
4. Add the tree-sitter package to `pyproject.toml` dependencies.
5. Add a fixture file to `tests/fixtures/` and tests to `tests/extractors/`.

## Security

All external input passes through `graphify/security.py` before use:

- URLs → `validate_url()` (http/https only) + `_NoFileRedirectHandler` (blocks file:// redirects)
- Fetched content → `safe_fetch()` / `safe_fetch_text()` (size cap, timeout)
- Graph file paths → `validate_graph_path()` (must resolve inside `graphify-out/`)
- Node labels → `sanitize_label()` (strips control chars, caps 256 chars, HTML-escapes)

See `SECURITY.md` for the full threat model.

## Testing

Tests are modularized under `tests/` mirroring the package layout (`tests/cli/`, `tests/detect/`, `tests/extract/`, etc.).
Run with:

```bash
pytest tests/ -q
```

All tests are pure unit tests - no network calls, no file system side effects outside `tmp_path`.
