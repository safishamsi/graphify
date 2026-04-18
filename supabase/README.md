# Supabase (depOS)

This folder holds the Supabase project scaffold for depOS: config, migrations,
and a local-dev seed. Every migration ends in the 14-digit `YYYYMMDDHHmmss_` prefix
consumed by the intelligence layer's migration sequencer
(see `depos/analysis/config.py` → `migration_timestamp_pattern`).

## Layout

```
supabase/
  config.toml                    Local project config for `supabase start`
  seed.sql                       Demo org + repos for local dev
  migrations/
    20260417120000_init_organizations.sql
    20260417120100_init_profiles_and_members.sql
    20260417120200_init_repositories.sql
    20260417120300_init_audit_logs.sql
    20260417120400_init_ci_signals.sql
    20260417120500_init_intelligence_runs.sql
    20260418120000_init_graph_snapshots.sql
    20260418120100_storage_graph_snapshots_bucket.sql
```

Migrations also create the private Storage bucket **`graph-snapshots`** (override
name with env `DEPOS_GRAPH_BUCKET` if you change it).

## Local development

Prerequisite: [Supabase CLI](https://supabase.com/docs/guides/cli) and Docker.

```bash
supabase start
supabase db reset    # applies migrations + seed.sql
```

`supabase start` exposes:

- API / REST / Auth at `http://127.0.0.1:54321`
- Postgres at `127.0.0.1:54322` (user `postgres`, password `postgres`)
- Studio at `http://127.0.0.1:54323`
- Inbucket (email testing) at `http://127.0.0.1:54324`

Copy the printed anon and service-role keys into `.env` / `apps/web/.env.local`.

## Environment variables

Backend (`.env`):

- `DATABASE_URL` — `postgres://postgres:postgres@127.0.0.1:54322/postgres`
- `SUPABASE_URL` — `http://127.0.0.1:54321`
- `SUPABASE_ANON_KEY` — from `supabase start` output
- `SUPABASE_SERVICE_ROLE_KEY` — from `supabase start` output
- `SUPABASE_JWT_SECRET` — from `supabase start` output
- `SUPABASE_JWT_ALG` — `HS256` locally, `RS256` with JWKS in production

Next.js (`apps/web/.env.local`):

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_DEPOS_API_URL` — e.g. `http://127.0.0.1:8080`

## RLS model

Every table in `public` enables RLS. Access is gated by membership in
`public.organization_members` via the `SECURITY DEFINER` helpers
`public.is_org_member(uuid)` and `public.is_org_admin(uuid)`. The service role
key bypasses RLS and is used by the FastAPI backend for internal operations
(snapshot, federation, intelligence runs).

- `profiles` — self-access only
- `organizations` — members read, admins write; authenticated users may create
  (trigger auto-inserts them as owner)
- `organization_members` — admins manage, members see their own + peers
- `repositories` — members read, admins write
- `audit_logs` — members read, service-role writes
- `ci_signals` — members read (or `org_id is null` legacy rows), service-role writes
- `intelligence_runs`, `intelligence_findings` — members read, service-role writes

## Acceptance tests that touch Supabase

- #2 Remove `organization_members` (via a new migration) while FastAPI handlers
  still reference it → Module 1 migration sequencer flags the table as removed
  in-branch; Module 6 verifier check 2 returns `fail`; finding lands at
  `confirmed`.
- #3 A FastAPI route with no explicit auth guard but fully covered by an RLS
  policy on the table it touches → NOT flagged as missing-guard.
- #4 A Celery worker using the service-role client against an RLS-protected
  table → Module 1 emits `rls_coverage: context_mismatch`; Module 6 caps the
  finding at `partially_confirmed`.
