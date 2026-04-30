# Cell Maps Pipeline — workflow & enrichment reference
> **Local notes — not part of upstream `idekerlab/cellmaps_pipeline`.**
> Excluded via `.git/info/exclude` so `git status` stays clean.
> Documents what the pipeline does end-to-end, with claims grounded
> in the source code where possible. Sections clearly labeled
> *(verified)* are read directly from source; *(inferred)* are
> reasoned from import names, README narrative, and call sequence.

## Table of contents
1. [What it is](#what-it-is)
2. [Installation](#installation)
3. [Inputs](#inputs)
4. [Execution modes](#execution-modes)
5. [Stage-by-stage workflow](#stage-by-stage-workflow)
6. [Output directory structure](#output-directory-structure)
7. [Stage 4b — Verified enrichment details](#stage-4b--verified-enrichment-details)
8. [CLI flag reference](#cli-flag-reference)
9. [What's verified vs inferred](#whats-verified-vs-inferred)
10. [Citation](#citation)

## What it is
The Cell Maps Pipeline is the orchestrator package of the Ideker Lab's
**Cell Mapping Toolkit**. It integrates two heterogeneous protein-data
modalities — ImmunoFluorescent (IF) imaging from the Human Protein
Atlas plus Affinity-Purification Mass-Spectrometry (AP-MS) interactions —
into a multi-resolution **hierarchical model of subcellular
organization**, registered as RO-Crates with FAIRSCAPE provenance.

The pipeline package itself is small (~1,400 LOC). It does no
scientific computation directly; it composes seven sibling packages
(also from idekerlab) into an ordered DAG.

- License: MIT
- Versions: v1.0.0 (2024-12) → v1.3.0 (2025-07)
- Python: 3.8 – 3.11 (hard pin)
- Repo: <https://github.com/idekerlab/cellmaps_pipeline>
- Citation: Lenkiewicz et al., *Bioinformatics* 2025 (`btaf205`)

## Installation
```bash
pip install cellmaps_pipeline
```
The pinned dep set is internally coordinated; bumping any single
sibling will likely break others. Install in a fresh venv. GPU
strongly preferred for the image-embedding stage.

## Inputs
Verified from `cellmaps_pipeline/cellmaps_pipelinecmd.py:24-118`.

### Required
- `outdir` (positional)
- `--provenance <file.json>` — seeds the FAIRSCAPE provenance chain.
  CLI prints a sample if missing.

### Two parallel input streams
**Stream A — IF images** (one of):
- `--samples <file.csv>` + `--unique <file.csv>` (latter optional since v1.1.0)
- *or* `--cm4ai_image <path>` — path to the **IF Image table file inside** a CM4AI RO-Crate (CLI help: *"Path to CM4AI IF Image table file in RO-Crate"*)

**Stream B — AP-MS interactions** (one of):
- `--edgelist <file.tsv>` + `--baitlist <file.tsv>`
- *or* `--cm4ai_apms <path>` — path to the **AP-MS table file inside** a CM4AI RO-Crate (CLI help: *"Path to CM4AI AP-MS table file in RO-Crate"*)

Note: argparse does not mark any of these `required=True`; runtime
validation in the runner constructor enforces that at least one
valid input set is supplied.

### Knobs
- `--fold {1 | 2 | 1 2}` — DenseNet image-embedding fold variants. Each
  spawns parallel `2.image_embedding_fold#` and `3.coembedding_fold#`
  directories. Default: `[1, 2]`.
- `--ppi_cutoffs` — thresholds for similarity-network construction.
  CLI help string verbatim: *"Cutoffs used to generate PPI input
  networks. For example, a value of 0.1 means to generate PPI input
  network using the top ten percent of coembedding entries. Each
  cutoff generates another PPI network."* The exact unit ("coembedding
  entries") is not defined in the CLI; it lives in
  `CosineSimilarityPPIGenerator` (not opened this session).
  **Default (15 values):**
  ```
  0.001 0.002 0.003 0.004 0.005 0.006 0.007 0.008 0.009 0.01 0.02 0.03 0.04 0.05 0.10
  ```
- `--model_path <url|path>` — image-embedding checkpoint URL or path.
  **Default is a DenseNet-121 checkpoint** from CellProfiling/densenet
  v0.1.0 (filename contains `densenet121`); the flag accepts arbitrary
  paths/URLs, so a user could substitute a different model.
- `--proteinatlasxml <url|path>` — default
  `https://www.proteinatlas.org/download/proteinatlas.xml.gz`.
- `--slurm` — switch from in-process to SLURM-script generation.
- `--fake` — replace heavy stages with `Fake*` generators.

## Execution modes
*(verified in `cellmaps_pipeline/runner.py:45+`)*

`PipelineRunner` is an abstract base; `run()` raises
`NotImplementedError`. Two concrete subclasses:

| Mode | Class | Behaviour |
|---|---|---|
| In-process | `ProgrammaticPipelineRunner` | Default. Instantiates each sibling package's `*Runner` directly in this process. |
| HPC | `SLURMPipelineRunner` | Writes `slurm_cellmaps_job.sh` plus per-step `.sh` files under `outdir`. Step dependencies encoded as `#SBATCH --dependency=afterok:...`. |

The data-flow DAG is identical in both modes.

`--fake` swaps the heaviest stages for synthetic generators
(`FakeImageDownloader`, `FakeEmbeddingGenerator`, `FakeCoEmbeddingGenerator`)
for end-to-end smoke testing without GPU/network.

## Stage-by-stage workflow

### Dependency DAG
```
samples/unique ─► 1.image_download ─┐
                                    ├─► 2.image_embedding_fold1 ─┐
                                    └─► 2.image_embedding_fold2 ─┤
                                                                 ├─► 3.coembedding_fold1 ─┐
                                                                 └─► 3.coembedding_fold2 ─┤
edgelist/baitlist ─► 1.ppi_download ─► 1.ppi_embedding ──────────┘                        ├─► 4.hierarchy ─► 4.hierarchyeval
                                                                                          ┘
provenance.json ─► (threaded through every stage as RO-Crate metadata)
```

### Stage 1a — `cellmaps_imagedownloader` → `1.image_download/`
*(imports verified in `cellmaps_pipeline/runner.py:13-17,33-36`)*

`CellmapsImageDownloader` orchestrates per-channel TIFF download from
HPA. Strategies:
- `MultiProcessImageDownloader` — parallel HTTP fetch
- `CM4AICopyDownloader` — copies from a CM4AI RO-Crate (skips download)
- `FakeImageDownloader` — placeholder bytes (`--fake`)

Helpers: `ProteinAtlasReader`, `ProteinAtlasImageUrlReader`,
`ImageDownloadTupleGenerator`, `LinkPrefixImageDownloadTupleGenerator`,
`CM4AIImageCopyTupleGenerator`, `ImageGeneNodeAttributeGenerator`,
`CM4AITableConverter`.

### Stage 1b — `cellmaps_ppidownloader` → `1.ppi_download/`
*(imports verified)*

`CellmapsPPIDownloader` ingests `--edgelist` + `--baitlist` (or a CM4AI
crate via `CM4AIGeneNodeAttributeGenerator`), produces a normalized
gene+edge table. Helper: `APMSGeneNodeAttributeGenerator`.

### Stage 2a — `cellmaps_ppi_embedding` → `1.ppi_embedding/`
*(import verified; algorithm inferred from import name)*

`CellMapsPPIEmbedder` runs `Node2VecEmbeddingGenerator` over the
NetworkX graph from Stage 1b → per-gene embeddings (`embedding.tsv`).

### Stage 2b — `cellmaps_image_embedding` → `2.image_embedding_fold{1,2}/`
*(imports verified; algorithm inferred from import name)*

`CellmapsImageEmbedder` runs `DensenetEmbeddingGenerator` over the
TIFFs from Stage 1a → per-image features → per-gene mean-pool. **GPU
dominates this stage.** `--fake` substitutes `FakeEmbeddingGenerator`.
One output dir per requested fold.

### Stage 3 — `cellmaps_coembedding` → `3.coembedding_fold{N}/`
*(imports verified; algorithm inferred from import name)*

Per fold, `CellmapsCoEmbedder` runs `MuseCoEmbeddingGenerator`
(MUSE-style joint latent space) over the PPI embedding from Stage 2a
and the corresponding image embedding from Stage 2b. Emits one fused
`coembedding.tsv` per fold. `--fake` substitutes `FakeCoEmbeddingGenerator`.

This is the gene's full-modality fingerprint — every downstream stage
consumes this.

### Stage 4a — `cellmaps_generate_hierarchy` → `4.hierarchy/`
*(imports verified; algorithm details inferred from import names)*

`CellmapsGenerateHierarchy` ingests every `3.coembedding_fold*/`. Four
sub-stages:

1. `CosineSimilarityPPIGenerator` — for each cutoff in `--ppi_cutoffs`,
   build a top-fraction similarity network. Produces 15 candidate
   networks by default (NOT the original AP-MS edges).
2. `CDAPSHiDeFHierarchyGenerator` — multi-resolution HiDeF community
   detection across all cutoffs, consensus-merged.
3. `HiDeFHierarchyRefiner` — drops weak/duplicate communities.
4. `HCXFromCDAPSCXHierarchy` — exports to HCX (CX2 hierarchy profile).

Output is a containment DAG of communities, ready for NDEx /
Cytoscape Web.

### Stage 4b — `cellmaps_hierarchyeval` → `4.hierarchyeval/`
*(verified in `cellmaps_hierarchyeval/runner.py`; see next section)*

## Stage 4b — Verified enrichment details
> **All claims here are read directly from
> `cellmaps_hierarchyeval/runner.py` v0.2.2.**
> Class entry point: `CellmapshierarchyevalRunner` (line 667+).

### Hard-coded class defaults
*(from `runner.py:671-677`)*

```python
MAX_FDR = 0.05
MIN_JACCARD_INDEX = 0.1
MIN_COMP_SIZE = 4
CORUM = '633291aa-6e1d-11ef-a7fd-005056ae23aa'
GO_CC = '6722d74d-6e20-11ef-a7fd-005056ae23aa'
HPA = '68c2f2c0-6e20-11ef-a7fd-005056ae23aa'
NDEX_SERVER = 'http://www.ndexbio.org'
```

### The three enrichment databases
*(from `runner.py:811-815`)*

```python
term_definitions = [
    ('CORUM', CORUM_EnrichmentTerms, self._corum),
    ('GO_CC', GO_EnrichmentTerms, self._go_cc),
    ('HPA',   HPA_EnrichmentTerms,   self._hpa),
]
```

| Database | Class | NDEx UUID (default) | Coverage |
|---|---|---|---|
| **CORUM** | `CORUM_EnrichmentTerms` | `633291aa-6e1d-11ef-a7fd-005056ae23aa` | Curated mammalian protein complexes |
| **GO Cellular Component** | `GO_EnrichmentTerms` | `6722d74d-6e20-11ef-a7fd-005056ae23aa` | GO subcellular-location terms only — *not* BP or MF |
| **HPA** | `HPA_EnrichmentTerms` | `68c2f2c0-6e20-11ef-a7fd-005056ae23aa` | Human Protein Atlas gene sets |

**Each "database" is an NDEx-hosted CX network, not a bundled file.**
Loaded at runtime via `ndex2.create_nice_cx_from_server(...)` from
`runner.py:822-847`. The fetch helper takes a `max_retries=3`
parameter, **but a `<` comparison in the loop guard means only
2 attempts are actually made** before raising
`CellmapshierarchyevalError` (the exception message says "3 attempts"
— off-by-one). 10-second `time.sleep` between attempts in the
`finally` clause, so the second (last) attempt also incurs a wait
before the error propagates.

UUIDs and the server URL are CLI-overridable: `--corum`, `--go_cc`,
`--hpa`, `--ndex_server`. The entire enrichment stage is skippable
with `--skip_term_enrichment`.

### Statistical test
*(from `runner.py:899-916`)*

For each `(community, term)` pair:
```python
pval = scipy.stats.hypergeom.sf(x - 1, cap_m, n, cap_n)
jaccard_index = len(overlap_genes) / len(node_genes.union(term_genes))
```

Where:
- `x` = gene overlap between community and term
- `cap_m` = universe = `genes_in_hierarchy ∩ genes_in_any_term`
- `n` = community size restricted to that universe
- `cap_n` = term size

### Multiple-testing correction
*(from `runner.py:925-926`)*

```python
fdr = multipletests(pvals.flatten(), method='fdr_bh')[1].reshape(pvals.shape)
```

Benjamini-Hochberg, applied across the full `hierarchy × terms`
matrix at once **per database**. `_enrichment_test()` is called from
`_process_term()`, which is invoked once per `term_definition`
(`runner.py:817-818`), so **CORUM, GO_CC, and HPA each get their own
independent BH correction** — there is no joint multiple-testing
correction across all three databases combined.

### Acceptance criteria
*(from `runner.py:935-936`)*

A `(community, term)` pair is **accepted** iff:
- `jaccard_index ≥ MIN_JACCARD_INDEX` (default 0.1) **AND**
- `BH-adjusted_pval ≤ MAX_FDR` (default 0.05)

Communities and terms with fewer than `MIN_COMP_SIZE` (default 4)
genes are skipped.

### Sort order
*(from `runner.py:954`)*

Accepted terms per community are sorted by **Jaccard index
descending**, *not* by p-value.

### Output node attributes
*(from `runner.py:957-972`)*

For each `<DB>` ∈ `{CORUM, GO_CC, HPA}`, six attributes are added per
community node:

| Attribute | Content |
|---|---|
| `<DB>_terms` | `\|`-joined term names |
| `<DB>_descriptions` | `\|`-joined descriptions — *only populated for `GO_CC`*; CORUM and HPA leave this empty |
| `<DB>_FDRs` | `\|`-joined BH-adjusted p-values, formatted `{:0.2e}` |
| `<DB>_jaccard_indexes` | `\|`-joined JIs, rounded to 2 decimals |
| `<DB>_overlap_genes` | `\|`-joined, comma-separated overlap gene lists |
| `<DB>_max_jaccard_index` | scalar — top JI among accepted (only set when ≥1 accepted) |

Empty values when no terms accepted (`runner.py:979-997`).

### What this code does *not* compute
- **No GO Biological Process or Molecular Function** — only Cellular Component.
- **No HPA-specific location-agreement score** — HPA is treated identically to CORUM/GO_CC: just another hypergeometric overlap test against an NDEx-hosted gene-set network.
- **No composite confidence score** — each database emits its own
  `_max_jaccard_index`; nothing rolls them up. Persistence inherited
  from Stage 4a's refiner remains as separate node attributes.

### Optional LLM annotation track
*(from `cellmaps_hierarchyevalcmd.py:12-14`, `analysis.py`)*

Three classes provide a separate per-community LLM annotation track,
**marked EXPERIMENTAL** in code comments ("interface may be changed or
removed in the future"):

- `OllamaCommandLineGeneSetAgent` — calls a local `ollama` binary
  (default path `/usr/local/bin/ollama`)
- `OllamaRestServiceGenesetAgent` — calls a remote Ollama REST endpoint
- `FakeGeneSetAgent` — for testing

Opt-in via:
```bash
--ollama_prompts <MODEL>            # uses default prompt
--ollama_prompts <MODEL>,<PROMPT>   # custom prompt or path-to-prompt-file
--ollama <path-or-url>              # binary path or http://.../api/generate
--ollama_user / --ollama_password   # basic auth for REST mode
```

Each agent receives the community's gene names and returns a tuple
`(process_name, confidence, raw_output)` attached as:
- `{prefix}_process`
- `{prefix}_confidence`
- `{prefix}_raw`

## Output directory structure
```
<outdir>/
├── 1.image_download/         TIFFs + RO-Crate
├── 1.ppi_download/           Edge table + RO-Crate
├── 1.ppi_embedding/          Node2Vec vectors + RO-Crate
├── 2.image_embedding_fold1/  DenseNet vectors + RO-Crate
├── 2.image_embedding_fold2/  (if --fold includes 2)
├── 3.coembedding_fold1/      MUSE-fused vectors + RO-Crate
├── 3.coembedding_fold2/
├── 4.hierarchy/              HCX hierarchy + RO-Crate
└── 4.hierarchyeval/          Annotated hierarchy + RO-Crate ← final consumer artifact
```

Each RO-Crate references its inputs via FAIRSCAPE identifiers. The
terminal `4.hierarchyeval/ro-crate-metadata.json` transitively cites
every prior crate up to the original `--provenance` JSON.

## CLI flag reference
*(verified from `cellmaps_pipelinecmd.py:24-118`)*

### Required
| Flag | Purpose |
|---|---|
| `outdir` | Output directory (positional) |
| `--provenance <file>` | JSON manifest seeding FAIRSCAPE chain |

### Input source
None of these are marked `required=True` in argparse; runtime
validation in the runner enforces that at least one valid set is
supplied.

| Flag | Purpose |
|---|---|
| `--samples` + (`--unique`) + `--edgelist` + `--baitlist` | Explicit input files |
| `--cm4ai_image` + `--cm4ai_apms` | Paths to table files inside CM4AI RO-Crates |

### Pipeline behaviour
| Flag | Default | Purpose |
|---|---|---|
| `--fold` | `1 2` | Image-embedding fold variants |
| `--ppi_cutoffs` | 15 values, `0.001`–`0.10` | Similarity-network thresholds |
| `--model_path` | CellProfiling DenseNet URL | Image-embedding checkpoint |
| `--proteinatlasxml` | HPA xml.gz URL | Image-URL lookup source |
| `--slurm` | off | Switch to SLURM-script generation |
| `--fake` | off | Substitute heavy stages with synthetic generators |

### Help / introspection
| Flag | Purpose |
|---|---|
| `--example_provenance` | Print example provenance JSON and exit |
| `--example_registered_provenance` | Print example with FAIRSCAPE identifiers |
| `--logconf <file>` | Override default logging config |
| `--verbose` / `-v` | Increase verbosity (cumulative, up to `-vvvv`) |
| `--version` | Print version and exit |

## What's verified vs inferred

### Verified — read directly from source this session
- `cellmaps_pipeline/cellmaps_pipelinecmd.py` (CLI surface, all flags, defaults)
- `cellmaps_pipeline/runner.py` (`PipelineRunner` / `ProgrammaticPipelineRunner` /
  `SLURMPipelineRunner` classes, imports of every sibling package's
  runner class, directory naming, partial SLURM batch generation)
- `cellmaps_pipeline/__init__.py` (version 1.3.0)
- `cellmaps_hierarchyeval/runner.py` (all of Stage 4b: hypergeometric +
  BH-FDR + JI thresholds + the three NDEx UUIDs + node-attribute
  schema + the retry off-by-one + the per-database BH scope)
- `cellmaps_hierarchyeval/cellmaps_hierarchyevalcmd.py` (CLI surface
  including Ollama opt-in flags)

### Inferred / unread

**Six sibling packages — none opened.** Roles described above come
from import names in `cellmaps_pipeline/runner.py`, README narrative,
and stage call sequence:
- `cellmaps_imagedownloader`
- `cellmaps_ppidownloader`
- `cellmaps_ppi_embedding`
- `cellmaps_image_embedding`
- `cellmaps_coembedding`
- `cellmaps_generate_hierarchy`

Specific algorithm or parameter claims about those packages should be
re-verified against their source before being treated as authoritative.
The only fully verified detail crossing into them is the
**DenseNet-121 checkpoint URL** that `cellmaps_pipelinecmd.py:69`
hard-codes as the default for `--model_path`.

**Other unread files in `cellmaps_hierarchyeval/`:**
- `analysis.py` (483 lines) — contains the actual implementations of
  `OllamaCommandLineGeneSetAgent`, `OllamaRestServiceGenesetAgent`,
  `FakeGeneSetAgent`. Only their *existence* is verified (via imports
  in the CLI module); their internals were not inspected.
- `perturb.py` (190 lines) — purpose unknown; not referenced by
  anything I documented.
- `default_prompt.txt` — the bundled default LLM prompt; content not
  inspected.
- The remaining ~700 lines of `runner.py` outside the enrichment
  block (lines ~1-665 plus 1000-1324) — mostly hierarchy I/O and
  RO-Crate provenance plumbing; not read in detail.

## Citation
> Lenkiewicz, J., Churas, C., Hu, M., Qian, G., Jain, M., Levinson, M. A.,
> ... & Schaffer, L. V. (2025). Cell Mapping Toolkit: An end-to-end
> pipeline for mapping subcellular organization. *Bioinformatics*, 41(6),
> btaf205, <https://doi.org/10.1093/bioinformatics/btaf205>.
