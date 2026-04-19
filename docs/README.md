# depOS documentation

**depOS** is the working name for the Dependency Map OS application: CI-centric dependency intelligence, cross-branch and cross-repository blast radius (with org-controlled allowlists), diagnostics fused into graphs for AI tools, and a product UI on top.

## Contents

1. **[Product](product.md)** - Problem, positioning, MVP goals, and what depOS adds beyond static graphs.
2. **[Architecture](architecture.md)** - High-level components, layered pipeline, and how diagnostics attach to graphs.
3. **[Detector platform](detector-platform.md)** - Cross-universe ingest, detector registry, verifier oracles, and how to add a detector.
4. **[Graphify internals](graphify-internals.md)** - The vendored `graphify/` Python package: pipeline, modules, and extending extraction.
5. **[Development](development.md)** - Local setup, tests, and packaging notes.
6. **[Dataset pipeline](dataset-pipeline.md)** - How to run the raw AST dataset through normalization, GraphCodeBERT, Gemma, verifier, and gray-zone evaluation.
7. **[Detector registry](detector-registry.md)** - Snapshot of built-in detector names grouped by family.
8. **[CI / OIDC trust](ci-oidc.md)** - How GitHub Actions should authenticate to the depOS API in production.
9. **[Handoff: detector platform (Apr 2026)](handoffs/2026-04-19-detector-platform.md)** - Detector-platform rollout summary and operational notes.
10. **[Handoff: web auth, landing, Supabase (Apr 2026)](handoffs/2026-04-19-web-auth-landing-supabase.md)** - Web/auth status and related UI/backend work.
11. **[Handoff: last three commits (Apr 2026)](handoffs/2026-04-18-last-three-commits.md)** - Historical note on backend hardening, migrations, and early org-console work.

## Relationship to graphify

This repo contains the **graphify** library as the engine for parsing code into nodes and edges. depOS documentation describes the **product and intelligence platform**; graphify internals describe the **library** used inside that product.
