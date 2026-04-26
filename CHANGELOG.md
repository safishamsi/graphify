# Changelog

Full release notes with details on each version: [GitHub Releases](https://github.com/safishamsi/graphify/releases)

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
