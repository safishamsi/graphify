"""Tests for graphify devin install / uninstall commands."""
from pathlib import Path
import sys
from unittest.mock import patch
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _devin_install_user(tmp_path):
    from graphify.__main__ import install
    old_cwd = Path.cwd()
    try:
        import os
        os.chdir(tmp_path)
        with patch("graphify.__main__.Path.home", return_value=tmp_path):
            install(platform="devin")
    finally:
        import os
        os.chdir(old_cwd)


def _skill_path_user(tmp_path):
    return tmp_path / ".config" / "devin" / "skills" / "graphify" / "SKILL.md"


def _skill_path_project(project_dir):
    return project_dir / ".devin" / "skills" / "graphify" / "SKILL.md"


def _rules_path(project_dir):
    return project_dir / ".windsurf" / "rules" / "graphify.md"


# ---------------------------------------------------------------------------
# User-scope install (graphify install --platform devin / graphify devin install)
# ---------------------------------------------------------------------------

def test_devin_install_user_creates_skill_file(tmp_path):
    """User-scope install copies skill to ~/.config/devin/skills/graphify/SKILL.md."""
    _devin_install_user(tmp_path)
    skill_path = _skill_path_user(tmp_path)
    assert skill_path.exists()


def test_devin_skill_file_contains_frontmatter(tmp_path):
    """Installed skill file must include Devin-specific YAML frontmatter."""
    _devin_install_user(tmp_path)
    content = _skill_path_user(tmp_path).read_text()
    assert "name: graphify" in content
    assert "argument-hint:" in content
    assert "triggers:" in content


def test_devin_skill_file_references_graphify_query(tmp_path):
    """/graphify skill must mention graphify query (query-first policy)."""
    _devin_install_user(tmp_path)
    content = _skill_path_user(tmp_path).read_text()
    assert "graphify query" in content or "/graphify query" in content


def test_devin_install_user_does_not_write_rules(tmp_path):
    """User-scope install does NOT write .windsurf/rules/ — that's project-only."""
    _devin_install_user(tmp_path)
    assert not _rules_path(tmp_path).exists()


# ---------------------------------------------------------------------------
# Project-scope install (graphify devin install --project)
# ---------------------------------------------------------------------------

def test_devin_install_project_creates_skill_file(tmp_path, monkeypatch):
    """Project-scope install copies skill to .devin/skills/graphify/SKILL.md."""
    from graphify.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(sys, "argv", ["graphify", "devin", "install", "--project"])
    with patch("graphify.__main__.Path.home", return_value=home):
        main()
    assert _skill_path_project(project).exists()
    assert not _skill_path_user(home).exists()


def test_devin_install_project_creates_rules_file(tmp_path, monkeypatch):
    """Project-scope install writes .windsurf/rules/graphify.md."""
    from graphify.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(sys, "argv", ["graphify", "devin", "install", "--project"])
    with patch("graphify.__main__.Path.home", return_value=home):
        main()
    rules = _rules_path(project)
    assert rules.exists()
    assert "graphify" in rules.read_text()
    assert "GRAPH_REPORT.md" in rules.read_text()


def test_devin_rules_content_recommends_graphify_query(tmp_path):
    """The rules file installed by devin must use query-first policy."""
    from graphify.__main__ import _devin_rules_install
    _devin_rules_install(tmp_path)
    content = _rules_path(tmp_path).read_text()
    assert "graphify query" in content


def test_devin_rules_install_idempotent(tmp_path, capsys):
    """Installing rules twice does not change content and prints 'no change'."""
    from graphify.__main__ import _devin_rules_install
    _devin_rules_install(tmp_path)
    content_first = _rules_path(tmp_path).read_text()
    _devin_rules_install(tmp_path)
    content_second = _rules_path(tmp_path).read_text()
    assert content_first == content_second
    assert "no change" in capsys.readouterr().out


def test_devin_install_project_hints_git_add(tmp_path, monkeypatch, capsys):
    """Project-scope install prints a git add hint covering .devin/ and .windsurf/."""
    from graphify.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(sys, "argv", ["graphify", "devin", "install", "--project"])
    with patch("graphify.__main__.Path.home", return_value=home):
        main()
    out = capsys.readouterr().out
    assert "git add" in out


# ---------------------------------------------------------------------------
# Uninstall — user scope
# ---------------------------------------------------------------------------

def test_devin_uninstall_user_removes_skill_file(tmp_path):
    """User-scope uninstall removes the skill file."""
    _devin_install_user(tmp_path)
    skill = _skill_path_user(tmp_path)
    assert skill.exists()

    from graphify.__main__ import _remove_skill_file
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        _remove_skill_file("devin")
    assert not skill.exists()


def test_devin_uninstall_user_noop_when_not_installed(tmp_path, capsys):
    """User-scope uninstall prints an appropriate message when nothing is installed."""
    from graphify.__main__ import main
    import os
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        with patch("graphify.__main__.Path.home", return_value=tmp_path):
            sys.argv = ["graphify", "devin", "uninstall"]
            main()
    finally:
        os.chdir(old_cwd)
    out = capsys.readouterr().out
    assert "nothing to remove" in out


# ---------------------------------------------------------------------------
# Uninstall — project scope
# ---------------------------------------------------------------------------

