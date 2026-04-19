# depOS - dataset pipeline

This guide explains how to run the depOS intelligence pipeline starting from the raw per-file AST JSON files under `dataset/`, through GraphCodeBERT scoring, into Gemma 4 reasoning, verifier checks, and gray-zone evaluation.

It is intended for contributors working with the current sample dataset format in this repo.

> **Team note (Apr 2026):** The **GraphCodeBERT** and **Gemma 4** stages still need a **focused backend review** (model versions, prompts, artifact contracts, reproducibility). See the current handoff: [`handoffs/2026-04-19-web-auth-landing-supabase.md`](handoffs/2026-04-19-web-auth-landing-supabase.md) — *Still to do*.

## What this pipeline does

The `dataset-pipeline` CLI command runs these stages:

1. Read raw AST JSON files from `dataset/`.
2. Normalize them into a graphify-valid enriched graph.
3. Generate depOS candidates.
4. Build context bundles.
5. Score bundles with GraphCodeBERT.
6. Send the top-ranked bundles to Gemma.
7. Run verifier checks.
8. Run gray-zone evaluation for ambiguous findings.
9. Write intermediate and final artifacts to disk.

The command is:

```powershell
depos-intel analyze dataset-pipeline --dataset-dir dataset --repo-root . --output-dir graphify-out/dataset-pipeline-gemma4 --top-n 20
```

## Required input data

The current dataset path expects a directory of individual AST JSON files, usually one file per source file.

Each JSON file should contain at least:

- `nodes`
- `edges`
- AST node `id`
- AST node `kind`
- AST node `label`
- AST node `span.start.line`
- AST node `span.end.line`
- child edges using `source_id`, `target_id`, and `type: "child"`

The normalizer also expects AST node IDs to follow the existing dataset pattern:

```text
ast:<commit_sha>:<source_file>:<start_byte>:<end_byte>:<kind>
```

Example:

```text
ast:5ad818789483d573d65008302d60e6e0b4cacf5b:backend/app/main.py:0:27:import_from_statement
```

If `source_file` cannot be inferred from those IDs, normalization will fail.

## What the normalizer adds

The raw AST dataset is too leaf-heavy for the depOS intelligence pipeline. The normalizer in [depos/analysis/ast_normalize.py](../depos/analysis/ast_normalize.py) promotes it into richer entities and edges.

It currently synthesizes:

- file entities
- function entities
- class entities
- import entities
- `CONTAINS` edges
- `IMPORTS` edges
- inferred `CALLS` edges

It also writes depOS-friendly node attributes such as:

- `label`
- `source_file`
- `start_line`
- `end_line`
- `embedded_text`
- `synthetic_entity`
- `entity_kind`

Those fields matter because candidates, bundles, GraphCodeBERT, and Gemma all depend on them.

## Environment and install

Use a virtualenv with the intelligence dependencies installed.

From the repo root:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[intelligence]"
```

If PowerShell activation is blocked, use the interpreter directly:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[intelligence]"
```

## Important environment variables

The pipeline reads configuration from environment variables through [depos/analysis/config.py](../depos/analysis/config.py).

Most useful settings:

- `DEPOS_INTEL_PROVIDER`
- `GEMMA_API_URL`
- `GEMMA_MODEL`
- `OLLAMA_HOST`
- `DEPOS_DATA`

### Gemma 4 over Ollama

If you are using Ollama locally with Gemma 4:

```powershell
$env:DEPOS_INTEL_PROVIDER="gemma"
$env:GEMMA_API_URL="http://localhost:11434/api/generate"
$env:GEMMA_MODEL="gemma4:e4b"
```

If you prefer the repo's Ollama provider path instead:

```powershell
$env:DEPOS_INTEL_PROVIDER="ollama"
$env:OLLAMA_HOST="http://localhost:11434"
```

### Optional output location

To control depOS run-output storage:

```powershell
$env:DEPOS_DATA="C:\\path\\to\\depos-data"
```

## One-command end-to-end run

This is the recommended command for this dataset:

```powershell
depos-intel analyze dataset-pipeline --dataset-dir dataset --repo-root . --output-dir graphify-out/dataset-pipeline-gemma4 --top-n 20
```

Useful options:

- `--dataset-dir`
  Path to the directory containing the raw AST JSON files.
- `--repo-root`
  Root of the actual source tree so the normalizer can read source files and embed real snippets.
- `--output-dir`
  Directory where all intermediate and final artifacts are written.
- `--top-n`
  Number of top GraphCodeBERT-ranked bundles to send to Gemma.
- `--max-bundles`
  Cap bundle creation earlier in the pipeline.
- `--min-score`
  Skip bundles below a GraphCodeBERT threshold.
- `--write-extraction`
  Persist the normalized extraction JSON in addition to the node-link graph.
- `--local-files-only`
  Avoid downloading model files from Hugging Face if they are already cached.
- `--device`
  Force GraphCodeBERT device, for example `cpu`.
- `--model-name`
  Override GraphCodeBERT model name. Default is `microsoft/graphcodebert-base`.

Example with extra controls:

```powershell
depos-intel analyze dataset-pipeline --dataset-dir dataset --repo-root . --output-dir graphify-out/dataset-pipeline-gemma4 --top-n 20 --min-score 0.72 --write-extraction
```

## Output artifacts

The command writes these intermediate artifacts under the chosen output directory:

- `dataset-normalized-node-link.json`
- `dataset-normalized-extraction.json` if `--write-extraction` is used
- `candidates.json`
- `bundles.json`
- `bundle-scores.json`

