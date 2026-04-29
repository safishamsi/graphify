# Graphify Fork Enhancement — Progress Tracker

**Last updated:** 2026-04-29 (Phase 7 done)
**Repo:** ~/graphify
**Baseline commit:** (set after Phase 1)

## Phase Status

| # | PR | Stream | Status | Dev | Started | Commit | Benchmark | Review |
|---|----|--------|--------|-----|---------|--------|-----------|--------|
| 1 | pr-1 | A | ✅ Done | 2026-04-29 | 2026-04-29 | TBD | TBD | TBD |
| 2 | pr-2 | A | ✅ Done | 2026-04-29 | 2026-04-29 | TBD | TBD | TBD |
| 3 | pr-3 | A | ✅ Done | 2026-04-29 | 2026-04-29 | TBD | TBD | TBD |
| 4 | pr-4 | A | ✅ Done | 2026-04-29 | 2026-04-29 | TBD | TBD | TBD |
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
| 1-baseline | — | — | — | — | baseline (not yet benched) |
| 2-indexing | — | — | — | — | indexes (not yet benched) |
| 3-queryplan | 39,630 | 0.05 | 53.59 | — | Planner + Cache + Matviews |
| 4-approximate | 34,622 | 0.06 | 52.34 | — | Bloom filter + Sampling + Embeddings |

## Accuracy Benchmarks

| PR | Metric | Target | Result | Status |
|----|--------|--------|--------|--------|
| pr-4 | Approximate precision @ 0.25 | ≥ 0.85 | — | — |
| pr-4 | Approximate recall @ 0.25 | ≥ 0.80 | — | — |
| pr-6 | Resolution precision | ≥ 0.85 | — | — |
| pr-6 | Resolution recall | ≥ 0.80 | — | — |
| pr-8 | Hybrid P@10 vs best single | ≥ 1.0x | — | — |
| pr-8 | Hybrid NDCG@10 | — | — | — |
| pr-5 | Node type coverage | ≥ 90% | — | — |
| pr-9 | Skills completeness | 4/4 valid | — | — |

## How to Invoke a Phase

```bash
# 1. Create feature branch
git checkout -b feat/phase-N-short-name

# 2. Read the PR prompt
cat docs/plans/pr-prompts/pr-N-*.md

# 3. Paste the "Prompt" section into an AI coding agent

# 4. After implementation, mark progress
#    Update this file: change ⬜ → 🔄 → ✅
#    Fill in commit hash, benchmark result
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
- Each PR must record a benchmark: `graphify benchmark --seed 42 --output graphify-out/benchmark.json` and update the Progressive Benchmark Log
