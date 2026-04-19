# Runbook: reasoner produced zero findings

Use this runbook when a dataset or bundle pipeline run reports "0 findings"
and you need to know whether that is a genuine clean negative or a silent
failure.

It maps the `failure_reason` values written into
`gemma4-run/run_summary.json` and `reasoner_queue.jsonl` to concrete
operator actions.

## 1. Triage in 30 seconds

Open `<output-dir>/gemma4-run/run_summary.json` and check, in order:

1. `reasoner_run_health` — `ok`, `degraded`, or `failed`.
2. `reasoner_call_stats.attempts` vs `successes` vs `failures`.
3. `reasoner_call_stats.by_reason` — which failure clusters dominate.
4. `evidence_summary.bundles_skipped_low_evidence` — was anything sent at
   all?
5. `dataset_path_resolution.summary.resolution_ratio` (top-level
   `dataset_path_resolution.json`) — did the normalizer find real source?

The combination of those five fields is enough to point at the right fix
below.

## 2. Strict-mode exit codes

When `--strict` is passed, the CLI maps run health onto exit codes so CI
can distinguish failure modes:

| Exit code | Meaning |
| --------- | ------- |
| `0` | Run is healthy. `reasoner_run_health == "ok"` and path resolution is acceptable. |
| `2` | Reasoner health is `degraded`. Some calls failed; some succeeded. |
| `3` | Path resolution is below threshold. Most `source_file` references did not resolve against any provided source root. Bundles fell back to `label_only` or `missing` snippets. |
| `4` | Reasoner health is `failed`. Every reasoner call failed. |

Without `--strict`, the run always exits `0` and the same information is
available in `run_summary.json` for tooling to consume.

## 3. Failure reason → fix

`failure_reason` is written on each row of `reasoner_queue.jsonl` and
aggregated under `reasoner_call_stats.by_reason` in `run_summary.json`.

### `not_json`

The provider returned a body that did not parse as JSON at all (typical
for chatty Gemma/Ollama prompts where the model added prose around the
JSON envelope).

**Fix:**

- Confirm the provider's response path is correct. Configure
  `gemma_response_path`, `openai_response_path`, or `ollama_response_path`
  in `IntelligenceConfig`/env to extract the JSON body from the provider
  envelope.
- Lower the temperature on the provider if the model is paraphrasing
  instead of returning JSON.
- For one-off recovery, replay queued rows after fixing config:
  `depos-intel detectors replay --run-id <id> --mode A`.

### `json_but_invalid_schema` (also surfaces as `validation_error`)

The body parsed as JSON but failed the Pydantic schema for the mode
(`ModeAOutput` / `ModeBOutput` / `ModeCOutput`). The replay row contains
the validation errors so you can see which fields the model omitted or
reshaped.

**Fix:**

- Inspect `validation_errors` and `raw_response_excerpt` on the queue row.
- Update the prompt template if the model is consistently producing the
  wrong envelope. The repair pass already strips fences and trailing
  commas; truly off-schema output needs prompt-level work.
- Replay after the prompt change:
  `depos-intel detectors replay --run-id <id> --mode <mode>`.

### `http_error` and `timeout`

The provider returned a non-2xx HTTP status (or did not respond in time).
`http_status` and `provider_name` on the queue row identify which call
failed.

**Fix:**

- For local Ollama/Gemma: confirm the daemon is running and reachable on
  the configured host.
- For OpenAI: check API key validity and rate-limit status.
- After resolving the upstream issue, replay with
  `depos-intel detectors replay --run-id <id> --max <n>`.

### `auth_error`

A 401 / 403 from the provider.

**Fix:** rotate or re-set the credentials env var
(`OPENAI_API_KEY`, etc.) and replay.

### `unknown` / unset

Either the failure reason did not match a known typed exception, or the
queue row was written by an older pipeline build.

**Fix:** read `raw_response_excerpt` and the stderr log from the run. If
the failure recurs on a current build, file an issue with the queue row
attached.

## 4. When the failure is *not* the reasoner

Every step above assumes calls reached the model. If the run summary shows
`bundles_built > 0` but `bundles_sent_to_reasoner == 0`, the evidence
gate skipped everything. That is almost always a path-resolution problem:

1. Inspect `dataset_path_resolution.json`. The `unresolved_files` array
   lists every `source_file` that no source root could satisfy.
2. Add the missing roots with one or more `--source-root <path>` flags.
3. Add prefix rewrites with `--path-alias from=to` for monorepo layouts
   where the dataset paths do not match the checkout exactly.
4. Re-run the dataset pipeline. The `evidence_summary.by_quality`
   histogram should shift away from `label_only` / `missing` toward
   `embedded` / `full`.

If resolution is good but bundles are still being skipped, lower
`min_evidence_score_for_reasoner` (env: `DEPOS_INTEL_MIN_EVIDENCE_SCORE`)
or pass `--min-evidence label_only` to drop the gate to its floor.

## 5. Related references

- [`docs/dataset-pipeline.md`](../dataset-pipeline.md) — the full pipeline
  guide, including the operational checklist.
- `depos/analysis/reasoning_engine.py` — typed exception dispatch and
  queue-row writer.
- `depos/analysis/context_bundle.py` — evidence-quality computation.
- `depos/analysis/ast_normalize.py` — path-resolution report writer.
