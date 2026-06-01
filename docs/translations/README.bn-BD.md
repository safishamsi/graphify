<p align="center">
  <img src="https://raw.githubusercontent.com/safishamsi/graphify/v4/docs/logo-text.svg" width="260" height="64" alt="Graphify"/>
</p>

<p align="center">
  🇺🇸 <a href="../../README.md">English</a> | 🇨🇳 <a href="README.zh-CN.md">简体中文</a> | 🇯🇵 <a href="README.ja-JP.md">日本語</a> | 🇰🇷 <a href="README.ko-KR.md">한국어</a> | 🇩🇪 <a href="README.de-DE.md">Deutsch</a> | 🇫🇷 <a href="README.fr-FR.md">Français</a> | 🇪🇸 <a href="README.es-ES.md">Español</a> | 🇮🇳 <a href="README.hi-IN.md">हिन्दी</a> | 🇧🇩 <a href="README.bn-BD.md">বাংলা</a> | 🇧🇷 <a href="README.pt-BR.md">Português</a> | 🇷🇺 <a href="README.ru-RU.md">Русский</a> | 🇸🇦 <a href="README.ar-SA.md">العربية</a> | 🇮🇹 <a href="README.it-IT.md">Italiano</a> | 🇵🇱 <a href="README.pl-PL.md">Polski</a> | 🇳🇱 <a href="README.nl-NL.md">Nederlands</a> | 🇹🇷 <a href="README.tr-TR.md">Türkçe</a> | 🇺🇦 <a href="README.uk-UA.md">Українська</a> | 🇻🇳 <a href="README.vi-VN.md">Tiếng Việt</a> | 🇮🇩 <a href="README.id-ID.md">Bahasa Indonesia</a> | 🇸🇪 <a href="README.sv-SE.md">Svenska</a> | 🇬🇷 <a href="README.el-GR.md">Ελληνικά</a> | 🇷🇴 <a href="README.ro-RO.md">Română</a> | 🇨🇿 <a href="README.cs-CZ.md">Čeština</a> | 🇫🇮 <a href="README.fi-FI.md">Suomi</a> | 🇩🇰 <a href="README.da-DK.md">Dansk</a> | 🇳🇴 <a href="README.no-NO.md">Norsk</a> | 🇭🇺 <a href="README.hu-HU.md">Magyar</a> | 🇹🇭 <a href="README.th-TH.md">ภาษาไทย</a> | 🇺🇿 <a href="README.uz-UZ.md">Oʻzbekcha</a> | 🇹🇼 <a href="README.zh-TW.md">繁體中文</a> | 🇵🇭 <a href="README.fil-PH.md">Filipino</a>
</p>

<p align="center">
  <a href="https://github.com/safishamsi/graphify/actions/workflows/ci.yml"><img src="https://github.com/safishamsi/graphify/actions/workflows/ci.yml/badge.svg?branch=v4" alt="CI"/></a>
  <a href="https://pypi.org/project/graphifyy/"><img src="https://img.shields.io/pypi/v/graphifyy" alt="PyPI"/></a>
  <a href="https://pepy.tech/project/graphifyy"><img src="https://static.pepy.tech/badge/graphifyy" alt="Downloads"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://www.linkedin.com/in/safi-shamsi"><img src="https://img.shields.io/badge/LinkedIn-Safi%20Shamsi-0077B5?logo=linkedin" alt="LinkedIn"/></a>
</p>

**একটি AI কোডিং অ্যাসিস্ট্যান্ট স্কিল।** Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro বা Google Antigravity-তে `/graphify` টাইপ করুন — এটি আপনার ফাইল পড়ে, একটি নলেজ গ্রাফ তৈরি করে, এবং আপনি জানতেন না এমন কাঠামো ফিরিয়ে দেয়। কোডবেস দ্রুত বুঝুন। আর্কিটেকচারাল সিদ্ধান্তের পিছনের "কেন" খুঁজে বের করুন।

