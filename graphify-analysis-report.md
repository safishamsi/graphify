# Graphify 深度分析报告

> 分析日期：2026-04-19
> 项目版本：v0.4.23
> 分析者：Claude Code

---

## 执行摘要

**Graphify** 是一个 AI 编程助手技能，将任意文件夹（代码、文档、论文、图片、视频）转化为可查询的知识图谱。

### 核心价值
- **71.5x token 减少** - 在混合语料上，相比直接读取原始文件
- **跨会话持久化** - 知识图谱存储在 `graph.json`，可数周后查询
- **诚实审计追踪** - 每个关系标记为 EXTRACTED/INFERRED/AMBIGUOUS
- **跨文档发现** - 通过社区检测发现隐含关联

### 市场表现
- **PyPI 包名**: `graphifyy`（注意双 y）
- **总下载量**: 200k+
- **支持平台**: 14 个 AI 编程平台
- **开源协议**: GitHub: safishamsi/graphify

---

## 一、项目概览

### 1.1 基本信息

| 属性 | 详情 |
|------|------|
| **名称** | graphifyy (PyPI), graphify (CLI) |
| **版本** | v0.4.23 |
| **作者** | Safi Shamsi |
| **语言** | Python 3.10+ |
| **下载量** | 200k+ |
| **仓库** | github.com/safishamsi/graphify |

### 1.2 技术栈

```
核心依赖:
├── networkx          # 图引擎
├── tree-sitter       # AST 解析 (25+ 语言)
├── graspologic       # Leiden 社区检测 (python < 3.13)
└── faster-whisper    # 音频转录 (可选)

可选依赖:
├── mcp               # MCP 服务器支持
├── neo4j             # Neo4j 导出
├── pypdf/html2text   # PDF 处理
├── watchdog          # 文件监控
└── matplotlib        # SVG 导出
```

### 1.3 支持的 14 个平台

| 平台 | Hook 支持 | 技能触发 |
|------|----------|---------|
| Claude Code | PreToolUse Hook | `/graphify` |
| Codex | PreToolUse Hook | `$graphify` |
| OpenCode | tool.execute.before 插件 | `/graphify` |
| Cursor | alwaysApply 规则 | `/graphify` |
| Gemini CLI | BeforeTool Hook | `/graphify` |
| GitHub Copilot CLI | 无 | `/graphify` |
| VS Code Copilot Chat | 无 | `/graphify` |
| Aider | 无 | `/graphify` |
| OpenClaw | 无 | `/graphify` |
| Factory Droid | 无 | `/graphify` |
| Trae/Trae CN | 无 | `/graphify` |
| Hermes | 无 | `/graphify` |
| Kiro IDE/CLI | inclusion:always | `/graphify` |
| Google Antigravity | 规则文件 | `/graphify` |

---

## 二、核心问题与解决方案

### 2.1 解决的四大问题

#### 问题 1：AI 助手上下文爆炸
**痛点**: 大型代码库 + 文档 + 论文 → 每次查询都要读取全部文件，Token 消耗巨大

**解决**: 71.5x token 减少，通过图谱结构化查询替代全量读取

#### 问题 2：知识结构缺失
**痛点**: AI 只能逐个文件读取，无法理解整体架构和跨文件关联

**解决**: 知识图谱自动提取上帝节点、社区结构、惊喜连接

#### 问题 3：多模态内容无法统一
**痛点**: 代码、PDF、图片、视频、音频各自分离，难以建立跨模态关联

**解决**: 统一图谱，所有内容类型成为节点和边

#### 问题 4：AI 猜测无审计追踪
**痛点**: AI 经常"猜测"关系，用户无法知道哪些是事实

**解决**: 每个关系标记 EXTRACTED/INFERRED/AMBIGUOUS

### 2.2 技术架构

