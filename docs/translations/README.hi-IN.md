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
  <a href="https://www.linkedin.com/in/safi-shamsi"><img src="https://img.shields.io/badge/LinkedIn-Safi%20Shamsi-0077B5?logo=linkedin" alt="LinkedIn"/></a>
</p>

**एक AI कोडिंग असिस्टेंट स्किल।** Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro या Google Antigravity में `/graphify` टाइप करें — यह आपकी फ़ाइलें पढ़ता है, एक नॉलेज ग्राफ बनाता है, और आपको वह संरचना वापस देता है जो आप नहीं जानते थे कि मौजूद है। कोडबेस को तेज़ी से समझें। आर्किटेक्चरल निर्णयों के पीछे का "क्यों" खोजें।

पूरी तरह मल्टीमोडल। कोड, PDFs, मार्कडाउन, स्क्रीनशॉट, डायग्राम, व्हाइटबोर्ड फोटो, अन्य भाषाओं में छवियां, या वीडियो और ऑडियो फ़ाइलें डालें — graphify इन सभी से अवधारणाएं और संबंध निकालता है और उन्हें एक ग्राफ में जोड़ता है। वीडियो को Whisper से स्थानीय रूप से ट्रांसक्राइब किया जाता है। 25 प्रोग्रामिंग भाषाएं tree-sitter AST के माध्यम से समर्थित हैं (Python, JS, TS, Go, Rust, Java, C, C++, Ruby, C#, Kotlin, Scala, PHP, Swift, Lua, Zig, PowerShell, Elixir, Objective-C, Julia, Verilog, SystemVerilog, Vue, Svelte, Dart)।

> Andrej Karpathy एक `/raw` फोल्डर रखते हैं जहां वह papers, tweets, स्क्रीनशॉट और नोट्स डालते हैं। graphify उस समस्या का जवाब है — रॉ फ़ाइलें पढ़ने की तुलना में प्रति क्वेरी **71.5x** कम tokens, सत्रों में स्थायी, ईमानदार कि क्या पाया गया बनाम अनुमान लगाया गया।

```
/graphify .                        # किसी भी फोल्डर पर काम करता है — कोडबेस, नोट्स, papers, सब कुछ
```

```
graphify-out/
├── graph.html       इंटरेक्टिव ग्राफ — किसी भी ब्राउज़र में खोलें, नोड्स क्लिक करें, खोजें
├── GRAPH_REPORT.md  गॉड नोड्स, आश्चर्यजनक कनेक्शन, सुझाए गए प्रश्न
├── graph.json       स्थायी ग्राफ — हफ्तों बाद भी क्वेरी करें
└── cache/           SHA256 कैश — पुनः चलाने पर केवल बदली हुई फ़ाइलें प्रोसेस होती हैं
```

अनचाहे फोल्डर को बाहर करने के लिए `.graphifyignore` फ़ाइल जोड़ें:

```
# .graphifyignore
vendor/
node_modules/
dist/
*.generated.py
```

`.gitignore` जैसी ही सिंटेक्स।

## यह कैसे काम करता है

graphify तीन चरणों में चलता है। पहले, एक निर्धारक AST पास कोड फ़ाइलों से संरचना निकालता है — बिना किसी LLM के। दूसरे, वीडियो और ऑडियो फ़ाइलों को faster-whisper से स्थानीय रूप से ट्रांसक्राइब किया जाता है। तीसरे, Claude सबएजेंट दस्तावेज़ों, papers, छवियों और ट्रांसक्रिप्ट पर समानांतर में चलते हैं। परिणामों को NetworkX ग्राफ में मर्ज किया जाता है, Leiden कम्युनिटी डिटेक्शन से क्लस्टर किया जाता है, और इंटरेक्टिव HTML, क्वेरी करने योग्य JSON और एक ऑडिट रिपोर्ट के रूप में निर्यात किया जाता है।

**क्लस्टरिंग ग्राफ-टोपोलॉजी आधारित है — कोई embeddings नहीं।** Claude द्वारा निकाले गए सिमेंटिक समानता किनारे पहले से ग्राफ में हैं, इसलिए वे कम्युनिटी डिटेक्शन को सीधे प्रभावित करते हैं।

प्रत्येक संबंध `EXTRACTED` (स्रोत में सीधे पाया गया), `INFERRED` (उचित अनुमान, कॉन्फिडेंस स्कोर के साथ) या `AMBIGUOUS` (समीक्षा के लिए चिह्नित) के रूप में टैग किया जाता है।

## इंस्टॉलेशन

**आवश्यकताएं:** Python 3.10+ और निम्न में से एक: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com), [Gemini CLI](https://github.com/google-gemini/gemini-cli), [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli), [VS Code Copilot Chat](https://code.visualstudio.com/docs/copilot/overview), [Aider](https://aider.chat), [OpenClaw](https://openclaw.ai), [Factory Droid](https://factory.ai), [Trae](https://trae.ai), [Kiro](https://kiro.dev), Hermes या [Google Antigravity](https://antigravity.google)

```bash
# अनुशंसित — Mac और Linux पर PATH सेटअप के बिना काम करता है
uv tool install graphifyy && graphify install
# या pipx के साथ
pipx install graphifyy && graphify install
# या सामान्य pip
pip install graphifyy && graphify install
```

> **आधिकारिक पैकेज:** PyPI पैकेज का नाम `graphifyy` है (`pip install graphifyy` से इंस्टॉल करें)। PyPI पर `graphify*` नाम वाले अन्य पैकेज इस प्रोजेक्ट से संबद्ध नहीं हैं। एकमात्र आधिकारिक रिपॉजिटरी [safishamsi/graphify](https://github.com/safishamsi/graphify) है।

### प्लेटफॉर्म समर्थन

| प्लेटफॉर्म | इंस्टॉल कमांड |
|------------|---------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (स्वतः-पहचान) या `graphify install --platform windows` |
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

फिर अपना AI कोडिंग असिस्टेंट खोलें और टाइप करें:

```
/graphify .
```

## उपयोग

```
/graphify                          # वर्तमान डायरेक्टरी
/graphify ./raw                    # विशिष्ट फोल्डर
/graphify ./raw --update           # केवल बदली हुई फ़ाइलें फिर से निकालें
/graphify ./raw --directed         # निर्देशित ग्राफ
/graphify ./raw --no-viz           # केवल रिपोर्ट + JSON
/graphify ./raw --obsidian         # Obsidian vault बनाएं

/graphify add https://arxiv.org/abs/1706.03762   # paper प्राप्त करें
/graphify add <video-url>                         # वीडियो ट्रांसक्राइब करें
/graphify query "attention और optimizer को क्या जोड़ता है?"
/graphify path "DigestAuth" "Response"
/graphify explain "SwinTransformer"

graphify hook install              # Git hooks इंस्टॉल करें
graphify update ./src              # कोड फ़ाइलें पुनः निकालें, LLM की जरूरत नहीं
graphify watch ./src               # स्वचालित ग्राफ अपडेट
```

## आपको क्या मिलता है

**गॉड नोड्स** — सबसे अधिक डिग्री वाली अवधारणाएं (जिनसे सब कुछ गुजरता है)

**आश्चर्यजनक कनेक्शन** — कम्पोजिट स्कोर द्वारा रैंक किए गए। कोड-पेपर किनारे उच्च रैंक पाते हैं।

**सुझाए गए प्रश्न** — 4-5 प्रश्न जिन्हें ग्राफ विशेष रूप से अच्छी तरह उत्तर दे सकता है

**"क्यों"** — docstrings, inline comments, और design rationale को `rationale_for` नोड्स के रूप में निकाला जाता है।

**कॉन्फिडेंस स्कोर** — प्रत्येक INFERRED किनारे का `confidence_score` (0.0-1.0) होता है।

**टोकन बेंचमार्क** — प्रत्येक रन के बाद स्वचालित रूप से प्रिंट होता है। मिश्रित corpus पर: रॉ फ़ाइलों की तुलना में **71.5x** कम tokens।

## गोपनीयता

graphify दस्तावेज़ों, papers और छवियों के सिमेंटिक निष्कर्षण के लिए आपके AI असिस्टेंट की मॉडल API को फ़ाइल सामग्री भेजता है। कोड फ़ाइलें tree-sitter AST के माध्यम से स्थानीय रूप से प्रोसेस होती हैं। वीडियो और ऑडियो फ़ाइलें faster-whisper से स्थानीय रूप से ट्रांसक्राइब होती हैं। कोई टेलीमेट्री नहीं, कोई ट्रैकिंग नहीं।

## graphify पर बनाया — Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai) graphify के ऊपर एंटरप्राइज़ लेयर है। जहां graphify फ़ाइलों के एक फोल्डर को नॉलेज ग्राफ में बदलता है, Penpax वही ग्राफ आपके पूरे कार्य जीवन पर लागू करता है — निरंतर।

**फ्री ट्रायल जल्द लॉन्च होगा।** [वेटलिस्ट में शामिल हों →](https://safishamsi.github.io/penpax.ai)

## Star इतिहास

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
