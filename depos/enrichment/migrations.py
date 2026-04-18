"""Module 1: migration sequencer.

Reads the configured migration glob (default ``supabase/migrations/*.sql``)
and emits:

- ``SCHEMA_DEFINED_BY_MIGRATION`` edges from each referenced table (synth
  node ``sql:table:<name>``) to a synth migration node
  ``sql:migration:<filename>``.
- ``MIGRATION_PRECEDES`` edges between consecutive migrations sorted by
  their lexical filename (Supabase timestamps make this correct by
  construction).

Each edge carries ``migration_id`` and ``migration_order`` so the
verifier's migration-awareness checks can answer "does this table exist
in this branch yet?" without replaying SQL.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import networkx as nx

from depos.analysis.config import IntelligenceConfig
from depos.analysis.schemas import ContractKind, SemanticEdgeMetadata
from depos.enrichment.semantic_edges import (
    MIGRATION_PRECEDES,
    SCHEMA_DEFINED_BY_MIGRATION,
)


_CREATE_TABLE = re.compile(
    r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?(?P<table>[a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)
_DROP_TABLE = re.compile(
    r"drop\s+table\s+(?:if\s+exists\s+)?(?:public\.)?(?P<table>[a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)


def _find_migrations(config: IntelligenceConfig) -> list[Path]:
    return sorted(Path().glob(config.migration_glob))


def _table_ops_in(text: str) -> list[tuple[str, str]]:
    """Return list of (op, table) tuples where op is 'create' or 'drop'."""
    stripped = re.sub(r"--[^\n]*", "", text)
    ops: list[tuple[str, str]] = []
    for m in _CREATE_TABLE.finditer(stripped):
        ops.append(("create", m.group("table").lower()))
    for m in _DROP_TABLE.finditer(stripped):
        ops.append(("drop", m.group("table").lower()))
    return ops


def emit_migration_edges(graph: nx.DiGraph, *, config: IntelligenceConfig) -> int:
    migrations = _find_migrations(config)
    if not migrations:
        return 0

    prev_mig_node: str | None = None
    added = 0
    for order, path in enumerate(migrations):
        mig_node = f"sql:migration:{path.name}"
        if not graph.has_node(mig_node):
            graph.add_node(
                mig_node,
                label=path.name,
                file_type="sql_migration",
                synthetic=True,
                source_file=str(path),
                migration_order=order,
            )
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        for op, table in _table_ops_in(text):
            table_node = f"sql:table:{table}"
            if not graph.has_node(table_node):
                graph.add_node(
                    table_node,
                    label=table,
                    file_type="sql_table",
                    synthetic=True,
                )
            metadata = SemanticEdgeMetadata(
                confidence=1.0,
                inferred=False,
                source_system="postgres",
                target_system="postgres",
                contract_kind=ContractKind.schema,
                table_name=table,
                migration_id=path.name,
                migration_order=order,
                branch_visible=(op == "create"),
            )
            graph.add_edge(
                table_node,
                mig_node,
                key=f"schema:{op}:{path.name}",
                relation=SCHEMA_DEFINED_BY_MIGRATION,
                **metadata.model_dump(mode="json"),
            )
            added += 1

        if prev_mig_node is not None:
            graph.add_edge(
                prev_mig_node,
                mig_node,
                key=f"precedes:{path.name}",
                relation=MIGRATION_PRECEDES,
                migration_order=order,
                migration_id=path.name,
            )
            added += 1
        prev_mig_node = mig_node

    return added


__all__ = ["emit_migration_edges"]
