"""Module 1 orchestrator: run all probes, emit semantic edges, compute the
:class:`StitcherCoverageReport`.

Writes back into the SAME ``nx.DiGraph`` passed in. Callers that need the
pre-enrichment graph should copy it before calling :func:`enrich_graph`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

import networkx as nx

from depos.analysis.config import IntelligenceConfig
from depos.analysis.schemas import IngestReport
from depos.analysis.schemas import (
    ContractKind,
    RLSCoverage,
    SemanticEdgeMetadata,
    StitcherCoverageReport,
)
from depos.enrichment.http_probes import (
    annotate_fastapi_routes,
    annotate_ts_http_calls,
    iter_fastapi_route_nodes,
)
from depos.enrichment.url_normalize import normalize_route, score_match

HTTP_CALLS_ROUTE = "HTTP_CALLS_ROUTE"
ROUTE_READS_TABLE = "ROUTE_READS_TABLE"
ROUTE_WRITES_TABLE = "ROUTE_WRITES_TABLE"
ROUTE_CALLS_RPC = "ROUTE_CALLS_RPC"
ROUTE_GUARDED_BY_RLS = "ROUTE_GUARDED_BY_RLS"
TASK_ENQUEUES = "TASK_ENQUEUES"
TASK_CONSUMES = "TASK_CONSUMES"
PRODUCES_PAYLOAD = "PRODUCES_PAYLOAD"
CONSUMES_PAYLOAD = "CONSUMES_PAYLOAD"
SCHEMA_DEFINED_BY_MIGRATION = "SCHEMA_DEFINED_BY_MIGRATION"
MIGRATION_PRECEDES = "MIGRATION_PRECEDES"
DECLARES_DEP = "DECLARES_DEP"
RESOLVES_TO = "RESOLVES_TO"
PEER_OF = "PEER_OF"
IMPORTS_PACKAGE = "IMPORTS_PACKAGE"
READS_ENV_VAR = "READS_ENV_VAR"
WRITES_ENV_VAR = "WRITES_ENV_VAR"
DEFINED_BY_CONFIG = "DEFINED_BY_CONFIG"
RENDERED_BY_PROMPT = "RENDERED_BY_PROMPT"
PROMPT_DECLARES_VAR = "PROMPT_DECLARES_VAR"
PROMPT_USES_VAR = "PROMPT_USES_VAR"
IMPLEMENTS_OPENAPI_OP = "IMPLEMENTS_OPENAPI_OP"
CONSUMES_OPENAPI_OP = "CONSUMES_OPENAPI_OP"
SCHEMA_OF = "SCHEMA_OF"
NEXT_ROUTE_GUARDED_BY_MIDDLEWARE = "NEXT_ROUTE_GUARDED_BY_MIDDLEWARE"
NEXT_ROUTE_USES_LAYOUT = "NEXT_ROUTE_USES_LAYOUT"
WORKFLOW_USES_SECRET = "WORKFLOW_USES_SECRET"
SERVICE_DEPENDS_ON = "SERVICE_DEPENDS_ON"
STAGE_COPIES_PATH = "STAGE_COPIES_PATH"


def _edge_key(metadata: SemanticEdgeMetadata) -> str:
    """Stable edge key suffix so the same edge is not double-emitted."""
    return f"{metadata.contract_kind}:{metadata.api_method or ''}:{metadata.route_pattern or metadata.table_name or metadata.task_name or ''}"


def _safe_run(name: str, fn: Callable[[], Any], errors_out: list[dict[str, Any]]) -> Any:
    try:
        return fn()
    except ImportError as exc:
        errors_out.append({"probe": name, "kind": "import_error", "message": str(exc)})
    except Exception as exc:  # noqa: BLE001 - defensive by design
        errors_out.append({"probe": name, "kind": "probe_error", "message": str(exc)})
    return None


def emit_http_calls_route(graph: nx.DiGraph) -> int:
    """Match annotated TS fetch/axios call sites to annotated FastAPI route
    nodes and emit :data:`HTTP_CALLS_ROUTE` edges.

    Returns the number of edges added.
    """
    # Index FastAPI routes by normalized (method, path).
    routes: list[tuple[str, object]] = []
    for nid, attrs in iter_fastapi_route_nodes(graph):
        method = (attrs.get("http_method") or "").upper()
        path = attrs.get("route_pattern") or ""
        routes.append((nid, normalize_route(path, method=method)))

    if not routes:
        return 0

    added = 0
    for node_id, node_attrs in list(graph.nodes(data=True)):
        sites = node_attrs.get("http_call_sites")
        if not sites:
            continue
        for site in sites:
            client = normalize_route(
                site["url_literal"],
                method=site.get("http_method"),
                strip_api=True,
            )
            best = None
            best_score = 0.0
            for (handler_id, server_nr) in routes:
                result = score_match(
                    client,
                    server_nr,
                    client_is_dynamic_url=bool(site.get("is_dynamic_url")),
                    client_method_inferred=bool(site.get("method_inferred")),
                )
                if result.emit and result.score > best_score:
                    best = (handler_id, server_nr, result)
                    best_score = result.score
            if best is None:
                continue
            handler_id, server_nr, result = best

            metadata = SemanticEdgeMetadata(
                confidence=result.score,
                inferred=result.inferred,
                source_system="typescript",
                target_system="python",
                contract_kind=ContractKind.http,
                api_method=server_nr.method,
                route_pattern=server_nr.normalized,
            )
            graph.add_edge(
                site.get("node_id", node_id),
                handler_id,
                key=_edge_key(metadata),
                relation=HTTP_CALLS_ROUTE,
                **metadata.model_dump(mode="json"),
            )
            added += 1
    return added


def _discover_rls_policy_nodes(graph: nx.DiGraph) -> int:
    """Count nodes that look like RLS policies so the coverage report can
    distinguish "no SQL extracted" (0) from "SQL extracted but no policies"."""
    count = 0
    for _, attrs in graph.nodes(data=True):
        label = (attrs.get("label") or "").lower()
        relation = attrs.get("relation") or ""
        if "rls" in label or "policy" in label and label.startswith(("create policy", "rls_")):
            count += 1
            continue
        if relation in {"rls_policy", "policy"}:
            count += 1
    return count


def _discover_migration_files(graph: nx.DiGraph, glob: str, repo_root: Optional[Path] = None) -> int:
    """Count migration files present in the graph (via source_file) AND on
    disk at the configured glob. We report the on-disk number so the
    coverage report reflects what Module 1 can actually sequence over.
    """
    base = repo_root or Path()
    on_disk = sorted(base.glob(glob))
    return len(on_disk)


def compute_coverage(
    graph: nx.DiGraph,
    *,
    config: IntelligenceConfig,
    repo_root: Optional[Path] = None,
) -> StitcherCoverageReport:
    routes = list(iter_fastapi_route_nodes(graph))
    total = len(routes)
    linked = 0
    unlinked: list[str] = []
    for nid, attrs in routes:
        has_incoming = any(
            data.get("relation") == HTTP_CALLS_ROUTE for _, _, data in graph.in_edges(nid, data=True)
        )
        if has_incoming:
            linked += 1
        else:
            pattern = attrs.get("route_pattern") or nid
            method = (attrs.get("http_method") or "").upper()
            unlinked.append(f"{method} {pattern}".strip())

    ratio = (linked / total) if total else 1.0
    report = StitcherCoverageReport(
        total_fastapi_routes=total,
        linked_routes=linked,
        unlinked_routes=unlinked,
        coverage_ratio=round(ratio, 4),
        low_coverage=total > 0 and ratio < config.low_stitcher_coverage_threshold,
        rls_nodes_found=_discover_rls_policy_nodes(graph),
        migration_files_found=_discover_migration_files(graph, config.migration_glob, repo_root),
    )
    return report


def enrich_graph(
    graph: nx.DiGraph,
    *,
    config: IntelligenceConfig,
    repo_root: Optional[Path] = None,
) -> tuple[nx.DiGraph, StitcherCoverageReport]:
    """Run all Module 1 passes in order and return the enriched graph plus
    the :class:`StitcherCoverageReport`.

    Graceful degradation: each probe catches its own errors so a bug in one
    does not prevent the others from running.
    """
    graph.graph["migration_glob"] = config.migration_glob
    errors: list[dict[str, Any]] = []
    ingest_reports: list[IngestReport] = []

    # Layer 0 - ingest extra universes before stitching them into code nodes.
    if repo_root is not None:
        result = _safe_run(
            "ingest_all",
            lambda: __import__("depos.ingest", fromlist=["ingest_all"]).ingest_all(  # noqa: WPS421
                graph,
                repo_root=repo_root,
                config=config,
            ),
            errors,
        )
        if isinstance(result, list):
            ingest_reports = result
            for report in ingest_reports:
                if hasattr(report, "errors"):
                    errors.extend(list(report.errors))

    # 1. HTTP probes (annotate nodes)
    _safe_run("annotate_fastapi_routes", lambda: annotate_fastapi_routes(graph, repo_root=repo_root), errors)
    _safe_run("annotate_ts_http_calls", lambda: annotate_ts_http_calls(graph, repo_root=repo_root), errors)

    # 2. Existing code-centric stitchers
    _safe_run("emit_http_calls_route", lambda: emit_http_calls_route(graph), errors)
    _safe_run(
        "emit_rls_edges",
        lambda: __import__("depos.enrichment.rls_resolver", fromlist=["emit_rls_edges"]).emit_rls_edges(  # noqa: WPS421
            graph,
            repo_root=repo_root,
        ),
        errors,
    )
    _safe_run(
        "emit_migration_edges",
        lambda: __import__("depos.enrichment.migrations", fromlist=["emit_migration_edges"]).emit_migration_edges(  # noqa: WPS421
            graph,
            config=config,
            repo_root=repo_root,
        ),
        errors,
    )
    _safe_run(
        "emit_celery_payload_edges",
        lambda: __import__("depos.enrichment.celery_payload", fromlist=["emit_celery_payload_edges"]).emit_celery_payload_edges(  # noqa: WPS421
            graph,
            repo_root=repo_root,
        ),
        errors,
    )

    # 3. Cross-universe resolvers
    _safe_run(
        "emit_dependency_edges",
        lambda: __import__("depos.enrichment.deps_resolver", fromlist=["emit_dependency_edges"]).emit_dependency_edges(  # noqa: WPS421
            graph,
            repo_root=repo_root,
        ),
        errors,
    )
    _safe_run(
        "emit_env_edges",
        lambda: __import__("depos.enrichment.env_resolver", fromlist=["emit_env_edges"]).emit_env_edges(  # noqa: WPS421
            graph,
            repo_root=repo_root,
        ),
        errors,
    )
    _safe_run(
        "emit_prompt_edges",
        lambda: __import__("depos.enrichment.prompt_resolver", fromlist=["emit_prompt_edges"]).emit_prompt_edges(  # noqa: WPS421
            graph,
            repo_root=repo_root,
        ),
        errors,
    )
    _safe_run(
        "emit_openapi_edges",
        lambda: __import__("depos.enrichment.openapi_resolver", fromlist=["emit_openapi_edges"]).emit_openapi_edges(  # noqa: WPS421
            graph,
            repo_root=repo_root,
        ),
        errors,
    )
    _safe_run(
        "emit_nextjs_edges",
        lambda: __import__("depos.enrichment.nextjs_resolver", fromlist=["emit_nextjs_edges"]).emit_nextjs_edges(  # noqa: WPS421
            graph,
            repo_root=repo_root,
        ),
        errors,
    )

    coverage = compute_coverage(graph, config=config, repo_root=repo_root)
    coverage.errors.extend(errors)
    # Expose run-level metadata so downstream modules / CLI can read flags.
    graph.graph.setdefault("run_metadata", {})
    graph.graph["run_metadata"]["low_stitcher_coverage"] = coverage.low_coverage
    graph.graph["run_metadata"]["coverage"] = coverage.model_dump(mode="json")
    graph.graph["run_metadata"]["ingest_reports"] = [report.model_dump(mode="json") for report in ingest_reports]
    graph.graph["run_metadata"]["ingest_errors"] = list(errors)
    return graph, coverage


__all__ = [
    "enrich_graph",
    "compute_coverage",
    "emit_http_calls_route",
    "HTTP_CALLS_ROUTE",
    "ROUTE_READS_TABLE",
    "ROUTE_WRITES_TABLE",
    "ROUTE_CALLS_RPC",
    "ROUTE_GUARDED_BY_RLS",
    "TASK_ENQUEUES",
    "TASK_CONSUMES",
    "PRODUCES_PAYLOAD",
    "CONSUMES_PAYLOAD",
    "SCHEMA_DEFINED_BY_MIGRATION",
    "MIGRATION_PRECEDES",
    "DECLARES_DEP",
    "RESOLVES_TO",
    "PEER_OF",
    "IMPORTS_PACKAGE",
    "READS_ENV_VAR",
    "WRITES_ENV_VAR",
    "DEFINED_BY_CONFIG",
    "RENDERED_BY_PROMPT",
    "PROMPT_DECLARES_VAR",
    "PROMPT_USES_VAR",
    "IMPLEMENTS_OPENAPI_OP",
    "CONSUMES_OPENAPI_OP",
    "SCHEMA_OF",
    "NEXT_ROUTE_GUARDED_BY_MIDDLEWARE",
    "NEXT_ROUTE_USES_LAYOUT",
    "WORKFLOW_USES_SECRET",
    "SERVICE_DEPENDS_ON",
    "STAGE_COPIES_PATH",
]
