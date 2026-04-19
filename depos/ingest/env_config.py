"""Environment and config ingest."""
from __future__ import annotations

import json
import re
import tomllib
from collections import defaultdict
from pathlib import Path

import networkx as nx

from depos.analysis.schemas import IngestReport
from depos.env import _parse_env_line


def _add_node(graph: nx.DiGraph, node_id: str, **attrs) -> bool:
    if graph.has_node(node_id):
        graph.nodes[node_id].update(attrs)
        return False
    graph.add_node(node_id, **attrs)
    return True


def _add_edge(graph: nx.DiGraph, source: str, target: str, **attrs) -> bool:
    if graph.has_edge(source, target):
        return False
    graph.add_edge(source, target, **attrs)
    return True


def _infer_type(value: str) -> str:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return "bool"
    if re.fullmatch(r"-?\d+", value):
        return "int"
    if re.fullmatch(r"-?\d+\.\d+", value):
        return "float"
    if value.startswith(("http://", "https://")):
        return "url"
    return "string"


def _env_node_id(name: str, path: Path) -> str:
    return f"env::{name}@{path.as_posix()}"


def _config_node_id(key: str, path: Path) -> str:
    return f"config::{key}@{path.as_posix()}"


def _scan_env_file(graph: nx.DiGraph, repo_root: Path, path: Path, report: IngestReport, seen_types: dict[str, set[str]]) -> None:
    rel = path.relative_to(repo_root)
    report.files_seen += 1
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        name, value = parsed
        node_id = _env_node_id(name, rel)
        inferred = _infer_type(value)
        seen_types[name].add(inferred)
        if _add_node(
            graph,
            node_id,
            node_kind="env_var",
            universe="env",
            source_file=str(path),
            name=name,
            label=name,
            value=value,
            defined=True,
            expected_type=inferred,
        ):
            report.nodes_added += 1
        config_id = _config_node_id(name, rel)
        if _add_node(
            graph,
            config_id,
            node_kind="config_key",
            universe="env",
            source_file=str(path),
            key=name,
            label=name,
            value=value,
            origin=_origin_from_value(value),
        ):
            report.nodes_added += 1
        if _add_edge(graph, config_id, node_id, relation="DEFINED_BY_CONFIG", source_system="config", target_system="env"):
            report.edges_added += 1


def _origin_from_value(value: str) -> str:
    if value.startswith(("http://", "https://")):
        parts = value.split("/", 3)
        return "/".join(parts[:3])
    return value


def _scan_json_config(graph: nx.DiGraph, repo_root: Path, path: Path, report: IngestReport) -> None:
    report.files_seen += 1
    rel = path.relative_to(repo_root)
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, value in data.items():
        node_id = _config_node_id(key, rel)
        attrs = {
            "node_kind": "config_key",
            "universe": "env",
            "source_file": str(path),
            "key": key,
            "label": key,
            "value": value,
        }
        if key.lower().endswith("origins") and isinstance(value, list):
            attrs["origins"] = value
        if _add_node(graph, node_id, **attrs):
            report.nodes_added += 1


def _scan_js_config(graph: nx.DiGraph, repo_root: Path, path: Path, report: IngestReport) -> None:
    report.files_seen += 1
    rel = path.relative_to(repo_root)
    text = path.read_text(encoding="utf-8", errors="replace")
    env_refs = sorted(set(re.findall(r"process\.env\.([A-Z0-9_]+)", text)))
    redirects = re.findall(r"""destination:\s*["']([^"']+)["']""", text)
    node_id = _config_node_id(path.stem, rel)
    if _add_node(
        graph,
        node_id,
        node_kind="config_key",
        universe="env",
        source_file=str(path),
        key=path.stem,
        label=path.name,
        env_refs=env_refs,
        redirect_targets=redirects,
    ):
        report.nodes_added += 1
    for env_name in env_refs:
        env_id = _env_node_id(env_name, rel)
        if _add_node(
            graph,
            env_id,
            node_kind="env_var",
            universe="env",
            source_file=str(path),
            name=env_name,
            label=env_name,
            defined=False,
        ):
            report.nodes_added += 1
        if _add_edge(graph, node_id, env_id, relation="READS_ENV_VAR", source_system="config", target_system="env"):
            report.edges_added += 1


def _scan_toml(graph: nx.DiGraph, repo_root: Path, path: Path, report: IngestReport) -> None:
    report.files_seen += 1
    rel = path.relative_to(repo_root)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    for section, payload in data.items():
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            full_key = f"{section}.{key}"
            node_id = _config_node_id(full_key, rel)
            attrs = {
                "node_kind": "config_key",
                "universe": "env",
                "source_file": str(path),
                "key": full_key,
                "label": full_key,
                "value": value,
            }
            if "origins" in key.lower() and isinstance(value, list):
                attrs["origins"] = value
            if _add_node(graph, node_id, **attrs):
                report.nodes_added += 1


def ingest(graph: nx.DiGraph, *, repo_root: Path, config) -> IngestReport:
    report = IngestReport(module=__name__)
    seen_types: dict[str, set[str]] = defaultdict(set)

    for path in repo_root.glob("**/.env*"):
        if not path.is_file() or "node_modules" in path.parts or ".next" in path.parts:
            continue
        _scan_env_file(graph, repo_root, path, report, seen_types)

    for path in repo_root.glob("**/tsconfig.json"):
        if path.is_file():
            try:
                _scan_json_config(graph, repo_root, path, report)
            except Exception as exc:  # noqa: BLE001
                report.errors.append({"path": str(path), "kind": "parse_error", "message": str(exc)})

    for pattern in ("**/next.config.js", "**/next.config.ts", "**/next.config.mjs", "**/tailwind.config.ts", "**/tailwind.config.js"):
        for path in repo_root.glob(pattern):
            if path.is_file():
                try:
                    _scan_js_config(graph, repo_root, path, report)
                except Exception as exc:  # noqa: BLE001
                    report.errors.append({"path": str(path), "kind": "parse_error", "message": str(exc)})

    for path in repo_root.glob("**/supabase/config.toml"):
        if path.is_file():
            try:
                _scan_toml(graph, repo_root, path, report)
            except Exception as exc:  # noqa: BLE001
                report.errors.append({"path": str(path), "kind": "parse_error", "message": str(exc)})

    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("node_kind") == "env_var":
            name = str(attrs.get("name") or "")
            attrs["typed_drift"] = len(seen_types.get(name, set())) > 1
    return report


__all__ = ["ingest"]
