# Graph Report - worked\mcp-pipeline  (2026-05-27)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 59 nodes · 82 edges · 15 communities (9 shown, 6 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `eea5778e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]

## God Nodes (most connected - your core abstractions)
1. `npx` - 13 edges
2. `uvx` - 11 edges
3. `slack` - 5 edges
4. `filesystem` - 4 edges
5. `github` - 4 edges
6. `brave-search` - 4 edges
7. `google-maps` - 4 edges
8. `everything-search` - 4 edges
9. `cdk-mcp` - 4 edges
10. `cost-analysis` - 4 edges

## Surprising Connections (you probably didn't know these)
- `filesystem` --references--> `npx`  [EXTRACTED]
  mcp.json → mcp.json  _Bridges community 5 → community 6_
- `github` --references--> `npx`  [EXTRACTED]
  mcp.json → mcp.json  _Bridges community 6 → community 3_
- `postgres` --references--> `npx`  [EXTRACTED]
  mcp.json → mcp.json  _Bridges community 6 → community 11_
- `puppeteer` --references--> `npx`  [EXTRACTED]
  mcp.json → mcp.json  _Bridges community 6 → community 12_
- `brave-search` --references--> `npx`  [EXTRACTED]
  mcp.json → mcp.json  _Bridges community 6 → community 7_

## Communities (15 total, 6 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.16
Nodes (14): AWS_PROFILE, AWS_REGION, EVERYTHING_SDK_PATH, uvx, docker-mcp, mcp-pandoc, mcp-server-everything-search, mcp-text-editor (+6 more)

### Community 1 - "Community 1"
Cohesion: 0.18
Nodes (10): @kazuph/mcp-taskmanager, mcp-logic, mcp-neo4j-cypher, mcp-server-fetch, mcp-solver, fetch, mcp-logic, mcp-solver (+2 more)

### Community 2 - "Community 2"
Cohesion: 0.50
Nodes (4): SLACK_BOT_TOKEN, SLACK_TEAM_ID, @modelcontextprotocol/server-slack, slack

### Community 3 - "Community 3"
Cohesion: 0.67
Nodes (3): GITHUB_PERSONAL_ACCESS_TOKEN, @modelcontextprotocol/server-github, github

### Community 4 - "Community 4"
Cohesion: 0.67
Nodes (3): MONGODB_CONNECTION_STRING, mongodb-mcp-server, mongodb

### Community 5 - "Community 5"
Cohesion: 0.67
Nodes (3): FILESYSTEM_ROOT, @modelcontextprotocol/server-filesystem, filesystem

### Community 6 - "Community 6"
Cohesion: 0.67
Nodes (3): npx, @modelcontextprotocol/server-memory, memory

### Community 7 - "Community 7"
Cohesion: 0.67
Nodes (3): BRAVE_API_KEY, @modelcontextprotocol/server-brave-search, brave-search

### Community 8 - "Community 8"
Cohesion: 0.67
Nodes (3): GOOGLE_MAPS_API_KEY, @modelcontextprotocol/server-google-maps, google-maps

## Knowledge Gaps
- **30 isolated node(s):** `@modelcontextprotocol/server-filesystem`, `FILESYSTEM_ROOT`, `@modelcontextprotocol/server-github`, `GITHUB_PERSONAL_ACCESS_TOKEN`, `@modelcontextprotocol/server-postgres` (+25 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `npx` connect `Community 6` to `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 7`, `Community 8`, `Community 10`, `Community 11`, `Community 12`, `Community 13`, `Community 14`?**
  _High betweenness centrality (0.151) - this node is a cross-community bridge._
- **Why does `slack` connect `Community 2` to `Community 1`, `Community 6`?**
  _High betweenness centrality (0.103) - this node is a cross-community bridge._
- **Why does `uvx` connect `Community 0` to `Community 1`, `Community 9`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **What connects `@modelcontextprotocol/server-filesystem`, `FILESYSTEM_ROOT`, `@modelcontextprotocol/server-github` to the rest of the system?**
  _30 weakly-connected nodes found - possible documentation gaps or missing edges._