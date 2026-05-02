# Docker MCP Toolkit + SQLite MCP server

A reproducible runbook for installing the **SQLite MCP server** into the
[Docker MCP Toolkit](https://docs.docker.com/desktop/features/mcp/) so any
connected MCP client (Claude Code, Claude Desktop, Cursor, VS Code, etc.) gains
six SQLite tools: `read_query`, `write_query`, `create_table`, `list_tables`,
`describe_table`, and `append_insight`.

This document is *not* required to use graphify — it lives here as a known-good
recipe for users who want a lightweight, persistent SQL workspace exposed to
their AI clients alongside graphify's knowledge-graph tools.

## Why SQLite (and not `sqlite-mcp-server`)
At time of writing the catalog ships two SQLite MCP images:

| Catalog name        | Image                  | Status |
| ------------------- | ---------------------- | ------ |
| `SQLite`            | `mcp/sqlite`           | Marked "Archived" in catalog metadata, but **boots and serves correctly** |
| `sqlite-mcp-server` | `mcp/sqlite-mcp-server`| **Broken**: entrypoint `/app/.venv/bin/mcp-server-sqlite` does not exist in the published layer |

Use `SQLite` (`mcp/sqlite`) until the newer image is fixed upstream.

## Prerequisites
- Docker Desktop running and healthy
  - `docker info` returns a `Server Version`
  - Public socket present at `/var/run/docker.sock` (or its symlink to
    `~/.docker/run/docker.sock`)
- Docker MCP Toolkit CLI plugin (`docker mcp`)
  - Bundled with recent Docker Desktop releases; `docker mcp --version` should
    print a version string

## Install
```bash
# Add the working SQLite server to the default MCP profile
docker mcp profile server add default \
  --server catalog://mcp/docker-mcp-catalog/SQLite

# Pre-pull the image so the first tool call is fast
docker pull mcp/sqlite:latest
```

Verify the profile now contains both `fetch` (built-in) and `SQLite`:
```bash
docker mcp profile show default | grep -E '^[[:space:]]+name:'
```

Expected output:
```
            name: fetch
            name: SQLite
```

The Docker MCP gateway should now expose 6 additional tools:
```bash
docker mcp tools count
# → 15 tools (was 9 before adding SQLite)
```

## Smoke test
The CLI can call MCP tools directly (each call boots a fresh gateway, ~5s
overhead per call):
```bash
docker mcp tools call list_tables
docker mcp tools call create_table \
  query='CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)'
docker mcp tools call write_query \
  query="INSERT INTO notes(body) VALUES ('first row'), ('second row')"
docker mcp tools call read_query \
  query='SELECT * FROM notes ORDER BY id'
docker mcp tools call describe_table table_name=notes
docker mcp tools call append_insight insight='3 rows inserted; aggregates work.'
```

`read_query` should return the inserted rows with timestamps.

## Storage layout
Database file lives in a Docker named volume `mcp-sqlite`, mounted at `/mcp`
inside containers:
```
mcp-sqlite (named volume) → /mcp/db.sqlite
```

Inspect from the host:
```bash
docker volume inspect mcp-sqlite
docker run --rm -v mcp-sqlite:/mcp:ro alpine ls -la /mcp
docker run --rm -v mcp-sqlite:/mcp:ro keinos/sqlite3 \
  sqlite3 /mcp/db.sqlite '.schema'
```

The volume persists across `docker run --rm` invocations of the SQLite MCP
container, so writes from one MCP tool call are visible to the next.

## Wiring into MCP clients
Connect once per client; the gateway exposes every server in the active profile:
```bash
docker mcp client connect claude-code   # already connected for many users
docker mcp client connect cursor
docker mcp client connect vscode
docker mcp client connect claude-desktop
# Supported: claude-code, claude-desktop, cline, codex, continue, crush,
#            cursor, gemini, goose, gordon, kiro, lmstudio, opencode, sema4,
#            vscode, zed
```

Verify wiring:
```bash
docker mcp client ls
```

## Uninstall / reset
```bash
# Remove server from the profile
docker mcp profile server remove default SQLite

# Drop the database volume (irreversible)
docker volume rm mcp-sqlite

# Remove the image
docker rmi mcp/sqlite:latest
```

## Troubleshooting
- **`starting client: calling "initialize": EOF`** — the requested server
  failed its MCP handshake. Run the image directly to see the error:
  ```bash
  printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0.0"}}}\n' \
    | docker run --rm -i -v mcp-sqlite:/mcp <image-ref> --db-path /mcp/db.sqlite
  ```
  Common causes: missing entrypoint binary in the image (the
  `sqlite-mcp-server` failure mode) or missing required env/secrets.
- **`cannot use --enable-all-servers with --servers flag`** — these gateway
  args are mutually exclusive; pick one.
- **No new tools appear in `docker mcp tools count` after install** — the
  gateway may be running with `dynamic-tools` enabled, exposing only meta-tools
  (`mcp-add`, `mcp-find`, …) until a profile is activated mid-session. Either
  invoke `docker mcp tools` (which spins up an ephemeral gateway against the
  default profile) or call `mcp-activate-profile` from inside an MCP session.
