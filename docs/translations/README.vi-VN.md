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

**Kỹ năng dành cho trợ lý lập trình AI.** Gõ `/graphify` trong Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro hoặc Google Antigravity — nó đọc các tệp của bạn, xây dựng đồ thị kiến thức và trả lại cho bạn cấu trúc mà bạn không biết là tồn tại. Hiểu codebase nhanh hơn. Tìm ra "tại sao" đằng sau các quyết định kiến trúc.

Hoàn toàn đa phương thức. Thêm code, PDF, markdown, ảnh chụp màn hình, sơ đồ, ảnh bảng trắng, hình ảnh bằng ngôn ngữ khác hoặc tệp video và âm thanh — graphify trích xuất các khái niệm và mối quan hệ từ tất cả mọi thứ và kết nối chúng trong một đồ thị duy nhất. Video được phiên âm cục bộ bằng Whisper. Hỗ trợ 25 ngôn ngữ lập trình qua tree-sitter AST.

> Andrej Karpathy duy trì một thư mục `/raw` nơi anh ấy đặt các bài báo, tweet, ảnh chụp màn hình và ghi chú. graphify là câu trả lời cho vấn đề đó — **71,5x** ít token hơn trên mỗi truy vấn so với đọc các tệp thô, liên tục giữa các phiên.

```
/graphify .
```

```
graphify-out/
├── graph.html       đồ thị tương tác — mở trong bất kỳ trình duyệt nào
├── GRAPH_REPORT.md  nút thần, kết nối bất ngờ, câu hỏi được đề xuất
├── graph.json       đồ thị liên tục — có thể truy vấn sau nhiều tuần
└── cache/           bộ nhớ đệm SHA256 — các lần chạy lại chỉ xử lý các tệp đã thay đổi
```

## Cách hoạt động

graphify hoạt động theo ba lần duyệt. Đầu tiên, một lần duyệt AST xác định trích xuất cấu trúc từ các tệp code mà không cần LLM. Sau đó, các tệp video và âm thanh được phiên âm cục bộ bằng faster-whisper. Cuối cùng, các sub-agent Claude chạy song song trên các tài liệu, bài báo, hình ảnh và bản phiên âm. Kết quả được hợp nhất vào đồ thị NetworkX, phân cụm với Leiden và xuất dưới dạng HTML tương tác, JSON có thể truy vấn và báo cáo kiểm tra.

Mỗi mối quan hệ được gắn nhãn `EXTRACTED`, `INFERRED` (với điểm tin cậy) hoặc `AMBIGUOUS`.

## Cài đặt

**Yêu cầu:** Python 3.10+ và một trong: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com) và các công cụ khác.

```bash
uv tool install graphifyy && graphify install
# hoặc với pipx
pipx install graphifyy && graphify install
# hoặc pip
pip install graphifyy && graphify install
```

> **Gói chính thức:** Gói PyPI có tên là `graphifyy`. Kho lưu trữ chính thức duy nhất là [safishamsi/graphify](https://github.com/safishamsi/graphify).

## Sử dụng

```
/graphify .
/graphify ./raw --update
/graphify query "điều gì kết nối Attention với optimizer?"
/graphify path "DigestAuth" "Response"
graphify hook install
graphify update ./src
```

## Những gì bạn nhận được

**Nút thần** — các khái niệm có bậc cao nhất · **Kết nối bất ngờ** — được xếp hạng theo điểm · **Câu hỏi được đề xuất** · **"Tại sao"** — docstring và lý do thiết kế được trích xuất dưới dạng nút · **Benchmark token** — **71,5x** ít token hơn trên corpus hỗn hợp.

## Quyền riêng tư

Các tệp code được xử lý cục bộ qua tree-sitter AST. Video được phiên âm cục bộ với faster-whisper. Không có telemetry.

## Được xây dựng trên graphify — Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai) là lớp doanh nghiệp trên graphify. **Dùng thử miễn phí sắp ra mắt.** [Tham gia danh sách chờ →](https://safishamsi.github.io/penpax.ai)

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
