# Graphify Evaluation — opencode (2026-04-16)

**Evaluator:** Human-assisted review using actual graphify run output  
**Corpus:** `packages/opencode/src/` — 406 TypeScript/TSX/JavaScript files, ~88,600 words  
**Pipeline:** `graphify update packages/opencode/src` (AST-only, no LLM, no semantic extraction)  
**Graphify version:** 0.4.14  
**Method:** Real run. All findings verified against actual `graph.json` and `GRAPH_REPORT.md`.

---

## Summary

- **1,772 nodes · 2,958 edges · 213 communities**
- 66% EXTRACTED · 34% INFERRED · 0% AMBIGUOUS (INFERRED avg confidence: 0.8)
- Token reduction: **12.6x** (88,600-word corpus, ~9,349 tokens/query average)
- Token cost: 0 (AST-only run)

---

## Token Reduction Benchmark

| Metric                             | Value         |
| ---------------------------------- | ------------- |
| Corpus tokens (naive full-context) | ~118,133      |
| Average query cost (BFS subgraph)  | ~9,349 tokens |
| **Reduction ratio**                | **12.6x**     |

Per-question breakdown:

| Reduction | Question                                |
| --------- | --------------------------------------- |
| 33.1x     | what are the core abstractions          |
| 33.1x     | how are errors handled                  |
| 16.7x     | what connects the data layer to the api |
| 9.7x      | what is the main entry point            |
| 5.8x      | how does authentication work            |

**Context:** The karpathy-repos example achieves 71.5x on a 52-file mixed corpus (code + papers + images). This corpus is code-only and 8x larger (406 files). The 12.6x number is honest: BFS query cost scales with graph density, not corpus size, but a denser code-only graph means broader traversals. Still meaningfully cheaper than full-context.

---

## Graph Quality Evaluation

### 1. God Nodes — Score: 2/10

The 10 god nodes are:

1. `push()` — 72 edges
2. `get()` — 65 edges
3. `set()` — 41 edges
4. `info()` — 39 edges
5. `trim()` — 38 edges
6. `has()` — 33 edges
7. `toString()` — 29 edges
8. `replace()` — 26 edges
9. `stream()` — 26 edges
10. `resolve()` — 24 edges

**These are all generic method names, not architectural concepts.** Every TypeScript codebase has `push()`, `get()`, `set()`. The extractor merges all functions named `push` across every file into the same node. With 406 files, any common method name accumulates edges from everywhere and rises to the top.

The actual architectural core of opencode — `Session`, `Agent`, `Tool`, `Provider`, `Message` — do not appear in the god nodes list at all. A developer new to this codebase would learn nothing from these results.

**Root cause:** The tree-sitter extractor uses `_make_id(stem, func_name)` scoped to file stem. But when many files define a function with the same short name, the graph query (`query_graph`) merges them by label match, not by ID. The `god_nodes` analysis uses degree centrality on the graph, which should use IDs, not labels — but if short generic names appear as nodes from many files, they naturally accumulate edges.

**Verified:** Running `graphify query "session agent" --budget 800` returns TUI route components (`session/index.tsx`) rather than the core `session/` module (`src/session/`). The graph finds the wrong "session."

---

### 2. Community Quality — Score: 4/10

213 communities detected. Of these:

- **38 communities** have 2+ nodes (real clusters)
- **175 communities** are single-file isolates (Communities 38–212)

The 175 isolate problem is severe. Every file in `src/tool/`, `src/cli/cmd/`, `src/storage/`, `src/share/` becomes its own community because the AST extractor doesn't resolve cross-file imports in TypeScript. A `tool/bash.ts` file imports from `../util/filesystem` — the extractor creates an import edge, but if the target file's node ID doesn't match (due to path resolution), the edge is dropped and the file becomes isolated.

**What the real communities are** (verified by reading the actual opencode source):

