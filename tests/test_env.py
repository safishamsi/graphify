"""Tests for graphify .env loading."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from graphify.env import _candidate_dotenv_paths, load_env


def test_load_env_reads_parent_dotenv(tmp_path):
    parent = tmp_path / "workspace"
    project = parent / "project"
    project.mkdir(parents=True)
    (parent / ".env").write_text("MOONSHOT_API_KEY=from-parent\n", encoding="utf-8")

    env: dict[str, str] = {}
    load_env(cwd=project, home=tmp_path, environ=env)

    assert env["MOONSHOT_API_KEY"] == "from-parent"


def test_load_env_closer_dotenv_overrides_parent_dotenv(tmp_path):
    parent = tmp_path / "workspace"
    project = parent / "project"
    project.mkdir(parents=True)
    (parent / ".env").write_text("MOONSHOT_API_KEY=from-parent\n", encoding="utf-8")
    (project / ".env").write_text("MOONSHOT_API_KEY=from-project\n", encoding="utf-8")

    env: dict[str, str] = {}
    load_env(cwd=project, home=tmp_path, environ=env)

    assert env["MOONSHOT_API_KEY"] == "from-project"


def test_load_env_project_dotenv_outside_home_overrides_home_dotenv(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "workspace" / "project"
    home.mkdir()
    project.mkdir(parents=True)
    (home / ".env").write_text("MOONSHOT_API_KEY=from-home\n", encoding="utf-8")
    (project / ".env").write_text("MOONSHOT_API_KEY=from-project\n", encoding="utf-8")

    env: dict[str, str] = {}
    load_env(cwd=project, home=home, environ=env)

    assert env["MOONSHOT_API_KEY"] == "from-project"


def test_load_env_does_not_override_process_env(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text("MOONSHOT_API_KEY=from-file\n", encoding="utf-8")

    env = {"MOONSHOT_API_KEY": "from-process"}
    load_env(cwd=project, home=tmp_path, environ=env)

    assert env["MOONSHOT_API_KEY"] == "from-process"


def test_load_env_supports_export_and_quotes(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text("export MOONSHOT_API_KEY='quoted-key'\n", encoding="utf-8")

    env: dict[str, str] = {}
    load_env(cwd=project, home=tmp_path, environ=env)

    assert env["MOONSHOT_API_KEY"] == "quoted-key"


def test_candidate_dotenv_paths_include_wsl_windows_home(tmp_path):
    home = tmp_path / "alice"
    users_root = Path("/mnt/c/Users")
    with patch("graphify.env.platform.system", return_value="Linux"), \
         patch("graphify.env._wsl_windows_users_root", return_value=users_root):
        paths = _candidate_dotenv_paths(tmp_path / "project", home)

    assert users_root / home.name / ".env" in paths
