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

**Képesség AI kódolási asszisztensekhez.** Írja be a `/graphify` parancsot a Claude Code-ban, Codexben, OpenCode-ban, Cursorban, Gemini CLI-ben, GitHub Copilot CLI-ben, VS Code Copilot Chatben, Aiderben, OpenClawban, Factory Droidban, Traeben, Hermesben, Kiroban vagy a Google Antigravityben — beolvassa a fájljait, tudásgráfot épít, és visszaadja azt a struktúrát, amelyről nem tudta, hogy létezik. Értse meg gyorsabban a kódbázist. Találja meg az architektúrális döntések mögött álló „miértet".

Teljesen multimodális. Adjon hozzá kódot, PDF-eket, markdownt, képernyőképeket, diagramokat, táblafotókat, más nyelvű képeket vagy video- és hangfájlokat — a graphify mindenből kinyeri a fogalmakat és kapcsolatokat, és egyetlen gráfba köti össze őket. A videókat a Whisper segítségével helyben írja át. 25 programozási nyelvet támogat tree-sitter AST-n keresztül.

> Andrej Karpathy fenntart egy `/raw` mappát, ahova cikkeket, tweeteket, képernyőképeket és jegyzeteket helyez el. A graphify erre a problémára adott válasz — **71,5x** kevesebb token lekérdezésenként a nyers fájlok olvasásához képest, munkamenetek között is megmarad.

```
/graphify .
```

```
graphify-out/
├── graph.html       interaktív gráf — nyissa meg bármely böngészőben
├── GRAPH_REPORT.md  isten-csúcspontok, meglepő kapcsolatok, javasolt kérdések
├── graph.json       állandó gráf — hetekkel később is lekérdezhető
└── cache/           SHA256-gyorsítótár — ismételt futtatások csak a módosított fájlokat dolgozzák fel
```

## Hogyan működik

A graphify három menetben dolgozik. Először egy determinisztikus AST-menet kinyeri a struktúrát a kódfájlokból LLM nélkül. Ezután a video- és hangfájlokat a faster-whisper segítségével helyben írja át. Végül a Claude alügynökök párhuzamosan futnak dokumentumokon, cikkeken, képeken és átiratokban. Az eredményeket egy NetworkX-gráfba olvasztja össze, Leiden-nel klaszterezik, és interaktív HTML-ként, lekérdezhető JSON-ként és auditjelentésként exportálja.

Minden kapcsolat `EXTRACTED`, `INFERRED` (megbízhatósági pontszámmal) vagy `AMBIGUOUS` feliratot kap.

## Telepítés

**Követelmények:** Python 3.10+ és az alábbiak egyike: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com) és mások.

```bash
uv tool install graphifyy && graphify install
# vagy pipx-szel
pipx install graphifyy && graphify install
# vagy pip
pip install graphifyy && graphify install
```

> **Hivatalos csomag:** A PyPI-csomag neve `graphifyy`. Az egyetlen hivatalos tároló a [safishamsi/graphify](https://github.com/safishamsi/graphify).

## Használat

```
/graphify .
/graphify ./raw --update
/graphify query "mi köti össze az Attentiont az optimalizálóval?"
/graphify path "DigestAuth" "Response"
graphify hook install
graphify update ./src
```

## Mit kap

**Isten-csúcspontok** — a legmagasabb fokú fogalmak · **Meglepő kapcsolatok** — pontszám szerint rendezve · **Javasolt kérdések** · **A „miért"** — docstringek és tervezési indoklások csúcspontként kinyerve · **Token-benchmark** — **71,5x** kevesebb token vegyes korpuszon.

## Adatvédelem

A kódfájlokat helyben dolgozza fel tree-sitter AST-n keresztül. A videókat helyben írja át a faster-whisper. Nincs telemetria.

## A graphify-ra épülve — Penpax

A [**Penpax**](https://safishamsi.github.io/penpax.ai) a graphify feletti vállalati réteg. **Ingyenes próbaverzió hamarosan.** [Csatlakozzon a várólistához →](https://safishamsi.github.io/penpax.ai)

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
