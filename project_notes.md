# Project Notes

## 2026-05-20: FTS5 Full-Text Search + Node Descriptions (PLAN)

### Goal

Add ranked full-text search over the knowledge graph. Enables discovery of nodes by concept (not just exact label match), especially when meaning lives in docstrings/comments rather than function names.

### What to implement

**1. Node description extraction (`graphify/extract.py`)**

Add `_extract_description(node, source, config)` before `_extract_generic` (~line 1158):
- Strategy 1 — Docstring in body: first `expression_statement > string` (Python) or first `comment` child (JS/Java/C)
- Strategy 2 — Leading comment: `node.prev_named_sibling` of type `comment`, strip `///`, `//!`, `//`, `#`, `/*`, `/**`
- Filters: reject decorative separators (`---`, `===`), require >10 chars
- Post-process: collapse whitespace, truncate to 200 chars + `...`

Modify `add_node()` inner function (~line 1202):
```python
def add_node(nid: str, label: str, line: int, description: str = "") -> None:
    ...
    if description:
        node_dict["description"] = description
```

Call at class/function node creation points in `_extract_generic` and language-specific walkers (`_js_extra_walk`, `_csharp_extra_walk`, `_swift_extra_walk`).

**2. DB schema + FTS5 index (`graphify/db.py`)**

Schema:
- Add `description TEXT DEFAULT ''` column to `nodes` table
- Add `"description"` to `_NODE_TYPED` set
- New FTS5 virtual table:
  ```sql
  CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
      label, description, source_file,
      content='nodes', content_rowid='rowid'
  );
  ```
- Bump `SCHEMA_VERSION` to 2

`_insert_node()`: include `attrs.get("description", "")` in INSERT.

`save_db()`: after all node inserts, populate FTS:
```sql
INSERT INTO nodes_fts(rowid, label, description, source_file)
SELECT rowid, COALESCE(label,''), COALESCE(description,''), COALESCE(source_file,'') FROM nodes
```

Migration for old DBs in `_connect()`:
- Detect v1 schema → `ALTER TABLE nodes ADD COLUMN description TEXT DEFAULT ''`
- Create FTS table, populate from existing nodes, update meta version

New `search(path, query, limit=20)` function:
- Check `nodes_fts` exists in `sqlite_master` (backward compat)
- Build FTS query: `" OR ".join(f"{t}*" for t in terms)` (prefix matching)
- Execute: `SELECT n.id, n.label, n.description, n.source_file, n.community, bm25(nodes_fts, 5.0, 10.0, 1.0) AS rank FROM nodes_fts f JOIN nodes n ON f.rowid = n.rowid WHERE nodes_fts MATCH ? ORDER BY rank LIMIT ?`
- BM25 weights: label=5.0, description=10.0, source_file=1.0
- Fallback to `search_label()` on exception or missing FTS table
- Return: `[{"id", "label", "description", "score", "source_file", "community"}, ...]`

Update `load_db()`: load `description` into NetworkX node attrs.
Update `get_node()`: include `description` in SELECT and returned dict.

**3. Public API (`graphify/store.py`)**

New `search(out_dir, query, limit=20)` function:
- DB backend: call `db.search()`
- JSON backend: in-memory scoring (label=1.0, description=1.5, source_file=0.5 per matching term)

**4. Skill prompt update (`graphify/skill.md` + all variants)**

Add `"description"` to node JSON schema:
```json
{"id":"...", "label":"...", "description":"One sentence explaining what this entity does or represents", ...}
```

Ensures LLM-extracted nodes (PDFs, images, docs) also get descriptions.

**5. aa-service search endpoint (`main.py`)**

```python
@app.get("/kb/{kb_id}/search")
async def search_kb(kb_id: str, q: str, limit: int = 20):
    hits = store.search(kb["graphify_out"], q, limit=limit)
    return {"query": q, "hits": hits}
```

Add to discovery manifest.

**6. Merge behavior**

Same as graphify-mw: AST nodes extracted first (with docstring descriptions), then LLM semantic nodes overwrite via same-ID merge in `build.py`. Semantic descriptions take precedence when both exist.

**7. Tests**

`tests/test_fts.py`:
- `test_save_db_creates_fts_table`
- `test_search_finds_by_label` (exact + prefix)
- `test_search_finds_by_description` (term in description but not label)
- `test_search_finds_by_source_file`
- `test_search_bm25_ranking` (description match ranks higher)
- `test_search_fallback_no_fts` (old DB without FTS)
- `test_search_empty_query`

`tests/test_description_extract.py`:
- `test_python_docstring_extraction`
- `test_leading_comment_extraction`
- `test_decorative_separator_filtered`
- `test_truncation_200_chars`
- `test_no_description_returns_empty`

### Agent workflow enabled

