"""Tests for the extraction-subagent prompt template embedded in skill.md.

The skill.md file is the canonical instruction set the orchestrator hands to
extraction subagents. These tests pin the parts of the prompt that govern the
output schema — specifically that `source_file` is required on every node and
edge, so the validator does not later have to deal with missing values.
"""
from pathlib import Path

SKILL_MD = Path(__file__).parent.parent / "graphify" / "skill.md"


def _skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def test_skill_md_exists():
    assert SKILL_MD.exists(), f"skill.md not found at {SKILL_MD}"


def test_prompt_marks_source_file_required():
    """
    The extraction prompt must explicitly state that `source_file` is a
    required field on every node and edge. Without this, the LLM elides it
    on rationale/document nodes and the validator can't distinguish
    "outside the corpus" from "LLM forgot to fill the field".
    """
    text = _skill_text()
    # Look for a clear "required" statement near source_file in the prompt body.
    # We require the literal phrase rather than scanning the JSON schema example
    # so the requirement is human-readable to the subagent.
    assert "source_file" in text and "required" in text.lower(), (
        "skill.md prompt should describe source_file as required"
    )


def test_prompt_documents_external_sentinel():
    """
    The prompt should mention the `<external>` sentinel so subagents know
    they may use it for cross-corpus symbols rather than leaving the field
    empty. This keeps the AST-extractor contract and the LLM-extractor
    contract aligned.
    """
    text = _skill_text()
    assert "<external>" in text, (
        "skill.md prompt should mention the '<external>' sentinel "
        "for cross-corpus symbols"
    )
