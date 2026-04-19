"""Infra ingest for Docker, Compose, and GitHub Actions."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import networkx as nx

from depos.analysis.schemas import IngestReport

_SECRET_REF = re.compile(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}")
_MATRIX_NODE = re.compile(r"node-version\s*:\s*(.+)")


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


def _yaml_like(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _compose_services_from_text(text: str) -> dict[str, dict[str, Any]]:
    services: dict[str, dict[str, Any]] = {}
    current = ""
    in_services = False
    current_section = ""
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.strip() == "services:":
            in_services = True
            continue
        if in_services and not line.startswith(" "):
            break
        if in_services and re.match(r"^\s{2}[A-Za-z0-9_-]+:\s*$", line):
            current = line.strip().rstrip(":")
            current_section = ""
            services[current] = {"networks": [], "depends_on": []}
            continue
        if not current:
            continue
        if re.match(r"^\s{4}(depends_on|networks):\s*$", line):
            current_section = line.strip().rstrip(":")
            continue
        if re.match(r"^\s{4}build:\s*", line):
            services[current]["build"] = line.split(":", 1)[1].strip() or "."
            current_section = ""
            continue
        if re.match(r"^\s{6}-\s*", line) and current_section in {"depends_on", "networks"}:
            services[current][current_section].append(line.split("-", 1)[1].strip())
    return services


def _workflow_jobs_from_text(text: str) -> dict[str, dict[str, Any]]:
    jobs: dict[str, dict[str, Any]] = {}
    current = ""
    in_jobs = False
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.strip() == "jobs:":
            in_jobs = True
            continue
        if in_jobs and not line.startswith(" "):
            break
        if in_jobs and re.match(r"^\s{2}[A-Za-z0-9_-]+:\s*$", line):
            current = line.strip().rstrip(":")
            jobs[current] = {}
    return jobs


def _dockerfile(graph: nx.DiGraph, repo_root: Path, path: Path, report: IngestReport) -> None:
    rel = path.relative_to(repo_root)
    text = path.read_text(encoding="utf-8", errors="replace")
    stage_name = "default"
    lines = text.splitlines()
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.upper().startswith("FROM "):
            stage_name = stripped.split(" AS ", 1)[-1].strip() if " AS " in stripped.upper() else f"stage{idx}"
            node_id = f"infra::docker-stage:{rel.as_posix()}::{stage_name}"
            if _add_node(
                graph,
                node_id,
                node_kind="dockerfile_stage",
                universe="infra",
                source_file=str(path),
                label=stage_name,
                stage_name=stage_name,
                build_context=str(rel.parent.as_posix() or "."),
            ):
                report.nodes_added += 1
        elif stripped.upper().startswith("COPY "):
            source_path = stripped.split()[1] if len(stripped.split()) > 2 else ""
            copy_id = f"infra::copy:{rel.as_posix()}::{idx}"
            if _add_node(
                graph,
                copy_id,
                node_kind="config_key",
                universe="infra",
                source_file=str(path),
                label=f"COPY {source_path}",
                copy_source=source_path,
            ):
                report.nodes_added += 1
            stage_id = f"infra::docker-stage:{rel.as_posix()}::{stage_name}"
            if _add_edge(graph, stage_id, copy_id, relation="STAGE_COPIES_PATH", source_system="infra", target_system="infra"):
                report.edges_added += 1


def _compose(graph: nx.DiGraph, repo_root: Path, path: Path, report: IngestReport) -> None:
    rel = path.relative_to(repo_root)
    data = _yaml_like(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    services = data.get("services") or {}
    if not isinstance(services, dict) or not services:
        services = _compose_services_from_text(text)
    if not isinstance(services, dict):
        return
    for name, payload in services.items():
        if not isinstance(payload, dict):
            continue
        node_id = f"infra::service:{rel.as_posix()}::{name}"
        if _add_node(
            graph,
            node_id,
            node_kind="infra_service",
            universe="infra",
            source_file=str(path),
            label=name,
            service_name=name,
            networks=sorted(str(item) for item in (payload.get("networks") or [])),
            depends_on=sorted(str(item) for item in (payload.get("depends_on") or [])),
            build_context=str((payload.get("build") or {}).get("context") if isinstance(payload.get("build"), dict) else payload.get("build") or "."),
        ):
            report.nodes_added += 1
    for source_id, attrs in list(graph.nodes(data=True)):
        if attrs.get("node_kind") != "infra_service" or attrs.get("source_file") != str(path):
            continue
        for dep in attrs.get("depends_on") or []:
            target_id = f"infra::service:{rel.as_posix()}::{dep}"
            if graph.has_node(target_id) and _add_edge(graph, source_id, target_id, relation="SERVICE_DEPENDS_ON", source_system="infra", target_system="infra"):
                report.edges_added += 1


def _workflow(graph: nx.DiGraph, repo_root: Path, path: Path, report: IngestReport) -> None:
    rel = path.relative_to(repo_root)
    text = path.read_text(encoding="utf-8", errors="replace")
    data = _yaml_like(path)
    jobs = data.get("jobs") or {}
    if not isinstance(jobs, dict):
        jobs = {}
    if not jobs:
        jobs = _workflow_jobs_from_text(text)
    declared = sorted(set(re.findall(r"^\s*([A-Z0-9_]+):", text, flags=re.MULTILINE)))
    for job_name, payload in jobs.items():
        if not isinstance(payload, dict):
            continue
        node_id = f"infra::workflow:{rel.as_posix()}::{job_name}"
        secrets = sorted(set(match.group(1) for match in _SECRET_REF.finditer(text)))
        matrix_line = _MATRIX_NODE.search(text)
        matrix_versions = []
        if matrix_line:
            raw = matrix_line.group(1).strip()
            matrix_versions = [item.strip().strip("'\"[] ") for item in raw.split(",") if item.strip()]
        if _add_node(
            graph,
            node_id,
            node_kind="infra_workflow",
            universe="infra",
            source_file=str(path),
            label=job_name,
            job_name=job_name,
            secrets=secrets,
            declared_secrets=declared,
            matrix_node_versions=matrix_versions,
        ):
            report.nodes_added += 1
        for secret in secrets:
            secret_id = f"infra::secret:{rel.as_posix()}::{secret}"
            if _add_node(
                graph,
                secret_id,
                node_kind="config_key",
                universe="infra",
                source_file=str(path),
                label=secret,
                key=secret,
            ):
                report.nodes_added += 1
            if _add_edge(graph, node_id, secret_id, relation="WORKFLOW_USES_SECRET", source_system="infra", target_system="infra"):
                report.edges_added += 1


def ingest(graph: nx.DiGraph, *, repo_root: Path, config) -> IngestReport:
    report = IngestReport(module=__name__)
    for pattern in ("**/Dockerfile", "**/Dockerfile.*"):
        for path in repo_root.glob(pattern):
            if path.is_file():
                report.files_seen += 1
                try:
                    _dockerfile(graph, repo_root, path, report)
                except Exception as exc:  # noqa: BLE001
                    report.errors.append({"path": str(path), "kind": "parse_error", "message": str(exc)})
    for pattern in ("**/docker-compose.yml", "**/docker-compose.yaml", "**/compose.yml", "**/compose.yaml"):
        for path in repo_root.glob(pattern):
            if path.is_file():
                report.files_seen += 1
                try:
                    _compose(graph, repo_root, path, report)
                except Exception as exc:  # noqa: BLE001
                    report.errors.append({"path": str(path), "kind": "parse_error", "message": str(exc)})
    for path in repo_root.glob(".github/workflows/*.*"):
        if path.is_file():
            report.files_seen += 1
            try:
                _workflow(graph, repo_root, path, report)
            except Exception as exc:  # noqa: BLE001
                report.errors.append({"path": str(path), "kind": "parse_error", "message": str(exc)})
    return report


__all__ = ["ingest"]
