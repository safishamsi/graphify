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

**En ferdighet for AI-kodeassistenter.** Skriv `/graphify` i Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro eller Google Antigravity — den leser filene dine, bygger en kunnskapsgraf og gir deg tilbake strukturen du ikke visste eksisterte. Forstå en kodebase raskere. Finn «hvorfor» bak arkitektoniske beslutninger.

Fullt multimodal. Legg til kode, PDF-er, markdown, skjermbilder, diagrammer, whiteboardbilder, bilder på andre språk eller video- og lydfiler — graphify ekstraherer begreper og relasjoner fra alt og kobler dem i én graf. Videoer transkriberes lokalt med Whisper. Støtter 25 programmeringsspråk via tree-sitter AST.

> Andrej Karpathy opprettholder en `/raw`-mappe der han legger artikler, tweets, skjermbilder og notater. graphify er svaret på det problemet — **71,5x** færre tokens per spørring sammenlignet med å lese råfiler, vedvarende mellom sesjoner.

```
/graphify .
```

```
graphify-out/
├── graph.html       interaktiv graf — åpne i en hvilken som helst nettleser
├── GRAPH_REPORT.md  gudnoder, overraskende forbindelser, foreslåtte spørsmål
├── graph.json       vedvarende graf — forespørselbar uker senere
└── cache/           SHA256-cache — gjentatte kjøringer behandler bare endrede filer
```

## Hvordan det fungerer

graphify arbeider i tre gjennomganger. Først ekstraherer et deterministisk AST-gjennomgang struktur fra kodefiler uten LLM. Deretter transkriberes video- og lydfiler lokalt med faster-whisper. Til slutt kjører Claude-underagenter parallelt på dokumenter, artikler, bilder og transkripsjoner. Resultatene slås sammen i en NetworkX-graf, klynges med Leiden og eksporteres som interaktiv HTML, forespørselbar JSON og revisjonsrapport.

Hver relasjon er merket `EXTRACTED`, `INFERRED` (med konfidenspoeng) eller `AMBIGUOUS`.

## Installasjon

**Krav:** Python 3.10+ og én av: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com) og andre.

```bash
uv tool install graphifyy && graphify install
# eller med pipx
pipx install graphifyy && graphify install
# eller pip
pip install graphifyy && graphify install
```

> **Offisiell pakke:** PyPI-pakken heter `graphifyy`. Det eneste offisielle depotet er [safishamsi/graphify](https://github.com/safishamsi/graphify).

## Bruk

```
/graphify .
/graphify ./raw --update
/graphify query "hva kobler Attention til optimizeren?"
/graphify path "DigestAuth" "Response"
graphify hook install
graphify update ./src
```

## Hva du får

**Gudnoder** — begreper med høyest grad · **Overraskende forbindelser** — rangert etter poeng · **Foreslåtte spørsmål** · **«Hvorfor»** — docstrings og designbegrunnelse ekstrahert som noder · **Token-benchmark** — **71,5x** færre tokens på blandet korpus.

## Personvern

Kodefiler behandles lokalt via tree-sitter AST. Videoer transkriberes lokalt med faster-whisper. Ingen telemetri.

## Bygget på graphify — Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai) er enterprise-laget oppå graphify. **Gratis prøveperiode kommer snart.** [Bli med på ventelisten →](https://safishamsi.github.io/penpax.ai)

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