```
输入文件夹
    ↓
detect() → 文件分类与过滤
    ↓
extract() → 三遍提取策略
    ├── 第一遍: 代码文件 (tree-sitter AST, 0 LLM)
    ├── 第二遍: 音视频 (faster-whisper 本地, 0 LLM)
    └── 第三遍: 文档/论文/图片 (Claude 子代理并行)
    ↓
build_graph() → 图构建 (NetworkX)
    ↓
cluster() → Leiden 社区检测 (基于拓扑, 无嵌入)
    ↓
analyze() → 上帝节点、惊喜连接、建议问题
    ↓
report() → GRAPH_REPORT.md
    ↓
export() → 多格式导出
    ├── graph.html (交互式可视化)
    ├── graph.json (GraphRAG-ready)
    ├── graph.svg (静态矢量图)
    └── graph.graphml (Gephi/yEd)
```

### 2.3 核心模块职责

| 模块 | 函数 | 输入→输出 |
|------|------|----------|
| `detect.py` | `collect_files(root)` | 目录 → 过滤后文件列表 |
| `extract.py` | `extract(path)` | 文件路径 → {nodes, edges} |
| `build.py` | `build_graph(extractions)` | 提取列表 → nx.Graph |
| `cluster.py` | `cluster(G)` | 图 → 带 community 属性的图 |
| `analyze.py` | `analyze(G)` | 图 → 分析字典 |
| `report.py` | `render_report(G, analysis)` | 图 + 分析 → GRAPH_REPORT.md |
| `export.py` | `export(G, out_dir, ...)` | 图 → 多格式导出 |
| `security.py` | 验证辅助 | URL/路径/标签 → 验证或异常 |

---

## 三、LLM 需求分析

### 3.1 LLM 使用场景

| 内容类型 | 是否使用 LLM | 技术 |
|----------|-------------|------|
| 代码文件 | ❌ 不使用 | tree-sitter AST |
| 音视频 | ❌ 不使用 | faster-whisper 本地 |
| 文档 | ✅ 使用 | Claude 子代理并行提取 |
| 论文 (PDF) | ✅ 使用 | Claude + 引用挖掘 |
| 图片 | ✅ 使用 | Claude Vision |
| 转录文本 | ✅ 使用 | Claude 语义提取 |

### 3.2 LLM 具体任务

1. **语义提取**: 从文档/论文/图片提取概念和关系
2. **置信度标注**: 为每个关系标记 EXTRACTED/INFERRED/AMBIGUOUS
3. **跨文档关联**: 发现同 chunk 内的跨文件关系
4. **设计意图提取**: 提取设计原理和架构决策

### 3.3 LLM 调用策略

- **并行子代理**: 文件分块 (20-25 文件/chunk) → 多 Agent 并行
- **SHA256 缓存**: 只处理新/变更文件
- **增量更新**: 代码变更无 LLM，文档变更按比例

### 3.4 输出格式要求

```json
{
  "nodes": [
    {"id": "unique_id", "label": "名称", "source_file": "path", "source_location": "L42"}
  ],
  "edges": [
    {"source": "id_a", "target": "id_b", "relation": "uses", "confidence": "EXTRACTED"}
  ]
}
```

---

## 四、数据规模支持

### 4.1 硬性限制

| 限制类型 | 阈值 |
|----------|------|
| 单文本文件 | 10 MB |
| 单二进制下载 | 50 MB |
| 推荐词数 | < 2,000,000 |
| 推荐文件数 | < 200 |
| HTML 可视化 | < 5,000 节点 |

### 4.2 处理规模参考

```
文件数        处理方式
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
< 200         直接全量处理（推荐）
200-500       可能需要分批
500-1000      建议分目录处理
> 1000        必须分目录或使用 .graphifyignore
```

### 4.3 Chunk 策略

| 参数 | 值 |
|------|-----|
| Chunk 大小 | 20-25 文件 |
| 图片处理 | 每图独立 chunk |
| 估算时间 | ~45s / agent batch |

---

## 五、安全机制

### 5.1 内置安全检查

| 检查项 | 限制 |
|--------|------|
| URL 验证 | 仅 http/https，阻止私有 IP |
| 文件大小 | 文本 10MB，二进制 50MB |
| 路径验证 | 必须在 `graphify-out/` 内 |
| 标签清理 | 转义 HTML，限制 256 字符 |
| 敏感文件 | 自动跳过密码、密钥文件 |

### 5.2 置信度标签

| 标签 | 含义 |
|------|------|
| `EXTRACTED` | 源中明确声明 |
| `INFERRED` | 合理推断 |
| `AMBIGUOUS` | 不确定，需人工审查 |

