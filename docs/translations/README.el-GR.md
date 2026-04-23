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

**Μια δεξιότητα για βοηθούς κώδικα AI.** Πληκτρολογήστε `/graphify` στο Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro ή Google Antigravity — διαβάζει τα αρχεία σας, δημιουργεί ένα γράφο γνώσης και σας επιστρέφει δομή που δεν ξέρατε ότι υπήρχε. Κατανοήστε μια βάση κώδικα γρηγορότερα. Βρείτε το «γιατί» πίσω από αρχιτεκτονικές αποφάσεις.

Πλήρως πολυτροπικό. Προσθέστε κώδικα, PDF, markdown, στιγμιότυπα οθόνης, διαγράμματα, φωτογραφίες πίνακα, εικόνες σε άλλες γλώσσες ή αρχεία βίντεο και ήχου — το graphify εξάγει έννοιες και σχέσεις από όλα και τα συνδέει σε ένα ενιαίο γράφο. Τα βίντεο μεταγράφονται τοπικά με το Whisper. Υποστηρίζει 25 γλώσσες προγραμματισμού μέσω tree-sitter AST.

> Ο Andrej Karpathy διατηρεί ένα φάκελο `/raw` όπου αποθηκεύει εργασίες, tweets, στιγμιότυπα και σημειώσεις. Το graphify είναι η απάντηση σε αυτό το πρόβλημα — **71,5x** λιγότερα token ανά ερώτημα σε σύγκριση με την ανάγνωση αρχείων, επίμονο μεταξύ συνεδριών.

```
/graphify .
```

```
graphify-out/
├── graph.html       διαδραστικός γράφος — ανοίξτε σε οποιοδήποτε πρόγραμμα περιήγησης
├── GRAPH_REPORT.md  κόμβοι-θεοί, εκπληκτικές συνδέσεις, προτεινόμενες ερωτήσεις
├── graph.json       επίμονος γράφος — μπορεί να υποβληθεί σε ερωτήματα εβδομάδες αργότερα
└── cache/           κρυφή μνήμη SHA256 — επαναλαμβανόμενες εκτελέσεις επεξεργάζονται μόνο τα αλλαγμένα αρχεία
```

## Πώς λειτουργεί

Το graphify λειτουργεί σε τρεις διελεύσεις. Πρώτα, μια ντετερμινιστική διέλευση AST εξάγει δομή από αρχεία κώδικα χωρίς LLM. Στη συνέχεια, τα αρχεία βίντεο και ήχου μεταγράφονται τοπικά με faster-whisper. Τέλος, οι υπο-πράκτορες Claude εκτελούνται παράλληλα σε έγγραφα, εργασίες, εικόνες και μεταγραφές. Τα αποτελέσματα συγχωνεύονται σε ένα γράφο NetworkX, ομαδοποιούνται με Leiden και εξάγονται ως διαδραστική HTML, JSON για ερωτήματα και αναφορά ελέγχου.

Κάθε σχέση επισημαίνεται ως `EXTRACTED`, `INFERRED` (με βαθμολογία εμπιστοσύνης) ή `AMBIGUOUS`.

## Εγκατάσταση

**Απαιτήσεις:** Python 3.10+ και ένα από: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com) και άλλα.

```bash
uv tool install graphifyy && graphify install
# ή με pipx
pipx install graphifyy && graphify install
# ή pip
pip install graphifyy && graphify install
```

> **Επίσημο πακέτο:** Το πακέτο PyPI ονομάζεται `graphifyy`. Το μοναδικό επίσημο αποθετήριο είναι το [safishamsi/graphify](https://github.com/safishamsi/graphify).

## Χρήση

```
/graphify .
/graphify ./raw --update
/graphify query "τι συνδέει το Attention με τον optimizer;"
/graphify path "DigestAuth" "Response"
graphify hook install
graphify update ./src
```

## Τι λαμβάνετε

**Κόμβοι-θεοί** — έννοιες με τον υψηλότερο βαθμό · **Εκπληκτικές συνδέσεις** — ταξινομημένες κατά βαθμολογία · **Προτεινόμενες ερωτήσεις** · **Το «γιατί»** — docstrings και αιτιολόγηση σχεδιασμού εξαγόμενα ως κόμβοι · **Σημείο αναφοράς token** — **71,5x** λιγότερα token σε μικτό σώμα κειμένου.

## Απόρρητο

Τα αρχεία κώδικα επεξεργάζονται τοπικά μέσω tree-sitter AST. Τα βίντεο μεταγράφονται τοπικά με faster-whisper. Χωρίς τηλεμετρία.

## Δημιουργήθηκε στο graphify — Penpax

Το [**Penpax**](https://safishamsi.github.io/penpax.ai) είναι το εταιρικό επίπεδο πάνω από το graphify. **Δωρεάν δοκιμή σύντομα.** [Εγγραφείτε στη λίστα αναμονής →](https://safishamsi.github.io/penpax.ai)

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
