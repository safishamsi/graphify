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
| `intent_units.json` | Array of **IntentUnit**: `unit_id`, `kind`, `natural_language`, `scope_hints`, `evidence[]` (`chunk_id`, optional lines), `extractor` (`rules_v0` or `llm_v0`), `confidence`. v1 may emit **both** extractors without deduplication; consumers may prefer higher confidence or `llm_v0` when evidence overlaps. |
| `intent_file_summaries.jsonl` | When LLM add-on runs: one JSON object per file (`summary`, `bullet_claims`, `chunk_ids`). Otherwise a single stub line with `skipped_reason`. |
| `intent_repo_summary.json` | When LLM add-on produces a rollup: `summary`, `themes`, `file_relpaths`. Otherwise a stub with `skipped_reason`. |

## Graphical Context Layer — input spec (handoff)

**Required for alignment work**

1. **`intent_manifest.repo_sha`** — Tie the IR to the same commit as the graph snapshot.
2. **`intent_chunks.jsonl`** — Stable **`chunk_id`** keys; all **`intent_units[].evidence[].chunk_id`** MUST reference existing chunks.
3. **`intent_units.json`** — Treat each row as a **hypothesis** (`extractor` + `confidence`); never treat as confirmed bugs.
4. **`path_classification`** — `mixed` hints that prose lives next to implementation trees (higher drift risk).

**Merge policy (v1):** If both `rules_v0` and `llm_v0` cite the same `chunk_id`, prefer the unit with higher **`confidence`**, or prefer **`llm_v0`** if equal—document the choice in your consumer.

## Implementation layout

- Package: [`depos/intent_context/`](../depos/intent_context/)
- Glob / path hygiene patterns align with [`depos/ingest/prompts.py`](../depos/ingest/prompts.py) (walk + denylist); intent IR stays **separate** from the code graph.

## Non-goals

- No NetworkX / graph mutation from this layer.
- No SARIF or “confirmed vulnerability” wording—only **intent claims**.
- No automatic graph edges from LLM output without a separate verification story.
