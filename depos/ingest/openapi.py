"""OpenAPI ingest."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

from depos.analysis.schemas import IngestReport
from depos.ingest.common import add_edge_once, upsert_node

_DEFAULT_GLOBS = ["**/openapi.yaml", "**/openapi.yml", "**/openapi.json"]


def _load_doc(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        return dict(data) if isinstance(data, dict) else {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        return dict(data) if isinstance(data, dict) else {}
    except Exception as exc:
        raise ValueError(f"could not parse {path.name}: {exc}") from exc


def _schema_required(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    required = payload.get("required")
    if isinstance(required, list):
        return [str(item) for item in required]
    return []


def _schema_properties(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    properties = payload.get("properties")
    if isinstance(properties, dict):
        return sorted(str(key) for key in properties)
    return []


def _schema_enums(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    enums = payload.get("enum")
    if isinstance(enums, list):
        return sorted(str(item) for item in enums)
    return []


def _emit_operation(graph: nx.DiGraph, path: Path, rel: Path, method: str, route: str, payload: dict[str, Any], report: IngestReport) -> None:
    operation_id = str(payload.get("operationId") or f"{method}:{route}")
    node_id = f"openapi::op:{rel.as_posix()}::{method}:{route}"
    request_required: list[str] = []
    request_properties: list[str] = []
    response_properties: list[str] = []
    enum_values: set[str] = set()
    request_schema_name = ""
    response_schema_name = ""

    request_body = payload.get("requestBody") or {}
    content = (request_body.get("content") or {}) if isinstance(request_body, dict) else {}
    for media in content.values() if isinstance(content, dict) else []:
        schema = media.get("schema") if isinstance(media, dict) else None
        if isinstance(schema, dict):
            request_required.extend(_schema_required(schema))
            request_properties.extend(_schema_properties(schema))
            enum_values.update(_schema_enums(schema))
            request_schema_name = str(schema.get("$ref") or request_schema_name)

    responses = payload.get("responses") or {}
    if isinstance(responses, dict):
        for response in responses.values():
            content = (response.get("content") or {}) if isinstance(response, dict) else {}
            for media in content.values() if isinstance(content, dict) else []:
                schema = media.get("schema") if isinstance(media, dict) else None
                if isinstance(schema, dict):
                    response_properties.extend(_schema_properties(schema))
                    enum_values.update(_schema_enums(schema))
                    response_schema_name = str(schema.get("$ref") or response_schema_name)

    if upsert_node(
        graph,
        node_id,
        node_kind="openapi_operation",
        universe="schema",
        source_file=str(path),
        label=f"{method.upper()} {route}",
        path=route,
        method=method.upper(),
        operation_id=operation_id,
        request_required_fields=sorted(set(request_required)),
        request_fields=sorted(set(request_properties)),
        response_fields=sorted(set(response_properties)),
        enum_values=sorted(enum_values),
        request_schema_name=request_schema_name,
        response_schema_name=response_schema_name,
    ):
        report.nodes_added += 1


def _emit_schema(graph: nx.DiGraph, path: Path, rel: Path, name: str, payload: dict[str, Any], report: IngestReport) -> str:
    node_id = f"openapi::schema:{rel.as_posix()}::{name}"
    if upsert_node(
        graph,
        node_id,
        node_kind="openapi_schema",
        universe="schema",
        source_file=str(path),
        label=name,
        name=name,
        required_fields=_schema_required(payload),
        fields=_schema_properties(payload),
        enum_values=_schema_enums(payload),
        schema=payload,
    ):
        report.nodes_added += 1
    return node_id


def ingest(graph: nx.DiGraph, *, repo_root: Path, config) -> IngestReport:
    report = IngestReport(module=__name__)
    patterns = list(getattr(config, "openapi_globs", _DEFAULT_GLOBS))
    seen: set[Path] = set()
    for pattern in patterns:
        for path in repo_root.glob(pattern):
            if path in seen or not path.is_file() or "node_modules" in path.parts or ".next" in path.parts:
                continue
            seen.add(path)
            report.files_seen += 1
            try:
                rel = path.relative_to(repo_root)
                doc = _load_doc(path)
                paths = doc.get("paths") or {}
                for route, methods in paths.items() if isinstance(paths, dict) else []:
                    if not isinstance(methods, dict):
                        continue
                    for method, payload in methods.items():
                        if not isinstance(payload, dict):
                            continue
                        _emit_operation(graph, path, rel, str(method), str(route), payload, report)
                schemas = (((doc.get("components") or {}).get("schemas")) or {}) if isinstance(doc, dict) else {}
                schema_ids: dict[str, str] = {}
                if isinstance(schemas, dict):
                    for name, payload in schemas.items():
                        if isinstance(payload, dict):
                            schema_ids[name] = _emit_schema(graph, path, rel, str(name), payload, report)
                for node_id, attrs in list(graph.nodes(data=True)):
                    if attrs.get("node_kind") != "openapi_operation" or attrs.get("source_file") != str(path):
                        continue
                    for key in ("request_schema_name", "response_schema_name"):
                        ref = str(attrs.get(key) or "")
                        schema_name = ref.rsplit("/", 1)[-1] if ref else ""
                        schema_id = schema_ids.get(schema_name)
                        if schema_id and add_edge_once(graph, node_id, schema_id, relation="SCHEMA_OF", source_system="openapi", target_system="schema"):
                            report.edges_added += 1
            except Exception as exc:  # noqa: BLE001
                report.errors.append({"path": str(path), "kind": "parse_error", "message": str(exc)})
    return report


__all__ = ["ingest"]
