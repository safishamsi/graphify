"""Dependency manifest ingest."""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import networkx as nx

from depos.analysis.oracles.lockfile_resolver import lookup as lockfile_lookup
from depos.analysis.schemas import IngestReport


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


def _pkg_manifest_id(path: Path) -> str:
    return f"pkg::manifest:{path.as_posix()}"


def _pkg_dep_id(path: Path, package_name: str) -> str:
    return f"pkg::dep:{path.as_posix()}::{package_name}"


def _lock_resolution_id(path: Path, package_name: str, version: str) -> str:
    return f"pkg::lock:{path.as_posix()}::{package_name}@{version}"


def _parse_requirements(path: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for token in ("==", ">=", "<=", "~=", ">", "<"):
            if token in stripped:
                name, version = stripped.split(token, 1)
                out.append((name.strip(), f"{token}{version.strip()}"))
                break
        else:
            out.append((stripped, "*"))
    return out


def _load_package_lock(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    packages = data.get("packages") or {}
    out: dict[str, str] = {}
    if isinstance(packages, dict):
        for pkg_path, payload in packages.items():
            if pkg_path == "":
                continue
            name = str((payload or {}).get("name") or Path(pkg_path).name)
            version = str((payload or {}).get("version") or "")
            if name and version:
                out[name] = version
    deps = data.get("dependencies") or {}
    if isinstance(deps, dict):
        for name, payload in deps.items():
            version = str((payload or {}).get("version") or "")
            if name and version:
                out[name] = version
    return out


def _load_poetry_lock(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    name = ""
    version = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("name = "):
            name = stripped.split("=", 1)[1].strip().strip('"')
        elif stripped.startswith("version = "):
            version = stripped.split("=", 1)[1].strip().strip('"')
        elif stripped == "[[package]]":
            if name and version:
                out[name] = version
            name = ""
            version = ""
    if name and version:
        out[name] = version
    return out


def _load_pyproject(path: Path) -> list[tuple[str, str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    deps: list[tuple[str, str]] = []
    project = data.get("project") or {}
    for dep in project.get("dependencies", []) or []:
        dep = str(dep)
        match = re.match(r"^([A-Za-z0-9_.-]+)(.*)$", dep)
        if match:
            deps.append((match.group(1), match.group(2).strip() or "*"))
    poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
    for name, version in poetry.items():
        if name == "python":
            continue
        if isinstance(version, str):
            deps.append((name, version))
    return deps


def _load_cargo_toml(path: Path) -> list[tuple[str, str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    out: list[tuple[str, str]] = []
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        for name, payload in (data.get(section) or {}).items():
            if isinstance(payload, str):
                out.append((name, payload))
            elif isinstance(payload, dict):
                out.append((name, str(payload.get("version") or "*")))
    return out


def _load_lock_resolutions(path: Path) -> dict[str, str]:
    if path.name == "package-lock.json":
        return _load_package_lock(path)
    if path.name == "poetry.lock":
        return _load_poetry_lock(path)
    return {}


def _emit_manifest(graph: nx.DiGraph, repo_root: Path, path: Path, report: IngestReport) -> None:
    rel = path.relative_to(repo_root)
    manifest_id = _pkg_manifest_id(rel)
    report.files_seen += 1
    if _add_node(
        graph,
        manifest_id,
        node_kind="package_manifest",
        universe="deps",
        source_file=str(path),
        manifest_id=manifest_id,
        ecosystem="npm" if path.name == "package.json" else "python" if path.name.startswith(("requirements", "pyproject")) else "cargo" if path.name == "Cargo.toml" else "generic",
        label=path.name,
        name=path.name,
    ):
        report.nodes_added += 1

    deps: list[tuple[str, str]] = []
    dep_types: dict[str, str] = {}
    lock_resolutions: dict[str, str] = {}

    try:
        if path.name == "package.json":
            data = json.loads(path.read_text(encoding="utf-8"))
            for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                for name, version in (data.get(section) or {}).items():
                    deps.append((name, str(version)))
                    dep_types[name] = section.replace("Dependencies", "").replace("dependencies", "runtime") or "runtime"
            lock_path = path.with_name("package-lock.json")
            if lock_path.exists():
                lock_resolutions = _load_package_lock(lock_path)
        elif path.name.startswith("requirements"):
            deps = _parse_requirements(path)
        elif path.name == "pyproject.toml":
            deps = _load_pyproject(path)
            poetry_lock = path.with_name("poetry.lock")
            if poetry_lock.exists():
                lock_resolutions = _load_poetry_lock(poetry_lock)
        elif path.name == "Cargo.toml":
            deps = _load_cargo_toml(path)
        else:
            lock_resolutions = _load_lock_resolutions(path)
    except Exception as exc:  # noqa: BLE001
        report.errors.append({"path": str(path), "kind": "parse_error", "message": str(exc)})
        return

    for name, declared_range in deps:
        dep_id = _pkg_dep_id(rel, name)
        resolved_version = lock_resolutions.get(name, "")
        oracle = lockfile_lookup({"declared_range": declared_range, "resolved_version": resolved_version})
        attrs = {
            "node_kind": "package_dep",
            "universe": "deps",
            "source_file": str(path),
            "manifest_id": manifest_id,
            "package_name": name,
            "name": name,
            "label": name,
            "declared_range": declared_range,
            "resolved_version": resolved_version,
            "dep_type": dep_types.get(name, "runtime"),
            "declared": True,
            "lockfile_match": oracle.conclusion == "pass" if resolved_version else False,
            "lockfile_drift": bool(resolved_version and oracle.conclusion == "fail"),
            "peer_unsatisfied": dep_types.get(name) == "peer" and bool(resolved_version and oracle.conclusion == "fail"),
            "ecosystem": graph.nodes[manifest_id].get("ecosystem"),
        }
        if _add_node(graph, dep_id, **attrs):
            report.nodes_added += 1
        if _add_edge(graph, manifest_id, dep_id, relation="DECLARES_DEP", source_system="manifest", target_system="deps"):
            report.edges_added += 1
        if resolved_version:
            lock_id = _lock_resolution_id(rel, name, resolved_version)
            if _add_node(
                graph,
                lock_id,
                node_kind="lockfile_resolution",
                universe="deps",
                source_file=str(path),
                package_name=name,
                resolved_version=resolved_version,
                label=f"{name}@{resolved_version}",
                ecosystem=graph.nodes[manifest_id].get("ecosystem"),
            ):
                report.nodes_added += 1
            if _add_edge(graph, dep_id, lock_id, relation="RESOLVES_TO", source_system="deps", target_system="deps"):
                report.edges_added += 1


def ingest(graph: nx.DiGraph, *, repo_root: Path, config) -> IngestReport:
    report = IngestReport(module=__name__)
    patterns = [
        "package.json",
        "requirements*.txt",
        "pyproject.toml",
        "Cargo.toml",
    ]
    seen: set[Path] = set()
    for pattern in patterns:
        for path in repo_root.glob(f"**/{pattern}"):
            if path in seen or "node_modules" in path.parts or ".next" in path.parts:
                continue
            seen.add(path)
            _emit_manifest(graph, repo_root, path, report)
    return report


__all__ = ["ingest"]
