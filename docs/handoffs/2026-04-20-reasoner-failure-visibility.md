# Handoff: reasoner failure visibility + evidence gating

Date: 2026-04-20

## Context

A Gemma 4 dataset pipeline run was reported as successful while producing
zero findings. Investigation showed two compounding problems:

1. The dataset's `source_file` references did not match the checkout
   passed as `--repo-root`, so bundles fell back to label-only snippets
   and produced very weak prompts.
2. The reasoner caught every provider exception broadly, so silent JSON
   parse failures and HTTP errors disappeared from the run summary, and
   the pipeline reported "0 findings" instead of "all 48 reasoner calls
   failed".

The plan
`.cursor/plans/fix-zero-findings-gemma-run.plan.md` addressed both
clusters. This handoff documents the resulting changes.

## What changed

### Schemas and aggregate stats

- `depos/analysis/schemas.py`
  - `CodeSnippet` now records `evidence_quality`
    (`full` / `embedded` / `label_only` / `missing`) and `resolved_via`
    (which source root or alias produced the text).
  - New `BundleEvidence` model summarizes per-bundle evidence quality and
    a numeric `evidence_score` used to gate reasoner calls.
  - `ReasonerQueueRow` extended with `failure_reason`, `http_status`,
    `attempt_count`, `validation_errors`, `raw_response_excerpt`,
    `provider_name`, `model`, `request_payload_sha256`, etc., so replay
    rows are self-describing.
  - New `ReasonerCallStats` aggregator with `attempts`, `successes`,
    `failures`, and per-mode / per-reason breakdowns. It supports merging
    so module-level stats can be rolled up at the run level.
  - `RunMetadata` and `RunResult` now carry `reasoner_call_stats`,
    `reasoner_run_health` (`ok` / `degraded` / `failed`),
    `reasoner_health_reason`, `bundles_built`,
    `bundles_sent_to_reasoner`, `bundles_skipped_low_evidence`,
    `evidence_summary`, and `dataset_path_resolution`.

### Reasoning engine

- `depos/analysis/reasoning_engine.py` rewritten:
  - Typed `ProviderError` dispatch separates `not_json`,
    `json_but_invalid_schema`, `http_error`, `timeout`, `auth_error`, and
    `validation_error`.
  - Configurable response-path extraction
    (`gemma_response_path`, `openai_response_path`,
    `ollama_response_path`) with a fallback chain so different providers
    can return JSON in different envelopes.
  - JSON repair pass strips fences, trailing commas, and unwraps common
    envelopes before validation.
  - Per-prompt cache to `<run_dir>/prompts/<sha>.json` enables
    deterministic replay.
  - `replay_one` accepts an explicit `run_id`; new
    `depos-intel detectors replay` CLI subcommand drives it.

### Context bundling and AST normalization

- `depos/analysis/context_bundle.py`
  - `_read_snippet_for` accepts a list of `source_roots` and a
    `path_aliases` map, prefers full source text, then embedded text,
    then label-only fallback, and assigns `evidence_quality` /
    `resolved_via` accordingly.
  - `build_bundle` accepts the same args, computes `BundleEvidence`, and
    its truncation policy now drops `label_only` snippets first so
    full-text evidence survives budget pressure.
- `depos/analysis/ast_normalize.py`
  - `_read_source_text` iterates a list of roots and applies path
    aliases.
  - Each node carries `source_resolved_via`.
  - `normalize_dataset_dir` writes `dataset_path_resolution.json` with
    per-file resolution outcomes.

### CLI

- `depos/cli/__init__.py` and `depos/cli/analyze.py`
  - New flags on `dataset-pipeline` and `bundle-pipeline`:
    `--source-root` (repeatable), `--path-alias from=to` (repeatable),
    `--min-evidence {full,embedded,label_only}`, and `--strict`.
  - `--strict` exit codes:
    `0` ok, `2` reasoner degraded, `3` path resolution below threshold,
    `4` reasoner failed.
  - `run_summary.json` is written next to each run.
  - New top-level `depos-intel detectors replay --run-id <id> --mode A
    --max <n> --provider <name>` subcommand.

### Pipeline and config

- `depos/analysis/pipeline.py` gates reasoner calls on
  `bundle.evidence.evidence_score >=
  config.bundles.min_evidence_score_for_reasoner`, accumulates
  `ReasonerCallStats` across modes, and returns the same
  `RunResult` shape that the CLI now persists.
- `depos/analysis/config.py` adds `extra_source_roots`, `path_aliases`,
  `min_snippet_chars`, `min_evidence`,
  `min_evidence_score_for_reasoner`, and per-provider
  `*_response_path`. All are loadable from environment variables.
- `depos/analysis/candidate_identifier.py` rebalances candidate
  diversity for `full_repo_scan`: lowers `auth_boundary`'s priority,
  bumps `graph_anomaly` priorities, and adds a `dataset_unresolved`
  seed family so unresolved AST nodes still get investigation
  candidates.

### Persistence

- `supabase/migrations/20260420120000_intelligence_runs_reasoner_health.sql`
  adds the matching columns to `intelligence_runs`:
  `reasoner_run_health`, `reasoner_health_reason`,
  `reasoner_attempts`, `reasoner_successes`, `reasoner_failures`,
  `reasoner_failure_breakdown`, `evidence_summary`, `bundles_built`,
  `bundles_sent_to_reasoner`, `bundles_skipped_low_evidence`,
  `dataset_path_resolution`. A partial index on
  `(org_id, started_at desc) where reasoner_run_health <> 'ok'` lets the
  UI surface non-ok runs cheaply.
- `depos/db.py` mirrors those columns on the SQLAlchemy model.
- `depos/api_server.py` extends `IntelligenceRunCreate` with the same
  optional fields.
- `depos/intelligence_store.py` persists them in `persist_intelligence_run`.

### Tests

- `tests/dataset_pipeline/test_zero_findings_regression.py` pins three
  scenarios end-to-end against `tests/fixtures/datasets/tiny_drift/`:
  1. Stub provider with the right `--source-root` produces a healthy
     run (`reasoner_run_health == "ok"`).
  2. Wrong `--source-root` under `--strict` exits with the
     path-resolution code (2 or 3).
  3. Mode A returning malformed JSON for every call still produces
     successful B/C calls and records the per-reason breakdown.

### Documentation

- `docs/dataset-pipeline.md` — new flags documented, an operational
  checklist for verifying a "0 findings" run, and a section on
  replaying queued reasoner calls.
- `docs/runbooks/reasoner-zero-findings.md` — failure-reason → fix map
  and the strict-mode exit code table.

## Operational impact

- A "0 findings" run now means one of:
  - `reasoner_run_health == "ok"` and bundles were sent (clean
    negative), or
  - the `run_summary.json` says exactly which combination of weak
    evidence or reasoner failure caused it.
- CI can adopt `--strict` to fail when path resolution drifts or the
  reasoner degrades, instead of accepting silent green runs.
- The Supabase columns let the operator UI distinguish healthy runs
  from degraded/failed runs at a glance.

## Follow-ups

- Wire the new `intelligence_runs` columns into the operator UI so
  degraded/failed runs are visible without opening artifacts.
- Add a small CLI helper that diffs `dataset_path_resolution.json`
  between two runs to make it easy to confirm a `--source-root` change
  actually fixed resolution.
- Once enough replay data is collected, consider promoting the
  `failure_reason` taxonomy into a dedicated dashboard panel.
