"""Prompt/template ingest."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import networkx as nx

from depos.analysis.schemas import IngestReport
from depos.ingest.common import upsert_node

_DEFAULT_GLOBS = [
    "**/prompts/**/*.{md,toml,json,prompt}",
    "**/.cursor/rules/*.md",
    "**/agents/**/*.{md,toml}",
]
_DECLARED_VAR_PATTERNS = [
    re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*\}\}"),
    re.compile(r"\$\{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*\}"),
    re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_.-]*)\}(?!\})"),
]
def _load_yaml_like(path: Path) -> dict[str, Any]:
    return _load_yaml_text(path.read_text(encoding="utf-8", errors="replace"))


def _load_yaml_text(text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        out: dict[str, Any] = {}
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            out[key.strip()] = value.strip().strip('"').strip("'")
        return out


def _load_registry() -> dict[str, dict[str, Any]]:
    base = Path(__file__).parent / "prompt_schemas" / "registry.yaml"
    if not base.exists():
        return {}
    raw = _load_yaml_like(base)
    schemas = raw.get("schemas") if isinstance(raw, dict) else None
    return dict(schemas) if isinstance(schemas, dict) else {}


def _prompt_node_id(rel: Path) -> str:
    return f"prompt::{rel.as_posix()}"


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return {}, text
    lines = stripped.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    collected: list[str] = []
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body = "\n".join(lines[idx + 1 :])
            payload = _load_yaml_text("\n".join(collected))
            return payload, body
        collected.append(line)
    return {}, text


def _extract_vars(text: str) -> list[str]:
    out: set[str] = set()
    for pattern in _DECLARED_VAR_PATTERNS:
        out.update(pattern.findall(text))
    return sorted(out)


def _schema_for(path: Path, frontmatter: dict[str, Any], registry: dict[str, dict[str, Any]]) -> tuple[str, str]:
    family = str(frontmatter.get("schema_id") or frontmatter.get("family") or path.stem).strip()
    if family in registry:
        row = registry[family]
        return family, str(row.get("file") or "default.schema.json")
    default = registry.get("default", {})
    return family, str(default.get("file") or "default.schema.json")


def _providers(frontmatter: dict[str, Any], schema_id: str, registry: dict[str, dict[str, Any]]) -> list[str]:
    provider = frontmatter.get("provider")
    if provider:
        if isinstance(provider, str):
            return [provider]
        if isinstance(provider, list):
            return [str(item) for item in provider]
    row = registry.get(schema_id) or registry.get("default") or {}
    providers = row.get("providers")
    if isinstance(providers, list):
        return [str(item) for item in providers]
    if isinstance(providers, str):
        return [providers]
    return ["generic"]


def _iter_paths(repo_root: Path, patterns: list[str]) -> list[Path]:
    seen: set[Path] = set()
    results: list[Path] = []
    for pattern in patterns:
        if "{" in pattern and "}" in pattern:
            prefix, suffix = pattern.split("{", 1)
            choices, tail = suffix.split("}", 1)
            for choice in choices.split(","):
                for path in repo_root.glob(f"{prefix}{choice}{tail}"):
                    if path.is_file() and path not in seen and "node_modules" not in path.parts and ".next" not in path.parts:
                        seen.add(path)
                        results.append(path)
            continue
        for path in repo_root.glob(pattern):
            if path.is_file() and path not in seen and "node_modules" not in path.parts and ".next" not in path.parts:
                seen.add(path)
                results.append(path)
    results.sort()
    return results


def ingest(graph: nx.DiGraph, *, repo_root: Path, config) -> IngestReport:
    report = IngestReport(module=__name__)
    registry = _load_registry()
    patterns = list(getattr(config, "prompt_globs", _DEFAULT_GLOBS))
    for path in _iter_paths(repo_root, patterns):
        report.files_seen += 1
        try:
            rel = path.relative_to(repo_root)
            text = path.read_text(encoding="utf-8", errors="replace")
            frontmatter, body = _frontmatter(text)
            declared = _extract_vars(body)
            schema_id, schema_file = _schema_for(path, frontmatter, registry)
            providers = _providers(frontmatter, schema_id, registry)
            node_id = _prompt_node_id(rel)
            attrs = {
                "node_kind": "prompt_template",
                "universe": "prompt",
                "source_file": str(path),
                "label": path.name,
                "name": path.stem,
                "schema_id": schema_id,
                "schema_file": str((Path(__file__).parent / "prompt_schemas" / schema_file).resolve()),
                "declared_vars": declared,
                "used_vars": declared,
                "frontmatter": frontmatter,
                "provider": providers[0] if providers else "generic",
                "provider_versions": providers,
                "template_family": path.parent.name,
                "template_text": body[:8000],
            }
            if upsert_node(graph, node_id, **attrs):
                report.nodes_added += 1
        except Exception as exc:  # noqa: BLE001
            report.errors.append({"path": str(path), "kind": "parse_error", "message": str(exc)})
    return report


__all__ = ["ingest"]