---

## 六、使用指南

### 6.1 安装

```bash
# 基础安装
pip install graphifyy && graphify install

# 使用 pipx (推荐)
pipx install graphifyy && graphify install

# 带所有可选依赖
pip install "graphifyy[all]"
```

### 6.2 基础使用

```bash
# 构建知识图谱
/graphify .

# 输出结构
graphify-out/
├── graph.html          # 交互式可视化
├── GRAPH_REPORT.md     # 分析报告
├── graph.json          # 持久化图谱
└── cache/              # SHA256 缓存
```

### 6.3 排除文件

创建 `.graphifyignore`:
```
vendor/
node_modules/
dist/
*.generated.py
```

### 6.4 团队协作

**`.gitignore` 添加:**
```gitignore
# 提交图输出，忽略缓存
graphify-out/cache/
```

**工作流:**
1. 一人运行 `/graphify .` 并提交 `graphify-out/`
2. 其他人拉取后立即获得结构化认知
3. 安装 post-commit hook 自动重建

---

## 七、测试验证方案

### 7.1 本地验证

```bash
# 安装测试依赖
pip install -e ".[mcp,pdf,watch]" pytest

# 运行测试
python -m pytest tests/ -v

# 验证 CLI
graphify --help
graphify install
```

### 7.2 测试覆盖

- **26 个测试文件**，覆盖所有核心模块
- **25+ 种语言**的 AST 提取测试
- **CI/CD**: Python 3.10/3.12, Ubuntu

### 7.3 验证场景

| 场景 | 命令 | 验证内容 |
|------|------|----------|
| 小代码库 | `graphify tests/fixtures/` | Python 提取 |
| 多语言 | `graphify . --include` | 跨语言引用 |
| 增量更新 | 修改后 `graphify . --update` | 缓存机制 |
| HTML 导出 | 浏览器打开 `graph.html` | 可视化 |
| MCP 服务 | `python -m graphify.serve` | MCP 接口 |

---

## 八、总结与建议

### 8.1 核心优势

1. **降本**: 71.5x token 减少
2. **增效**: 结构化导航
3. **持久**: 跨会话 graph.json
4. **可信**: 审计追踪
5. **多模态**: 统一图谱
6. **智能**: 自动发现上帝节点和惊喜连接

### 8.2 使用建议

| 场景 | 建议 |
|------|------|
| 新代码库 | 先 `/graphify .` 了解架构 |
| 研究项目 | 代码+论文统一分析 |
| 团队协作 | 提交 graphify-out/ |
| 大型项目 | 分模块或使用 .graphifyignore |

### 8.3 快速开始

```bash
# 1. 安装
pip install graphifyy && graphify install

# 2. 分析项目
cd /your/project
graphify .

# 3. 查看结果
open graphify-out/graph.html
cat graphify-out/GRAPH_REPORT.md

# 4. 集成到 Claude Code
graphify claude install
```

---

## 附录

### A. 支持的文件类型

| 类型 | 扩展名 | 提取方式 |
|------|--------|----------|
| 代码 | .py, .ts, .js, .go, .rs 等 25+ 语言 | tree-sitter AST |
| 文档 | .md, .mdx, .html, .txt, .rst | Claude 语义提取 |
| 论文 | .pdf | pypdf + 引用挖掘 |
| 图片 | .png, .jpg, .jpeg, .gif, .webp, .svg | Claude Vision |
| 视频/音频 | .mp4, .mov, .webm, .mp3, .wav, .m4a | faster-whisper |

### B. 命令参考

```
graphify .                        # 完整流程
graphify . --update               # 增量更新
graphify . --watch                # 文件监控
graphify . --obsidian             # 导出 Obsidian vault
graphify . --wiki                 # 生成 wiki
graphify query "<question>"       # 图谱查询
graphify path "A" "B"             # 最短路径
graphify explain "concept"        # 概念解释
```

### C. 参考资料

- **GitHub**: github.com/safishamsi/graphify
- **PyPI**: pypi.org/project/graphifyy
- **文档**: README.md, ARCHITECTURE.md, SECURITY.md

---

*报告生成时间: 2026-04-19*
*工具: Claude Code + Graphify 自分析*
