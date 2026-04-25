# Intent Context Layer

The Intent Context Layer discovers **intent-bearing documentation** (Markdown, READMEs, ADRs, GitHub policy docs), normalizes and **chunks** it, then emits a **versioned, provenance-rich intermediate representation (IR)** for downstream consumers (for example a future Graphical Context Layer that compares intent to the AST graph).

It does **not** mutate the code graph or tree-sitter output. Intent entries are **claims with evidence** (file, chunk, line ranges), not ground truth.

## Pipeline order (top-down)

```text
checkout_at_SHA
  → intent-context build   (this layer)
  → graphify snapshot      (structural truth)
  → graphical context / detectors / rank / reason
```

Intent artifacts are designed to feed **graphical context** and similar tools; the detector spine can stay unchanged until you wire cross-layer signals.

## CLI

```bash
depos-intel intent-context build --repo-root . --output-dir ./intent-out
```

- **`--intent-llm auto|rules|llm`** — Overrides `DEPOS_INTEL_INTENT_LLM`. Default **`auto`**: if `OPENAI_API_KEY` is set, runs **`llm_v0`** unit extraction plus file/repo summaries **in addition to** **`rules_v0`**. With **`rules`**, no network calls (CI-friendly). With **`llm`**, OpenAI is **required**; the command exits non-zero if the key is missing.

## Configuration

| Env / setting | Purpose |
|----------------|---------|
| `OPENAI_API_KEY` | When set and mode is `auto`, enables the LLM add-on (same variable as the reasoner). |
| `OPENAI_MODEL` | Default chat model; reused unless `DEPOS_INTEL_INTENT_MODEL` is set. |
| `DEPOS_INTEL_INTENT_LLM` | `auto` (default), `rules`, or `llm`. |
| `DEPOS_INTEL_INTENT_MODEL` | Optional model override **only** for intent extraction/summaries. |
| `DEPOS_INTEL_INTENT_MAX_TOKENS`, `..._MAX_REPO_BYTES`, `..._MAX_CHUNKS`, `..._MAX_FILE_BYTES`, `..._CHUNK_CHARS`, `..._CHUNK_OVERLAP` | Caps and chunking (see [`depos/analysis/config.py`](../depos/analysis/config.py) `IntentContextConfig`). |
| `DEPOS_INTEL_INTENT_FENCED` | `strip` (default) or `annotate` — fenced ``` blocks are removed or replaced with an HTML comment marker in chunk text. |
| `DEPOS_INTEL_INTENT_TAG_SCAN` | `1` (default) or `0` — scan code globs for OpenFastTrace-style tags (`[impl->req~foo~1]`). |

Optional repo config: **`.depos/intent.yaml`**

```yaml
include_globs:
  - "design/**/*.md"
exclude_globs:
  - "**/vendor/**"
```

## Artifacts (output directory)

| File | Description |
|------|-------------|
| `intent_manifest.json` | Repo SHA (`git rev-parse` when available), timestamps, per-file `sha256` / byte counts, `path_classification` (`intent` vs `mixed`), parse and truncation warnings, LLM stats when enabled, chunk/unit counts. |
| `intent_chunks.jsonl` | One JSON object per line: `chunk_id`, `source_relpath`, `start_line`, `end_line`, `heading_stack`, `text`, `path_classification`. Line numbers refer to **normalized** text (after fenced-code policy), not necessarily original file lines. |
| `intent_units.json` | Array of **IntentUnit**: `unit_id`, `kind`, `natural_language`, `scope_hints`, `evidence[]`, `extractor` (`rules_v0`, `oft_markdown_v0`, or `llm_v0`), `confidence`. Optional **OFT fields** when `extractor` is `oft_markdown_v0`: `oft_spec_item_id`, `oft_needs`, `oft_covers`, `oft_depends`, `oft_status`, `oft_rationale_excerpt`, etc. |
| `intent_coverage_tags.jsonl` | One JSON object per line: coverage references found in source comments (long form `[impl->req~id~1]`, short form `[[name:rev]]`). |
| `intent_trace_hints.json` | Lightweight graph hint: **nodes** (OFT spec IDs from docs), **edges** (`covers`, `depends` from parsed doc blocks), **coverage_tags** (raw tag locations for joining to the AST by path/line). Not a full OpenFastTrace `aspec` export. |
| `intent_file_summaries.jsonl` | When LLM add-on runs: one JSON object per file (`summary`, `bullet_claims`, `chunk_ids`). Otherwise a single stub line with `skipped_reason`. |
| `intent_repo_summary.json` | When LLM add-on produces a rollup: `summary`, `themes`, `file_relpaths`. Otherwise a stub with `skipped_reason`. |

## OpenFastTrace interoperability (optional strict layer)

[OpenFastTrace](https://github.com/itsallcode/openfasttrace) models **specification items** with stable IDs (`` `type~name~revision` ``), `Needs` / `Covers` / `Depends`, revisions that invalidate stale links, and **code comment tags** pointing from implementation to spec IDs.

graphify’s intent layer **does not replace** OFT or embed the Java engine. It **consumes compatible Markdown** and **tag shapes** so you can mix:

- **Broad discovery:** `rules_v0` + `llm_v0` on normal READMEs and ADRs.
- **Audit-grade items:** when authors use OFT-style IDs in backticks, `oft_markdown_v0` emits structured units plus `intent_trace_hints.json` edges for `Covers` / `Depends`.

**Scan guards:** HTML comments `<!-- oft:off -->` … `<!-- oft:on -->` (and RST-style `.. oft:off` / `.. oft:on`) strip regions before chunking—same idea as OFT’s `oft:off` switch so examples do not create false spec items.

**Merge precedence (recommended for consumers):** When multiple units cite the same `chunk_id`, prefer **higher `confidence`**. If tied, prefer **`oft_markdown_v0`** (explicit ID) over `llm_v0`, then over `rules_v0` heuristics—unless you explicitly want LLM nuance to override weak OFT stubs.

**Do not** treat OFT tag presence or `Needs` lists as proof of correctness—only as **link evidence**; the AST graph and detectors still own behavior truth.

## Graphical Context Layer — input spec (handoff)

**Required for alignment work**

1. **`intent_manifest.repo_sha`** — Tie the IR to the same commit as the graph snapshot.
2. **`intent_chunks.jsonl`** — Stable **`chunk_id`** keys; all **`intent_units[].evidence[].chunk_id`** MUST reference existing chunks.
3. **`intent_units.json`** — Treat each row as a **hypothesis** (`extractor` + `confidence`); never treat as confirmed bugs.
4. **`path_classification`** — `mixed` hints that prose lives next to implementation trees (higher drift risk).

**Merge policy (v1):** If `rules_v0` and `llm_v0` cite the same `chunk_id`, prefer higher **`confidence`**, or prefer **`llm_v0`** if equal. If **`oft_markdown_v0`** is present for the same chunk, prefer it over heuristic `rules_v0` (explicit spec ID). Document any different policy in your consumer.

## Implementation layout

- Package: [`depos/intent_context/`](../depos/intent_context/)
- Glob / path hygiene patterns align with [`depos/ingest/prompts.py`](../depos/ingest/prompts.py) (walk + denylist); intent IR stays **separate** from the code graph.

## Non-goals

- No NetworkX / graph mutation from this layer.
- No SARIF or “confirmed vulnerability” wording—only **intent claims**.
- No automatic graph edges from LLM output without a separate verification story.
