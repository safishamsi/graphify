# graphify

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md) | [한국어](README.ko-KR.md)

[![CI](https://github.com/safishamsi/graphify/actions/workflows/ci.yml/badge.svg?branch=v3)](https://github.com/safishamsi/graphify/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/graphifyy)](https://pypi.org/project/graphifyy/)
[![Sponsor](https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors)](https://github.com/sponsors/safishamsi)

**AI 코딩 어시스턴트를 위한 스킬.** Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, Aider, OpenClaw, Factory Droid, 또는 Trae에서 `/graphify`를 입력하면 파일을 읽고 지식 그래프를 구축하여, 미처 몰랐던 구조를 보여줍니다. 코드베이스를 더 빠르게 이해하고, 아키텍처 결정의 "이유"를 찾아보세요.

완전한 멀티모달 지원. 코드, PDF, 마크다운, 스크린샷, 다이어그램, 화이트보드 사진, 심지어 다른 언어로 된 이미지까지 — graphify는 Claude Vision을 사용하여 이 모든 것에서 개념과 관계를 추출하고 하나의 그래프로 연결합니다. tree-sitter AST를 통해 20개 언어를 지원합니다(Python, JS, TS, Go, Rust, Java, C, C++, Ruby, C#, Kotlin, Scala, PHP, Swift, Lua, Zig, PowerShell, Elixir, Objective-C, Julia).

> Andrej Karpathy는 논문, 트윗, 스크린샷, 메모를 모아두는 `/raw` 폴더를 관리합니다. graphify는 바로 그 문제에 대한 답입니다 — 원본 파일을 직접 읽는 것 대비 쿼리당 토큰 소비가 71.5배 적고, 세션 간에 영속적이며, 발견한 것과 추측한 것을 정직하게 구분합니다.

```
/graphify .                        # 어떤 폴더든 동작 - 코드베이스, 노트, 논문, 무엇이든
```

```
graphify-out/
├── graph.html       인터랙티브 그래프 - 노드 클릭, 검색, 커뮤니티별 필터
├── GRAPH_REPORT.md  갓 노드, 의외의 연결, 추천 질문
├── graph.json       영속 그래프 - 몇 주 후에도 재읽기 없이 쿼리 가능
└── cache/           SHA256 캐시 - 재실행 시 변경된 파일만 처리
```

그래프에 포함하지 않을 폴더를 제외하려면 `.graphifyignore` 파일을 추가하세요:

```
# .graphifyignore
vendor/
node_modules/
dist/
*.generated.py
```

`.gitignore`와 동일한 문법입니다. 패턴은 graphify를 실행한 폴더 기준의 상대 경로에 대해 매칭됩니다.

## 동작 원리

graphify는 두 번의 패스로 실행됩니다. 첫 번째는 결정론적 AST 패스로, 코드 파일에서 구조(클래스, 함수, 임포트, 콜 그래프, docstring, 근거 주석)를 LLM 없이 추출합니다. 두 번째는 Claude 서브에이전트가 문서, 논문, 이미지에 대해 병렬로 실행되어 개념, 관계, 설계 근거를 추출합니다. 결과는 NetworkX 그래프로 병합되고, Leiden 커뮤니티 탐지로 클러스터링되며, 인터랙티브 HTML, 쿼리 가능한 JSON, 그리고 일반 언어 감사 보고서로 내보내집니다.

**클러스터링은 그래프 토폴로지 기반 — 임베딩을 사용하지 않습니다.** Leiden은 엣지 밀도를 기반으로 커뮤니티를 찾습니다. Claude가 추출하는 의미적 유사성 엣지(`semantically_similar_to`, INFERRED로 표시)는 이미 그래프에 포함되어 있으므로 커뮤니티 탐지에 직접 영향을 줍니다. 그래프 구조 자체가 유사성 신호이며 — 별도의 임베딩 단계나 벡터 데이터베이스가 필요하지 않습니다.

모든 관계는 `EXTRACTED`(소스에서 직접 발견), `INFERRED`(합리적 추론, 신뢰도 점수 포함), `AMBIGUOUS`(리뷰 필요 표시) 중 하나로 태깅됩니다. 무엇이 발견된 것이고 무엇이 추측된 것인지 항상 알 수 있습니다.

## 설치

**필수 요구사항:** Python 3.10+ 및 다음 중 하나: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com), [Gemini CLI](https://github.com/google-gemini/gemini-cli), [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli), [Aider](https://aider.chat), [OpenClaw](https://openclaw.ai), [Factory Droid](https://factory.ai), 또는 [Trae](https://trae.ai)

```bash
pip install graphifyy && graphify install
```

> PyPI 패키지는 `graphify` 이름을 되찾는 동안 임시로 `graphifyy`로 명명되어 있습니다. CLI와 스킬 명령은 여전히 `graphify`입니다.

### 플랫폼 지원

| 플랫폼 | 설치 명령 |
|--------|-----------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (자동 감지) 또는 `graphify install --platform windows` |
| Codex | `graphify install --platform codex` |
| OpenCode | `graphify install --platform opencode` |
| GitHub Copilot CLI | `graphify install --platform copilot` |
| Aider | `graphify install --platform aider` |
| OpenClaw | `graphify install --platform claw` |
| Factory Droid | `graphify install --platform droid` |
| Trae | `graphify install --platform trae` |
| Trae CN | `graphify install --platform trae-cn` |
| Gemini CLI | `graphify install --platform gemini` |
| Cursor | `graphify cursor install` |

Codex 사용자는 병렬 추출을 위해 `~/.codex/config.toml`의 `[features]` 아래에 `multi_agent = true`도 필요합니다. Factory Droid는 병렬 서브에이전트 디스패치에 `Task` 도구를 사용합니다. OpenClaw과 Aider는 순차 추출을 사용합니다(해당 플랫폼들의 병렬 에이전트 지원은 아직 초기 단계입니다). Trae는 병렬 서브에이전트 디스패치에 Agent 도구를 사용하며 PreToolUse 훅을 **지원하지 않습니다** — AGENTS.md가 상시 작동 메커니즘입니다.

그런 다음 AI 코딩 어시스턴트를 열고 입력하세요:

```
/graphify .
```

참고: Codex는 스킬 호출에 `/` 대신 `$`를 사용하므로 `$graphify .`라고 입력하세요.

### 어시스턴트가 항상 그래프를 사용하도록 설정 (권장)

그래프를 빌드한 후, 프로젝트에서 한 번만 실행하세요:

| 플랫폼 | 명령 |
|--------|------|
| Claude Code | `graphify claude install` |
| Codex | `graphify codex install` |
| OpenCode | `graphify opencode install` |
| GitHub Copilot CLI | `graphify copilot install` |
| Aider | `graphify aider install` |
| OpenClaw | `graphify claw install` |
| Factory Droid | `graphify droid install` |
| Trae | `graphify trae install` |
| Trae CN | `graphify trae-cn install` |
| Cursor | `graphify cursor install` |
| Gemini CLI | `graphify gemini install` |

**Claude Code**는 두 가지를 수행합니다: 아키텍처 질문에 답하기 전에 `graphify-out/GRAPH_REPORT.md`를 읽도록 Claude에게 지시하는 `CLAUDE.md` 섹션을 작성하고, 모든 Glob 및 Grep 호출 전에 실행되는 **PreToolUse 훅**(`settings.json`)을 설치합니다. 지식 그래프가 존재하면 Claude는 다음 메시지를 보게 됩니다: _"graphify: Knowledge graph exists. Read GRAPH_REPORT.md for god nodes and community structure before searching raw files."_ — 이를 통해 Claude는 모든 파일을 grep하는 대신 그래프를 통해 탐색합니다.

**Codex**는 `AGENTS.md`에 작성하고 Bash 도구 호출 전에 실행되는 **PreToolUse 훅**을 `.codex/hooks.json`에 설치합니다 — Claude Code와 동일한 상시 작동 메커니즘입니다.

**OpenCode**는 `AGENTS.md`에 작성하고 bash 도구 호출 전에 실행되는 **`tool.execute.before` 플러그인**(`.opencode/plugins/graphify.js` + `opencode.json` 등록)을 설치합니다 — 그래프가 존재할 때 도구 출력에 그래프 리마인더를 삽입합니다.

**Cursor**는 `alwaysApply: true`로 설정된 `.cursor/rules/graphify.mdc`를 작성합니다 — Cursor가 모든 대화에 자동으로 포함하므로 훅이 필요 없습니다.

**Gemini CLI**는 스킬을 `~/.gemini/skills/graphify/SKILL.md`로 복사하고, `GEMINI.md` 섹션을 작성하며, 파일 읽기 도구 호출 전에 실행되는 `BeforeTool` 훅을 `.gemini/settings.json`에 설치합니다 — Claude Code와 동일한 상시 작동 메커니즘입니다.

**Aider, OpenClaw, Factory Droid, Trae**는 프로젝트 루트의 `AGENTS.md`에 동일한 규칙을 작성합니다. 이 플랫폼들은 도구 훅을 지원하지 않으므로 AGENTS.md가 상시 작동 메커니즘입니다.

**GitHub Copilot CLI**는 스킬을 `~/.copilot/skills/graphify/SKILL.md`로 복사합니다. `graphify copilot install`을 실행하여 설정하세요.

제거는 대응하는 uninstall 명령으로 수행합니다(예: `graphify claude uninstall`).

**상시 작동 vs 명시적 트리거 — 차이점은?**

상시 작동 훅은 `GRAPH_REPORT.md`를 노출합니다 — 갓 노드, 커뮤니티, 의외의 연결을 한 페이지로 요약한 것입니다. 어시스턴트는 파일 검색 전에 이것을 읽으므로 키워드 매칭이 아닌 구조 기반으로 탐색합니다. 이것만으로 대부분의 일상적인 질문을 처리할 수 있습니다.

`/graphify query`, `/graphify path`, `/graphify explain`은 더 깊이 들어갑니다: 원시 `graph.json`을 홉 단위로 순회하고, 노드 간의 정확한 경로를 추적하며, 엣지 수준의 세부 정보(관계 유형, 신뢰도 점수, 소스 위치)를 보여줍니다. 일반적인 오리엔테이션이 아닌 그래프에서 특정 질문에 답하고 싶을 때 사용하세요.

이렇게 생각하면 됩니다: 상시 작동 훅은 어시스턴트에게 지도를 주고, `/graphify` 명령은 그 지도를 정확하게 탐색하게 합니다.

## `graph.json`을 LLM과 함께 사용하기

`graph.json`은 프롬프트에 한 번에 전부 붙여넣기 위한 것이 아닙니다. 유용한 워크플로우는 다음과 같습니다:

1. `graphify-out/GRAPH_REPORT.md`로 높은 수준의 개요를 파악합니다.
2. `graphify query`를 사용하여 답하려는 특정 질문에 대한 더 작은 서브그래프를 가져옵니다.
3. 전체 원시 코퍼스 대신 그 집중된 결과를 어시스턴트에게 제공합니다.

예를 들어, 프로젝트에서 graphify를 실행한 후:

```bash
graphify query "show the auth flow" --graph graphify-out/graph.json
graphify query "what connects DigestAuth to Response?" --graph graphify-out/graph.json
```

출력에는 노드 레이블, 엣지 유형, 신뢰도 태그, 소스 파일, 소스 위치가 포함됩니다. 이는 LLM을 위한 좋은 중간 컨텍스트 블록이 됩니다:

```text
이 그래프 쿼리 결과를 사용하여 질문에 답하세요. 추측보다 그래프 구조를 우선하고,
가능한 경우 소스 파일을 인용하세요.
```

어시스턴트가 도구 호출이나 MCP를 지원하는 경우, 텍스트를 붙여넣는 대신 그래프를 직접 사용하세요. graphify는 `graph.json`을 MCP 서버로 노출할 수 있습니다:

```bash
python -m graphify.serve graphify-out/graph.json
```

이를 통해 어시스턴트가 `query_graph`, `get_node`, `get_neighbors`, `shortest_path` 같은 반복 쿼리에 구조화된 그래프 접근을 할 수 있습니다.

<details>
<summary>수동 설치 (curl)</summary>

```bash
mkdir -p ~/.claude/skills/graphify
curl -fsSL https://raw.githubusercontent.com/safishamsi/graphify/v3/graphify/skill.md \
  > ~/.claude/skills/graphify/SKILL.md
```

`~/.claude/CLAUDE.md`에 추가:

```
- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, invoke the Skill tool with `skill: "graphify"` before doing anything else.
```

</details>

## 사용법

```
/graphify                          # 현재 디렉토리에서 실행
/graphify ./raw                    # 특정 폴더에서 실행
/graphify ./raw --mode deep        # 더 적극적인 INFERRED 엣지 추출
/graphify ./raw --update           # 변경된 파일만 재추출하여 기존 그래프에 병합
/graphify ./raw --cluster-only     # 기존 그래프의 클러스터링만 재실행, 재추출 없음
/graphify ./raw --no-viz           # HTML 건너뛰기, 보고서 + JSON만 생성
/graphify ./raw --obsidian                          # Obsidian 볼트도 생성 (옵트인)
/graphify ./raw --obsidian --obsidian-dir ~/vaults/myproject  # 볼트를 특정 디렉토리에 생성

/graphify add https://arxiv.org/abs/1706.03762        # 논문 가져오기, 저장, 그래프 업데이트
/graphify add https://x.com/karpathy/status/...       # 트윗 가져오기
/graphify add https://... --author "Name"             # 원저자 태그
/graphify add https://... --contributor "Name"        # 코퍼스에 추가한 사람 태그

/graphify query "어텐션과 옵티마이저를 연결하는 것은?"
/graphify query "어텐션과 옵티마이저를 연결하는 것은?" --dfs   # 특정 경로 추적
/graphify query "어텐션과 옵티마이저를 연결하는 것은?" --budget 1500  # N 토큰으로 제한
/graphify path "DigestAuth" "Response"
/graphify explain "SwinTransformer"

/graphify ./raw --watch            # 파일 변경 시 그래프 자동 동기화 (코드: 즉시, 문서: 알림)
/graphify ./raw --wiki             # 에이전트가 크롤 가능한 위키 빌드 (index.md + 커뮤니티별 문서)
/graphify ./raw --svg              # graph.svg 내보내기
/graphify ./raw --graphml          # graph.graphml 내보내기 (Gephi, yEd)
/graphify ./raw --neo4j            # Neo4j용 cypher.txt 생성
/graphify ./raw --neo4j-push bolt://localhost:7687    # 실행 중인 Neo4j 인스턴스에 직접 푸시
/graphify ./raw --mcp              # MCP stdio 서버 시작

# git 훅 - 플랫폼 무관, 커밋 및 브랜치 전환 시 그래프 재빌드
graphify hook install
graphify hook uninstall
graphify hook status

# 상시 작동 어시스턴트 지시 - 플랫폼별
graphify claude install            # CLAUDE.md + PreToolUse 훅 (Claude Code)
graphify claude uninstall
graphify codex install             # AGENTS.md (Codex)
graphify opencode install          # AGENTS.md + tool.execute.before 플러그인 (OpenCode)
graphify copilot install           # 스킬 파일 (GitHub Copilot CLI)
graphify copilot uninstall
graphify aider install             # AGENTS.md (Aider)
graphify aider uninstall
graphify claw install              # AGENTS.md (OpenClaw)
graphify droid install             # AGENTS.md (Factory Droid)
graphify trae install              # AGENTS.md (Trae)
graphify trae uninstall
graphify trae-cn install           # AGENTS.md (Trae CN)
graphify trae-cn uninstall
graphify cursor install            # .cursor/rules/graphify.mdc (Cursor)
graphify cursor uninstall
graphify gemini install            # GEMINI.md + BeforeTool 훅 (Gemini CLI)
graphify gemini uninstall

# 터미널에서 직접 그래프 쿼리 (AI 어시스턴트 불필요)
graphify query "어텐션과 옵티마이저를 연결하는 것은?"
graphify query "인증 흐름 보기" --dfs
graphify query "CfgNode이 뭐지?" --budget 500
graphify query "..." --graph path/to/graph.json
```

다양한 파일 유형의 조합과 함께 동작합니다:

| 유형 | 확장자 | 추출 방식 |
|------|--------|-----------|
| 코드 | `.py .ts .js .jsx .tsx .go .rs .java .c .cpp .rb .cs .kt .scala .php .swift .lua .zig .ps1 .ex .exs .m .mm .jl` | tree-sitter AST + 콜 그래프 + docstring/주석 근거 |
| 문서 | `.md .txt .rst` | Claude를 통한 개념 + 관계 + 설계 근거 |
| 오피스 | `.docx .xlsx` | 마크다운으로 변환 후 Claude를 통해 추출 (`pip install graphifyy[office]` 필요) |
| 논문 | `.pdf` | 인용 마이닝 + 개념 추출 |
| 이미지 | `.png .jpg .webp .gif` | Claude Vision - 스크린샷, 다이어그램, 모든 언어 |

## 결과물

**갓 노드** - 최고 차수의 개념 (모든 것이 연결되는 허브)

**의외의 연결** - 복합 점수로 순위 지정. 코드-논문 엣지는 코드-코드보다 높게 순위됩니다. 각 결과에는 쉬운 설명이 포함됩니다.

**추천 질문** - 그래프가 고유하게 답할 수 있는 4~5개의 질문

**"이유"** - docstring, 인라인 주석(`# NOTE:`, `# IMPORTANT:`, `# HACK:`, `# WHY:`), 문서의 설계 근거가 `rationale_for` 노드로 추출됩니다. 코드가 무엇을 하는지뿐만 아니라 — 왜 그렇게 작성되었는지.

**신뢰도 점수** - 모든 INFERRED 엣지에는 `confidence_score`(0.0~1.0)가 있습니다. 무엇이 추측되었는지뿐 아니라 모델이 얼마나 확신했는지도 알 수 있습니다. EXTRACTED 엣지는 항상 1.0입니다.

**의미적 유사성 엣지** - 구조적 연결 없는 파일 간 개념 링크. 서로를 호출하지 않으면서 같은 문제를 해결하는 두 함수, 코드의 클래스와 같은 알고리즘을 설명하는 논문의 개념 등.

**하이퍼엣지** - 쌍별 엣지로는 표현할 수 없는 3개 이상 노드의 그룹 관계. 공유 프로토콜을 구현하는 모든 클래스, 인증 흐름의 모든 함수, 논문 섹션에서 하나의 아이디어를 구성하는 모든 개념 등.

**토큰 벤치마크** - 매 실행 후 자동으로 출력됩니다. 혼합 코퍼스(Karpathy 리포지토리 + 논문 + 이미지)에서: 원본 파일 대비 쿼리당 **71.5배** 적은 토큰. 첫 실행은 추출과 그래프 빌드를 수행합니다(토큰이 소비됩니다). 이후 모든 쿼리는 원본 파일 대신 압축된 그래프를 읽습니다 — 여기서 절약이 복리로 누적됩니다. SHA256 캐시로 재실행 시 변경된 파일만 재처리합니다.

**자동 동기화** (`--watch`) - 백그라운드 터미널에서 실행하면 코드베이스가 변경될 때 그래프가 자동으로 업데이트됩니다. 코드 파일 저장 시 즉시 재빌드가 트리거됩니다(AST만, LLM 없음). 문서/이미지 변경 시에는 LLM 재처리를 위해 `--update` 실행을 알려줍니다.

**Git 훅** (`graphify hook install`) - post-commit 및 post-checkout 훅을 설치합니다. 모든 커밋과 브랜치 전환 후 그래프가 자동으로 재빌드됩니다. 재빌드가 실패하면 훅이 0이 아닌 코드로 종료하여 git이 에러를 표시하고 조용히 계속 진행하지 않습니다. 백그라운드 프로세스가 필요 없습니다.

**위키** (`--wiki`) - 커뮤니티 및 갓 노드별 위키피디아 스타일 마크다운 문서와 `index.md` 진입점. 어떤 에이전트든 `index.md`를 가리키면 JSON을 파싱하는 대신 파일을 읽어서 지식 베이스를 탐색할 수 있습니다.

## 실전 예제

| 코퍼스 | 파일 수 | 축소율 | 결과 |
|--------|---------|--------|------|
| Karpathy 리포지토리 + 논문 5편 + 이미지 4장 | 52 | **71.5x** | [`worked/karpathy-repos/`](worked/karpathy-repos/) |
| graphify 소스 + Transformer 논문 | 4 | **5.4x** | [`worked/mixed-corpus/`](worked/mixed-corpus/) |
| httpx (합성 Python 라이브러리) | 6 | ~1x | [`worked/httpx/`](worked/httpx/) |

토큰 축소는 코퍼스 크기에 비례하여 확장됩니다. 6개 파일은 어차피 컨텍스트 윈도우에 들어가므로, 그래프의 가치는 압축이 아닌 구조적 명확성에 있습니다. 52개 파일(코드 + 논문 + 이미지)에서는 71배 이상을 달성합니다. 각 `worked/` 폴더에는 원본 입력 파일과 실제 출력(`GRAPH_REPORT.md`, `graph.json`)이 있어 직접 실행하여 수치를 검증할 수 있습니다.

## 개인정보 보호

graphify는 문서, 논문, 이미지의 의미적 추출을 위해 파일 내용을 AI 코딩 어시스턴트의 기반 모델 API로 전송합니다 — Anthropic(Claude Code), OpenAI(Codex), 또는 사용 중인 플랫폼의 제공자. 코드 파일은 tree-sitter AST를 통해 로컬에서 처리됩니다 — 코드의 경우 파일 내용이 사용자의 머신을 벗어나지 않습니다. 어떠한 텔레메트리, 사용 추적, 분석도 없습니다. 유일한 네트워크 호출은 추출 중 플랫폼 모델 API에 대한 것이며, 사용자 본인의 API 키를 사용합니다.

## 기술 스택

NetworkX + Leiden (graspologic) + tree-sitter + vis.js. 의미적 추출은 Claude(Claude Code), GPT-4(Codex), 또는 플랫폼이 실행하는 모델을 통해 수행됩니다. Neo4j 불필요, 서버 불필요, 완전히 로컬에서 실행됩니다.

## 다음 계획

graphify는 그래프 레이어입니다. 그 위에 [Penpax](https://safishamsi.github.io/penpax.ai)를 개발하고 있습니다 — 회의, 브라우저 기록, 파일, 이메일, 코드를 하나의 지속적으로 업데이트되는 지식 그래프로 연결하는 온디바이스 디지털 트윈입니다. 클라우드 없음, 데이터 학습 없음. [대기 목록에 등록하세요.](https://safishamsi.github.io/penpax.ai)

## 스타 히스토리

[![Star History Chart](https://starchart.cc/safishamsi/graphify.svg)](https://starchart.cc/safishamsi/graphify)

<details>
<summary>기여하기</summary>

**실전 예제**는 가장 신뢰를 쌓는 기여 방식입니다. 실제 코퍼스에서 `/graphify`를 실행하고, 결과를 `worked/{slug}/`에 저장하고, 그래프가 맞게 파악한 것과 틀린 것을 평가하는 솔직한 `review.md`를 작성하여 PR을 제출하세요.

**추출 버그** - 입력 파일, 캐시 엔트리(`graphify-out/cache/`), 그리고 누락되거나 날조된 내용과 함께 이슈를 열어주세요.

모듈 책임과 언어 추가 방법은 [ARCHITECTURE.md](ARCHITECTURE.md)를 참조하세요.

</details>
