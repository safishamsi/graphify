# Detector Registry

> Snapshot of the built-in detector registry in the detector-platform rollout.

## Code graph

- `diff-anchor`
- `interface-surface`
- `graph-anomaly`
- `lexical-keyword-seed`

## Dependencies

- `dep-version-mismatch-across-workspaces`
- `lockfile-drift`
- `peer-dep-unsatisfied`
- `phantom-dep`
- `unused-dep`
- `vulnerable-dep`
- `transitive-pin-conflict`

## Env and config

- `env-var-referenced-but-undefined`
- `env-var-defined-but-unused`
- `env-var-typed-drift`
- `next-route-protected-in-middleware-but-not-layout`
- `cors-origin-omits-known-client-origin`
- `redirect-target-not-safelisted`

## Prompt and template

- `prompt-missing-required-field`
- `prompt-field-type-mismatch`
- `prompt-references-undefined-variable`
- `prompt-drift-between-provider-versions`

## Schema and contract

- `request-body-missing-required-field`
- `response-field-consumed-but-not-produced`
- `enum-value-used-but-not-in-schema`
- `migration-adds-not-null-without-default`

## Auth and authorization

- `route-without-session-check`
- `rpc-invoked-without-rls-or-service-role`
- `password-reset-link-handler-redirects-to-external-origin`
- `cookie-set-without-httponly-or-secure-in-prod`

## Flow and control

- `error-swallowed-in-async-handler`
- `awaitable-returned-unawaited`
- `transaction-started-but-not-committed-on-all-branches`

## Build and infra

- `dockerfile-copies-path-not-in-build-context`
- `gha-workflow-uses-secret-not-declared`
- `gha-matrix-node-version-diverges-from-engines`
- `compose-service-depends-on-service-with-different-network`
