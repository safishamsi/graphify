# graphify

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md) | [한국어](README.ko-KR.md)

[![CI](https://github.com/safishamsi/graphify/actions/workflows/ci.yml/badge.svg?branch=v4)](https://github.com/safishamsi/graphify/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/graphifyy)](https://pypi.org/project/graphifyy/)
[![Downloads](https://static.pepy.tech/badge/graphifyy)](https://pepy.tech/project/graphifyy)
[![Sponsor](https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors)](https://github.com/sponsors/safishamsi)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Safi%20Shamsi-0077B5?logo=linkedin)](https://www.linkedin.com/in/safi-shamsi)

**An AI coding assistant skill.** Type `/graphify` in Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro, or Google Antigravity - it reads your files, builds a knowledge graph, and gives you back structure you didn't know was there. Understand a codebase faster. Find the "why" behind architectural decisions.

Fully multimodal. Drop in code, PDFs, markdown, screenshots, diagrams, whiteboard photos, images in other languages, or video and audio files - graphify extracts concepts and relationships from all of it and connects them into one graph. Videos are transcribed with Whisper using a domain-aware prompt derived from your corpus. 25 languages supported via tree-sitter AST (Python, JS, TS, Go, Rust, Java, C, C++, Ruby, C#, Kotlin, Scala, PHP, Swift, Lua, Zig, PowerShell, Elixir, Objective-C, Julia, Verilog, SystemVerilog, Vue, Svelte, Dart).

> Andrej Karpathy keeps a `/raw` folder where he drops papers, tweets, screenshots, and notes. graphify is the answer to that problem - 71.5x fewer tokens per query vs reading the raw files, persistent across sessions, honest about what it found vs guessed.

```
/graphify .                        # works on any folder - your codebase, notes, papers, anything
```

```
graphify-out/
├── graph.html       interactive graph - open in any browser, click nodes, search, filter by community
├── GRAPH_REPORT.md  god nodes, surprising connections, suggested questions
├── graph.json       persistent graph - query weeks later without re-reading
└── cache/           SHA256 cache - re-runs only process changed files
```

Add a `.graphifyignore` file to exclude folders you don't want in the graph:

```
# .graphifyignore
vendor/
node_modules/
dist/
*.generated.py
```

Same syntax as `.gitignore`. You can keep a single `.graphifyignore` at your repo root — patterns work correctly even when graphify is run on a subfolder.

## How it works

graphify runs in three passes. First, a deterministic AST pass extracts structure from code files (classes, functions, imports, call graphs, docstrings, rationale comments) with no LLM needed. Second, video and audio files are transcribed locally with faster-whisper using a domain-aware prompt derived from corpus god nodes — transcripts are cached so re-runs are instant. Third, Claude subagents run in parallel over docs, papers, images, and transcripts to extract concepts, relationships, and design rationale. The results are merged into a NetworkX graph, clustered with Leiden community detection, and exported as interactive HTML, queryable JSON, and a plain-language audit report.

**Clustering is graph-topology-based — no embeddings.** Leiden finds communities by edge density. The semantic similarity edges that Claude extracts (`semantically_similar_to`, marked INFERRED) are already in the graph, so they influence community detection directly. The graph structure is the similarity signal — no separate embedding step or vector database needed.

Every relationship is tagged `EXTRACTED` (found directly in source), `INFERRED` (reasonable inference, with a confidence score), or `AMBIGUOUS` (flagged for review). You always know what was found vs guessed.

## Install

**Requires:** Python 3.10+ and one of: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com), [Gemini CLI](https://github.com/google-gemini/gemini-cli), [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli), [VS Code Copilot Chat](https://code.visualstudio.com/docs/copilot/overview), [Aider](https://aider.chat), [OpenClaw](https://openclaw.ai), [Factory Droid](https://factory.ai), [Trae](https://trae.ai), [Kiro](https://kiro.dev), Hermes, or [Google Antigravity](https://antigravity.google)

```bash
pip install graphifyy && graphify install

# or with pipx (keeps the CLI isolated from your project environments)
pipx install graphifyy && graphify install

# or with uvx (keeps the CLI isolated from your project environments)
uvx --from graphifyy graphify install --platform opencode 
```

> **Official package:** The PyPI package is named `graphifyy` (install with `pip install graphifyy`). Other packages named `graphify*` on PyPI are not affiliated with this project. The only official repository is [safishamsi/graphify](https://github.com/safishamsi/graphify). The CLI and skill command are still `graphify`.

> **`graphify: command not found`?** On Windows, pip user scripts land in `%APPDATA%\Python\PythonXY\Scripts` — add that to your PATH or use `python -m graphify` instead. On macOS with pipx, run `pipx ensurepath` then restart your terminal.

### Platform support

| Platform | Install command |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (auto-detected) or `graphify install --platform windows` |
| Codex | `graphify install --platform codex` |
| OpenCode | `graphify install --platform opencode` |
| GitHub Copilot CLI | `graphify install --platform copilot` |
| VS Code Copilot Chat | `graphify vscode install` |
| Aider | `graphify install --platform aider` |
| OpenClaw | `graphify install --platform claw` |
| Factory Droid | `graphify install --platform droid` |
| Trae | `graphify install --platform trae` |
| Trae CN | `graphify install --platform trae-cn` |
| Gemini CLI | `graphify install --platform gemini` |
| Hermes | `graphify install --platform hermes` |
| Kiro IDE/CLI | `graphify kiro install` |
| Cursor | `graphify cursor install` |
| Google Antigravity | `graphify antigravity install` |

Codex users also need `multi_agent = true` under `[features]` in `~/.codex/config.toml` for parallel extraction. Factory Droid uses the `Task` tool for parallel subagent dispatch. OpenClaw and Aider use sequential extraction (parallel agent support is still early on those platforms). Trae uses the Agent tool for parallel subagent dispatch and does **not** support PreToolUse hooks — AGENTS.md is the always-on mechanism. Codex supports PreToolUse hooks — `graphify codex install` installs one in `.codex/hooks.json` in addition to writing AGENTS.md.

Then open your AI coding assistant and type:

```
/graphify .
```

Note: Codex uses `$` instead of `/` for skill calling, so type `$graphify .` instead.

### Make your assistant always use the graph (recommended)

After building a graph, run this once in your project:

| Platform | Command |
|----------|---------|
| Claude Code | `graphify claude install` |
| Codex | `graphify codex install` |
| OpenCode | `graphify opencode install` |
| GitHub Copilot CLI | `graphify copilot install` |
| VS Code Copilot Chat | `graphify vscode install` |
| Aider | `graphify aider install` |
| OpenClaw | `graphify claw install` |
| Factory Droid | `graphify droid install` |
| Trae | `graphify trae install` |
| Trae CN | `graphify trae-cn install` |
| Cursor | `graphify cursor install` |
| Gemini CLI | `graphify gemini install` |
| Hermes | `graphify hermes install` |
| Kiro IDE/CLI | `graphify kiro install` |
| Google Antigravity | `graphify antigravity install` |

**Claude Code** does two things: writes a `CLAUDE.md` section telling Claude to read `graphify-out/GRAPH_REPORT.md` before answering architecture questions, and installs a **PreToolUse hook** (`settings.json`) that fires before every Glob and Grep call. If a knowledge graph exists, Claude sees: _"graphify: Knowledge graph exists. Read GRAPH_REPORT.md for god nodes and community structure before searching raw files."_ — so Claude navigates via the graph instead of grepping through every file.

**Codex** writes to `AGENTS.md` and also installs a **PreToolUse hook** in `.codex/hooks.json` that fires before every Bash tool call — same always-on mechanism as Claude Code.

**OpenCode** writes to `AGENTS.md` and also installs a **`tool.execute.before` plugin** (`.opencode/plugins/graphify.js` + `opencode.json` registration) that fires before bash tool calls and injects the graph reminder into tool output when the graph exists.

**Cursor** writes `.cursor/rules/graphify.mdc` with `alwaysApply: true` — Cursor includes it in every conversation automatically, no hook needed.

**Gemini CLI** copies the skill to `~/.gemini/skills/graphify/SKILL.md`, writes a `GEMINI.md` section, and installs a `BeforeTool` hook in `.gemini/settings.json` that fires before file-read tool calls — same always-on mechanism as Claude Code.

**Aider, OpenClaw, Factory Droid, Trae, and Hermes** write the same rules to `AGENTS.md` in your project root and copy the skill to the platform's global skill directory. These platforms don't support tool hooks, so AGENTS.md is the always-on mechanism.

**Kiro IDE/CLI** writes the skill to `.kiro/skills/graphify/SKILL.md` (invoked via `/graphify`) and a steering file to `.kiro/steering/graphify.md` with `inclusion: always` — Kiro injects this into every conversation automatically, no hook needed.

**Google Antigravity** writes `.agent/rules/graphify.md` (always-on rules) and `.agent/workflows/graphify.md` (registers `/graphify` as a slash command). No hook equivalent exists in Antigravity — rules are the always-on mechanism.

**GitHub Copilot CLI** copies the skill to `~/.copilot/skills/graphify/SKILL.md`. Run `graphify copilot install` to set it up.

**VS Code Copilot Chat** installs a Python-only skill (works on Windows PowerShell and macOS/Linux alike) and writes `.github/copilot-instructions.md` in your project root — VS Code reads this automatically every session, making graph context always-on without any hook mechanism. Run `graphify vscode install`. Note: this configures the chat panel in VS Code, not the Copilot CLI terminal tool.

Uninstall with the matching uninstall command (e.g. `graphify claude uninstall`).

**Always-on vs explicit trigger — what's the difference?**

The always-on hook surfaces `GRAPH_REPORT.md` — a one-page summary of god nodes, communities, and surprising connections. Your assistant reads this before searching files, so it navigates by structure instead of keyword matching. That covers most everyday questions.

`/graphify query`, `/graphify path`, and `/graphify explain` go deeper: they traverse the raw `graph.json` hop by hop, trace exact paths between nodes, and surface edge-level detail (relation type, confidence score, source location). Use them when you want a specific question answered from the graph rather than a general orientation.

Think of it this way: the always-on hook gives your assistant a map. The `/graphify` commands let it navigate the map precisely.

### Team workflows

`graphify-out/` is designed to be committed to git so every teammate starts with a fresh map.

**Recommended `.gitignore` additions:**
```
# commit graph outputs, ignore the extraction cache
graphify-out/cache/
```

**Shared setup:**
1. One person runs `/graphify .` to build the initial graph and commits `graphify-out/`.
2. Everyone else pulls — their assistant reads `GRAPH_REPORT.md` immediately with no extra steps.
3. Install the post-commit hook (`graphify hook install`) so the graph rebuilds automatically after code changes — no LLM calls needed for code-only updates.
4. For doc/paper changes, whoever edits the files runs `/graphify --update` to refresh semantic nodes.

**Excluding paths** — create `.graphifyignore` in your project root (same syntax as `.gitignore`). Files matching those patterns are skipped during detection and extraction.

## Using `graph.json` with an LLM

`graph.json` is not meant to be pasted into a prompt all at once. The useful
workflow is:

1. Start with `graphify-out/GRAPH_REPORT.md` for the high-level overview.
2. Use `graphify query` to pull a smaller subgraph for the specific question
   you want to answer.
3. Give that focused output to your assistant instead of dumping the full raw
   corpus.

For example, after running graphify on a project:

```bash
graphify query "show the auth flow" --graph graphify-out/graph.json
graphify query "what connects DigestAuth to Response?" --graph graphify-out/graph.json
```

The output includes node labels, edge types, confidence tags, source files, and
source locations. That makes it a good intermediate context block for an LLM:

```text
Use this graph query output to answer the question. Prefer the graph structure
over guessing, and cite the source files when possible.
```

If your assistant supports tool calling or MCP, use the graph directly instead
of pasting text. graphify can expose `graph.json` as an MCP server:

```bash
python -m graphify.serve graphify-out/graph.json
```

That gives the assistant structured graph access for repeated queries such as
`query_graph`, `get_node`, `get_neighbors`, and `shortest_path`.

> **WSL / Linux note:** Ubuntu ships `python3`, not `python`. Install into a project venv to avoid PEP 668 conflicts, and use the full venv path in your `.mcp.json`:
> ```bash
> python3 -m venv .venv && .venv/bin/pip install "graphifyy[mcp]"
> ```
> ```json
> { "mcpServers": { "graphify": { "type": "stdio", "command": ".venv/bin/python3", "args": ["-m", "graphify.serve", "graphify-out/graph.json"] } } }
> ```
> Also note: the PyPI package is `graphifyy` (double-y) — `pip install graphify` installs an unrelated package.

<details>
<summary>Manual install (curl)</summary>

```bash
mkdir -p ~/.claude/skills/graphify
curl -fsSL https://raw.githubusercontent.com/safishamsi/graphify/v4/graphify/skill.md \
  > ~/.claude/skills/graphify/SKILL.md
```

Add to `~/.claude/CLAUDE.md`:

```
- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, invoke the Skill tool with `skill: "graphify"` before doing anything else.
```

</details>

## Usage

```
/graphify                          # run on current directory
/graphify ./raw                    # run on a specific folder
/graphify ./raw --mode deep        # more aggressive INFERRED edge extraction
/graphify ./raw --update           # re-extract only changed files, merge into existing graph
/graphify ./raw --directed          # build directed graph (preserves edge direction: source→target)
/graphify ./raw --cluster-only     # rerun clustering on existing graph, no re-extraction
/graphify ./raw --no-viz           # skip HTML, just produce report + JSON
/graphify ./raw --obsidian                          # also generate Obsidian vault (opt-in)
/graphify ./raw --obsidian --obsidian-dir ~/vaults/myproject  # write vault to a specific directory

/graphify add https://arxiv.org/abs/1706.03762        # fetch a paper, save, update graph
/graphify add https://x.com/karpathy/status/...       # fetch a tweet
/graphify add <video-url>                              # download audio, transcribe, add to graph
/graphify add https://... --author "Name"             # tag the original author
/graphify add https://... --contributor "Name"        # tag who added it to the corpus

/graphify query "what connects attention to the optimizer?"
/graphify query "what connects attention to the optimizer?" --dfs   # trace a specific path
/graphify query "what connects attention to the optimizer?" --budget 1500  # cap at N tokens
/graphify path "DigestAuth" "Response"
/graphify explain "SwinTransformer"

/graphify ./raw --watch            # auto-sync graph as files change (code: instant, docs: notifies you)
/graphify ./raw --wiki             # build agent-crawlable wiki (index.md + article per community)
/graphify ./raw --svg              # export graph.svg
/graphify ./raw --graphml          # export graph.graphml (Gephi, yEd)
/graphify ./raw --neo4j            # generate cypher.txt for Neo4j
/graphify ./raw --neo4j-push bolt://localhost:7687    # push directly to a running Neo4j instance
/graphify ./raw --mcp              # start MCP stdio server

# git hooks - platform-agnostic, rebuild graph on commit and branch switch
graphify hook install
graphify hook uninstall
graphify hook status

# always-on assistant instructions - platform-specific
graphify claude install            # CLAUDE.md + PreToolUse hook (Claude Code)
graphify claude uninstall
graphify codex install             # AGENTS.md + PreToolUse hook in .codex/hooks.json (Codex)
graphify opencode install          # AGENTS.md + tool.execute.before plugin (OpenCode)
graphify cursor install            # .cursor/rules/graphify.mdc (Cursor)
graphify cursor uninstall
graphify gemini install            # GEMINI.md + BeforeTool hook (Gemini CLI)
graphify gemini uninstall
graphify copilot install           # skill file (GitHub Copilot CLI)
graphify copilot uninstall
graphify aider install             # AGENTS.md (Aider)
graphify aider uninstall
graphify claw install              # AGENTS.md (OpenClaw)
graphify droid install             # AGENTS.md (Factory Droid)
graphify trae install              # AGENTS.md (Trae)
graphify trae uninstall
graphify trae-cn install           # AGENTS.md (Trae CN)
graphify trae-cn uninstall
graphify hermes install             # AGENTS.md + ~/.hermes/skills/ (Hermes)
graphify hermes uninstall
graphify kiro install               # .kiro/skills/ + .kiro/steering/graphify.md (Kiro IDE/CLI)
graphify kiro uninstall
graphify antigravity install       # .agent/rules + .agent/workflows (Google Antigravity)
graphify antigravity uninstall

# query and navigate the graph directly from the terminal (no AI assistant needed)
graphify query "what connects attention to the optimizer?"
graphify query "show the auth flow" --dfs
graphify query "what is CfgNode?" --budget 500
graphify query "..." --graph path/to/graph.json
graphify path "DigestAuth" "Response"       # shortest path between two nodes
graphify explain "SwinTransformer"           # plain-language explanation of a node

# add content and update the graph from the terminal
graphify add https://arxiv.org/abs/1706.03762          # fetch paper, save to ./raw, update graph
graphify add https://... --author "Name" --contributor "Name"

# incremental update and maintenance
graphify watch ./src                         # auto-rebuild on code changes
graphify update ./src                        # re-extract code files, no LLM needed
graphify cluster-only ./my-project           # rerun clustering on existing graph.json
```

Works with any mix of file types:

| Type | Extensions | Extraction |
|------|-----------|------------|
| Code | `.py .ts .js .jsx .tsx .mjs .go .rs .java .c .cpp .rb .cs .kt .scala .php .swift .lua .zig .ps1 .ex .exs .m .mm .jl .vue .svelte` | AST via tree-sitter + call-graph (cross-file for all languages) + docstring/comment rationale |
| Docs | `.md .mdx .html .txt .rst` | Concepts + relationships + design rationale via Claude |
| Office | `.docx .xlsx` | Converted to markdown then extracted via Claude (requires `pip install graphifyy[office]`) |
| Papers | `.pdf` | Citation mining + concept extraction |
| Images | `.png .jpg .webp .gif` | Claude vision - screenshots, diagrams, any language |
| Video / Audio | `.mp4 .mov .mkv .webm .avi .m4v .mp3 .wav .m4a .ogg` | Transcribed locally with faster-whisper, transcript fed into Claude extraction (requires `pip install graphifyy[video]`) |
| YouTube / URLs | any video URL | Audio downloaded via yt-dlp, then same Whisper pipeline (requires `pip install graphifyy[video]`) |

## Video and audio corpus

Drop video or audio files into your corpus folder alongside your code and docs — graphify picks them up automatically:

```bash
pip install 'graphifyy[video]'   # one-time setup
/graphify ./my-corpus            # transcribes any video/audio files it finds
```

Add a YouTube video (or any public video URL) directly:

```bash
/graphify add <video-url>
```

yt-dlp downloads audio-only (fast, small), Whisper transcribes it locally, and the transcript is fed into the same extraction pipeline as your other docs. Transcripts are cached in `graphify-out/transcripts/` so re-runs skip already-transcribed files.

For better accuracy on technical content, use a larger model:

```bash
/graphify ./my-corpus --whisper-model medium
```

Audio never leaves your machine. All transcription runs locally.

## What you get

**God nodes** - highest-degree concepts (what everything connects through)

**Surprising connections** - ranked by composite score. Code-paper edges rank higher than code-code. Each result includes a plain-English why.

**Suggested questions** - 4-5 questions the graph is uniquely positioned to answer

**The "why"** - docstrings, inline comments (`# NOTE:`, `# IMPORTANT:`, `# HACK:`, `# WHY:`), and design rationale from docs are extracted as `rationale_for` nodes. Not just what the code does - why it was written that way.

**Confidence scores** - every INFERRED edge has a `confidence_score` (0.0-1.0). You know not just what was guessed but how confident the model was. EXTRACTED edges are always 1.0.

**Semantic similarity edges** - cross-file conceptual links with no structural connection. Two functions solving the same problem without calling each other, a class in code and a concept in a paper describing the same algorithm.

**Hyperedges** - group relationships connecting 3+ nodes that pairwise edges can't express. All classes implementing a shared protocol, all functions in an auth flow, all concepts from a paper section forming one idea.

**Token benchmark** - printed automatically after every run. On a mixed corpus (Karpathy repos + papers + images): **71.5x** fewer tokens per query vs reading raw files. The first run extracts and builds the graph (this costs tokens). Every subsequent query reads the compact graph instead of raw files — that's where the savings compound. The SHA256 cache means re-runs only re-process changed files.

**Auto-sync** (`--watch`) - run in a background terminal and the graph updates itself as your codebase changes. Code file saves trigger an instant rebuild (AST only, no LLM). Doc/image changes notify you to run `--update` for the LLM re-pass.

**Git hooks** (`graphify hook install`) - installs post-commit and post-checkout hooks. Graph rebuilds automatically after every commit and every branch switch. If a rebuild fails, the hook exits with a non-zero code so git surfaces the error instead of silently continuing. No background process needed.

**Wiki** (`--wiki`) - Wikipedia-style markdown articles per community and god node, with an `index.md` entry point. Point any agent at `index.md` and it can navigate the knowledge base by reading files instead of parsing JSON.

## Worked examples

| Corpus | Files | Reduction | Output |
|--------|-------|-----------|--------|
| Karpathy repos + 5 papers + 4 images | 52 | **71.5x** | [`worked/karpathy-repos/`](worked/karpathy-repos/) |
| graphify source + Transformer paper | 4 | **5.4x** | [`worked/mixed-corpus/`](worked/mixed-corpus/) |
| httpx (synthetic Python library) | 6 | ~1x | [`worked/httpx/`](worked/httpx/) |

Token reduction scales with corpus size. 6 files fits in a context window anyway, so graph value there is structural clarity, not compression. At 52 files (code + papers + images) you get 71x+. Each `worked/` folder has the raw input files and the actual output (`GRAPH_REPORT.md`, `graph.json`) so you can run it yourself and verify the numbers.

## Privacy

graphify sends file contents to your AI coding assistant's underlying model API for semantic extraction of docs, papers, and images — Anthropic (Claude Code), OpenAI (Codex), or whichever provider your platform uses. Code files are processed locally via tree-sitter AST — no file contents leave your machine for code. Video and audio files are transcribed locally with faster-whisper — audio never leaves your machine. No telemetry, usage tracking, or analytics of any kind. The only network calls are to your platform's model API during extraction, using your own API key.

## Tech stack

NetworkX + Leiden (graspologic) + tree-sitter + vis.js. Semantic extraction via Claude (Claude Code), GPT-4 (Codex), or whichever model your platform runs. Video transcription via faster-whisper + yt-dlp (optional, `pip install graphifyy[video]`). No Neo4j required, no server, runs entirely locally.

## Built on graphify — Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai) is the enterprise layer on top of graphify. Where graphify turns a folder of files into a knowledge graph, Penpax applies the same graph to your entire working life — continuously.

| | graphify | Penpax |
|---|---|---|
| Input | A folder of files | Browser history, meetings, emails, files, code — everything |
| Runs | On demand | Continuously in the background |
| Scope | A project | Your entire working life |
| Query | CLI / MCP / AI skill | Natural language, always on |
| Privacy | Local by default | Fully on-device, no cloud |

Built for lawyers, consultants, executives, doctors, researchers — anyone whose work lives across hundreds of conversations and documents they can never fully reconstruct.

**Free trial launching soon.** [Join the waitlist →](https://safishamsi.github.io/penpax.ai)

## What we are building next

graphify is the graph layer. Penpax is the always-on layer on top of it — an on-device digital twin that connects your meetings, browser history, files, emails, and code into one continuously updating knowledge graph. No cloud, no training on your data. [Join the waitlist.](https://safishamsi.github.io/penpax.ai)

## Star history

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)

<details>
<summary>Contributing</summary>

**Worked examples** are the most trust-building contribution. Run `/graphify` on a real corpus, save output to `worked/{slug}/`, write an honest `review.md` evaluating what the graph got right and wrong, submit a PR.

**Extraction bugs** - open an issue with the input file, the cache entry (`graphify-out/cache/`), and what was missed or invented.

See [ARCHITECTURE.md](ARCHITECTURE.md) for module responsibilities and how to add a language.

</details>
