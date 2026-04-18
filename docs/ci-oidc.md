# GitHub Actions and depOS API trust (OIDC)

Today, tenant APIs require a **Supabase user JWT** (`Authorization: Bearer`). GitHub Actions does not receive that token automatically. For **multi-tenant SaaS** you should avoid long-lived user passwords in repository secrets.

## Recommended pattern: GitHub OIDC

1. **Enable OIDC** on the workflow (`permissions: id-token: write`).
2. **Issue a short-lived depOS token** from your API (or an auth gateway) that:
   - Verifies the GitHub OIDC JWT (issuer `https://token.actions.githubusercontent.com`, audience you configure).
   - Checks claims: `repository`, `ref`, `sha`, and optionally `environment`.
   - Returns a **narrow-scoped** bearer token (minutes TTL) limited to `POST /v1/orgs/{org}/graph-snapshots/*` and `POST /v1/ci/analyze` for that repository.

3. **Workflow** exchanges OIDC for that token, then runs prepare → upload → complete → analyze as documented in the root `README.md`.

## What you must configure outside this repo

- **GitHub**: allowed OIDC subjects (repo/environment) matching your policy.
- **API / gateway**: JWKS or PEM for GitHub’s signing keys, plus mapping from `repository` to `org_slug` / `repo_slug` in depOS.
- **No** static Supabase user password in `GITHUB_TOKEN`-visible logs; prefer the short-lived exchange token only.

## Alternative: GitHub App

Install a **GitHub App** on selected repositories; the API verifies `installation` JWTs or uses installation tokens server-side to clone and snapshot. Heavier than OIDC but gives strong repo identity.
