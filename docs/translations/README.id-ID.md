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

**Keterampilan untuk asisten kode AI.** Ketik `/graphify` di Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro, atau Google Antigravity — membaca file Anda, membangun graf pengetahuan, dan mengembalikan struktur yang tidak Anda ketahui ada. Pahami codebase lebih cepat. Temukan "mengapa" di balik keputusan arsitektur.

Sepenuhnya multimodal. Tambahkan kode, PDF, markdown, tangkapan layar, diagram, foto papan tulis, gambar dalam bahasa lain, atau file video dan audio — graphify mengekstrak konsep dan hubungan dari semuanya dan menghubungkannya dalam satu graf. Video ditranskrip secara lokal dengan Whisper. Mendukung 25 bahasa pemrograman melalui tree-sitter AST.

> Andrej Karpathy memelihara folder `/raw` tempat ia menyimpan makalah, tweet, tangkapan layar, dan catatan. graphify adalah jawaban untuk masalah itu — **71,5x** lebih sedikit token per kueri dibandingkan membaca file mentah, persisten di antara sesi.

```
/graphify .
```

```
graphify-out/
├── graph.html       graf interaktif — buka di browser mana saja
├── GRAPH_REPORT.md  node dewa, koneksi mengejutkan, pertanyaan yang disarankan
├── graph.json       graf persisten — dapat dikueri berminggu-minggu kemudian
└── cache/           cache SHA256 — pengulangan hanya memproses file yang berubah
```

## Cara Kerja

graphify bekerja dalam tiga tahap. Pertama, tahap AST deterministik mengekstrak struktur dari file kode tanpa LLM. Kemudian file video dan audio ditranskrip secara lokal dengan faster-whisper. Terakhir, sub-agen Claude berjalan secara paralel pada dokumen, makalah, gambar, dan transkripsi. Hasilnya digabungkan ke dalam graf NetworkX, dikelompokkan dengan Leiden, dan diekspor sebagai HTML interaktif, JSON yang dapat dikueri, dan laporan audit.

Setiap hubungan diberi label `EXTRACTED`, `INFERRED` (dengan skor kepercayaan), atau `AMBIGUOUS`.

## Instalasi

**Persyaratan:** Python 3.10+ dan salah satu dari: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com) dan lainnya.

```bash
uv tool install graphifyy && graphify install
# atau dengan pipx
pipx install graphifyy && graphify install
# atau pip
pip install graphifyy && graphify install
```

> **Paket resmi:** Paket PyPI bernama `graphifyy`. Satu-satunya repositori resmi adalah [safishamsi/graphify](https://github.com/safishamsi/graphify).

## Penggunaan

```
/graphify .
/graphify ./raw --update
/graphify query "apa yang menghubungkan Attention dengan optimizer?"
/graphify path "DigestAuth" "Response"
graphify hook install
graphify update ./src
```

## Apa yang Anda Dapatkan

**Node dewa** — konsep dengan derajat tertinggi · **Koneksi mengejutkan** — diurutkan berdasarkan skor · **Pertanyaan yang disarankan** · **"Mengapa"** — docstring dan alasan desain diekstrak sebagai node · **Benchmark token** — **71,5x** lebih sedikit token pada corpus campuran.

## Privasi

File kode diproses secara lokal melalui tree-sitter AST. Video ditranskrip secara lokal dengan faster-whisper. Tidak ada telemetri.

## Dibangun di atas graphify — Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai) adalah lapisan enterprise di atas graphify. **Uji coba gratis segera hadir.** [Bergabunglah dengan daftar tunggu →](https://safishamsi.github.io/penpax.ai)

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
