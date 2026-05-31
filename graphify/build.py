# assemble node+edge dicts into a NetworkX graph, preserving edge direction
#
# Node deduplication — three layers:
#
# 1. Within a file (AST): each extractor tracks a `seen_ids` set. A node ID is
#    emitted at most once per file, so duplicate class/function definitions in
#    the same source file are collapsed to the first occurrence.
#
# 2. Between files (build): NetworkX G.add_node() is idempotent — calling it
#    twice with the same ID overwrites the attributes with the second call's
#    values. Nodes are added in extraction order (AST first, then semantic),
#    so if the same entity is extracted by both passes the semantic node
#    silently overwrites the AST node. This is intentional: semantic nodes
#    carry richer labels and cross-file context, while AST nodes have precise
#    source_location. If you need to change the priority, reorder extractions
#    passed to build().
#
# 3. Semantic merge (skill): before calling build(), the skill merges cached
#    and new semantic results using an explicit `seen` set keyed on node["id"],
#    so duplicates across cache hits and new extractions are resolved there
#    before any graph construction happens.
#
from __future__ import annotations
import json
import hashlib
import os
import re
import sys
import unicodedata
from collections.abc import Hashable
from pathlib import Path
import networkx as nx
from .edge_identity import make_stable_key, strip_schema_key
from .validate import is_hashable, validate_extraction


# Synonym mapper for known invalid file_type values that LLM subagents commonly
# emit. Keeps semantic intent close (markdown→document, tool→code) and falls
# back to "concept" for any other invalid value (see #840).
_LANG_FAMILY: dict[str, str] = {
    ".py": "py",
    ".pyi": "py",
    ".js": "js",
    ".mjs": "js",
    ".cjs": "js",
    ".jsx": "js",
    ".ts": "js",
    ".tsx": "js",
    ".go": "go",
    ".rs": "rs",
    ".java": "jvm",
    ".kt": "jvm",
    ".scala": "jvm",
    ".groovy": "jvm",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".rb": "rb",
    ".php": "php",
    ".cs": "cs",
    ".swift": "swift",
    ".lua": "lua",
}


_FILE_TYPE_SYNONYMS = {
    "markdown": "document",
    "text": "document",
    "tool": "code",
    "library": "code",
    "pattern": "concept",
    "principle": "concept",
    "constraint": "concept",
    "tech": "concept",
    "technology": "concept",
    "data-source": "concept",
    "data_source": "concept",
    "gotcha": "concept",
    "framework": "concept",
}


