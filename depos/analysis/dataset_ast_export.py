"""Export pipeline-compatible raw AST dataset files from a repository checkout.

This bridges a gap between graphify's structural extraction flow and the
dataset-pipeline normalizer, which currently expects one raw AST JSON file per
source file.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from graphify.detect import detect


_LANGUAGE_BY_SUFFIX: dict[str, tuple[str, str, str]] = {
    ".py": ("tree_sitter_python", "language", "python"),
    ".js": ("tree_sitter_javascript", "language", "javascript"),
    ".jsx": ("tree_sitter_javascript", "language", "javascript"),
    ".mjs": ("tree_sitter_javascript", "language", "javascript"),
    ".ts": ("tree_sitter_typescript", "language_typescript", "typescript"),
    ".tsx": ("tree_sitter_typescript", "language_typescript", "typescript"),
    ".go": ("tree_sitter_go", "language", "go"),
    ".rs": ("tree_sitter_rust", "language", "rust"),
    ".java": ("tree_sitter_java", "language", "java"),
    ".c": ("tree_sitter_c", "language", "c"),
    ".h": ("tree_sitter_c", "language", "c"),
    ".cpp": ("tree_sitter_cpp", "language", "cpp"),
    ".cc": ("tree_sitter_cpp", "language", "cpp"),
    ".cxx": ("tree_sitter_cpp", "language", "cpp"),
    ".hpp": ("tree_sitter_cpp", "language", "cpp"),
    ".rb": ("tree_sitter_ruby", "language", "ruby"),
    ".cs": ("tree_sitter_c_sharp", "language", "csharp"),
    ".kt": ("tree_sitter_kotlin", "language", "kotlin"),
    ".kts": ("tree_sitter_kotlin", "language", "kotlin"),
    ".scala": ("tree_sitter_scala", "language", "scala"),
    ".php": ("tree_sitter_php", "language_php", "php"),
    ".swift": ("tree_sitter_swift", "language", "swift"),
    ".lua": ("tree_sitter_lua", "language", "lua"),
    ".toc": ("tree_sitter_lua", "language", "lua"),
    ".zig": ("tree_sitter_zig", "language", "zig"),
    ".ps1": ("tree_sitter_powershell", "language", "powershell"),
    ".ex": ("tree_sitter_elixir", "language", "elixir"),
    ".exs": ("tree_sitter_elixir", "language", "elixir"),
    ".m": ("tree_sitter_objc", "language", "objc"),
    ".mm": ("tree_sitter_objc", "language", "objc"),
    ".jl": ("tree_sitter_julia", "language", "julia"),
    ".v": ("tree_sitter_verilog", "language", "verilog"),
    ".sv": ("tree_sitter_verilog", "language", "verilog"),
}


@dataclass(frozen=True)
class DatasetExportResult:
    repo_name: str
    repo_root: Path
    dataset_dir: Path
    commit_sha: str
    files_written: int
    files_skipped: int
    skipped_files: list[dict[str, str]]


def _sanitize_repo_name(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-")
    return cleaned or "repo"


def repo_name_from_url(repo_url: str) -> str:
    tail = repo_url.rstrip("/").rsplit("/", 1)[-1]
    if tail.endswith(".git"):
        tail = tail[:-4]
    return _sanitize_repo_name(tail)


def _dataset_filename(relative_path: str) -> str:
    normalized = relative_path.replace("\\", "/").replace("/", "_")
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", normalized)
    return f"{normalized}.json"


def _git_stdout(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def resolve_repo_metadata(repo_root: Path, repo_url: str | None = None) -> tuple[str, str]:
    commit_sha = _git_stdout(repo_root, "rev-parse", "HEAD") or "working-tree"
    if repo_url:
        return commit_sha, repo_url
    discovered = _git_stdout(repo_root, "remote", "get-url", "origin")
    return commit_sha, discovered


def clone_public_repo(repo_url: str, *, checkout_root: Path) -> Path:
    repo_name = repo_name_from_url(repo_url)
    target = checkout_root / repo_name
    if target.exists():
        if not (target / ".git").exists():
            raise ValueError(f"checkout target exists but is not a git repo: {target}")
        return target
    checkout_root.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(target)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"git clone failed for {repo_url}: {detail}")
    return target


def _load_language(module_name: str, fn_name: str):
    mod = importlib.import_module(module_name)
    from tree_sitter import Language

    lang_fn = getattr(mod, fn_name, None)
    if lang_fn is None:
        lang_fn = getattr(mod, "language", None)
    if lang_fn is None:
        raise RuntimeError(f"no language function found in {module_name}")
    return Language(lang_fn())


def _span_payload(node) -> dict[str, Any]:
    return {
        "start": {
            "line": int(node.start_point[0]) + 1,
            "column": int(node.start_point[1]),
            "byte": int(node.start_byte),
        },
        "end": {
            "line": int(node.end_point[0]) + 1,
            "column": int(node.end_point[1]),
            "byte": int(node.end_byte),
        },
    }


def _node_id(*, commit_sha: str, relative_path: str, node) -> str:
    rel = relative_path.replace("\\", "/")
    return f"ast:{commit_sha}:{rel}:{int(node.start_byte)}:{int(node.end_byte)}:{node.type}"


def _node_label(node, source_bytes: bytes) -> str:
    raw = source_bytes[int(node.start_byte) : int(node.end_byte)]
    return raw.decode("utf-8", errors="replace")


def _edge_id(source_id: str, target_id: str, index: int, *, file_id_prefix: str) -> str:
    return f"{file_id_prefix}:edge:{source_id}->{target_id}:{index}"


def _parse_one_file(
    path: Path,
    *,
    repo_root: Path,
    commit_sha: str,
    repository_name: str,
    repository_url: str,
) -> dict[str, Any]:
    if path.name.endswith(".blade.php"):
        raise RuntimeError("blade templates are not supported by the raw AST exporter yet")
    suffix = path.suffix.lower()
    language_spec = _LANGUAGE_BY_SUFFIX.get(suffix)
    if language_spec is None:
        raise RuntimeError(f"unsupported extension for raw AST export: {suffix}")

    module_name, fn_name, source_language = language_spec
    try:
        from tree_sitter import Parser
    except ImportError as exc:  # pragma: no cover - environment safety
        raise RuntimeError("tree-sitter is not installed") from exc

    relative_path = path.relative_to(repo_root).as_posix()
    language = _load_language(module_name, fn_name)
    parser = Parser(language)
    source = path.read_bytes()
    tree = parser.parse(source)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    edge_index = 0
    file_prefix = f"ast:{commit_sha}:{relative_path}"

    def walk(node, parent_id: str | None = None) -> str | None:
        nonlocal edge_index
        if not node.is_named:
            return None
        node_id = _node_id(commit_sha=commit_sha, relative_path=relative_path, node=node)
        child_ids: list[str] = []
        for child in node.children:
            child_id = walk(child, parent_id=node_id)
            if child_id is not None:
                child_ids.append(child_id)
        nodes.append(
            {
                "id": node_id,
                "kind": node.type,
                "label": _node_label(node, source),
                "span": _span_payload(node),
                "children_ids": child_ids,
                "text_digest": hashlib.sha256(
                    source[int(node.start_byte) : int(node.end_byte)]
                ).hexdigest(),
            }
        )
        if parent_id is not None:
            edges.append(
                {
                    "id": _edge_id(parent_id, node_id, edge_index, file_id_prefix=file_prefix),
                    "role": "child",
                    "source_id": parent_id,
                    "target_id": node_id,
                    "type": "child",
                }
            )
            edge_index += 1
        return node_id

    walk(tree.root_node)
    nodes.reverse()
    edges.reverse()
    return {
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "branch": _git_stdout(repo_root, "rev-parse", "--abbrev-ref", "HEAD") or "HEAD",
        "commit_sha": commit_sha,
        "dependency_resolution_status": "manifest_only",
        "edges": edges,
        "errors": [],
        "generation_version": "depos-dataset-export-0.1",
        "nodes": nodes,
        "parser_id": module_name,
        "relative_path": relative_path,
        "repository_name": repository_name,
        "repository_url": repository_url,
        "source_language": source_language,
        "warnings": [],
    }


def export_dataset_from_repo(
    repo_root: Path,
    *,
    dataset_root: Path,
    repo_name: str | None = None,
    repo_url: str | None = None,
) -> DatasetExportResult:
    repo_root = repo_root.resolve()
    resolved_repo_name = _sanitize_repo_name(repo_name or repo_root.name)
    dataset_dir = (dataset_root / resolved_repo_name).resolve()
    dataset_dir.mkdir(parents=True, exist_ok=True)
    commit_sha, resolved_repo_url = resolve_repo_metadata(repo_root, repo_url)

    detected = detect(repo_root)
    code_paths = [Path(raw) for raw in detected.get("files", {}).get("code", [])]
    files_written = 0
    skipped: list[dict[str, str]] = []
    written_names: set[str] = set()

    for path in code_paths:
        try:
            payload = _parse_one_file(
                path,
                repo_root=repo_root,
                commit_sha=commit_sha,
                repository_name=resolved_repo_name,
                repository_url=resolved_repo_url,
            )
        except Exception as exc:  # noqa: BLE001
            skipped.append({"path": str(path), "reason": str(exc)})
            continue
        target = dataset_dir / _dataset_filename(payload["relative_path"])
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written_names.add(target.name)
        files_written += 1

    for stale in dataset_dir.glob("*.json"):
        if stale.name not in written_names:
            stale.unlink()

    return DatasetExportResult(
        repo_name=resolved_repo_name,
        repo_root=repo_root,
        dataset_dir=dataset_dir,
        commit_sha=commit_sha,
        files_written=files_written,
        files_skipped=len(skipped),
        skipped_files=skipped,
    )


def prepare_dataset_from_source(
    *,
    repo_root: Path | None = None,
    repo_url: str | None = None,
    dataset_root: Path = Path("dataset"),
    checkout_root: Path = Path("worked") / "repos",
    repo_name: str | None = None,
) -> DatasetExportResult:
    if bool(repo_root) == bool(repo_url):
        raise ValueError("pass exactly one of repo_root or repo_url")
    if repo_url:
        resolved_repo_root = clone_public_repo(repo_url, checkout_root=checkout_root)
        resolved_repo_name = repo_name or repo_name_from_url(repo_url)
        return export_dataset_from_repo(
            resolved_repo_root,
            dataset_root=dataset_root,
            repo_name=resolved_repo_name,
            repo_url=repo_url,
        )
    assert repo_root is not None
    return export_dataset_from_repo(
        repo_root,
        dataset_root=dataset_root,
        repo_name=repo_name,
    )


__all__ = [
    "DatasetExportResult",
    "clone_public_repo",
    "export_dataset_from_repo",
    "prepare_dataset_from_source",
    "repo_name_from_url",
]
