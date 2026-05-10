"""Tests for the opt-in understand-quickly publish path."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest import mock

from graphify import publish as pub


def _init_git(repo: Path) -> str:
    """Initialise a tiny git repo and return HEAD sha."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "README.md").write_text("hi\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init", "--no-gpg-sign"], cwd=repo, check=True
    )
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def test_stamp_metadata_adds_required_fields(tmp_path: Path) -> None:
    sha = _init_git(tmp_path)
    out = tmp_path / "graphify-out"
    out.mkdir()
    graph_path = out / "graph.json"
    graph_path.write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")

    md = pub.stamp_metadata(graph_path, repo_dir=tmp_path, tool_version="0.0.0-test")
    data = json.loads(graph_path.read_text(encoding="utf-8"))

    assert md["tool"] == "graphify"
    assert md["tool_version"] == "0.0.0-test"
    assert md["commit"] == sha
    assert md["generated_at"].endswith("Z")
    # Round-trip: file actually contains the stamped metadata.
    assert data["metadata"] == md
    # Existing arrays untouched.
    assert data["nodes"] == [] and data["links"] == []


def test_publish_no_token_skips_dispatch(tmp_path: Path, capsys) -> None:
    _init_git(tmp_path)
    out = tmp_path / "graphify-out"
    out.mkdir()
    graph_path = out / "graph.json"
    graph_path.write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")

    env = {k: v for k, v in os.environ.items() if k != pub.TOKEN_ENV}
    with mock.patch.dict(os.environ, env, clear=True):
        result = pub.publish(graph_path, repo_dir=tmp_path)

    assert result["dispatched"] is False
    err = capsys.readouterr().err
    assert "skipping registry dispatch" in err
    # Metadata still stamped even without token.
    assert json.loads(graph_path.read_text())["metadata"]["tool"] == "graphify"
