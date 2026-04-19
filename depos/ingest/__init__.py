"""Layer-0 ingest registry."""
from __future__ import annotations

from typing import Callable

import networkx as nx

from depos.analysis.schemas import IngestReport

Ingestor = Callable[..., IngestReport]


def _load_ingestors() -> list[Ingestor]:
    from depos.ingest.env_config import ingest as ingest_env_config
    from depos.ingest.infra import ingest as ingest_infra
    from depos.ingest.manifests import ingest as ingest_manifests
    from depos.ingest.nextjs_routes import ingest as ingest_nextjs_routes
    from depos.ingest.openapi import ingest as ingest_openapi
    from depos.ingest.prompts import ingest as ingest_prompts

    return [
        ingest_manifests,
        ingest_env_config,
        ingest_prompts,
        ingest_openapi,
        ingest_nextjs_routes,
        ingest_infra,
    ]


INGESTORS = _load_ingestors()


def ingest_all(graph: nx.DiGraph, *, repo_root, config) -> list[IngestReport]:
    reports: list[IngestReport] = []
    for ingestor in INGESTORS:
        try:
            report = ingestor(graph, repo_root=repo_root, config=config)
        except Exception as exc:  # noqa: BLE001
            report = IngestReport(module=ingestor.__module__, errors=[{"path": str(repo_root), "kind": "ingest_exception", "message": str(exc)}])
        reports.append(report)
    return reports


__all__ = ["INGESTORS", "ingest_all"]
