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

## depOS API (optional)

```bash
pip install -e ".[depos]"
depos-api
# or: python -m uvicorn depos.api_server:app --host 0.0.0.0 --port 8080
```

Endpoints include `POST /v1/snapshot`, `POST /v1/ci/analyze`, `POST /v1/ci/postci`, org/repo toggles, and `POST /v1/federation/preview`.

## Web dashboard (optional)

```bash
cd apps/web && npm install && npm run dev
```

Open [http://localhost:3001](http://localhost:3001).

## Layout

| Path | Purpose |
| --- | --- |
| `depos/` | Product Python package (snapshot, fusion, blast, API) |
| `graphify/` | Vendored static graph library (MIT) |
| `apps/web/` | Next.js UI shell |
| `apps/worker/` | Worker notes / future job runners |
