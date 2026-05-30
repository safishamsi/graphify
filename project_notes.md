# Setup Guide

This project uses `uv` for lightning-fast Python package and project management.

## 1. Prerequisites

Ensure you have `uv` installed. If not, you can install it via:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 2. Environment Setup

Sync the project dependencies. It is recommended to install with the `gemini` and `test` extras for full functionality.

```bash
# Basic setup for Gemini CLI and testing
uv sync --extra gemini --extra test

# OR: Install ALL optional features (SQL, PDF, Video, etc.)
uv sync --all-extras
```

This will create a `.venv` directory and install all required packages.

## 3. Running Tests

You can run the test suite using `pytest` through `uv`. Note that some tests (like SQL) will be skipped if their respective optional dependencies are not installed.

```bash
# Run all tests
uv run pytest

# Run tests with specific markers (e.g., integration tests)
uv run pytest -m integration

# Run a specific test file
uv run pytest tests/test_extract.py
```

## 4. Installing the `pyaag` Skill

The `pyaag` skill allows you to use `graphify` directly from your AI assistant (like Gemini CLI or Claude Code) using your local Python environment.

To install it for the **Gemini CLI**:

```bash
uv run graphify pyinstall gemini
```

### What this does:
1.  **Installs the Skill**: Copies the logic to `~/.gemini/skills/pyaag/SKILL.md`.
2.  **Configures Project**: Updates/creates `GEMINI.md` in your project root.
3.  **Sets up Hooks**: Configures `.gemini/settings.json` with a `BeforeTool` hook for automatic graph checks.

### Usage in Gemini CLI:
Once installed, trigger the skill inside your Gemini CLI session:
```bash
/pyaag .
```

## 5. Other Platforms

If you are using **Claude Code**, install the skill via:
```bash
uv run graphify pyinstall claude
```
