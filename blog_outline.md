# Blog post outlines

Two posts, intentionally. Don't bundle.

## Post A — primary, ship first

**Title options (pick one):**
- *"Graphify already speaks MCP. Here's how to make it listen."*
- *"MCP-as-corpus: indexing your AI assistant's tool layer"*
- *"What's in your `.mcp.json`? Indexing it with Graphify."*

**Target length:** 1000–1400 words. Read time: 5–7 min.

**Where to host:** dev.to or hashnode (technical audience, low overhead) > Medium (broader reach, paywall risk) > your own site (best long-term but slow to build).

**Structure:**

1. **Hook (1 short para).** Every Claude Code / Cursor / OpenCode user with an `.mcp.json` has an invisible second layer in their project — the configured tool surface. Graphify already exposes itself AS an MCP server but doesn't index the inverse. Here's the missing piece.

2. **The asymmetry (1 para + small diagram if you want one).** Show `graphify/serve.py` is an MCP server. Show that the corpus side has loaders for SQL, bash, JSON, audio, video, docx, gdocs — but not MCP config. Frame as "loop not yet closed."

3. **What the extractor does (~3 short paras).** Schema bullets. Mention deterministic, no LLM, no tree-sitter (it's already JSON), env values never read, args not persisted. Keep brief — link to the PR for full schema.

4. **What it surfaces (the killer demo).** Two concrete queries that the graph now answers:
   - *"What env vars does my agent setup require?"* — show the env_var community in the graph
   - *"Which of my MCP servers depend on the same command/package?"* — show the global-node collapse
   Include the sample-output block from the PR body (4-server fixture, 13 nodes, 14 edges).

5. **The aside: how I got here (optional, 1 para).** Briefly: was building MCP-tool-dep graphs as a side project (`mcp-tool-deps`), saw Graphify, realized this was the bridge. Honest origin story, builds credibility.

6. **The Terraform detour (optional, 1 short para + link).** *"While at this I also did an HCL extractor experiment on real production Terraform — 8 modules, 608 nodes, 733 edges. Found a small gap in PR #416 worth a follow-up. Worked example here: [link to worked-terraform-infra/GRAPH_REPORT.md]."* This is where you sneak in the Terraform work without it being the headline.

7. **Roadmap (1 para).** What's intentionally out of scope: tool-level edges (would need running `tools/list` on each server, not deterministic), sidecar `tools.json` ingestion, MCP registry support. All easy follow-ups.

8. **Close.** Link to PR, link to repo, your handle. One sentence: "Currently looking for roles — DMs open."

**Visuals you can use right now:**
- The PR-body sample-output text block (formatted as a code block) — works as a screenshot too
- `tests/fixtures/sample.mcp.json` — show the source the demo came from
- The 13-node demo output you generated this morning
- If you have a real `.mcp.json` on your machine (sanitized), running graphify on it would produce a richer graph for the screenshot

**Cross-post checklist:**
- Substack, dev.to, or hashnode as primary
- Cross-post to LinkedIn (devs there respond to graph/visualisation content well)
- Submit to Hacker News under "Show HN" — only if the PR has merged or has visible Safi engagement
- Tweet thread links to the post (or vice versa)

---

## Post B — supplementary, ship after Post A

**Title options:**
- *"Graphifying my Terraform: 608 nodes, 8 modules, and one resolver gap"*
- *"What a knowledge graph of my AWS infra actually showed me"*

**Target length:** 800–1000 words.

**Why this post exists:** It's the concrete "graphify on real infra" case study that complements the conceptual MCP post. Doubles as the worked-example writeup.

**Structure:**

1. **Hook.** "I ran a knowledge-graph extractor over my entire AWS Terraform — 8 modules, 54 files. Here's what it surfaced." One sentence on what Graphify is, link to the project.

2. **The setup.** Brief: the corpus is the `aws-terraform-multi-env-template` repo. ECS + RDS + ALB + S3 + VPC + Route53 + monitoring. Multi-env. Real, not toy.

3. **The numbers.** 608 nodes, 733 edges, 168 cross-file references, 8 communities. Embed the stats table from `GRAPH_REPORT.md`.

4. **What the graph showed.** Three concrete findings:
   - **God nodes.** `variable_domain_name` had 10 references — shared across half the modules. Renaming or moving it would touch the whole infra.
   - **Module boundaries via `outputs.tf`.** 58 of the 168 cross-file refs originated from output declarations. The graph made the "outputs are interface" pattern visible structurally.
   - **VPC-as-foundation.** `aws_vpc.main` had 9 references. Everything depends on it. Obvious in retrospect, instantly visible from the graph.

5. **What didn't work.** Honest section. Stem-independent nids would collide for multi-module repos with same-named resources. No diagnostics for unresolved refs. No secret scrubbing. The current branch is a prototype, not production-ready.

6. **The community PR that does it better.** Link to #416. Frame as positive: someone else built the production-grade version, your work surfaced a narrow gap (general resource cross-file refs), which you'll PR as a follow-up.

7. **Bridge to Post A.** "While doing this I noticed Graphify itself had an indexing gap on a different corpus — MCP configs. Built that too: [link to PR + Post A]."

8. **Close.** Same as Post A — PR link, repo, handle, looking for roles.

**Visuals:**
- The `GRAPH_REPORT.md` rendered on GitHub
- If you can export `graph.json` to an interactive vis (pyvis), embed a screenshot
- The stats table

---

## Post sequencing

| Day | Action |
|---|---|
| 0 (today) | Comment on PR #416. Open MCP PR (done). Post the X thread (drafted). DM Safi (drafted). |
| +1 | Watch for engagement. If Safi or Maurice reply, respond promptly. If not, no follow-up DM. |
| +2 to +5 | Draft Post A. ~3 hours of focused writing. |
| +6 | Publish Post A. Tweet about it (separate from the day-0 thread). Cross-post to LinkedIn. |
| +7 to +10 | Draft Post B. Lower priority. |
| +11 | Publish Post B as a "if you liked the MCP one, here's the Terraform one" follow-up. |

Don't blast both posts at once. Sequencing makes you look like a person who ships consistently, not someone who dumped two posts before applying.

---

## What to put on your application / portfolio

Use this exact ordering (most important first):

1. PR [safishamsi/graphify#1034](https://github.com/safishamsi/graphify/pull/1034) — MCP config extractor for Graphify (YC S26).
2. Post A (when published) — link.
3. Post B (when published) — link.
4. PR #416 comment on follow-up gap — link.
5. Personal Graphify fork — `github.com/adityachaudhary99/graphify`.
6. Worked example — `worked-terraform-infra/GRAPH_REPORT.md` on fork.

That ordering puts the merged-or-mergeable contribution at the top and supports it with the writing.