def test_devin_uninstall_project_removes_skill_file(tmp_path, monkeypatch):
    """Project-scope uninstall removes .devin/skills/graphify/SKILL.md."""
    from graphify.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    with patch("graphify.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["graphify", "devin", "install", "--project"])
        main()
        monkeypatch.setattr(sys, "argv", ["graphify", "devin", "uninstall", "--project"])
        main()
    assert not _skill_path_project(project).exists()


def test_devin_uninstall_project_removes_rules_file(tmp_path, monkeypatch):
    """Project-scope uninstall removes .windsurf/rules/graphify.md."""
    from graphify.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    with patch("graphify.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["graphify", "devin", "install", "--project"])
        main()
        monkeypatch.setattr(sys, "argv", ["graphify", "devin", "uninstall", "--project"])
        main()
    assert not _rules_path(project).exists()


def test_devin_uninstall_project_does_not_touch_user_scope(tmp_path, monkeypatch):
    """Project-scope uninstall must not remove the user-scope skill file."""
    from graphify.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    # Pre-create a user-scope skill file
    user_skill = _skill_path_user(home)
    user_skill.parent.mkdir(parents=True, exist_ok=True)
    user_skill.write_text("user skill")
    monkeypatch.chdir(project)
    with patch("graphify.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["graphify", "devin", "install", "--project"])
        main()
        monkeypatch.setattr(sys, "argv", ["graphify", "devin", "uninstall", "--project"])
        main()
    assert user_skill.exists()


def test_devin_rules_uninstall_noop_when_not_installed(tmp_path):
    """_devin_rules_uninstall does nothing if the rules file was never written."""
    from graphify.__main__ import _devin_rules_uninstall
    _devin_rules_uninstall(tmp_path)  # should not raise


# ---------------------------------------------------------------------------
# Skill file content
# ---------------------------------------------------------------------------

def test_devin_skill_file_exists_in_package():
    """skill-devin.md must be present in the installed package."""
    import graphify
    skill = Path(graphify.__file__).parent / "skill-devin.md"
    assert skill.exists(), "skill-devin.md missing from package"


def test_devin_skill_file_uses_python_c_syntax():
    """Devin skill must use inline python -c syntax (cross-platform, no bash heredocs).

    All mature graphify skills use the interpreter-detection pattern
    ``$(cat graphify-out/.graphify_python) -c "..."`` rather than bare
    ``python -c "..."`` so they work in pipx / venv environments.
    """
    import graphify
    skill = (Path(graphify.__file__).parent / "skill-devin.md").read_text()
    assert '.graphify_python) -c "' in skill, (
        "skill-devin.md must use the interpreter-detection pattern "
        "'$(cat graphify-out/.graphify_python) -c \"...\"'"
    )
    assert "#!/bin/bash" not in skill


def test_devin_skill_file_frontmatter_has_triggers():
    """Devin skill frontmatter must list triggers for model-invocable activation."""
    import graphify
    skill = (Path(graphify.__file__).parent / "skill-devin.md").read_text()
    assert "triggers:" in skill
    assert "model" in skill


# ---------------------------------------------------------------------------
# Platform config sanity
# ---------------------------------------------------------------------------

def test_devin_in_platform_config():
    """devin must be registered in _PLATFORM_CONFIG."""
    from graphify.__main__ import _PLATFORM_CONFIG
    assert "devin" in _PLATFORM_CONFIG
    assert _PLATFORM_CONFIG["devin"]["skill_file"] == "skill-devin.md"
    assert _PLATFORM_CONFIG["devin"]["claude_md"] is False


def test_devin_platform_skill_destination_user_scope(tmp_path):
    """User-scope destination must be ~/.config/devin/skills/graphify/SKILL.md."""
    from graphify.__main__ import _platform_skill_destination
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        dst = _platform_skill_destination("devin", project=False)
    assert dst == tmp_path / ".config" / "devin" / "skills" / "graphify" / "SKILL.md"


def test_devin_in_main_help_text(capsys, monkeypatch):
    """`graphify --help` must list devin in the platform list and in the per-platform section."""
    from graphify.__main__ import main
    monkeypatch.setattr(sys, "argv", ["graphify", "--help"])
    main()
    captured = capsys.readouterr().out
    # devin should appear in the top-level platform list
    assert "|devin)" in captured or "|devin |" in captured or "|devin" in captured, (
        "devin missing from `graphify --help` platform list"
    )
    # devin install / uninstall should appear in the per-platform section
    assert "devin install" in captured, "`devin install` line missing from help text"
    assert "devin uninstall" in captured, "`devin uninstall` line missing from help text"
    assert "~/.config/devin" in captured, "devin user-scope path missing from help text"
    # Convention: `--project` is supported by all platforms but documented by none.
    # devin should not be the lone outlier that documents it.
    devin_section = captured.split("devin install", 1)[1].split("\n\n", 1)[0]
    assert "--project" not in devin_section, (
        "devin help should NOT document --project — no other platform does"
    )


def test_devin_platform_skill_destination_project_scope(tmp_path):
    """Project-scope destination must be <project>/.devin/skills/graphify/SKILL.md."""
    from graphify.__main__ import _platform_skill_destination
    dst = _platform_skill_destination("devin", project=True, project_dir=tmp_path)
    assert dst == tmp_path / ".devin" / "skills" / "graphify" / "SKILL.md"
