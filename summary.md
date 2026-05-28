# Graphify Contributions — Summary

*Last updated: 2026-05-26*

## Fork

| Detail | Value |
|--------|-------|
| URL | `github.com/adityachaudhary99/graphify` |
| Upstream | `github.com/safishamsi/graphify` (default branch `v8`) |
| Remote name (local) | `fork` |
| Base | `3efae38` (origin/v8 at time of branching) |

> **Profile visibility**: Commits on non-default branches don't show on your GitHub contribution graph. They appear after merging into upstream `v8` via PRs.

## Branches on fork

Kept all branches as portfolio artefact — the dead branches tell the "tried Terraform, read #416, pivoted to MCP" arc. Don't waste cycles updating the deprecated ones; reference only.

### Relevant — active work

| Branch | Ahead of v8 | Purpose | What to do with it |
|---|---|---|---|
| `mcp-ingest` | 1 commit (`eea5778`) | MCP server config extractor — `graphify/mcp_ingest.py` + tests + fixture | **PR #1034 open against upstream.** Push updates here if reviewers request changes. |
| `worked-terraform-infra` | 3 commits (top: `7de21af`) | Real production AWS Terraform corpus + extracted graph (608 nodes / 733 edges) | Linked from PR #416 comment, DM, blog post. Reference only — no further commits expected. |

### Deprecated — kept as portfolio / learning artefact

Treat these as read-only history. **Do not patch, do not open PRs from them, do not push more commits.** They exist to show due diligence (the path you walked before landing on the MCP contribution).

| Branch | Ahead of v8 | Why kept | Why deprecated |
|---|---|---|---|
| `extract-terraform` | 1 commit (`51d5e85`) | Documents the initial HCL extractor attempt | Superseded by upstream PR #416 by Maurice Wittek (+2055 LOC, far more complete: diagnostics, secret scrubbing, resource limits, `.tfvars`, provider blocks, confidence scoring). Same fate as closed PR #841 if opened. |
| `cross-file-refs` | 2 commits (top: `3a629ea`) | Documents the cross-file ref attempt + `_walk_expr` recursion fix | Built on stem-independent globals; #416 uses per-file nids (`hcl_file:<path>::<kind>:<identity>`). Wrong foundation. Future follow-up must be a rewrite, not a patch. |

### Already deleted

| Branch | Reason |
|---|---|
| ~~`extract-bash`~~ (local + fork) | Obsoleted by upstream v8 release #866 |
| ~~`v7`~~ (local) | Replaced by rebasing onto v8 |
| ~~`v8-base`~~ (local) | Unused 0-commit reference; equivalent to `fork/v8` |

### Fork mirror branches (not your work)

`fork/v1` through `fork/v7`, `fork/main` — historical upstream mirrors inherited at fork time. Cosmetic clutter in the GitHub branch dropdown; do not delete (upstream still has them live).

## Changes per branch

### `mcp-ingest` (+755, 4 files) → upstream PR #1034

`graphify/mcp_ingest.py` (392 LOC): extracts `.mcp.json` / `claude_desktop_config.json` / `mcp.json` / `mcp_servers.json` into graph nodes (`mcp_server`, `mcp_command`, `mcp_package`, `env_var`) and edges (`contains`, `references`, `requires_env`).

- Cross-config emergent edges via globally-scoped command / package / env var IDs.
- Filename-routed in `_get_extractor` before generic `.json` dispatch.
- 29 tests, all passing locally. 331 LOC tests + 26 LOC fixture.
- Security: env var values never read/persisted, args not persisted, 1 MiB cap, all labels through `sanitize_label`.

### `extract-terraform` (+316/−2, 5 files) — deprecated

`extract_terraform()` via `tree-sitter-hcl`. Resources, data sources, variables, outputs, modules, locals, terraform blocks with attribute-level granularity. 9 single-file tests. **Superseded by #416.**

