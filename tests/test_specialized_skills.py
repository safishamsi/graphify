import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from graphify.__main__ import _get_specialized_skill_content, _get_claude_hook, _get_gemini_hook

def test_specialized_content_python():
    """Verify 'aag' imports are replaced with 'graphify' in python mode."""
    with patch("sys.frozen", False, create=True):
        src = Path("test_skill_py.md")
        src.write_text("from aag.extract import extract\nimport aag", encoding="utf-8")
        try:
            content = _get_specialized_skill_content(src)
            assert "from graphify.extract import extract" in content
            assert "import graphify" in content
            assert "from aag" not in content
        finally:
            src.unlink()

def test_specialized_content_binary():
    """Verify content is specialized in binary mode."""
    with patch("sys.frozen", True, create=True), \
         patch("sys.executable", "/usr/local/bin/aag"):
        src = Path("test_skill_binary.md")
        original = """### Step 1 - Ensure aag is installed

```bash
# Detect the correct Python interpreter (handles uv tool, pipx, venv, system installs)
PYTHON=""
GRAPHIFY_BIN=$(which aag 2>/dev/null)
```

$(cat graphify-out/.aag_python) -c "import aag"
"""
        src.write_text(original, encoding="utf-8")
        try:
            content = _get_specialized_skill_content(src)
            assert "PYTHON=/usr/local/bin/aag" in content
            assert "/usr/local/bin/aag eval \"import aag\"" in content
            assert "Detect the correct Python interpreter" not in content
        finally:
            src.unlink()

def test_claude_hook_python():
    """Verify Claude hook uses python3 -c in python mode."""
    with patch("sys.frozen", False, create=True):
        hook = _get_claude_hook()
        cmd = hook["hooks"][0]["command"]
        assert "python3 -c" in cmd
        assert "aag eval" not in cmd

def test_claude_hook_binary():
    """Verify Claude hook uses aag eval in binary mode."""
    with patch("sys.frozen", True, create=True), \
         patch("sys.executable", "/usr/local/bin/aag"):
        hook = _get_claude_hook()
        cmd = hook["hooks"][0]["command"]
        assert "/usr/local/bin/aag eval" in cmd
        assert "python3 -c" not in cmd

def test_gemini_hook_python():
    """Verify Gemini hook uses python3 -c in python mode."""
    with patch("sys.frozen", False, create=True):
        hook = _get_gemini_hook()
        cmd = hook["hooks"][0]["command"]
        assert "python3 -c" in cmd
        assert "aag eval" not in cmd

def test_gemini_hook_binary():
    """Verify Gemini hook uses aag eval in binary mode."""
    with patch("sys.frozen", True, create=True), \
         patch("sys.executable", "/usr/local/bin/aag"):
        hook = _get_gemini_hook()
        cmd = hook["hooks"][0]["command"]
        assert "/usr/local/bin/aag eval" in cmd
        assert "python3 -c" not in cmd
