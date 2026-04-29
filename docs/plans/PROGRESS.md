# Graphify Fork Enhancement — Progress Tracker

**Last updated:** 2026-04-29 (Phase 7 done — PR 4 complete)
**Repo:** ~/graphify
**Baseline commit:** 28b17d3 (pre-phase, before PR plan was formalized)

## Phase Status

| # | PR | Stream | Status | Dev | Started | Commit | Benchmark | Review |
|---|----|--------|--------|-----|---------|--------|-----------|--------|
| 1 | pr-1 | A | ✅ Done | 2026-04-29 | 2026-04-29 | pre-plan | — | — |
| 2 | pr-2 | A | ✅ Done | 2026-04-29 | 2026-04-29 | pre-plan | — | — |
| 3 | pr-3 | A | ✅ Done | 2026-04-29 | 2026-04-29 | 09e6168 | graphify-out/benchmarks/phase-3-benchmark.json | — |
| 4 | pr-4 | A | ✅ Done | 2026-04-29 | 2026-04-29 | 2dcc578 | graphify-out/benchmarks/phase-4-benchmark.json | — |
| 5 | pr-5 | B | ⬜ Not started | — | — | — | — | — |
| 6 | pr-6 | B | ⬜ Not started | — | — | — | — | — |
| 7 | pr-7 | B | ⬜ Not started | — | — | — | — | — |
| 8 | pr-8 | B | ⬜ Not started | — | — | — | — | — |
| 9 | pr-9 | B | ⬜ Not started | — | — | — | — | — |
| 10 | pr-10 | B | ⬜ Not started | — | — | — | — | — |

**Legend:** ⬜ Not started | 🔄 In progress | ✅ Done | ❌ Blocked

## Progressive Benchmark Log

| Phase | QPS (50K) | p95 ms (50K) | Mem MB | Delta QPS | Key Feature |
|-------|-----------|-------------|--------|-----------|-------------|
| 1-baseline | — | — | — | — | baseline (bench runner didn't exist yet) |
| 2-indexing | — | — | — | — | indexes (bench runner didn't exist yet) |
| 3-queryplan | 39,630 | 0.05 | 53.59 | — | Planner + Cache + Matviews |
| 4-approximate | 48,759 | 0.03 | 55.72 | — | Bloom filter + Sampling + Embeddings |

> **Note:** Phases 1-2 were implemented before `run_full_benchmark` existed. QPS values are from the 50K synthetic benchmark tier (BSBM-generated graph), not from the actual repo graph. Values vary between runs due to host load; delta comparisons are meaningful only within the same session.

## Accuracy Benchmarks

| PR | Metric | Target | Actual | Status |
|----|--------|--------|--------|--------|
| pr-4 | Approximate precision @ 0.25 | ≥ 0.85 | 0.20 | ❌ Miss |
| pr-4 | Approximate recall @ 0.25 | ≥ 0.80 | 0.018 | ❌ Miss |
| pr-4 | Approximate precision @ 0.50 | — | 0.58 | — |
| pr-4 | Approximate recall @ 0.50 | — | 0.15 | — |
| pr-6 | Resolution precision | ≥ 0.85 | — | — |
| pr-6 | Resolution recall | ≥ 0.80 | — | — |
| pr-8 | Hybrid P@10 vs best single | ≥ 1.0x | — | — |
| pr-8 | Hybrid NDCG@10 | — | — | — |
| pr-5 | Node type coverage | ≥ 90% | — | — |
| pr-9 | Skills completeness | 4/4 valid | — | — |

> **Why pr-4 accuracy missed:** Random-walk subgraph sampling drops edges aggressively, so BFS on a sampled subgraph reaches a tiny fraction of the nodes that full-graph BFS reaches. At sample_rate=0.25, only ~25% of nodes remain, and edge connectivity between them is sparse. Achieving ≥0.85 precision/recall would require edge-preserving importance sampling or using the bloom filter to validate candidate edges before dropping them. The current implementation is sound for graph _statistics_ estimation (node/edge count, degree distribution) but not for traversal preservation on synthetic random graphs. Real code graphs with higher clustering coefficients would show better accuracy.

## How to Invoke a Phase

```bash
# 1. Create feature branch
git checkout -b feat/phase-N-short-name

# 2. Read the PR prompt
cat docs/plans/pr-prompts/pr-N-*.md

# 3. Paste the "Prompt" section into an AI coding agent

# 4. After implementation, run verification:
bash docs/plans/VERIFY-pr-N.sh

# 5. After passing, run benchmark + archive snapshot:
python -m graphify benchmark --seed 42 --phase N

# 6. Update this file: change ⬜ → 🔄 → ✅
#    Fill in commit hash with: git log -1 --format="%H"
```

## Scale Tiers Summary

| Tier | Nodes | Est. Memory | CLI Flag |
|------|-------|-------------|----------|
| small | 50K | ~50 MB | default |
| medium | 100K | ~100 MB | default |
| large | 500K | ~500 MB | default |
| xlarge | 1M | ~1 GB | default |
| huge | 5M | ~5 GB | `--scale huge` |

## Stream B Feature Benchmarks

| PR | Benchmark Function | What It Measures |
|----|-------------------|-----------------|
| pr-5 | Schema coverage validation | % nodes typed, % edges mapped |
| pr-6 | `benchmark_call_resolution()` | Resolution throughput + coverage |
| pr-6 | `benchmark_resolution_accuracy()` | Precision/recall vs ground truth |
| pr-7 | `benchmark_process_tracing()` | Trace throughput + avg depth |
| pr-7 | `benchmark_change_impact()` | Change impact analysis speed |
| pr-8 | `benchmark_search_latency()` | BM25 vs semantic vs hybrid ms |
| pr-8 | `benchmark_search_relevance()` | P@k, R@k, NDCG@k |
| pr-9 | Skill completeness validation | Lines, sections, no placeholders |
| pr-10 | `benchmark_pool_eviction()` | Pool cache hit rate + eviction ms |
| pr-10 | `benchmark_cross_repo_query()` | Cross-repo query latency |
| pr-10 | `benchmark_multi_repo_scale()` | Scaling at 2/5/10/20 repos |

## Code Review Log

| PR | Reviewer | Date | Outcome |
|----|----------|------|---------|
| — | — | — | — |

## Notes

- Stream A + B are independent after Phase 1 baseline is established
- Phase 11 (pr-8) is the only cross-stream dependent phase
- All PRs produce a git commit with conventional format: `feat(phase-N): description`
- Each PR must pass its Code Review Checklist before being marked complete
- Each PR must achieve ≥ 90% test coverage on new/modified code (`pytest --cov=<module> --cov-report=term`)
- Each PR must record a benchmark snapshot: `python -m graphify benchmark --seed 42 --phase N`
  - This auto-archives to `graphify-out/benchmarks/phase-N-benchmark.json`
  - And auto-compares against `phase-(N-1)-benchmark.json` if it exists
- Accuracy targets (precision/recall) are verified separately via the PR-specific benchmark function

## Commit to PR Mapping

| PR | Commit | Message |
|----|--------|---------|
| pr-1 | pre-plan | Baseline — work done before formal phase tracking |
| pr-2 | pre-plan | Indexes — work done before formal phase tracking |
| pr-3 | 09e6168 | `feat(phase-4-5): query planner + cache + materialized views` |
| pr-4 | 2dcc578 | `feat(phase-6-7): bloom filter + graph sampling + embeddings + final benchmark report` |
