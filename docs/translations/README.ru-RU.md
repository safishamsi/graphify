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

**Навык для AI-ассистента по написанию кода.** Введите `/graphify` в Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro или Google Antigravity — он прочитает ваши файлы, построит граф знаний и вернёт вам структуру, о существовании которой вы не подозревали. Понимайте кодовую базу быстрее. Находите «почему» за архитектурными решениями.

Полностью мультимодальный. Добавляйте код, PDF, markdown, скриншоты, диаграммы, фотографии досок, изображения на других языках, видео и аудиофайлы — graphify извлекает концепции и связи из всего этого и объединяет их в один граф. Видео транскрибируются локально с Whisper, используя доменный промпт из вашего корпуса. Поддерживается 25 языков программирования через tree-sitter AST (Python, JS, TS, Go, Rust, Java, C, C++, Ruby, C#, Kotlin, Scala, PHP, Swift, Lua, Zig, PowerShell, Elixir, Objective-C, Julia, Verilog, SystemVerilog, Vue, Svelte, Dart).

> Андрей Карпати ведёт папку `/raw`, куда складывает статьи, твиты, скриншоты и заметки. graphify — ответ на эту проблему: в **71,5 раза** меньше токенов на запрос по сравнению с чтением сырых файлов, сохранение между сессиями, честность относительно того, что найдено, а что выведено.

```
/graphify .                        # работает с любой папкой — код, заметки, статьи, всё что угодно
```

```
graphify-out/
├── graph.html       интерактивный граф — открыть в браузере, кликать по узлам, искать, фильтровать
├── GRAPH_REPORT.md  бог-узлы, неожиданные связи, предлагаемые вопросы
├── graph.json       постоянный граф — запрашивать через недели без повторного чтения
└── cache/           SHA256-кэш — повторные запуски обрабатывают только изменённые файлы
```

Добавьте файл `.graphifyignore` для исключения папок:

```
# .graphifyignore
vendor/
node_modules/
dist/
*.generated.py
```

Синтаксис аналогичен `.gitignore`.

## Как это работает

graphify работает в три прохода. Сначала детерминированный AST-проход извлекает структуру из файлов кода (классы, функции, импорты, графы вызовов, docstrings, комментарии с обоснованием) — без LLM. Затем видео и аудиофайлы транскрибируются локально с faster-whisper. Наконец, Claude-субагенты запускаются параллельно над документами, статьями, изображениями и транскриптами для извлечения концепций, связей и обоснований дизайна. Результаты объединяются в граф NetworkX, кластеризуются с помощью Leiden-детекции сообществ и экспортируются как интерактивный HTML, запрашиваемый JSON и аудит-отчёт на естественном языке.

**Кластеризация основана на топологии графа — без эмбеддингов.** Leiden находит сообщества по плотности рёбер. Рёбра семантического сходства, извлечённые Claude (`semantically_similar_to`, помечены как INFERRED), уже в графе. Структура графа — это сигнал сходства. Отдельный шаг с эмбеддингами или векторная база данных не нужны.

Каждая связь помечена как `EXTRACTED` (найдена непосредственно в источнике), `INFERRED` (обоснованный вывод с оценкой уверенности) или `AMBIGUOUS` (помечена для проверки).

## Установка

**Требования:** Python 3.10+ и одно из: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com), [Gemini CLI](https://github.com/google-gemini/gemini-cli), [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli), [VS Code Copilot Chat](https://code.visualstudio.com/docs/copilot/overview), [Aider](https://aider.chat), [OpenClaw](https://openclaw.ai), [Factory Droid](https://factory.ai), [Trae](https://trae.ai), [Kiro](https://kiro.dev), Hermes или [Google Antigravity](https://antigravity.google)

```bash
# Рекомендуется — работает на Mac и Linux без настройки PATH
uv tool install graphifyy && graphify install
# или с pipx
pipx install graphifyy && graphify install
# или обычный pip
pip install graphifyy && graphify install
```

> **Официальный пакет:** Пакет PyPI называется `graphifyy` (установить через `pip install graphifyy`). Другие пакеты с именем `graphify*` на PyPI не связаны с этим проектом. Единственный официальный репозиторий — [safishamsi/graphify](https://github.com/safishamsi/graphify).

### Поддержка платформ

| Платформа | Команда установки |
|-----------|-------------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (авто-определение) или `graphify install --platform windows` |
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

Затем откройте AI-ассистент и введите:

```
/graphify .
```

Примечание: Codex использует `$` вместо `/` для навыков, поэтому вводите `$graphify .`.

### Заставить ассистента всегда использовать граф (рекомендуется)

После построения графа выполните это один раз в вашем проекте:

| Платформа | Команда |
|-----------|---------|
| Claude Code | `graphify claude install` |
| Codex | `graphify codex install` |
| OpenCode | `graphify opencode install` |
| Cursor | `graphify cursor install` |
| Gemini CLI | `graphify gemini install` |
| Kiro IDE/CLI | `graphify kiro install` |
| Google Antigravity | `graphify antigravity install` |

## Использование

```
/graphify                          # текущая директория
/graphify ./raw                    # конкретная папка
/graphify ./raw --mode deep        # более агрессивное извлечение INFERRED-рёбер
/graphify ./raw --update           # повторно извлечь только изменённые файлы
/graphify ./raw --directed         # направленный граф
/graphify ./raw --cluster-only     # перезапустить кластеризацию на существующем графе
/graphify ./raw --no-viz           # без HTML, только отчёт + JSON
/graphify ./raw --obsidian         # создать Obsidian vault (opt-in)

/graphify add https://arxiv.org/abs/1706.03762   # получить статью
/graphify add <video-url>                         # скачать аудио, транскрибировать, добавить
/graphify query "что связывает Attention с оптимизатором?"
/graphify path "DigestAuth" "Response"
/graphify explain "SwinTransformer"

graphify hook install              # установить Git-хуки
graphify update ./src              # повторно извлечь файлы кода, без LLM
graphify watch ./src               # автоматическое обновление графа
```

## Что вы получаете

**Бог-узлы** — концепции с наибольшей степенью (через которые проходит всё)

**Неожиданные связи** — отсортированы по составному баллу. Рёбра код-статья получают более высокий рейтинг. Каждый результат содержит объяснение «почему» на естественном языке.

**Предлагаемые вопросы** — 4-5 вопросов, на которые граф уникально способен ответить

**«Почему»** — docstrings, встроенные комментарии (`# NOTE:`, `# IMPORTANT:`, `# HACK:`, `# WHY:`), и обоснования дизайна из документов извлекаются как узлы `rationale_for`.

**Оценки уверенности** — каждое INFERRED-ребро имеет `confidence_score` (0,0-1,0).

**Бенчмарк токенов** — выводится автоматически после каждого запуска. На смешанном корпусе: **71,5-кратное** сокращение токенов на запрос vs сырые файлы.

**Авто-синхронизация** (`--watch`) — обновляет граф автоматически при изменении кода.

**Git-хуки** (`graphify hook install`) — устанавливает post-commit и post-checkout хуки.

## Конфиденциальность

graphify отправляет содержимое файлов в API модели вашего AI-ассистента для семантического извлечения из документов, статей и изображений. Файлы кода обрабатываются локально через tree-sitter AST. Видео и аудиофайлы транскрибируются локально с faster-whisper. Никакой телеметрии, никакого отслеживания использования.

## Технологический стек

NetworkX + Leiden (graspologic) + tree-sitter + vis.js. Семантическое извлечение через Claude, GPT-4 или модель вашей платформы. Транскрипция видео через faster-whisper + yt-dlp (опционально).

## Построено на graphify — Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai) — корпоративный слой поверх graphify. Там, где graphify превращает папку с файлами в граф знаний, Penpax применяет тот же граф ко всей вашей рабочей жизни — непрерывно.

**Бесплатный пробный период скоро.** [Вступить в список ожидания →](https://safishamsi.github.io/penpax.ai)

## История звёзд

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
