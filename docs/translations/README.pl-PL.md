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

**Umiejętność dla asystenta kodowania AI.** Wpisz `/graphify` w Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro lub Google Antigravity — czyta Twoje pliki, buduje graf wiedzy i zwraca Ci strukturę, o której nie wiedziałeś, że istnieje. Rozumiej bazę kodu szybciej. Znajdź „dlaczego" za decyzjami architektonicznymi.

W pełni multimodalny. Dodaj kod, PDF, markdown, zrzuty ekranu, diagramy, zdjęcia tablic, obrazy w innych językach lub pliki wideo i audio — graphify wyodrębnia koncepcje i relacje ze wszystkiego i łączy je w jeden graf. Wideo są transkrybowane lokalnie za pomocą Whisper. Obsługuje 25 języków programowania przez tree-sitter AST.

> Andrej Karpathy prowadzi folder `/raw`, gdzie wrzuca artykuły, tweety, zrzuty ekranu i notatki. graphify jest odpowiedzią na ten problem — **71,5x** mniej tokenów na zapytanie w porównaniu z czytaniem surowych plików, trwały między sesjami.

```
/graphify .                        # działa na dowolnym folderze
```

```
graphify-out/
├── graph.html       interaktywny graf — otwórz w dowolnej przeglądarce
├── GRAPH_REPORT.md  węzły boga, zaskakujące połączenia, sugerowane pytania
├── graph.json       trwały graf — zapytaj tygodnie później
└── cache/           cache SHA256 — ponowne uruchomienia przetwarzają tylko zmienione pliki
```

## Jak to działa

graphify działa w trzech przebiegach. Najpierw deterministyczny przebieg AST wyodrębnia strukturę z plików kodu bez LLM. Następnie pliki wideo i audio są transkrybowane lokalnie za pomocą faster-whisper. Na koniec subagenci Claude działają równolegle na dokumentach, artykułach, obrazach i transkrypcjach. Wyniki są łączone w graf NetworkX, grupowane za pomocą Leiden i eksportowane jako interaktywny HTML, JSON i raport audytu.

Każda relacja jest oznaczona `EXTRACTED`, `INFERRED` (z wynikiem pewności) lub `AMBIGUOUS`.

## Instalacja

**Wymagania:** Python 3.10+ i jedno z: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com) i inne.

```bash
uv tool install graphifyy && graphify install
# lub z pipx
pipx install graphifyy && graphify install
# lub pip
pip install graphifyy && graphify install
```

> **Oficjalny pakiet:** Pakiet PyPI nazywa się `graphifyy`. Jedyne oficjalne repozytorium to [safishamsi/graphify](https://github.com/safishamsi/graphify).

## Użycie

```
/graphify .
/graphify ./raw --update           # tylko zmienione pliki
/graphify ./raw --mode deep
/graphify query "co łączy Attention z optymalizatorem?"
/graphify path "DigestAuth" "Response"
graphify hook install
graphify update ./src
```

## Co otrzymujesz

**Węzły boga** — koncepcje o najwyższym stopniu · **Zaskakujące połączenia** — posortowane według wyniku · **Sugerowane pytania** — 4-5 pytań, na które graf jest wyjątkowo zdolny odpowiedzieć · **„Dlaczego"** — docstringi i uzasadnienia projektowe wyodrębnione jako węzły · **Benchmark tokenów** — **71,5x** mniej tokenów na mieszanym korpusie.

## Prywatność

Pliki kodu są przetwarzane lokalnie przez tree-sitter AST. Wideo transkrybowane lokalnie z faster-whisper. Brak telemetrii.

## Zbudowane na graphify — Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai) to warstwa enterprise nad graphify. **Bezpłatna wersja próbna wkrótce.** [Dołącz do listy oczekujących →](https://safishamsi.github.io/penpax.ai)

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
