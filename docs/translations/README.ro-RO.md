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

**O abilitate pentru asistenții de cod AI.** Tastați `/graphify` în Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro sau Google Antigravity — citește fișierele dvs., construiește un graf de cunoștințe și vă returnează structura pe care nu știați că există. Înțelegeți mai rapid o bază de cod. Găsiți „de ce"-ul din spatele deciziilor arhitecturale.

Complet multimodal. Adăugați cod, PDF-uri, markdown, capturi de ecran, diagrame, fotografii cu tablă albă, imagini în alte limbi sau fișiere video și audio — graphify extrage concepte și relații din toate și le conectează într-un singur graf. Videoclipurile sunt transcrise local cu Whisper. Suportă 25 de limbaje de programare prin tree-sitter AST.

> Andrej Karpathy menține un folder `/raw` unde depune lucrări, tweet-uri, capturi de ecran și note. graphify este răspunsul la această problemă — **71,5x** mai puțini token pe interogare față de citirea fișierelor brute, persistent între sesiuni.

```
/graphify .
```

```
graphify-out/
├── graph.html       graf interactiv — deschideți în orice browser
├── GRAPH_REPORT.md  noduri-zeu, conexiuni surprinzătoare, întrebări sugerate
├── graph.json       graf persistent — interogabil săptămâni mai târziu
└── cache/           cache SHA256 — rulările repetate procesează doar fișierele modificate
```

## Cum funcționează

graphify lucrează în trei treceri. Mai întâi, o trecere AST deterministă extrage structura din fișierele de cod fără LLM. Apoi fișierele video și audio sunt transcrise local cu faster-whisper. În final, sub-agenții Claude rulează în paralel pe documente, lucrări, imagini și transcrieri. Rezultatele sunt îmbinate într-un graf NetworkX, grupate cu Leiden și exportate ca HTML interactiv, JSON interogabil și raport de audit.

Fiecare relație este etichetată `EXTRACTED`, `INFERRED` (cu scor de încredere) sau `AMBIGUOUS`.

## Instalare

**Cerințe:** Python 3.10+ și unul din: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com) și altele.

```bash
uv tool install graphifyy && graphify install
# sau cu pipx
pipx install graphifyy && graphify install
# sau pip
pip install graphifyy && graphify install
```

> **Pachet oficial:** Pachetul PyPI se numește `graphifyy`. Singurul depozit oficial este [safishamsi/graphify](https://github.com/safishamsi/graphify).

## Utilizare

```
/graphify .
/graphify ./raw --update
/graphify query "ce conectează Attention cu optimizatorul?"
/graphify path "DigestAuth" "Response"
graphify hook install
graphify update ./src
```

## Ce obțineți

**Noduri-zeu** — concepte cu cel mai mare grad · **Conexiuni surprinzătoare** — clasificate după scor · **Întrebări sugerate** · **„De ce"** — docstring-uri și raționale de design extrase ca noduri · **Benchmark token** — **71,5x** mai puțini token pe corpus mixt.

## Confidențialitate

Fișierele de cod sunt procesate local prin tree-sitter AST. Videoclipurile sunt transcrise local cu faster-whisper. Fără telemetrie.

## Construit pe graphify — Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai) este stratul enterprise peste graphify. **Perioadă de probă gratuită în curând.** [Alăturați-vă listei de așteptare →](https://safishamsi.github.io/penpax.ai)

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
