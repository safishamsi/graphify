# Handoff: last three commits (18 Apr 2026)

Short summary for teammates of what landed in **`12d30a2` → `2778234` → `e1a5620`** (oldest to newest). Commit messages on the branch are minimal; this doc spells out intent and touchpoints.

| Commit     | Subject            |
| ---------- | ------------------ |
| `12d30a2`  | no more sqlite     |
| `2778234`  | tightened backend  |
| `e1a5620`  | frontend           |

---

## 1. `12d30a2` — no more sqlite

**Intent:** depOS API always talks to **Postgres** (Supabase); the old SQLite dev path is gone.

**What changed**

- **`depos/db.py`** — `DATABASE_URL` is **required**. It must look like a Postgres URL (`postgres://`, `postgresql://`, or `postgresql+…`). If it is missing or not Postgres, startup raises a **clear `RuntimeError`** with pointers to `supabase start` / hosted project settings. Removed `DEPOS_ALLOW_SQLITE_FALLBACK`, on-disk `depos.db`, and the `db_path` arguments on `get_engine` / `get_session_factory` / `get_session`.
- **`depos/api_server.py`** — Tiny follow-up aligned with the DB layer (no behavioral expansion in this commit).
- **`.env.example`** — Dropped SQLite-related env hints so new setups default to Postgres only.

**What you need to do locally**

- Run **`supabase start`** (or use a hosted DB) and set **`DATABASE_URL`** to the pooler/direct connection string Supabase prints. See root **`.env.example`**.

---

## 2. `2778234` — tightened backend

**Intent:** Production-shaped API: more routes, storage-backed graph snapshots, intelligence persistence hooks, security tests, CI, and docs.

**Highlights (non-exhaustive)**

- **`depos/api_server.py`** — Large expansion: tenant routes for orgs, repos, CI analyze/postci, graph snapshot **prepare/complete**, federation/drift snapshot endpoints, intelligence runs, `/v1/me`, etc. (Aligns with what the new web app calls.)
- **`depos/graph_storage.py`** — Signed upload / graph blob access for snapshots.
- **`depos/intelligence_store.py`** — Intelligence run/findings persistence path.
- **`depos/internal_auth.py`**, **`depos/settings.py`** — Internal/auth and settings wiring.
- **`depos/postci.py`** — Post-CI correlation adjustments for API usage.
- **`depos/snapshot.py`** — Snapshot-related tweaks for the new flow.
- **Supabase migrations** — `graph_snapshots` table + **Storage bucket** for graph JSON (`supabase/migrations/20260418120000_*`, `20260418120100_*`).
- **`.github/workflows/depos-ci.yml`** — CI updates for the new stack.
- **`tests/test_api_security.py`**, **`tests/test_graph_snapshot_flow.py`**, updates to **`tests/test_depos_api.py`** — Coverage for security and snapshot flow.
- **Docs** — **`docs/ci-oidc.md`**, **`docs/README.md`**, **`README.md`**, **`supabase/README.md`** — How to run things and OIDC notes.
- **`.cursor/plans/backend_production_readiness_df6d0663.plan.md`** — Planning artifact checked in next to the work.

**Teammate checklist**

- Apply **Supabase migrations** and ensure **Storage** policies/bucket exist for your environment.
- Re-read root **`README.md`** and **`.env.example`** for any new variables (CORS, bucket names, etc.).

---

## 3. `e1a5620` — frontend

**Intent:** Replace the minimal Next shell with the **org-scoped depOS console** under **`/orgs/*`**, wired to FastAPI with the Supabase JWT and **RLS-backed reads** where lists come from Postgres.

**What changed**

- **`apps/web/`** — New route tree: **`/orgs`**, **`/orgs/[slug]`** (dashboard), **`repos`**, **`snapshots`**, **`analyze`**, **`postci`**, **`ci`**, **`federation`**, **`drift`**, **`intelligence`** (+ run detail). Server actions in **`app/orgs/[slug]/actions.ts`**; org create in **`app/orgs/actions.ts`**.
- **Removed** flat **`/repos`** and **`/ci`** app routes; **`next.config.js`** redirects those paths toward **`/orgs`**.
- **`middleware.ts`** — Auth gate on **`/orgs`** (logged-out users → **`/login?next=…`**).
- **`lib/depos/`** — `api.ts`, `types.ts`, `server.ts`, `roles.ts` for JWT calls and admin checks.
- **`lib/supabase/queries.ts`** — Org id by slug + list helpers for snapshots, CI signals, intelligence runs (SELECT-only, RLS).
- **UI** — `AppShell`, sidebar nav, org switcher (`GET /v1/me`), Radix-based controls, **`globals.css`** design tokens, **`next/font`** (Fraunces + IBM Plex Sans), marketing **`/`** + auth polish.
- **`apps/web/.env.local.example`**, **`README.md`** — **`NEXT_PUBLIC_DEPOS_API_URL`**, Supabase keys, and **CORS** (`DEPOS_CORS_ORIGINS` must include the web origin, e.g. `http://localhost:3001`).
- **`apps/web/DESIGN_LAYER1.md`** — Layer 1 design checkpoint for the shell.
- **`.cursor/plans/depos_web_frontend_44bea6cf.plan.md`** — Full frontend plan artifact.

**How to run the web app**

```bash
cd apps/web && npm install && npm run dev
```

Default dev port is **3001** (see `package.json`). Ensure API CORS allows that origin.

---

## Quick “who owns what” map

| Layer        | Where to look |
| ------------ | ------------- |
| API contract | `depos/api_server.py`, `apps/web/lib/depos/types.ts` |
| DB / RLS     | `supabase/migrations/`, `depos/db.py` |
| Web data     | `apps/web/lib/supabase/queries.ts`, org pages under `apps/web/app/orgs/` |

If something in this handoff disagrees with the tree, **git is authoritative** — use `git show <commit> --stat` on each hash above.
