# depOS - architecture

## Graph construction

depOS keeps graphify's graph-building logic for code snapshots:

- `graphify.extract.extract`
- `graphify.build.build_from_json`
- `graphify.nx_compat` to normalize node-link JSON across legacy `links` payloads and newer NetworkX `edges` payloads

That path owns NetworkX assembly, node IDs, and edge reconciliation. Diagnostics attach after the graph is built unless a future change extends graphify's extraction schema in a validated way.

## Goals

- Graph-first and change-aware
- Diagnostics-fused
- CI-native
- Org-scoped and allowlist-aware
- LLM-exportable without losing provenance

## Layered pipeline

| Layer | Role |
| --- | --- |
| Layer 0 ingest | Extend the code graph with dependency, env/config, prompt, OpenAPI, Next.js, and infra nodes. |
| Layer 1 enrichment | Stitch those universes back to code through semantic probes and resolvers. |
| Layer 2 detectors | Emit replayable candidates from many small registered decision trees. |
| Layer 3 reasoner | Optional LLM stage only for detectors that require it. |
| Layer 4 verifier | Deterministic trust boundary plus local oracles, negation checks, and cross-universe checks. |
| Layer 5 ranking/store | Phase-0 ranking, gray-zone evaluation, persistence, and observability. |

## Logical components

| Component | Role |
| --- | --- |
| Snapshot worker | Clone + run vendored `graphify` extract/build; persist node-link graph per `(repo, commit)`. |
| Diagnostics fusion | Map SARIF and tool output onto graph nodes and edges. |
| Federation | Resolve cross-repo edges within the configured allowlist. |
| Blast engine | Seed from git diff; k-hop expansion on directed graph; defect-aware ranking. |
| Detector platform | Cross-universe candidate generation over code, deps, env, prompts, schema, Next.js, and infra. |
| API | Auth, org/repo settings, CI callback, detector registry, and intelligence run storage. |
| Web app | Dashboards, graph explorer with error overlays, allowlist admin, and CI history. |

## Data flow

```mermaid
flowchart LR
  source[Source tree] --> graph[Graph snapshot]
  diagnostics[Diagnostics] --> fusion[Diagnostics fusion]
  graph --> ingest[Layer 0 ingest]
  ingest --> enrich[Layer 1 enrichment]
  fusion --> enrich
  enrich --> detectors[Layer 2 detectors]
  detectors --> verifier[Layer 4 verifier]
  detectors --> reasoner[Layer 3 reasoner]
  reasoner --> verifier
  verifier --> store[Store / API / artifacts]
```

## Graph contract for AI consumers

- Nodes may include `errors[]` with category, severity, rule id, message, and provenance.
- Edges may include `fault` metadata and cross-universe relation metadata.
- Responses should include a compact error index and optional blast-radius summary.
- GraphCodeBERT can act as a pre-ranker in the operational pipeline, but only behind `config.ranker.use_graphcodebert` and defaults to off.

See [detector-platform.md](detector-platform.md) for the detector authoring contract and [graphify-internals.md](graphify-internals.md) for the extraction engine details.