| graphify community      | What it actually contains                                          | Correct label                       |
| ----------------------- | ------------------------------------------------------------------ | ----------------------------------- |
| Community 0 (71 nodes)  | `Agent`, `buildAvailableModels`, `defaultModel`, `getContextLimit` | Provider + Model configuration      |
| Community 1 (54 nodes)  | `Api`, `AuthError`, `connect`, `create`                            | HTTP client / API layer             |
| Community 2 (68 nodes)  | `patchJsonc`, `pluginOptions`, `resolvePluginSpec`, `errorData`    | Plugin system + config parsing      |
| Community 5 (37 nodes)  | `abortAfter`, `callback`, `close`, `migrations`, `transaction`     | Effect-ts runtime + DB transactions |
| Community 8 (39 nodes)  | `buildAuthorizeUrl`, `generatePKCE`, `exchangeCodeForTokens`       | OAuth / auth flow                   |
| Community 10 (40 nodes) | `argPath`, `cmd`, `collect`, `cygpath`, `dynamic`                  | CLI commands                        |

Communities 0–37 do make structural sense when cross-referenced with the source. The names are generic ("Community 0") but the node lists correctly cluster related code.

**The 175 isolates:** Every file that only exports one thing and imports are unresolved lands as a single-node community. This is correct behavior given the constraints of AST-only extraction without TypeScript module resolution, but it makes the report noisy and the community navigation useless for ~80% of communities.

---

### 3. Surprising Connections — Score: 3/10

Five connections reported:

1. `retryable()` --calls--> `iife()` [INFERRED] (`session/retry.ts` → `util/iife.ts`)
2. `buildAuthorizeUrl()` --calls--> `toString()` [INFERRED] (`plugin/codex.ts` → `util/keybind.ts`)
3. `isHostSlotPlugin()` --calls--> `isRecord()` [INFERRED] (`cli/.../slots.tsx` → `util/record.ts`)
4. `killTree()` --calls--> `sleep()` [INFERRED] (`shell/shell.ts` → `util/flock.ts`)
5. `collect()` --calls--> `isDir()` [INFERRED] (`tool/bash.ts` → `util/filesystem.ts`)

**All five are INFERRED with no way to verify.** The AST-only pipeline did not do semantic extraction — so where did these INFERRED edges come from? They appear to be residual INFERRED edges from a previous graphify run's semantic pass, loaded from cache. This is misleading: running `graphify update` (code-only) should produce only EXTRACTED edges from the AST, but 34% of edges (996) are INFERRED.

**Verified edge #4:** `killTree()` in `shell.ts` — checking the actual source, `killTree` calls `shell.kill()` which eventually calls a process kill, but it doesn't call `sleep()`. The edge is a false INFERRED connection.

**Verified edge #5:** `collect()` in `tool/bash.ts` does call `isDir()` via `filesystem.ts`. This one is **correct** — but it's not surprising. The bash tool checking if a path is a directory before deciding how to collect it is an obvious implementation detail.

**The genuinely interesting connection** (not in the list): The opencode codebase has `session/subtask-handler.ts` which spawns child agent sessions. This creates a recursive session → session dependency that would be architecturally significant. The graph does not surface this.

---

### 4. Node/Edge Quality — Score: 5/10

**What's captured well:**

- All exported functions and classes across 406 files
- File-level nodes with correct source paths and line numbers
- `contains` edges from file nodes to their symbols
- Import edges where TypeScript module paths can be resolved as relative paths

**What's wrong:**

**Cross-file resolution fails silently for index.ts re-exports.** opencode heavily uses `index.ts` barrel files. When `session/index.ts` re-exports from `session/prompt.ts`, the import edge from a consumer points to `session` (the module), not the specific file. These edges are dropped. Result: `src/session/` appears as isolated files rather than a cohesive module.

**Generic function names merge across files.** Functions named `create`, `get`, `set`, `parse` exist in dozens of files. The graph's node label match treats them as the same node, inflating their degree and making them appear as god nodes. This is a fundamental issue for TypeScript codebases that use functional patterns with short, common names.

**Effect-ts service constructors not recognized.** opencode uses Effect-ts patterns extensively — `Layer.effect(...)`, `Effect.gen(...)`, `Service.Tag`. These don't map to standard class/function AST patterns, so the architectural boundaries they define (service boundaries, dependency injection) are invisible to the graph.

