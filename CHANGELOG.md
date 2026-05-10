# Changelog

Full release notes with details on each version: [GitHub Releases](https://github.com/safishamsi/graphify/releases)

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
