# Handoff: detector platform rollout

Date: 2026-04-19

## Implementation status

The detector-platform plan in `.cursor/plans/decision-tree-detector-platform_5ea21a9c.plan.md` is fully implemented and audited.

The rollout now includes:

- detector schemas, registry, policy loading, DSL, and the builtin detector catalog
- verifier oracle, cross-universe, negation, version, and mechanical-confirmation paths
- ingest modules for manifests, env/config, prompts, OpenAPI, Next.js, and infra
- enrichment resolvers plus structured probe-error collection in `semantic_edges`
- `RunResult` pipeline wiring, detector stats, ingest reports, observability JSONL, and optional GraphCodeBERT pre-ranking
- Supabase migrations, SQLAlchemy mirrors, API registry/policy endpoints, and CLI detector list/explain/include/exclude flows
- detector/oracle/ingest/pipeline coverage for the first cross-universe end-to-end paths

## Audit follow-up fixes

The codebase-wide audit surfaced and fixed a few additional issues beyond the original rollout:

- fixed a gray-zone evaluator regression where `unconfirmed` findings backed only by unavailable verifier checks were being over-downgraded instead of staying ambiguous until the panel reconciled them
- added `graphify/nx_compat.py` and wired it through graph export/load paths so both legacy node-link `links` payloads and newer NetworkX `edges` payloads work across exports, snapshots, benchmarks, CLI commands, and MCP serving
- updated Windows symlink tests to skip cleanly when the environment lacks symlink privileges instead of failing before the code under test runs

## Operational notes

- GraphCodeBERT stays off by default in the operational pipeline via `DEPOS_INTEL_USE_GRAPHCODEBERT`.
- Advisory lookups are file-backed from `data/advisories/`; refresh them with `scripts/refresh_advisories.py`.
- Prompt schema snapshots live under `depos/ingest/prompt_schemas/`.
- Detector registry snapshots can be regenerated with `scripts/snapshot_detector_registry.py`.

## Verification

Final audit verification on this branch:

- `uv run --with pytest pytest`
- result: `490 passed, 5 skipped`

The 5 skipped tests are the Windows symlink cases, which now skip intentionally when the host lacks symlink privileges.
