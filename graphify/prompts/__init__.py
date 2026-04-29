"""Bundled prompt templates that ship with the graphify package.

Skills consume long prompts (e.g. the semantic-extraction subagent prompt)
via `graphify prompts <name>` instead of inlining them in skill.md. That
keeps SKILL.md slim — it's loaded into the assistant's context every time
the skill fires — while letting prompts evolve in version-controlled files.
"""
from __future__ import annotations
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


def available() -> list[str]:
    """Return the canonical name of every prompt template that ships with graphify."""
    return sorted(p.stem for p in PROMPTS_DIR.glob("*.md"))


def load(name: str) -> str:
    """Read a bundled prompt by canonical name. Raises FileNotFoundError if missing."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"prompt '{name}' not found. Available: {', '.join(available()) or '(none)'}"
        )
    return path.read_text(encoding="utf-8")