```
1. GET  /kb/{kb_id}/search?q=terms    → ranked node discovery via FTS (BM25)
2. POST /kb/{kb_id}/explain {node_id} → node + neighbors + community
3. POST /kb/{kb_id}/query {question}  → BFS/DFS subgraph traversal from seeds
4. GET  /kb/{kb_id}/dashboard         → interactive HTML dashboard
```

### File change summary

| File | Change |
|------|--------|
| `graphify/extract.py` | `_extract_description()`, modify `add_node()`, call at class/function creation |
| `graphify/db.py` | `description` column, FTS5 table, `search()`, schema migration v1→v2, update `load_db`/`get_node` |
| `graphify/store.py` | `search()` public function |
| `graphify/skill.md` (+ variants) | `description` field in node schema |
| `aa-service/main.py` | `GET /kb/{kb_id}/search` endpoint |
| `tests/test_fts.py` | FTS search tests |
| `tests/test_description_extract.py` | Description extraction tests |

### Future features (not in this implementation)

**A. Community summaries**

Generate 1-2 sentence descriptions per community cluster (beyond the current short labels in `.graphify_labels.json`). Store in a `communities` table in graph.db. APIs that would use them:
- `GET /kb/{kb_id}/search` — enrich results with community context
- `POST /kb/{kb_id}/query` — traversal text shows community summary instead of bare ID
- `POST /kb/{kb_id}/explain` — node detail includes community summary
- `GET /kb/{kb_id}/stats` — cluster overview with summaries
- `GET /kb/{kb_id}/dashboard` — community table gains summary column
- New `GET /kb/{kb_id}/communities` endpoint — orientation: list all clusters with label, summary, node count, cohesion

**B. Wire FTS into query seed selection**

Replace `_score_nodes()` (substring LIKE matching) in `POST /kb/{kb_id}/query` with `store.search()` for BFS/DFS seed finding. Benefits: BM25 ranking, prefix matching, description-aware discovery. No breaking change since `search()` falls back to `score_nodes()` on old DBs.

---

## 2026-05-16: Domain Plugin System

Added a plugin architecture that extends graphify for non-code domains (finance, due diligence) without modifying core modules.

### New Files

- `graphify/domain.py` — DomainSpec dataclass, Protocol, registry, entry-point discovery
- `graphify/shared/tables.py` — HTML table extraction, layout filtering, Table dataclass, graph conversion
- `graphify/shared/spreadsheet.py` — Excel/CSV → Table (merged cells, sub-table split)
- `graphify/shared/pdf_tables.py` — 3-tier PDF table extraction (basic/plumber/vision)
- `graphify/domains/finance.py` — Finance domain (counterparties, covenants, concentration risk)
- `graphify/domains/diligence.py` — Due diligence domain (conflict inference, red flags, key-person risk)
- `tests/test_domain.py`, `tests/test_tables.py`, `tests/test_spreadsheet.py`, `tests/test_pdf_tables.py`, `tests/test_domains_finance.py`, `tests/test_domains_diligence.py` — 54 tests

### Modified Files

- `graphify/__main__.py` — `--domain` flag + 5 hook insertion points in extract pipeline
- `graphify/llm.py` — `extra_prompt` parameter threaded through extract chain; `system` param on backend calls
- `graphify/skill.md` — `--domain` flag, DOMAIN_NAMES_PLACEHOLDER in Steps 3C and 4
- `pyproject.toml` — `pdf-tables` and `domains` optional deps, `graphify.plugins` entry-points, package list
- `README.md` — "Domain plugins" section with usage, capabilities, and custom domain authoring guide

### Plugin Hook Architecture (5 hooks)

1. `prompt_fragments()` — injected into LLM system prompt before semantic extraction
2. Domain structural extractors — run after core extraction (tables, spreadsheets, PDFs)
3. `post_extract(extraction) → extraction` — mutate nodes/edges before graph build (conflict inference, edge fixing)
4. `post_build(G)` — mutate graph after build+cluster (cross-community contradiction edges)
5. `analyzers` — read-only reporting (concentration risk, red flags, key-person)

### Usage

```bash
# In AI coding assistant
/graphify ./filings --domain finance
/graphify ./dataroom --domain finance,diligence

# Headless CLI (any terminal, no IDE needed)
graphify extract ./filings --backend gemini --domain finance
graphify extract ./corpus --backend gemini --domain finance,diligence
```

Both paths produce the same graph, report, and analysis. The skill path additionally generates `graph.html` with interactive visualization and community labels.

### Design Decisions