**INFERRED edge confidence is uniformly 0.8.** All 996 INFERRED edges have `avg confidence: 0.8`. This suggests they were generated with a default rather than per-edge reasoning. Confidence should vary.

---

### 5. Overall Usefulness — Score: 4/10

**Would this graph help a developer understand the opencode codebase?**

**Yes, for:**

- Quickly locating the auth flow (Community 8 is clearly the OAuth module)
- Finding that plugin resolution and config parsing are in the same cluster (Community 2)
- Confirming that Effect-ts runtime utilities (abort, transaction) cluster together (Community 5)
- Token savings on targeted queries — 12.6x cheaper than pasting all 406 files

**No, for:**

- Understanding the core architecture (Session → Agent → Tool → Provider chain invisible)
- Finding the main entry points (generic method names dominate god nodes)
- Understanding the TUI component tree (175 isolated single-file communities)
- Cross-module flows (session spawning subtasks, tool results feeding back to provider)

**The 12.6x reduction is real and useful.** Even with quality issues, targeted BFS queries on this graph are significantly cheaper than full-context reads. For a developer asking "where is the auth code?", the graph correctly points to Community 8 (`generatePKCE`, `buildAuthorizeUrl`, `exchangeCodeForTokens`).

---

## Specific Bugs Found

### Bug 1: Generic method names pollute god nodes (HIGH)

**Impact:** God nodes list is completely useless for TypeScript codebases using functional patterns.  
**Root cause:** Node label matching treats all `push()` functions as interchangeable. Degree is computed by label match, not by scoped node ID.  
**Repro:** Any large TypeScript codebase with common short function names.  
**Fix suggestion:** Score god nodes by scoped ID, not label. Or filter out functions whose label is a JavaScript built-in method name.

### Bug 2: INFERRED edges appear in AST-only update run (MEDIUM)

**Impact:** Surprising connections shows INFERRED edges with no way to verify — they may be cached from a prior LLM run or incorrectly generated.  
**Repro:** Run `graphify update <path>` on a fresh directory. Check that 0% INFERRED edges appear in output.  
**Expected:** `graphify update` should produce 100% EXTRACTED edges (AST only).  
**Actual:** 34% INFERRED (996 edges), avg confidence 0.8.

### Bug 3: TypeScript barrel file re-exports unresolved (MEDIUM)

**Impact:** Modules using `index.ts` re-exports (common in TypeScript monorepos) appear as isolated files.  
**Repro:** Any TypeScript project with `src/module/index.ts` that re-exports from sibling files.  
**Fix suggestion:** When resolving `import { X } from './session'`, check if `session/index.ts` exists and follow its re-exports.

### Bug 4: `path.shortest` returns "No path" for clearly connected nodes (LOW)

**Repro:** `graphify path "session" "tool"` returns "No path found."  
**Expected:** A path exists: `session/llm.ts` calls tools via `session/prompt.ts` → `tool/*.ts`.  
**Root cause:** Path search uses label match. "session" matches the TUI route file, not the session module. "tool" matches no node by that name.

---

## Scores Summary

| Dimension              | Score | Key Finding                                                        |
| ---------------------- | ----- | ------------------------------------------------------------------ |
| God nodes              | 2/10  | All generic method names — useless for TypeScript                  |
| Community quality      | 4/10  | 175/213 single-file isolates; 38 real clusters are reasonable      |
| Surprising connections | 3/10  | All INFERRED, at least 1 verified false, 0 genuinely surprising    |
| Node/edge quality      | 5/10  | Good structure coverage; generic name merging is a major flaw      |
| Token reduction        | 8/10  | 12.6x real, honest benchmark on 406-file production codebase       |
| Overall usefulness     | 4/10  | Useful for targeted queries; misleading for architectural overview |

**Overall: 4.3/10**

The graph works as a search index (find auth code, find plugin code) but fails as an architectural map. The core problem is that TypeScript functional patterns with short method names break the god nodes feature entirely. This is worth fixing upstream.