### `cross-file-refs` (+67/−14, 1 file) — deprecated

Bug fix for `_walk_expr` recursion + stem-independent block nids + `_resolve_cross_file_tf_refs()` orchestration pass. **Wrong foundation vs #416's per-file nid scheme.** The genuine value (cross-file `resource.x.y` resolution) is a real gap in #416 but the correct follow-up is a rewrite against #416's primitives once it merges, not a patch on this branch.

### `worked-terraform-infra` (+15,819/−1,313, 71 files) — fork-only asset

Real production AWS Terraform from `github.com/adityachaudhary99/aws-terraform-multi-env-template`. 8 modules, 54 `.tf` files, multi-env, CI/CD. Extracted graph: 608 nodes / 733 edges / 168 cross-file refs / 8 communities. `review.md` toned down (commit `7de21af`) to remove production-readiness overclaims.

## Tests

| Group | Count | Status |
|---|---|---|
| MCP ingest (`tests/test_mcp_ingest.py`) | 29 | ✅ all passing |
| Terraform extractor (`tests/test_languages.py` additions on deprecated branches) | 9 | ✅ passing (but obsoleted by #416) |
| Broader suite (`tests/test_extract.py`, `test_detect.py`, `test_languages.py`) | 314 of 322 | ✅ — 8 failures are pre-existing Windows symlink-permission issues unrelated to either contribution |

## PRs

| # | Upstream | Title | Status |
|---|---|---|---|
| [1034](https://github.com/safishamsi/graphify/pull/1034) | `safishamsi/graphify` | `feat: MCP config extractor (.mcp.json, claude_desktop_config.json)` | **OPEN, MERGEABLE** (opened 2026-05-26) |

## Verified findings

- **PR #416 (HCL/Terraform) has a real gap.** Pulled the full diff and verified: `resolve_hcl_cross_file` only handles `module_input` / `module_output`. No `resource_index`; general `aws_vpc.main.id` cross-file refs are NOT resolved. Follow-up window for an HCL contribution exists, but must be written against #416's primitives once it merges.
- **PR #841 (closed)** confirmed the dynamic: a 326-LOC competing PR was closed by its own author in deference to #416. Same fate would apply to opening `extract-terraform` as-is.

## Today's plan

1. ✅ Open MCP PR — **DONE** ([#1034](https://github.com/safishamsi/graphify/pull/1034))
2. ✅ Tone down `worked-terraform-infra/review.md` — **DONE** (`7de21af`)
3. ✅ Verify #416's cross-file scope — **DONE** (gap confirmed)
4. ⏳ Comment on PR #416 with the resource cross-file gap observation + intent to follow up (draft in `tweet_dm_drafts.md`)
5. ⏳ Publish public X post + DM Safi (drafts in `tweet_dm_drafts.md`)
6. ⏳ Optional: blog post on the worked example (outline in `blog_outline.md`)

## Watch points

- **PR #1034 review feedback.** Likely topics: relation naming (`requires_env`), per-file vs global node scope, whether `args` should be partially indexed (and how to handle path/secret leakage if so), where to surface diagnostics for malformed inputs.
- **PR #416 merge.** When it lands, prepare the HCL cross-file follow-up:
  - Adopt #416's `hcl_file:<path>::<kind>:<identity>` nid scheme.
  - Add `resource_index: dict[dir, dict[(type, name), nid]]` mirroring `var_index` / `out_index`.
  - Resolve deferred resource refs against that index using #416's `hcl_make_edge` / `hcl_deferred_refs` plumbing.
  - ~150-200 LOC PR, narrow, easy review.
- **Before opening the follow-up:** glance at the deprecated `cross-file-refs` branch (`git show 3a629ea`). The `_walk_expr` recursion fix in there caught a real bug — references inside nested expressions like `coalesce(var.x, var.y)` were silently dropped. Check whether #416's walker has the same bug. If yes, the follow-up PR gets to land that fix too. If no, ignore.
