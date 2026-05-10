# Graphify Standalone Binary - Quick Start

Thank you for downloading the standalone version of Graphify! This guide will help you get set up in seconds.

## 1. Installation

### Linux / macOS
1. Move the `graphify` binary to a folder in your system PATH (e.g., `/usr/local/bin`):
   ```bash
   chmod +x graphify
   sudo mv graphify /usr/local/bin/graphify
   ```
2. Verify it's working:
   ```bash
   graphify --help
   ```

### Windows
1. Move `graphify-windows.exe` to a folder included in your User PATH (e.g., `%USERPROFILE%\bin`).
2. Rename it to `graphify.exe` for convenience.
3. Open a new terminal (cmd or PowerShell) and verify:
   ```cmd
   graphify --help
   ```

## 2. Setup AI Skill

Graphify works best as a "Skill" for AI coding assistants. Run the installation command for your preferred platform:

```bash
# For Claude Code (Recommended)
graphify install --platform claude

# For Gemini CLI
graphify install --platform gemini

# For Codex / OpenCode
graphify install --platform codex
graphify install --platform opencode

# For Aider / Copilot / Trae
graphify install --platform aider
graphify install --platform copilot
graphify install --platform trae
```

## 3. Basic Usage

To turn your current folder into a knowledge graph:

```bash
/graphify .
```

This will:
1. **Detect** your files.
2. **Extract** entities and relationships.
3. **Cluster** them into communities.
4. **Generate** a `graphify-out/` folder with an interactive `graph.html` and a detailed `GRAPH_REPORT.md`.

---
For more details, visit the [official repository](https://github.com/hhfeng/aa-graphify).
