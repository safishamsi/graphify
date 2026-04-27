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

**Una habilidad para asistentes de código IA.** Escribe `/graphify` en Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro o Google Antigravity — lee tus archivos, construye un grafo de conocimiento y te devuelve estructura que no sabías que existía. Entiende una base de código más rápido. Encuentra el «por qué» detrás de las decisiones arquitectónicas.

Totalmente multimodal. Deposita código, PDFs, markdown, capturas de pantalla, diagramas, fotos de pizarras, imágenes en otros idiomas, o archivos de video y audio — graphify extrae conceptos y relaciones de todo ello y los conecta en un solo grafo. Los videos se transcriben localmente con Whisper usando un prompt adaptado al dominio derivado de tu corpus. 25 lenguajes de programación soportados mediante tree-sitter AST (Python, JS, TS, Go, Rust, Java, C, C++, Ruby, C#, Kotlin, Scala, PHP, Swift, Lua, Zig, PowerShell, Elixir, Objective-C, Julia, Verilog, SystemVerilog, Vue, Svelte, Dart).

> Andrej Karpathy mantiene una carpeta `/raw` donde deposita papers, tweets, capturas de pantalla y notas. graphify es la respuesta a ese problema — 71,5 veces menos tokens por consulta versus leer los archivos sin procesar, persistente entre sesiones, honesto sobre lo que encontró versus lo que infirió.

```
/graphify .                        # funciona con cualquier carpeta — tu código, notas, papers, todo
```

```
graphify-out/
├── graph.html       grafo interactivo — abrir en cualquier navegador, hacer clic en nodos, buscar
├── GRAPH_REPORT.md  nodos dios, conexiones sorprendentes, preguntas sugeridas
├── graph.json       grafo persistente — consultar semanas después sin releer
└── cache/           caché SHA256 — las re-ejecuciones solo procesan archivos modificados
```

Añade un archivo `.graphifyignore` para excluir carpetas:

```
# .graphifyignore
vendor/
node_modules/
dist/
*.generated.py
```

Misma sintaxis que `.gitignore`. Puedes mantener un único `.graphifyignore` en la raíz del repositorio.

## Cómo funciona

graphify se ejecuta en tres pasadas. Primero, una pasada AST determinista extrae estructura de los archivos de código (clases, funciones, importaciones, grafos de llamadas, docstrings, comentarios de justificación) sin necesidad de LLM. Segundo, los archivos de video y audio se transcriben localmente con faster-whisper usando un prompt adaptado al dominio derivado de los nodos dios del corpus. Tercero, subagentes de Claude se ejecutan en paralelo sobre documentos, papers, imágenes y transcripciones para extraer conceptos, relaciones y justificaciones de diseño. Los resultados se fusionan en un grafo NetworkX, se agrupan con detección de comunidades Leiden, y se exportan como HTML interactivo, JSON consultable y un informe de auditoría en lenguaje natural.

**El clustering se basa en la topología del grafo — sin embeddings.** Leiden encuentra comunidades por densidad de aristas. Las aristas de similitud semántica que Claude extrae (`semantically_similar_to`, marcadas como INFERRED) ya están en el grafo. La estructura del grafo es la señal de similitud — no se necesita paso de embedding separado ni base de datos vectorial.

Cada relación está etiquetada como `EXTRACTED` (encontrada directamente en la fuente), `INFERRED` (inferencia razonable con puntuación de confianza) o `AMBIGUOUS` (marcada para revisión).

## Instalación

**Requisitos:** Python 3.10+ y uno de: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com), [Gemini CLI](https://github.com/google-gemini/gemini-cli), [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli), [VS Code Copilot Chat](https://code.visualstudio.com/docs/copilot/overview), [Aider](https://aider.chat), [OpenClaw](https://openclaw.ai), [Factory Droid](https://factory.ai), [Trae](https://trae.ai), [Kiro](https://kiro.dev), Hermes o [Google Antigravity](https://antigravity.google)

```bash
# Recomendado — funciona en Mac y Linux sin configurar el PATH
uv tool install graphifyy && graphify install
# o con pipx
pipx install graphifyy && graphify install
# o pip simple
pip install graphifyy && graphify install
```

> **Paquete oficial:** El paquete PyPI se llama `graphifyy` (instalar con `pip install graphifyy`). Otros paquetes llamados `graphify*` en PyPI no están afiliados con este proyecto. El único repositorio oficial es [safishamsi/graphify](https://github.com/safishamsi/graphify).

### Soporte de plataformas

| Plataforma | Comando de instalación |
|------------|------------------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (detección automática) o `graphify install --platform windows` |
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

Luego abre tu asistente de código IA y escribe:

```
/graphify .
```

Nota: Codex usa `$` en lugar de `/` para habilidades, así que escribe `$graphify .`.

### Hacer que el asistente siempre use el grafo (recomendado)

Después de construir un grafo, ejecuta esto una vez en tu proyecto:

| Plataforma | Comando |
|------------|---------|
| Claude Code | `graphify claude install` |
| Codex | `graphify codex install` |
| OpenCode | `graphify opencode install` |
| Cursor | `graphify cursor install` |
| Gemini CLI | `graphify gemini install` |
| Kiro IDE/CLI | `graphify kiro install` |
| Google Antigravity | `graphify antigravity install` |

## Uso

```
/graphify                          # directorio actual
/graphify ./raw                    # carpeta específica
/graphify ./raw --mode deep        # extracción de aristas INFERRED más agresiva
/graphify ./raw --update           # re-extraer solo archivos modificados
/graphify ./raw --directed         # grafo dirigido
/graphify ./raw --cluster-only     # re-ejecutar clustering en grafo existente
/graphify ./raw --no-viz           # sin HTML, solo informe + JSON
/graphify ./raw --obsidian         # generar vault de Obsidian (opt-in)

/graphify add https://arxiv.org/abs/1706.03762   # obtener un paper
/graphify add <video-url>                         # descargar audio, transcribir, añadir
/graphify query "¿qué conecta Attention con el optimizador?"
/graphify path "DigestAuth" "Response"
/graphify explain "SwinTransformer"

graphify hook install              # instalar hooks de Git
graphify update ./src              # re-extraer archivos de código, sin LLM
graphify watch ./src               # actualización automática del grafo
```

## Qué obtienes

**Nodos dios** — conceptos con mayor grado (por donde todo pasa)

**Conexiones sorprendentes** — clasificadas por puntuación compuesta. Las aristas código-paper puntúan más alto. Cada resultado incluye un por qué en lenguaje natural.

**Preguntas sugeridas** — 4-5 preguntas que el grafo está en posición única de responder

**El «por qué»** — docstrings, comentarios inline (`# NOTE:`, `# IMPORTANT:`, `# HACK:`, `# WHY:`), y justificaciones de diseño extraídas como nodos `rationale_for`.

**Puntuaciones de confianza** — cada arista INFERRED tiene un `confidence_score` (0,0-1,0).

**Benchmark de tokens** — impreso automáticamente tras cada ejecución. En un corpus mixto: **71,5 veces** menos tokens por consulta vs archivos sin procesar.

**Sincronización automática** (`--watch`) — actualiza el grafo automáticamente cuando cambia el código.

**Hooks de Git** (`graphify hook install`) — instala hooks post-commit y post-checkout.

## Privacidad

graphify envía contenido de archivos a la API del modelo de tu asistente IA para extracción semántica de documentos, papers e imágenes. Los archivos de código se procesan localmente mediante tree-sitter AST. Los archivos de video y audio se transcriben localmente con faster-whisper. Sin telemetría, sin seguimiento de uso.

## Stack técnico

NetworkX + Leiden (graspologic) + tree-sitter + vis.js. Extracción semántica via Claude, GPT-4 o el modelo de tu plataforma. Transcripción de video via faster-whisper + yt-dlp (opcional).

## Construido sobre graphify — Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai) es la capa enterprise sobre graphify. Donde graphify convierte una carpeta de archivos en un grafo de conocimiento, Penpax aplica el mismo grafo a toda tu vida laboral — continuamente.

**Prueba gratuita próximamente.** [Unirse a la lista de espera →](https://safishamsi.github.io/penpax.ai)

## Historial de estrellas

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date)](https://star-history.com/#safishamsi/graphify&Date)
