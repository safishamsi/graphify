# graphify

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md) | [한국어](README.ko-KR.md)

[![CI](https://github.com/safishamsi/graphify/actions/workflows/ci.yml/badge.svg?branch=v3)](https://github.com/safishamsi/graphify/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/graphifyy)](https://pypi.org/project/graphifyy/)

**一个面向 AI 编码助手的技能。** 在 Claude Code、Codex、OpenCode、OpenClaw、Factory Droid、Trae 或 Qoder 中输入 `/graphify`，它会读取你的文件、构建知识图谱，并把原本不明显的结构关系还给你。更快理解代码库，找到架构决策背后的"为什么"。

完全多模态。你可以直接丢进去代码、PDF、Markdown、截图、流程图、白板照片，甚至其他语言的图片 —— graphify 会用 Claude vision 从这些内容中提取概念和关系，并把它们连接到同一张图里。

> Andrej Karpathy 会维护一个 `/raw` 文件夹，把论文、推文、截图和笔记都丢进去。graphify 就是在解决这类问题 —— 相比直接读取原始文件，每次查询的 token 消耗可降低 **71.5 倍**，结果还能跨会话持久保存，并且会明确区分哪些内容是实际发现的，哪些只是合理推断。

```
/graphify .                        # 可用于任意目录：代码库、笔记、论文都可以
```

```
graphify-out/
├── graph.html       可交互图谱：可点节点、搜索、按社区过滤
├── GRAPH_REPORT.md  God nodes、意外连接、建议提问
├── graph.json       持久化图谱：数周后仍可查询，无需重新读原始文件
└── cache/           SHA256 缓存：重复运行时只处理变更过的文件
```

## 工作原理

graphify 分两轮执行。第一轮是确定性的 AST 提取，对代码文件做结构分析（类、函数、导入、调用图、docstring、解释性注释），这一轮不需要 LLM。第二轮会并行调用 Claude 子代理处理文档、论文和图片，从中提取概念、关系和设计动机。最后把两边结果合并到一个 NetworkX 图里，用 Leiden 社区发现算法做聚类，并导出成可交互 HTML、可查询 JSON，以及一份人类可读的审计报告。

**聚类是基于图拓扑完成的，不依赖 embeddings。** Leiden 按边密度发现社区。Claude 抽取出的语义相似边（`semantically_similar_to`，标记为 `INFERRED`）本来就存在于图中，所以会直接影响社区划分。图结构本身就是相似性信号，不需要额外的 embedding 步骤，也不需要向量数据库。

每条关系都会被标记为 `EXTRACTED`（直接在源材料中找到）、`INFERRED`（合理推断，并附带置信度分数）或 `AMBIGUOUS`（有歧义，需要复核）。所以你始终知道哪些是实际发现的，哪些是模型猜出来的。

## 安装

**要求：** Python 3.10+，并且使用以下平台之一：[Claude Code](https://claude.ai/code)、[Codex](https://openai.com/codex)、[OpenCode](https://opencode.ai)、[OpenClaw](https://openclaw.ai)、[Factory Droid](https://factory.ai)、[Trae](https://trae.ai) 或 [Qoder](https://github.com/qoder-ai/qoder)

```bash
pip install graphifyy && graphify install
```

> PyPI 包当前暂时叫 `graphifyy`，因为 `graphify` 这个名字还在回收中。CLI 命令和 skill 命令仍然都是 `graphify`。

### 平台支持

| 平台 | 安装命令 |
|------|----------|
| Claude Code | `graphify install` |
| Codex | `graphify install --platform codex` |
| OpenCode | `graphify install --platform opencode` |
| OpenClaw | `graphify install --platform claw` |
| Factory Droid | `graphify install --platform droid` |
| Trae | `graphify install --platform trae` |
| Trae CN | `graphify install --platform trae-cn` |
| Qoder | `graphify install --platform qoder` |

Codex 用户还需要在 `~/.codex/config.toml` 的 `[features]` 下打开 `multi_agent = true`，这样才能并行提取。OpenClaw 目前的并行 agent 支持还比较早期，所以使用顺序提取。Trae 使用 Agent 工具进行并行子代理调度，**不支持** PreToolUse hook，因此 AGENTS.md 是其常驻机制。

然后打开你的 AI 编码助手，输入：

```
/graphify .
```

### 让助手始终优先使用图谱（推荐）

图构建完成后，在项目里运行一次：

| 平台 | 命令 |
|------|------|
| Claude Code | `graphify claude install` |
| Codex | `graphify codex install` |
| OpenCode | `graphify opencode install` |
| OpenClaw | `graphify claw install` |
| Factory Droid | `graphify droid install` |
| Trae | `graphify trae install` |
| Trae CN | `graphify trae-cn install` |
| Qoder | `graphify qoder install` |

**Claude Code** 会做两件事：
1. 在 `CLAUDE.md` 中写入一段规则，告诉 Claude 在回答架构问题前先读 `graphify-out/GRAPH_REPORT.md`
2. 安装一个 **PreToolUse hook**（写入 `settings.json`），在每次 `Glob` 和 `Grep` 前触发

如果知识图谱存在，Claude 会先看到：_"graphify: Knowledge graph exists. Read graphify-out/GRAPH_REPORT.md for god nodes and community structure before searching raw files."_ —— 这样 Claude 会优先按图谱导航，而不是一上来就 grep 整个项目。

**Codex、OpenCode、OpenClaw、Factory Droid、Trae** 会把同样的规则写进项目根目录的 `AGENTS.md`。这些平台没有 PreToolUse hook，所以 `AGENTS.md` 是它们的常驻机制。

**Qoder** 会向 `.qoder/rules/graphify.md` 写入规则（Always Apply 类型），并在 `.qoder/settings.json` 中注册 PreToolUse hook。两者都指示 Qoder 在回答代码库问题前先检查图谱。当 `graphify-out/graph.json` 存在时，hook 会在每次工具调用前自动触发。

卸载时使用对应平台的 uninstall 命令即可（例如 `graphify claude uninstall`）。

**常驻模式和显式触发有什么区别？**

常驻 hook 会优先暴露 `GRAPH_REPORT.md` —— 这是一页式总结，包含 god nodes、社区结构和意外连接。你的助手在搜索文件前会先读它，因此会按结构导航，而不是按关键字乱搜。这已经能覆盖大部分日常问题。

`/graphify query`、`/graphify path` 和 `/graphify explain` 会更深入：它们会逐跳遍历底层 `graph.json`，追踪节点之间的精确路径，并展示边级别细节（关系类型、置信度、源位置）。当你想从图谱里精确回答某个问题，而不仅仅是获得整体感知时，就该用这些命令。

可以这样理解：常驻 hook 是先给助手一张地图，`/graphify` 这几个命令则是让它沿着地图精确导航。

<details>
<summary>手动安装（curl）</summary>

```bash
mkdir -p ~/.claude/skills/graphify
curl -fsSL https://raw.githubusercontent.com/safishamsi/graphify/v3/graphify/skill.md \
  > ~/.claude/skills/graphify/SKILL.md
```

把下面内容加到 `~/.claude/CLAUDE.md`：

```
- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, invoke the Skill tool with `skill: "graphify"` before doing anything else.
```

</details>

## 用法

```
/graphify                          # 对当前目录运行
/graphify ./raw                    # 对指定目录运行
/graphify ./raw --mode deep        # 更激进地抽取 INFERRED 边
/graphify ./raw --update           # 只重新提取变更文件，并合并到已有图谱
/graphify ./raw --cluster-only     # 只重新聚类已有图谱，不重新提取
/graphify ./raw --no-viz           # 跳过 HTML，只生成 report + JSON
/graphify ./raw --obsidian         # 额外生成 Obsidian vault（可选）

/graphify add https://arxiv.org/abs/1706.03762        # 拉取论文、保存并更新图谱
/graphify add https://x.com/karpathy/status/...       # 拉取推文
/graphify add https://... --author "Name"             # 标记原作者
/graphify add https://... --contributor "Name"        # 标记是谁把它加入语料库的

/graphify query "what connects attention to the optimizer?"
/graphify query "what connects attention to the optimizer?" --dfs   # 追踪一条具体路径
/graphify query "what connects attention to the optimizer?" --budget 1500  # 把预算限制在 N tokens
/graphify path "DigestAuth" "Response"
/graphify explain "SwinTransformer"

/graphify ./raw --watch            # 文件变更时自动同步图谱（代码：立即更新；文档：提醒你）
/graphify ./raw --wiki             # 构建可供 agent 抓取的 wiki（index.md + 每个 community 一篇文章）
/graphify ./raw --svg              # 导出 graph.svg
/graphify ./raw --graphml          # 导出 graph.graphml（Gephi、yEd）
/graphify ./raw --neo4j            # 生成给 Neo4j 用的 cypher.txt
/graphify ./raw --neo4j-push bolt://localhost:7687    # 直接推送到运行中的 Neo4j
/graphify ./raw --mcp              # 启动 MCP stdio server

# git hooks - 跨平台，在 commit 和切分支后重建图谱
graphify hook install
graphify hook uninstall
graphify hook status

# 常驻助手规则 - 按平台区分
graphify claude install            # CLAUDE.md + PreToolUse hook（Claude Code）
graphify claude uninstall
graphify codex install             # AGENTS.md（Codex）
graphify opencode install          # AGENTS.md（OpenCode）
graphify claw install              # AGENTS.md（OpenClaw）
graphify droid install             # AGENTS.md（Factory Droid）
graphify trae install              # AGENTS.md（Trae）
graphify trae uninstall
graphify trae-cn install           # AGENTS.md（Trae CN）
graphify trae-cn uninstall
```

支持混合文件类型：

| 类型 | 扩展名 | 提取方式 |
|------|--------|----------|
| 代码 | `.py .ts .js .go .rs .java .c .cpp .rb .cs .kt .scala .php` | tree-sitter AST + 调用图 + docstring / 注释中的 rationale |
| 文档 | `.md .txt .rst` | 通过 Claude 提取概念、关系和设计动机 |
| 论文 | `.pdf` | 引文挖掘 + 概念提取 |
| 图片 | `.png .jpg .webp .gif` | Claude vision —— 截图、图表、任意语言都可以 |

## 你会得到什么

**God nodes** —— 度最高的概念节点（整个系统最容易汇聚到的地方）

**意外连接** —— 按综合得分排序。代码-论文之间的边会比代码-代码边权重更高。每条结果都会附带一段人话解释。

**建议提问** —— 图谱特别擅长回答的 4 到 5 个问题。

**“为什么”** —— docstring、行内注释（`# NOTE:`、`# IMPORTANT:`、`# HACK:`、`# WHY:`）以及文档里的设计动机都会被抽取成 `rationale_for` 节点。不只是知道代码“做了什么”，还能知道“为什么要这么写”。

**置信度分数** —— 每条 `INFERRED` 边都有 `confidence_score`（0.0-1.0）。你不只知道哪些是猜出来的，还知道模型对这个猜测有多有把握。`EXTRACTED` 边恒为 1.0。

**语义相似边** —— 跨文件的概念连接，即使结构上没有直接依赖也能建立关联。比如两个函数做的是同一类问题但彼此没有调用，或者某个代码类和某篇论文里的算法概念本质相同。

**超边（Hyperedges）** —— 用来表达 3 个以上节点的群组关系，这是普通两两边表达不出来的。比如：一组类共同实现一个协议、认证链路里的一组函数、同一篇论文某一节里的多个概念共同组成一个想法。

**Token 基准** —— 每次运行后都会自动打印。对混合语料（Karpathy 的仓库 + 论文 + 图片），每次查询的 token 消耗可以比直接读原文件少 **71.5 倍**。第一次运行需要先提取并建图，这一步会花 token；后续查询直接读取压缩后的图谱，节省会越来越明显。SHA256 缓存保证重复运行时只重新处理变更文件。

**自动同步**（`--watch`）—— 在后台终端里跑着，代码库一变化，图谱就会跟着更新。代码文件保存会立刻触发重建（只走 AST，不用 LLM）；文档/图片变更则会提醒你跑 `--update` 进行 LLM 再提取。

**Git hooks**（`graphify hook install`）—— 安装 `post-commit` 和 `post-checkout` hook。每次 commit 后、每次切分支后都会自动重建图谱，不需要额外开一个后台进程。

**Wiki**（`--wiki`）—— 为每个 community 和 god node 生成类似维基百科的 Markdown 文章，并提供 `index.md` 作为入口。任何 agent 只要读 `index.md`，就能通过普通文件导航整个知识库，而不必直接解析 JSON。

## Worked examples

| 语料 | 文件数 | 压缩比 | 输出 |
|------|--------|--------|------|
| Karpathy 的仓库 + 5 篇论文 + 4 张图片 | 52 | **71.5x** | [`worked/karpathy-repos/`](worked/karpathy-repos/) |
| graphify 源码 + Transformer 论文 | 4 | **5.4x** | [`worked/mixed-corpus/`](worked/mixed-corpus/) |
| httpx（合成 Python 库） | 6 | ~1x | [`worked/httpx/`](worked/httpx/) |

Token 压缩效果会随着语料规模增大而更明显。6 个文件本来就塞得进上下文窗口，所以 graphify 在这种场景里的价值更多是结构清晰度，而不是 token 压缩。到了 52 个文件（代码 + 论文 + 图片）这种规模，就能做到 71x+。每个 `worked/` 目录里都带了原始输入和真实输出（`GRAPH_REPORT.md`、`graph.json`），你可以自己跑一遍核对数字。

## 隐私

graphify 会把文档、论文和图片的内容发送给你所用 AI 编码助手背后的模型 API 来做语义提取 —— 可能是 Anthropic（Claude Code）、OpenAI（Codex），或者你当前平台使用的其他提供方。代码文件则完全在本地通过 tree-sitter AST 处理，不会把代码内容发出去。项目本身没有任何遥测、使用跟踪或分析。唯一的网络请求就是语义提取阶段调用你平台自己的模型 API，使用的也是你自己的 API key。

## 技术栈

NetworkX + Leiden（graspologic）+ tree-sitter + vis.js。语义提取由 Claude（Claude Code）、GPT-4（Codex）或你当前平台所运行的模型完成。不需要 Neo4j，不需要 server，整体是纯本地运行。

<details>
<summary>贡献</summary>

**Worked examples** 是最能建立信任的贡献方式。对一个真实语料跑 `/graphify`，把输出保存到 `worked/{slug}/`，再写一份诚实的 `review.md`，评价图谱哪些地方做得对、哪些地方做得不对，然后提交 PR。

**提取 bug** —— 提 issue 时请附上输入文件、对应的缓存项（`graphify-out/cache/`）以及它漏提取或瞎编了什么。

模块职责和新增语言的方法见 [ARCHITECTURE.md](ARCHITECTURE.md)。

</details>
