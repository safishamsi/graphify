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

**Taito tekoälykoodiavustajille.** Kirjoita `/graphify` Claude Codessa, Codexissa, OpenCodessa, Cursorissa, Gemini CLI:ssä, GitHub Copilot CLI:ssä, VS Code Copilot Chatissa, Aiderissa, OpenClawissa, Factory Droidissa, Traessa, Hermeksessä, Kirossa tai Google Antigravityssa — se lukee tiedostosi, rakentaa tietograafin ja palauttaa sinulle rakenteen, jota et tiennyt olevan. Ymmärrä koodikanta nopeammin. Löydä arkkitehtuuripäätösten taustalla oleva "miksi".

Täysin multimodaalinen. Lisää koodia, PDF:iä, markdownia, kuvakaappauksia, kaavioita, liitutaulun valokuvia, muilla kielillä olevia kuvia tai video- ja äänitiedostoja — graphify poimii käsitteitä ja suhteita kaikesta ja yhdistää ne yhdeksi graafaksi. Videot litteroidaan paikallisesti Whisperillä. Tukee 25 ohjelmointikieltä tree-sitter AST:n kautta.

> Andrej Karpathy ylläpitää `/raw`-kansiota, johon hän tallentaa papereita, tviittejä, kuvakaappauksia ja muistiinpanoja. graphify on vastaus tähän ongelmaan — **71,5x** vähemmän tokeneita kyselyä kohden verrattuna raakatiedostojen lukemiseen, pysyvä istuntojen välillä.

```
/graphify .
```

```
graphify-out/
├── graph.html       interaktiivinen graafi — avaa missä tahansa selaimessa
├── GRAPH_REPORT.md  jumalsolmut, yllättävät yhteydet, ehdotetut kysymykset
├── graph.json       pysyvä graafi — kyselytavissa viikkojen kuluttua
└── cache/           SHA256-välimuisti — toistuvat ajot käsittelevät vain muuttuneet tiedostot
```

## Miten se toimii

graphify toimii kolmessa läpiajossa. Ensin deterministinen AST-läpiajo poimii rakenteen kooditiedostoista ilman LLM:ää. Sitten video- ja äänitiedostot litteroidaan paikallisesti faster-whisperillä. Lopuksi Clauden ala-agentit suoritetaan rinnakkain asiakirjoissa, papereissa, kuvissa ja litteroinneissa. Tulokset yhdistetään NetworkX-graafiin, klusteroidaan Leidenillä ja viedään interaktiivisena HTML:nä, kyselytavissa olevana JSON:na ja tarkastusraporttina.

Jokainen suhde on merkitty `EXTRACTED`, `INFERRED` (luottamuspisteineen) tai `AMBIGUOUS`.

## Asennus

**Vaatimukset:** Python 3.10+ ja jokin seuraavista: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com) ja muut.

```bash
uv tool install graphifyy && graphify install
# tai pipx:llä
pipx install graphifyy && graphify install
# tai pip
pip install graphifyy && graphify install
```

> **Virallinen paketti:** PyPI-paketti on nimeltään `graphifyy`. Ainoa virallinen repositorio on [safishamsi/graphify](https://github.com/safishamsi/graphify).

## Käyttö

```
/graphify .
/graphify ./raw --update
/graphify query "mikä yhdistää Attentionin optimizeriin?"
/graphify path "DigestAuth" "Response"
graphify hook install
graphify update ./src
```

## Mitä saat

**Jumalsolmut** — korkeimman asteen käsitteet · **Yllättävät yhteydet** — pisteiden mukaan järjestetty · **Ehdotetut kysymykset** · **"Miksi"** — docstringit ja suunnitteluperusteet solmuina · **Token-vertailu** — **71,5x** vähemmän tokeneita sekakorpuksessa.

## Yksityisyys

Kooditiedostot käsitellään paikallisesti tree-sitter AST:n kautta. Videot litteroidaan paikallisesti faster-whisperillä. Ei telemetriaa.

## Rakennettu graphifyn päälle — Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai) on graphifyn päälle rakennettu yritystaso. **Ilmainen kokeilujakso tulossa pian.** [Liity odotuslistalle →](https://safishamsi.github.io/penpax.ai)

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
