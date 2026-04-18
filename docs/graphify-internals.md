# Vendored graphify — internals

The `graphify/` Python package in this repository provides **static extraction** of nodes and edges from source files (tree-sitter), graph assembly (NetworkX), clustering, analysis, and export. depOS **reuses** this layer for snapshots; product-specific code will live outside `graphify/` as the application grows.

## Pipeline

```
detect() → extract() → build_graph() → cluster() → analyze() → report() → export()
```

| Module | Responsibility |
| ------ | ---------------- |
| `detect.py` | Discover and classify files; respect `.graphifyignore`. |
| `extract.py` | Per-language AST-style extraction; cross-file import/call resolution. |
| `build.py` | Build NetworkX graph from extraction JSON (`build_from_json`). |
| `cluster.py` | Community detection (Leiden / Louvain fallback). |
| `analyze.py` | God nodes, surprising connections, suggested questions. |
| `report.py` | `GRAPH_REPORT.md` generation. |
| `export.py` | JSON, HTML, SVG, etc. |
| `serve.py` | MCP stdio server for graph queries (patterns reusable for depOS MCP). |
| `validate.py` | Extraction schema validation. |

## Extraction shape

Extractions are JSON with `nodes`, `edges`, optional `hyperedges`, and confidence labels (`EXTRACTED`, `INFERRED`, `AMBIGUOUS`).

## Extending languages

Add an `extract_<lang>` function, register suffixes in `extract()` dispatch, extend `CODE_EXTENSIONS` in `detect.py`, add tree-sitter dependency in `pyproject.toml`, and add fixtures under `tests/`.

## Licensing

Graphify-derived files remain under the **MIT License** and upstream copyright where applicable; see [LICENSE](../LICENSE).
