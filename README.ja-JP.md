# graphify

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md) | [한국어](README.ko-KR.md)

[![CI](https://github.com/safishamsi/graphify/actions/workflows/ci.yml/badge.svg?branch=v3)](https://github.com/safishamsi/graphify/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/graphifyy)](https://pypi.org/project/graphifyy/)
[![Sponsor](https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors)](https://github.com/sponsors/safishamsi)

**AIコーディングアシスタント向けのスキル。** Claude Code、Codex、OpenCode、OpenClaw、Factory Droid で `/graphify` と入力するだけで、ファイルを読み込んでナレッジグラフを構築し、あなたが気づいていなかった構造を返します。コードベースをより速く理解し、アーキテクチャ上の意思決定の「なぜ」を見つけ出します。

完全にマルチモーダル対応。コード、PDF、Markdown、スクリーンショット、図、ホワイトボード写真、他言語の画像まで――graphify は Claude Vision を使ってそれらすべてから概念と関係性を抽出し、1 つのグラフに接続します。tree-sitter AST により 19 言語をサポート（Python、JS、TS、Go、Rust、Java、C、C++、Ruby、C#、Kotlin、Scala、PHP、Swift、Lua、Zig、PowerShell、Elixir、Objective-C）。

> Andrej Karpathy は論文、ツイート、スクリーンショット、メモを放り込む `/raw` フォルダを持っています。graphify はまさにその問題への答えです――生ファイルを読むのに比べて1クエリあたりのトークン数が 71.5 倍少なく、セッションをまたいで永続化され、見つけたものと推測したものを正直に区別します。

```
/graphify .                        # どのフォルダでも動作 - コードベース、メモ、論文、なんでも
```

```
graphify-out/
├── graph.html       インタラクティブなグラフ - ノードをクリック、検索、コミュニティでフィルタ
├── GRAPH_REPORT.md  ゴッドノード、意外なつながり、推奨される質問
├── graph.json       永続化されたグラフ - 数週間後でも再読み込みなしでクエリ可能
└── cache/           SHA256 キャッシュ - 再実行時は変更されたファイルのみ処理
```

グラフに含めたくないフォルダを除外するには `.graphifyignore` ファイルを追加します：

```
# .graphifyignore
vendor/
node_modules/
dist/
*.generated.py
```

構文は `.gitignore` と同じです。パターンは graphify を実行したフォルダからの相対パスに対してマッチします。

## 仕組み

graphify は 2 パスで動作します。まず、決定論的な AST パスがコードファイルから構造（クラス、関数、インポート、コールグラフ、docstring、根拠コメント）を LLM なしで抽出します。次に、Claude サブエージェントがドキュメント、論文、画像に対して並列に実行され、概念、関係性、設計の根拠を抽出します。結果は NetworkX グラフにマージされ、Leiden コミュニティ検出でクラスタリングされ、インタラクティブ HTML、クエリ可能な JSON、平易な言葉の監査レポートとしてエクスポートされます。

**クラスタリングはグラフトポロジベース――埋め込みは使いません。** Leiden はエッジ密度によってコミュニティを見つけます。Claude が抽出する意味的類似性エッジ（`semantically_similar_to`、INFERRED とマーク）は既にグラフに含まれているため、コミュニティ検出に直接影響します。グラフ構造そのものが類似性シグナルであり――別途の埋め込みステップやベクターデータベースは不要です。

すべての関係は `EXTRACTED`（ソースから直接見つかった）、`INFERRED`（合理的な推論、信頼度スコア付き）、`AMBIGUOUS`（レビュー対象としてフラグ付け）のいずれかでタグ付けされます。何が見つかったもので何が推測されたものか、常に分かります。

## インストール

**必要なもの:** Python 3.10+ および以下のいずれか： [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [OpenClaw](https://openclaw.ai), または [Factory Droid](https://factory.ai)

```bash
pip install graphifyy && graphify install
```

> PyPI パッケージは `graphify` の名前が再取得されるまでの間、一時的に `graphifyy` となっています。CLI とスキルコマンドは依然として `graphify` です。

### プラットフォームサポート

| プラットフォーム | インストールコマンド |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install`（自動検出）または `graphify install --platform windows` |
| Codex | `graphify install --platform codex` |
| OpenCode | `graphify install --platform opencode` |
| OpenClaw | `graphify install --platform claw` |
| Factory Droid | `graphify install --platform droid` |

Codex ユーザーは並列抽出のために `~/.codex/config.toml` の `[features]` の下に `multi_agent = true` も必要です。Factory Droid は並列サブエージェントディスパッチに `Task` ツールを使用します。OpenClaw は逐次抽出を使用します（並列エージェントサポートはこのプラットフォームではまだ初期段階です）。

次に、AI コーディングアシスタントを開いて入力します：

```
/graphify .
```

注意：Codex はスキル呼び出しに `/` ではなく `$` を使用するため、代わりに `$graphify .` と入力してください。

### アシスタントに常にグラフを使わせる（推奨）

グラフを構築した後、プロジェクトで一度だけ以下を実行します：

| プラットフォーム | コマンド |
|----------|---------|
| Claude Code | `graphify claude install` |
| Codex | `graphify codex install` |
| OpenCode | `graphify opencode install` |
| OpenClaw | `graphify claw install` |
| Factory Droid | `graphify droid install` |

**Claude Code** は 2 つのことを行います：Claude にアーキテクチャの質問に答える前に `graphify-out/GRAPH_REPORT.md` を読むように指示する `CLAUDE.md` セクションを書き込み、すべての Glob と Grep 呼び出しの前に発火する **PreToolUse フック**（`settings.json`）をインストールします。ナレッジグラフが存在する場合、Claude は次のメッセージを見ます：_"graphify: Knowledge graph exists. Read GRAPH_REPORT.md for god nodes and community structure before searching raw files."_ ――これにより Claude はすべてのファイルを grep するのではなく、グラフを介してナビゲートします。

**Codex、OpenCode、OpenClaw、Factory Droid** は同じルールをプロジェクトルートの `AGENTS.md` に書き込みます。これらのプラットフォームは PreToolUse フックをサポートしていないため、AGENTS.md が常時有効のメカニズムとなります。

アンインストールは対応するアンインストールコマンドで行います（例：`graphify claude uninstall`）。

**常時有効 vs 明示的トリガー――何が違うのか？**

常時有効のフックは `GRAPH_REPORT.md` を表面化します――これはゴッドノード、コミュニティ、意外なつながりを 1 ページにまとめた要約です。アシスタントはファイル検索の前にこれを読み、キーワードマッチではなく構造に基づいてナビゲートします。これで日常的な質問のほとんどをカバーできます。

`/graphify query`、`/graphify path`、`/graphify explain` はさらに深く踏み込みます：生の `graph.json` をホップごとに辿り、ノード間の正確なパスをトレースし、エッジレベルの詳細（関係タイプ、信頼度スコア、ソース位置）を表面化します。一般的なオリエンテーションではなく、特定の質問をグラフから答えさせたいときに使います。

こう考えてください：常時有効のフックはアシスタントに地図を与え、`/graphify` コマンドはその地図を正確にナビゲートさせます。

<details>
<summary>手動インストール（curl）</summary>

```bash
mkdir -p ~/.claude/skills/graphify
curl -fsSL https://raw.githubusercontent.com/safishamsi/graphify/v3/graphify/skill.md \
  > ~/.claude/skills/graphify/SKILL.md
```

`~/.claude/CLAUDE.md` に追加します：

```
- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, invoke the Skill tool with `skill: "graphify"` before doing anything else.
```

</details>

## 使い方

```
/graphify                          # カレントディレクトリで実行
/graphify ./raw                    # 特定のフォルダで実行
/graphify ./raw --mode deep        # より積極的な INFERRED エッジ抽出
/graphify ./raw --update           # 変更されたファイルのみ再抽出し、既存グラフにマージ
/graphify ./raw --cluster-only     # 既存グラフのクラスタリングを再実行（再抽出なし）
/graphify ./raw --no-viz           # HTML をスキップ、レポート + JSON のみ生成
/graphify ./raw --obsidian                          # Obsidian ボールトも生成（オプトイン）
/graphify ./raw --obsidian --obsidian-dir ~/vaults/myproject  # ボールトを特定のディレクトリに書き込み

/graphify add https://arxiv.org/abs/1706.03762        # 論文を取得、保存、グラフを更新
/graphify add https://x.com/karpathy/status/...       # ツイートを取得
/graphify add https://... --author "Name"             # 元の著者をタグ付け
/graphify add https://... --contributor "Name"        # コーパスに追加した人をタグ付け

/graphify query "アテンションとオプティマイザを結ぶものは？"
/graphify query "アテンションとオプティマイザを結ぶものは？" --dfs   # 特定のパスをトレース
/graphify query "アテンションとオプティマイザを結ぶものは？" --budget 1500  # N トークンで上限設定
/graphify path "DigestAuth" "Response"
/graphify explain "SwinTransformer"

/graphify ./raw --watch            # ファイル変更時にグラフを自動同期（コード：即時、ドキュメント：通知）
/graphify ./raw --wiki             # エージェントがクロール可能な wiki を構築（index.md + コミュニティごとの記事）
/graphify ./raw --svg              # graph.svg をエクスポート
/graphify ./raw --graphml          # graph.graphml をエクスポート（Gephi、yEd）
/graphify ./raw --neo4j            # Neo4j 用の cypher.txt を生成
/graphify ./raw --neo4j-push bolt://localhost:7687    # 実行中の Neo4j インスタンスに直接プッシュ
/graphify ./raw --mcp              # MCP stdio サーバーを起動

# git フック - プラットフォーム非依存、コミット時とブランチ切り替え時にグラフを再構築
graphify hook install
graphify hook uninstall
graphify hook status

# 常時有効のアシスタント指示 - プラットフォーム固有
graphify claude install            # CLAUDE.md + PreToolUse フック（Claude Code）
graphify claude uninstall
graphify codex install             # AGENTS.md（Codex）
graphify opencode install          # AGENTS.md（OpenCode）
graphify claw install              # AGENTS.md（OpenClaw）
graphify droid install             # AGENTS.md（Factory Droid）

# ターミナルから直接グラフをクエリ（AI アシスタント不要）
graphify query "アテンションとオプティマイザを結ぶものは？"
graphify query "認証フローを表示" --dfs
graphify query "CfgNode とは？" --budget 500
graphify query "..." --graph path/to/graph.json
```

あらゆるファイルタイプの組み合わせで動作します：

| タイプ | 拡張子 | 抽出方法 |
|------|-----------|------------|
| コード | `.py .ts .js .go .rs .java .c .cpp .rb .cs .kt .scala .php .swift .lua .zig .ps1 .ex .exs .m .mm` | tree-sitter による AST + コールグラフ + docstring/コメントの根拠 |
| ドキュメント | `.md .txt .rst` | Claude による概念 + 関係性 + 設計根拠 |
| Office | `.docx .xlsx` | Markdown に変換した後 Claude で抽出（`pip install graphifyy[office]` が必要） |
| 論文 | `.pdf` | 引用マイニング + 概念抽出 |
| 画像 | `.png .jpg .webp .gif` | Claude Vision - スクリーンショット、図、任意の言語 |

## 得られるもの

**ゴッドノード** - 最高次数の概念（すべてが接続するもの）

**意外なつながり** - 複合スコアでランク付け。コード-論文のエッジはコード-コードよりも高くランクされます。各結果には平易な英語の理由が含まれます。

**推奨される質問** - グラフがユニークに答えられる 4〜5 の質問

**「なぜ」** - docstring、インラインコメント（`# NOTE:`、`# IMPORTANT:`、`# HACK:`、`# WHY:`）、ドキュメントからの設計根拠が `rationale_for` ノードとして抽出されます。コードが何をするかだけでなく――なぜそのように書かれたか。

**信頼度スコア** - すべての INFERRED エッジには `confidence_score`（0.0〜1.0）があります。何が推測されたかだけでなく、モデルがどれだけ確信していたかもわかります。EXTRACTED エッジは常に 1.0 です。

**意味的類似性エッジ** - 構造的接続のないクロスファイル概念リンク。互いを呼び出さずに同じ問題を解いている 2 つの関数、同じアルゴリズムを記述しているコード内のクラスと論文内の概念など。

**ハイパーエッジ** - ペアワイズエッジでは表現できない 3+ ノードを接続するグループ関係。共有プロトコルを実装するすべてのクラス、認証フロー内のすべての関数、論文セクションから 1 つのアイデアを形成するすべての概念など。

**トークンベンチマーク** - 実行ごとに自動的に出力されます。混合コーパス（Karpathy リポジトリ + 論文 + 画像）で、生ファイルを読むのに比べて 1 クエリあたり **71.5 倍** 少ないトークン。最初の実行で抽出とグラフ構築を行います（これにはトークンがかかります）。以降のクエリはすべて生ファイルではなくコンパクトなグラフを読みます――ここで節約が複利的に効いてきます。SHA256 キャッシュにより、再実行時は変更されたファイルのみ再処理されます。

**自動同期** (`--watch`) - バックグラウンドターミナルで実行し、コードベースが変更されるとグラフが自動的に更新されます。コードファイルの保存は即座の再構築をトリガーします（AST のみ、LLM なし）。ドキュメント/画像の変更は、LLM の再パスのために `--update` を実行するよう通知します。

**Git フック** (`graphify hook install`) - post-commit と post-checkout フックをインストールします。コミットごと、ブランチ切り替えごとにグラフが自動的に再構築されます。再構築が失敗した場合、フックは非ゼロコードで終了するため、git がエラーを表面化し、静かに続行することはありません。バックグラウンドプロセスは不要です。

**Wiki** (`--wiki`) - コミュニティごとおよびゴッドノードごとの Wikipedia スタイルの Markdown 記事と、`index.md` エントリポイント。任意のエージェントを `index.md` に向ければ、JSON をパースする代わりにファイルを読むことでナレッジベースをナビゲートできます。

## 実例

| コーパス | ファイル数 | 削減率 | 出力 |
|--------|-------|-----------|--------|
| Karpathy リポジトリ + 論文5本 + 画像4枚 | 52 | **71.5x** | [`worked/karpathy-repos/`](worked/karpathy-repos/) |
| graphify ソース + Transformer 論文 | 4 | **5.4x** | [`worked/mixed-corpus/`](worked/mixed-corpus/) |
| httpx（合成 Python ライブラリ） | 6 | ~1x | [`worked/httpx/`](worked/httpx/) |

トークン削減はコーパスサイズに応じてスケールします。6 ファイルはいずれにせよコンテキストウィンドウに収まるため、そこでのグラフの価値は圧縮ではなく構造的明瞭さです。52 ファイル（コード + 論文 + 画像）では 71 倍以上が得られます。各 `worked/` フォルダには生の入力ファイルと実際の出力（`GRAPH_REPORT.md`、`graph.json`）があり、自分で実行して数字を検証できます。

## プライバシー

graphify はドキュメント、論文、画像の意味的抽出のために、ファイル内容を AI コーディングアシスタントの基盤モデル API に送信します――Anthropic（Claude Code）、OpenAI（Codex）、またはプラットフォームが使用するプロバイダーです。コードファイルは tree-sitter AST を介してローカルで処理されます――コードに関してはファイル内容がマシンから出ることはありません。テレメトリ、利用追跡、分析は一切ありません。ネットワーク呼び出しは抽出中のプラットフォームのモデル API への呼び出しのみで、あなた自身の API キーを使用します。

## 技術スタック

NetworkX + Leiden（graspologic） + tree-sitter + vis.js。意味的抽出は Claude（Claude Code）、GPT-4（Codex）、またはプラットフォームが実行するモデルを介して行われます。Neo4j は不要、サーバーも不要、完全にローカルで実行されます。

## スター履歴

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)

<details>
<summary>コントリビューション</summary>

**実例** は最も信頼を築くコントリビューションです。実際のコーパスで `/graphify` を実行し、出力を `worked/{slug}/` に保存し、グラフが正しく捉えたもの・間違えたものを評価する正直な `review.md` を書き、PR を提出してください。

**抽出バグ** - 入力ファイル、キャッシュエントリ（`graphify-out/cache/`）、何が見逃された/捏造されたかを添えて issue を開いてください。

モジュールの責任と言語の追加方法については [ARCHITECTURE.md](ARCHITECTURE.md) を参照してください。

</details>
