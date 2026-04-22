"""Module 1: RLS resolver.

Reads SQL migration files (``supabase/migrations/*.sql`` by default) to
build an in-memory model of RLS status per table, then emits
``ROUTE_GUARDED_BY_RLS`` edges from route handlers to the tables they
touch. Annotations use the :class:`depos.analysis.schemas.RLSCoverage`
enum (``full`` / ``partial_operation`` / ``none``).

Fallback posture when the project has no SQL migrations:
- We do not claim ``none`` (which would imply "we proved there is no
  RLS"). Instead, no edge is emitted for those routes and a run-level
  flag ``needs_manual_rls_config`` is set on ``graph.graph['run_metadata']``
  so the verifier knows to apply inferred-edge confidence floors.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import networkx as nx

from depos.analysis.schemas import (
    ContractKind,
    RLSCoverage,
    SemanticEdgeMetadata,
)
from depos.graph_relations import ROUTE_GUARDED_BY_RLS


# ---------------------------------------------------------------------------
# SQL parsing (regex-based; good enough for supabase migrations)
# ---------------------------------------------------------------------------

_ENABLE_RLS = re.compile(
    r"alter\s+table\s+(?:only\s+)?(?:public\.)?(?P<table>[a-zA-Z_][a-zA-Z0-9_]*)\s+enable\s+row\s+level\s+security",
    re.IGNORECASE,
)
_DISABLE_RLS = re.compile(
    r"alter\s+table\s+(?:only\s+)?(?:public\.)?(?P<table>[a-zA-Z_][a-zA-Z0-9_]*)\s+disable\s+row\s+level\s+security",
    re.IGNORECASE,
)
_FORCE_RLS = re.compile(
    r"alter\s+table\s+(?:only\s+)?(?:public\.)?(?P<table>[a-zA-Z_][a-zA-Z0-9_]*)\s+force\s+row\s+level\s+security",
    re.IGNORECASE,
)
_CREATE_POLICY = re.compile(
    r"create\s+policy\s+(?P<pol>[\"'a-zA-Z_][\"'a-zA-Z0-9_ ]*)\s+on\s+(?:public\.)?(?P<table>[a-zA-Z_][a-zA-Z0-9_]*)"
    r"(?:\s+as\s+(?P<perm>permissive|restrictive))?"
    r"(?:\s+for\s+(?P<cmd>all|select|insert|update|delete))?",
    re.IGNORECASE,
)


@dataclass
class _TableRLS:
    table: str
    enabled: bool = False
    forced: bool = False
    policy_count: int = 0
    policies: list[dict] = field(default_factory=list)


def _scan_sql(text: str, tables: dict[str, _TableRLS]) -> None:
    stripped = re.sub(r"--[^\n]*", "", text)
    for m in _ENABLE_RLS.finditer(stripped):
        t = m.group("table").lower()
        tables.setdefault(t, _TableRLS(table=t)).enabled = True
    for m in _DISABLE_RLS.finditer(stripped):
        t = m.group("table").lower()
        tables.setdefault(t, _TableRLS(table=t)).enabled = False
    for m in _FORCE_RLS.finditer(stripped):
        t = m.group("table").lower()
        tables.setdefault(t, _TableRLS(table=t)).forced = True
    for m in _CREATE_POLICY.finditer(stripped):
        t = m.group("table").lower()
        row = tables.setdefault(t, _TableRLS(table=t))
        row.policy_count += 1
        row.policies.append(
            {
                "name": m.group("pol").strip("'\""),
                "permissive": (m.group("perm") or "permissive").lower() == "permissive",
                "command": (m.group("cmd") or "all").lower(),
            }
        )


def build_table_model(migration_files: Iterable[Path]) -> dict[str, _TableRLS]:
    tables: dict[str, _TableRLS] = {}
    for path in migration_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        _scan_sql(text, tables)
    return tables


def classify(row: Optional[_TableRLS]) -> Optional[RLSCoverage]:
    """Return the RLSCoverage enum for a table, or ``None`` if unknown."""
    if row is None:
        return None
    if not row.enabled:
        return RLSCoverage.none
    if row.policy_count == 0:
        return RLSCoverage.partial_operation
    return RLSCoverage.full


# ---------------------------------------------------------------------------
# Graph wiring
# ---------------------------------------------------------------------------


def _find_migration_files(
    graph: nx.DiGraph,
    default_glob: str = "supabase/migrations/*.sql",
    repo_root: Optional[Path] = None,
) -> list[Path]:
    meta_glob = graph.graph.get("migration_glob") or default_glob
    base = repo_root or Path()
    return sorted(base.glob(meta_glob))


def _iter_route_table_pairs(graph: nx.DiGraph, repo_root: Optional[Path] = None) -> Iterable[tuple[str, str]]:
    table_name_re = re.compile(
        r"\b(?:from|into|update|join)\s+(?:public\.)?([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE
    )
    for nid, attrs in graph.nodes(data=True):
        if not attrs.get("is_fastapi_route"):
            continue
        sf = attrs.get("source_file")
        if not sf:
            continue
        try:
            path = Path(sf)
            if not path.is_absolute() and repo_root is not None:
                path = repo_root / path
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        seen: set[str] = set()
        for m in table_name_re.finditer(text):
            t = m.group(1).lower()
            if t in seen:
                continue
            seen.add(t)
            yield nid, t


def emit_rls_edges(graph: nx.DiGraph, *, repo_root: Optional[Path] = None) -> int:
    migration_files = _find_migration_files(graph, repo_root=repo_root)
    tables = build_table_model(migration_files)

    graph.graph.setdefault("run_metadata", {})
    if not migration_files:
        graph.graph["run_metadata"]["needs_manual_rls_config"] = True

    added = 0
    for handler_id, table_name in _iter_route_table_pairs(graph, repo_root=repo_root):
        coverage = classify(tables.get(table_name))
        attrs = graph.nodes[handler_id]
        per_table = attrs.setdefault("rls_coverage_per_table", {})
        per_table[table_name] = coverage.value if coverage else "unknown"

        table_node_id = f"sql:table:{table_name}"
        if not graph.has_node(table_node_id):
            graph.add_node(
                table_node_id,
                label=table_name,
                file_type="sql_table",
                synthetic=True,
            )

        inferred = coverage is None
        metadata = SemanticEdgeMetadata(
            confidence=0.4 if inferred else 1.0,
            inferred=inferred,
            source_system="python",
            target_system="postgres",
            contract_kind=ContractKind.rls,
            table_name=table_name,
            rls_coverage=coverage,
        )
        graph.add_edge(
            handler_id,
            table_node_id,
            key=f"rls:{table_name}",
            relation=ROUTE_GUARDED_BY_RLS,
            **metadata.model_dump(mode="json"),
        )
        added += 1
    return added


__all__ = ["emit_rls_edges", "build_table_model", "classify"]