def _normalize_id(s: str) -> str:
    r"""Normalize an ID string the same way extract._make_id does.

    Used to reconcile edge endpoints when the LLM generates IDs with slightly
    different punctuation or casing than the AST extractor. Must stay in sync
    with extract._make_id — NFKC normalization, \w with re.UNICODE, underscore
    collapse, and casefold must all match (#811).
    """
    s = unicodedata.normalize("NFKC", s)
    cleaned = re.sub(r"[^\w]+", "_", s, flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_").casefold()


def _norm_source_file(p: str | None, root: str | None = None) -> str | None:
    """Normalize path separators and relativize absolute paths.

    Converts backslashes to forward slashes (Windows compatibility) and, when
    root is provided, strips the absolute prefix from paths produced by semantic
    subagents so source_file is always repo-relative (fixes #932).
    """
    if not p:
        return p
    p = p.replace("\\", "/")
    if root and os.path.isabs(p):
        try:
            p = Path(p).relative_to(root).as_posix()
        except ValueError:
            pass
    return p


def _stable_identity_component(value: object) -> str | None:
    """Normalize malformed edge identity values before stable-key hashing."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, os.PathLike):
        # os.fspath can return bytes for bytes-flavored PathLike; coerce to str
        # so downstream json.dumps / hashing always sees text.
        fs_value = os.fspath(value)
        return (
            fs_value.decode("utf-8", errors="replace") if isinstance(fs_value, bytes) else fs_value
        )
    if isinstance(value, (set, frozenset)):
        return json.dumps(sorted(str(item) for item in value), ensure_ascii=False)
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def _make_collision_key(base_key: str, attrs: dict, *, salt: int = 0) -> str:
    payload = {
        "base_key": base_key,
        "attrs": attrs,
    }
    if salt:
        payload["salt"] = salt
    repair_payload = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    repair_digest = hashlib.sha256(repair_payload.encode()).hexdigest()
    return f"{base_key}:alt:{repair_digest}"


def _list_field(data: dict, key: str) -> list:
    """Return ``data[key]`` if it is a list; otherwise warn to stderr and return ``[]``.

    Extraction dicts come from LLM subagents and can contain malformed shapes;
    matching the rest of build_from_json's skip+warn policy keeps a single bad
    field from crashing the whole build.
    """
    value = data.get(key, [])
    if isinstance(value, list):
        return value
    print(
        f"[graphify] WARNING: extraction field '{key}' must be a list, "
        f"got {type(value).__name__}; treating as empty.",
        file=sys.stderr,
    )
    return []


def edge_data(G: nx.Graph, u: Hashable, v: Hashable) -> dict:
    """Return one edge attribute dict for (u, v), tolerating MultiGraph.

    For MultiGraph/MultiDiGraph there can be multiple parallel edges;
    this returns the first one (sufficient for callers that only need
    relation/confidence for rendering). Fixes #796.
    """
    raw = G[u][v]
    if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)):
        return next(iter(raw.values()), {})
    return raw


def edge_datas(G: nx.Graph, u: Hashable, v: Hashable) -> list[dict]:
    """Return every edge attribute dict for (u, v); always a list."""
    raw = G[u][v]
    if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)):
        return list(raw.values())
    return [raw]


def build_from_json(
    extraction: dict,
    *,
    directed: bool = False,
    root: str | Path | None = None,
    multigraph: bool = False,
) -> nx.Graph | nx.DiGraph | nx.MultiDiGraph:
    """Build a NetworkX graph from an extraction dict.

    directed=True produces a DiGraph that preserves edge direction (source→target).
    directed=False (default) produces an undirected Graph for backward compatibility.
    multigraph=True produces a directed MultiDiGraph with keyed parallel edges for
        internal tests/callers; public CLI exposure is intentionally deferred.
        In this mode, directed is ignored because MultiDiGraph is always directed.
    root: if given, absolute source_file paths from semantic subagents are made
        relative to root so all nodes share a consistent path key (#932).
    """
    if not isinstance(extraction, dict):
        raise TypeError("extraction must be a JSON object")

    _root = str(Path(root).resolve()) if root else None
    # NetworkX <= 3.1 serialised edges as "links"; remap to "edges" for compatibility.
    if "edges" not in extraction and "links" in extraction:
        extraction = dict(extraction, edges=extraction["links"])

    nodes = _list_field(extraction, "nodes")
    edges = _list_field(extraction, "edges")
    extraction = dict(extraction, nodes=nodes, edges=edges)

    # Canonicalize legacy node/edge schema before validation.
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if "source" in node and "source_file" not in node:
            # Count edges that reference this node so the warning is actionable (#479)
            node_id = node.get("id", "?")
            affected_edges = sum(
                1
                for e in edges
                if isinstance(e, dict)
                and (e.get("source") == node_id or e.get("target") == node_id)
            )
            print(
                f"[graphify] WARNING: node '{node_id}' uses field 'source' instead of "
                f"'source_file' — {affected_edges} edge(s) may be misrouted. "
                f"Rename the field to 'source_file' to silence this warning.",
                file=sys.stderr,
            )
            node["source_file"] = node.pop("source")
        # Default missing/None file_type to "concept" so legacy graph.json
        # entries (and stub nodes preserved by `_rebuild_code` from older
        # graphify versions that didn't always populate file_type) don't
        # trigger spurious "invalid file_type 'None'" validator warnings (#660).
        if node.get("file_type") in (None, ""):
            node["file_type"] = "concept"
        ft = node.get("file_type", "")
        if ft and ft not in {"code", "document", "paper", "image", "rationale", "concept"}:
            node["file_type"] = _FILE_TYPE_SYNONYMS.get(ft, "concept")

    errors = validate_extraction(extraction)
    # Dangling edges (stdlib/external imports) are expected - only warn about real schema errors.
    real_errors = [e for e in errors if "does not match any node id" not in e]
    if real_errors:
        print(
            f"[graphify] Extraction warning ({len(real_errors)} issues): {real_errors[0]}",
            file=sys.stderr,
        )
    if multigraph:
        from .multigraph_compat import require_multigraph_capabilities

        require_multigraph_capabilities()
    G: nx.Graph = nx.MultiDiGraph() if multigraph else nx.DiGraph() if directed else nx.Graph()
    for node in nodes:
        if not isinstance(node, dict) or "id" not in node:
            continue
        node_id = node["id"]
        if not is_hashable(node_id):
            continue
        if "source_file" in node:
            node["source_file"] = _norm_source_file(
                _stable_identity_component(node["source_file"]), _root
            )
        node_attrs = {k: v for k, v in node.items() if k != "id"}
        # Reject node ids that JSON-serialize but won't round-trip to the same
        # hashable type. Tuples serialize as JSON arrays and come back as lists
        # (unhashable), so they cannot be used as NetworkX node ids after a
        # save/load cycle even though json.dumps would accept them.
        if isinstance(node_id, (list, tuple, set, frozenset, dict)):
            print(
                f"[graphify] WARNING: node id {node_id!r} ({type(node_id).__name__}) "
                f"would not round-trip through JSON as the same hashable type; skipping.",
                file=sys.stderr,
            )
            continue
        # Check id AND attrs are JSON-serializable. NetworkX allows hashable but
        # non-JSON-safe ids (e.g., custom objects); accepting them here would
        # break later node_link_data + json.dump.
        try:
            json.dumps({"id": node_id, **node_attrs}, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            print(
                f"[graphify] WARNING: node {node_id!r} has non-JSON-serializable "
                f"id or attrs ({exc}); skipping.",
                file=sys.stderr,
            )
            continue
        G.add_node(node_id, **node_attrs)
    node_set = set(G.nodes())
    # Normalized ID map: lets edges survive when the LLM generates IDs with
    # slightly different casing or punctuation than the AST extractor.
    # e.g. "Session_ValidateToken" maps to "session_validatetoken".
    norm_to_id: dict[str, Hashable] = {
        _normalize_id(nid): nid for nid in node_set if isinstance(nid, str)
    }
    multigraph_groups: dict[tuple[Hashable, Hashable, str], list[dict]] = {}
    multigraph_explicit_keys: set[tuple[Hashable, Hashable, str]] = set()
    multigraph_diagnostics = {"exact_duplicate_edges": 0, "key_collision_edges": 0}

    # Iterate edges in a deterministic order. The graph is undirected and stores
    # direction in _src/_tgt; when two edges collapse onto the same node pair the
    # last write wins, so an unstable iteration order flips _src/_tgt run-to-run
    # and makes the serialized graph churn. Sorting also stabilizes multigraph
    # key-collision grouping before keyed emission.
    def _edge_sort_key(edge: object) -> tuple[str, str, str, str]:
        if not isinstance(edge, dict):
            return ("", "", "", repr(edge))
        return (
            str(edge.get("source", edge.get("from", ""))),
            str(edge.get("target", edge.get("to", ""))),
            str(edge.get("relation", "")),
            json.dumps(edge, sort_keys=True, ensure_ascii=False, default=str),
        )

    for edge in sorted(edges, key=_edge_sort_key):
        if not isinstance(edge, dict):
            continue
        if "source" not in edge and "from" in edge:
            edge["source"] = edge["from"]
        if "target" not in edge and "to" in edge:
            edge["target"] = edge["to"]
        if "source" not in edge or "target" not in edge:
            continue
        src, tgt = edge["source"], edge["target"]
        srcis_hashable = is_hashable(src)
        tgtis_hashable = is_hashable(tgt)
        if not srcis_hashable or not tgtis_hashable:
            endpoint = "source" if not srcis_hashable else "target"
            endpoint_value = src if not srcis_hashable else tgt
            print(
                "[graphify] WARNING: skipped edge with unhashable "
                f"{endpoint} endpoint ({type(endpoint_value).__name__})",
                file=sys.stderr,
            )
            continue
        # Remap mismatched IDs via normalization before dropping the edge.
        if isinstance(src, str) and src not in node_set:
            src = norm_to_id.get(_normalize_id(src), src)
        if isinstance(tgt, str) and tgt not in node_set:
            tgt = norm_to_id.get(_normalize_id(tgt), tgt)
        if src not in node_set or tgt not in node_set:
            continue  # skip edges to external/stdlib nodes - expected, not an error
        # Exclude legacy from/to alongside source/target so they don't survive
        # as ordinary edge attrs after legacy-shape remap above.
        base_attrs = {k: v for k, v in edge.items() if k not in ("source", "target", "from", "to")}
        raw_key, attrs = strip_schema_key(base_attrs)
        if "source_file" in attrs:
            attrs["source_file"] = _norm_source_file(
                _stable_identity_component(attrs["source_file"]), _root
            )
        # Drop cross-language INFERRED `calls` edges — same short names (render,
        # parse, etc.) appear across language boundaries in multi-language chunks,
        # producing phantom edges that don't represent real call relationships.
        if attrs.get("relation") == "calls" and attrs.get("confidence") == "INFERRED":
            src_ext = Path(G.nodes[src].get("source_file") or "").suffix.lower()
            tgt_ext = Path(G.nodes[tgt].get("source_file") or "").suffix.lower()
            if src_ext and tgt_ext and _LANG_FAMILY.get(src_ext) != _LANG_FAMILY.get(tgt_ext):
                continue
        # Preserve original edge direction - undirected graphs lose it otherwise,
        # causing display functions to show edges backwards.
        attrs["_src"] = src
        attrs["_tgt"] = tgt
        # Refuse to store any edge whose attrs cannot round-trip through JSON.
        # Mutating attrs in place would silently change the user's stored value;
        # skipping with a warning matches the rest of the build's defensive policy
        # and prevents later json.dump crashes during export, identically in
        # simple-graph and multigraph modes.
        try:
            json.dumps(attrs, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            print(
                f"[graphify] WARNING: edge ({src}->{tgt}) has non-JSON-serializable "
                f"attrs ({exc}); skipping.",
                file=sys.stderr,
            )
            continue
        if multigraph:
            if raw_key is not None and not isinstance(raw_key, str):
                raise TypeError(
                    f"multigraph edge 'key' must be a string, got "
                    f"{type(raw_key).__name__} ({raw_key!r})"
                )
            base_key = (
                raw_key
                if raw_key is not None
                else make_stable_key(
                    _stable_identity_component(attrs.get("relation")),
                    _stable_identity_component(attrs.get("source_file")),
                    _stable_identity_component(attrs.get("source_location")),
                )
            )
            if raw_key is not None:
                multigraph_explicit_keys.add((src, tgt, base_key))
            multigraph_groups.setdefault((src, tgt, base_key), []).append(dict(attrs))
        else:
            # When the graph is undirected and the same node pair appears twice with
            # the same relation but opposite directions (e.g. a `calls` b and b `calls` a),
            # nx.Graph collapses them into one edge. The deterministic sort above means
            # the lexicographically-later direction would systematically overwrite the
            # earlier one's _src/_tgt, silently flipping the surviving edge's caller
            # and callee. First-seen direction wins instead — drop the redundant
            # reverse-direction duplicate so the original direction is preserved (#1061).
            if not G.is_directed() and G.has_edge(src, tgt):
                existing = edge_data(G, src, tgt)
                if existing.get("relation") == attrs.get("relation") and (
                    existing.get("_src") == tgt and existing.get("_tgt") == src
                ):
                    continue
            G.add_edge(src, tgt, **attrs)
    if multigraph:
        singleton_groups: list[tuple[Hashable, Hashable, str, dict]] = []
        multi_groups: list[tuple[Hashable, Hashable, str, list[dict]]] = []
        used_keys_by_pair: dict[tuple[Hashable, Hashable], set[str]] = {}
        for (src, tgt, base_key), group_attrs in multigraph_groups.items():
            unique_attrs: list[dict] = []
            seen_attr_fingerprints: set[str] = set()
            for attrs in group_attrs:
                attr_fingerprint = json.dumps(
                    attrs, sort_keys=True, ensure_ascii=False, default=str
                )
                if attr_fingerprint in seen_attr_fingerprints:
                    multigraph_diagnostics["exact_duplicate_edges"] += 1
                else:
                    seen_attr_fingerprints.add(attr_fingerprint)
                    unique_attrs.append(attrs)
            if len(unique_attrs) > 1:
                multigraph_diagnostics["key_collision_edges"] += 1
                unique_attrs.sort(
                    key=lambda attrs: json.dumps(
                        attrs, sort_keys=True, ensure_ascii=False, default=str
                    )
                )
                multi_groups.append((src, tgt, base_key, unique_attrs))
            elif unique_attrs:
                # Reserve the singleton's base_key so any later multi-attr
                # collision-repair on the same (src, tgt) avoids it.
                used_keys_by_pair.setdefault((src, tgt), set()).add(base_key)
                singleton_groups.append((src, tgt, base_key, unique_attrs[0]))
        # Sort both lists deterministically.
        singleton_groups.sort(
            key=lambda item: (
                repr(item[0]),
                repr(item[1]),
                item[2],
                json.dumps(item[3], sort_keys=True, ensure_ascii=False, default=str),
            )
        )
        multi_groups.sort(
            key=lambda item: (
                repr(item[0]),
                repr(item[1]),
                item[2],
                json.dumps(item[3], sort_keys=True, ensure_ascii=False, default=str),
            )
        )
        # Emit singletons first: they use base_key directly and were reserved
        # in the pre-loop above, so collision-repair from multi groups will
        # see those reservations and salt around them.
        for src, tgt, base_key, attrs in singleton_groups:
            G.add_edge(src, tgt, key=base_key, **attrs)
        # Then emit multi-attr groups with collision-repair salting against
        # both reserved singleton base_keys and earlier multi-group repair
        # keys on the same (src, tgt) pair.
        for src, tgt, base_key, unique_attrs in multi_groups:
            used_keys = used_keys_by_pair.setdefault((src, tgt), set())
            preserve_explicit = (src, tgt, base_key) in multigraph_explicit_keys
            for index, attrs in enumerate(unique_attrs):
                # When the user passed an explicit `key` shared across multiple
                # distinct edges, preserve it on the first emit so at least one
                # edge per group keeps the canonical user-supplied key.
                # Derived base_keys (from make_stable_key) always go through
                # collision-repair so emission stays order-independent.
                if preserve_explicit and index == 0 and base_key not in used_keys:
                    key = base_key
                else:
                    key = _make_collision_key(base_key, attrs)
                    salt = 0
                    while key in used_keys:
                        salt += 1
                        key = _make_collision_key(base_key, attrs, salt=salt)
                used_keys.add(key)
                G.add_edge(src, tgt, key=key, **attrs)
    hyperedges = extraction.get("hyperedges", [])
    if hyperedges:
        G.graph["hyperedges"] = hyperedges
    if multigraph:
        G.graph["graphify_multigraph_diagnostics"] = multigraph_diagnostics
    return G


def build(
    extractions: list[dict],
    *,
    directed: bool = False,
    dedup: bool = True,
    dedup_llm_backend: str | None = None,
    root: str | Path | None = None,
    multigraph: bool = False,
) -> nx.Graph | nx.DiGraph | nx.MultiDiGraph:
    """Merge multiple extraction results into one graph.

    directed=True produces a DiGraph that preserves edge direction (source→target).
    directed=False (default) produces an undirected Graph for backward compatibility.
    dedup=True (default) runs entity deduplication before building the graph.
    dedup_llm_backend: if set (e.g. "gemini", "claude", or "kimi"), uses LLM to resolve
        ambiguous pairs in the 75–92 Jaro-Winkler score zone.
    root: if given, absolute source_file paths are made relative to root (#932).

    Extractions are merged in order. For nodes with the same ID, the last
    extraction's attributes win (NetworkX add_node overwrites). Pass AST
    results before semantic results so semantic labels take precedence, or
    reverse the order if you prefer AST source_location precision to win.
    """
    from graphify.dedup import deduplicate_entities

    combined = _combine_extractions(extractions)
    dedup_diagnostics: dict = {}
    if dedup and combined["nodes"]:
        combined["nodes"], combined["edges"] = deduplicate_entities(
            combined["nodes"],
            combined["edges"],
            communities={},
            dedup_llm_backend=dedup_llm_backend,
            diagnostics=dedup_diagnostics,
        )
    G = build_from_json(combined, directed=directed, root=root, multigraph=multigraph)
    if multigraph and dedup_diagnostics:
        existing = G.graph.get("graphify_multigraph_diagnostics", {})
        existing.update(dedup_diagnostics)
        G.graph["graphify_multigraph_diagnostics"] = existing
    return G


def _combine_extractions(extractions: list[dict]) -> dict:
    combined: dict = {
        "nodes": [],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    for ext in extractions:
        combined["nodes"].extend(ext.get("nodes", []))
        combined["edges"].extend(ext.get("edges", []))
        combined["hyperedges"].extend(ext.get("hyperedges", []))
        combined["input_tokens"] += ext.get("input_tokens", 0)
        combined["output_tokens"] += ext.get("output_tokens", 0)
    return combined


def _norm_label(label: str) -> str:
    """Canonical dedup key — Unicode-aware, preserves CJK/word characters."""
    label = unicodedata.normalize("NFKC", label)
    return re.sub(r"[\W_ ]+", " ", label.casefold(), flags=re.UNICODE).strip()


def deduplicate_by_label(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Merge nodes that share a normalised label, rewriting edge references.

    Prefers IDs without chunk suffixes (_c\\d+) and shorter IDs when tied.
    Drops self-loops created by the merge. Called in build() automatically.
    """
    _CHUNK_SUFFIX = re.compile(r"_c\d+$")
    canonical: dict[str, dict] = {}  # norm_label -> surviving node
    remap: dict[str, str] = {}  # old_id -> surviving_id

    for node in nodes:
        key = _norm_label(node.get("label", node.get("id", "")))
        if not key:
            continue
        existing = canonical.get(key)
        if existing is None:
            canonical[key] = node
        else:
            has_suffix = bool(_CHUNK_SUFFIX.search(node["id"]))
            existing_has_suffix = bool(_CHUNK_SUFFIX.search(existing["id"]))
            if has_suffix and not existing_has_suffix:
                remap[node["id"]] = existing["id"]
            elif existing_has_suffix and not has_suffix:
                remap[existing["id"]] = node["id"]
                canonical[key] = node
            elif len(node["id"]) < len(existing["id"]):
                remap[existing["id"]] = node["id"]
                canonical[key] = node
            else:
                remap[node["id"]] = existing["id"]

    if not remap:
        return nodes, edges

    print(f"[graphify] Deduplicated {len(remap)} duplicate node(s) by label.", file=sys.stderr)
    deduped_nodes = list(canonical.values())
    deduped_edges = []
    for edge in edges:
        e = dict(edge)
        e["source"] = remap.get(e["source"], e["source"])
        e["target"] = remap.get(e["target"], e["target"])
        if e["source"] != e["target"]:
            deduped_edges.append(e)
    return deduped_nodes, deduped_edges


def _chunk_has_graph_records(chunk: dict) -> bool:
    return bool(
        chunk.get("nodes") or chunk.get("edges") or chunk.get("links") or chunk.get("hyperedges")
    )


def build_merge(
    new_chunks: list[dict],
    graph_path: str | Path = "graphify-out/graph.json",
    prune_sources: list[str] | None = None,
    *,
    directed: bool | None = None,
    dedup: bool = True,
    dedup_llm_backend: str | None = None,
    root: str | Path | None = None,
    multigraph: bool | None = None,
) -> nx.Graph | nx.DiGraph | nx.MultiDiGraph:
    """Load existing graph.json, merge new chunks into it, and return the merged graph.

    Persistence is the caller's responsibility (e.g., via ``export.to_json``);
    this function does not write back to disk.

    Never replaces - only grows (or prunes deleted-file nodes via prune_sources).
    Safe to call repeatedly: existing nodes and edges are preserved.
    root: if given, absolute source_file paths in new_chunks are made relative (#932).

    ``directed`` defaults to inheriting the saved graph's flag when an
    existing graph.json is present, so updating a directed simple graph with
    default args no longer silently downgrades it to undirected.

    ``multigraph`` likewise defaults to inheriting the saved graph's flag. When
    the saved graph.json has ``multigraph: true`` the merge produces a
    MultiDiGraph that preserves keyed parallel edges end-to-end — existing edges
    keep their stored ``key`` (so distinct parallel edges between the same pair
    survive the re-feed), new chunks are merged without collapsing parallels, and
    the result round-trips back out as multigraph. There is no silent fallback to
    simple-graph behavior.
    """
    graph_path = Path(graph_path)
    if graph_path.exists():
        # Read JSON directly instead of going through node_link_graph().
        # The latter rebuilds an undirected nx.Graph and then enumerating
        # edges() yields endpoints based on node insertion order, which
        # silently flips directional edges (e.g. `calls`) when the callee
        # was inserted before the caller. The _src/_tgt direction-preserving
        # attrs are popped before saving in export.py, so going through the
        # NetworkX round-trip loses direction permanently (#760).
        from graphify.security import check_graph_file_size_cap

        check_graph_file_size_cap(graph_path)
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError(
                f"saved graph.json at {graph_path} must be a JSON object, got {type(data).__name__}"
            )
        # Honor the saved graph's `multigraph` flag so a stateful update of a
        # multigraph graph.json preserves keyed parallel edges instead of
        # collapsing to a simple graph. Existing edges keep their stored `key`
        # when re-fed through build(multigraph=True), so distinct parallel edges
        # between the same node pair survive the merge round-trip.
        saved_multigraph = data.get("multigraph", False)
        if saved_multigraph is not True and saved_multigraph is not False:
            raise TypeError(
                f"'multigraph' in {graph_path} must be a boolean, "
                f"got {type(saved_multigraph).__name__} ({saved_multigraph!r})"
            )
        if multigraph is None:
            multigraph = saved_multigraph
        elif multigraph != saved_multigraph:
            print(
                f"[graphify] WARNING: build_merge multigraph={multigraph} overrides "
                f"saved graph.json multigraph={saved_multigraph}",
                file=sys.stderr,
            )
        # Honor the saved graph's `directed` flag unless the caller explicitly
        # overrides. Without this, an update with default args on a directed
        # graph silently downgrades it and loses edge direction on next export.
        saved_directed_raw = data.get("directed", False)
        if saved_directed_raw is not True and saved_directed_raw is not False:
            raise TypeError(
                f"'directed' in {graph_path} must be a boolean, "
                f"got {type(saved_directed_raw).__name__} ({saved_directed_raw!r})"
            )
        saved_directed = saved_directed_raw
        if directed is None:
            directed = saved_directed
        elif directed != saved_directed:
            print(
                f"[graphify] WARNING: build_merge directed={directed} overrides "
                f"saved graph.json directed={saved_directed}",
                file=sys.stderr,
            )
        links_key = "links" if "links" in data else "edges"
        existing_nodes = list(data.get("nodes", []))
        existing_edges = list(data.get(links_key, []))
        base = [{"nodes": existing_nodes, "edges": existing_edges}]
    else:
        if directed is None:
            directed = False
        if multigraph is None:
            multigraph = False
        existing_nodes = []
        base = []

    incoming_chunks = list(new_chunks)
    incoming_has_records = any(_chunk_has_graph_records(chunk) for chunk in incoming_chunks)
    dedup_diagnostics: dict = {}
    if graph_path.exists() and dedup:
        effective_dedup = False
        if incoming_has_records:
            from graphify.dedup import deduplicate_entities

            incoming = _combine_extractions(incoming_chunks)
            if incoming["nodes"]:
                incoming["nodes"], incoming["edges"] = deduplicate_entities(
                    incoming["nodes"],
                    incoming["edges"],
                    communities={},
                    dedup_llm_backend=dedup_llm_backend,
                    diagnostics=dedup_diagnostics,
                )
            all_chunks = base + [incoming]
        else:
            all_chunks = base + incoming_chunks
    else:
        effective_dedup = dedup
        all_chunks = base + incoming_chunks
    G = build(
        all_chunks,
        directed=directed,
        dedup=effective_dedup,
        dedup_llm_backend=dedup_llm_backend,
        root=root,
        multigraph=multigraph,
    )
    if multigraph and dedup_diagnostics:
        existing = G.graph.get("graphify_multigraph_diagnostics", {})
        existing.update(dedup_diagnostics)
        G.graph["graphify_multigraph_diagnostics"] = existing

    # Prune nodes and edges from deleted source files
    if prune_sources:
        # Build a set containing both the raw form (matches nodes that kept
        # absolute source_file) and the normalised relative form (matches nodes
        # that were relativised by _norm_source_file at build time).
        # .resolve() handles symlinked roots and redundant ".." / "./" segments
        # so Path.relative_to() succeeds even when the scan root is a symlink.
        # (#1007: manifest absolute paths vs graph relative source_file mismatch)
        _root_str = str(Path(root).resolve()) if root is not None else None
        prune_set: set[str] = set()
        for p in prune_sources:
            if not p:
                continue
            prune_set.add(p)
            norm = _norm_source_file(p, _root_str)
            if norm:
                prune_set.add(norm)
        to_remove = [n for n, d in G.nodes(data=True) if d.get("source_file") in prune_set]
        G.remove_nodes_from(to_remove)
        n_files = len(prune_sources)
        n_nodes = len(to_remove)
        if n_nodes:
            print(
                f"[graphify] Pruned {n_nodes} node(s) from {n_files} deleted source file(s).",
                file=sys.stderr,
            )

        # Prune edges belonging to changed/deleted source files. On a
        # MultiDiGraph a single (u, v) pair can carry MULTIPLE parallel edges
        # from DIFFERENT source files, so removal MUST be keyed: drop only the
        # parallel edges whose source_file is in prune_set and leave parallel
        # edges from other files between the same pair intact. The two-tuple
        # remove_edges_from used by simple graphs would drop only one edge per
        # pair on a multigraph (first key) and could evict the wrong file's edge.
        # remove_all_parallel_edges is deliberately NOT used here — it is too
        # broad and would delete other-file parallels between the same pair.
        if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)):
            keyed_to_remove = [
                (u, v, k)
                for u, v, k, d in G.edges(keys=True, data=True)
                if d.get("source_file") in prune_set
            ]
            for u, v, k in keyed_to_remove:
                G.remove_edge(u, v, key=k)
            n_edges_removed = len(keyed_to_remove)
        else:
            edges_to_remove = [
                (u, v) for u, v, d in G.edges(data=True) if d.get("source_file") in prune_set
            ]
            if edges_to_remove:
                G.remove_edges_from(edges_to_remove)
            n_edges_removed = len(edges_to_remove)
        if n_edges_removed:
            print(
                f"[graphify] Pruned {n_edges_removed} edge(s) from deleted source file(s).",
                file=sys.stderr,
            )

        if not n_nodes and not n_edges_removed:
            print(
                f"[graphify] {n_files} source file(s) deleted since last run — "
                f"no matching nodes or edges in graph, already clean.",
                file=sys.stderr,
            )

    # Safety check: refuse to shrink the graph silently (#479).
    # Stateful dedup applies only to incoming chunks, so only explicit pruning
    # may reduce the saved graph's node count.
    if graph_path.exists() and not prune_sources:
        existing_n = len(existing_nodes)
        new_n = G.number_of_nodes()
        if new_n < existing_n:
            raise ValueError(
                f"graphify: build_merge would shrink graph from {existing_n} → {new_n} nodes. "
                f"Pass prune_sources explicitly if you intend to remove nodes."
            )

    # No write to graph_path here; persistence is the caller's responsibility.
    return G


def prefix_graph_for_global(G: nx.Graph, repo_tag: str) -> nx.Graph:
    """Return a copy of G with all node IDs prefixed with repo_tag::.

    Labels are preserved unchanged (for display). A 'local_id' attribute
    is added to each node so the original ID can be recovered. Edges are
    rewritten to match the new prefixed IDs. The 'repo' attribute is set
    on every node.
    """
    relabel = {n: f"{repo_tag}::{n}" for n in G.nodes}
    H = nx.relabel_nodes(G, relabel, copy=True)
    for node, data in H.nodes(data=True):
        data["repo"] = repo_tag
        data.setdefault("local_id", node.split("::", 1)[1])
    return H


def prune_repo_from_graph(G: nx.Graph, repo_tag: str) -> int:
    """Remove all nodes tagged with repo_tag from G in-place. Returns count removed."""
    to_remove = [n for n, d in G.nodes(data=True) if d.get("repo") == repo_tag]
    G.remove_nodes_from(to_remove)
    return len(to_remove)
