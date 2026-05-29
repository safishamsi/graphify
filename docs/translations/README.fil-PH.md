<p align="center">
  <img src="https://raw.githubusercontent.com/safishamsi/graphify/v4/docs/logo-text.svg" width="260" height="64" alt="Graphify"/>
</p>

<p align="center">
  🇺🇸 <a href="../../README.md">English</a> | 🇨🇳 <a href="README.zh-CN.md">简体中文</a> | 🇯🇵 <a href="README.ja-JP.md">日本語</a> | 🇰🇷 <a href="README.ko-KR.md">한국어</a> | 🇩🇪 <a href="README.de-DE.md">Deutsch</a> | 🇫🇷 <a href="README.fr-FR.md">Français</a> | 🇪🇸 <a href="README.es-ES.md">Español</a> | 🇮🇳 <a href="README.hi-IN.md">हिन्दी</a> | 🇧🇷 <a href="README.pt-BR.md">Português</a> | 🇷🇺 <a href="README.ru-RU.md">Русский</a> | 🇸🇦 <a href="README.ar-SA.md">العربية</a> | 🇮🇹 <a href="README.it-IT.md">Italiano</a> | 🇵🇱 <a href="README.pl-PL.md">Polski</a> | 🇳🇱 <a href="README.nl-NL.md">Nederlands</a> | 🇹🇷 <a href="README.tr-TR.md">Türkçe</a> | 🇺🇦 <a href="README.uk-UA.md">Українська</a> | 🇻🇳 <a href="README.vi-VN.md">Tiếng Việt</a> | 🇮🇩 <a href="README.id-ID.md">Bahasa Indonesia</a> | 🇸🇪 <a href="README.sv-SE.md">Svenska</a> | 🇬🇷 <a href="README.el-GR.md">Ελληνικά</a> | 🇷🇴 <a href="README.ro-RO.md">Română</a> | 🇨🇿 <a href="README.cs-CZ.md">Čeština</a> | 🇫🇮 <a href="README.fi-FI.md">Suomi</a> | 🇩🇰 <a href="README.da-DK.md">Dansk</a> | 🇳🇴 <a href="README.no-NO.md">Norsk</a> | 🇭🇺 <a href="README.hu-HU.md">Magyar</a> | 🇹🇭 <a href="README.th-TH.md">ภาษาไทย</a> | 🇺🇿 <a href="README.uz-UZ.md">Oʻzbekcha</a> | 🇹🇼 <a href="README.zh-TW.md">繁體中文</a> | 🇵🇭 <a href="README.fil-PH.md">Filipino</a>
</p>

<p align="center">
  <a href="https://github.com/safishamsi/graphify/actions/workflows/ci.yml"><img src="https://github.com/safishamsi/graphify/actions/workflows/ci.yml/badge.svg?branch=v4" alt="CI"/></a>
  <a href="https://pypi.org/project/graphifyy/"><img src="https://img.shields.io/pypi/v/graphifyy" alt="PyPI"/></a>
  <a href="https://pepy.tech/project/graphifyy"><img src="https://static.pepy.tech/badge/graphifyy" alt="Downloads"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
</p>

**Kasanayan para sa mga AI coding assistant.** I-type ang `/graphify` sa Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro, o Google Antigravity — binabasa nito ang iyong mga file, gumagawa ng knowledge graph, at ibinabalik sa iyo ang mga istrukturang hindi mo alam na nandoon pala. Maunawaan ang codebase nang mas mabilis. Tuklasin ang "bakit" sa likod ng mga desisyon sa arkitektura.

Ganap na multimodal. Magdagdag ng code, PDF, markdown, mga screenshot, diagram, larawan ng whiteboard, mga imahe sa ibang wika, o mga video at audio file — kine-extract ng graphify ang mga konsepto at relasyon mula sa lahat ng ito at pinag-uugnay ang mga ito sa iisang graph. Ang mga video ay tina-transcribe nang lokal gamit ang Whisper. Sumusuporta ng 25 na programming language sa pamamagitan ng tree-sitter AST.

> Si Andrej Karpathy ay nagpapanatili ng `/raw` folder kung saan nilalagay niya ang mga papel, tweet, screenshot, at tala. Ang graphify ang sagot sa problemang iyon — **71.5x** na mas kaunting token bawat query kumpara sa pagbasa ng mga raw file, at persistent sa pagitan ng mga session.

```
/graphify .
```

```
graphify-out/
├── graph.html       interactive na graph — buksan sa kahit anong browser
├── GRAPH_REPORT.md  mga god node, nakakagulat na koneksyon, mga iminumungkahing tanong
├── graph.json       persistent na graph — maaaring i-query kahit pagkalipas ng mga linggo
└── cache/           SHA256 cache — ang mga pag-uulit ay nagpo-proseso lang ng mga nabagong file
```

## Paano Gumagana

Gumagana ang graphify sa tatlong pass. Una, isang deterministikong AST pass ang nag-e-extract ng istruktura mula sa mga code file nang walang LLM. Pagkatapos, ang mga video at audio file ay tina-transcribe nang lokal gamit ang faster-whisper. Panghuli, mga Claude sub-agent ang tumatakbo nang magkakasabay sa mga dokumento, papel, imahe, at transkripsyon. Ang mga resulta ay pinagsasama sa isang NetworkX graph, naka-cluster gamit ang Leiden, at ine-export bilang interactive na HTML, queryable na JSON, at audit report.

Ang bawat relasyon ay may label na `EXTRACTED`, `INFERRED` (may confidence score), o `AMBIGUOUS`.

## Pag-install

**Mga Kinakailangan:** Python 3.10+ at isa sa mga sumusunod: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com) at iba pa.

```bash
uv tool install graphifyy && graphify install
# o gamit ang pipx
pipx install graphifyy && graphify install
# o pip
pip install graphifyy && graphify install
```

> **Opisyal na package:** Ang PyPI package ay pinangalanang `graphifyy`. Ang tanging opisyal na repository ay [safishamsi/graphify](https://github.com/safishamsi/graphify).

## Paggamit

```
/graphify .
/graphify ./raw --update
/graphify query "ano ang nagkokonekta sa Attention at sa optimizer?"
/graphify path "DigestAuth" "Response"
graphify hook install
graphify update ./src
```

## Ano ang Makukuha Mo

**Mga god node** — mga konsepto na may pinakamataas na degree · **Mga nakakagulat na koneksyon** — naka-rank ayon sa score · **Mga iminumungkahing tanong** · **"Bakit"** — mga docstring at disenyo na rason ay ine-extract bilang mga node · **Token benchmark** — **71.5x** na mas kaunting token sa mixed corpus.

## Privacy

Ang mga code file ay prinoseso nang lokal sa pamamagitan ng tree-sitter AST. Ang mga video ay tina-transcribe nang lokal gamit ang faster-whisper. Walang telemetry.

## Binuo sa ibabaw ng graphify — Penpax

Ang [**Penpax**](https://graphifylabs.ai) ay ang enterprise layer sa ibabaw ng graphify. **Malapit nang magkaroon ng libreng trial.** [Sumali sa waitlist →](https://graphifylabs.ai)

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