Final reasoning artifacts are written under:

- `gemma4-run/violations.json`
- `gemma4-run/gray_zone_audit.jsonl`
- `gemma4-run/bundle_pipeline_trace.json`

## What each artifact means

### `dataset-normalized-node-link.json`

The enriched graph used by the rest of the pipeline.

### `candidates.json`

Module 2 candidate seeds. These are not findings. They are investigation targets.

### `bundles.json`

Module 3 context bundles. These are the evidence packs fed into GraphCodeBERT and Gemma.

### `bundle-scores.json`

GraphCodeBERT ranking output. Each row contains:

- `bundle_id`
- `candidate_id`
- `scope_id`
- `graphcodebert_score`
- `graphcodebert_pattern`
- `top_patterns`

### `gemma4-run/violations.json`

Final surfaced findings after Gemma, verifier, and gray-zone processing.

### `gemma4-run/gray_zone_audit.jsonl`

Audit log for ambiguous findings that entered the gray-zone evaluator.

### `gemma4-run/bundle_pipeline_trace.json`

Per-bundle trace of:

- selected bundle
- GraphCodeBERT score and pattern
- which Gemma modes returned
- how many findings came out of verifier for that bundle

## Recommended run order while developing

If you want to inspect each step manually instead of using the one-command path:

1. Normalize the dataset.
2. Inspect the normalized graph.
3. Generate candidates and bundles.
4. Score bundles with GraphCodeBERT.
5. Run Gemma on the top-ranked bundles.
6. Inspect verifier and gray-zone outputs.

The dedicated commands are:

```powershell
depos-intel analyze normalize-dataset --dataset-dir dataset --repo-root . --output graphify-out/dataset-normalized-node-link.json --extraction-output graphify-out/dataset-normalized-extraction.json
```

```powershell
depos-intel analyze score-bundles --bundles-json graphify-out/bundles.json --output graphify-out/bundle-scores.json
```

```powershell
depos-intel analyze bundle-pipeline --bundles-json graphify-out/bundles.json --scores-json graphify-out/bundle-scores.json --graph-json graphify-out/dataset-normalized-node-link.json --top-n 20 --output-dir graphify-out/gemma4-run
```

## Current contributor notes for this dataset

### 1. The dataset is not native graphify extraction output

The files under `dataset/` are AST-shaped JSON, not graphify's full extraction schema. Do not feed them directly into the depOS intelligence pipeline if you want good results. Run them through `normalize-dataset` or `dataset-pipeline`.

### 2. `repo_root` matters

Pass `--repo-root .` when the actual source files exist locally. The normalizer uses that to read source text and produce better `embedded_text` and snippets. Without it, bundles are still usable, but thinner.

### 3. This command intentionally avoids git-diff seeding

The dataset pipeline uses an empty manual manifest so it does not accidentally seed candidates from the current git diff of the repo you are editing. That keeps the run focused on the dataset graph instead of local documentation or code edits.

### 4. The normalizer is heuristic

`IMPORTS` and `CALLS` are inferred from AST labels and local structure. They are useful, but they are not as precise as a purpose-built semantic extractor. If you extend the dataset schema later, prefer improving the normalizer instead of bypassing it.

### 5. GraphCodeBERT is a ranking prior, not a verdict

The score is only used to prioritize which bundles Gemma sees first. It does not confirm a bug by itself.

### 6. `confirmed` is still verifier-only

Gray-zone and Gemma outputs can help surface results, but they must not blur the trust boundary:

- `confirmed` means verifier-supported
- `evaluator_surfaced` means panel-supported but not mechanically proven

### 7. Thin outputs usually mean thin graph inputs

If Gemma returns no findings and gray-zone is empty, first inspect:

- `candidates.json`
- `bundles.json`
- `bundle-scores.json`

In practice the most common cause is weak graph enrichment, not a broken reasoner.

## Troubleshooting

### `ModuleNotFoundError: networkx`

Use the repo virtualenv interpreter instead of a different Python launcher.

### Hugging Face load warnings with GraphCodeBERT

Warnings about `lm_head.*` being `UNEXPECTED` and `pooler.*` being `MISSING` are normal for this embedding-style use of `microsoft/graphcodebert-base`.

### `pytest` is missing in the venv

If you want to run tests locally:

```powershell
python -m pip install pytest
```

### Gemma is not configured

Check:

```powershell
echo $env:DEPOS_INTEL_PROVIDER
echo $env:GEMMA_API_URL
echo $env:GEMMA_MODEL
```

## Example contributor workflow

```powershell
.venv\Scripts\Activate.ps1
$env:DEPOS_INTEL_PROVIDER="gemma"
$env:GEMMA_API_URL="http://localhost:11434/api/generate"
$env:GEMMA_MODEL="gemma4:e4b"

depos-intel analyze dataset-pipeline --dataset-dir dataset --repo-root . --output-dir graphify-out/dataset-pipeline-gemma4 --top-n 20 --write-extraction
```

Then inspect:

```powershell
Get-Content graphify-out\dataset-pipeline-gemma4\bundle-scores.json -TotalCount 80
Get-Content graphify-out\dataset-pipeline-gemma4\gemma4-run\bundle_pipeline_trace.json -TotalCount 120
Get-Content graphify-out\dataset-pipeline-gemma4\gemma4-run\violations.json -TotalCount 160
Get-Content graphify-out\dataset-pipeline-gemma4\gemma4-run\gray_zone_audit.jsonl -TotalCount 80
```
