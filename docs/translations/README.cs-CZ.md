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

**Dovednost pro asistenty kódování AI.** Napište `/graphify` v Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro nebo Google Antigravity — přečte vaše soubory, vytvoří znalostní graf a vrátí vám strukturu, o které jste nevěděli, že existuje. Pochopte kódovou základnu rychleji. Najděte „proč" za architektonickými rozhodnutími.

Plně multimodální. Přidejte kód, PDF, markdown, snímky obrazovky, diagramy, fotografie tabule, obrázky v jiných jazycích nebo video a zvukové soubory — graphify extrahuje koncepty a vztahy ze všeho a spojuje je do jediného grafu. Videa jsou přepisována lokálně pomocí Whisper. Podporuje 25 programovacích jazyků prostřednictvím tree-sitter AST.

> Andrej Karpathy udržuje složku `/raw`, kde ukládá články, tweety, snímky obrazovky a poznámky. graphify je odpovědí na tento problém — **71,5x** méně tokenů na dotaz ve srovnání se čtením surových souborů, přetrvávající mezi sezeními.

```
/graphify .
```

```
graphify-out/
├── graph.html       interaktivní graf — otevřete v libovolném prohlížeči
├── GRAPH_REPORT.md  boží uzly, překvapivá propojení, navrhované otázky
├── graph.json       trvalý graf — dotazovatelný týdny poté
└── cache/           SHA256 cache — opakovaná spuštění zpracovávají pouze změněné soubory
```

## Jak to funguje

graphify pracuje ve třech průchodech. Nejprve deterministický průchod AST extrahuje strukturu z kódových souborů bez LLM. Poté jsou video a zvukové soubory přepisovány lokálně pomocí faster-whisper. Nakonec sub-agenti Claude běží paralelně na dokumentech, článcích, obrázcích a přepisech. Výsledky jsou sloučeny do grafu NetworkX, clusterovány pomocí Leiden a exportovány jako interaktivní HTML, dotazovatelný JSON a auditní zpráva.

Každý vztah je označen `EXTRACTED`, `INFERRED` (se skóre spolehlivosti) nebo `AMBIGUOUS`.

## Instalace

**Požadavky:** Python 3.10+ a jedno z: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com) a další.

```bash
uv tool install graphifyy && graphify install
# nebo s pipx
pipx install graphifyy && graphify install
# nebo pip
pip install graphifyy && graphify install
```

> **Oficiální balíček:** Balíček PyPI se jmenuje `graphifyy`. Jediné oficiální úložiště je [safishamsi/graphify](https://github.com/safishamsi/graphify).

## Použití

```
/graphify .
/graphify ./raw --update
/graphify query "co spojuje Attention s optimizerem?"
/graphify path "DigestAuth" "Response"
graphify hook install
graphify update ./src
```

## Co získáte

**Boží uzly** — koncepty s nejvyšším stupněm · **Překvapivá propojení** — seřazená podle skóre · **Navrhované otázky** · **„Proč"** — docstringy a návrhové odůvodnění extrahované jako uzly · **Benchmark tokenů** — **71,5x** méně tokenů na smíšeném korpusu.

## Soukromí

Kódové soubory jsou zpracovávány lokálně prostřednictvím tree-sitter AST. Videa jsou přepisována lokálně pomocí faster-whisper. Žádná telemetrie.

## Postaveno na graphify — Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai) je enterprise vrstva nad graphify. **Bezplatná zkušební verze brzy.** [Přidejte se na čekací listinu →](https://safishamsi.github.io/penpax.ai)

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
