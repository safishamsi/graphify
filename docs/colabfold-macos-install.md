# Installing LocalColabFold on macOS Apple Silicon
A reproducible runbook for installing
[LocalColabFold](https://github.com/YoshitakaMo/localcolabfold)
(ColabFold + AlphaFold2 weights) on Apple Silicon (arm64) Macs, so you can
predict protein structures locally and feed the resulting PDBs / confidence
scores into a graphify corpus.

This document is **optional** and unrelated to graphify's pipeline. It is
included as a known-good recipe for users who want a CPU-capable local
ColabFold install alongside graphify on the same machine.

## Why a separate runbook
LocalColabFold's current top-level installer (`install_colabbatch_linux.sh`)
hardcodes `Miniforge3-Linux-x86_64.sh` and later runs
`pip install jax[cuda12]==0.5.3`. Both fail on Apple Silicon: there are no
macOS CUDA wheels, and Apple GPUs are unreachable from JAX's CUDA backend.
Upstream stopped shipping a current macOS installer after v1.5.5. The
**v1.5.5 M1 installer** (bundled in the LocalColabFold repo at
`v1.5.5_old_installers/install_colabbatch_M1mac.sh`) is the working Apple
Silicon path — ColabFold 1.6.1, JAX 0.4.23 CPU build.

## Verified configuration
- Hardware: Apple Silicon (arm64)
- OS: macOS (Darwin)
- ColabFold installed: 1.6.1 (commit `de5ab5f`)
- JAX: 0.4.23 (CPU build)
- 62-residue smoke test (1 model, 1 recycle, single-sequence MSA): ~60 s wall

## Prerequisites (Homebrew)
The M1 installer fail-fasts on these. Install once before running:

```bash
brew tap brewsci/bio                 # custom tap for hh-suite
brew install brewsci/bio/hh-suite \
             kalign \
             mmseqs2

# verify
for c in wget hhsearch kalign mmseqs; do
  printf "%-10s " "$c" && command -v "$c" || echo MISSING
done
```

Roughly ~600 MB of brew downloads (gcc, open-mpi, hh-suite are the heavy
items); 5–10 minutes on a modern internet link.

## Install
Clone LocalColabFold (or use an existing clone), then from the repo root:

```bash
git clone https://github.com/YoshitakaMo/localcolabfold.git
cd localcolabfold
bash v1.5.5_old_installers/install_colabbatch_M1mac.sh
```

What the installer does, in order:
1. Downloads `Miniforge3-MacOSX-arm64.sh` and installs into
   `localcolabfold/conda/`
2. `conda update -n base conda -y`
3. Creates env at `localcolabfold/colabfold-conda` with
   `python=3.10 openmm==8.0.0 pdbfixer==1.9` from conda-forge
4. `pip install "colabfold[alphafold] @ git+https://github.com/sokrypton/ColabFold"`
5. `pip install jax==0.4.23 jaxlib==0.4.23` (CPU build)
6. `pip install silence_tensorflow`
7. Downloads `update_M1mac.sh`
8. `python -m colabfold.download` — pulls AlphaFold2 weights into
   `~/Library/Caches/colabfold` (~5.3 GB total: 3.82 GB multimer_v3 +
   3.47 GB AlphaFold2-ptm)

Total install time: ~10–30 min depending on network and AlphaFold weight
download speed.

## Add to PATH
The installer's last step prints the line for your shell. Adapt the prefix
to wherever you cloned LocalColabFold:

```bash
export PATH="$(pwd)/localcolabfold/colabfold-conda/bin:$PATH"
```

Add the line to `~/.zshrc` to persist across shell sessions.

## Smoke test
A minimal CPU-only inference exercising the JAX path (no MMseqs2 server,
no templates, single model, single recycle). Use any short FASTA — the
LocalColabFold repo ships `1BJP_1.fasta` (62 residues).

```bash
colabfold_batch \
  --num-models 1 --num-recycle 1 \
  --msa-mode single_sequence \
  --random-seed 0 \
  1BJP_1.fasta out_smoketest/
```

Expected output in `out_smoketest/`:
- `*.pdb` — predicted structure
- `*_scores_*.json` — per-residue confidence
- `*_pae.png`, `*_plddt.png`, `*_coverage.png` — diagnostic plots
- `1BJP_1.done.txt` — sentinel marker

Sample log lines on success:
```
Running colabfold 1.6.1 (de5ab5f795ed95c70a7a9b6a9dc6bb5625016142)
WARNING: no GPU detected, will be using CPU
Query 1/1: 1BJP_1 (length 62)
alphafold2_ptm_model_1_seed_000 recycle=0 pLDDT=56.7 pTM=0.363
alphafold2_ptm_model_1_seed_000 took 18.1s (1 recycles)
```

The low pLDDT (~57) is **expected** — single-sequence MSA, 1 model, and
1 recycle is the cheapest config that still exercises the JAX inference
path. It is **not** representative of structure quality. Use the
production config below for real predictions.

## Production run (CPU-friendly defaults)
LocalColabFold's bundled `run_colabfoldbatch_sample.sh` uses
`--use-gpu-relax`, `--templates`, and `--amber` — all of which require
either GPU or extra setup that doesn't apply on macOS. Use this
CPU-friendly variant instead:

```bash
colabfold_batch \
  --num-recycle 3 \
  --num-models 5 \
  --model-order 1,2,3,4,5 \
  --random-seed 0 \
  YOUR_INPUT.fasta out_dir/
# Dropped from the sample script:
#   --use-gpu-relax  (no GPU)
#   --amber          (slow on CPU; pdbfixer-only is fine for many use cases)
#   --templates      (requires hhsearch + a PDB templates DB)
```

MSA defaults to MMseqs2 server-side queries — needs network, ~30–90 s
roundtrip per sequence.

Expect 5–15 min per ~100-residue monomer on this hardware. Multimers and
longer chains scale much worse on CPU.

## Honest caveats
- **CPU-only.** No CUDA wheels for macOS exist; JAX has experimental
  Metal support but LocalColabFold's pinned `jax==0.4.23` is the CPU
  build. Inference can be 30–100× slower than a recent NVIDIA GPU.
- **ColabFold version is 1.6.1**, pinned by the v1.5.5 installer track.
  Newer features in ColabFold `main` aren't available here. For latest
  features either use Google Colab or a Linux + NVIDIA box.
- **Weights cache is ~5.3 GB** at `~/Library/Caches/colabfold`. Move with
  `XDG_CACHE_HOME` if disk is tight.
- **Apple Silicon Metal** is not used by this JAX. There's no
  straightforward way to enable it without changing the pinned versions
  in the installer script.

## Update
```bash
bash localcolabfold/update_M1mac.sh
```

## Uninstall / reset
```bash
# Remove the conda env + Miniforge (keeps weights cache)
rm -rf localcolabfold/

# Optionally drop weights cache
rm -rf ~/Library/Caches/colabfold

# Optionally remove brew prereqs
brew uninstall brewsci/bio/hh-suite kalign mmseqs2
brew untap brewsci/bio
```
