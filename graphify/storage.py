"""NeuG graph database adapter for graphify.

Provides an optional parallel storage engine alongside NetworkX.
All functions are guarded by `import neug` — when NeuG is not installed,
callers should catch ImportError and skip silently.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

import neug

from .build import _FILE_TYPE_SYNONYMS, _normalize_id, _norm_source_file
from .validate import VALID_FILE_TYPES

# ---------------------------------------------------------------------------
# Node tables (one per file_type)
# ---------------------------------------------------------------------------

_NODE_TABLES = {
    "code": """CREATE NODE TABLE IF NOT EXISTS code (
        id STRING PRIMARY KEY, label STRING,
        source_file STRING, source_location STRING, community INT64)""",
    "document": """CREATE NODE TABLE IF NOT EXISTS document (
        id STRING PRIMARY KEY, label STRING,
        source_file STRING, community INT64)""",
    "paper": """CREATE NODE TABLE IF NOT EXISTS paper (
        id STRING PRIMARY KEY, label STRING,
        source_file STRING, community INT64)""",
    "image": """CREATE NODE TABLE IF NOT EXISTS image (
        id STRING PRIMARY KEY, label STRING,
        source_file STRING, community INT64)""",
    "concept": """CREATE NODE TABLE IF NOT EXISTS concept (
        id STRING PRIMARY KEY, label STRING,
        source_file STRING, community INT64)""",
    "rationale": """CREATE NODE TABLE IF NOT EXISTS rationale (
        id STRING PRIMARY KEY, label STRING,
        source_file STRING, community INT64)""",
}

# ---------------------------------------------------------------------------
# Edge tables — split by (src_type, tgt_type, relation).
# ---------------------------------------------------------------------------

_EDGE_DDL_TEMPLATE = """CREATE REL TABLE IF NOT EXISTS {tbl}(
    FROM {src} TO {tgt},
    relation STRING, confidence STRING,
    confidence_score DOUBLE, source_file STRING, weight DOUBLE)"""

# Known relation types per (src, tgt) pair — pre-built at init time.
_KNOWN_RELATIONS: dict[tuple[str, str], list[str]] = {
    ("code", "code"): [
        "calls", "contains", "method", "uses", "inherits", "defines",
        "references", "imports", "imports_from", "listened_by", "case_of",
        "references_constant", "bound_to", "uses_static_prop", "uses_config",
    ],
    ("rationale", "code"): ["rationale_for"],
}

_created_rel_tables: set[str] = set()


def _sanitize_rel_name(relation: str) -> str:
    """Normalize a relation string into a safe table-name suffix."""
    r = relation.lower().strip()
    r = re.sub(r"[^a-z0-9_]", "_", r)
    r = re.sub(r"_+", "_", r).strip("_")
    return r or "rel"


def _edge_table_name(src_type: str, tgt_type: str, relation: str) -> str:
    return f"edge_{src_type}_{tgt_type}_{_sanitize_rel_name(relation)}"


# ---------------------------------------------------------------------------
# Cypher string escaping
# ---------------------------------------------------------------------------


def _cesc(value: str) -> str:
    return (
        value
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_db(db_path: str) -> tuple[neug.Database, object]:
    """Open (or create) a NeuG database and connect."""
    db = neug.Database(db_path)
    conn = db.connect()
    return db, conn


def ensure_schema(conn: object) -> None:
    """Create node/edge tables if not exist. Call once during extract."""
    for ddl in _NODE_TABLES.values():
        conn.execute(ddl)

    _created_rel_tables.clear()

    for (src, tgt), rels in _KNOWN_RELATIONS.items():
        for rel in rels:
            tbl = _edge_table_name(src, tgt, rel)
            conn.execute(_EDGE_DDL_TEMPLATE.format(tbl=tbl, src=src, tgt=tgt))
            _created_rel_tables.add(tbl)


def _ensure_rel_table(conn: object, src_type: str, tgt_type: str, relation: str) -> str:
    """Resolve edge table name, creating on-the-fly if needed. Returns table name."""
    tbl = _edge_table_name(src_type, tgt_type, relation)
    if tbl in _created_rel_tables:
        return tbl
    conn.execute(_EDGE_DDL_TEMPLATE.format(tbl=tbl, src=src_type, tgt=tgt_type))
    _created_rel_tables.add(tbl)
    return tbl


def _fix_file_type(ft: str | None) -> str:
    """Canonicalize file_type, matching build.py:138-146 logic."""
    if not ft or ft not in VALID_FILE_TYPES:
        return _FILE_TYPE_SYNONYMS.get(ft, "concept") if ft else "concept"
    return ft


def ingest_extraction(
    conn: object,
    extraction: dict,
    *,
    incremental: bool = False,
    prune_sources: list[str] | None = None,
    root: str | Path | None = None,
) -> None:
    """Write an extraction dict into NeuG.

    incremental=False: first build — uses CREATE (faster).
    incremental=True:  update — uses MERGE (upsert).
    """
    _root = str(Path(root).resolve()) if root else None

    # --- prune deleted/changed files first ---
    if prune_sources:
        for sf in prune_sources:
            sf_norm = _norm_source_file(sf, _root) or sf
            for tbl in _NODE_TABLES:
                conn.execute(
                    f"MATCH (n:{tbl}) WHERE n.source_file = '{_cesc(sf_norm)}' "
                    f"DETACH DELETE n"
                )

    # --- build node lookup: id -> file_type ---
    node_types: dict[str, str] = {}
    nodes = extraction.get("nodes") or []
    edges = extraction.get("edges") or []

    # --- write nodes ---
    _written_ids: set[str] = set()
    _n_errors = 0
    for node in nodes:
        nid = _normalize_id(node.get("id", ""))
        if not nid:
            continue
        ft = _fix_file_type(node.get("file_type"))
        label = node.get("label", "")
        sf = _norm_source_file(node.get("source_file"), _root) or ""
        sl = node.get("source_location") or ""
        node_types[nid] = ft
        if nid in _written_ids:
            continue
        _written_ids.add(nid)

        try:
            if incremental:
                existing = list(conn.execute(
                    f"MATCH (n:{ft} {{id: '{_cesc(nid)}'}}) RETURN n.id"
                ))
                if existing:
                    props = f"n.label = '{_cesc(label)}', n.source_file = '{_cesc(sf)}'"
                    if ft == "code":
                        props += f", n.source_location = '{_cesc(sl)}'"
                    conn.execute(
                        f"MATCH (n:{ft} {{id: '{_cesc(nid)}'}}) SET {props}"
                    )
                else:
                    if ft == "code":
                        conn.execute(
                            f"CREATE (n:code {{id: '{_cesc(nid)}', "
                            f"label: '{_cesc(label)}', "
                            f"source_file: '{_cesc(sf)}', "
                            f"source_location: '{_cesc(sl)}'}})"
                        )
                    else:
                        conn.execute(
                            f"CREATE (n:{ft} {{id: '{_cesc(nid)}', "
                            f"label: '{_cesc(label)}', "
                            f"source_file: '{_cesc(sf)}'}})"
                        )
            else:
                if ft == "code":
                    conn.execute(
                        f"CREATE (n:code {{id: '{_cesc(nid)}', "
                        f"label: '{_cesc(label)}', "
                        f"source_file: '{_cesc(sf)}', "
                        f"source_location: '{_cesc(sl)}'}})"
                    )
                else:
                    conn.execute(
                        f"CREATE (n:{ft} {{id: '{_cesc(nid)}', "
                        f"label: '{_cesc(label)}', "
                        f"source_file: '{_cesc(sf)}'}})"
                    )
        except RuntimeError:
            _n_errors += 1

    # --- write edges ---
    _e_errors = 0
    for edge in edges:
        src_key = edge.get("source") or edge.get("from", "")
        tgt_key = edge.get("target") or edge.get("to", "")
        src_id = _normalize_id(src_key)
        tgt_id = _normalize_id(tgt_key)
        if not src_id or not tgt_id:
            continue

        src_ft = node_types.get(src_id)
        tgt_ft = node_types.get(tgt_id)
        if not src_ft or not tgt_ft:
            continue

        rel_raw = edge.get("relation", "")
        conf_raw = edge.get("confidence", "")
        tbl = _ensure_rel_table(conn, src_ft, tgt_ft, rel_raw)
        rel = _cesc(rel_raw)
        conf = _cesc(conf_raw)
        conf_score = float(edge.get("confidence_score", 0.0))
        e_sf = _cesc(_norm_source_file(edge.get("source_file"), _root) or "")
        weight = float(edge.get("weight", 1.0))

        try:
            conn.execute(
                f"MATCH (a:{src_ft} {{id: '{_cesc(src_id)}'}}), "
                f"(b:{tgt_ft} {{id: '{_cesc(tgt_id)}'}}) "
                f"CREATE (a)-[:{tbl} {{relation: '{rel}', confidence: '{conf}', "
                f"confidence_score: {conf_score}, source_file: '{e_sf}', "
                f"weight: {weight}}}]->(b)"
            )
        except RuntimeError:
            _e_errors += 1

    if _n_errors or _e_errors:
        import logging
        logging.getLogger(__name__).warning(
            "NeuG ingest: %d node(s) and %d edge(s) skipped due to errors",
            _n_errors, _e_errors,
        )


def ingest_communities(
    conn: object,
    communities: dict[int, list[str]],
    community_labels: dict[int, str] | None = None,
) -> None:
    """Write community assignments into NeuG node properties."""
    for cid, node_ids in communities.items():
        for nid in node_ids:
            nid_norm = _normalize_id(nid)
            if not nid_norm:
                continue
            for tbl in _NODE_TABLES:
                conn.execute(
                    f"MATCH (n:{tbl}) WHERE n.id = '{_cesc(nid_norm)}' "
                    f"SET n.community = {int(cid)}"
                )


def execute_cypher(conn: object, query: str) -> list[list]:
    """Execute a Cypher query and return results as list of lists."""
    try:
        return list(conn.execute(query))
    except RuntimeError as exc:
        raise RuntimeError(f"Cypher query failed: {exc}") from exc


def close_db(db: neug.Database, conn: object) -> None:
    """Close the NeuG connection and database."""
    conn.close()
    db.close()