- Core stays untouched — code domain is implicit (existing pipeline)
- Domains are additive — new files only, minimal hooks into existing flow
- Node IDs namespaced by domain (`finance__jpmorgan`, `diligence__clause_4_2`)
- Table structure preserved (not flattened to text) via shared Table dataclass
- Layout tables auto-filtered via heuristics (nested, width=100%, role=presentation, etc.)
- Based on graphify-plugin-dd SUMMARY.md patterns (WeWork S-1 case study)
- Relations organized by category (governance, conflict, financial, disclosure, risk)
- Entry-point group: `graphify.plugins` — third-party domains installable via pip

### Domains Implemented

**Finance**: company, security, obligation, covenant, counterparty, fund, metric nodes. Concentration risk analyzer. Post-extract infers concentration edges.

**Due Diligence**: entity, person, contract, clause, risk, liability, asset, IP, role, transaction nodes. Red flag analyzer, key-person risk analyzer. Post-extract infers conflict_of_interest edges. Post-build connects aspirational claims to contradicting mechanisms.

### Test Results

- 51 new tests pass, 3 skipped (openpyxl not in venv)
- 729 existing tests pass with no regressions

---

## graphify pyinstall (pre-existing feature)

`graphify pyinstall` installs a `pyaag` skill that uses `python3` directly instead of the standalone binary. For development/testing without building PyInstaller binaries.

**What it does:**
1. Copies `skill.md` to `~/.claude/skills/pyaag/SKILL.md`
2. Renames skill from `aag` → `pyaag` (frontmatter, trigger)
3. Replaces `from aag.` → `from graphify.` (module imports)
4. Simplifies Step 1 interpreter detection to just `PYTHON=python3`
5. Replaces `$(cat graphify-out/.aag_python) -c` with `python3 -c`
6. Replaces `/aag` references with `/pyaag`

**Usage:**
```bash
cd aa-graphify
bash
export UV_DEFAULT_INDEX=https://mw-python-repository.mathworks.com/artifactory/api/pypi/pypi-repos/simple
uv pip install -e ".[all]"
uv run python -m graphify pyinstall
# Then use /pyaag in Claude Code
```

**Location:** `graphify/__main__.py:352-401`

---

## 2026-05-17: Analysis Dashboard & aa-service Changes

### Dashboard (`graphify/dashboard.py`)

New module that generates a self-contained `dashboard.html` from `.graphify_analysis.json`. Features:
- Dark/light mode (OS preference via `prefers-color-scheme`)
- Sortable tables for all analysis sections
- Sections: summary stats, concentration risk, red flags, key-person risk, god nodes, surprises, communities
- Generic renderer for unknown domain analyzers (auto-tables from arrays)
- No external dependencies — pure inline HTML/CSS/JS

### Integration in `graphify/__main__.py`

- Auto-generates `dashboard.html` after domain extraction (after `.graphify_analysis.json` write, ~line 2851)
- Added `graphify export dashboard [--open]` subcommand to regenerate from existing analysis

### aa-service Changes (`/local-nvme/hfeng/aa/aa-service/main.py`)

- Added `HTMLResponse` import
- Added `GET /kb/{kb_id}/dashboard` endpoint — serves `dashboard.html` from `graphify_out/`, returns 404 if not present
- Added dashboard to discovery manifest endpoint list
- No changes needed for domain nodes/edges — they flow through existing graph/query/path/explain endpoints transparently

### Analyst Workflow

1. Build KB with domain: `graphify extract ./filings --domain finance`
2. `dashboard.html` auto-generated in `graphify-out/`
3. aa-service serves it at `GET /kb/{kb_id}/dashboard`
4. Claude outputs clickable link in Claude Desktop → analyst clicks → browser opens dashboard

### Assessment: What Didn't Need Changing in aa-service

- `GET /kb/{kb_id}/graph` — domain nodes/edges already in graph.json/graph.db
- `POST /kb/{kb_id}/query` — BFS/DFS finds domain nodes by label match
- `POST /kb/{kb_id}/path` — shortest path works across domain and code nodes
- `POST /kb/{kb_id}/explain` — returns any node's connections regardless of namespace
- `GET /kb/{kb_id}/report` — GRAPH_REPORT.md already includes domain sections
- `GET /kb/{kb_id}/stats` — counts include domain nodes

---

## 2026-05-12: Fix `aag export wiki` failing when `.graphify_analysis.json` missing

**Problem:** `aag export wiki` errored with "`.graphify_analysis.json` is missing or empty" even though communities data existed inside `graph.db`.

**Root cause:** The export command (`graphify/__main__.py` ~line 2112) only read communities from `.graphify_analysis.json`. When using the DB backend, `save_db` stores community as a per-node integer attribute, and `load_db` loads it back into the graph's node attributes — but the export code never tried to extract communities from there.

**Fix:** Added a fallback in the `else` branch (~line 2119) that reconstructs the `communities` dict from `G.nodes(data=True)` by reading each node's `community` attribute and inverting it into `{community_id: [node_ids]}`.

**Location:** `graphify/__main__.py:2119-2128`
