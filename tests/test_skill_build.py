"""Tests for the skill-file generator and the progressive-disclosure split (#1106).

Covers:
* the generator is a lossless round-trip of skill.md (nothing dropped on the way
  to the split);
* the committed Claude split tree is in sync with skill.md (CI drift gate);
* the lean SKILL.md is actually lean and keeps the query-first description
  verbatim;
* the load-bearing node-ID rule + JSON contract move as **verbatim slices** and
  the spec's file-node examples still match what the extractor's code produces
  (pinned against ``_file_node_id``, not a frozen string, per #1106);
* split-mode install copies SKILL.md + reference/, and uninstall removes the
  whole tree without clobbering unrelated files.
"""
import os
from pathlib import Path
from unittest.mock import patch

from graphify import skill_build
from graphify.extract import _file_node_id


def _read(rel: str) -> str:
    return (skill_build.CLAUDE_DIR / rel).read_text(encoding="utf-8")


def _frontmatter_description(text: str) -> str:
    fm, _ = skill_build.split_frontmatter(text)
    for line in fm.splitlines():
        if line.startswith("description:"):
            return line
    raise AssertionError("no description line in frontmatter")


# --------------------------------------------------------------------------- #
# Generator integrity
# --------------------------------------------------------------------------- #

def test_flatten_is_lossless_roundtrip():
    """Reassembling the parsed segments reproduces skill.md byte-for-byte."""
    assert skill_build.flatten() == skill_build.SOURCE.read_text(encoding="utf-8")


def test_committed_tree_in_sync_with_skill_md():
    """The committed skill_claude/ tree must match a fresh generation.

    This is the CI drift gate: edit skill.md without regenerating and this fails.
    """
    assert skill_build.check() == 0, (
        "skill_claude/ is out of sync — run `python -m graphify.skill_build`."
    )


def test_build_is_deterministic():
    assert skill_build.build_artifacts() == skill_build.build_artifacts()


def test_every_mapped_section_lands_in_the_tree():
    """No H2 section silently disappears in the split."""
    tree = "".join(skill_build.build_artifacts().values())
    for title in skill_build.H2_DESTINATION:
        assert f"## {title}" in tree, f"section '## {title}' was dropped from the split"


# --------------------------------------------------------------------------- #
# Lean core + preserved discovery description
# --------------------------------------------------------------------------- #

def test_skill_md_is_lean():
    """The always-loaded SKILL.md is a small fraction of the full document."""
    lean = _read("SKILL.md")
    full = skill_build.SOURCE.read_text(encoding="utf-8")
    assert len(lean) < 0.2 * len(full), "SKILL.md is not lean enough (>20% of skill.md)"
    assert len(lean.splitlines()) < 200


def test_routing_table_points_at_every_reference_file():
    lean = _read("SKILL.md")
    for name in skill_build.REFERENCE_FILES:
        assert f"reference/{name}.md" in lean, f"SKILL.md never routes to reference/{name}.md"


def test_description_preserved_verbatim():
    """The skill description carries the query-first discovery clause (#580); the
    split must not alter it."""
    assert _frontmatter_description(_read("SKILL.md")) == _frontmatter_description(
        skill_build.SOURCE.read_text(encoding="utf-8")
    )


def test_honesty_rules_stay_in_core():
    assert "## Honesty Rules" in _read("SKILL.md")


def test_no_stale_pointers_to_moved_sections():
    """The lean core must not still tell the agent to 'jump to ## For ...' a
    section that now lives in a reference file (silent-replacement-failure guard)."""
    lean = _read("SKILL.md")
    for stale in (
        "skip Steps 1–5 entirely",
        "run Step 0 before anything else",
        "Follow these steps in order. Do not skip steps.",
    ):
        assert stale not in lean, f"stale pointer left in SKILL.md: {stale!r}"


# --------------------------------------------------------------------------- #
# Routing: each command's flow lands in its own reference file
# --------------------------------------------------------------------------- #

def test_command_flows_route_to_expected_files():
    assert "Node ID format" in _read("reference/extract.md")
    assert "## For --update" in _read("reference/update.md")
    assert "## For /graphify query" in _read("reference/query.md")
    assert "## For /graphify add" in _read("reference/add.md")
    assert "## For --watch" in _read("reference/watch.md")


