# Security policy — depOS

## Reporting

Do **not** open a public issue for undisclosed security vulnerabilities. Use GitHub private vulnerability reporting or contact maintainers privately. Include reproduction steps, impact, and affected components.

## Supported versions

Security support follows active **depOS** release branches; see release notes when published.

## Scope

This repository contains:

1. **depOS application documentation** and future services (API, workers, web) — follow least privilege for tokens (GitHub App, CI secrets, database credentials).
2. The **vendored graphify library** — primarily a local analysis tool and optional MCP server.

### Graphify (local library) — reference

When running graph analysis locally, graphify limits fetch URLs, response sizes, and path access for MCP; see `graphify/security.py` and upstream threat notes. Network use is limited to explicit user-driven ingest flows.

### depOS (planned SaaS)

- Enforce authentication and authorization on org/repo allowlists.
- Never send repository contents to third parties without customer policy.
- Treat SARIF and CI artifacts as sensitive; encrypt at rest and in transit.
- Rotate GitHub App keys and API tokens on schedule.

Details will expand as the cloud surface ships.
