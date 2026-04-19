# depOS documentation

**depOS** is the working name for the Dependency Map OS application: CI-centric dependency intelligence, cross-branch and cross-repository blast radius (with org-controlled allowlists), diagnostics fused into graphs for AI tools (Claude Code, MCP, and other LLMs), and a full product UI.

## Contents

1. **[Product](product.md)** — Problem, positioning, MVP goals, and what depOS adds beyond static graphs.
2. **[Architecture](architecture.md)** — High-level components, data flow, CI integration, and how diagnostics attach to graphs.
3. **[Graphify internals](graphify-internals.md)** — The vendored `graphify/` Python package: pipeline, modules, and extending extraction.
4. **[Development](development.md)** — Local setup, tests, and packaging notes.
5. **[Dataset pipeline](dataset-pipeline.md)** — How to run the raw AST dataset through normalization, GraphCodeBERT, Gemma, verifier, and gray-zone evaluation.
6. **[CI / OIDC trust](ci-oidc.md)** — How GitHub Actions should authenticate to the depOS API in production (short-lived tokens, OIDC).
7. **[Handoff: web auth, landing, Supabase (Apr 2026)](handoffs/2026-04-19-web-auth-landing-supabase.md)** — **Current** teammate summary: Supabase auth + web alignment, landing redesign, `/auth/*` routes; **open:** review intelligence pipeline for Gemma 4 and GraphCodeBERT.
8. **[Handoff: last three commits (Apr 2026)](handoffs/2026-04-18-last-three-commits.md)** — Historical note on Postgres-only DB, backend hardening + migrations, first `/orgs` console cut.

## Relationship to graphify

This repo contains the **graphify** library (upstream-derived) as the engine for parsing code into nodes and edges. depOS documentation describes the **product**; graphify internals describe the **library** used inside that product.
