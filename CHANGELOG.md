# Changelog

Full release notes with details on each version: [GitHub Releases](https://github.com/safishamsi/graphify/releases)

## 0.8.24 (2026-05-29)

- Feat: type-reference edges for ObjC, Julia, C, C++, Scala, Fortran, and PowerShell — extends cross-language semantic context work from #1015 to a second wave of languages; CI matrix now covers Python 3.10 with `faster-whisper` version guard (#1071)
- Fix: claude-cli backend no longer loops on hollow streamed responses — handles all four documented failure modes (empty stream, no JSON, missing `result`, empty `result`) with tests (#1063)
- Fix: `calls` edges no longer flip caller/callee when the same node pair appears in both directions in an undirected build — first-seen direction preserved on bidirectional collision (#1061)
- Fix: `graphify-out/.graphify_python` path prefix was missing in 8 skill files (256 instances) causing `cat: .graphify_python: No such file or directory` on every non-Claude-Code platform
- Chore: all skill files now use uv-aware interpreter detection — `uv tool run graphifyy python` preferred over shebang parsing when uv is available

## 0.8.23 (2026-05-28)

- Feat: type-reference edges for Swift, Kotlin, PHP, Rust, and Go — `references` edges with `parameter_type`, `return_type`, `generic_arg`, `field`, and `attribute` contexts; inheritance split into `inherits` (superclass) vs `implements` (protocol/interface/trait) for all five languages (#1015)
- Chore: CI switched from pip to uv (`astral-sh/setup-uv`, `uv sync`, `uv run pytest`); `uv.lock` committed for reproducible installs; dev setup docs updated (#885)

## 0.8.22 (2026-05-28)

- Feat: BYOND DreamMaker support — `.dm`/`.dme` files extracted via tree-sitter-dm (type definitions, proc declarations, `#include` edges, in-file call resolution, `new /type()` instantiation edges); `.dmi` PNG icon files parsed for icon-state nodes; `.dmm` map files parsed for type-path `uses` edges from the tile dictionary section; `.dmf` interface files parsed for window/elem/control-type hierarchy (#884)
- Feat: `graphify extract --mode deep` flag enables richer semantic extraction using an extended system prompt; flag propagated through all four LLM backends (#1030)

## 0.8.21 (2026-05-27)

- Fix: `graphify update` (no `--changed` flag) no longer leaves ghost nodes from files deleted between runs — full re-extraction path now reconciles the existing graph against current disk state and evicts any node whose `source_file` no longer exists; `_norm_source_file` used on both sides to guarantee path format consistency (#1007)
- Fix: `graphify install --platform opencode --project` now writes `SKILL.md` to `.opencode/skills/graphify/SKILL.md` (discoverable by OpenCode) instead of the incorrect `.config/opencode/skills/` path; git-add hint updated accordingly (#1040)
- Fix: post-commit hook no longer triggers rebuild when only `graphify-out/` files were committed (avoids infinite dirty-tree loop when graph outputs are tracked in git); `GRAPHIFY_SKIP_HOOK=1` env var added for one-off skip; hook rebuild log now appends (`>>`) instead of overwriting (`>`) (#1018, #1037)
- Fix: graph output is now byte-for-byte deterministic across runs — edges sorted by `(source, target, relation)` in `build_from_json`; `PYTHONHASHSEED=0` exported in hook scripts to stabilize Louvain community ordering (#1010)
- Feat: Amp (ampcode.com) platform support — `graphify amp install/uninstall` installs the skill into `.amp/skills/graphify/SKILL.md` (#948)
- Fix: query punctuation no longer breaks node matching — `"what calls extract?"` correctly finds the `extract` node; `_search_tokens` helper strips punctuation from search terms in `_query_terms`, `_score_nodes`, and `_find_node` (#994, #978)
- Fix: language built-in globals (`String`, `Number`, `Boolean`, `Object`, `Array`, etc.) no longer accumulate spurious call edges — filtered at same-file and cross-file resolution in the AST extractor, eliminating god-node pollution from constructor-style calls (#916, #726)
- Feat: SystemVerilog header files (`.svh`) now extracted using the Verilog parser alongside `.v` and `.sv` (#1042)
- Fix: `@property`, `@staticmethod`, `@classmethod` methods no longer produce orphaned nodes without a class-qualified ID — `decorated_definition` is now treated as a transparent wrapper in the Python AST walker, preserving `parent_class_nid` through the decorator layer (#1050)
- Fix: Pass 2 dedup no longer merges nodes with identical labels that live in different files — same-file partition enforced for the identical-label subcase so `foo()` in `a.py` and `foo()` in `b.py` are not collapsed into one node (#1046)
- Fix: `graphify-out/memory/` files are no longer silently excluded by `.gitignore` pattern matching — memory dir files now bypass the gitignore filter in `detect.py`, ensuring knowledge accumulated via `graphify remember` is always scanned (#1047)

## 0.8.20 (2026-05-26)

- Fix: stale nodes persist after `graphify update` when files are deleted on Windows — `deleted_paths` and `evict_sources` in `_rebuild_code` now use `.as_posix()` for consistent forward-slash paths; `_relativize_source_files` called on the existing graph before eviction (not after); `_relativize_source_files` itself now produces forward slashes (#1007)
- Fix: `graphify extract` stale-node pruning now also handles symlinked scan roots — `prune_set` expansion uses `Path(root).resolve()` before `relative_to()` so symlinked roots produce correct relative paths (#1007)
- Feat: MCP config extractor — `.mcp.json`, `mcp.json`, `mcp_servers.json`, `claude_desktop_config.json` now extracted into the knowledge graph; captures server nodes, npm/pip package refs, env var requirements; env values discarded to prevent secret leakage (#1034)
- Fix: `cluster-only` no longer drops community label alignment after re-clustering — `remap_communities_to_previous` now applied in the `cluster-only` path, matching the behaviour of `graphify update` (#1028)
- Fix: Dart child node IDs no longer embed absolute paths — switched from `_make_id(str(path), name)` to `_make_id(_file_stem(path), name)`, consistent with all other extractors; existing Dart graphs should be rebuilt with `--force` (#999)
- Security: XML parsing in `extract_csproj` and `extract_lazarus_package` now pre-screens for `<!DOCTYPE` / `<!ENTITY` declarations before calling `ET.fromstring`, blocking billion-laughs DoS on malicious project files; `extract_lpk` also gains the missing 2 MiB size cap

## 0.8.19 (2026-05-26)

- Feat: .NET project file support — `.sln`, `.csproj`, `.fsproj`, `.vbproj`, `.razor`, `.cshtml` now extracted; captures NuGet package refs, project-to-project dependencies, target frameworks, SDK attributes, Blazor/Razor directives (`@using`, `@inject`, `@inherits`, `@model`, `@page`), component refs, and `@code` block methods (#1025)
- Feat: Chinese query segmentation — compound Chinese tokens (e.g. `页面路由`) are split into meaningful words using jieba when installed, with character bigram fallback; original compound preserved alongside segments for exact-match; new `pip install "graphifyy[chinese]"` extra (#1026)
- Fix: Wiki TypeError when `source_file` is `None` — `G.nodes[n].get("source_file") or ""` replaces `.get("source_file", "")`, which did not handle explicit `None` values (#1016)
- Fix: Nested `.claude/worktrees/` no longer indexed — `_is_noise_dir` now accepts an optional `parent` param and skips `worktrees/` directories nested inside dotted dirs like `.claude/` (#1023)
- Fix: `backup_if_protected` no longer accumulates one folder per run — uses content-hash comparison to skip identical backups and overwrite in-place when content changes; one folder per day maximum
- Feat: Devin CLI support — `graphify devin install/uninstall` installs the skill into Devin's `.devin/rules/` directory (#1020)
- Fix: TypeScript 5.0 array-form `extends` in `tsconfig.json` now handled — `_read_tsconfig_aliases` normalizes `extends` to a list before iteration (#1017)

## 0.8.18 (2026-05-24)

- Fix: post-commit hook now updates graph after delete-only commits — shrink-guard is bypassed when `changed_paths` contains explicit deletions, preventing stale nodes from accumulating indefinitely (#1000)
- Fix: `graphify export` (html/obsidian/wiki/svg/graphml/neo4j) no longer collapses to "Single community" when `.graphify_analysis.json` is absent — falls back to per-node `community` attribute already present in `graph.json` (#1001)
- Fix: Ukrainian README translation updated to v8 — all new sections, correct badges, 31 languages (#995)
- Feat: semantic context tags on `references` edges for Python/JS/TS/C#/Java — `parameter_type`, `return_type`, `generic_arg`, `attribute`, `field`; C#/Java split `inherits`/`implements`; dedup key now includes context (#996)
  - **Breaking:** Java `extends` edges are now emitted as `inherits` — queries filtering on `relation="extends"` for Java nodes must be updated to `relation="inherits"`
- Feat: constrained query expansion in skill — Step 0 extracts actual graph vocab and forces LLM to pick expansion tokens only from that set, preventing hallucinated expansions; Unicode regex fix captures Cyrillic/CJK labels (#998)
- Docs: Ukrainian README updated to v8 with all new sections, correct badges, YC badge, 31 language count (#995)

## 0.8.17 (2026-05-23)

- Fix: Case-sensitive call resolution for Go, Rust, and Elixir — resolvers previously lowercased both the label index and the callee name, causing `Authorize` to match `authorize` and produce phantom edges; Ruby/C#/Java/Kotlin/Scala/PHP use the same generic resolver which now splits into case-sensitive (all languages) and case-insensitive (PHP only, where function/class names are genuinely case-insensitive) dicts (#993)
- Fix: Cross-language phantom `calls` edges from semantic extraction dropped at graph-build time — INFERRED `calls` edges whose source and target nodes belong to different language families (py/js/go/rs/jvm/c/cpp/rb/php/cs/swift/lua) are now discarded; skill.md prompt updated with an explicit anti-rule (#991)

## 0.8.16 (2026-05-22)

- Fix: CJK/Unicode labels no longer silently stripped during dedup — `_norm()` and `_norm_label()` now use Unicode-aware `[\W_]+` regex with `casefold()` and NFKC normalization; previously `道具処理クラス` and any non-ASCII label collapsed to empty string and got falsely merged (#937)
- Fix: `.ets` (ArkTS/HarmonyOS) files now recognized as code and extracted via the TypeScript parser (#926)
- Fix: `graphify` now exits non-zero when all semantic-extraction chunks fail — previously a silent empty graph was written with exit code 0, masking backend failures (#889)
- Feat: `graphify install --project` installs the skill into the current repository (`.claude/skills/`, `.agents/skills/`, etc.) instead of the user home directory; per-platform subcommands support the same flag (#931)
- Docs: Uzbek (uz-UZ) README translation (#982)

## 0.8.15 (2026-05-22)

- Fix: `cluster-only` subcommand crashed with `FileNotFoundError` when `graphify-out/` did not yet exist — output directory is now created before any write (#934)
- Fix: `GRAPHIFY_MAX_OUTPUT_TOKENS` env var now respected for all OpenAI-compatible backends — previously the token limit was hardcoded, causing truncated responses on high-context queries (#973)
- Fix: Swift extension nodes no longer duplicated across files — `_merge_swift_extensions` deduplicates by canonical name before graph insertion (#969)
- Fix: Non-Latin query terms (CJK, Arabic, Cyrillic, etc.) now preserved through query preprocessing — previous normalization stripped non-ASCII chars, making multi-lingual codebases unsearchable (#964)
- Feat: Multigraph runtime compatibility probe — emits a warning if a `MultiDiGraph` is passed where a `Graph` is expected by any downstream consumer (analyze, cluster, wiki, export, report) (#956)
- Feat: JS/TS barrel re-exports tracked as explicit `re_exports` graph edges — `export { X } from './mod'` emits typed edges with `context="re-export"` and `confidence=EXTRACTED`; file-level `imports_from` edges also emitted (#960)
- Feat: `--affected` and `--import-resolution` flags for the `v8` subcommand — impact analysis and cross-file import resolution exposed as first-class CLI options

## 0.8.14 (2026-05-20)

- Fix: `--wiki` crash when community node IDs are stale after dedup or re-extract — stale IDs are now silently dropped with a stderr warning; raises a clear error only if every ID is stale (#936)
- Fix: `.gitignore` patterns now respected when no `.graphifyignore` exists — previous behaviour silently ignored the project's gitignore, causing expected exclusions to be skipped (#945)
- Feat: `--exclude <pattern>` CLI flag to pass extra gitignore-style exclusion patterns at runtime without modifying `.graphifyignore` (#947)
- Fix: `.worktrees/` directory now skipped during scan — git worktree sibling checkouts inside `.worktrees/` were previously indexed as duplicate source (#947)
- Security: NAT64 IPv6 addresses (`64:ff9b::/96`) no longer false-positive as blocked reserved IPs — affects hosts like `arxiv.org` on IPv6-only networks where the ISP uses RFC 6052 NAT64

## 0.8.13 (2026-05-18)

- Fix: node ID collisions across same-named files in different directories — SQL extractor and Python import resolver now use directory-qualified stems (`dir_file_entity`) instead of bare filename stems, preventing silent node merging on repos with duplicate filenames (#1A, #1B)
- Perf: stat-based mtime fastpath for `file_hash` — skips full SHA256 read when file size+mtime_ns unchanged, same trade-off as make; index flushed atomically via atexit
- Fix: absolute `source_file` paths from semantic subagents no longer stored in graph — `build_from_json`, `build`, and `build_merge` accept a `root` param and relativize paths at build time (#932)
- Fix: failed semantic chunks no longer permanently freeze their files in the manifest — only files that appear in extraction output get `semantic_hash` stamped; failed-chunk files keep empty `semantic_hash` and are re-queued on next run (#933)
- Feat: `graphify cache-check`, `graphify merge-chunks`, `graphify merge-semantic` CLI subcommands expose cache and merge logic as library-callable commands for skill pipelines

## 0.8.12 (2026-05-18)

- Security: `_is_sensitive` now correctly flags underscore-prefixed secret filenames (`api_token.txt`, `oauth_token.json`) — `\b` word boundary was treating `_` as a word char, so names like `api_token` never matched (#920)
- Security: `_is_sensitive` now checks parent directories against a `_SENSITIVE_DIRS` blocklist (`.ssh`, `.aws`, `.gcloud`, `secrets`, etc.) so any file inside those dirs is skipped regardless of name; root-level files named `credentials` or `secrets` are no longer falsely flagged (#920)
- Fix: `--wiki` Relationships section was always empty — `_cross_community_links` read `community` from node attributes (always None) instead of the `communities` dict; `_god_node_article` had the same bug and never linked to the owning community (#925)
- Fix: `--watch` now respects `.graphifyignore` — the event handler was checking extensions before the ignore filter, so paths inside `node_modules/`, `.venv/`, etc. triggered rebuilds (#928)
- Fix: `graphify <path>` now correctly dispatches to `graphify extract <path>` — previously a bare path argument returned "unknown command" instead of starting extraction
- Fix: skill fast path — if `graphify-out/graph.json` already exists and the request is a natural-language question, extraction steps are skipped entirely and `graphify query` runs immediately; previously the skill re-ran detect and hit the corpus-size gate on every question
- Fix: large-corpus gate raised from 200 to 500 files; `detect()` now returns `scan_root` so the skill correctly computes relative subdirectory breakdowns instead of showing absolute paths; flat repos with no subdirectories no longer ask the user to pick a subfolder that doesn't exist
- Docs: clarify that code-only corpora skip the LLM semantic extraction pass entirely — AST handles code, Pass 3 is reserved for docs, papers, images, and transcripts (#836)

## 0.8.11 (2026-05-18)

- Fix: LLM empty choices / None message guard — Gemini and other providers return `choices=[]` on content-filtered HTTP 200 responses; now raises a clean error instead of crashing with IndexError (#924)
- Fix: OpenCode skill removed invalid `general-purpose` agent reference and headless-incompatible interactive halt (#911, closes #825)
- Fix: Codex skill now uses graphify query/explain/path even when graph artifacts are dirty in worktree (#913, closes #860)
- Perf: precompute degrees once in surprise scoring — ~11x speedup per lookup on large graphs (#914)

## 0.8.10 (2026-05-17)

- Fix: git hooks phantom directory on git < 2.31 — drop `--path-format=absolute`, validate path contains no newlines, anchor relative paths on repo root (#907)
- Fix: `save_manifest` incremental data loss — seed from existing manifest before loop so untouched files aren't erased on partial runs (#917)
- Fix: C++ class/struct inheritance edges missing — extract `base_class_clause` for `class_specifier` and `struct_specifier` (#915)
- Fix: cohesion split threshold unreachable due to rounding — `cohesion_score` now returns raw float, display rounds to 2dp (#919)
- Fix: Rust cross-crate spurious INFERRED edges — skip `Type::method()` scoped calls and common trait-method names from cross-file resolver (#908)
- Feat: `--resolution N` for `extract` and `cluster-only` — control Leiden/Louvain community granularity (>1 = more smaller, <1 = fewer larger) (#919)
- Feat: `--exclude-hubs P` for `extract` and `cluster-only` — exclude degree-percentile super-hubs from partitioning, reattach by majority-vote neighbour community (#919)

## 0.8.9 (2026-05-17)

- Feat: DeepSeek backend support — set `DEEPSEEK_API_KEY` and use `--backend deepseek`; default model `deepseek-v4-flash`

## 0.8.8 (2026-05-16)

- Feat: `graphify prs` — graph-aware PR dashboard: CI state, review decision, worktree mapping, and graph blast radius per PR; `--triage` ranks your queue via any configured LLM backend (claude, kimi, openai, gemini, claude-cli, ollama — auto-detected); `--conflicts` shows PRs sharing graph communities with node labels; `--worktrees` maps worktree paths to branches to open PRs; MCP tools `list_prs`, `get_pr_impact`, `triage_prs` for agent access

## 0.8.7 (2026-05-16)

- Fix: query seed selection now uses IDF weighting — common terms like `error` or `handle` that match dozens of nodes are down-weighted so a rare identifier like `FooBarService` ranks first and BFS expands from the right node (#897)
- Fix: seed count is now dynamic — a dominant match (score gap >80% vs next candidate) gets one seed rather than always picking three, preventing noise nodes from consuming BFS slots alongside the target (#897)
- Fix: truncation message in `query_graph` now tells Claude what to do (call `get_node` or add a `context_filter`) rather than just saying "truncated" (#897)
- Fix: C++ class data members (`int x;`, `static const int MAX = 100;`) now extracted as nodes with `defines` edges from the parent class — previously the field_declaration branch was a no-op due to a wrong child type guard (#898)
- Fix: dedup Pass 1 now partitions same-label groups by source_file before merging — nodes with generic labels (`handle`, `init`, `run`) from different files no longer collapse into artificial god nodes; cross-file matches are routed to Pass 2 fuzzy (#895)
- Fix: C/C++ `#include "path/to/file.h"` edges now resolve the include path relative to the including file and use the full resolved path as the target node ID, matching what extraction creates for the included file — previously all include edges dangled with a basename-only ID (#899)
- Fix: `exact_merges` counter in dedup now reports only merges actually performed rather than counting all same-label nodes across files (#895)

## 0.8.6 (2026-05-16)

- Fix: cross-language INFERRED `calls`/`uses` edges (e.g. Python → TypeScript) are suppressed in Surprising Connections — label-matching across language boundaries in monorepos is resolver pollution, not structural insight; all structural bonuses zeroed for these edges
- Fix: code-to-doc INFERRED `calls`/`uses` edges suppressed in Surprising Connections — the LLM seeing a symbol name in a README and emitting a `calls` edge is documentation cross-reference noise, not a real architectural connection (#890)
- Fix: generic JSON key nodes (`name`, `id`, `type`, `start`, `end`, `key`, `value`, `data`, `items`, `title`, `description`, `version`, `properties`) filtered from god_nodes — their degree is positional (every sibling record in the same JSON file references them), not architectural (#890)
- Fix: Alembic migrations, Django migrations, and protobuf-generated files now have their module-level docstrings suppressed from rationale extraction — these are boilerplate headers, not design intent; function docstrings inside migration files are still captured
- Feat: `--follow-symlinks` is now auto-detected — if symlinked children are present in the target directory, follow-symlinks is enabled automatically without requiring an explicit flag (#887)
- Fix: install guidance now directs users to run `/graphify query` interactively rather than reading `GRAPH_REPORT.md` first; the report is a summary, not a starting point (#891)

## 0.8.5 (2026-05-15)

- Fix: `.graphifyignore` parent-exclusion rule now correctly blocks files under an excluded directory even when a `!` negation exists elsewhere in the file — previously any negation pattern disabled directory pruning entirely (#882)
- Fix: dedup no longer false-merges chip/model SKU variants like `ASR1603`/`ASR1605` or `M1`/`M1 Pro` — Jaro-Winkler prefix bonus is now gated by `_is_variant_pair` and `_short_label_blocked` guards; real typos on short labels still merge (#878)
- Docs: added `worked/rsl-siege-manager/` — case study on a real-world Python + TypeScript monorepo (FastAPI backend, React/Vite frontend, Discord bot); covers god node behaviour with tests included, cross-language INFERRED edges, community cohesion, and Alembic migration noise (#881)

## 0.8.4 (2026-05-15)

- Feat: Firebird SQL — trigger and stored procedure extraction via `CREATE TRIGGER` and regex fallback; FK detection via global regex covering `REFERENCES` and `FOREIGN KEY` clauses (#875)
- Fix: SQL extraction regex fallback now decodes source as UTF-8 instead of latin-1, preventing non-ASCII identifier hash mismatches (#875)
- Fix: `--update` deletion pruning now matches on full source file paths instead of basenames, preventing false node removal when different directories contain files with the same name (#876)
- Fix: `--update` now also prunes edges whose `source_file` attr points to deleted files, not just nodes (#876)
- Fix: community label keys from `graph.json` (stored as strings) are now coerced to int before lookup, fixing blank community names in GRAPH_REPORT.md and graph.html (#877)

## 0.8.3 (2026-05-15)

- Fix: Windows skill temp files (chunk JSONs, `.graphify_python`, `.graphify_root`) no longer pollute the project root — all written under `graphify-out/` (#831)
- Fix: `--update` with deletions-only no longer errors when `.graphify_extract.json` does not yet exist — creates an empty extraction file before merging (#876)

## 0.8.2 (2026-05-15)

- Fix: Python interpreter detection for `uv tool` and `pipx` installs on Windows — `graphify install` and all skill steps now find the correct executable (#831)
- Fix: antigravity Windows skill path resolution (#831)
- Fix: dot directories (e.g. `.github/`, `.vscode/`) are now indexed when explicitly included via `.graphifyignore` (#873)
- Fix: MCP server hot-reloads the graph when `graph.json` changes on disk (#874)

## 0.8.1 (2026-05-15)

- Feat: Bash extractor — `.sh` and `.bash` files now indexed via tree-sitter; extracts functions, cross-function calls, `source`/`.` imports resolved to real file paths, and `export`/`declare` variable declarations (#866)
- Feat: JSON extractor — `.json` files now indexed via tree-sitter; extracts key/value `contains` tree, `dependencies`/`devDependencies` blocks as `imports` edges, `extends` edges (tsconfig, eslintrc), and `$ref` references (#866)
- Feat: `.sh`, `.bash`, `.json` added to `CODE_EXTENSIONS` in `detect.py` so files are picked up during corpus scan (#866)
- Feat: Mermaid callflow HTML auto-regenerates on every graph rebuild when `*-callflow.html` exists in `graphify-out/` — works with `--watch` and `graphify hook install`
- Fix: `coverage/`, `lcov-report/`, `visual-tests/`, `visual-test/`, `__snapshots__/`, `snapshots/`, `storybook-static/`, `dist-protected/` added to `_SKIP_DIRS` — generated artefact dirs no longer appear in the corpus (#869, #870)
- Fix: `graphify hook install` now works in git linked worktrees — uses `git rev-parse --git-path hooks` instead of constructing `.git/hooks/` directly (#865)
- Fix: office sidecar files in `graphify-out/converted/` are now checked against `.graphifyignore` before being added to the file list (#861)
- Fix: `save_manifest()` accepts a `kind` parameter (`ast`, `semantic`, `both`) — incremental AST-only `graphify update` no longer overwrites `semantic_hash` entries, preventing spurious full re-extracts on the next run (#857)
- Fix: five paths in `skill-windows.md` Step B3 were missing the `graphify-out/` prefix, causing chunk files to be written to the wrong directory (#862)

## 0.7.19 (2026-05-14)

- Feat: `.astro` files now extracted as code — frontmatter static imports, dynamic imports, and `<script>` block imports all produce edges; tsconfig path aliases resolved (#850, PR #852)
- Fix: `.rebuild.lock` no longer accumulates PIDs across rebuilds — now contains a single owning PID while running and is unlinked on release so downstream tooling polling for its absence unblocks promptly (#858, PR #859)
- Docs: skill.md now clarifies that graphify does not read `ANTHROPIC_API_KEY` or other provider keys during `/graphify` skill runs — the host IDE session provides the LLM (PR #864)

## 0.7.18 (2026-05-14)

- Fix: `graphify update` is now idempotent — graph.json and GRAPH_REPORT.md are only rewritten when content actually changes; topology comparison short-circuits clustering entirely on unchanged graphs, eliminating residual community-count drift (#824)
- Fix: community IDs are now stable across rebuilds — Leiden/Louvain receive deterministically sorted input and a fixed random seed; greedy overlap remapper preserves existing IDs so hand-edited `.graphify_labels.json` labels don't drift onto wrong communities (#824)
- Fix: `--no-cluster` flag added to `graphify update` — writes raw AST graph without clustering, consistent with `graphify extract --no-cluster` (#824)
- Fix: `graphify update --no-cluster` now writes `"links"` key matching the schema of the full clustered path; previously wrote `"edges"`, causing schema toggle on every mode switch
- Fix: `.graphify_labels.json` was rewritten on every rebuild even when nothing changed; now only written when outputs actually change
- Fix: shrink-check (refuse overwrite when new graph has fewer nodes) was duplicated across two code paths; unified into a single `_check_shrink()` helper
- Fix: node ID format in skill.md corrected to `{parent_dir}_{filename_stem}_{entity}` — the old filename-only format caused ghost-duplicate nodes when AST and semantic extractors disagreed on the stem; top-level files use just the filename stem; existing graphs with ghost duplicates can be cleaned up with `graphify extract --force`
- Fix: safer JSON serialization in clustering sort keys (`default=str`) prevents crashes when edge attributes contain non-serializable values
- Docs: added Prerequisites, optional extras table, environment variables reference, troubleshooting, and dev setup to README (#833)

## 0.7.17 (2026-05-13)

- Fix: `graphify path` and `graphify explain` now render arrow direction correctly — `-->` for caller→callee, `<--` for callee←caller; previously the graph was loaded undirected so every hop printed `-->` regardless of stored direction (#849, #853)
- Fix: MCP `shortest_path` and `get_neighbors` tools had the same reversed-arrow bug; now fixed in `serve.py` alongside the CLI commands (#849, #853)
- Fix: `graphify extract --backend bedrock` was rejected by the CLI guard even when `AWS_PROFILE`/`AWS_REGION`/`AWS_DEFAULT_REGION`/`AWS_ACCESS_KEY_ID` were set — boto3 session auth was never reached (#846)
- Fix: BFS/DFS query traversal now skips expanding high-degree hub nodes (threshold: `max(50, p99_degree)`) as transit — hubs can still be destinations but no longer produce semantically meaningless 2-hop paths like `ClassA → View → ClassB` in Android/Spring corpora (#830)
- Fix: `--update` manifest shrink — after an incremental run, `manifest.json` was overwritten with only the changed-file subset, causing the next `--update` to re-flag the entire unchanged corpus as new; Step 9 now persists the full corpus via `all_files` fallback (#837)
- Fix: `file_type` enum aligned across `skill.md` and `llm.py` (both now enumerate all six values: `code`, `document`, `paper`, `image`, `rationale`, `concept`); synonym mapper in `build.py` silently coerces known LLM-emitted synonyms (`pattern→concept`, `markdown→document`, `tool→code`, etc.) before validation (#840)
- Fix: Fortran test fixture renamed `sample.F90` → `sample_preprocessed.F90` to avoid case-collision with `sample.f90` on macOS case-insensitive filesystems (credit: @FatahChan, #823)

## 0.7.16 (2026-05-12)

- Fix: all `read_text()`/`write_text()` calls in `skill.md` and `skill-windows.md` now specify `encoding="utf-8"` — bare calls defaulted to the system codepage on Chinese-locale Windows, silently mojibaking node labels and Markdown content on `--update` (#832)
- Fix: `json.dumps` in skill pipeline now uses `ensure_ascii=False` so Chinese/CJK characters are stored as-is rather than `\uXXXX` escaped (#832)
- Fix: Step 1 install fallback in skill now prefers `uv tool install --upgrade graphifyy` over `pip` when uv is on PATH — pip was installing to the wrong environment when graphify was originally installed via `uv tool` (#831)
- Fix: `_score_nodes` in `serve.py` now uses three-tier precedence (exact 1000 / prefix 100 / substring 1) instead of flat substring scoring — `graphify path "Foo" "FooBar"` no longer returns 0 hops when both labels substring-match the same node (#828)
- Fix: `graphify path` and MCP `_tool_shortest_path` now emit a clear error when source and target resolve to the same node, instead of silently returning 0 hops (#828)
- Fix: `file_hash` in `cache.py` now normalises path keys via `.as_posix().lower()` — Windows junction/case variants of the same file now hash identically, fixing `save_semantic_cache` always reporting "Cached 0 files" on subsequent `--update` runs (#826)
- Fix: `check_semantic_cache` now applies the same absolute-path normalization as `save_semantic_cache` so relative `source_file` paths resolve consistently on both sides (#826)
- Fix: `_AGENTS_MD_SECTION` now includes the `/graphify` skill trigger instruction — all 7 AGENTS.md platforms (OpenCode, Codex, Aider, Trae, Hermes, OpenClaw, Factory Droid) now correctly invoke the skill tool when the user types `/graphify` (#827)

## 0.7.15 (2026-05-11)

- Fix: `-h`/`--help`/`-?` in any position now stops execution — previously `graphify cursor install --help` silently installed into Cursor; `graphify benchmark --help` crashed with FileNotFoundError (#821)
- Fix: `--version`, `-v`, and `graphify version` now print the installed version and exit (#818)
- Fix: `GRAPHIFY_OLLAMA_NUM_CTX=<invalid>` no longer falls back to hardcoded 131072 (which exhausted VRAM) — it now falls through to the auto-derived value and prints a warning (#820)
- Fix: when `GRAPHIFY_OLLAMA_NUM_CTX` is set smaller than the estimated chunk size, graphify now warns explicitly that Ollama will silently truncate the prompt and suggests a corrected `--token-budget` (#820)

## 0.7.14 (2026-05-11)

- Fix: `_make_id` and `_normalize_id` now apply NFKC Unicode normalization before ID generation -- composed/decomposed forms of the same character (e.g. `é` typed vs pasted from a PDF) now produce the same node ID; switched from `.lower()` to `.casefold()` for correct Turkish/German/Greek case folding; both functions are now byte-for-byte equivalent (#811)
- Fix: non-ASCII identifiers (CJK, Cyrillic, Arabic, accented Latin) are no longer collapsed to a bare file stem -- `[^\w]+` with `re.UNICODE` replaces the old `[^a-zA-Z0-9]+` so Unicode word chars are preserved as part of the ID (#811)
- Fix: dedup edge remap uses explicit key-presence check instead of `or` so empty-string `source` is not silently swapped for `from`; stale `from`/`to` keys are now popped before the edge is emitted so they can't leak into `graph.json` edge attributes (#803)
- Fix: `--update` merge now calls `build_merge()` directly instead of an inline NetworkX round-trip that re-introduced the direction-flip bug from #760; dict merge ordering fixed so explicit `source`/`target` always win over stale attrs; hyperedges pulled from `G.graph` (merged) rather than just the new extraction (#801)
- Fix: subagent chunk files are now written to an absolute path (`CHUNK_PATH` injected at dispatch time from `graphify-out/.graphify_root`) so the Write tool doesn't lose chunks to an undefined working directory (#808)
- Fix: skill version mismatch warning is now suppressed during `hook-check` (runs on every editor tool use and must be silent) and routed to stderr for all other commands

## 0.7.13 (2026-05-09)

- Fix: Ollama `num_ctx` now derived from actual chunk size instead of hardcoded 131072 -- over-allocating 128k KV-cache slots for small chunks exhausted VRAM by chunk 4 on large models; formula is `min(input_tokens + output_cap + 2000, 131072)` so `--token-budget 8192` gets ~26k instead of 131072 (#798)
- Fix: hollow-response warning now mentions VRAM pressure and `GRAPHIFY_OLLAMA_NUM_CTX` / `GRAPHIFY_OLLAMA_KEEP_ALIVE` env vars as tuning knobs (#798)
- Feat: `graphify export callflow-html` -- generates a self-contained Mermaid architecture/call-flow HTML page from `graphify-out/graph.json`, grouped by community with interactive zoom/pan diagrams, call detail tables, and graph report highlights (#797)
- Feat: callflow HTML auto-regenerates on every `--watch` rebuild and post-commit hook if the file already exists -- opt-in by existence, zero config (#800)

## 0.7.12 (2026-05-09)

- Fix: `graphify explain` and `graphify path` no longer crash on `MultiGraph` inputs -- new `edge_data()`/`edge_datas()` helpers in `build.py` handle both simple and multi-graphs; all 8 production call sites and 30 skill-file inline heredocs updated (#796)
- Fix: hollow Ollama responses (0 tokens / empty string) now trigger adaptive retry bisection instead of silently dropping the chunk -- `_response_is_hollow()` detects empty/null/whitespace content and parsed results with no nodes/edges, then rewrites `finish_reason="length"` to route into the existing bisection path (#792)
- Fix: post-commit hook no longer spawns unbounded parallel rebuilds -- per-repo `fcntl.flock` non-blocking lock in `_rebuild_code`; `changed_paths` wired from hook through to AST extractor; stale nodes evicted on deletion; `GRAPHIFY_REBUILD_TIMEOUT` watchdog; Darwin-aware memory cap (#791)
- Fix: Antigravity install now writes to `.agents/` (plural) -- corrected in platform config, paths, workflow body, and help text (#453)
- Fix: Antigravity rules file now includes `trigger: always_on` YAML frontmatter so Antigravity recognises it (#785)
- Feat: `graphify extract` gains `--max-workers`, `--token-budget`, `--max-concurrency`, `--api-timeout` flags; hard 8-worker AST cap removed; explicit HTTP timeout on OpenAI client (default 600s, `GRAPHIFY_API_TIMEOUT`); ollama API key gate skipped for loopback URLs (#792)
- Feat: Pascal/Delphi extraction now works without `tree-sitter-pascal` -- regex fallback covers unit/program/library headers, uses clauses, class/interface inheritance, method declarations, and intra-file calls (#781)
- Feat: `/graphify --help` now prints the Usage block and stops without running pipeline steps (all 12 skill files) (#795)

## 0.7.11 (2026-05-09)

- Fix: context-window-exceeded API errors now trigger automatic retry with bisected file chunks -- exponential bisection up to 6 levels deep; covers `"context_length_exceeded"`, `"maximum context length"`, and `"too_large"` across OpenAI-compat backends (#789)
- Fix: Windows pipeline unblocked -- `print_benchmark()` falls back to ASCII box-drawing on cp1252 consoles; `ProcessPoolExecutor` `BrokenProcessPool` caught and falls back to sequential extraction when caller lacks `if __name__ == "__main__":` guard; Windows skill file (`skill-windows.md`) rewrites all `python -c "..."` blocks as PowerShell heredocs to fix quote-escaping failures (#788)
- Fix: reversed `calls` edges after `--update` -- `build_merge()` now reads the saved JSON directly instead of round-tripping through NetworkX `node_link_graph()`, which was silently reversing edge direction on reload (#760)
- Fix: atomic SKILL.md install -- temp-file + `os.replace()` pattern prevents half-installed empty skill directories that looked valid but contained no file; version-stamp guard and warning added for missing installs (#725)
- Feat: `graphify uninstall` top-level command -- removes graphify skill files from all platforms in one shot; `--purge` flag also deletes `graphify-out/`
- Feat: SQL `ALTER TABLE` FK extraction -- `ADD CONSTRAINT ... FOREIGN KEY` and `ADD FOREIGN KEY` DDL statements now emit `references` edges; schema-qualified table names (`schema.table`) correctly resolved (#779)

## 0.7.10 (2026-05-07)

- Fix: `.tsx` files now use `language_tsx` grammar for JSX-aware parsing -- previously `language_typescript` was used, silently dropping all JSX-specific nodes (#766)
- Fix: `edges` key in saved graph JSON now normalised to `links` before loading -- prevents `KeyError: 'links'` on graphs written by older NetworkX versions in `query`, `path`, `explain`, and serve (#768)
- Fix: Google Workspace `gws export` drops unsupported `resourceKey` query param -- Drive API requires it as an HTTP header; sending it as a query param was a silent no-op (#772)
- Security: eleven hardening fixes -- Cypher escape strips C0 control chars and `\n`/`\r`; YAML frontmatter escapes U+2028, U+2029, tabs, and C0; MCP `sanitize_label` applied to all LLM-derived fields; C preprocessor blocked from `#include` exfiltration via `-nostdinc -I /dev/null`; merge-driver 50 MB file size cap and 100k node cap; `detect_backend()` places Ollama last so paid API keys take precedence over ambient `OLLAMA_BASE_URL`; Neo4j `--password` reads from `NEO4J_PASSWORD` env var by default; hooks exception handling narrowed to `(configparser.Error, OSError)`
- Refactor: skill YAML descriptions rewritten to be trigger-oriented (#774)
- Refactor: generated `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` templates strengthened with `ALWAYS`/`NEVER`/`IF ... EXISTS` graph-first directives (#775)

## 0.7.9 (2026-05-07)

- Feat: TypeScript extraction parity -- interface, enum, type alias, and module-level const nodes extracted; new_expression emits calls edges; parity with Java/C# class_types (#708)
- Feat: Quarto (`.qmd`) file support -- routed through existing Markdown extractor; Quarto executable code blocks (` ```{python} `) extracted as code nodes (#761)
- Feat: optional Google Workspace shortcut export for headless extraction -- `graphify extract ./docs --google-workspace` converts `.gdoc`, `.gsheet`, and `.gslides` files into Markdown sidecars with the `gws` CLI before semantic extraction; account email pseudonymized via SHA256 hash; `[google]` extra adds Sheets table rendering support (#752)
- Fix: Google Workspace exports now run `gws` from the sidecar output directory with a relative `-o` path, matching `gws` path validation and avoiding failures when extracting a corpus outside the current working directory.
- Feat: AWS Bedrock backend -- `graphify extract ./docs --backend bedrock`; credentials via standard AWS provider chain (AWS_PROFILE, AWS_REGION, IAM roles, SSO); model via GRAPHIFY_BEDROCK_MODEL (default anthropic.claude-3-5-sonnet-20241022-v2:0); `[bedrock]` extra adds boto3 (#757)

## 0.7.8 (2026-05-06)

- Fix: CommonJS `require()` imports now extracted from JS/TS -- `const { foo } = require('./mod')`, `const m = require('./mod')`, and `const x = require('./mod').y` all emit EXTRACTED `imports_from` (and per-symbol `imports`) edges. Previously CJS-only Node.js codebases produced AST graphs missing every import edge, which downgraded all cross-file calls to INFERRED.
- Fix: cross-file `calls` edges are now promoted from INFERRED to EXTRACTED when the caller's file has an explicit `imports` or `imports_from` edge to the callee. Previously every cross-file call was unconditionally INFERRED, even when a top-of-file `import` / `require` proved the binding. On a 92-file CJS Node.js corpus this promoted 88% of cross-file calls (104 of 118) to EXTRACTED.
- Feat: Gemini and OpenAI backends -- `graphify extract ./docs --backend gemini` (GEMINI_API_KEY / GOOGLE_API_KEY) or `--backend openai` (OPENAI_API_KEY); `[gemini]` and `[openai]` extras added (#735)
- Feat: Groovy and Spock support -- `.groovy` and `.gradle` extracted via tree-sitter-groovy; Spock spec files (`def "feature"()` syntax) handled via regex fallback (#732)
- Feat: Luau support -- `.luau` (Roblox Luau) added to code extraction using the Lua tree-sitter parser (#745)
- Feat: Markdown structural extraction -- headings, fenced code blocks, and nesting hierarchy extracted as graph nodes from `.md` and `.mdx` files with zero new dependencies (#711)
- Fix: `collect_files()` extension set now auto-syncs with `_DISPATCH` -- previously 18 extensions (`.sql`, `.vue`, `.svelte`, `.jsx`, `.ex`, `.jl`, etc.) were silently skipped in skill-mode extraction (#711)
- Fix: `detect_incremental` now forwards `follow_symlinks` to `detect()` -- symlinked subtrees no longer vanish on `--update` runs (#736)
- Fix: TS bare-path / `.svelte.ts` / `.svelte.js` / `index.ts` directory / multi-dot imports now resolve correctly -- previously these produced phantom edges dropped at merge time (#717, #716)
- Fix: `cluster-only` now loads and saves `.graphify_labels.json` -- human-readable community labels survive re-clustering instead of resetting to "Community N" (#744)
- Fix: `graphify export wiki` now fails fast with exit 1 if `.graphify_analysis.json` is missing -- prevents silent deletion of existing wiki articles (#746)
- Fix: `to_wiki()` now raises before the cleanup loop when `communities` is empty -- second safety layer against wiki data loss (#746)
- Fix: Ollama import error message now says "Ollama" not "Kimi" and points to `pip install openai`; `[ollama]` extras group added (#750)
- Security: hooks.py path execution now validates scripts are within the repo root -- closes supply-chain attack vector where a malicious commit could redirect hook execution (#747)

## 0.7.7 (2026-05-05)

- Feat: Ollama backend for headless extraction -- `graphify extract ./docs --backend ollama`; auto-detected when `OLLAMA_BASE_URL` is set; defaults to `qwen2.5-coder:7b`; zero cost ($0.00); sentinel API key handles OpenAI client auth requirement (#729)
- Feat: Cross-project global graph at `~/.graphify/global.json` -- `graphify global add/remove/list/path` to register multiple project graphs with `<repo>::<id>` prefixed node IDs, preventing silent collisions; hash-based skip avoids re-ingesting unchanged graphs (#729)
- Feat: `graphify extract --global --as <tag>` flag -- after building a project graph, auto-registers it into the global graph in one step (#729)
- Feat: `merge-graphs` now prefix-relabels each input graph before composing, preventing silent node ID collisions when two projects share entity names (#729)
- Fix: `deduplicate_entities` raises `ValueError` if called with nodes spanning multiple repos (cross-project dedup disabled by design -- per-project graphs are deduplicated in isolation) (#729)
- Fix: `detect_incremental()` now accepts and forwards `follow_symlinks` to `detect()`. Without this, `--update` runs silently miss any files reached through a symlinked sub-tree (e.g. `state_of_truth/` symlinking to a directory outside the corpus root), even when the original full run had detected them. Previously the flag was on `detect()` and `collect_files()` only. (#736)

## 0.7.6 (2026-05-05)

- Fix: `cluster-only` now accepts `--graph <path>` to specify a non-default graph.json location; positional path and flags can appear in any order (#724)
- Fix: `_is_sensitive()` no longer drops legitimate source files — word boundaries on the keyword pattern prevent false positives like `tokenizer.py`, `password_verification.py`, `SecretManager.java` (#718)
- Fix: `graphify extract --backend claude/kimi` raises default `max_tokens` from 8192 → 16384, eliminating the truncation-then-recursive-split cascade on dense doc corpora; respects `GRAPHIFY_MAX_OUTPUT_TOKENS` env var (#730)
- Fix: `--update` prune message now clearly distinguishes "N nodes pruned from M deleted files" from "M deletions detected but graph already clean — no drift" (#539)
- Fix: `extract_svelte()` stub nodes now carry the resolved import path as `source_file` instead of the importer's path, preventing metadata corruption after merge (#712)
- Fix: `extract_svelte()` now catches static `import X from './foo.svelte'` via a dedicated regex pass over `<script>` block content — previously tree-sitter's JS parser silently dropped all static imports in `.svelte` files (#713)
- Fix: `graphify extract` (full rebuild path) now saves `manifest.json` on every successful run, not only on `--update`; prevents stale-manifest drift on subsequent incremental runs (#538)
- Fix: `graphify antigravity install` now writes to `.agent/` (no trailing s) matching Antigravity's actual config paths (#704)
- Fix: Pi skill YAML frontmatter description simplified to avoid "nested mappings" parse error on Pi startup (#737)
- Fix: `--dedup-llm` flag now correctly threads LLM backend through to `deduplicate_entities` in both fresh and incremental extract paths; fresh extract path now also runs dedup (previously called `build_from_json` directly, bypassing dedup entirely)

## 0.7.5 (2026-05-04)

- Feat: `graphify extract` now runs incrementally - auto-detects prior `manifest.json` and re-extracts only changed/new files; semantic results cached by content hash so unchanged docs cost zero LLM tokens on repeat runs (#698)
- Feat: Entity deduplication pipeline runs on every build - entropy gate + MinHash/LSH blocking + Jaro-Winkler verification + same-community boost collapses near-duplicate entities (typos, spacing, plurals) before clustering
- Feat: `--dedup-llm` flag for `graphify extract` - optional LLM tiebreaker for ambiguous entity pairs (~$0.01 for 10k-node graphs), off by default
- Fix: `graphify hook install` rebuild now preserves human-readable community labels from `.graphify_labels.json` instead of resetting to generic "Community N" names on every commit (#705)
- Fix: `graphify install --platform gemini` now works correctly (#706)
- Deps: `datasketch` and `rapidfuzz` added as base dependencies

## 0.7.4 (2026-05-04)

- Fix: `_read_tsconfig_aliases()` now parses JSONC — handles `//` line comments, `/* */` block comments, and trailing commas that every TypeScript framework starter generates; warns to stderr on parse failure instead of silently returning `{}` (#700)
- Fix: `extract_svelte()` regex fallback now captures aliased dynamic imports (`$lib/...`, `$partials/...`, `@/...`) and uses correct `_make_id(str(path))` scheme so edges survive into `graph.json` instead of being dropped as phantom nodes (#701)

## 0.7.3 (2026-05-04)

- Feat: `graphify extract <path>` — headless full-pipeline extraction for CI; runs AST extraction on code files and semantic LLM extraction on docs/papers/images without Claude Code in the loop; supports `--backend kimi|claude`, `--out DIR`, `--no-cluster`; auto-detects backend from `MOONSHOT_API_KEY` / `ANTHROPIC_API_KEY`; docs-only corpora (issue #698) work cleanly
- Fix: export/query/path/explain CLI subcommands added in 0.7.2 now ship with integration tests
- Fix: skill.md reduced from 63KB to 47KB by replacing Python heredocs with CLI calls (#696)

## 0.7.2 (2026-05-04)

- Feat: Fortran support - extracts modules, subroutines, functions, programs, `use` imports, and `call` edges from `.f`, `.F`, `.f90`, `.F90`, `.f95`, `.F95`, `.f03`, `.F03`, `.f08`, `.F08` files; names are lowercased for case-insensitive matching (#694)

## 0.7.1 (2026-05-04)

- Fix: Obsidian export - community labels with `.`, `&`, `(`, `)` now produce valid Obsidian tags; only `[a-zA-Z0-9_\-/]` characters survive, preventing broken Dataview queries (#690)
- Fix: `_load_tsconfig_aliases()` now follows tsconfig `extends` chains - SvelteKit, Nuxt, and NestJS path aliases defined in extended configs are no longer silently dropped (#691)
- Fix: `.svelte` files now get a regex pass over the template layer after JS AST extraction - `{#await import('./X.svelte')}` markup-level dynamic imports are captured as edges (#692)
- Fix: recursion limit raised to 10,000 at extract entry points (main process + each worker) with a `_safe_extract` wrapper that skips pathological files with a clear warning instead of crashing the whole run (#695)

## 0.7.0 (2026-05-03)

Multi-dev busy-repo support: four gaps that caused merge conflicts, stale graphs, and silent cache misses in team workflows.

- Feat: `graphify hook install` now also configures a git merge driver for `graphify-out/graph.json` — union-merges two graph.json files so git never produces conflict markers in the knowledge graph; writes `.gitattributes` and registers `graphify merge-driver` in `.git/config`
- Feat: `graphify merge-driver <base> <current> <other>` subcommand — takes two graph.json variants and writes their node/edge union back to `<current>`; always exits 0 so merge never blocks
- Feat: Leiden community detection now seeded (`seed=42` when supported) for deterministic community IDs across parallel rebuilds — reduces JSON diff churn in multi-dev repos
- Feat: `graph.json` now embeds `built_at_commit` (git HEAD) at write time; `GRAPH_REPORT.md` surfaces the commit hash and a freshness check hint
- Fix: `file_hash` is now content-only (path removed from hash) — renamed files reuse their cache entry instead of re-extracting; cached `source_file` fields are updated to the new path on load
- Fix: watch mode mixed-batch handling — commits with both code and non-code files now rebuild code immediately AND write `needs_update` flag; previously code changes were silently dropped in mixed batches

## 0.6.9 (2026-05-03)

- Fix: `source_file` path separators normalized to forward slashes at graph ingestion — same physical file emitted with backslashes (Windows AST extractor) and forward slashes (semantic subagents) now merges into one node instead of splitting into two disconnected components (#683)
- Fix: two-phase cohesion re-clustering — communities with cohesion < 0.05 and ≥ 50 nodes are re-split, preventing doc-hub nodes (e.g. `CLAUDE.md`) from merging unrelated subsystems into one giant community (#683)
- Fix: VS Code Copilot instructions rewritten to be prescriptive — agent's first tool call must read `GRAPH_REPORT.md`, explicit trigger list, narrow allowlist for raw source reads (#688)
- Feat: `GRAPHIFY_OUT` env var overrides the output directory — accepts a relative name or absolute path, wires through `cache.py`, `watch.py`, and the CLI; useful for sharing one graph across multiple git worktrees (#686)
- Fix: `graphify antigravity install` now auto-updates stale rules and workflow files on re-run instead of silently skipping them (#652)
- Docs: README simplified — less dense, plain language; technical pipeline details moved to `docs/how-it-works.md`

## 0.6.8 (2026-05-03)

- Fix: `.graphifyignore` negation patterns (`!src/**`) now work correctly — when any `!` pattern is present, directory pruning is deferred to per-file checks so negated files inside ignored directories are reached (#676)
- Fix: Antigravity slash command `/graphify` now appears in the command dropdown — workflow file now includes YAML frontmatter with `name: graphify` required for Antigravity discovery (#678)
- Fix: Gemini CLI BeforeTool hook replaced `[ -f ... ] && echo` (bash-only) with cross-platform `python -c` using `json.dumps` — fixes hook failure on Windows CMD and Git Bash (#681)
- Fix: Codex hook-check exits silently — resolves `additionalContext` rejection on Codex Desktop PreToolUse (#651)
- Fix: `graphify install --platform codex` now writes absolute path to `graphify` executable — fixes PATH resolution in VS Code extension on Windows (#651)
- Fix: thin communities (fewer than 3 concept nodes) are now omitted from the Communities section in `GRAPH_REPORT.md` by default; report header shows `(N total, M thin omitted)` and Knowledge Gaps collapses thin communities to one summary line (#664)

## 0.6.7 (2026-05-02)

- Feat: `graphify tree` — self-contained D3 v7 collapsible-tree HTML view of `graph.json`; expand/collapse controls, depth-based colours, hover inspector; XSS-safe (#557)
- Feat: token-aware chunking with split-and-retry on truncation (#625)
- Feat: cross-language edge context filters in MCP `query_graph` tool (#573)
- Feat: dynamic `import()` extraction for JS/TS (#579)
- Fix: `save_semantic_cache` crashed with `IsADirectoryError` when a node's `source_file` was a directory path — `p.exists()` → `p.is_file()` (#655)
- Fix: `sanitize_label(None)` raised `TypeError` crashing `to_html` on graphs with null `source_file` rationale nodes — return `""` early (#656)
- Fix: chunk-extraction prompt omitted `rationale` from valid `file_type` values — model hallucinated `concept` on every doc/paper run; explicit merge step added to all skill variants (#657)
- Fix: `cost.json` always reported 0 tokens — chunk JSONs have placeholder zeros; orchestrator now globs and sums real token counts before merging (#658)
## 0.6.6 (2026-05-02)

- Fix: `skill-windows.md` rewritten from PowerShell to bash — Claude Code on Windows uses git-bash so PowerShell syntax (`$null`, `$LASTEXITCODE`, `Select-Object`, `& (Get-Content ...)`, `Remove-Item`) caused exit code 49 failures; now mirrors `skill.md` structure with `python` added as fallback after `python3` for Windows Conda (#39)
- Fix: wiki `to_wiki()` now clears stale articles before regenerating, preventing orphan .md accumulation (#558)
- Fix: `_safe_filename()` in wiki.py now strips Windows-reserved characters (`< > : " / \ | ? *`) and caps length at 200 chars (#594)
- Fix: rationale-node leakage in cross-file INFERRED call resolution — rationale nodes now excluded from name lookup; edge direction (`calls`, `rationale_for`) preserved correctly at JSON export (#576)
- Feat: `.graphifyinclude` hidden path allowlist — opt specific hidden dirs into traversal (e.g. `.hermes/plans/**/*.md`) (#583)
- Feat: `--no-viz` flag wired in `cluster-only`; `GRAPHIFY_VIZ_NODE_LIMIT` env var overrides 5000-node HTML threshold (#565)
- Fix: stray colon SyntaxError in `skill-trae.md` `--cluster-only` block (#603)
- Docs: skill INFERRED confidence score guidance changed to discrete rubric (0.55/0.65/0.75/0.85/0.95) backed by calibration data (#546)
- Docs: skill `--update` prune output clarified — splits no-drift vs drift cases (#544)
- Docs: skill `--update` merge step now calls `save_manifest` to prevent deleted files reappearing (#545)
- Feat: `graphify tree` — self-contained D3 v7 collapsible-tree HTML view of `graph.json`; expand/collapse controls, depth-based colours, hover inspector; XSS-safe via `html.escape()` and `_js_safe()` (#557)

## 0.6.5 (2026-05-02)

- Fix: Kotlin call-walker now accepts both `simple_identifier` and `identifier` node types — PyPI's `tree_sitter_kotlin` grammar uses `identifier` while older forks use `simple_identifier`, causing zero `calls` edges to be emitted (#659)
- Feat: community sidebar now uses checkbox-based multi-select instead of show/hide buttons — supports indeterminate "select all" state (#647)
- Feat: `graphify update --force` and `GRAPHIFY_FORCE=1` env var — bypass the node-count safety check after refactors that legitimately shrink the graph (#639)
- Fix: Codex PreToolUse hook on Windows — replaced `python3 -c "..."` inline command (fails on Conda where only `python` exists, and breaks PowerShell JSON parsing) with `graphify hook-check`, a new shell-agnostic subcommand. Re-run `graphify codex install` to regenerate the hook (#651, #522)

## 0.6.4 (2026-05-02)

- Fix: Codex PreToolUse hook failed on Windows — `[ -f ]` is bash-only and crashes on `cmd.exe`; replaced with a cross-platform Python one-liner (`pathlib.Path.exists()`) (#651)

## 0.6.3 (2026-05-02)

- Fix: incremental rebuild (`graphify update`, post-commit hook) dropped INFERRED/AMBIGUOUS semantic nodes extracted from code files — node preservation now filters by ID membership in the new AST output instead of `file_type`, so LLM-extracted call/data-flow edges survive code-only rebuilds (#653)
- Fix: post-commit and post-checkout hooks blocked `git commit` for the full rebuild duration (hours on large repos) — rebuilds now detach via `nohup & disown`, git returns in ~100ms, log written to `~/.cache/graphify-rebuild.log` (#650)
- Fix: cross-file INFERRED `calls` resolution used a last-write-wins name map, causing common short names (`log`, `execute`, `find`) to accumulate hundreds of spurious edges and dominate god_nodes ranking — resolution now skips any callee name that matches 2+ candidates (ambiguous, no import evidence to pick the right target) (#543)
- Fix: `cluster-only` command crashed on graphs with >5000 nodes due to unguarded `to_html` call — now wrapped in try/except ValueError matching the watch/hook path (#541)

## 0.6.2 (2026-05-01)

- Fix: Kimi K2.6 reasoning mode consumed entire token budget leaving `content` empty — thinking now disabled on Moonshot calls so graphs actually populate (#623)
- Fix: `graphify update` / `graphify watch` never persisted the manifest, so every subsequent `--update` re-extracted all files — manifest now saved after each rebuild (#621)
- Fix: inline comments in `.graphifyignore` (e.g. `vendor/ # legacy`) now stripped correctly — whitespace + `#` suffix is treated as a comment, `path#hash.py` preserved (#605)
- Fix: `graphify query "FunctionName"` now returns the exact matching node first instead of high-degree hub modules hijacking the output — 100-point exact-match bonus + seeds render before BFS expansion (#638)
- Fix: concurrent AST extractors raced on a shared `.tmp` cache file — each writer now gets a unique tempfile via `mkstemp`, eliminating cache corruption under parallel extraction (#589)
- Fix: `_clone_repo` branch names starting with `-` could be interpreted as git flags — validation added, `--` separator inserted before positional args (#589)
- Fix: replaced `html2text` (GPL-3.0) with `markdownify` (MIT) — removes the only copyleft dependency from a MIT project (#586)
- Fix: `--update` re-extracted files whose mtime was bumped by sync tools (Obsidian, Nextcloud) without content changes — manifest now stores content hash alongside mtime; mtime bump triggers an MD5 check before re-extraction (#593)
- Feat: R language support — `.r` files classified as code and processed via LLM semantic extraction (#617)
- Feat: extensionless shell scripts now detected via shebang (`#!/bin/bash`, `#!/usr/bin/env python3`, etc.) and included as code (#619)
- Fix: cross-language INFERRED `calls` edges (e.g. Python→TypeScript name collision) no longer appear as top surprising connections in GRAPH_REPORT.md (#630)
- Fix: `cluster-only` CLI silently flipped directed graphs to undirected — `directed` flag now read from graph.json and preserved through re-clustering (#590)
- Fix: Windows UNC / extended-length paths (`\\?\C:\...`) now normalize to consistent cache keys (#629)
- Fix: `.graphifyignore` negation patterns (`!src/lib/secrets.ts`) now work — full last-match-wins evaluation with `!` un-ignore support (#628)

## 0.6.1 (2026-05-01)

- Fix: `.graphifyignore` discovery now uses correct gitignore semantics — outer rules are loaded first so inner (closer) rules always win via last-match-wins, matching standard gitignore behavior (#643)
- Fix: without a VCS root, `.graphifyignore` discovery is now hermetic to the scan folder — no leakage across sibling projects in a shared workspace (#643)
- Fix: anchored patterns (leading `/`) in a parent `.graphifyignore` now correctly apply only relative to their own directory, not the scan root (#643)
- Fix: trailing spaces in patterns are now handled per gitignore spec — unescaped trailing spaces are stripped, `vendor\ ` (escaped) is preserved (#643)

## 0.6.0 (2026-05-01)

- Feat: SQL AST extractor — `.sql` files now processed deterministically via tree-sitter. Extracts tables, views, functions/procedures, foreign key references, and FROM/JOIN reads_from edges. No LLM needed. Requires `pip install 'graphifyy[sql]'` (#349)
- Feat: `xlsx_extract_structure()` utility — extracts sheet names, named tables, and column headers from .xlsx files as structural nodes

## 0.5.7 (2026-04-30)

- Feat: YAML/YML files now indexed for semantic extraction — Kubernetes, Kustomize, Helm, and any YAML corpus now picked up automatically (#633)

## 0.5.6 (2026-04-30)

- Fix: `NameError: name '_os' is not defined` crash after `graphify update` — this was fixed in v5 branch but not released to PyPI (#618, #612)

## 0.5.5 (2026-04-29)

- Feat: Kimi K2.6 backend — `pip install 'graphifyy[kimi]'` + `MOONSHOT_API_KEY` routes semantic extraction through Kimi K2.6. 3-6x richer relation extraction at ~3x lower cost. Claude remains default; Kimi is opt-in.
- Fix: phantom god nodes (#598) — member-call callees (`this.logger.log()` → `log`) no longer cross-file resolved. Go package-qualified calls (`pkg.Func()`) correctly preserved. Affects JS/TS, Go, Rust, Swift, Kotlin, Scala, PHP, C++, C#, Zig, Elixir.
- Fix: `concept` file_type no longer triggers validation warnings (#601)
- Fix: `graphify update` remembers scan root via `graphify-out/.graphify_root` — no path argument needed on subsequent runs
- Fix: Kimi K2.6 temperature 400 error — temperature param is now skipped for Kimi backends (model enforces its own fixed value) (#610)
- Fix: community labels deleted in Step 9 cleanup — `.graphify_labels.json` is now preserved so wiki/obsidian/HTML retain human-readable names after re-cluster (#608)
- Fix: `NameError: name '_os' is not defined` in `graphify update` Kimi tip (#612)
- Fix: `SyntaxWarning` in `__main__.py` for shell glob pattern with backslash escapes
- Fix: Python upper bound removed — `requires-python = ">=3.10"` now supports Python 3.14+ (#607)

## 0.5.4 (2026-04-28)

- Fix: SSRF DNS rebinding — `safe_fetch` now patches `socket.getaddrinfo` for the full request duration (#591)
- Fix: yt-dlp SSRF bypass — `download_audio` now calls `validate_url` before handing URL to yt-dlp (#592)

## 0.5.3 (2026-04-27)

- Fix: cache namespace — AST and semantic entries now live in `cache/ast/` and `cache/semantic/` subdirectories; flat entries read as migration fallback

## 0.5.2 (2026-04-26)

- Fix: PreToolUse hook now matches on `Bash` instead of `Glob|Grep` for Claude Code v2.1.117+

## 0.5.1 (2026-04-25)

- Fix: node ID collision for same-named files in different directories
- Fix: `source_file` paths relativized before return so `graph.json` is portable
- Fix: desync guard — `to_json()` returns bool; report only written on successful JSON write
- Feat: TypeScript `@/` path aliases resolved via `tsconfig.json`
- Feat: Show All / Hide All buttons in HTML community panel

## 0.5.0 (2026-04-24)

- Feat: `graphify clone <github-url>` — clone and graph any public repo
- Feat: `graphify merge-graphs` — combine multiple `graph.json` outputs into one cross-repo graph
- Feat: `CLAUDE_CONFIG_DIR` support in `graphify install`
- Feat: shrink guard — `to_json()` refuses to overwrite with a smaller graph
- Feat: `build_merge()` for safe incremental updates
- Feat: duplicate node deduplication via `deduplicate_by_label()`
- Fix: `graphify-out/` excluded from source scanning

## 0.4.23 (2026-04-18)

- Fix: stale skill version warning persists after running `graphify install` when multiple platforms were previously installed — `graphify install` now refreshes `.graphify_version` in all other known skill directories so the warning clears across the board (#178)
- Fix: `.html` files silently skipped during detection — added `.html` to `DOC_EXTENSIONS`; HTML pages, docs, and web project content now indexed correctly (#260)
- Fix: `_rebuild_code` (watch/update/hook) fails entirely on graphs > 5000 nodes because `to_html` raises `ValueError` — wrapped in its own try/except so `graph.json` and `GRAPH_REPORT.md` always land; stale `graph.html` from a previous smaller run is removed (#432)
- Fix: Go stdlib imports (e.g. `"context"`) produced `imports_from` edges pointing at local files of the same basename — Go import node IDs now prefixed `go_pkg_` using the full import path, eliminating false cycle-dependency pairs (#431)

## 0.4.22 (2026-04-18)

- Fix: AST cache written to `src/graphify-out/cache/` instead of project root when all code files share a common prefix like `src/` — `extract()` now called with explicit `cache_root=watch_path` in `_rebuild_code` and `cache_root=Path('.')` in the Codex skill AST step (#429)
- Fix: `.mdx` files silently skipped during detection — added `.mdx` to `DOC_EXTENSIONS` in `detect.py`; MDX-based corpora (Next.js, Docusaurus, Astro) now indexed correctly (#428)

## 0.4.21 (2026-04-17)

- Fix: `graphify cluster-only` crashed with `KeyError: 'total_files'` in `report.py` — cluster-only skips detection so the stats dict was empty; now passes a `warning` key so the report skips the file-stats section (#422)
- Fix: `/graphify --update` dropped all existing graph nodes — the merge block built a correct in-memory `G_existing` but never wrote it back to `.graphify_extract.json`, so Step 4 rebuilt from the new-extraction-only file; merged result is now serialized back before Step 4 runs (#423)

## 0.4.20 (2026-04-17)

- Fix: JS/MJS `imports_from` edges were silently dropped for files that use `../subdir/file.mjs` style imports — `Path.parent / raw` left `..` segments unnormalized, so the generated target ID didn't match the actual file node ID. Fixed with `os.path.normpath` (#414)
- Fix: `graphify update .` and `graphify cluster-only` now generate `graph.html` alongside `graph.json` and `GRAPH_REPORT.md` — previously only the skill generated the interactive HTML (#418)

## 0.4.19 (2026-04-17)

- Fix: AST and semantic extraction no longer produce mismatched node IDs — `build_from_json` now normalises IDs before dropping edges, so edges survive when the LLM generates slightly different casing or punctuation than the AST extractor (#390)
- Fix: cross-file call resolution extended to Go, Rust, Zig, PowerShell, and Elixir — unresolved callees are now saved as `raw_calls` and resolved globally in a post-pass, matching existing behaviour for Python, Swift, Java, C#, Kotlin, Scala, Ruby, and PHP (#298)
- Fix: Windows `graphify-out/graphify-out` nesting bug — `cache_dir` and `_rebuild_code` in watch.py now call `.resolve()` on the root path, preventing a nested output directory when graphify is run from a subdirectory (#410)
- Fix: `graphify hook install` now respects `core.hooksPath` git config (used by Husky and similar tools) — hooks are written to the configured path instead of always `.git/hooks` (#401)
- Fix: Kiro skill YAML frontmatter — `description` value is now quoted and colons replaced with dashes, preventing a parse error in Kiro's YAML loader (#385)
- Docs: added Windows PATH tip (`%APPDATA%\Python\PythonXY\Scripts`) and macOS pipx tip (`pipx ensurepath`) to the install section (#413)
- Docs: added team workflow section — committing `graphify-out/`, `.graphifyignore` usage, and recommended `.gitignore` additions (#369)

## 0.4.16 (2026-04-16)

- Fix: graphify watch crashed on all platforms with NameError because import sys was missing from watch.py (#386, #394)
- Fix: .mjs files were detected but produced 0 nodes — added .mjs to the AST extractor dispatch table (#387)
- Fix: llm.py excluded from the published wheel (local benchmarking file, not part of the public API) (#391)

## 0.4.15 (2026-04-15)

- Feat: VS Code Copilot Chat support — `graphify vscode install` installs a Python-only skill (works on Windows PowerShell) and writes `.github/copilot-instructions.md` for always-on graph context (#206)
- Fix: OpenCode plugin path used backslashes on Windows causing duplicate entries in `opencode.json` — now uses forward slashes via `.as_posix()` (#378)
- Fix: Gemini CLI on Windows now installs skill to `~/.agents/skills/` (higher priority) instead of `~/.gemini/skills/` (#368)
- Fix: `.mjs` and `.ejs` files now recognised by the AST extractor as JavaScript (#365, #372)
- Fix: `god_nodes()` field renamed from `edges` to `degree` for clarity — updated in report, wiki, serve, and all tests (#375)
- Fix: macOS `graphify watch` now uses `PollingObserver` by default to avoid missed events with FSEvents (#373)

## 0.4.14 (2026-04-15)

- Fix: cross-file call edges now emitted for all languages (Swift, Go, Rust, Java, C#, Kotlin, Scala, Ruby, PHP, and others) — previously only Python had cross-file resolution; unresolved call sites are now saved per file and resolved against a global label map in a post-pass (#348)
- Fix: PHP extractor now handles `scoped_call_expression` (static method calls like `Helper::format()`) and `class_constant_access_expression` (enum/constant references like `Status::ACTIVE`) — both were silently dropped before (#230, #232)
- Fix: `--wiki` flag now runs `to_wiki()` as Step 6b in the skill pipeline before the cleanup step — community labels are available and the wiki is written to `graphify-out/wiki/` (#229, #354)
- Fix: `graphify install --platform opencode` now also installs the `.opencode/plugins/graphify.js` plugin, matching what `graphify opencode install` does (#356)
- Fix: `extract()` accepts explicit `cache_root` parameter so subdirectory runs no longer write cache to `<subdir>/graphify-out/cache/` (#350)
- Fix: `os.replace` in cache writer falls back to `shutil.copy2` on `PermissionError` (Windows WinError 5) (#287)
- Fix: `graphify update` exits with code 1 on rebuild failure instead of silently returning (#287)
- Fix: `CLAUDE.md`, Cursor, and Antigravity templates now use `graphify update .` instead of hardcoded `python3 -c` invocation (#287)
- Fix: `skill-kiro.md` added to `pyproject.toml` package-data — `graphify kiro install` was failing on fresh pip installs (#352)
- Fix: `betweenness_centrality` in `suggest_questions` uses `k=100` approximate sampling for graphs over 1000 nodes; `edge_betweenness_centrality` returns early for graphs over 5000 nodes (#341)

## 0.4.13 (2026-04-14)

- Add: Verilog/SystemVerilog support — `.v` and `.sv` files extracted via tree-sitter-verilog (modules, functions, tasks, package imports, module instantiations with `instantiates` edges) (#325)
- Fix: hyperedge polygons render correctly on HiDPI/Retina displays — `afterDrawing` callback ctx is now used directly (already in network coordinate space), removing the double-applied transform and incorrect `canvas.width/2` DPR anchor (#334)
- Fix: AGENTS.md and GEMINI.md rebuild rule now uses `graphify update .` instead of hardcoded `python3 -c "..."` — correct Python is resolved through the graphify binary, no more interpreter mismatches in Nix/pipx/uv environments (#324)
- Fix: `graphify query` and `graphify explain` no longer crash with `AttributeError` when a node has `label: null` — all `.get("label", "")` calls guarded with `or ""` to handle explicit null values (#323)

## 0.4.12 (2026-04-13)

- Add: Kiro IDE/CLI support — `graphify kiro install` writes `.kiro/skills/graphify/SKILL.md` (invoked via `/graphify`) and `.kiro/steering/graphify.md` (`inclusion: always` — always-on context before every conversation) (#319, #321)
- Fix: cache `file_hash()` now uses the path relative to project root instead of the resolved absolute path — cache entries are now portable across machines, CI runners, and different checkout directories (#311)

## 0.4.11 (2026-04-13)

- Fix: `graphify query` no longer crashes with `ValueError` on MultiGraph graphs — `G.edges[u, v]` replaced with `G[u][v]` + MultiGraph guard (#305)
- Fix: `graphify query` no longer crashes with `AttributeError: 'NoneType' has no attribute 'lower'` when a node has a null `source_file` (#307)
- Fix: MCP server launched from a different directory now correctly derives the `graphify-out` base from the absolute path provided, instead of CWD (#309)
- Fix: `.graphifyignore` patterns from a parent directory now fire correctly when graphify is run on a subfolder — patterns are matched against paths relative to both the scan root and the `.graphifyignore`'s anchor directory (#303)

## 0.4.10 (2026-04-13)

- Fix: `graphify install --platform cursor` no longer crashes — passes `Path(".")` to `_cursor_install` (#281)
- Fix: `_agents_uninstall` now only removes the OpenCode plugin when uninstalling the `opencode` platform — other platforms were incorrectly having their OpenCode plugin stripped (#276)
- Fix: misleading comment in query `--graph` path handler removed (#278)
- Fix: `skill-codex.md` — `wait` → `wait_agent` (correct Codex tool name) (#273)
- Add: `svg = ["matplotlib"]` optional extra in pyproject.toml; `matplotlib` added to `[all]` extra (#288)
- Fix: `graspologic` dependency now has `python_version < '3.13'` env marker in `leiden` and `all` extras — prevents install failures on Python 3.13+ (#290)
- Add: Dart/Flutter support — `.dart` files extracted via regex (classes, mixins, functions, imports); added to `CODE_EXTENSIONS` (#292)
- Add: `norm_label` field written at build time in `to_json()` for diacritic-insensitive search; `_score_nodes` and `_find_node` in `serve.py` use `norm_label` with Unicode NFKD normalization fallback (#293)
- Add: Hermes Agent platform support — `graphify hermes install` writes skill to `~/.hermes/skills/graphify/SKILL.md` and AGENTS.md (#251)
- Add: PHP extractor now captures static property access (`Foo::$bar`) as `uses_static_prop` edges (#234)
- Add: PHP extractor now captures `config()` helper calls as `uses_config` edges pointing to the first config key segment (#236)
- Add: PHP extractor now captures service container bindings (`bind`, `singleton`, `scoped`, `instance`) as `bound_to` edges (#238)
- Add: PHP extractor now captures `$listen` / `$subscribe` event listener arrays as `listened_by` edges (#240)
- Add: `prune_dangling_edges()` utility in `export.py` — removes edges whose source/target is not in the node set (#294)
- Fix: Antigravity install injects YAML frontmatter into skill file for native tool discovery; rules now include MCP navigation hint; prints MCP config snippet (#268)
- Fix: Windows hook tests now use platform-aware assertions instead of POSIX executable bit checks (#279)
- Add: CLI commands `path`, `explain`, `add`, `watch`, `update`, `cluster-only` now work as bare terminal commands (not just AI skill invocations) — documented in `--help` output (#277)

## 0.4.8 (2026-04-12)

- Fix: platform skill files (aider, codex, opencode, claw, droid, copilot, windows) no longer contain Claude-specific language — references to "Claude" as the AI model replaced with platform-agnostic wording (#272)

## 0.4.7 (2026-04-12)

- Fix: `watch` semantic edge preservation was always empty — `graph.json` uses `links` key but code read `edges` (#269)
- Fix: `graphify claw install` now writes to `.openclaw/` (correct OpenClaw directory) instead of `.claw/` (#208)
- Add: Blade template support — `@include`, `<livewire:>` components, and `wire:click` bindings extracted from `.blade.php` files (#242)
- Docs: WSL/Linux MCP setup note — package name is `graphifyy`, use `.venv/bin/python3` in `.mcp.json` (#250)

## 0.4.6 (2026-04-12)

- Add: Google Antigravity support — `graphify antigravity install` writes `.agent/rules/graphify.md` (always-on rules) and `.agent/workflows/graphify.md` (`/graphify` slash command) (#203, #199, #53)

## 0.4.5 (2026-04-12)

- Fix: MCP server no longer crashes with `ValidationError` on blank lines sent between JSON messages by some clients (#201)

## 0.4.4 (2026-04-12)

- Fix: `watch` now preserves INFERRED/AMBIGUOUS edges (code↔doc rationale links) across rebuilds — previously all cross-type edges were dropped (#261)
- Fix: Codex hook no longer emits `permissionDecision:allow` which codex-cli 0.120.0 rejects (#249)
- Fix: Common lockfiles (`package-lock.json`, `yarn.lock`, `Cargo.lock`, etc.) are now skipped during detection, preventing token drain on large JS/Rust/Python projects (#266)

## 0.4.3 (2026-04-12)

- Fix: JS/TS relative imports now resolve to full-path node IDs — previously all `imports_from` edges were silently dropped on large TypeScript codebases (#256)
- Fix: Python relative imports (`from .foo import bar`) now resolve correctly to full-path node IDs (#256)
- Fix: `watch --rebuild_code` now merges fresh AST with existing semantic nodes from docs/papers instead of overwriting them (#253)
- Fix: Windows hooks now fall back to `python` if `python3` is not found; exits cleanly if neither has graphify installed (#244)
- Fix: `surprising_connections` / `suggest_questions` no longer crash with `KeyError` on stale `_src`/`_tgt` edge hints after node merges (#226)
- Add: `.vue` and `.svelte` files now recognized as code and included in extraction (#254)

## 0.4.2 (2026-04-11)

- Fix: same-basename files in different directories produced colliding node IDs — now uses full path (#211)
- Fix: edges using `from`/`to` keys instead of `source`/`target` were silently dropped (#216)
- Fix: empty graphs (no edges) crashed `to_html` with `ZeroDivisionError` (#217)
- Fix: post-commit hook skipped `.tsx`, `.jsx`, and other valid code extensions due to stale allowlist (#222)
- Fix: NetworkX ≤3.1 serialises edges as `links` — now accepted alongside `edges` (#212)
- Fix: version warning fired during `install`/`uninstall` and duplicated on shared paths (#220)
- Fix: all file IO now uses `encoding="utf-8"` — prevents crashes on Windows with CJK or emoji labels; hook writes use `newline="\n"` to prevent CRLF shebang breakage (#204)
- Fix: Obsidian export — node labels ending in `.md` produced `.md.md` filenames; `GRAPH_REPORT.md` now links to community hub files so vault stays in one connected component (#221)

## 0.4.1 (2026-04-10)

- Fix: `collect_files()` in `extract.py` now respects `.graphifyignore` — previously ignored patterns, causing thousands of unwanted files (e.g. `node_modules/`) to be scanned (#188)
- Fix: skill.md Step B2 now explicitly requires `subagent_type="general-purpose"` — using `Explore` type silently dropped extraction results since it is read-only and cannot write chunk files (#195)
- Fix: Step B3 now warns when chunk files are missing from disk instead of silently skipping them

## 0.4.0 (2026-04-10)

- Branch: v4 — video and audio corpus support
- Add: drop `.mp4`, `.mp3`, `.wav`, `.mov`, `.webm`, `.m4a`, `.ogg`, `.mkv`, `.avi`, `.m4v` files into any corpus and graphify transcribes them locally with faster-whisper before extraction
- Add: YouTube and URL download via yt-dlp — `/graphify add https://youtube.com/...` downloads audio-only and feeds it through the same Whisper pipeline
- Add: domain-aware Whisper prompts — the coding agent reads god nodes from the corpus and writes a one-sentence domain hint for Whisper itself, no separate API call
- Add: `graphify-out/transcripts/` cache — transcripts cached by filename; YouTube URLs cached by hash so re-runs skip already-transcribed files
- Requires: `pip install 'graphifyy[video]'` for faster-whisper and yt-dlp

## 0.3.29 (2026-04-10)

- Add: video and audio corpus support — drop `.mp4`, `.mp3`, `.wav`, `.mov`, `.webm`, `.m4a`, `.ogg`, `.mkv`, `.avi`, `.m4v` files into any corpus and graphify transcribes them with faster-whisper before extraction
- Add: YouTube and URL video download — pass a YouTube link (or any video URL) to `/graphify add <url>` and yt-dlp downloads audio-only, which is then transcribed and added to the corpus automatically
- Add: domain-aware Whisper prompts — god nodes from non-video files are used to build a one-sentence domain hint for Whisper via a cheap Haiku call, improving transcript accuracy on technical content
- Add: `graphify-out/transcripts/` cache — transcripts are cached by filename so re-runs skip already-transcribed files; URLs cached by hash
- Requires: `pip install 'graphifyy[video]'` for faster-whisper + yt-dlp

## 0.3.28 (2026-04-10)

- Fix: hook installers (Claude Code, Codex, Gemini CLI) now always remove and reinstall the hook on re-run — users upgrading from old versions no longer get stuck with a broken hook format (#182)
- Fix: rationale node labels no longer contain bare `\r` characters on Windows/WSL CRLF files — breaks Obsidian export was silently producing invalid filenames (#176)
- Fix: `skill-windows.md` now includes `--wiki`, `--obsidian-dir`, and `--directed` which were missing vs the main skill (#177)

## 0.3.27 (2026-04-10)

- Fix: graphify install --platform gemini now also copies the skill file to ~/.gemini/skills/graphify/SKILL.md so the /graphify trigger works in Gemini CLI (#174)

## 0.3.26 (2026-04-10)

- Fix: MCP server no longer uses a circular path validation when loading a graph outside cwd — now validates the path exists and ends in `.json` instead of checking containment within its own parent directory (security fix)

## 0.3.25 (2026-04-09)

- Fix: `graphify install --platform gemini` now routes to `gemini_install()` instead of erroring — `gemini` was missing from `_PLATFORM_CONFIG` (#171)
- Fix: `graphify install --platform cursor` now routes to `_cursor_install()` the same way (#171)
- Fix: `serve.py` `validate_graph_path` now passes `base=Path(graph_path).resolve().parent` so MCP server works when graph is outside cwd (#170)
- Fix: MCP `call_tool()` handler now wraps dispatch in try/except — exceptions in tool handlers return graceful error strings instead of crashing the stdio loop (#163)
- Fix: `_load_graphifyignore` now walks parent directories up to the `.git` boundary, matching `.gitignore` discovery behavior — subdirectory scans now inherit root ignore patterns (#168)
- Add: Aider platform support — `graphify install --platform aider` copies skill to `~/.aider/graphify/SKILL.md`; `graphify aider install/uninstall` writes AGENTS.md rules (#74)
- Add: GitHub Copilot CLI platform support — `graphify install --platform copilot` copies skill to `~/.copilot/skills/graphify/SKILL.md`; `graphify copilot install/uninstall` for skill management (#134)
- Add: `--directed` flag — `build_from_json()` and `build()` now accept `directed=True` to produce a `DiGraph` preserving edge direction (source→target); `cluster()` converts to undirected internally for Leiden; `graph_diff` edge key handles directed graphs correctly (#125)
- Add: Frontmatter-aware cache for Markdown files — `.md` files hash only the body below YAML frontmatter, so metadata-only changes (reviewed, status, tags) no longer invalidate the cache (#131)

## 0.3.24 (2026-04-09)

- Fix: `graphify codex install` (and opencode) no longer exits early when `AGENTS.md` already has the graphify section — partial installs with a missing `.codex/hooks.json` can now recover on re-run (#153)

## 0.3.23 (2026-04-09)

- Add: Gemini CLI support — `graphify gemini install` writes a `GEMINI.md` section and a `BeforeTool` hook in `.gemini/settings.json` that fires before file-read tool calls (#105)
- Add: sponsor nudge at pipeline completion — all skill files now print a one-line sponsor link after a fresh build, not on `--update` runs

## 0.3.22 (2026-04-09)

- Add: Cursor support — `graphify cursor install` writes `.cursor/rules/graphify.mdc` with `alwaysApply: true` so the graph context is always included; `graphify cursor uninstall` removes it (#137)
- Fix: `_rebuild_code()` KeyError — `detected[FileType.CODE]` corrected to `detected['files']['code']` matching `detect()`'s actual return shape; was silently breaking git hooks on every commit (#148)
- Fix: `to_json()` crash on NetworkX 3.2.x — `node_link_data(G, edges="links")` now falls back to `node_link_data(G)` on older NetworkX, same shim already used for `node_link_graph` (#149)
- Fix: README clarifies `graphifyy` is the only official PyPI package — other `graphify*` packages are not affiliated (#129)

## 0.3.21 (2026-04-09)

- Fix: Codex PreToolUse hook now places `systemMessage` at the top level of the output JSON instead of inside `hookSpecificOutput` — matches the strict schema enforced by codex-cli 0.118.0+ which uses `additionalProperties: false` (#138)
- Fix: git hooks now use `#!/bin/sh` instead of `#!/bin/bash` — Git for Windows ships `sh.exe` not `bash`, so hooks were silently skipped on Windows (#140)

## 0.3.20 (2026-04-09)

- Fix: XSS in interactive HTML graph — node labels, file types, community names, source files, and edge relations now HTML-escaped before `innerHTML` injection; neighbor link `onclick` uses `JSON.stringify` instead of raw string interpolation
- Add: OpenCode `tool.execute.before` plugin — `graphify opencode install` now writes `.opencode/plugins/graphify.js` and registers it in `opencode.json`, firing the graph reminder before bash calls (equivalent to Claude Code's PreToolUse hook) (#71)
- Fix: AST-resolved call edges now carry `confidence=EXTRACTED, weight=1.0` instead of INFERRED/0.8 — tree-sitter call resolution is deterministic, not probabilistic (#127)
- Fix: `tree-sitter>=0.23.0` now pinned in dependencies and `_check_tree_sitter_version()` guard added — stale environments now get a clear `RuntimeError` with upgrade instructions instead of a cryptic `TypeError` deep in the AST pipeline (#89)

## 0.3.19 (2026-04-09)

- Fix: install step now tries plain `pip install` before falling back to `--break-system-packages` — Homebrew and PEP 668 managed environments no longer risk environment corruption (#126)

## 0.3.18 (2026-04-09)

- Fix: `--watch` mode now respects `.graphifyignore` — `_rebuild_code` was calling `collect_files()` directly instead of `detect()`, bypassing ignore patterns (#120)
- Fix: Codex PreToolUse hook now uses `systemMessage` instead of `additionalContext` — Codex does not support `additionalContext` and was returning an error (#121)
- Fix: Trae link corrected from `trae.com` to `trae.ai` in README, README.zh-CN.md, README.ja-JP.md, README.ko-KR.md (#122)
- Docs: Korean README added (README.ko-KR.md) (#112)
- Refactor: `save_query_result` inline Python blocks in all 6 skill files replaced with `graphify save-result` CLI command — shorter, maintainable, less tokens for LLM (#114)
- Add: `graphify save-result` CLI subcommand — saves Q&A results to memory dir without inline Python
- Fix: HTML graph click detection now uses hover-tracking (`hoveredNodeId`) — more reliable than vis.js click params on small/dense nodes (#82)
- Fix: `mkdir -p graphify-out` now runs before writing `.graphify_python` in `skill.md` — prevents write failure on first run; `.graphify_python` no longer deleted in Step 9 cleanup across all skill files so follow-up commands keep their interpreter (#93)
- Fix: `skill-trae.md` added to `pyproject.toml` package-data — Trae users no longer hit `ModuleNotFoundError` after `pip install` (#102)
- Fix: `analyze.py` and `watch.py` now import extension sets from `detect.py` instead of local copies — Swift, Lua, Zig, PowerShell, Elixir, JSX, Julia, Objective-C files no longer misclassified as documents (#109)
- Refactor: dead `build_graph()` function removed from `cluster.py` (#109)

## 0.3.17 (2026-04-08)

- Add: Julia (.jl) support — modules, structs, abstract types, functions, short functions, using/import, call edges, inherits edges via tree-sitter-julia (#98)
- Fix: Semantic extraction chunks now group files by directory so related artifacts land in the same chunk, reducing missed cross-chunk relationships (#65)
- Fix: `tree-sitter>=0.21` now pinned in dependencies — prevents silent empty AST output when older tree-sitter is installed with newer language bindings (#52)
- Add: Progress output every 100 files during AST extraction so large projects don't appear to hang (#52)

## 0.3.16 (2026-04-08)

- Fix: `graphify query`, `serve`, and `benchmark` now work on NetworkX < 3.4 — version-safe shim for `node_link_graph()` at all call sites (#95)
- Fix: `.jsx` files now detected and extracted via the JS extractor — added to `CODE_EXTENSIONS` and `_DISPATCH` (#94)
- Fix: `.graphify_python` no longer deleted in Step 9 cleanup across all 6 skill files — pipx users no longer hit `ModuleNotFoundError` on follow-up commands (#92)

## 0.3.15 (2026-04-08)

- Feat: Trae and Trae CN platform support (`graphify install --platform trae` / `trae-cn`)
- Fix: `skill-droid.md` was missing from PyPI package data — Factory Droid users couldn't install the skill
- Fix: XSS in HTML legend — community labels now HTML-escaped before `innerHTML` injection
- Fix: Shebang allowlist validation in `hooks.py` and all 6 skill files — prevents metacharacter injection from malicious binaries
- Fix: `louvain_communities()` kwargs now inspected at runtime for cross-version NetworkX compatibility
- Fix: pipx installs now detected correctly in git hooks (reads shebang from graphify binary)
- Fix: graspologic ANSI escape codes no longer corrupt PowerShell 5.1 scroll buffer
- Docs: Japanese README added
- Docs: `graph.json` + LLM workflow example added to README
- Docs: Codex PreToolUse hook now documented in platform table

## 0.3.14 (2026-04-08)

- Fix: `graphify codex install` now also writes a PreToolUse hook to `.codex/hooks.json` so the graph reminder fires before every Bash tool call (#86)
- Fix: `--update` now prunes ghost nodes from deleted files before merging new extraction (#51)

## 0.3.13 (2026-04-08)

- Fix: PreToolUse hook now outputs `additionalContext` JSON so Claude actually sees the graph reminder before Glob/Grep calls (#83)
- Fix: Go AST method receivers and type declarations now use package directory scope, eliminating disconnected duplicate type nodes across files in the same package (#85)
- Fix: PDFs inside Xcode asset catalogs (`.imageset`, `.xcassets`) are no longer misclassified as academic papers (#52)
- Fix: `_resolve_cross_file_imports` is now guarded with `if py_paths` and wrapped in try/except so a Python parser crash can't abort extraction for non-Python files (#52)
- Fix: Skill intermediate files (`.graphify_*.json`) now live in `graphify-out/` instead of project root, preventing git pollution (#81)

## 0.3.12 (2026-04-07)

- Fix: `sanitize_label` was double-encoding HTML entities in the interactive graph (`&amp;lt;` instead of `&lt;`) — removed `html.escape()` from `sanitize_label`; callers that inject directly into HTML now call `html.escape()` themselves (#66)
- Fix: `--wiki` flag missing from `skill.md` usage table (#55)

## 0.3.11 (2026-04-07)

- Fix: Louvain fallback hangs indefinitely on large sparse graphs — added `max_level=10, threshold=1e-4` to prevent infinite loops while preserving community quality (#48)

## 0.3.10 (2026-04-07)

- Fix: Windows UnicodeEncodeError during `graphify install` — replaced arrow character with `->` in all print statements (#47)
- Add: skill version staleness check — warns when installed skill is older than the current package, across all platforms (#46)

## 0.3.9 (2026-04-07)

- Add: `follow_symlinks` parameter to `detect()` and `collect_files()` — opt-in symlink following with circular symlink cycle detection (#33)
- Fix: `watch.py` now uses `collect_files()` instead of manual rglob loop for consistency
- Docs: Codex uses `$graphify .` not `/graphify .` (#36)
- Test: 5 new symlink tests (367 total)

## 0.3.8 (2026-04-07)

- Add: C# inheritance and interface implementation extraction — `base_list` now emits `inherits` edges for both simple (`identifier`) and generic (`generic_name`) base types (#45)
- Add: `graphify query "<question>"` CLI command — BFS/DFS traversal of `graph.json` without needing Claude Code skill (`--dfs`, `--budget N`, `--graph <path>` flags)
- Test: 2 new C# inheritance tests (362 total)

## 0.3.7 (2026-04-07)

- Add: Objective-C support (`.m`, `.mm`) — `@interface`, `@implementation`, `@protocol`, method declarations, `#import` directives, message-expression call edges
- Add: `--obsidian-dir <path>` flag — write Obsidian vault to a custom directory instead of `graphify-out/obsidian`
- Fix: semantic cache was only saving 4/17 files — relative paths from subagents now resolved against corpus root before existence check
- Fix: 75 validation warnings per run for `file_type: "rationale"` — added `"rationale"` to `VALID_FILE_TYPES`
- Test: 6 Objective-C tests; `.m`/`.mm` added to `test_collect_files_from_dir` supported set (360 total)

## 0.3.0 (2026-04-06)

- Add: multi-platform support — Codex (`skill-codex.md`), OpenCode (`skill-opencode.md`), OpenClaw (`skill-claw.md`)
- Add: `graphify install --platform <codex|opencode|claw>` routes skill to correct config directory
- Add: `graphify codex install` / `opencode install` / `claw install` — writes AGENTS.md for always-on graph-first behaviour
- Add: `graphify claude uninstall` / `codex uninstall` / `opencode uninstall` / `claw uninstall`
- Add: MIT license
- Fix: `build()` was silently dropping hyperedges when merging multiple extractions
- Refactor: `extract.py` 2527 → 1588 lines — replaced 12 copy-pasted language extractors with `LanguageConfig` dataclass + `_extract_generic()`
- Docs: clustering is graph-topology-based (no embeddings) — explained in README
- Docs: all missing flags documented (`--cluster-only`, `--no-viz`, `--neo4j-push`, `query --dfs`, `query --budget`, `add --author`, `add --contributor`)

## 0.2.2 (2026-04-06)

- Add: `graphify claude install` — writes graphify section to local CLAUDE.md + PreToolUse hook in `.claude/settings.json`
- Add: `graphify claude uninstall` — removes section and hook
- Add: `graphify hook install` — installs post-commit and post-checkout git hooks (platform-agnostic)
- Add: `graphify hook uninstall` / `hook status`
- Add: `graphify benchmark` CLI command
- Fix: node deduplication documented at all three layers

## 0.1.8 (2026-04-05)

- Fix: follow-up questions now check for wiki first (graphify-out/wiki/index.md) before falling back to graph.json
- Fix: --update now auto-regenerates wiki if graphify-out/wiki/ exists
- Fix: community articles show truncation notice ("... and N more nodes") when > 25 nodes
- UX: pipeline completion message now lists all available flags and commands so users know what graphify can do

## 0.1.7 (2026-04-05)

- Add: `--wiki` flag — generates Wikipedia-style agent-crawlable wiki from the graph (index.md + community articles + god node articles)
- Add: `graphify/wiki.py` module with `to_wiki()` — cross-community wikilinks, cohesion scores, audit trail, navigation footer
- Add: 14 wiki tests (245 total)
- Fix: follow-up question example code now correctly splits node labels by `_` to extract verb prefixes (previous version used `def`/`fn` prefix matching which always returned zero results)

## 0.1.6 (2026-04-05)

- Fix: follow-up questions after pipeline now answered from graph.json, not by re-exploring the directory (was 25 tool calls / 1m30s; now instant)
- Skill: added "Answering Follow-up Questions" section with graph query patterns

## 0.1.5 (2026-04-05)

- Perf: semantic extraction chunks 12-15 → 20-25 files (fewer subagent round trips)
- Perf: code-only corpora skip semantic dispatch entirely (AST handles it)
- Perf: print timing estimate before extraction so the wait feels intentional
- Fix: 5 skill gaps - --graphml in Usage table, --update manifest timing, query/path/explain graph existence check, --no-viz clarity
- Refactor: dead imports removed (shutil, sys, inline os); _node_community_map() helper replaces 8 copy-pasted dict comprehensions; to_html() split into _html_styles() + _html_script(); serve.py call_tool() if/elif chain replaced with dispatch table
- Test: end-to-end pipeline integration test (detect → extract → build → cluster → analyze → report → export)

## 0.1.4 (2026-04-05)

- Replace pyvis with custom vis.js HTML renderer - node size by degree, click-to-inspect panel with clickable neighbors, search box, community filter, physics clustering
- HTML graph generated by default on every run (no flag needed)
- Token reduction benchmark auto-runs after every pipeline on corpora over 5,000 words
- Fix: 292 edge warnings per run eliminated - stdlib/external edges now silently skipped
- Fix: `build()` cross-extraction edges were silently dropped - now merged before assembly
- Fix: `pip install graphify` → `pip install graphifyy` in skill Step 1 (critical install bug)
- Add: `--graphml` flag implemented in skill pipeline (was documented but not wired up)
- Remove: pyvis dependency, dead lib/ folder, misplaced eval reports from tests/
- Add: 5 HTML renderer tests (223 total)

## 0.1.3 (2026-04-04)

- Fix: `pyproject.toml` structure - `requires-python` and `dependencies` were incorrectly placed under `[project.urls]`
- Add: GitHub repository and issues URLs to PyPI page
- Add: `keywords` for PyPI search discoverability
- Docs: README clarifies Claude Code requirement, temporary PyPI name, worked examples footnote

## 0.1.1 (2026-04-04)

- Add: CI badge to README (GitHub Actions, Python 3.10 + 3.12)
- Add: ARCHITECTURE.md - pipeline overview, module table, extraction schema, how to add a language
- Add: SECURITY.md - threat model, mitigations, vulnerability reporting
- Add: `worked/` directory with eval reports (karpathy-repos 71.5x benchmark, httpx, mixed-corpus)
- Fix: pytest not found in CI - added explicit `pip install pytest` step
- Fix: README test count (163 → 212), language table, worked examples links
- Docs: README reframed as Claude Code skill; Karpathy problem → graphify answer framing

## 0.1.0 (2026-04-03)

Initial release.

- 13-language AST extraction via tree-sitter (Python, JS, TS, Go, Rust, Java, C, C++, Ruby, C#, Kotlin, Scala, PHP)
- Leiden community detection via graspologic with oversized community splitting
- SHA256 semantic cache - warm re-runs skip unchanged files
- MCP stdio server - `query_graph`, `get_node`, `get_neighbors`, `shortest_path`, `god_nodes`
- Memory feedback loop - Q&A results saved to `graphify-out/memory/`, extracted on `--update`
- Obsidian vault export with wikilinks, community tags, Canvas layout
- Security module - URL validation, safe fetch with size cap, path guards, label sanitisation
- `graphify install` CLI - copies skill to `~/.claude/skills/` and registers in `CLAUDE.md`
- Parallel subagent extraction for docs, papers, and images
