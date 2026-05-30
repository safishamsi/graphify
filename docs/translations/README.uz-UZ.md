<p align="center">
  <img src="https://raw.githubusercontent.com/safishamsi/graphify/v4/docs/logo-text.svg" width="260" height="64" alt="Graphify"/>
</p>

<p align="center">
  🇺🇸 <a href="../../README.md">English</a> | 🇨🇳 <a href="README.zh-CN.md">简体中文</a> | 🇯🇵 <a href="README.ja-JP.md">日本語</a> | 🇰🇷 <a href="README.ko-KR.md">한국어</a> | 🇩🇪 <a href="README.de-DE.md">Deutsch</a> | 🇫🇷 <a href="README.fr-FR.md">Français</a> | 🇪🇸 <a href="README.es-ES.md">Español</a> | 🇮🇳 <a href="README.hi-IN.md">हिन्दी</a> | 🇧🇷 <a href="README.pt-BR.md">Português</a> | 🇷🇺 <a href="README.ru-RU.md">Русский</a> | 🇸🇦 <a href="README.ar-SA.md">العربية</a> | 🇮🇹 <a href="README.it-IT.md">Italiano</a> | 🇵🇱 <a href="README.pl-PL.md">Polski</a> | 🇳🇱 <a href="README.nl-NL.md">Nederlands</a> | 🇹🇷 <a href="README.tr-TR.md">Türkçe</a> | 🇺🇦 <a href="README.uk-UA.md">Українська</a> | 🇻🇳 <a href="README.vi-VN.md">Tiếng Việt</a> | 🇮🇩 <a href="README.id-ID.md">Bahasa Indonesia</a> | 🇸🇪 <a href="README.sv-SE.md">Svenska</a> | 🇬🇷 <a href="README.el-GR.md">Ελληνικά</a> | 🇷🇴 <a href="README.ro-RO.md">Română</a> | 🇨🇿 <a href="README.cs-CZ.md">Čeština</a> | 🇫🇮 <a href="README.fi-FI.md">Suomi</a> | 🇩🇰 <a href="README.da-DK.md">Dansk</a> | 🇳🇴 <a href="README.no-NO.md">Norsk</a> | 🇭🇺 <a href="README.hu-HU.md">Magyar</a> | 🇹🇭 <a href="README.th-TH.md">ภาษาไทย</a> | 🇺🇿 <a href="README.uz-UZ.md">Oʻzbekcha</a> | 🇹🇼 <a href="README.zh-TW.md">繁體中文</a>
</p>

<p align="center">
  <a href="https://github.com/safishamsi/graphify/actions/workflows/ci.yml"><img src="https://github.com/safishamsi/graphify/actions/workflows/ci.yml/badge.svg?branch=v4" alt="CI"/></a>
  <a href="https://pypi.org/project/graphifyy/"><img src="https://img.shields.io/pypi/v/graphifyy" alt="PyPI"/></a>
  <a href="https://pepy.tech/project/graphifyy"><img src="https://static.pepy.tech/badge/graphifyy" alt="Downloads"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://www.linkedin.com/in/safi-shamsi"><img src="https://img.shields.io/badge/LinkedIn-Safi%20Shamsi-0077B5?logo=linkedin" alt="LinkedIn"/></a>
</p>

**Sun'iy intellektga asoslangan kod yordamchilari uchun ko'nikma.** Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro yoki Google Antigravity da `/graphify` deb yozing — u sizning fayllaringizni o'qiydi, bilim grafini quradi va siz bilmagan tuzilmani sizga qaytaradi. Kod bazasini tezroq tushuning. Arxitektura qarorlari ortidagi "nima uchun" savoliga javob toping.

