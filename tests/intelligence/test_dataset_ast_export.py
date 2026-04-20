from __future__ import annotations

import json
import re
from pathlib import Path

from graphify.build import build_from_json

from depos.analysis.ast_normalize import normalize_dataset_dir
from depos.analysis.dataset_ast_export import export_dataset_from_repo
from depos.cli import main


_AST_ID_RE = re.compile(r"^ast:[^:]+:.+:\d+:\d+:[^:]+$")


def test_export_dataset_from_repo_emits_pipeline_compatible_ast(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    dataset_root = tmp_path / "dataset"
    source_path = repo_root / "backend" / "app" / "main.py"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        "from app.services.auth import verify_token\n\n"
        "def handle_request():\n"
        "    return verify_token()\n",
        encoding="utf-8",
    )

    result = export_dataset_from_repo(repo_root, dataset_root=dataset_root)

    assert result.files_written == 1
    dataset_file = result.dataset_dir / "backend_app_main.py.json"
    assert dataset_file.exists()

    payload = json.loads(dataset_file.read_text(encoding="utf-8"))
    assert payload["relative_path"] == "backend/app/main.py"
    assert payload["commit_sha"]
    assert payload["nodes"]
    assert payload["edges"]
    assert all(_AST_ID_RE.match(node["id"]) for node in payload["nodes"])
    assert all({"source_id", "target_id", "type"} <= set(edge) for edge in payload["edges"])
    assert any(edge["type"] == "child" for edge in payload["edges"])

    extraction = normalize_dataset_dir(result.dataset_dir, repo_root=repo_root)
    graph = build_from_json(extraction, directed=True)
    function_nodes = {
        nid: attrs for nid, attrs in graph.nodes(data=True) if attrs.get("entity_kind") == "function"
    }
    import_nodes = {
        nid: attrs for nid, attrs in graph.nodes(data=True) if attrs.get("entity_kind") == "import"
    }
    assert any(attrs.get("label") == "handle_request()" for attrs in function_nodes.values())
    assert any("app.services.auth" in attrs.get("label", "") for attrs in import_nodes.values())


def test_export_dataset_from_repo_reports_progress_steps(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    dataset_root = tmp_path / "dataset"
    source_path = repo_root / "backend" / "app" / "main.py"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("def handle_request():\n    return True\n", encoding="utf-8")

    messages: list[str] = []
    result = export_dataset_from_repo(repo_root, dataset_root=dataset_root, progress=messages.append)

    assert result.files_written == 1
    assert any("source repository root is" in message or "exporting from repo root" in message for message in messages)
    assert any("resolving repository metadata" in message.lower() for message in messages)
    assert any("running graphify detect" in message.lower() for message in messages)
    assert any("detect found 1 code file" in message.lower() for message in messages)
    assert any("export progress 1/1 processed" in message.lower() for message in messages)
    assert any("cleaning stale dataset files" in message.lower() for message in messages)
    assert any("export complete (1 written, 0 skipped)" in message.lower() for message in messages)


def test_prepare_dataset_cli_exports_into_repo_named_subdir(tmp_path: Path, capsys) -> None:
    repo_root = tmp_path / "sample-repo"
    dataset_root = tmp_path / "dataset"
    source_path = repo_root / "backend" / "app" / "auth.py"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        "def verify_token():\n"
        "    return True\n",
        encoding="utf-8",
    )

    rc = main(
        [
            "analyze",
            "prepare-dataset",
            "--repo-root",
            str(repo_root),
            "--dataset-root",
            str(dataset_root),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert "[depos-intel]" in captured.err
    assert "running graphify detect" in captured.err.lower()
    assert "export progress 1/1 processed" in captured.err.lower()
    assert "cleaning stale dataset files" in captured.err.lower()
    payload = json.loads(captured.out)
    assert payload["repo_name"] == "sample-repo"
    assert Path(payload["dataset_dir"]) == (dataset_root / "sample-repo").resolve()
    assert (dataset_root / "sample-repo" / "backend_app_auth.py.json").exists()
