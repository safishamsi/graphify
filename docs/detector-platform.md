# depOS detector platform

The detector platform is the depOS intelligence v2 path for cross-universe findings. It keeps the existing graph-first pipeline, but turns Module 2 into a registry of many small detectors instead of one fixed candidate generator.

## Layers

1. Layer 0 ingest extends the graph with dependency, env/config, prompt, OpenAPI, Next.js, and infra nodes under `depos/ingest/`.
2. Layer 1 enrichment stitches those universes back to code through `depos/enrichment/*_resolver.py` and records structured probe errors.
3. Layer 2 detectors under `depos/analysis/detectors/` emit candidates with detector metadata and deterministic replay envelopes.
4. Layer 3 reasoning stays optional. Mechanical detectors skip LLMs entirely.
5. Layer 4 verifier remains the trust boundary and now includes oracle, negation, cross-universe, and version checks.
6. Layer 5 stores findings, detector stats, ingest reports, and observability rows.

## Detector contract

Each built-in detector exports:

- `SPEC = Detector(...)`
- `run(graph, manifest, mode, config, ctx) -> list[Candidate]`

`Candidate.extra["detector"]` is normalized into:

- `detector_name`
- `detector_version`
- `pipeline_version`
- `severity`
- `oracle_hints`

That envelope is what lets the verifier and persistence layer replay the exact decision path later.

## DSL

The detector DSL is intentionally small and safe. It is parsed with `ast.parse(..., mode="eval")` and only allows:

- boolean operators and comparisons
- literal containers
- attribute access without dunders
- direct helper calls from `depos/analysis/detectors/dsl_helpers.py`

Helpful built-ins include:

- `attr(obj, key)`
- `regex(pattern, value)`
- `has_edge(graph, rel, src, dst)`
- `count(items)`
- `version_satisfies(range_spec, version)`
- `cross_universe(node)`
- `schema_validate(schema_id, payload)`

## Adding a detector

1. Pick the universe and witness shape you want.
2. Add or reuse ingest/resolver support if the needed nodes or edges do not exist yet.
3. Create `depos/analysis/detectors/builtin/<name>.py`.
4. Define `SPEC` with verifier checks and `requires_reasoner`.
5. Emit candidates through `make_candidate(...)`.
6. Add positive, negative, and verifier coverage under `tests/detectors/`.
7. Snapshot the registry with `scripts/snapshot_detector_registry.py`.

## Cross-universe node kinds

The shared taxonomy lives in `depos/analysis/schemas.py` and currently includes:

- `package_manifest`, `package_dep`, `lockfile_resolution`
- `env_var`, `config_key`
- `prompt_template`
- `openapi_operation`, `openapi_schema`
- `next_route`, `next_middleware`
- `infra_workflow`, `infra_service`, `dockerfile_stage`

## GraphCodeBERT

GraphCodeBERT is now an operational pre-ranker, but it is opt-in through `config.ranker.use_graphcodebert` and defaults to off. The dataset pipeline still uses it directly for bundle triage.

## Operational guardrails

- Node-link graph JSON is normalized through `graphify/nx_compat.py` so both legacy `links` payloads and newer NetworkX `edges` payloads keep working across exports, snapshots, the CLI, benchmarks, and MCP serving.
- The gray-zone evaluator only surfaces ambiguous findings as `evaluator_surfaced`; it never upgrades them to `confirmed`, and the audit pass tightened the dissent logic so unavailable verifier checks stay ambiguous instead of being over-penalized.
