"""Tests for the bundled prompt registry (graphify.prompts)."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

import pytest

from graphify import prompts


def test_extraction_subagent_is_bundled():
    """The extraction-subagent prompt must ship with the package."""
    assert "extraction_subagent" in prompts.available()


def test_load_returns_full_template():
    body = prompts.load("extraction_subagent")
    # Must contain the placeholder tokens skill.md substitutes at dispatch time.
    assert "CHUNK_NUM" in body
    assert "TOTAL_CHUNKS" in body
    assert "FILE_LIST" in body
    # Must contain the exact JSON shape contract — drift here will silently
    # break extraction subagents in the field.
    assert '"nodes":[' in body
    assert '"edges":[' in body
    assert '"hyperedges":[' in body


def test_load_unknown_raises():
    with pytest.raises(FileNotFoundError):
        prompts.load("does_not_exist")


def test_cli_prompts_list():
    """`graphify prompts list` must include extraction_subagent."""
    out = subprocess.run(
        [sys.executable, "-m", "graphify", "prompts", "list"],
        capture_output=True, text=True, check=True,
    )
    names = out.stdout.strip().splitlines()
    assert "extraction_subagent" in names


def test_cli_prompts_print_accepts_hyphen_alias():
    """`graphify prompts extraction-subagent` should equal load('extraction_subagent')."""
    out = subprocess.run(
        [sys.executable, "-m", "graphify", "prompts", "extraction-subagent"],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout == prompts.load("extraction_subagent")


def test_cli_prompts_unknown_exits_nonzero():
    out = subprocess.run(
        [sys.executable, "-m", "graphify", "prompts", "no_such_prompt"],
        capture_output=True, text=True,
    )
    assert out.returncode != 0
    assert "not found" in out.stderr