To'liq multimodal. Kod, PDF, markdown, ekran tasvirlari, diagrammalar, doska suratlari, boshqa tillardagi tasvirlar, video va audio fayllarni qo'shing — graphify ularning barchasidan tushuncha va aloqalarni chiqarib, bitta grafga birlashtiradi. Videolar Whisper yordamida mahalliy ravishda transkripsiya qilinadi, sizning korpusingizdan olingan domen-maxsus so'rov bilan. tree-sitter AST orqali 25 ta dasturlash tilini qo'llab-quvvatlaydi (Python, JS, TS, Go, Rust, Java, C, C++, Ruby, C#, Kotlin, Scala, PHP, Swift, Lua, Zig, PowerShell, Elixir, Objective-C, Julia, Verilog, SystemVerilog, Vue, Svelte, Dart).

> Andrej Karpati maqolalar, tvitlar, ekran tasvirlari va eslatmalarni saqlaydigan `/raw` papkasini yuritadi. graphify ushbu muammoga javob — xom fayllarni o'qishga nisbatan har bir so'rov uchun **71,5 marta** kamroq token, sessiyalar orasida saqlanadi, topilgan va xulosa qilinganlar haqida halol.

```
/graphify .                        # istalgan papka bilan ishlaydi — kod, eslatmalar, maqolalar, hammasi
```

```
graphify-out/
├── graph.html       interaktiv graf — brauzerda oching, tugunlarni bosing, qidiring, filtrlang
├── GRAPH_REPORT.md  god-tugunlar, kutilmagan aloqalar, taklif qilingan savollar
├── graph.json       doimiy graf — haftalardan keyin qayta o'qimasdan so'rov qiling
└── cache/           SHA256-kesh — qayta ishga tushirish faqat o'zgargan fayllarni qayta ishlaydi
```

Papkalarni istisno qilish uchun `.graphifyignore` faylini qo'shing:

```
# .graphifyignore
vendor/
node_modules/
dist/
*.generated.py
```

Sintaksisi `.gitignore` ga o'xshash.

## Qanday ishlaydi

graphify uch bosqichda ishlaydi. Birinchi navbatda, deterministik AST bosqichi kod fayllaridan tuzilmani chiqaradi (klasslar, funksiyalar, importlar, chaqiruv graflari, docstring lar, sabab izohlari) — LLM ishtirokisiz. Keyin video va audio fayllar faster-whisper yordamida mahalliy ravishda transkripsiya qilinadi. Nihoyat, Claude subagentlari hujjatlar, maqolalar, tasvirlar va transkriptlar ustida parallel ishlab, tushunchalar, aloqalar va dizayn asoslarini chiqarib oladi. Natijalar NetworkX grafiga birlashtiriladi, Leiden hamjamiyat aniqlash algoritmi bilan klasterlanadi va interaktiv HTML, so'rov qilinadigan JSON hamda tabiiy tildagi audit hisoboti sifatida eksport qilinadi.

**Klasterlash graf topologiyasiga asoslangan — embedding ishlatilmaydi.** Leiden hamjamiyatlarni qirralar zichligi bo'yicha topadi. Claude tomonidan chiqarilgan semantik o'xshashlik qirralari (`semantically_similar_to`, INFERRED deb belgilangan) allaqachon grafda. Graf tuzilmasining o'zi o'xshashlik signali. Alohida embedding bosqichi yoki vektor ma'lumotlar bazasi shart emas.

Har bir aloqa `EXTRACTED` (manbada to'g'ridan-to'g'ri topilgan), `INFERRED` (ishonch bahosi bilan asoslangan xulosa) yoki `AMBIGUOUS` (tekshirish uchun belgilangan) deb teglanadi.

## O'rnatish

**Talablar:** Python 3.10+ va quyidagilardan biri: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com), [Gemini CLI](https://github.com/google-gemini/gemini-cli), [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli), [VS Code Copilot Chat](https://code.visualstudio.com/docs/copilot/overview), [Aider](https://aider.chat), [OpenClaw](https://openclaw.ai), [Factory Droid](https://factory.ai), [Trae](https://trae.ai), [Kiro](https://kiro.dev), Hermes yoki [Google Antigravity](https://antigravity.google)

```bash
# Tavsiya etiladi — Mac va Linux da PATH ni sozlashsiz ishlaydi
uv tool install graphifyy && graphify install
# yoki pipx bilan
pipx install graphifyy && graphify install
# yoki oddiy pip
pip install graphifyy && graphify install
```

> **Rasmiy paket:** PyPI dagi paket nomi `graphifyy` (`pip install graphifyy` orqali o'rnatiladi). PyPI dagi boshqa `graphify*` nomli paketlar bu loyiha bilan bog'liq emas. Yagona rasmiy repozitoriy — [safishamsi/graphify](https://github.com/safishamsi/graphify).

### Platforma qo'llab-quvvatlash

| Platforma | O'rnatish buyrug'i |
|-----------|--------------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (avto-aniqlash) yoki `graphify install --platform windows` |
| Codex | `graphify install --platform codex` |
| OpenCode | `graphify install --platform opencode` |
| GitHub Copilot CLI | `graphify install --platform copilot` |
| VS Code Copilot Chat | `graphify vscode install` |
| Aider | `graphify install --platform aider` |
| OpenClaw | `graphify install --platform claw` |
| Factory Droid | `graphify install --platform droid` |
| Trae | `graphify install --platform trae` |
| Trae CN | `graphify install --platform trae-cn` |
| Gemini CLI | `graphify install --platform gemini` |
| Hermes | `graphify install --platform hermes` |
| Kiro IDE/CLI | `graphify kiro install` |
| Cursor | `graphify cursor install` |
| Google Antigravity | `graphify antigravity install` |

Keyin AI yordamchingizni oching va kiriting:

```
/graphify .
```

Eslatma: Codex ko'nikmalar uchun `/` o'rniga `$` ishlatadi, shuning uchun `$graphify .` deb kiriting.

### Yordamchini har doim grafdan foydalanishga majbur qilish (tavsiya etiladi)

Graf qurilgandan so'ng, loyihangizda buni bir marta bajaring:

| Platforma | Buyruq |
|-----------|--------|
| Claude Code | `graphify claude install` |
| Codex | `graphify codex install` |
| OpenCode | `graphify opencode install` |
| Cursor | `graphify cursor install` |
| Gemini CLI | `graphify gemini install` |
| Kiro IDE/CLI | `graphify kiro install` |
| Google Antigravity | `graphify antigravity install` |

## Foydalanish

```
/graphify                          # joriy katalog
/graphify ./raw                    # ma'lum bir papka
/graphify ./raw --mode deep        # INFERRED qirralarini agressivroq chiqarish
/graphify ./raw --update           # faqat o'zgargan fayllarni qayta chiqarish
/graphify ./raw --directed         # yo'naltirilgan graf
/graphify ./raw --cluster-only     # mavjud grafda klasterlashni qayta ishga tushirish
/graphify ./raw --no-viz           # HTML siz, faqat hisobot + JSON
/graphify ./raw --obsidian         # Obsidian vault yaratish (opsional)

/graphify add https://arxiv.org/abs/1706.03762   # maqolani olish
/graphify add <video-url>                         # audio yuklab olish, transkripsiya qilish va qo'shish
/graphify query "Attention ni optimallashtiruvchi bilan nima bog'laydi?"
/graphify path "DigestAuth" "Response"
/graphify explain "SwinTransformer"

graphify hook install              # Git ilgaklarini o'rnatish
graphify update ./src              # kod fayllarini qayta chiqarish, LLM siz
graphify watch ./src               # grafni avtomatik yangilash
```

## Nima olasiz

**God-tugunlar** — eng yuqori darajadagi tushunchalar (hamma narsa ular orqali o'tadi)

**Kutilmagan aloqalar** — qo'shma ball bo'yicha tartiblangan. Kod-maqola qirralari yuqoriroq baholanadi. Har bir natijada tabiiy tildagi "nima uchun" tushuntirishi bor.

**Taklif qilingan savollar** — graf alohida javob bera oladigan 4-5 ta savol

**"Nima uchun"** — docstring lar, ichki izohlar (`# NOTE:`, `# IMPORTANT:`, `# HACK:`, `# WHY:`) va hujjatlardagi dizayn asoslari `rationale_for` tugunlari sifatida chiqariladi.

**Ishonch ballari** — har bir INFERRED qirrasida `confidence_score` (0,0-1,0) mavjud.

**Token benchmark** — har bir ishga tushirishdan keyin avtomatik chiqariladi. Aralash korpusda: so'rov uchun **71,5 marta** kamroq token, xom fayllarga nisbatan.

**Avto-sinxronlash** (`--watch`) — kod o'zgarganida grafni avtomatik yangilaydi.

**Git ilgaklari** (`graphify hook install`) — post-commit va post-checkout ilgaklarini o'rnatadi.

## Maxfiylik

graphify hujjatlar, maqolalar va tasvirlardan semantik chiqarish uchun fayl mazmunini AI yordamchingizning model API siga yuboradi. Kod fayllari tree-sitter AST orqali mahalliy ravishda qayta ishlanadi. Video va audio fayllar faster-whisper bilan mahalliy ravishda transkripsiya qilinadi. Hech qanday telemetriya, foydalanishni kuzatish yo'q.

## Texnologiyalar to'plami

NetworkX + Leiden (graspologic) + tree-sitter + vis.js. Semantik chiqarish Claude, GPT-4 yoki sizning platformangiz modeli orqali. Video transkripsiyasi faster-whisper + yt-dlp orqali (opsional).

## graphify ustida qurilgan — Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai) — graphify ustidagi korporativ qatlam. graphify fayllar papkasini bilim grafiga aylantirganidek, Penpax o'sha yondashuvni butun ish hayotingizga uzluksiz qo'llaydi.

**Tez orada bepul sinov muddati.** [Kutish ro'yxatiga qo'shiling →](https://safishamsi.github.io/penpax.ai)

## Yulduzlar tarixi

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