সম্পূর্ণ মাল্টিমোডাল। কোড, PDF, মার্কডাউন, স্ক্রিনশট, ডায়াগ্রাম, হোয়াইটবোর্ডের ছবি, অন্য ভাষার ছবি, বা ভিডিও ও অডিও ফাইল যোগ করুন — graphify এগুলো থেকে ধারণা ও সম্পর্ক বের করে একটি গ্রাফে জোড়া দেয়। ভিডিও Whisper দিয়ে স্থানীয়ভাবে ট্রান্সক্রাইব হয়। ২৫টি প্রোগ্রামিং ভাষা tree-sitter AST-এর মাধ্যমে সমর্থিত (Python, JS, TS, Go, Rust, Java, C, C++, Ruby, C#, Kotlin, Scala, PHP, Swift, Lua, Zig, PowerShell, Elixir, Objective-C, Julia, Verilog, SystemVerilog, Vue, Svelte, Dart)।

> Andrej Karpathy একটি `/raw` ফোল্ডার রাখেন যেখানে তিনি papers, tweets, স্ক্রিনশট ও নোট রাখেন। graphify সেই সমস্যার সমাধান — raw ফাইল পড়ার তুলনায় প্রতি কোয়েরিতে **৭১.৫x** কম tokens, সেশন জুড়ে স্থায়ী, এবং কী পাওয়া গেছে বনাম অনুমান করা হয়েছে তা স্পষ্ট।

```
/graphify .                        # যেকোনো ফোল্ডারে কাজ করে — কোডবেস, নোট, papers, সবকিছু
```

```
graphify-out/
├── graph.html       ইন্টারঅ্যাক্টিভ গ্রাফ — যেকোনো ব্রাউজারে খুলুন, নোড ক্লিক করুন, খুঁজুন
├── GRAPH_REPORT.md  god নোড, আশ্চর্যজনক সংযোগ, প্রস্তাবিত প্রশ্ন
├── graph.json       স্থায়ী গ্রাফ — সপ্তাহ পরেও কোয়েরি করুন
└── cache/           SHA256 ক্যাশ — পুনরায় চালালে শুধু পরিবর্তিত ফাইল প্রসেস হয়
```

অযাচিত ফোল্ডার বাদ দিতে `.graphifyignore` ফাইল যোগ করুন:

```
# .graphifyignore
vendor/
node_modules/
dist/
*.generated.py
```

`.gitignore`-এর মতোই সিনট্যাক্স।

## এটি কীভাবে কাজ করে

graphify তিন ধাপে চলে। প্রথমে, একটি নির্ধারক AST পাস কোড ফাইল থেকে কাঠামো বের করে — কোনো LLM ছাড়াই। দ্বিতীয়ত, ভিডিও ও অডিও ফাইল faster-whisper দিয়ে স্থানীয়ভাবে ট্রান্সক্রাইব হয়। তৃতীয়ত, Claude সাব-এজেন্টগুলো ডকুমেন্ট, papers, ছবি ও ট্রান্সক্রিপ্টে সমান্তরালে চলে। ফলাফল NetworkX গ্রাফে মার্জ হয়, Leiden কমিউনিটি ডিটেকশন দিয়ে ক্লাস্টার হয়, এবং ইন্টারঅ্যাক্টিভ HTML, কোয়েরিযোগ্য JSON ও একটি অডিট রিপোর্ট হিসেবে এক্সপোর্ট হয়।

**ক্লাস্টারিং গ্রাফ-টপোলজি ভিত্তিক — কোনো embeddings নেই।** Claude-এর বের করা সেমান্টিক সাদৃশ্যের এজ আগে থেকেই গ্রাফে থাকে, তাই সেগুলো কমিউনিটি ডিটেকশনকে সরাসরি প্রভাবিত করে।

প্রতিটি সম্পর্ক `EXTRACTED` (সোর্সে সরাসরি পাওয়া), `INFERRED` (যুক্তিসঙ্গত অনুমান, কনফিডেন্স স্কোরসহ) বা `AMBIGUOUS` (পর্যালোচনার জন্য চিহ্নিত) হিসেবে ট্যাগ করা হয়।

## ইনস্টলেশন

**প্রয়োজনীয়তা:** Python 3.10+ এবং নিম্নলিখিতগুলোর একটি: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com), [Gemini CLI](https://github.com/google-gemini/gemini-cli), [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli), [VS Code Copilot Chat](https://code.visualstudio.com/docs/copilot/overview), [Aider](https://aider.chat), [OpenClaw](https://openclaw.ai), [Factory Droid](https://factory.ai), [Trae](https://trae.ai), [Kiro](https://kiro.dev), Hermes বা [Google Antigravity](https://antigravity.google)

```bash
# সুপারিশকৃত — Mac ও Linux-এ PATH সেটআপ ছাড়াই কাজ করে
uv tool install graphifyy && graphify install
# অথবা pipx দিয়ে
pipx install graphifyy && graphify install
# অথবা সাধারণ pip
pip install graphifyy && graphify install
```

> **অফিসিয়াল প্যাকেজ:** PyPI প্যাকেজের নাম `graphifyy` (`pip install graphifyy` দিয়ে ইনস্টল করুন)। PyPI-তে `graphify*` নামের অন্য প্যাকেজ এই প্রজেক্টের সাথে সম্পর্কিত নয়। একমাত্র অফিসিয়াল রিপোজিটরি [safishamsi/graphify](https://github.com/safishamsi/graphify)।

### প্ল্যাটফর্ম সাপোর্ট

| প্ল্যাটফর্ম | ইনস্টল কমান্ড |
|------------|---------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (স্বয়ং-শনাক্তকরণ) বা `graphify install --platform windows` |
| Codex | `graphify install --platform codex` |
| OpenCode | `graphify install --platform opencode` |
| GitHub Copilot CLI | `graphify install --platform copilot` |
| VS Code Copilot Chat | `graphify vscode install` |
| Aider | `graphify install --platform aider` |
| OpenClaw | `graphify install --platform claw` |
| Factory Droid | `graphify install --platform droid` |
| Trae | `graphify install --platform trae` |
| Gemini CLI | `graphify install --platform gemini` |
| Hermes | `graphify install --platform hermes` |
| Kiro IDE/CLI | `graphify kiro install` |
| Cursor | `graphify cursor install` |
| Google Antigravity | `graphify antigravity install` |

তারপর আপনার AI কোডিং অ্যাসিস্ট্যান্ট খুলে টাইপ করুন:

```
/graphify .
```

## ব্যবহার

```
/graphify                          # বর্তমান ডিরেক্টরি
/graphify ./raw                    # নির্দিষ্ট ফোল্ডার
/graphify ./raw --update           # শুধু পরিবর্তিত ফাইল পুনরায় বের করুন
/graphify ./raw --directed         # দিকনির্দেশিত গ্রাফ
/graphify ./raw --no-viz           # শুধু রিপোর্ট + JSON
/graphify ./raw --obsidian         # Obsidian vault তৈরি করুন

/graphify add https://arxiv.org/abs/1706.03762   # paper আনুন
/graphify add <video-url>                         # ভিডিও ট্রান্সক্রাইব করুন
/graphify query "attention ও optimizer-কে কী যুক্ত করে?"
/graphify path "DigestAuth" "Response"
/graphify explain "SwinTransformer"

graphify hook install              # Git hooks ইনস্টল করুন
graphify update ./src              # কোড ফাইল পুনরায় বের করুন, LLM লাগে না
graphify watch ./src               # স্বয়ংক্রিয় গ্রাফ আপডেট
```

## আপনি যা পাবেন

**God নোড** — সর্বোচ্চ ডিগ্রির ধারণা (যার মধ্য দিয়ে সবকিছু যায়)

**আশ্চর্যজনক সংযোগ** — কম্পোজিট স্কোর অনুযায়ী র‍্যাঙ্ক। কোড-পেপার এজ উচ্চ র‍্যাঙ্ক পায়।

**প্রস্তাবিত প্রশ্ন** — ৪-৫টি প্রশ্ন যা গ্রাফ বিশেষভাবে ভালো উত্তর দিতে পারে

**"কেন"** — docstrings, inline comments ও design rationale `rationale_for` নোড হিসেবে বের করা হয়।

**কনফিডেন্স স্কোর** — প্রতিটি INFERRED এজের `confidence_score` (০.০-১.০) থাকে।

**টোকেন বেঞ্চমার্ক** — প্রতিটি রানের পর স্বয়ংক্রিয়ভাবে প্রিন্ট হয়। মিশ্র corpus-এ: raw ফাইলের তুলনায় **৭১.৫x** কম tokens।

## গোপনীয়তা

graphify ডকুমেন্ট, papers ও ছবির সেমান্টিক এক্সট্র্যাকশনের জন্য আপনার AI অ্যাসিস্ট্যান্টের মডেল API-তে ফাইলের বিষয়বস্তু পাঠায়। কোড ফাইল tree-sitter AST-এর মাধ্যমে স্থানীয়ভাবে প্রসেস হয়। ভিডিও ও অডিও ফাইল faster-whisper দিয়ে স্থানীয়ভাবে ট্রান্সক্রাইব হয়। কোনো টেলিমেট্রি নেই, কোনো ট্র্যাকিং নেই।

## graphify-এর উপর নির্মিত — Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai) graphify-এর উপর এন্টারপ্রাইজ লেয়ার। যেখানে graphify একটি ফোল্ডারের ফাইলকে নলেজ গ্রাফে রূপান্তর করে, Penpax সেই গ্রাফ আপনার পুরো কাজের জীবনে প্রয়োগ করে — ক্রমাগত।

**ফ্রি ট্রায়াল শীঘ্রই চালু হবে।** [ওয়েটলিস্টে যোগ দিন →](https://safishamsi.github.io/penpax.ai)

## Star ইতিহাস

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
