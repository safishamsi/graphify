## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)

## Remote and Rebase Policy

Rules:
- `origin` is the active development target unless the user explicitly says otherwise.
- `upstream` is read-only/reference by default. Do not open, update, or describe work as ready for upstream contribution unless the user explicitly reopens that path.
- Still follow upstream Graphify closely: before planning implementation slices or rebases, fetch `origin` and `upstream`, verify current branch/HEAD/ahead-behind state, and compare live upstream changes that touch the same files.
- Prefer rebasing/pulling useful upstream changes into the local/origin development branch when doing so preserves the Graphify direction and reduces future drift.
- Upstream synchronization is preauthorized only for this Graphify/vampyre checkout (`/Users/jonathandirks/Development/vampyre`). Do not generalize this permission to any other repo or project. In this checkout, do not ask for human approval before stashing local work, fetching `origin`/`upstream`, comparing upstream changes, rebasing onto useful upstream updates, resolving conflicts by comparison, reapplying the stash, and rerunning verification.
- If upstream changes are harmful, irrelevant, or incompatible with the local Graphify direction, skip them only after comparing the change and recording the reason in the handoff.
- Helper scripts for stash/fetch/rebase workflows may be created only in local-only paths that are excluded from git, such as `.agent-local/`; do not add those helper scripts to GitHub-bound history.
- Absolute conflict rule: never resolve merge, rebase, cherry-pick, or generated-artifact conflicts by blindly choosing ours/theirs or by assuming the local branch is always correct. Always inspect and compare both sides, identify the intended behavior on each side, preserve useful upstream behavior unless it is deliberately incompatible with the local plan, and document the resolution in the handoff or commit notes.
- If conflict behavior is unclear after comparing both sides and the relevant tests/docs, stop and ask before resolving.
- For this checkout only, publishing a verified local/origin development branch is part of closing an upstream sync. Before pushing, run the full local verification stack, including local Copilot review, tests, lint/type/security/warning gates, pre-commit/pre-push gates, and graph refresh when applicable.
- After verification passes, fetch `origin` and compare. If local `HEAD` contains `origin` or deliberately supersedes it because origin-only commits are already integrated, duplicated by rebase, or intentionally rejected with the reason recorded, update `origin` with a normal push for fast-forwards or `--force-with-lease` for rewritten history.
- Do not leave `origin` behind a verified local stack merely because the local branch was rebased. If the lease fails, or if origin contains new valuable or unclear work that is not in local, stop, fetch, compare, and integrate or ask before publishing.
- This does not authorize publishing to `upstream`, changing remotes, or generalizing the Graphify/vampyre publication rule to any other repo.

## Verification and Failure Policy

Rules:
- Do not waive test failures, skips, warnings, linter findings, gate failures, graphify update failures, or audit findings as "pre-existing." If an issue is reproducible in the current workspace, it becomes the current agent's active task until resolved or until the user explicitly redirects the work.
- Do not mark a slice, PR, branch, or handoff as ready while any reproduced failure, skip, warning, or gate finding remains unresolved.
- If another agent reports an issue as pre-existing, independently reproduce it, root-cause it, fix it when it is in scope, and record the invalid waiver in the handoff or audit notes.
