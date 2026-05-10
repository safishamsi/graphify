# Graphify Standalone Binary - Quick Start

Thank you for downloading the standalone version of Graphify! This guide will help you get set up in seconds.

## 1. Installation

### Linux / macOS
1. Move the `aag` binary to a folder in your system PATH (e.g., `/usr/local/bin`):
   ```bash
   chmod +x aag
   sudo mv aag /usr/local/bin/aag
   ```
2. Verify it's working:
   ```bash
   aag --help
   ```

### Windows
1. Move `aag-windows.exe` to a folder included in your User PATH (e.g., `%USERPROFILE%\bin`).
2. Rename it to `aag.exe` for convenience.
3. Open a new terminal (cmd or PowerShell) and verify:
   ```cmd
   aag --help
   ```

## 2. Setup AI Skill

Graphify works best as a "Skill" for AI coding assistants. Run the installation command for your preferred platform:

```bash
# For Claude Code (Recommended)
aag install --platform claude

# For Gemini CLI
aag install --platform gemini

# For Codex / OpenCode
aag install --platform codex
aag install --platform opencode

# For Aider / Copilot / Trae
aag install --platform aider
aag install --platform copilot
aag install --platform trae
```

## 3. Basic Usage

To turn your current folder into a knowledge graph:

```bash
/aag .
```

This will:
1. **Detect** your files.
2. **Extract** entities and relationships.
3. **Cluster** them into communities.
4. **Generate** a `aag-out/` folder with an interactive `graph.html` and a detailed `GRAPH_REPORT.md`.

---
For more details, visit the [official repository](https://github.com/hhfeng/aa-aag).
