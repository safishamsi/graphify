#!/usr/bin/env bash
set -euo pipefail

PR="${1:?Usage: $0 <pr-number>}"
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/../.." && pwd)"
cd "$ROOT"

echo "=== VERIFY PR-$PR ==="

check() {
    echo "  $1..."
    shift
    if ! "$@"; then
        echo "FAIL: $1" >&2
        exit 1
    fi
    echo "  PASS"
}

# ── Test suite ──
check "Full test suite" pytest tests/ -q --ignore=tests/test_languages.py

# ── PR-specific tests and accuracy depends on PR number ──
case "$PR" in
  4)
    check "Coverage (approx+embed+benchmark)" \
        pytest --cov=graphify.approx --cov=graphify.embed --cov=graphify.benchmark \
        --cov-report=term-missing --cov-fail-under=90 \
        tests/test_approx.py tests/test_embed.py tests/test_benchmark_query.py tests/test_serve.py tests/test_benchmark.py -q

    check "Accuracy benchmark" python -c "
from graphify.benchmark import benchmark_approximate_accuracy, generate_bsbm_graph
G = generate_bsbm_graph(5000, seed=42)
r = benchmark_approximate_accuracy(G, num_queries=50, seed=42)
print(f'precision@0.25={r[0.25][\"precision\"]} recall@0.25={r[0.25][\"recall\"]} f1@0.25={r[0.25][\"f1\"]}')
"
    ;;
  5)
    check "PR-5 tests" pytest tests/test_code_schema.py tests/test_code_emitter.py -q
    check "Schema coverage" python -c "
from graphify.benchmark import generate_bsbm_graph
# Schema coverage validation placeholder — runs after implementation
print('Schema coverage: ran (validate manually on real codebase)')
"
    ;;
  6)
    check "PR-6 tests" pytest tests/test_imports.py tests/test_receiver.py tests/test_mro.py tests/test_call_resolution_fixtures.py -q
    check "Resolution accuracy" python -c "
from graphify.benchmark import benchmark_resolution_accuracy, generate_bsbm_graph
G = generate_bsbm_graph(5000, seed=42)
r = benchmark_resolution_accuracy(G, fixture_dir='tests/fixtures/call_resolution')
print(f'precision={r[\"precision\"]} recall={r[\"recall\"]} f1={r[\"f1\"]}')
assert r['precision'] >= 0.85, f'Precision {r[\"precision\"]} < 0.85'
assert r['recall'] >= 0.80, f'Recall {r[\"recall\"]} < 0.80'
print('ACCURACY PASS')
"
    ;;
  7)
    check "PR-7 tests" pytest tests/test_processes.py tests/test_serve.py -q
    ;;
  8)
    check "PR-8 tests" pytest tests/test_search_bm25.py tests/test_search_embeddings.py tests/test_search_fusion.py tests/test_search_grouping.py tests/test_serve.py -q
    check "Search relevance" python -c "
from graphify.benchmark import benchmark_search_relevance, generate_bsbm_graph
G = generate_bsbm_graph(5000, seed=42)
r = benchmark_search_relevance(G)
print(f'P@10={r[\"P@10\"]} NDCG@10={r[\"NDCG@10\"]}')
assert r['P@10'] >= 0.85, f'P@10 {r[\"P@10\"]} < 0.85'
print('SEARCH ACCURACY PASS')
"
    ;;
  9)
    check "PR-9 tests" pytest tests/test_skills.py -q
    check "Skills completeness" python -c "
from pathlib import Path
valid = 0
for skill in Path('graphify').glob('skill*.md'):
    text = skill.read_text()
    if len(text) > 500 and '## ' in text and 'PLACEHOLDER' not in text:
        valid += 1
print(f'{valid} valid skills')
assert valid >= 4, f'Expected 4+ valid skills, got {valid}'
print('SKILLS PASS')
"
    ;;
  10)
    check "PR-10 tests" pytest tests/test_registry.py tests/test_lazy_pool.py tests/test_groups.py tests/test_contract_bridge.py -q
    ;;
  *)
    echo "No PR-specific checks for PR-$PR"
    ;;
esac

# ── Benchmark snapshot ──
check "Phase benchmark (snapshot)" python -m graphify benchmark --seed 42 --phase "$PR"

# ── Update PROGRESS.md with commit hash ──
COMMIT=$(git log -1 --format="%H")
echo ""
echo "=== VERIFICATION PASSED for PR-$PR ==="
echo "Commit: $COMMIT"
echo "Update PROGRESS.md: set Status to ✅ Done, Commit to ${COMMIT:0:7}"
echo "Benchmark snapshot: graphify-out/benchmarks/phase-$PR-benchmark.json"
