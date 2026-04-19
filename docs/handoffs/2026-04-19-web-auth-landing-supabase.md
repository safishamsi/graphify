# Handoff: web auth, landing, and Supabase-facing work (19 Apr 2026)

**For teammates** — status after the Supabase-aligned web and auth workstream. Use this as the canonical “what’s done / what’s next” note until the next handoff replaces it.

---

## Done (landed in tree)

### Supabase conversion (product-facing)

- **API + data:** depOS already runs on **Postgres via Supabase** (no SQLite path). Migrations, RLS, and Storage for graph snapshots are in `supabase/migrations/` — see [`supabase/README.md`](../../supabase/README.md) and root [`README.md`](../../README.md).
- **Auth:** End-user auth is **Supabase Auth** end-to-end on the web app: JWT sessions, email confirmation, password reset, magic link / OTP paths, and middleware protection for `/orgs/*`.
- **Web env:** `apps/web` reads `NEXT_PUBLIC_SUPABASE_*` (and related keys); the web `prebuild` script syncs repo-root `.env` into `apps/web/.env.local` for local dev.

### Landing page

- Marketing **`/`** was rebuilt as a **dark, graph-native** experience: design tokens in `apps/web/styles/theme.ts`, Tailwind mapping, Framer Motion, and reusable marketing sections (hero, features, pipeline, etc.). This is the visual baseline for the rest of the product UI.

### Sign in / sign up / auth UX

Primary routes (all custom UI — not Supabase hosted widgets):

| Route | Purpose |
| --- | --- |
| `/auth/sign-in` | Email + password; magic link tab |
| `/auth/sign-up` | Registration + confirmation pending state |
| `/auth/forgot-password` | Reset email request |
| `/auth/reset-password` | New password (recovery session) |
| `/auth/verify` | OTP entry when needed |
| `/auth/callback` | PKCE `code` exchange |
| `/auth/confirm` | `token_hash` email links |
| `/auth/sign-out` | POST/GET sign-out (used by forms and `/orgs/logout`) |

**Legacy:** `/login` and `/signup` **redirect** to `/auth/sign-in` and `/auth/sign-up` (preserving `next` where safe). Middleware sends unauthenticated users to **`/auth/sign-in?next=…`**.

**Console:** Org shell sidebar links to **`/orgs/logout`** for a confirmation step before POSTing to `/auth/sign-out`.

Supporting code lives under `apps/web/lib/auth/` (errors, actions, redirects, hooks, `AuthProvider`) and `apps/web/components/auth/`.

---

## Still to do / needs review

### Backend intelligence pipeline — Gemma 4 and GraphCodeBERT

The **dataset → normalize → GraphCodeBERT → Gemma → verifier** path is documented in [`docs/dataset-pipeline.md`](../dataset-pipeline.md), but it has **not** been fully re-validated against the latest model/tooling choices:

- **GraphCodeBERT** — scoring stage assumptions (weights, tokenizer, batching, hardware) should be reviewed for current deps and reproducibility.
- **Gemma 4** — reasoning stage: prompt contracts, API or local runner, and output schema alignment with the verifier need a focused pass.

**Ask:** Whoever owns intelligence should schedule a **pipeline review** (run `depos-intel analyze dataset-pipeline …` on the sample dataset, inspect artifacts, update `dataset-pipeline.md` if behavior or flags drift).

---

## Quick pointers

| Topic | Where |
| --- | --- |
| Auth routes + middleware | `apps/web/middleware.ts`, `apps/web/app/auth/` |
| Auth client utilities | `apps/web/lib/auth/` |
| Design tokens | `apps/web/styles/theme.ts` |
| Org console | `apps/web/app/orgs/` |
| Dataset / LLM pipeline | `docs/dataset-pipeline.md`, `depos/` intelligence modules |

If this handoff disagrees with the repo, **the code and migrations win** — update this file when you change the above.