def test_interpreter_guard_shared_into_subcommand_files_only():
    guard = "## Interpreter guard for subcommands"
    for name in skill_build.NEEDS_INTERPRETER_GUARD:
        assert guard in _read(f"reference/{name}.md"), f"guard missing from {name}.md"
    # watch.md is outside the guard's own stated scope.
    assert guard not in _read("reference/watch.md")


# --------------------------------------------------------------------------- #
# Byte-accuracy guardrail: load-bearing content moves verbatim AND matches code
# --------------------------------------------------------------------------- #

def test_node_id_rule_and_json_contract_are_verbatim_slices():
    """The node-ID rule and JSON contract appear in extract.md exactly as they
    appear in skill.md (substring-identical), never paraphrased."""
    source = skill_build.SOURCE.read_text(encoding="utf-8")
    extract_ref = _read("reference/extract.md")

    rule = "Node ID format: lowercase, only `[a-z0-9_]`, no dots or slashes."
    contract = '{"nodes":[{"id":"session_validatetoken","label":"Human Readable Name"'
    for needle in (rule, contract):
        assert needle in source
        assert needle in extract_ref, "load-bearing spec text was altered or dropped"


def test_spec_file_node_examples_match_the_extractor_code():
    """Pin the spec's file-node examples against ``_file_node_id`` (not a frozen
    string) so the doc and the code can never drift apart silently (#1106).

    Each (path, stem, symbol) triple: the doc must contain the symbol example,
    the symbol must extend the file stem, and the code must derive that stem.
    """
    extract_ref = _read("reference/extract.md")
    examples = [
        ("src/auth/session.py", "auth_session", "auth_session_validatetoken"),
        ("lib/utils/helpers.py", "utils_helpers", "utils_helpers_parse_url"),
        ("tests/test_foo.py", "tests_test_foo", "tests_test_foo_helper"),
    ]
    for path, stem, symbol in examples:
        assert _file_node_id(Path(path)) == stem, (
            f"code derives {_file_node_id(Path(path))!r} for {path}, spec says {stem!r}"
        )
        assert symbol in extract_ref, f"spec example {symbol!r} missing from extract.md"
        assert symbol.startswith(stem + "_")

    # Top-level files collapse to the bare stem.
    assert _file_node_id(Path("setup.py")) == "setup"
    assert "`setup.py`" in extract_ref


# --------------------------------------------------------------------------- #
# Split-mode install / uninstall
# --------------------------------------------------------------------------- #

def _install_claude(home: Path) -> Path:
    from graphify.__main__ import install

    old_cwd = Path.cwd()
    try:
        os.chdir(home)
        with patch("graphify.__main__.Path.home", return_value=home):
            install(platform="claude")
    finally:
        os.chdir(old_cwd)
    return home / ".claude" / "skills" / "graphify" / "SKILL.md"


def test_split_install_copies_skill_and_references(tmp_path):
    skill = _install_claude(tmp_path)
    skill_dir = skill.parent
    assert skill.exists()
    ref = skill_dir / "reference"
    assert sorted(p.name for p in ref.glob("*.md")) == [
        "add.md", "extract.md", "query.md", "update.md", "watch.md",
    ]
    assert (skill_dir / ".graphify_version").exists()
    # The installed files match the packaged generated tree.
    assert skill.read_text(encoding="utf-8") == _read("SKILL.md")


def test_uninstall_removes_the_whole_tree(tmp_path):
    from graphify.__main__ import _remove_skill_file

    skill = _install_claude(tmp_path)
    skill_dir = skill.parent
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        assert _remove_skill_file("claude") is True
    assert not skill_dir.exists(), "skill dir (with reference/) should be gone"


def test_uninstall_keeps_unrelated_user_files(tmp_path):
    """Removal is scoped to graphify-owned names; a user file in the skill dir
    survives (we never blind-rmtree the directory)."""
    from graphify.__main__ import _remove_skill_file

    skill = _install_claude(tmp_path)
    stray = skill.parent / "my-notes.md"
    stray.write_text("keep me", encoding="utf-8")
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        _remove_skill_file("claude")
    assert stray.exists(), "uninstall must not delete unrelated user files"
    assert not skill.exists()
    assert not (skill.parent / "reference").exists()
