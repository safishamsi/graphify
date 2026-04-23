---
name: depOS prod impact
overview: "Ship depOS as a production-credible product by closing the gap between “APIs return 200” and measurable engineering impact: short-lived CI trust (OIDC), truthful analyze (blast + SARIF + warnings), a golden GitHub workflow (diff + postci), then lifecycle, observability, security, web feedback, deploy, and intelligence regression—deferring optional server-side intel execution until the core loop is proven."
todos:
  - id: phase-a-oidc
    content: Implement GitHub OIDC token exchange (depos/ci_auth.py, settings, api_server routes + dependency), repo→org mapping (migration or env), update depos-ci.yml; tests T-A1–T-A5 per comprehensive doc
    status: pending
  - id: phase-b-analyze-truth
    content: Add analysis_warnings + CIAnalyzeRequest path hints; thread into diagnostics; path-only CODEOWNERS; extend models/export_llm/api_server; tests T-B1–T-B4
    status: pending
  - id: phase-c-golden-workflow
    content: "Composite GitHub Action: git diff changed_files, optional SARIF, analyze then postci with identical predictions; docs ci-oidc + README"
    status: pending
  - id: phase-d-snapshot-lifecycle
    content: Idempotency or dedupe for prepare; pending TTL failure; upload size guard; migration/API changes as chosen
    status: pending
  - id: phase-e-observability
    content: Structured logs + analyze timing/seed/SARIF counts; optional metrics; docs/runbooks weak-analyze triage
    status: pending
  - id: phase-f-security
    content: Rate limits + body caps on analyze/federation; rotation runbook; RLS audit for new CI mapping table if added
    status: pending
  - id: phase-g-web
    content: AnalyzeLab + types for warnings; intelligence detail surfacing health/evidence; optional ci_signals rollup
    status: pending
  - id: phase-h-deploy
    content: Dockerfile + deploy docs; staging parity with production env validation (depos/settings.py)
    status: pending
  - id: phase-i-intel-regression
    content: CI job on fixed corpus with depos-intel --strict; link to dataset-pipeline.md maintenance
    status: pending
  - id: phase-j-defer
    content: "Optional: server-side intel worker or workflow_dispatch; spec only after A–E exit criteria met"
    status: pending
isProject: false
---

# depOS — production shipment and real impact

## Canonical reference

The full phased spec (success metrics M1–M6, per-phase test scenarios, risks, go/no-go checklist) lives in [docs/plans/2026-04-22-prod-impact-comprehensive.md](docs/plans/2026-04-22-prod-impact-comprehensive.md). This plan is the execution spine; treat that file as the detailed appendix and keep it in sync when scope shifts.

## Problem and outcome

**Problem:** Core engines exist ([depos/snapshot.py](depos/snapshot.py), [depos/blast.py](depos/blast.py), [depos/diagnostics.py](depos/diagnostics.py), [depos/fusion.py](depos/fusion.py), [depos/api_server.py](depos/api_server.py), [depos/intelligence_store.py](depos/intelligence_store.py), [apps/web/](apps/web/)), but **impact** depends on CI glue that today fails quietly: long-lived JWTs ([.github/workflows/depos-ci.yml](.github/workflows/depos-ci.yml)), empty `changed_files`, weak SARIF mapping when `repo_root` is not a real checkout ([depos/api_server.py](depos/api_server.py) snapshot branch + [depos/diagnostics.py](depos/diagnostics.py)), CODEOWNERS only on internal+`root`, and intelligence **persisted by clients** rather than guaranteed by a golden job.

**Outcome:** Every primary path produces **verifiable** results (non-empty blast when the diff truly touches the graph, SARIF mapped or explicitly warned, post-CI uses the same predictions as analyze) and **safe** multi-tenant CI ([docs/ci-oidc.md](docs/ci-oidc.md)).

## Architecture after changes (high level)

