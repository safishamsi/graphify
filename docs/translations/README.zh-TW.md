<p align="center">
  <img src="https://raw.githubusercontent.com/safishamsi/graphify/v4/docs/logo-text.svg" width="260" height="64" alt="Graphify"/>
</p>

<p align="center">
  🇺🇸 <a href="../../README.md">English</a> | 🇨🇳 <a href="README.zh-CN.md">简体中文</a> | 🇯🇵 <a href="README.ja-JP.md">日本語</a> | 🇰🇷 <a href="README.ko-KR.md">한국어</a> | 🇩🇪 <a href="README.de-DE.md">Deutsch</a> | 🇫🇷 <a href="README.fr-FR.md">Français</a> | 🇪🇸 <a href="README.es-ES.md">Español</a> | 🇮🇳 <a href="README.hi-IN.md">हिन्दी</a> | 🇧🇷 <a href="README.pt-BR.md">Português</a> | 🇷🇺 <a href="README.ru-RU.md">Русский</a> | 🇸🇦 <a href="README.ar-SA.md">العربية</a> | 🇮🇹 <a href="README.it-IT.md">Italiano</a> | 🇵🇱 <a href="README.pl-PL.md">Polski</a> | 🇳🇱 <a href="README.nl-NL.md">Nederlands</a> | 🇹🇷 <a href="README.tr-TR.md">Türkçe</a> | 🇺🇦 <a href="README.uk-UA.md">Українська</a> | 🇻🇳 <a href="README.vi-VN.md">Tiếng Việt</a> | 🇮🇩 <a href="README.id-ID.md">Bahasa Indonesia</a> | 🇸🇪 <a href="README.sv-SE.md">Svenska</a> | 🇬🇷 <a href="README.el-GR.md">Ελληνικά</a> | 🇷🇴 <a href="README.ro-RO.md">Română</a> | 🇨🇿 <a href="README.cs-CZ.md">Čeština</a> | 🇫🇮 <a href="README.fi-FI.md">Suomi</a> | 🇩🇰 <a href="README.da-DK.md">Dansk</a> | 🇳🇴 <a href="README.no-NO.md">Norsk</a> | 🇭🇺 <a href="README.hu-HU.md">Magyar</a> | 🇹🇭 <a href="README.th-TH.md">ภาษาไทย</a> | 🇹🇼 <a href="README.zh-TW.md">繁體中文</a>
</p>

<p align="center">
  <a href="https://github.com/safishamsi/graphify/actions/workflows/ci.yml"><img src="https://github.com/safishamsi/graphify/actions/workflows/ci.yml/badge.svg?branch=v4" alt="CI"/></a>
  <a href="https://pypi.org/project/graphifyy/"><img src="https://img.shields.io/pypi/v/graphifyy" alt="PyPI"/></a>
  <a href="https://pepy.tech/project/graphifyy"><img src="https://static.pepy.tech/badge/graphifyy" alt="Downloads"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
</p>

**AI 程式碼助手的技能。** 在 Claude Code、Codex、OpenCode、Cursor、Gemini CLI、GitHub Copilot CLI、VS Code Copilot Chat、Aider、OpenClaw、Factory Droid、Trae、Hermes、Kiro 或 Google Antigravity 中輸入 `/graphify` — 它會讀取您的檔案、建立知識圖譜，並返回您不知道存在的結構。更快理解程式碼庫。找到架構決策背後的「為什麼」。

完全多模態。添加程式碼、PDF、Markdown、截圖、圖表、白板照片、其他語言的圖片或視訊和音訊檔案 — graphify 從所有內容中提取概念和關係，並將它們連接成單一圖譜。視訊使用 Whisper 在本地轉錄。透過 tree-sitter AST 支援 25 種程式語言。

> Andrej Karpathy 維護一個 `/raw` 資料夾，在那裡他放置論文、推文、截圖和筆記。graphify 是這個問題的答案 — 每次查詢比讀取原始檔案少 **71.5 倍** 的 token，在會話之間持久存在。

```
/graphify .
```

```
graphify-out/
├── graph.html       互動式圖譜 — 在任何瀏覽器中開啟
├── GRAPH_REPORT.md  神級節點、令人驚訝的連接、建議問題
├── graph.json       持久圖譜 — 幾週後仍可查詢
└── cache/           SHA256 快取 — 重複執行只處理已變更的檔案
```

## 運作原理

graphify 分三個階段工作。首先，確定性 AST 遍歷在不使用 LLM 的情況下從程式碼檔案中提取結構。然後使用 faster-whisper 在本地轉錄視訊和音訊檔案。最後，Claude 子代理並行處理文件、論文、圖片和轉錄文字。結果被合併到 NetworkX 圖譜中，使用 Leiden 進行聚類，並匯出為互動式 HTML、可查詢 JSON 和審計報告。

每個關係都標記為 `EXTRACTED`、`INFERRED`（帶有置信度分數）或 `AMBIGUOUS`。

## 安裝

**需求：** Python 3.10+ 以及以下之一：[Claude Code](https://claude.ai/code)、[Codex](https://openai.com/codex)、[OpenCode](https://opencode.ai)、[Cursor](https://cursor.com) 等。

```bash
uv tool install graphifyy && graphify install
# 或使用 pipx
pipx install graphifyy && graphify install
# 或 pip
pip install graphifyy && graphify install
```

> **官方套件：** PyPI 套件名稱為 `graphifyy`。唯一的官方儲存庫是 [safishamsi/graphify](https://github.com/safishamsi/graphify)。

## 使用方式

```
/graphify .
/graphify ./raw --update
/graphify query "什麼將 Attention 與 optimizer 連接起來？"
/graphify path "DigestAuth" "Response"
graphify hook install
graphify update ./src
```

## 您會得到什麼

**神級節點** — 度數最高的概念 · **令人驚訝的連接** — 按分數排名 · **建議問題** · **「為什麼」** — 提取為節點的文件字串和設計理由 · **Token 基準測試** — 在混合語料庫上少 **71.5 倍** 的 token。

## 隱私

程式碼檔案透過 tree-sitter AST 在本地處理。視訊使用 faster-whisper 在本地轉錄。無遙測。

## 基於 graphify 構建 — Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai) 是 graphify 之上的企業層。**免費試用即將推出。** [加入等待名單 →](https://safishamsi.github.io/penpax.ai)

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
