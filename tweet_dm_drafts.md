# X + DM drafts

## Context

- MCP PR #1034 — **MERGED** by @safishamsii with 🚀
- Founder: @safishamsii
- Project: @graphifyy
- Worked examples: `worked/terraform-infra/`, `worked/mcp-pipeline/`

## Order of operations

1. Reply to Safi's "solid" with closed PR screenshot (done)
2. Quote-tweet his hiring post with graph.png
3. DM him
4. **Terraform extractor story thread** (1-2 weeks later)
5. Blog post (optional)

---

## Post 1: MCP PR — quote-tweet of Safi's hiring post

Graphify speaks MCP via serve.py. Now it also *ingests* MCP configs as graph data.

PR #1034 treats .mcp.json / claude_desktop_config.json as first-class graph nodes — extracting servers, commands, packages, and env vars into a queryable knowledge graph.

Pictured: 24 MCP servers parsed from a single config file. npx and uvx at the center as dependency hubs, server+env clusters branching out. 59 nodes, 82 edges, 100% from AST — no LLM.

github.com/safishamsi/graphify/pull/1034

P.S. more on the way

*(Attach: graph.png)*

---

## Post 2: Terraform extractor story — X thread (1-2 weeks later)

### Tweet 1

> Wanted to add HCL/Terraform support to @graphifyy. Spent a weekend building extract_terraform() using tree-sitter-hcl — variable blocks, resources, outputs, module calls, cross-file references. Got it working on my 8-module production AWS infra (54 files, 608 nodes, 733 edges).

### Tweet 2

> What I didn't know: there was already a PR open (#416) by @mauricewittek — 2055 LOC, 3 thumbs-up, mergeable, with diagnostics, secret scrubbing, resource limits, everything. I'd spent my weekend building something someone else had already done better.

### Tweet 3

> Best thing I did: I stopped, read the PR carefully, and pivoted. Instead of shipping a worse version of #416, I found an actual gap — general resource.x.y cross-file refs that #416 doesn't resolve (it handles module_input/output only). Flagged it on the PR, noted it for a follow-up.

### Tweet 4

> Lesson: open-source contribution isn't about being first. It's about reading what's already there, finding where you actually add value, and being honest about when someone else's work is better. The MCP config extractor (#1034) is what I built after the pivot.

---

## DM to @safishamsii

Hi Safi — opened #1034: MCP config extractor for graphify. Graphify already speaks MCP via serve.py; this adds the inverse direction. 29 tests, ~400 LOC, deterministic, security-conscious (env values never read, args not persisted).

X post: [link]

Would love to chat if you're hiring — DMs open.

---

## Screenshot tip

Take a full-page screenshot of `graph.html` — the interactive force-directed graph. Crop to show the cluster layout clearly (npx/uvx hubs in center, server+env clusters around them). Dark mode in the browser looks more polished.

Don't include env var values in the frame (even blurred — crop them out). The 3-column community cluster structure + god nodes at center is the most visually impressive frame.
