# depOS

**depOS** (Dependency Map OS) is an architecture-intelligence product: blast-radius analysis, diagnostics-aware dependency graphs, and LLM-oriented context for modern engineering teams. This repository hosts the application workstream and currently **vendors the graphify extraction library** under its original license for static graph generation.

Documentation lives in **[`docs/`](docs/README.md)**.

| Doc | Description |
| --- | ------------- |
| [docs/README.md](docs/README.md) | Documentation index |
| [docs/product.md](docs/product.md) | Product vision and MVP scope |
| [docs/architecture.md](docs/architecture.md) | System architecture and graph pipeline |
| [docs/graphify-internals.md](docs/graphify-internals.md) | Vendored graphify module map (extraction, build, export) |

## Quick links

- **License:** see [LICENSE](LICENSE) (includes graphify upstream MIT).
- **Python package:** the installable package in this repo remains the historical `graphifyy` / `graphify` CLI until renamed in a future release.

For development setup of the vendored library, see [docs/development.md](docs/development.md).

## Running locally (Supabase + depOS API + web)

depOS persists orgs, repos, audit logs, CI signals, and intelligence-layer
artifacts in Supabase Postgres. Auth is Supabase Auth. Start the full stack:

```bash
# 1. Supabase (Postgres + Auth + Studio). Requires Docker + Supabase CLI.
supabase start
supabase db reset          # applies supabase/migrations/*.sql + seed.sql

# 2. Backend env: copy .env.example to .env and fill the keys supabase
#    printed in step 1 (anon / service-role / jwt-secret).
cp .env.example .env
```

See [`supabase/README.md`](supabase/README.md) for the full variable list and
RLS model.

### depOS API

```bash
pip install -e ".[depos,supabase]"
depos-api
# or: python -m uvicorn depos.api_server:app --host 0.0.0.0 --port 8080
```

**Public:** `GET /health`, `GET /ready`.

**Internal** (require `DEPOS_INTERNAL_API_KEY` via `X-DepOS-Internal-Key` or
`Authorization: Bearer <same>` when that env var is set): `POST /v1/snapshot`,
`POST /v1/federation/preview`, `POST /v1/drift` (server-local graph JSON paths).

**Tenant** (`Authorization: Bearer <supabase-jwt>`): org/repo CRUD, CI, graph
snapshots, federation/drift from Storage, intelligence runs — for example
`POST /v1/orgs/{slug}/graph-snapshots/prepare` → upload JSON to the signed URL
→ `POST /v1/orgs/{slug}/graph-snapshots/{id}/complete` →
`POST /v1/ci/analyze` with `org_slug`, `repo_slug`, and `graph_snapshot_id`
(optional `root` only together with the internal key for workers).
`POST /v1/federation/snapshots`, `POST /v1/drift/snapshots`,
`POST /v1/ci/postci`, `POST /v1/orgs`, `GET /v1/orgs/{slug}/repos`,
`PATCH /v1/repos/toggle`, `GET /v1/me`,
`POST/GET /v1/orgs/{slug}/intelligence/runs`, `GET .../runs/{run_id}`.

Production (`DEPOS_ENV=production`) requires `DEPOS_INTERNAL_API_KEY`,
non-wildcard `DEPOS_CORS_ORIGINS`, and `DEPOS_GRAPH_BUCKET`. See
[docs/ci-oidc.md](docs/ci-oidc.md) for GitHub Actions → API trust without
long-lived passwords.

### depOS intelligence CLI

```bash
pip install -e ".[depos,supabase,intelligence]"
depos-intel --help
depos-intel analyze coverage --path .
```

### Web dashboard

```bash
cp apps/web/.env.local.example apps/web/.env.local    # edit with your keys
cd apps/web && npm install && npm run dev
```

Open [http://localhost:3001](http://localhost:3001). Sign up or log in;
protected routes under `/repos` require an authenticated session.

## Layout

| Path | Purpose |
| --- | --- |
| `depos/` | Product Python package (snapshot, fusion, blast, API) |
| `graphify/` | Vendored static graph library (MIT) |
| `apps/web/` | Next.js UI shell |
| `apps/worker/` | Worker notes / future job runners |