```mermaid
sequenceDiagram
  participant GHA as GitHubActions
  participant API as depOS_API
  participant SB as Supabase_AuthStorageDB
  GHA->>API POST_ci_auth_github with OIDC
  API-->>GHA short_lived_scoped_token
  GHA->>API graph_snapshots_prepare_complete
  GHA->>API ci_analyze with changed_files_and_sarif
  GHA->>API ci_postci same_predictions
  Note over API,SB: Humans still use Supabase_JWT for web routes
```

## Phase order (do not reorder A before B for “demo impact” if SaaS is the goal)

1. **Phase A — CI trust (OIDC exchange)** — New [depos/ci_auth.py](depos/ci_auth.py) (or equivalent), [depos/settings.py](depos/settings.py) env for audience/JWKS/map, [depos/api_server.py](depos/api_server.py) exchange route + auth dependency for snapshot/analyze/postci, migration or env map for `repository` → org/repo, update [.github/workflows/depos-ci.yml](.github/workflows/depos-ci.yml). Align with [docs/ci-oidc.md](docs/ci-oidc.md).

2. **Phase B — Analyze truth** — Extend `LLMGraphExport` / analyze response with `analysis_warnings` ([depos/models.py](depos/models.py), [depos/export_llm.py](depos/export_llm.py), [depos/api_server.py](depos/api_server.py)); add `workspace_root_hint` / `sarif_path_prefix` to `CIAnalyzeRequest` and thread into [depos/diagnostics.py](depos/diagnostics.py) `map_diagnostics_to_nodes`; implement path-only CODEOWNERS in [depos/ownership.py](depos/ownership.py) + `ci_analyze`.

3. **Phase C — Golden workflow** — Composite under `.github/actions/` or expanded workflow: real `git diff` → normalized paths, optional SARIF artifact, **same** predicted files for `postci` as for analyze output. Update [README.md](README.md) / [docs/ci-oidc.md](docs/ci-oidc.md).

4. **Phase D — Snapshot lifecycle** — Idempotency or dedupe policy on prepare; stale `pending` cleanup; max upload size on complete ([depos/graph_storage.py](depos/graph_storage.py), [depos/api_server.py](depos/api_server.py), [supabase/migrations/](supabase/migrations/)).

5. **Phase E — Observability** — Structured logs + timing on `ci_analyze` (seed count, SARIF map counts); optional metrics endpoint; runbook under [docs/runbooks/](docs/runbooks/).

6. **Phase F — Hardening** — Rate limits / body size caps on hot routes; internal key rotation doc; RLS review checklist for new tables.

7. **Phase G — Web** — Surface `analysis_warnings` in [apps/web/components/analyze/AnalyzeLabClient.tsx](apps/web/components/analyze/AnalyzeLabClient.tsx) and types in [apps/web/lib/depos/types.ts](apps/web/lib/depos/types.ts); intelligence run detail shows health/evidence; optional CI rollup from `ci_signals`.

8. **Phase H — Deploy** — Dockerfile + `/ready` gate in deploy pipeline; extend [docs/development.md](docs/development.md).

9. **Phase I — Intelligence regression** — Scheduled workflow on fixed corpus with `depos-intel` `--strict`; keep [docs/dataset-pipeline.md](docs/dataset-pipeline.md) aligned with CLI.

10. **Phase J (optional)** — Server-side intelligence worker **or** GitHub `workflow_dispatch` integration; defer until A–E stable.

## Testing strategy (minimum bar)

- Unit: OIDC verify mocks, diagnostics path normalization, blast seed warnings, ownership path-only.
- API: `TestClient` tests for `ci_analyze` response warnings and SARIF hint behavior.
- E2E: local Supabase + script prepare → PUT → complete → analyze → postci (fixture graph JSON in `tests/` or `worked/`).

## Exit signal

Dogfood repo: PR flow produces non-empty blast when files change, postci recorded, no static Supabase JWT in secrets, and UI shows warnings when inputs are weak.
