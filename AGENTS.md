## depOS

This repository is oriented around **depOS** (Dependency Map OS). Product and architecture docs are under [`docs/`](docs/README.md).

### When a graph exists

If `graphify-out/GRAPH_REPORT.md` is present (from running the vendored `graphify` tooling), use it for high-level structure before deep file reads.

### After code changes

If you use the local graphify CLI, run `graphify update .` to refresh AST-only graphs when appropriate.

### Documentation

Prefer [`docs/architecture.md`](docs/architecture.md), [`docs/product.md`](docs/product.md), and [`docs/detector-platform.md`](docs/detector-platform.md) for depOS direction. For **current teammate status** (web, Supabase auth, landing, open pipeline work), see [`docs/handoffs/2026-04-19-web-auth-landing-supabase.md`](docs/handoffs/2026-04-19-web-auth-landing-supabase.md). For the detector rollout specifically, see [`docs/handoffs/2026-04-19-detector-platform.md`](docs/handoffs/2026-04-19-detector-platform.md).
